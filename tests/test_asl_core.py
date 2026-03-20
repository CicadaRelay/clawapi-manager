"""Tests for ASL core modules: action_cost, budget_gate, action_queue, cost_estimator, elastic_router.

Uses fakeredis to simulate Redis without a running server.
"""

import sys
import os
import pytest

# Ensure lib/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import fakeredis

from lib.action_cost import (
    ActionCostVector,
    ActionFormulator,
    ActionSource,
    Complexity,
    ScheduleStatus,
    compute_priority_score,
    _complexity_to_tier,
)
from lib.budget_gate import BudgetGate, ReservationStatus, BUDGET_KEY, ASL_BUDGET
from lib.action_queue import ActionQueue
from lib.cost_estimator import CostEstimator
from lib.elastic_router import ElasticRouter


@pytest.fixture
def r():
    """Fresh fakeredis instance per test."""
    client = fakeredis.FakeRedis(decode_responses=False)
    # Set default budget: $0.50/hr
    client.hset(BUDGET_KEY, mapping={
        "hourlySpent": "0",
        "hourlyLimit": "0.50",
        "dailySpent": "0",
        "dailyLimit": "10",
        "monthlySpent": "0",
        "monthlyLimit": "200",
        "modelTier": "standard",
    })
    return client


@pytest.fixture
def formulator():
    return ActionFormulator()


def _make_action(
    priority=50, complexity=Complexity.MEDIUM, cost=0.01,
    tokens=5000, degradable=True, min_model="free",
    category="general", source=ActionSource.OMC,
) -> ActionCostVector:
    """Helper to create test actions."""
    return ActionCostVector(
        action_id=f"test-{priority}-{complexity.value}",
        task_id="task-1",
        source=source,
        tokens_est=tokens,
        latency_ms_est=3000,
        cost_usd_est=cost,
        context_window_pct=0.05,
        priority=priority,
        complexity=complexity,
        category=category,
        deadline_ms=0,
        degradable=degradable,
        min_model=min_model,
    )


# ============================================================
# ActionCostVector tests
# ============================================================

class TestActionCostVector:
    def test_frozen(self):
        action = _make_action()
        with pytest.raises(AttributeError):
            action.priority = 99  # type: ignore

    def test_to_dict_roundtrip(self):
        action = _make_action(priority=75, complexity=Complexity.EXPENSIVE)
        d = action.to_dict()
        assert d["source"] == "omc"
        assert d["complexity"] == "expensive"
        restored = ActionCostVector.from_dict(d)
        assert restored.priority == 75
        assert restored.complexity == Complexity.EXPENSIVE

    def test_complexity_to_tier(self):
        assert _complexity_to_tier(Complexity.FREE) == "free"
        assert _complexity_to_tier(Complexity.MEDIUM) == "standard"
        assert _complexity_to_tier(Complexity.EXPENSIVE) == "premium"


class TestActionFormulator:
    def test_formulate_basic(self, formulator):
        action = formulator.formulate(
            task_id="t1",
            source=ActionSource.FSC,
            prompt_tokens=1000,
            category="implementation",
            complexity=Complexity.EXPENSIVE,
            priority=80,
        )
        assert action.tokens_est > 1000  # output tokens added
        assert action.cost_usd_est > 0
        assert action.priority == 80
        assert action.source == ActionSource.FSC

    def test_formulate_free_zero_cost(self, formulator):
        action = formulator.formulate(
            task_id="t2",
            source=ActionSource.OMC,
            prompt_tokens=500,
            complexity=Complexity.FREE,
        )
        assert action.cost_usd_est == 0.0

    def test_context_window_pct_capped(self, formulator):
        action = formulator.formulate(
            task_id="t3",
            source=ActionSource.A2A,
            prompt_tokens=500_000,  # Very large
            complexity=Complexity.FREE,  # 32k context
        )
        assert action.context_window_pct <= 1.0


class TestPriorityScore:
    def test_higher_priority_higher_score(self):
        low = _make_action(priority=20)
        high = _make_action(priority=90)
        assert compute_priority_score(high) > compute_priority_score(low)

    def test_cheaper_gets_efficiency_bonus(self):
        cheap = _make_action(priority=50, cost=0.001)
        expensive = _make_action(priority=50, cost=0.05)
        assert compute_priority_score(cheap) > compute_priority_score(expensive)


