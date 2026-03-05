#!/usr/bin/env python3
"""
FreeClaw - 共享常量
统一配置路径、默认值，消除各模块硬编码
"""

import os
from pathlib import Path

# 核心路径
HOME = Path(os.path.expanduser("~"))
OPENCLAW_DIR = HOME / ".openclaw"
OPENCLAW_CONFIG = OPENCLAW_DIR / "openclaw.json"
FREECLAW_DIR = HOME / ".freeclaw"
FREECLAW_CONFIG = FREECLAW_DIR / "freeclaw.json"
PROJECT_DIR = Path(__file__).parent.parent
DATA_DIR = PROJECT_DIR / "data"

# 确保目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)


# 最小骨架配置
_MINIMAL_CONFIG = {
    "models": {
        "providers": {}
    },
    "agents": {
        "defaults": {
            "model": {
                "primary": "",
                "fallbacks": []
            }
        }
    }
}


def resolve_config_path() -> Path:
    """解析配置文件路径，优先级: $FREECLAW_CONFIG > ~/.openclaw/openclaw.json > ~/.freeclaw/freeclaw.json"""
    env_path = os.environ.get("FREECLAW_CONFIG")
    if env_path:
        return Path(env_path)
    if OPENCLAW_CONFIG.exists():
        return OPENCLAW_CONFIG
    return FREECLAW_CONFIG


def ensure_config() -> Path:
    """确保配置文件存在，不存在时创建最小骨架"""
    import json
    config_path = resolve_config_path()
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(_MINIMAL_CONFIG, f, indent=2, ensure_ascii=False)
            f.write('\n')
    return config_path

# 数据文件
COSTS_FILE = DATA_DIR / "costs.json"
ROUTING_FILE = DATA_DIR / "routing.json"
CIRCUIT_STATE_FILE = DATA_DIR / "circuit_state.json"
SCHEDULER_DB = DATA_DIR / "scheduler.db"

# 默认阈值
QUOTA_WARNING_PERCENT = 80
QUOTA_CRITICAL_PERCENT = 95
CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_RECOVERY_TIMEOUT = 30  # seconds
MAX_TASK_RETRIES = 3

# Provider 列表（避免各模块重复定义）
KNOWN_PROVIDERS = [
    'codex', 'copilot', 'antigravity', 'windsurf',
    'openai', 'anthropic', 'openrouter', 'google',
    'moonshot', 'ollama', 'groq', 'deepseek', 'volcengine'
]
