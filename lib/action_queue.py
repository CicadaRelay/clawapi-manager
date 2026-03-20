"""ASL Action Queue — Redis-backed priority queue with eviction.

Inspired by ARL-Tangram's greedy eviction heuristic: when budget pressure
is high, low-priority queued (not yet dispatched) actions are evicted to
a deferred list, freeing headroom for higher-priority actions.
"""

from __future__ import annotations

from typing import Optional

try:
    import redis
except ImportError:
    redis = None

from .action_cost import ActionCostVector, compute_priority_score


# Redis keys
ASL_ACTIONS = "asl:actions"             # ZSET: action_id → priority_score
ASL_ACTION_PREFIX = "asl:actions:"      # HASH per action: full vector
ASL_DEFERRED = "asl:deferred"           # LIST: evicted action_ids
ASL_BUDGET = "asl:budget"


class ActionQueue:
    """Priority queue for LLM API actions, backed by Redis ZSET.

    Operations:
    - enqueue: Add action with computed priority score
    - dequeue: Pop highest-priority action
    - evict_lowest: Remove lowest-priority actions to free budget headroom
    - restore_deferred: Move deferred actions back when budget recovers
    """

    def __init__(self, redis_client: "redis.Redis", *, max_queue_size: int = 500):
        self._r = redis_client
        self._max_queue_size = max_queue_size

    def enqueue(self, action: ActionCostVector, score: float = 0) -> int:
        """Add action to priority queue.

        Args:
            action: The action cost vector to enqueue.
            score: Priority score (computed by compute_priority_score).
                   If 0, computes automatically.

        Returns:
            Current queue depth after insertion.
        """
        if score <= 0:
            score = compute_priority_score(action)

        pipe = self._r.pipeline()
        # Store full vector as HASH
        pipe.hset(
            f"{ASL_ACTION_PREFIX}{action.action_id}",
            mapping={k: str(v) for k, v in action.to_dict().items()},
        )
        # Add to priority ZSET
        pipe.zadd(ASL_ACTIONS, {action.action_id: score})
        # Get queue depth
        pipe.zcard(ASL_ACTIONS)
        results = pipe.execute()

        return results[2]

    def dequeue(self) -> Optional[ActionCostVector]:
        """Pop the highest-priority action from the queue.

        Returns:
            ActionCostVector if queue is non-empty, else None.
        """
        # ZPOPMAX returns [(member, score)] — highest score first
        result = self._r.zpopmax(ASL_ACTIONS, count=1)
        if not result:
            return None

        action_id = result[0][0]
        if isinstance(action_id, bytes):
            action_id = action_id.decode()

        # Fetch full vector
        raw = self._r.hgetall(f"{ASL_ACTION_PREFIX}{action_id}")
        if not raw:
            return None

        # Clean up the detail HASH
        self._r.delete(f"{ASL_ACTION_PREFIX}{action_id}")

        return _parse_action_hash(raw)

    def peek(self, count: int = 1) -> list[tuple[ActionCostVector, float]]:
        """Peek at top N actions without removing them.

        Returns:
            List of (ActionCostVector, score) tuples, highest-priority first.
        """
        # ZREVRANGE returns highest scores first
        results = self._r.zrevrange(ASL_ACTIONS, 0, count - 1, withscores=True)
        actions = []
        for action_id, score in results:
            if isinstance(action_id, bytes):
                action_id = action_id.decode()
            raw = self._r.hgetall(f"{ASL_ACTION_PREFIX}{action_id}")
            if raw:
                actions.append((_parse_action_hash(raw), score))
        return actions

    def evict_lowest(self, count: int = 1) -> list[str]:
        """Evict lowest-priority actions to deferred list.

        Called by ElasticRouter when budget headroom is too low and a
        high-priority action needs to be scheduled.

        Returns:
            List of evicted action_ids.
        """
        # ZPOPMIN returns [(member, score)] — lowest score first
        results = self._r.zpopmin(ASL_ACTIONS, count=count)
        evicted = []

        pipe = self._r.pipeline()
        for action_id, _ in results:
            if isinstance(action_id, bytes):
                action_id = action_id.decode()
            evicted.append(action_id)
            # Move to deferred list (preserves the detail HASH)
            pipe.rpush(ASL_DEFERRED, action_id)

        if evicted:
            pipe.execute()

        return evicted

    def restore_deferred(self, count: int = 10) -> int:
        """Move deferred actions back to the priority queue.

        Called when budget headroom recovers (e.g., new hour starts).

        Returns:
            Number of actions restored.
        """
        restored = 0
        for _ in range(count):
            action_id = self._r.lpop(ASL_DEFERRED)
            if action_id is None:
                break
            if isinstance(action_id, bytes):
                action_id = action_id.decode()

            # Check if detail HASH still exists
            raw = self._r.hgetall(f"{ASL_ACTION_PREFIX}{action_id}")
            if not raw:
                continue

            action = _parse_action_hash(raw)
            score = compute_priority_score(action)
            self._r.zadd(ASL_ACTIONS, {action_id: score})
            restored += 1

        return restored

    def depth(self) -> int:
        """Return current queue depth."""
        return self._r.zcard(ASL_ACTIONS) or 0

    def deferred_count(self) -> int:
        """Return number of deferred actions."""
        return self._r.llen(ASL_DEFERRED) or 0

    def clear(self) -> None:
        """Clear the queue and deferred list. Use with caution."""
        # Get all action IDs to clean up detail HASHes
        action_ids = self._r.zrange(ASL_ACTIONS, 0, -1)
        deferred_ids = self._r.lrange(ASL_DEFERRED, 0, -1)

        pipe = self._r.pipeline()
        for aid in action_ids + deferred_ids:
            if isinstance(aid, bytes):
                aid = aid.decode()
            pipe.delete(f"{ASL_ACTION_PREFIX}{aid}")
        pipe.delete(ASL_ACTIONS)
        pipe.delete(ASL_DEFERRED)
        pipe.execute()


def _parse_action_hash(raw: dict) -> ActionCostVector:
    """Parse a Redis HASH into an ActionCostVector."""
    d = {}
    for k, v in raw.items():
        key = k.decode() if isinstance(k, bytes) else k
        val = v.decode() if isinstance(v, bytes) else v

        # Type coercion based on field
        if key in ("tokens_est", "tokens_actual", "priority"):
            val = int(float(val))
        elif key in (
            "latency_ms_est", "cost_usd_est", "context_window_pct",
            "deadline_ms", "cost_usd_actual", "latency_ms_actual", "completed_at",
        ):
            val = float(val)
        elif key == "degradable":
            val = val.lower() in ("true", "1", "yes")

        d[key] = val

    return ActionCostVector.from_dict(d)