# ============================================================
# BudgetGate tests
# ============================================================

class TestBudgetGate:
    def test_reserve_approved(self, r):
        gate = BudgetGate(r)
        action = _make_action(cost=0.01)
        result = gate.reserve(action)
        assert result.status == ReservationStatus.APPROVED
        assert result.reserved_cost == 0.01

    def test_reserve_deferred_when_exhausted(self, r):
        gate = BudgetGate(r)
        # Spend most of the budget
        r.hset(BUDGET_KEY, "hourlySpent", "0.48")
        action = _make_action(cost=0.05)
        result = gate.reserve(action)
        assert result.status == ReservationStatus.DEFERRED

    def test_reserve_rejected_rate(self, r):
        gate = BudgetGate(r, max_reservation_pct=0.1)
        # Single action > 10% of $0.50 = $0.05
        action = _make_action(cost=0.10)
        result = gate.reserve(action)
        assert result.status == ReservationStatus.REJECTED_RATE

    def test_reconcile_updates_spent(self, r):
        gate = BudgetGate(r)
        action = _make_action(cost=0.01)
        gate.reserve(action)

        gate.reconcile(action.action_id, actual_cost=0.008, actual_tokens=4500)

        # Reservation should be cleared
        pending = gate.pending_reservations()
        assert action.action_id not in pending

        # hourlySpent should be updated
        spent = float(r.hget(BUDGET_KEY, "hourlySpent") or 0)
        assert abs(spent - 0.008) < 0.001

    def test_cancel_reservation(self, r):
        gate = BudgetGate(r)
        action = _make_action(cost=0.02)
        gate.reserve(action)

        assert gate.cancel_reservation(action.action_id)
        assert action.action_id not in gate.pending_reservations()

    def test_headroom_calculation(self, r):
        gate = BudgetGate(r)
        # Fresh budget: headroom = 100%
        assert gate.get_headroom() == 1.0

        # Spend half
        r.hset(BUDGET_KEY, "hourlySpent", "0.25")
        assert abs(gate.get_headroom() - 0.5) < 0.01

    def test_concurrent_reservations_atomic(self, r):
        """Two reservations that together exceed budget — second should defer."""
        gate = BudgetGate(r)
        r.hset(BUDGET_KEY, "hourlySpent", "0.40")

        a1 = _make_action(cost=0.05)
        a2 = ActionCostVector(
            action_id="test-concurrent-2",
            task_id="task-1", source=ActionSource.OMC,
            tokens_est=5000, latency_ms_est=3000,
            cost_usd_est=0.05, context_window_pct=0.05,
            priority=50, complexity=Complexity.MEDIUM,
            category="general", deadline_ms=0,
        )

        r1 = gate.reserve(a1)
        r2 = gate.reserve(a2)

        assert r1.status == ReservationStatus.APPROVED
        assert r2.status == ReservationStatus.DEFERRED


# ============================================================
# ActionQueue tests
# ============================================================

class TestActionQueue:
    def test_enqueue_dequeue_priority_order(self, r):
        q = ActionQueue(r)
        low = _make_action(priority=20, cost=0.01)
        high = _make_action(priority=90, cost=0.01)

        q.enqueue(low)
        q.enqueue(high)

        # Highest priority should come out first
        first = q.dequeue()
        assert first is not None
        assert first.priority == 90

    def test_depth(self, r):
        q = ActionQueue(r)
        assert q.depth() == 0
        q.enqueue(_make_action(priority=50))
        assert q.depth() == 1

    def test_evict_lowest(self, r):
        q = ActionQueue(r)
        q.enqueue(_make_action(priority=20, cost=0.001))
        q.enqueue(_make_action(priority=80, cost=0.01))

        evicted = q.evict_lowest(count=1)
        assert len(evicted) == 1
        assert q.depth() == 1
        assert q.deferred_count() == 1

    def test_restore_deferred(self, r):
        q = ActionQueue(r)
        q.enqueue(_make_action(priority=20, cost=0.001))
        q.evict_lowest(count=1)

        assert q.depth() == 0
        restored = q.restore_deferred()
        assert restored == 1
        assert q.depth() == 1

    def test_clear(self, r):
        q = ActionQueue(r)
        q.enqueue(_make_action(priority=50))
        q.enqueue(_make_action(priority=60, cost=0.02))
        q.clear()
        assert q.depth() == 0


