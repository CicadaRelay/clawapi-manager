#!/usr/bin/env python3
"""
FreeClaw ↔ FSC-Mesh Bridge
打通 FreeClaw (Python) 与 claw-mesh (TypeScript/Redis) 的数据通道

功能:
1. 读写 Redis fsc:budget — 与 CostController 共享成本状态
2. 模型层级对齐 — 5级制 (premium/standard/economy/free/paused)
3. 节点心跳同步 — 从 Redis 读取集群节点状态
4. OpenRouter 免费模型解析 — 为 free 层级提供真实模型
5. 成本上报 — FreeClaw 路由结果反馈到 mesh 预算系统
"""

import os
import json
import time
from typing import Optional, Dict, List

try:
    import redis
except ImportError:
    redis = None

MESH_TIERS = {
    'premium':  {'models': ['claude-sonnet-4'], 'cost_per_token': 0.003},
    'standard': {'models': ['doubao-seed-2.0-code'], 'cost_per_token': 0.0003},
    'economy':  {'models': ['minimax-2.5'], 'cost_per_token': 0.0001},
    'free':     {'models': ['openrouter/free'], 'cost_per_token': 0},
    'paused':   {'models': [], 'cost_per_token': 0},
}

FREECLAW_TO_MESH = {
    'free': 'free',
    'medium': 'standard',
    'expensive': 'premium',
}

MESH_TO_FREECLAW = {
    'premium': 'expensive',
    'standard': 'medium',
    'economy': 'medium',
    'free': 'free',
    'paused': 'free',
}

BUDGET_KEY = 'fsc:budget'
BUDGET_CHANNEL = 'fsc:budget:alert'
NODES_KEY_PREFIX = 'fsc:node:'
FREECLAW_ROUTING_KEY = 'fsc:freeclaw:routing'

CLUSTER_NODES = {
    'central': {'name': 'Central', 'ip': '10.10.0.1'},
    'silicon':  {'name': 'Silicon Valley', 'ip': '10.10.0.2'},
    'tokyo':    {'name': 'Tokyo', 'ip': '10.10.0.3'},
}


class MeshBridge:
    """FreeClaw ↔ FSC-Mesh Redis 桥接"""

    def __init__(self, redis_url: str = None):
        if redis is None:
            raise ImportError("pip install redis")

        self.redis_url = redis_url or os.getenv(
            'REDIS_URL', 'redis://:fsc-mesh-2026@10.10.0.1:6379/0'
        )
        self._client: Optional[redis.Redis] = None

    @property
    def client(self) -> 'redis.Redis':
        if self._client is None:
            self._client = redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    def ping(self) -> bool:
        try:
            return self.client.ping()
        except Exception:
            return False

    # ========== 预算状态 ==========

    def get_budget_state(self) -> Dict:
        """读取 fsc:budget — 与 CostController 共享"""
        data = self.client.hgetall(BUDGET_KEY)
        if not data:
            return {'error': 'no budget state', 'tier': 'standard'}

        return {
            'hourly_spent': float(data.get('hourlySpent', 0)),
            'hourly_limit': float(data.get('hourlyLimit', 0.5)),
            'daily_spent': float(data.get('dailySpent', 0)),
            'daily_limit': float(data.get('dailyLimit', 10)),
            'monthly_spent': float(data.get('monthlySpent', 0)),
            'monthly_limit': float(data.get('monthlyLimit', 200)),
            'tier': data.get('modelTier', 'standard'),
            'model': data.get('currentModel', ''),
        }

    def get_current_tier(self) -> str:
        """获取当前 mesh 层级 (premium/standard/economy/free/paused)"""
        state = self.get_budget_state()
        return state.get('tier', 'standard')

    def get_budget_usage(self) -> Dict[str, float]:
        """获取预算使用率百分比"""
        state = self.get_budget_state()
        if 'error' in state:
            return {'hourly': 0, 'daily': 0, 'monthly': 0}

        def pct(spent, limit):
            return round(spent / limit * 100, 1) if limit > 0 else 0

        return {
            'hourly': pct(state['hourly_spent'], state['hourly_limit']),
            'daily': pct(state['daily_spent'], state['daily_limit']),
            'monthly': pct(state['monthly_spent'], state['monthly_limit']),
        }

    # ========== 成本上报 ==========

    def report_cost(self, task_id: str, cost_usd: float,
                    tokens_used: int, model: str) -> Dict:
        """上报路由成本到 mesh 预算系统"""
        pipe = self.client.pipeline()
        pipe.hincrbyfloat(BUDGET_KEY, 'hourlySpent', cost_usd)
        pipe.hincrbyfloat(BUDGET_KEY, 'dailySpent', cost_usd)
        pipe.hincrbyfloat(BUDGET_KEY, 'monthlySpent', cost_usd)
        pipe.hgetall(BUDGET_KEY)
        results = pipe.execute()

        state = results[3]
        hourly_spent = float(state.get('hourlySpent', 0))
        hourly_limit = float(state.get('hourlyLimit', 0.5))
        ratio = hourly_spent / hourly_limit if hourly_limit > 0 else 0

        # 记录路由事件
        event = {
            'task_id': task_id,
            'model': model,
            'cost_usd': cost_usd,
            'tokens': tokens_used,
            'timestamp': time.time(),
        }
        self.client.lpush(FREECLAW_ROUTING_KEY, json.dumps(event))
        self.client.ltrim(FREECLAW_ROUTING_KEY, 0, 999)

        return {
            'hourly_spent': hourly_spent,
            'hourly_limit': hourly_limit,
            'ratio': round(ratio, 3),
            'tier': state.get('modelTier', 'standard'),
        }

    # ========== 模型解析 ==========

    def resolve_model(self, mesh_tier: str) -> str:
        """将 mesh 层级解析为实际可用模型
        特别处理 free 层: 调用 OpenRouterHub 获取真实免费模型
        """
        if mesh_tier == 'paused':
            return 'none'

        if mesh_tier == 'free':
            try:
                from lib.openrouter_hub import OpenRouterHub
                hub = OpenRouterHub()
                model = hub.get_model('weighted')
                if model:
                    return model
            except (ImportError, Exception):
                pass
            return 'qwen/qwen3.5-35b-a3b'

        tier_info = MESH_TIERS.get(mesh_tier, MESH_TIERS['standard'])
        return tier_info['models'][0] if tier_info['models'] else 'doubao-seed-2.0-code'

    def get_recommended_model(self) -> Dict:
        """基于 mesh 预算状态推荐模型"""
        tier = self.get_current_tier()
        model = self.resolve_model(tier)
        usage = self.get_budget_usage()

        return {
            'tier': tier,
            'model': model,
            'budget_usage': usage,
            'can_accept': tier != 'paused',
        }

    # ========== 节点状态 ==========

    def get_node_status(self) -> List[Dict]:
        """从 Redis 获取集群节点状态"""
        nodes = []
        for node_id, info in CLUSTER_NODES.items():
            key = f"{NODES_KEY_PREFIX}{node_id}"
            data = self.client.hgetall(key)

            if data:
                nodes.append({
                    'id': node_id,
                    'name': info['name'],
                    'ip': info['ip'],
                    'status': data.get('status', 'unknown'),
                    'cpu': float(data.get('cpu_usage', 0)),
                    'memory': float(data.get('memory_usage', 0)),
                    'active_tasks': int(data.get('active_tasks', 0)),
                    'last_heartbeat': float(data.get('last_heartbeat', 0)),
                })
            else:
                nodes.append({
                    'id': node_id,
                    'name': info['name'],
                    'ip': info['ip'],
                    'status': 'no_data',
                    'cpu': 0, 'memory': 0,
                    'active_tasks': 0,
                    'last_heartbeat': 0,
                })

        return nodes

    def publish_heartbeat(self, node_id: str, metrics: Dict):
        """发布节点心跳到 Redis"""
        key = f"{NODES_KEY_PREFIX}{node_id}"
        self.client.hset(key, mapping={
            'status': metrics.get('status', 'online'),
            'cpu_usage': str(metrics.get('cpu_usage', 0)),
            'memory_usage': str(metrics.get('memory_usage', 0)),
            'active_tasks': str(metrics.get('active_tasks', 0)),
            'last_heartbeat': str(time.time()),
        })
        self.client.expire(key, 600)  # 10分钟过期

    # ========== 路由历史 ==========

    def get_routing_history(self, count: int = 20) -> List[Dict]:
        """获取最近的路由记录"""
        raw = self.client.lrange(FREECLAW_ROUTING_KEY, 0, count - 1)
        return [json.loads(r) for r in raw]

    def get_routing_stats(self) -> Dict:
        """路由统计"""
        history = self.get_routing_history(100)
        if not history:
            return {'total': 0, 'total_cost': 0, 'models': {}}

        total_cost = sum(h.get('cost_usd', 0) for h in history)
        models = {}
        for h in history:
            m = h.get('model', 'unknown')
            models[m] = models.get(m, 0) + 1

        return {
            'total': len(history),
            'total_cost': round(total_cost, 4),
            'models': models,
        }

    def close(self):
        if self._client:
            self._client.close()
            self._client = None


