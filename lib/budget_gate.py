"""ASL Budget Gate — pre-dispatch cost reservation with atomic Redis ops.

Key difference from current post-hoc tracking (cost_monitor.py):
  Current:  dispatch -> execute -> record cost (fire-and-forget)
  ASL:      reserve cost -> dispatch -> execute -> reconcile (release reservation)

This prevents budget overruns when multiple actions dispatch concurrently.
Uses Redis Lua scripts (register_script) for atomicity.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

try:
    import redis
except ImportError:
    redis = None

from .action_cost import ActionCostVector


class ReservationStatus(str, Enum):
    APPROVED = "approved"
    REJECTED_BUDGET = "rejected_budget"
    REJECTED_RATE = "rejected_rate"
    DEFERRED = "deferred"


@dataclass(frozen=True, slots=True)
class ReservationResult:
    status: ReservationStatus
    action_id: str
    reserved_cost: float
    reason: str = ""


# Redis keys
BUDGET_KEY = "fsc:budget"           # Shared with mesh_bridge.py
ASL_RESERVATIONS = "asl:reservations"
ASL_BUDGET = "asl:budget"
ASL_HISTORY = "asl:history"

# Lua script: atomic reserve
_RESERVE_LUA = """
local budget_key = KEYS[1]
local reservations_key = KEYS[2]
local asl_budget_key = KEYS[3]
local action_id = ARGV[1]
local cost_est = tonumber(ARGV[2])
local headroom_floor = tonumber(ARGV[3])
local max_reserve_pct = tonumber(ARGV[4])

-- Read current budget state
local hourly_spent = tonumber(redis.call('HGET', budget_key, 'hourlySpent') or '0')
local hourly_limit = tonumber(redis.call('HGET', budget_key, 'hourlyLimit') or '0.5')
local hourly_reserved = tonumber(redis.call('HGET', asl_budget_key, 'hourlyReserved') or '0')

-- Check single-action cap
local max_single = hourly_limit * max_reserve_pct
if cost_est > max_single and cost_est > 0.001 then
    return {'rejected_rate', '0', 'single action exceeds ' .. max_reserve_pct * 100 .. '% of hourly budget'}
end

-- Check headroom
local committed = hourly_spent + hourly_reserved + cost_est
local headroom = (hourly_limit - committed) / hourly_limit

if headroom < headroom_floor then
    return {'deferred', '0', 'headroom ' .. string.format('%.1f%%', headroom * 100) .. ' below floor'}
end

-- Reserve
redis.call('HSET', reservations_key, action_id, tostring(cost_est))
redis.call('HINCRBYFLOAT', asl_budget_key, 'hourlyReserved', cost_est)
redis.call('HINCRBY', asl_budget_key, 'totalActionsQueued', 1)

return {'approved', tostring(cost_est), 'ok'}
"""

# Lua script: atomic reconcile
_RECONCILE_LUA = """
local budget_key = KEYS[1]
local reservations_key = KEYS[2]
local asl_budget_key = KEYS[3]
local history_key = KEYS[4]
local action_id = ARGV[1]
local actual_cost = tonumber(ARGV[2])
local actual_tokens = ARGV[3]
local model_used = ARGV[4]
local latency_ms = ARGV[5]
local timestamp = ARGV[6]

-- Get and remove reservation
local reserved = tonumber(redis.call('HGET', reservations_key, action_id) or '0')
redis.call('HDEL', reservations_key, action_id)

-- Release reserved amount
if reserved > 0 then
    redis.call('HINCRBYFLOAT', asl_budget_key, 'hourlyReserved', -reserved)
end

-- Record actual cost to fsc:budget (shared with mesh_bridge)
redis.call('HINCRBYFLOAT', budget_key, 'hourlySpent', actual_cost)
redis.call('HINCRBYFLOAT', budget_key, 'dailySpent', actual_cost)
redis.call('HINCRBYFLOAT', budget_key, 'monthlySpent', actual_cost)

-- Update ASL stats
redis.call('HINCRBY', asl_budget_key, 'totalActionsDispatched', 1)

-- Append to history stream (for CostEstimator learning)
redis.call('XADD', history_key, '*',
    'action_id', action_id,
    'cost_reserved', tostring(reserved),
    'cost_actual', tostring(actual_cost),
    'tokens', actual_tokens,
    'model', model_used,
    'latency_ms', latency_ms,
    'timestamp', timestamp
)

return 1
"""

# Lua script: atomic cancel
_CANCEL_LUA = """
local reservations_key = KEYS[1]
local asl_budget_key = KEYS[2]
local action_id = ARGV[1]

