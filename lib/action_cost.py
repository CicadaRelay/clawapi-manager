"""ASL Action Cost Vector — action-level resource modeling for LLM API calls.

Inspired by ARL-Tangram's vectorized cost representation, each LLM API call
is modeled as an ActionCostVector before dispatch. This enables:
1. Pre-dispatch cost estimation (vs current post-hoc tracking)
2. Priority-based scheduling across FSC/A2A/OMC sources
3. Elastic model selection under budget pressure
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass
from enum import Enum


class ActionSource(str, Enum):
    FSC = "fsc"
    A2A = "a2a"
    OMC = "omc"


class Complexity(str, Enum):
    FREE = "free"
    MEDIUM = "medium"
    EXPENSIVE = "expensive"


class ScheduleStatus(str, Enum):
    DISPATCH = "dispatch"
    DEFER = "defer"
    REJECT = "reject"


# Reuse pricing from a2a-dev/src/cost_tracker.py DEFAULT_PRICING
# Keyed by model tier, not agent name — maps to mesh_bridge MESH_TIERS
MODEL_PRICING: dict[str, float] = {
    # $/1M tokens (blended input+output)
    "premium": 15.0,       # Claude Opus/Sonnet
    "standard": 3.0,       # Doubao-seed-2.0-code
    "economy": 1.0,        # MiniMax-2.5
    "free": 0.0,           # OpenRouter free models
}

# Model context window sizes (tokens)
MODEL_CONTEXT_LIMITS: dict[str, int] = {
    "premium": 200_000,
    "standard": 128_000,
    "economy": 128_000,
    "free": 32_000,
}


@dataclass(frozen=True, slots=True)
class ActionCostVector:
    """Vectorized cost representation for a single LLM API call.

    Analogous to ARL-Tangram's C_i = (cpu, gpu, mem, quota),
    but for LLM resources: C_i = (tokens, latency, cost, context%, priority).
    """

    action_id: str
    task_id: str
    source: ActionSource

    # Pre-dispatch estimates
    tokens_est: int
    latency_ms_est: float
    cost_usd_est: float
    context_window_pct: float  # 0.0-1.0

    # Scheduling metadata
    priority: int              # 0-100 (higher = more important)
    complexity: Complexity
    category: str              # "analysis", "implementation", "testing", etc.
    deadline_ms: float         # Monotonic deadline (0 = no deadline)

    # Agent metadata (from cost_profile)
    agent_name: str = ""
    degradable: bool = True
    min_model: str = "free"

    # Post-dispatch actuals (filled by reconciler)
    tokens_actual: int = 0
    cost_usd_actual: float = 0.0
    latency_ms_actual: float = 0.0
    model_used: str = ""
    completed_at: float = 0.0

    def to_dict(self) -> dict:
        """Serialize for Redis HASH storage."""
        d = asdict(self)
        d["source"] = self.source.value
        d["complexity"] = self.complexity.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ActionCostVector:
        """Deserialize from Redis HASH."""
        d["source"] = ActionSource(d["source"])
        d["complexity"] = Complexity(d["complexity"])
        return cls(**d)


@dataclass(frozen=True, slots=True)
class ScheduleDecision:
    """Result of the elastic scheduling process."""

    action_id: str
    status: ScheduleStatus
    model_tier: str          # "premium" / "standard" / "economy" / "free"
    model: str               # Resolved model name
    reservation_id: str      # For BudgetGate tracking
    reserved_cost: float
    estimated_wait_ms: float
    reason: str = ""


class ActionFormulator:
    """Estimate action cost vector from task metadata.

    Uses historical averages (from CostEstimator) when available,
    falls back to heuristic estimation based on prompt token count.
    """

    # Default output/input token ratios by category
    DEFAULT_OUTPUT_RATIOS: dict[str, float] = {
        "analysis": 3.0,        # Analysis produces verbose output
        "implementation": 4.0,  # Code generation is output-heavy
        "testing": 2.5,
        "review": 2.0,
        "planning": 3.0,
        "general": 2.5,
    }

    def __init__(self, estimator=None):
        """
        Args:
            estimator: Optional CostEstimator for learned estimates.
                       Falls back to heuristics if None.
        """
        self._estimator = estimator

    def formulate(
        self,
        *,
        task_id: str,
        source: ActionSource,
        prompt_tokens: int,
        category: str = "general",
        complexity: Complexity = Complexity.MEDIUM,
        priority: int = 50,
        deadline_ms: float = 0,
        agent_name: str = "",
        degradable: bool = True,
        min_model: str = "free",
    ) -> ActionCostVector:
        """Create an ActionCostVector with estimated costs.

        Args:
            task_id: Parent task identifier.
            source: Which system is making the call (FSC/A2A/OMC).
            prompt_tokens: Known input token count (or estimate).
            category: Task category for output ratio lookup.
            complexity: Determines default model tier for cost estimation.
            priority: 0-100, higher = more important.
            deadline_ms: Soft deadline (monotonic clock), 0 = no deadline.
            agent_name: Agent identifier (for cost_profile lookup).
            degradable: Whether model can be downgraded under pressure.
            min_model: Lowest acceptable model tier.
        """
        # Estimate output tokens
        if self._estimator:
            est = self._estimator.estimate(category, complexity.value, prompt_tokens)
            if est is not None:
                tokens_est = est["tokens_est"]
                latency_ms_est = est["latency_ms_est"]
                cost_usd_est = est["cost_usd_est"]
                tier = _complexity_to_tier(complexity)
                ctx_limit = MODEL_CONTEXT_LIMITS.get(tier, 128_000)
                return ActionCostVector(
                    action_id=uuid.uuid4().hex[:16],
                    task_id=task_id,
                    source=source,
                    tokens_est=tokens_est,
                    latency_ms_est=latency_ms_est,
                    cost_usd_est=cost_usd_est,
                    context_window_pct=min(1.0, tokens_est / ctx_limit),
                    priority=priority,
                    complexity=complexity,
                    category=category,
                    deadline_ms=deadline_ms,
                    agent_name=agent_name,
                    degradable=degradable,
                    min_model=min_model,
                )

        # Heuristic fallback
        output_ratio = self.DEFAULT_OUTPUT_RATIOS.get(category, 2.5)
        output_est = int(prompt_tokens * output_ratio)
        tokens_est = prompt_tokens + output_est

        tier = _complexity_to_tier(complexity)
        rate = MODEL_PRICING.get(tier, 5.0)
        cost_usd_est = tokens_est * rate / 1_000_000

        # Latency heuristic: ~30 tokens/sec for premium, ~60 for free
        tokens_per_sec = {"premium": 30, "standard": 50, "economy": 60, "free": 80}
        tps = tokens_per_sec.get(tier, 40)
        latency_ms_est = (output_est / tps) * 1000

        ctx_limit = MODEL_CONTEXT_LIMITS.get(tier, 128_000)

        return ActionCostVector(
            action_id=uuid.uuid4().hex[:16],
            task_id=task_id,
            source=source,
            tokens_est=tokens_est,
            latency_ms_est=latency_ms_est,
            cost_usd_est=round(cost_usd_est, 6),
            context_window_pct=round(min(1.0, tokens_est / ctx_limit), 4),
            priority=priority,
            complexity=complexity,
            category=category,
            deadline_ms=deadline_ms,
            agent_name=agent_name,
            degradable=degradable,
            min_model=min_model,
        )


def _complexity_to_tier(c: Complexity) -> str:
    """Map complexity level to model tier (aligned with mesh_bridge.FREECLAW_TO_MESH)."""
    return {
        Complexity.FREE: "free",
        Complexity.MEDIUM: "standard",
        Complexity.EXPENSIVE: "premium",
    }[c]


def compute_priority_score(action: ActionCostVector, now_ms: float = 0) -> float:
    """Compute scheduling priority score for action queue ordering.

    Score formula (inspired by ARL-Tangram's greedy eviction heuristic):
      score = priority * 40 + urgency * 30 + efficiency * 20 + affinity * 10

    Higher score = scheduled first.
    """
    if now_ms <= 0:
        now_ms = time.monotonic() * 1000

    # Priority component (0-100 → 0-4000)
    priority_score = action.priority * 40

    # Urgency component (how close to deadline)
    if action.deadline_ms > 0:
        remaining = max(0, action.deadline_ms - now_ms)
        total = action.deadline_ms  # Assume deadline is relative from creation
        urgency = max(0, 100 - (remaining / max(total, 1)) * 100)
    else:
        urgency = 50  # Default urgency for no-deadline actions
    urgency_score = urgency * 30

    # Efficiency component (cheaper = higher score)
    efficiency = max(0, 100 - min(100, action.cost_usd_est * 10000))
    efficiency_score = efficiency * 20

    # Affinity bonus (context cache hit) — set externally via context_pool
    # Default 0, caller can add bonus after checking pool
    affinity_score = 0

    return priority_score + urgency_score + efficiency_score + affinity_score
