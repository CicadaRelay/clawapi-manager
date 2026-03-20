"""ASL Cost Estimator — learn token/cost estimates from historical data.

Uses Exponential Moving Average (EMA) per (category, complexity) pair.
Updated after every action reconciliation via asl:history stream.

Cold start: falls back to heuristic defaults from ActionFormulator.
After ~50 actions per category, estimates converge to within 20% of actuals.
"""

from __future__ import annotations

from typing import Optional

try:
    import redis
except ImportError:
    redis = None


ASL_ESTIMATOR_PREFIX = "asl:estimator"
ASL_HISTORY = "asl:history"

# EMA smoothing factor — 0.1 means ~10-action half-life
DEFAULT_ALPHA = 0.1

# Cold-start defaults (used before enough history)
COLD_START_DEFAULTS: dict[str, dict[str, float]] = {
    "analysis:free":       {"avg_output_ratio": 2.0, "avg_latency_ms": 2000, "sample_count": 0},
    "analysis:medium":     {"avg_output_ratio": 2.5, "avg_latency_ms": 5000, "sample_count": 0},
    "analysis:expensive":  {"avg_output_ratio": 3.0, "avg_latency_ms": 8000, "sample_count": 0},
    "implementation:free":      {"avg_output_ratio": 3.0, "avg_latency_ms": 3000, "sample_count": 0},
    "implementation:medium":    {"avg_output_ratio": 3.5, "avg_latency_ms": 8000, "sample_count": 0},
    "implementation:expensive": {"avg_output_ratio": 4.0, "avg_latency_ms": 15000, "sample_count": 0},
    "testing:free":        {"avg_output_ratio": 2.0, "avg_latency_ms": 2000, "sample_count": 0},
    "testing:medium":      {"avg_output_ratio": 2.5, "avg_latency_ms": 5000, "sample_count": 0},
    "testing:expensive":   {"avg_output_ratio": 3.0, "avg_latency_ms": 10000, "sample_count": 0},
    "review:medium":       {"avg_output_ratio": 2.0, "avg_latency_ms": 5000, "sample_count": 0},
    "review:expensive":    {"avg_output_ratio": 2.5, "avg_latency_ms": 10000, "sample_count": 0},
    "general:free":        {"avg_output_ratio": 2.0, "avg_latency_ms": 2000, "sample_count": 0},
    "general:medium":      {"avg_output_ratio": 2.5, "avg_latency_ms": 5000, "sample_count": 0},
    "general:expensive":   {"avg_output_ratio": 3.0, "avg_latency_ms": 8000, "sample_count": 0},
}

# Model pricing for cost estimation ($/1M tokens, aligned with action_cost.py)
_TIER_PRICING = {
    "premium": 15.0,
    "standard": 3.0,
    "economy": 1.0,
    "free": 0.0,
}

_COMPLEXITY_TO_TIER = {
    "free": "free",
    "medium": "standard",
    "expensive": "premium",
}


