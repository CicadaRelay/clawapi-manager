"""ASL Elastic Router — dynamic model selection under budget pressure.

Analogous to ARL-Tangram's elastic Degree-of-Parallelism (DoP) selection:
instead of statically assigning GPU counts, we dynamically select model
tiers per-action based on real-time budget headroom.

Integrates with:
- mesh_bridge.py: reads budget state from Redis fsc:budget
- smart_router.py: resolves model names within tiers
- budget_gate.py: reserves cost before dispatch
- action_queue.py: evicts low-priority actions when needed
"""

from __future__ import annotations

import os
from typing import Optional

from .action_cost import (
    ActionCostVector,
    ScheduleDecision,
    ScheduleStatus,
    MODEL_PRICING,
    _complexity_to_tier,
)
from .budget_gate import BudgetGate


# Model tier hierarchy (ordered cheapest → most expensive)
TIER_ORDER = ["free", "economy", "standard", "premium"]

# Default model names per tier (aligned with mesh_bridge.MESH_TIERS)
TIER_MODELS: dict[str, str] = {
    "premium": "claude-sonnet-4",
    "standard": "doubao-seed-2.0-code",
    "economy": "minimax-2.5",
    "free": "openrouter/free",
}

# Environment overrides
_ENV_MODELS = {
    "premium": "ASL_MODEL_PREMIUM",
    "standard": "ASL_MODEL_STANDARD",
    "economy": "ASL_MODEL_ECONOMY",
    "free": "ASL_MODEL_FREE",
}


def _resolve_model(tier: str) -> str:
    """Resolve model name for a tier, checking env overrides."""
    env_key = _ENV_MODELS.get(tier)
    if env_key:
        override = os.getenv(env_key)
        if override:
            return override
    return TIER_MODELS.get(tier, TIER_MODELS["free"])


class ElasticRouter:
    """Select model tier per-action based on real-time budget state.

    Budget headroom zones:
      > 60%  : Normal — use complexity-appropriate model
      30-60% : Pressure — downgrade non-critical expensive actions
      10-30% : High pressure — most actions go to free/economy
      < 10%  : Critical — only priority >= 95 actions, free models only

    This replaces the static model assignment in agent definitions
    with dynamic selection that responds to budget consumption.
    """

    def __init__(self, budget_gate: BudgetGate):
        self._gate = budget_gate

    def route(self, action: ActionCostVector) -> ScheduleDecision:
        """Determine model tier and reserve budget for an action.

        Args:
            action: The action to route.

        Returns:
            ScheduleDecision with model assignment and reservation.
        """
        headroom = self._gate.get_headroom()
        target_tier = self._select_tier(action, headroom)

        if target_tier is None:
            return ScheduleDecision(
                action_id=action.action_id,
                status=ScheduleStatus.DEFER,
                model_tier="",
                model="",
                reservation_id="",
                reserved_cost=0,
                estimated_wait_ms=_estimate_wait(headroom),
                reason=f"headroom {headroom:.1%} too low for priority {action.priority}",
            )

        # Re-estimate cost at the selected tier (may differ from original estimate)
        adjusted_cost = _estimate_cost_at_tier(action.tokens_est, target_tier)

        # Reserve budget
        adjusted_action = ActionCostVector(
            action_id=action.action_id,
            task_id=action.task_id,
            source=action.source,
            tokens_est=action.tokens_est,
            latency_ms_est=action.latency_ms_est,
            cost_usd_est=adjusted_cost,
            context_window_pct=action.context_window_pct,
            priority=action.priority,
            complexity=action.complexity,
            category=action.category,
            deadline_ms=action.deadline_ms,
            agent_name=action.agent_name,
            degradable=action.degradable,
            min_model=action.min_model,
        )

        reservation = self._gate.reserve(adjusted_action)

        if reservation.status.value == "approved":
            return ScheduleDecision(
                action_id=action.action_id,
                status=ScheduleStatus.DISPATCH,
                model_tier=target_tier,
                model=_resolve_model(target_tier),
                reservation_id=action.action_id,
                reserved_cost=reservation.reserved_cost,
                estimated_wait_ms=0,
                reason="ok",
            )
        elif reservation.status.value == "deferred":
            return ScheduleDecision(
                action_id=action.action_id,
                status=ScheduleStatus.DEFER,
                model_tier=target_tier,
                model="",
                reservation_id="",
                reserved_cost=0,
                estimated_wait_ms=_estimate_wait(headroom),
                reason=reservation.reason,
            )
        else:
            return ScheduleDecision(
                action_id=action.action_id,
                status=ScheduleStatus.REJECT,
                model_tier="",
                model="",
                reservation_id="",
                reserved_cost=0,
                estimated_wait_ms=0,
                reason=reservation.reason,
            )

    def _select_tier(self, action: ActionCostVector, headroom: float) -> Optional[str]:
        """Core elastic selection algorithm.

        Maps budget headroom to model tier, respecting agent's
        degradable flag and min_model constraint.
        """
        natural_tier = _complexity_to_tier(action.complexity)

        if headroom > 0.6:
            # Normal zone — use requested tier
            selected = natural_tier
        elif headroom > 0.3:
            # Pressure zone — downgrade expensive non-critical actions
            if natural_tier == "premium" and action.priority < 80 and action.degradable:
                selected = "standard"
            else:
                selected = natural_tier
        elif headroom > 0.1:
            # High pressure — aggressive downgrade
            if action.priority >= 90:
                selected = min_tier("standard", natural_tier)
            elif action.degradable:
                selected = "free"
            else:
                selected = natural_tier
        else:
            # Critical — only highest priority, free models
            if action.priority >= 95:
                selected = "free" if action.degradable else min_tier("economy", natural_tier)
            else:
                return None  # Defer

        # Enforce min_model constraint
        selected = enforce_min_model(selected, action.min_model)

        return selected


def enforce_min_model(selected: str, min_model: str) -> str:
    """Ensure selected tier is not below agent's minimum."""
    sel_idx = TIER_ORDER.index(selected) if selected in TIER_ORDER else 0
    min_idx = TIER_ORDER.index(min_model) if min_model in TIER_ORDER else 0
    if sel_idx < min_idx:
        return min_model
    return selected


def min_tier(a: str, b: str) -> str:
    """Return the cheaper of two tiers."""
    a_idx = TIER_ORDER.index(a) if a in TIER_ORDER else 0
    b_idx = TIER_ORDER.index(b) if b in TIER_ORDER else 0
    return a if a_idx <= b_idx else b


def _estimate_cost_at_tier(tokens: int, tier: str) -> float:
    """Re-estimate USD cost at a specific tier."""
    rate = MODEL_PRICING.get(tier, 5.0)
    return round(tokens * rate / 1_000_000, 6)


def _estimate_wait(headroom: float) -> float:
    """Estimate how long until budget headroom recovers (ms).

    Rough heuristic: lower headroom → longer wait (up to budget reset).
    """
    if headroom > 0.3:
        return 0
    # Linear interpolation: 0% headroom → 60min wait, 30% → 0
    minutes = (0.3 - headroom) / 0.3 * 60
    return minutes * 60 * 1000
