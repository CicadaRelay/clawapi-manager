#!/usr/bin/env python3
"""
配置缓存 - 全局单例，TTL 60s
消除 smart_router.py 中每次路由都重读配置文件的问题
"""

import time
from typing import Optional

_cache: Optional[dict] = None
_cache_ts: float = 0.0
_TTL: float = 60.0


def get_config() -> dict:
    """获取缓存的配置，过期则重新加载"""
    global _cache, _cache_ts
    now = time.monotonic()
    if _cache is not None and (now - _cache_ts) < _TTL:
        return _cache
    try:
        from lib.smart_router import _load_config_from_disk
    except ImportError:
        from smart_router import _load_config_from_disk
    _cache = _load_config_from_disk()
    _cache_ts = now
    return _cache


def invalidate():
    """写入配置后调用，立即失效缓存"""
    global _cache, _cache_ts
    _cache = None
    _cache_ts = 0.0