local reserved = tonumber(redis.call('HGET', reservations_key, action_id) or '0')
if reserved <= 0 then return 0 end

redis.call('HDEL', reservations_key, action_id)
redis.call('HINCRBYFLOAT', asl_budget_key, 'hourlyReserved', -reserved)
return 1
"""


class BudgetGate:
    """Reserve cost BEFORE dispatch, reconcile AFTER.

    Integrates with the existing fsc:budget HASH (mesh_bridge.py) for
    actual spend tracking, while maintaining separate asl:reservations
    for pending (in-flight) actions.
    """

    def __init__(
        self,
        redis_client: "redis.Redis",
        *,
        headroom_floor: float = 0.05,
        max_reservation_pct: float = 0.3,
    ):
        """
        Args:
            redis_client: Connected Redis client (from mesh_bridge).
            headroom_floor: Reject if headroom ratio below this (default 5%).
            max_reservation_pct: Max % of hourly budget one action can reserve.
        """
        self._r = redis_client
        self._headroom_floor = headroom_floor
        self._max_reservation_pct = max_reservation_pct

        # Register Lua scripts for atomic execution
        self._reserve_script = self._r.register_script(_RESERVE_LUA)
        self._reconcile_script = self._r.register_script(_RECONCILE_LUA)
        self._cancel_script = self._r.register_script(_CANCEL_LUA)

    def reserve(self, action: ActionCostVector) -> ReservationResult:
        """Atomically check budget and reserve cost for an action.

        Uses a registered Lua script that runs entirely server-side,
        preventing race conditions between concurrent reservations.

        Returns:
            ReservationResult with status and reserved amount.
        """
        result = self._reserve_script(
            keys=[BUDGET_KEY, ASL_RESERVATIONS, ASL_BUDGET],
            args=[
                action.action_id,
                str(action.cost_usd_est),
                str(self._headroom_floor),
                str(self._max_reservation_pct),
            ],
        )

        status_str, reserved_str, reason = result
        if isinstance(status_str, bytes):
            status_str = status_str.decode()
            reserved_str = reserved_str.decode()
            reason = reason.decode()

        status_map = {
            "approved": ReservationStatus.APPROVED,
            "rejected_rate": ReservationStatus.REJECTED_RATE,
            "deferred": ReservationStatus.DEFERRED,
        }

        return ReservationResult(
            status=status_map.get(status_str, ReservationStatus.DEFERRED),
            action_id=action.action_id,
            reserved_cost=float(reserved_str),
            reason=reason,
        )

    def reconcile(
        self,
        action_id: str,
        actual_cost: float,
        actual_tokens: int = 0,
        model_used: str = "",
        latency_ms: float = 0,
    ) -> None:
        """Release reservation and record actual cost.

        Called after action execution completes. Updates:
        1. asl:reservations - remove this action's reservation
        2. asl:budget - decrease hourlyReserved
        3. fsc:budget - increase hourlySpent (shared with mesh_bridge)
        4. asl:history - append completion record for estimator learning
        """
        self._reconcile_script(
            keys=[BUDGET_KEY, ASL_RESERVATIONS, ASL_BUDGET, ASL_HISTORY],
            args=[
                action_id,
                str(actual_cost),
                str(actual_tokens),
                model_used,
                str(latency_ms),
                str(time.time()),
            ],
        )

    def get_headroom(self) -> float:
        """Return current budget headroom ratio (0.0-1.0).

        headroom = (hourly_limit - hourly_spent - hourly_reserved) / hourly_limit
        """
        pipe = self._r.pipeline()
        pipe.hget(BUDGET_KEY, "hourlySpent")
        pipe.hget(BUDGET_KEY, "hourlyLimit")
        pipe.hget(ASL_BUDGET, "hourlyReserved")
        spent_raw, limit_raw, reserved_raw = pipe.execute()

        spent = float(spent_raw or 0)
        limit = float(limit_raw or 0.5)
        reserved = float(reserved_raw or 0)

        if limit <= 0:
            return 1.0
        return max(0.0, (limit - spent - reserved) / limit)

    def pending_reservations(self) -> dict[str, float]:
        """Return all pending reservations {action_id: reserved_usd}."""
        raw = self._r.hgetall(ASL_RESERVATIONS)
        return {k: float(v) for k, v in raw.items()}

    def cancel_reservation(self, action_id: str) -> bool:
        """Cancel a pending reservation (e.g., action was evicted from queue)."""
        result = self._cancel_script(
            keys=[ASL_RESERVATIONS, ASL_BUDGET],
            args=[action_id],
        )
        return bool(result)
