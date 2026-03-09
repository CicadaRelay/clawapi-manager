#!/usr/bin/env python3
"""
FreeClaw Scrapling Provider - 本地反爬网页抓取
零成本替代 Firecrawl，专治知乎/微信公众号等国内反爬站点
"""

import json
import sys
from datetime import datetime
from typing import Optional, Dict, List


class ScraplingProvider:
    """Scrapling 本地爬取适配器 — 三级反爬策略"""

    def __init__(self, mode: str = "auto"):
        """
        Args:
            mode: 抓取模式
                - "fast": Fetcher, 简单请求, 无反爬
                - "stealth": StealthyFetcher, 指纹伪装+Cloudflare绕过
                - "browser": DynamicFetcher, 完整浏览器渲染
                - "auto": 根据目标站点自动选择
        """
        self.mode = mode
        self._check_installed()

    def _check_installed(self) -> bool:
        try:
            import scrapling
            self._available = True
        except ImportError:
            self._available = False
        return self._available

    def _select_mode(self, url: str) -> str:
        """根据 URL 自动选择反爬级别"""
        if self.mode != "auto":
            return self.mode

        url_lower = url.lower()

        # 重度反爬站点 → 浏览器渲染
        heavy_sites = [
            "mp.weixin.qq.com", "weixin.sogou.com",  # 微信公众号
            "xueqiu.com",                              # 雪球
        ]
        if any(site in url_lower for site in heavy_sites):
            return "browser"

        # 中度反爬 → 隐身模式
        stealth_sites = [
            "zhihu.com", "zhuanlan.zhihu.com",  # 知乎
            "juejin.cn",                         # 掘金
            "bilibili.com",                      # B站
            "douban.com",                        # 豆瓣
            "toutiao.com", "36kr.com",           # 头条/36氪
            "baidu.com",                         # 百度
            "csdn.net",                          # CSDN
            "xiaohongshu.com",                   # 小红书
        ]
        if any(site in url_lower for site in stealth_sites):
            return "stealth"

        # 其他 → 快速模式
        return "fast"

    def scrape(self, url: str, selectors: Dict[str, str] = None,
               wait_for: str = None, extract_text: bool = True) -> dict:
        """抓取单个页面

        Args:
            url: 目标 URL
            selectors: CSS 选择器映射 {"title": "h1::text", "content": ".article-body"}
            wait_for: 等待某个元素出现 (browser 模式)
            extract_text: 是否提取纯文本
        """
        if not self._available:
            return {"success": False, "error": "scrapling not installed. Run: pip install scrapling"}

        mode = self._select_mode(url)

        try:
            page = self._fetch(url, mode, wait_for)

            result = {
                "success": True,
                "url": url,
                "mode": mode,
                "timestamp": datetime.now().isoformat(),
            }

            if selectors:
                extracted = {}
                for key, sel in selectors.items():
                    if sel.startswith("//"):
                        extracted[key] = page.xpath(sel).getall()
                    else:
                        extracted[key] = page.css(sel).getall()
                result["data"] = extracted
            elif extract_text:
                # 默认提取正文
                result["title"] = page.css("title::text").get() or ""
                result["text"] = self._extract_main_content(page)
                result["links"] = page.css("a::attr(href)").getall()[:50]

            return result

        except Exception as e:
            # 自动升级模式重试
            upgraded = self._upgrade_mode(mode)
            if upgraded and upgraded != mode:
                try:
                    page = self._fetch(url, upgraded, wait_for)
                    result = {
                        "success": True,
                        "url": url,
                        "mode": upgraded,
                        "upgraded_from": mode,
                        "timestamp": datetime.now().isoformat(),
                    }
                    if extract_text:
                        result["title"] = page.css("title::text").get() or ""
                        result["text"] = self._extract_main_content(page)
                    return result
                except Exception as e2:
                    return {"success": False, "error": f"Upgraded to {upgraded} but still failed: {e2}"}

            return {"success": False, "error": str(e), "mode": mode}

    def _fetch(self, url: str, mode: str, wait_for: str = None):
        """按模式执行抓取"""
        if mode == "fast":
            from scrapling.fetchers import Fetcher
            return Fetcher.get(url, stealthy_headers=True, verify=False)

        elif mode == "stealth":
            from scrapling.fetchers import StealthyFetcher
            return StealthyFetcher.fetch(url)

        elif mode == "browser":
            from scrapling.fetchers import DynamicFetcher
            kwargs = {"headless": True, "network_idle": True}
            if wait_for:
                kwargs["wait_selector"] = wait_for
            return DynamicFetcher.fetch(url, **kwargs)

        raise ValueError(f"Unknown mode: {mode}")

    def _upgrade_mode(self, current: str) -> Optional[str]:
        """失败时自动升级反爬等级"""
        chain = {"fast": "stealth", "stealth": "browser"}
        return chain.get(current)

    def _extract_main_content(self, page) -> str:
        """智能提取正文内容"""
        # 按优先级尝试常见正文容器
        content_selectors = [
            "article",
            ".Post-RichTextContainer",   # 知乎
            ".rich_media_content",        # 微信公众号
            "#js_content",               # 微信公众号 (备用)
            ".article-content",          # 通用
            ".post-content",             # 通用
            "main",
            ".content",
            "#content",
        ]
        for sel in content_selectors:
            el = page.css(sel)
            if el:
                texts = el[0].css("::text").getall()
                content = "\n".join(t.strip() for t in texts if t.strip())
                if len(content) > 100:
                    return content

        # fallback: body 全文
        texts = page.css("body ::text").getall()
        return "\n".join(t.strip() for t in texts if t.strip())[:10000]

    def batch_scrape(self, urls: List[str], selectors: Dict[str, str] = None) -> List[dict]:
        """批量抓取多个 URL"""
        return [self.scrape(url, selectors=selectors) for url in urls]

    def check_health(self) -> bool:
        """检查 scrapling 是否可用"""
        return self._available

    def get_usage(self) -> dict:
        return {
            "provider": "scrapling",
            "status": "ok" if self._available else "not_installed",
            "cost": 0,
            "mode": self.mode,
            "timestamp": datetime.now().isoformat(),
        }


