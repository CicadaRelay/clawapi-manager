#!/usr/bin/env python3
"""
FreeClaw Firecrawl Provider - 网页抓取与数据提取路由
通过 FreeClaw 统一管理 Firecrawl API 调用
"""

import os
import json
import requests
from datetime import datetime
from typing import Optional, Dict, List


FIRECRAWL_BASE_URL = "https://api.firecrawl.dev/v1"


class FirecrawlProvider:
    """Firecrawl API 适配器"""

    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or os.getenv("FIRECRAWL_API_KEY", "")
        self.base_url = (base_url or os.getenv("FIRECRAWL_BASE_URL", FIRECRAWL_BASE_URL)).rstrip("/")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """统一请求，带错误处理"""
        if not self.api_key:
            return {"success": False, "error": "FIRECRAWL_API_KEY not set"}

        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault("timeout", 30)
        kwargs["headers"] = self._headers()

        try:
            resp = requests.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            return {"success": False, "error": "Request timeout"}
        except requests.exceptions.HTTPError as e:
            return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e)}

    def scrape(self, url: str, formats: List[str] = None,
               only_main_content: bool = True, wait_for: int = 0) -> dict:
        """抓取单个页面

        Args:
            url: 目标 URL
            formats: 输出格式列表 ["markdown", "html", "rawHtml", "links", "screenshot"]
            only_main_content: 是否只提取正文
            wait_for: 等待页面加载毫秒数 (动态页面用)
        """
        payload = {
            "url": url,
            "formats": formats or ["markdown"],
            "onlyMainContent": only_main_content,
        }
        if wait_for > 0:
            payload["waitFor"] = wait_for

        return self._request("POST", "/scrape", json=payload)

    def crawl(self, url: str, max_depth: int = 2, limit: int = 10,
              include_paths: List[str] = None, exclude_paths: List[str] = None) -> dict:
        """爬取网站（异步任务）

        Args:
            url: 起始 URL
            max_depth: 最大爬取深度
            limit: 最大页面数
            include_paths: 只爬这些路径 (glob 模式)
            exclude_paths: 排除这些路径
        """
        payload = {
            "url": url,
            "maxDepth": max_depth,
            "limit": limit,
        }
        if include_paths:
            payload["includePaths"] = include_paths
        if exclude_paths:
            payload["excludePaths"] = exclude_paths

        return self._request("POST", "/crawl", json=payload)

    def crawl_status(self, crawl_id: str) -> dict:
        """查询爬取任务状态"""
        return self._request("GET", f"/crawl/{crawl_id}")

    def map(self, url: str, limit: int = 100) -> dict:
        """获取网站地图（所有可访问 URL 列表）"""
        payload = {"url": url, "limit": limit}
        return self._request("POST", "/map", json=payload)

    def extract(self, urls: List[str], prompt: str = None,
                schema: dict = None) -> dict:
        """LLM 结构化数据提取

        Args:
            urls: 目标 URL 列表
            prompt: 提取指令
            schema: JSON Schema 定义输出结构
        """
        payload = {"urls": urls}
        if prompt:
            payload["prompt"] = prompt
        if schema:
            payload["schema"] = schema

        return self._request("POST", "/extract", json=payload)

    def check_health(self) -> bool:
        """健康检查 - 用空 POST 测连通性"""
        if not self.api_key:
            return False
        try:
            resp = requests.post(
                f"{self.base_url}/scrape",
                headers=self._headers(),
                json={"url": "https://example.com"},
                timeout=10,
            )
            # 200 = success, 402 = quota exhausted, 422 = validation error
            # all mean API is reachable and key is recognized
            return resp.status_code in (200, 402, 422)
        except requests.exceptions.RequestException:
            return False

    def get_usage(self) -> dict:
        """获取用量（Firecrawl 没有专门的 usage endpoint，用 /scrape 测连通性）"""
        return {
            "provider": "firecrawl",
            "status": "ok" if self.check_health() else "error",
            "api_key_set": bool(self.api_key),
            "base_url": self.base_url,
            "timestamp": datetime.now().isoformat(),
        }


