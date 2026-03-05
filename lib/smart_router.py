#!/usr/bin/env python3
"""
FreeClaw Smart Router - 智能路由引擎
合并原 model_router.py + task_delegation.py + smart_router.py
核心功能：按任务复杂度路由到最便宜的可用模型
"""

import os
import sys
import json
import time
from datetime import datetime
from typing import Optional, Dict, List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(PARENT_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(DATA_DIR, 'routing.json')

# 模型分级（从便宜到贵）
DEFAULT_MODEL_TIERS = {
    "free": [
        "qwen/qwen-2.5-0.5b-instruct",
        "qwen/qwen3.5-35b-a3b",
        "meta-llama/llama-3.2-1b-instruct",
        "mistral-7b-instruct",
    ],
    "medium": [
        "minimax/MiniMax-M2.5",
        "google/gemini-3.1-flash-image-preview",
        "bytedance-seed/seed-2.0-mini",
        "volcengine/doubao-seed-2.0-code",
    ],
    "expensive": [
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o",
    ]
}

# 任务复杂度关键词
DEFAULT_SIGNALS = {
    "simple": ["search", "weather", "translate", "time", "date",
               "check", "list", "find", "count", "status"],
    "complex": ["analyze", "write code", "debug", "architect",
                "design", "implement", "refactor", "review"],
}


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return get_default_config()


def get_default_config() -> dict:
    return {
        "model_tiers": DEFAULT_MODEL_TIERS,
        "signals": DEFAULT_SIGNALS,
        "free_routing_enabled": True,
        "confirm_before_switch": True,
        "providers": {},
        "thresholds": {
            "quota_warning_percent": 80,
            "quota_critical_percent": 95,
        }
    }


def save_config(config: dict):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def analyze_complexity(task: str) -> str:
    """分析任务复杂度，返回 free/medium/expensive"""
    try:
        from ai_complexity_predictor import AIComplexityPredictor
        predictor = AIComplexityPredictor()
        return predictor.predict_complexity(task)
    except ImportError:
        pass

    config = load_config()
    signals = config.get('signals', DEFAULT_SIGNALS)
    task_lower = task.lower()

    if any(s in task_lower for s in signals.get('simple', [])):
        return "free"
    if any(s in task_lower for s in signals.get('complex', [])):
        return "expensive"
    return "medium"


def get_mesh_tier() -> Optional[str]:
    """查询 FSC-Mesh 预算状态，返回当前允许的模型层级"""
    try:
        from lib.mesh_bridge import MeshBridge
        bridge = MeshBridge()
        tier = bridge.get_current_tier()
        bridge.close()
        return tier
    except Exception:
        return None


def get_model_for_task(task: str) -> str:
    """获取最适合任务的模型（成本优先）
    优先查询 mesh 预算层级，受限时强制降级
    """
    complexity = analyze_complexity(task)

    # 检查 mesh 预算约束
    mesh_tier = get_mesh_tier()
    if mesh_tier:
        from lib.mesh_bridge import MESH_TO_FREECLAW
        allowed = MESH_TO_FREECLAW.get(mesh_tier, 'medium')
        tier_rank = {'free': 0, 'medium': 1, 'expensive': 2}
        if tier_rank.get(complexity, 1) > tier_rank.get(allowed, 1):
            complexity = allowed

        if mesh_tier == 'paused':
            return 'none'

        if mesh_tier == 'free' or complexity == 'free':
            model = get_free_model()
            if model:
                return model

    elif complexity == "free":
        model = get_free_model()
        if model:
            return model

    config = load_config()
    tiers = config.get('model_tiers', DEFAULT_MODEL_TIERS)
    models = tiers.get(complexity, tiers.get('medium', []))
    return models[0] if models else "minimax/MiniMax-M2.5"


def get_free_model(strategy: str = 'weighted') -> str:
    """获取免费模型（优先走 OpenRouter 负载均衡）"""
    try:
        from lib.openrouter_hub import OpenRouterHub
        hub = OpenRouterHub()
        model = hub.get_model(strategy)
        if model:
            return model
    except ImportError:
        pass

    config = load_config()
    free = config.get('model_tiers', {}).get('free', [])
    return free[0] if free else "qwen/qwen-2.5-0.5b-instruct"


def should_use_free(task: str) -> bool:
    """判断是否应使用免费模型"""
    config = load_config()
    if not config.get('free_routing_enabled', True):
        return False
    return analyze_complexity(task) == "free"


def get_next_model(current: str) -> str:
    """获取下一个备选模型（当前不可用时）"""
    config = load_config()
    tiers = config.get('model_tiers', DEFAULT_MODEL_TIERS)

    all_models = []
    for tier in ['free', 'medium', 'expensive']:
        all_models.extend(tiers.get(tier, []))

    if current not in all_models:
        return all_models[0] if all_models else current

    idx = all_models.index(current)
    return all_models[(idx + 1) % len(all_models)]


# === Provider 管理（原 smart_router.py） ===

def add_provider(name: str, url: str, cost_per_1k: float = 0,
                 latency_ms: int = 100, priority: int = 50):
    config = load_config()
    config['providers'][name] = {
        'url': url,
        'cost_per_1k': cost_per_1k,
        'latency_ms': latency_ms,
        'priority': priority,
        'status': 'active',
        'added_at': datetime.now().isoformat()
    }
    save_config(config)


def get_best_provider(criteria: str = 'balanced') -> Optional[tuple]:
    config = load_config()
    providers = config.get('providers', {})
    active = {k: v for k, v in providers.items() if v.get('status') == 'active'}

    if not active:
        return None

    scored = []
    for name, info in active.items():
        if criteria == 'cost':
            score = 100 - info.get('cost_per_1k', 0)
        elif criteria == 'latency':
            score = 100 - min(info.get('latency_ms', 100), 100)
        elif criteria == 'priority':
            score = info.get('priority', 50)
        else:
            score = (
                (100 - info.get('cost_per_1k', 0)) / 3 +
                (100 - min(info.get('latency_ms', 100), 100)) / 3 +
                info.get('priority', 50) / 3
            )
        scored.append((name, info, score))

    scored.sort(key=lambda x: x[2], reverse=True)
    return scored[0] if scored else None


def record_provider_failure(name: str):
    config = load_config()
    if name in config.get('providers', {}):
        p = config['providers'][name]
        p['priority'] = max(0, p.get('priority', 50) - 10)
        p['status'] = 'degraded'
        save_config(config)


def record_provider_success(name: str):
    config = load_config()
    if name in config.get('providers', {}):
        p = config['providers'][name]
        p['priority'] = min(100, p.get('priority', 50) + 5)
        p['status'] = 'active'
        save_config(config)


def route_task(task: str, target_model: str = None) -> dict:
    """完整路由：分析任务 → 选模型 → 返回路由结果
    自动上报成本到 mesh 预算系统
    """
    if target_model is None:
        target_model = get_model_for_task(task)

    complexity = analyze_complexity(task)
    mesh_tier = get_mesh_tier()

    result = {
        "task": task[:100],
        "complexity": complexity,
        "model": target_model,
        "is_free": complexity == "free",
    }

    if mesh_tier:
        result["mesh_tier"] = mesh_tier
        result["mesh_constrained"] = mesh_tier in ("economy", "free", "paused")

    return result


def main():
    if len(sys.argv) < 2:
        print("\nFreeClaw Smart Router")
        print("\nRouting:")
        print("  route <task>        Route task to best model")
        print("  check <task>        Check if task should use free model")
        print("  free                Get current free model")
        print("  next <model>        Get next fallback model")
        print("\nProvider Management:")
        print("  add <name> <url> <cost> <latency>")
        print("  best [cost|latency|balanced]")
        print("  fail <name>         Record provider failure")
        print("  ok <name>           Record provider success")
        print("  list                Show all providers")
        print("\nConfig:")
        print("  enable-free         Enable free model routing")
        print("  disable-free        Disable free model routing")
        print("  config              Show current config")
        return

    cmd = sys.argv[1]

    if cmd == 'route':
        task = ' '.join(sys.argv[2:])
        print(json.dumps(route_task(task), indent=2))
    elif cmd == 'check':
        task = ' '.join(sys.argv[2:])
        result = should_use_free(task)
        print(json.dumps({"task": task, "use_free": result,
                          "free_model": get_free_model() if result else None}, indent=2))
    elif cmd == 'free':
        print(get_free_model())
    elif cmd == 'next':
        current = sys.argv[2] if len(sys.argv) > 2 else ""
        print(get_next_model(current))
    elif cmd == 'add':
        add_provider(sys.argv[2], sys.argv[3],
                     float(sys.argv[4]) if len(sys.argv) > 4 else 0,
                     int(sys.argv[5]) if len(sys.argv) > 5 else 100)
        print(f"Added provider: {sys.argv[2]}")
    elif cmd == 'best':
        criteria = sys.argv[2] if len(sys.argv) > 2 else 'balanced'
        best = get_best_provider(criteria)
        if best:
            print(json.dumps({'provider': best[0], 'info': best[1], 'score': best[2]}, indent=2))
        else:
            print("No available providers")
    elif cmd == 'fail':
        record_provider_failure(sys.argv[2])
        print(f"Recorded failure: {sys.argv[2]}")
    elif cmd == 'ok':
        record_provider_success(sys.argv[2])
        print(f"Recorded success: {sys.argv[2]}")
    elif cmd == 'list':
        print(json.dumps(load_config().get('providers', {}), indent=2))
    elif cmd == 'enable-free':
        config = load_config()
        config['free_routing_enabled'] = True
        save_config(config)
        print("Free model routing enabled")
    elif cmd == 'disable-free':
        config = load_config()
        config['free_routing_enabled'] = False
        save_config(config)
        print("Free model routing disabled")
    elif cmd == 'config':
        print(json.dumps(load_config(), indent=2))
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == '__main__':
    main()
