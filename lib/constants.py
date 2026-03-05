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
PROJECT_DIR = Path(__file__).parent.parent
DATA_DIR = PROJECT_DIR / "data"

# 确保目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)

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