# === 路由集成 ===

CRAWL_SIGNALS = [
    "scrape", "crawl", "extract", "fetch page", "grab page",
    "抓取", "爬取", "提取网页", "网页内容", "抓网页",
]


def is_crawl_task(task: str) -> bool:
    """判断任务是否需要 Firecrawl"""
    task_lower = task.lower()
    return any(signal in task_lower for signal in CRAWL_SIGNALS)


def route_crawl(task: str, url: str = None, **kwargs) -> dict:
    """路由爬取任务到 Firecrawl

    自动判断应该用 scrape（单页）还是 crawl（多页）
    """
    provider = FirecrawlProvider()

    if not provider.api_key:
        return {"success": False, "error": "FIRECRAWL_API_KEY not configured"}

    task_lower = task.lower()

    # extract 类
    if any(k in task_lower for k in ["extract", "提取", "结构化"]):
        if url:
            return provider.extract(
                urls=[url],
                prompt=kwargs.get("prompt", task),
                schema=kwargs.get("schema"),
            )

    # crawl 类（多页）
    if any(k in task_lower for k in ["crawl", "爬取", "全站"]):
        if url:
            return provider.crawl(
                url=url,
                max_depth=kwargs.get("max_depth", 2),
                limit=kwargs.get("limit", 10),
            )

    # map 类
    if any(k in task_lower for k in ["map", "sitemap", "站点地图"]):
        if url:
            return provider.map(url=url, limit=kwargs.get("limit", 100))

    # 默认 scrape（单页）
    if url:
        return provider.scrape(
            url=url,
            formats=kwargs.get("formats", ["markdown"]),
            only_main_content=kwargs.get("only_main_content", True),
        )

    return {"success": False, "error": "No URL provided"}


def main():
    import sys

    if len(sys.argv) < 2:
        print("\nFirecrawl Provider (FreeClaw)")
        print("\nCommands:")
        print("  scrape <url>              Scrape single page to markdown")
        print("  crawl <url> [depth] [limit]  Crawl website")
        print("  status <crawl_id>         Check crawl job status")
        print("  map <url>                 Get site URL map")
        print("  extract <url> <prompt>    LLM structured extraction")
        print("  health                    Check API connectivity")
        print("  usage                     Show usage info")
        return

    cmd = sys.argv[1]
    provider = FirecrawlProvider()

    if cmd == "health":
        healthy = provider.check_health()
        print(json.dumps({"healthy": healthy, "api_key_set": bool(provider.api_key)}))

    elif cmd == "usage":
        print(json.dumps(provider.get_usage(), indent=2))

    elif cmd == "scrape":
        if len(sys.argv) < 3:
            print("Usage: firecrawl_provider.py scrape <url>")
            sys.exit(1)
        result = provider.scrape(sys.argv[2])
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "crawl":
        if len(sys.argv) < 3:
            print("Usage: firecrawl_provider.py crawl <url> [depth] [limit]")
            sys.exit(1)
        depth = int(sys.argv[3]) if len(sys.argv) > 3 else 2
        limit = int(sys.argv[4]) if len(sys.argv) > 4 else 10
        result = provider.crawl(sys.argv[2], max_depth=depth, limit=limit)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "status":
        if len(sys.argv) < 3:
            print("Usage: firecrawl_provider.py status <crawl_id>")
            sys.exit(1)
        result = provider.crawl_status(sys.argv[2])
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "map":
        if len(sys.argv) < 3:
            print("Usage: firecrawl_provider.py map <url>")
            sys.exit(1)
        result = provider.map(sys.argv[2])
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "extract":
        if len(sys.argv) < 4:
            print("Usage: firecrawl_provider.py extract <url> <prompt>")
            sys.exit(1)
        prompt = " ".join(sys.argv[3:])
        result = provider.extract([sys.argv[2]], prompt=prompt)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