def main():
    import sys

    if len(sys.argv) < 2:
        print("\nFreeClaw Mesh Bridge")
        print("\n  status       Show mesh budget + node status")
        print("  recommend    Get recommended model from mesh")
        print("  nodes        Show cluster nodes")
        print("  history      Show routing history")
        print("  stats        Show routing stats")
        print("  ping         Test Redis connection")
        return

    cmd = sys.argv[1]

    try:
        bridge = MeshBridge()
    except ImportError as e:
        print(f"Error: {e}")
        return

    if cmd == 'ping':
        ok = bridge.ping()
        print(f"Redis: {'OK' if ok else 'FAILED'}")

    elif cmd == 'status':
        state = bridge.get_budget_state()
        usage = bridge.get_budget_usage()
        print(f"\nMesh Budget Status")
        print(f"  Tier: {state.get('tier', '?')}")
        print(f"  Model: {state.get('model', '?')}")
        print(f"  Hourly: ${state.get('hourly_spent', 0):.3f} / ${state.get('hourly_limit', 0):.2f} ({usage['hourly']}%)")
        print(f"  Daily:  ${state.get('daily_spent', 0):.3f} / ${state.get('daily_limit', 0):.2f} ({usage['daily']}%)")
        print(f"  Monthly: ${state.get('monthly_spent', 0):.3f} / ${state.get('monthly_limit', 0):.2f} ({usage['monthly']}%)")

    elif cmd == 'recommend':
        rec = bridge.get_recommended_model()
        print(json.dumps(rec, indent=2))

    elif cmd == 'nodes':
        nodes = bridge.get_node_status()
        for n in nodes:
            print(f"  {n['name']} ({n['ip']}): {n['status']} | CPU {n['cpu']}% | MEM {n['memory']}% | tasks {n['active_tasks']}")

    elif cmd == 'history':
        for h in bridge.get_routing_history():
            print(f"  {h.get('model', '?')} | ${h.get('cost_usd', 0):.4f} | {h.get('task_id', '?')[:8]}")

    elif cmd == 'stats':
        stats = bridge.get_routing_stats()
        print(json.dumps(stats, indent=2))

    else:
        print(f"Unknown: {cmd}")

    bridge.close()


if __name__ == '__main__':
    main()