# ============================================================
# CostEstimator tests
# ============================================================

class TestCostEstimator:
    def test_cold_start_returns_none(self, r):
        est = CostEstimator(r)
        result = est.estimate("analysis", "medium", 1000)
        # Less than 5 samples → returns None
        assert result is None

    def test_update_and_estimate(self, r):
        est = CostEstimator(r)
        # Feed 10 samples
        for _ in range(10):
            est.update("analysis", "medium",
                       prompt_tokens=1000, output_tokens=2500,
                       latency_ms=5000)

        result = est.estimate("analysis", "medium", 1000)
        assert result is not None
        assert result["tokens_est"] > 1000
        assert result["latency_ms_est"] > 0

    def test_get_stats(self, r):
        est = CostEstimator(r)
        est.update("testing", "free", 500, 1000, 2000)
        stats = est.get_stats("testing", "free")
        assert stats is not None
        assert stats["sample_count"] == 1

    def test_reset(self, r):
        est = CostEstimator(r)
        est.update("general", "medium", 1000, 2000, 3000)
        est.reset("general", "medium")
        assert est.get_stats("general", "medium") is None


# ============================================================
# ElasticRouter tests
# ============================================================

class TestElasticRouter:
    def test_normal_headroom_uses_natural_tier(self, r):
        gate = BudgetGate(r)
        router = ElasticRouter(gate)

        action = _make_action(priority=50, complexity=Complexity.EXPENSIVE, cost=0.01)
        decision = router.route(action)

        assert decision.status == ScheduleStatus.DISPATCH
        assert decision.model_tier == "premium"

    def test_pressure_downgrades_low_priority(self, r):
        gate = BudgetGate(r)
        router = ElasticRouter(gate)

        # 35% headroom (pressure zone)
        r.hset(BUDGET_KEY, "hourlySpent", "0.325")

        action = _make_action(
            priority=50, complexity=Complexity.EXPENSIVE,
            cost=0.01, degradable=True,
        )
        decision = router.route(action)

        assert decision.status == ScheduleStatus.DISPATCH
        assert decision.model_tier == "standard"  # Downgraded

    def test_pressure_keeps_high_priority(self, r):
        gate = BudgetGate(r)
        router = ElasticRouter(gate)

        r.hset(BUDGET_KEY, "hourlySpent", "0.325")

        action = _make_action(
            priority=85, complexity=Complexity.EXPENSIVE, cost=0.01,
        )
        decision = router.route(action)

        assert decision.status == ScheduleStatus.DISPATCH
        assert decision.model_tier == "premium"  # Kept

    def test_non_degradable_respects_min_model(self, r):
        gate = BudgetGate(r)
        router = ElasticRouter(gate)

        # Pressure zone (40% headroom) — enough for premium re-estimation
        r.hset(BUDGET_KEY, "hourlySpent", "0.30")

        action = _make_action(
            priority=50, complexity=Complexity.EXPENSIVE,
            cost=0.005, degradable=False, min_model="standard",
        )
        decision = router.route(action)

        assert decision.status == ScheduleStatus.DISPATCH
        # Should not go below min_model
        tier_idx = ["free", "economy", "standard", "premium"].index(decision.model_tier)
        min_idx = ["free", "economy", "standard", "premium"].index("standard")
        assert tier_idx >= min_idx

    def test_critical_headroom_defers_low_priority(self, r):
        gate = BudgetGate(r)
        router = ElasticRouter(gate)

        # 5% headroom (critical)
        r.hset(BUDGET_KEY, "hourlySpent", "0.475")

        action = _make_action(priority=50, complexity=Complexity.MEDIUM, cost=0.005)
        decision = router.route(action)

        assert decision.status == ScheduleStatus.DEFER