# === 路由集成 ===

# 这些站点优先用 Scrapling 而非 Firecrawl（反爬更强 + 零成本）
STEALTH_PREFERRED_DOMAINS = [
    "zhihu.com", "zhuanlan.zhihu.com",
    "mp.weixin.qq.com", "weixin.sogou.com",
    "juejin.cn", "bilibili.com", "douban.com",
    "toutiao.com", "36kr.com", "baidu.com",
    "csdn.net", "xiaohongshu.com", "xueqiu.com",
]


def should_use_scrapling(url: str) -> bool:
    """判断该 URL 是否应优先用 Scrapling（国内反爬站点）"""
    if not url:
        return False
    url_lower = url.lower()
    return any(domain in url_lower for domain in STEALTH_PREFERRED_DOMAINS)


def route_stealth_crawl(task: str, url: str, **kwargs) -> dict:
    """路由反爬抓取任务到 Scrapling

    如果 Scrapling 不可用，fallback 到 Firecrawl
    """
    provider = ScraplingProvider(mode=kwargs.get("mode", "auto"))

    if provider.check_health():
        return provider.scrape(
            url,
            selectors=kwargs.get("selectors"),
            wait_for=kwargs.get("wait_for"),
            extract_text=kwargs.get("extract_text", True),
        )

    # Scrapling 不可用 → fallback Firecrawl
    try:
        from firecrawl_provider import route_crawl
        return route_crawl(task, url=url, **kwargs)
    except ImportError:
        return {"success": False, "error": "Neither scrapling nor firecrawl available"}


def main():
    if len(sys.argv) < 2:
        print("\nScrapling Provider (FreeClaw)")
        print("\nCommands:")
        print("  scrape <url>              Scrape with auto anti-detection")
        print("  scrape-fast <url>         Fast mode (no anti-detection)")
        print("  scrape-stealth <url>      Stealth mode (fingerprint spoofing)")
        print("  scrape-browser <url>      Browser mode (full JS rendering)")
        print("  batch <url1> <url2> ...   Batch scrape multiple URLs")
        print("  check <url>               Check which mode would be used")
        print("  health                    Check if scrapling is installed")
        return

    cmd = sys.argv[1]

    if cmd == "health":
        provider = ScraplingProvider()
        print(json.dumps(provider.get_usage(), indent=2, ensure_ascii=False))

    elif cmd == "check":
        if len(sys.argv) < 3:
            print("Usage: scrapling_provider.py check <url>")
            sys.exit(1)
        provider = ScraplingProvider()
        mode = provider._select_mode(sys.argv[2])
        preferred = should_use_scrapling(sys.argv[2])
        print(json.dumps({
            "url": sys.argv[2],
            "mode": mode,
            "scrapling_preferred": preferred,
        }, indent=2))

    elif cmd.startswith("scrape"):
        if len(sys.argv) < 3:
            print(f"Usage: scrapling_provider.py {cmd} <url>")
            sys.exit(1)
        mode_map = {
            "scrape": "auto",
            "scrape-fast": "fast",
            "scrape-stealth": "stealth",
            "scrape-browser": "browser",
        }
        mode = mode_map.get(cmd, "auto")
        provider = ScraplingProvider(mode=mode)
        result = provider.scrape(sys.argv[2])
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "batch":
        if len(sys.argv) < 3:
            print("Usage: scrapling_provider.py batch <url1> <url2> ...")
            sys.exit(1)
        provider = ScraplingProvider()
        results = provider.batch_scrape(sys.argv[2:])
        print(json.dumps(results, indent=2, ensure_ascii=False))

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