class CostEstimator:
    """Learn token/cost estimates from historical action data.

    Maintains per-(category, complexity) EMA statistics in Redis.
    Called by ActionFormulator for pre-dispatch estimation,
    and updated by BudgetGate reconciliation.
    """

    def __init__(self, redis_client: "redis.Redis", *, alpha: float = DEFAULT_ALPHA):
        self._r = redis_client
        self._alpha = alpha

    def estimate(
        self, category: str, complexity: str, prompt_tokens: int,
    ) -> Optional[dict]:
        """Estimate output tokens, latency, and cost.

        Args:
            category: Task category (analysis, implementation, etc.)
            complexity: Complexity level (free, medium, expensive)
            prompt_tokens: Known input token count.

        Returns:
            Dict with tokens_est, latency_ms_est, cost_usd_est
            or None if no data available (use heuristic fallback).
        """
        key = f"{ASL_ESTIMATOR_PREFIX}:{category}:{complexity}"
        raw = self._r.hgetall(key)

        if not raw:
            # Try cold-start defaults
            default_key = f"{category}:{complexity}"
            defaults = COLD_START_DEFAULTS.get(default_key)
            if defaults is None:
                return None
            raw = {k.encode(): str(v).encode() for k, v in defaults.items()}

        stats = _decode_hash(raw)
        sample_count = int(stats.get("sample_count", 0))

        # Use stats if we have enough samples, otherwise return None
        # to let ActionFormulator use its own heuristics
        if sample_count < 5:
            return None

        output_ratio = stats.get("avg_output_ratio", 2.5)
        output_est = int(prompt_tokens * output_ratio)
        tokens_est = prompt_tokens + output_est

        tier = _COMPLEXITY_TO_TIER.get(complexity, "standard")
        rate = _TIER_PRICING.get(tier, 5.0)
        cost_usd_est = round(tokens_est * rate / 1_000_000, 6)

        latency_ms_est = stats.get("avg_latency_ms", 5000)

        return {
            "tokens_est": tokens_est,
            "latency_ms_est": latency_ms_est,
            "cost_usd_est": cost_usd_est,
        }

    def update(
        self,
        category: str,
        complexity: str,
        prompt_tokens: int,
        output_tokens: int,
        latency_ms: float,
    ) -> None:
        """Update EMA with actual results. Called after reconciliation.

        Args:
            category: Task category.
            complexity: Complexity level.
            prompt_tokens: Actual input tokens.
            output_tokens: Actual output tokens.
            latency_ms: Actual latency in milliseconds.
        """
        if prompt_tokens <= 0:
            return

        key = f"{ASL_ESTIMATOR_PREFIX}:{category}:{complexity}"
        actual_ratio = output_tokens / prompt_tokens

        # Atomic EMA update via Lua
        lua_script = """
        local key = KEYS[1]
        local alpha = tonumber(ARGV[1])
        local actual_ratio = tonumber(ARGV[2])
        local actual_latency = tonumber(ARGV[3])

        local count = tonumber(redis.call('HGET', key, 'sample_count') or '0')
        local old_ratio = tonumber(redis.call('HGET', key, 'avg_output_ratio') or ARGV[2])
        local old_latency = tonumber(redis.call('HGET', key, 'avg_latency_ms') or ARGV[3])

        local new_count = count + 1

        -- EMA: new = alpha * actual + (1 - alpha) * old
        -- For first few samples, use simple average for stability
        local new_ratio, new_latency
        if count < 5 then
            new_ratio = (old_ratio * count + actual_ratio) / new_count
            new_latency = (old_latency * count + actual_latency) / new_count
        else
            new_ratio = alpha * actual_ratio + (1 - alpha) * old_ratio
            new_latency = alpha * actual_latency + (1 - alpha) * old_latency
        end

        redis.call('HSET', key,
            'avg_output_ratio', tostring(new_ratio),
            'avg_latency_ms', tostring(new_latency),
            'sample_count', tostring(new_count)
        )

        -- Set TTL: 7 days (auto-expire stale estimator data)
        redis.call('EXPIRE', key, 604800)

        return 1
        """

        update_script = self._r.register_script(lua_script)
        update_script(
            keys=[key],
            args=[str(self._alpha), str(actual_ratio), str(latency_ms)],
        )

    def get_stats(self, category: str, complexity: str) -> Optional[dict]:
        """Read current estimator stats for a category:complexity pair."""
        key = f"{ASL_ESTIMATOR_PREFIX}:{category}:{complexity}"
        raw = self._r.hgetall(key)
        if not raw:
            return None
        return _decode_hash(raw)

    def reset(self, category: str, complexity: str) -> None:
        """Reset estimator for a category:complexity pair."""
        key = f"{ASL_ESTIMATOR_PREFIX}:{category}:{complexity}"
        self._r.delete(key)


def _decode_hash(raw: dict) -> dict[str, float]:
    """Decode a Redis HASH with bytes keys/values to float dict."""
    result = {}
    for k, v in raw.items():
        key = k.decode() if isinstance(k, bytes) else k
        val = v.decode() if isinstance(v, bytes) else v
        try:
            result[key] = float(val)
        except (ValueError, TypeError):
            result[key] = 0.0
    return result
