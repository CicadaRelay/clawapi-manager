#!/usr/bin/env python3
"""
FreeClaw Provider Adapter - 统一的 Provider 适配器基类
替代原来 codex.py / copilot.py / antigravity.py / windsurf.py 四个重复文件
"""

import os
import json
import requests
from datetime import datetime
from typing import Optional


class ProviderAdapter:
    """通用 Provider 适配器"""

    def __init__(self, provider_name: str, api_key: str = None,
                 api_url: str = None, auth_header: str = "Authorization",
                 auth_prefix: str = "Bearer", quota_endpoint: str = "/v1/usage",
                 health_endpoint: str = "/v1/health",
                 quota_mapping: dict = None):
        self.provider_name = provider_name
        self.api_key = api_key
        self.api_url = api_url
        self.auth_header = auth_header
        self.auth_prefix = auth_prefix
        self.quota_endpoint = quota_endpoint
        self.health_endpoint = health_endpoint
        self.quota_mapping = quota_mapping or {
            'used': 'used', 'total': 'limit'
        }

    def _headers(self):
        if self.auth_prefix:
            return {self.auth_header: f'{self.auth_prefix} {self.api_key}',
                    'Content-Type': 'application/json'}
        return {self.auth_header: self.api_key,
                'Content-Type': 'application/json'}

    def get_quota(self):
        if not self.api_key or not self.api_url:
            return {'provider': self.provider_name, 'status': 'error',
                    'error': 'API key or URL not configured',
                    'timestamp': datetime.now().isoformat()}
        try:
            response = requests.get(
                f'{self.api_url}{self.quota_endpoint}',
                headers=self._headers(), timeout=10)
            response.raise_for_status()
            data = response.json()

            used_key = self.quota_mapping['used']
            total_key = self.quota_mapping['total']
            used = data.get(used_key, 0)
            total = data.get(total_key, 0)

            return {
                'provider': self.provider_name,
                'status': 'ok',
                'quota': {
                    'used': used,
                    'total': total,
                    'remaining': total - used,
                    'percentage': (used / max(total, 1)) * 100
                },
                'timestamp': datetime.now().isoformat()
            }
        except requests.exceptions.RequestException as e:
            return {'provider': self.provider_name, 'status': 'error',
                    'error': str(e), 'timestamp': datetime.now().isoformat()}

    def check_health(self):
        if not self.api_key or not self.api_url:
            return False
        try:
            response = requests.get(
                f'{self.api_url}{self.health_endpoint}',
                headers=self._headers(), timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False


# 预定义的 Provider 配置
PROVIDER_CONFIGS = {
    'codex': {
        'env_key': 'CODEX_API_KEY', 'env_url': 'CODEX_API_URL',
        'auth_prefix': 'Bearer', 'quota_endpoint': '/v1/usage',
        'health_endpoint': '/v1/status',
        'quota_mapping': {'used': 'used', 'total': 'limit'}
    },
    'copilot': {
        'env_key': 'COPILOT_API_KEY', 'env_url': 'COPILOT_API_URL',
        'auth_header': 'Authorization', 'auth_prefix': 'token',
        'quota_endpoint': '/api/quota', 'health_endpoint': '/api/health',
        'quota_mapping': {'used': 'usage', 'total': 'quota'}
    },
    'antigravity': {
        'env_key': 'ANTIGRAVITY_API_KEY', 'env_url': 'ANTIGRAVITY_API_URL',
        'auth_prefix': 'Bearer', 'quota_endpoint': '/v1/quota',
        'health_endpoint': '/v1/health',
        'quota_mapping': {'used': 'used', 'total': 'total'}
    },
    'windsurf': {
        'env_key': 'WINDSURF_API_KEY', 'env_url': 'WINDSURF_API_URL',
        'auth_header': 'X-API-Key', 'auth_prefix': '',
        'quota_endpoint': '/v1/account/quota',
        'health_endpoint': '/v1/health',
        'quota_mapping': {'used': 'consumed', 'total': 'allocated'}
    },
    'firecrawl': {
        'env_key': 'FIRECRAWL_API_KEY', 'env_url': 'FIRECRAWL_BASE_URL',
        'auth_prefix': 'Bearer', 'quota_endpoint': '/v1/scrape',
        'health_endpoint': '/v1/scrape',
        'quota_mapping': {'used': 'used', 'total': 'limit'}
    },
}


def create_adapter(provider_name: str,
                   api_key: str = None,
                   api_url: str = None) -> ProviderAdapter:
    """工厂函数：创建指定 Provider 的适配器"""
    cfg = PROVIDER_CONFIGS.get(provider_name, {})
    return ProviderAdapter(
        provider_name=provider_name,
        api_key=api_key or os.getenv(cfg.get('env_key', ''), ''),
        api_url=api_url or os.getenv(cfg.get('env_url', ''), ''),
        auth_header=cfg.get('auth_header', 'Authorization'),
        auth_prefix=cfg.get('auth_prefix', 'Bearer'),
        quota_endpoint=cfg.get('quota_endpoint', '/v1/usage'),
        health_endpoint=cfg.get('health_endpoint', '/v1/health'),
        quota_mapping=cfg.get('quota_mapping', {'used': 'used', 'total': 'limit'})
    )


def get_all_quotas() -> list:
    """查询所有已配置 Provider 的配额"""
    results = []
    for name in PROVIDER_CONFIGS:
        adapter = create_adapter(name)
        if adapter.api_key and adapter.api_url:
            results.append(adapter.get_quota())
    return results


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: provider_adapter.py <provider> [quota|health]")
        print(f"Providers: {', '.join(PROVIDER_CONFIGS.keys())}")
        sys.exit(1)

    provider = sys.argv[1]
    command = sys.argv[2] if len(sys.argv) > 2 else 'quota'
    adapter = create_adapter(provider)

    if command == 'quota':
        print(json.dumps(adapter.get_quota(), indent=2))
    elif command == 'health':
        print(json.dumps({'healthy': adapter.check_health()}))
