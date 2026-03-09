#!/usr/bin/env python3
"""
FreeClaw Device Provider - 设备端反爬抓取（第三级）
通过真实设备/代理拦截绕过重度反爬站点

架构：
  轻度反爬 → Scrapling (scrapling_provider.py)
  重度反爬 → Device Provider (本文件)
    ├─ 微信公众号 → wechat-spider (mitmproxy 代理拦截)
    └─ 其他APP → uiautomator2 (Android UI 自动化)
  通用站点 → Firecrawl (firecrawl_provider.py)
"""

import os
import json
import sys
import subprocess
from datetime import datetime
from typing import Optional, Dict, List

# wechat-spider 项目路径
WECHAT_SPIDER_DIR = os.getenv(
    "WECHAT_SPIDER_DIR",
    "D:/projects/wechat-spider"
)

# 设备配置
DEVICE_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "data", "device_config.json"
)


def load_device_config() -> dict:
    if os.path.exists(DEVICE_CONFIG_FILE):
        try:
            with open(DEVICE_CONFIG_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return get_default_config()


def get_default_config() -> dict:
    return {
        "wechat_spider": {
            "enabled": False,
            "proxy_port": 8080,
            "mysql": {
                "host": "127.0.0.1",
                "port": 3306,
                "db": "wechat",
                "user": "root",
                "passwd": "root",
            },
            "redis": {
                "host": "10.10.0.1",
                "port": 6379,
                "db": 1,
                "passwd": "fsc-mesh-2026",
            },
            "docker": True,
        },
        "android": {
            "enabled": False,
            "devices": [],
            # 示例: [{"name": "pixel", "addr": "192.168.50.100", "apps": ["com.zhihu.android"]}]
        },
    }


def save_device_config(config: dict):
    os.makedirs(os.path.dirname(DEVICE_CONFIG_FILE), exist_ok=True)
    with open(DEVICE_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


class WeChatSpiderProvider:
    """微信公众号爬虫 — 通过 mitmproxy 代理拦截微信客户端请求"""

    def __init__(self, config: dict = None):
        self.config = config or load_device_config().get("wechat_spider", {})
        self.spider_dir = WECHAT_SPIDER_DIR
        self._docker = self.config.get("docker", True)

    def check_health(self) -> dict:
        """检查 wechat-spider 环境"""
        checks = {
            "spider_dir_exists": os.path.isdir(self.spider_dir),
            "docker_compose_exists": os.path.isfile(
                os.path.join(self.spider_dir, "docker-compose.yml")
            ),
        }

        if self._docker:
            try:
                result = subprocess.run(
                    ["docker", "compose", "ps", "--format", "json"],
                    cwd=self.spider_dir,
                    capture_output=True, text=True, timeout=10,
                )
                checks["docker_running"] = result.returncode == 0
                if result.returncode == 0 and result.stdout.strip():
                    checks["services"] = result.stdout.strip()
            except (subprocess.TimeoutExpired, FileNotFoundError):
                checks["docker_running"] = False

        return {
            "provider": "wechat-spider",
            "status": "ok" if all(checks.get(k) for k in ["spider_dir_exists"]) else "not_configured",
            "checks": checks,
            "timestamp": datetime.now().isoformat(),
        }

    def start(self) -> dict:
        """启动 wechat-spider (Docker Compose)"""
        if not self._docker:
            return {"success": False, "error": "Non-docker mode not implemented yet"}

        try:
            result = subprocess.run(
                ["docker", "compose", "up", "-d"],
                cwd=self.spider_dir,
                capture_output=True, text=True, timeout=120,
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "proxy_port": self.config.get("proxy_port", 8080),
                "instructions": (
                    "微信客户端配置代理:\n"
                    f"  代理地址: 本机IP:{self.config.get('proxy_port', 8080)}\n"
                    "  需要先安装 mitmproxy CA 证书到设备\n"
                    "  证书路径: ./mitmproxy/mitmproxy-ca-cert.pem"
                ),
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Docker compose start timeout"}
        except FileNotFoundError:
            return {"success": False, "error": "Docker not found"}

    def stop(self) -> dict:
        """停止 wechat-spider"""
        try:
            result = subprocess.run(
                ["docker", "compose", "down"],
                cwd=self.spider_dir,
                capture_output=True, text=True, timeout=60,
            )
            return {"success": result.returncode == 0, "output": result.stdout}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def add_account(self, biz: str, name: str = "") -> dict:
        """添加公众号抓取任务

        Args:
            biz: 公众号的 __biz 参数（Base64编码的ID）
            name: 公众号名称（可选）
        """
        # 通过 Redis 直接写入任务
        try:
            import redis
            r = redis.Redis(
                host=self.config["redis"]["host"],
                port=self.config["redis"]["port"],
                db=self.config["redis"]["db"],
                password=self.config["redis"].get("passwd"),
            )
            task_key = f"wechat:account_task"
            task_data = json.dumps({"__biz": biz, "name": name, "status": "pending"})
            r.lpush(task_key, task_data)
            return {"success": True, "biz": biz, "name": name}
        except ImportError:
            return {"success": False, "error": "redis package not installed"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_articles(self, biz: str = None, limit: int = 20) -> dict:
        """获取已抓取的文章（从 MySQL 读取）"""
        try:
            import pymysql
            conn = pymysql.connect(
                host=self.config["mysql"]["host"],
                port=self.config["mysql"]["port"],
                db=self.config["mysql"]["db"],
                user=self.config["mysql"]["user"],
                password=self.config["mysql"]["passwd"],
                charset="utf8mb4",
            )
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            if biz:
                cursor.execute(
                    "SELECT * FROM articles WHERE __biz=%s ORDER BY publish_time DESC LIMIT %s",
                    (biz, limit),
                )
            else:
                cursor.execute(
                    "SELECT * FROM articles ORDER BY publish_time DESC LIMIT %s",
                    (limit,),
                )

            articles = cursor.fetchall()
            conn.close()
            return {"success": True, "count": len(articles), "articles": articles}
        except ImportError:
            return {"success": False, "error": "pymysql not installed"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class AndroidProvider:
    """Android 设备 UI 自动化 — 通过 uiautomator2 控制真机/模拟器"""

    def __init__(self, config: dict = None):
        self.config = config or load_device_config().get("android", {})
        self._devices = {}

    def connect(self, addr: str, name: str = "default") -> dict:
        """连接 Android 设备

        Args:
            addr: 设备地址 (IP 或 serial)
            name: 设备别名
        """
        try:
            import uiautomator2 as u2
            d = u2.connect(addr)
            info = d.info
            self._devices[name] = d
            return {
                "success": True,
                "name": name,
                "addr": addr,
                "device_info": {
                    "brand": info.get("productName", ""),
                    "sdk": info.get("sdkInt", 0),
                    "screen": f"{d.window_size()[0]}x{d.window_size()[1]}",
                    "serial": info.get("serial", ""),
                },
            }
        except ImportError:
            return {"success": False, "error": "uiautomator2 not installed. Run: pip install uiautomator2"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def scrape_zhihu_question(self, question_id: str, device: str = "default") -> dict:
        """从知乎 APP 抓取问题页面内容"""
        d = self._devices.get(device)
        if not d:
            return {"success": False, "error": f"Device '{device}' not connected"}

        try:
            # 启动知乎 APP 并打开指定问题
            d.app_start("com.zhihu.android")
            import time
            time.sleep(2)

            # 通过 deeplink 打开问题
            d.shell(f"am start -a android.intent.action.VIEW -d 'zhihu://question/{question_id}'")
            time.sleep(3)

            # 抓取页面文本
            elements = d.xpath('//*[@class="android.widget.TextView"]').all()
            texts = [e.text for e in elements if e.text and len(e.text) > 10]

            return {
                "success": True,
                "question_id": question_id,
                "mode": "android_app",
                "texts": texts,
                "element_count": len(texts),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def scrape_app_screen(self, package: str, device: str = "default",
                          selectors: Dict[str, str] = None) -> dict:
        """通用 APP 屏幕抓取

        Args:
            package: APP 包名
            device: 设备别名
            selectors: XPath 选择器 {"title": "//TextView[@resource-id='title']"}
        """
        d = self._devices.get(device)
        if not d:
            return {"success": False, "error": f"Device '{device}' not connected"}

        try:
            d.app_start(package)
            import time
            time.sleep(3)

            result = {
                "success": True,
                "package": package,
                "mode": "android_app",
                "timestamp": datetime.now().isoformat(),
            }

            if selectors:
                data = {}
                for key, xpath in selectors.items():
                    els = d.xpath(xpath).all()
                    data[key] = [e.text for e in els if e.text]
                result["data"] = data
            else:
                # 默认抓取所有文本
                els = d.xpath('//*[@class="android.widget.TextView"]').all()
                result["texts"] = [e.text for e in els if e.text]

            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def screenshot(self, device: str = "default", save_path: str = None) -> dict:
        """截屏"""
        d = self._devices.get(device)
        if not d:
            return {"success": False, "error": f"Device '{device}' not connected"}

        try:
            save_path = save_path or f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            d.screenshot(save_path)
            return {"success": True, "path": save_path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_devices(self) -> dict:
        return {
            "connected": list(self._devices.keys()),
            "configured": self.config.get("devices", []),
        }

    def check_health(self) -> dict:
        try:
            import uiautomator2
            available = True
        except ImportError:
            available = False

        return {
            "provider": "android",
            "status": "ok" if available else "not_installed",
            "connected_devices": list(self._devices.keys()),
            "timestamp": datetime.now().isoformat(),
        }


# === 路由集成 ===

# 重度反爬站点 → 需要设备端抓取
DEVICE_PREFERRED_DOMAINS = {
    "mp.weixin.qq.com": "wechat",
    "weixin.sogou.com": "wechat",
    "zhihu.com": "android",
    "zhuanlan.zhihu.com": "android",
    "xiaohongshu.com": "android",
    "xueqiu.com": "android",
}


def get_device_type(url: str) -> Optional[str]:
    """判断 URL 应该用哪种设备抓取，返回 'wechat'/'android'/None"""
    if not url:
        return None
    url_lower = url.lower()
    for domain, dtype in DEVICE_PREFERRED_DOMAINS.items():
        if domain in url_lower:
            return dtype
    return None


def is_device_available(device_type: str) -> bool:
    """检查设备端是否可用"""
    config = load_device_config()
    if device_type == "wechat":
        return config.get("wechat_spider", {}).get("enabled", False)
    elif device_type == "android":
        cfg = config.get("android", {})
        return cfg.get("enabled", False) and len(cfg.get("devices", [])) > 0
    return False


def route_device_crawl(task: str, url: str, **kwargs) -> dict:
    """路由到设备端抓取

    如果设备不可用，自动降级到 Scrapling → Firecrawl
    """
    device_type = get_device_type(url)

    if device_type == "wechat" and is_device_available("wechat"):
        provider = WeChatSpiderProvider()
        return {
            "success": True,
            "provider": "wechat-spider",
            "message": "微信公众号任务已提交到 wechat-spider",
            "instructions": (
                "wechat-spider 通过代理拦截工作，不是即时返回。\n"
                "文章会自动入库 MySQL，用 get_articles() 查询结果。"
            ),
        }

    if device_type == "android" and is_device_available("android"):
        config = load_device_config()
        devices = config["android"]["devices"]
        provider = AndroidProvider(config["android"])
        first_device = devices[0]
        conn = provider.connect(first_device["addr"], first_device.get("name", "default"))
        if conn["success"]:
            return provider.scrape_app_screen(
                package=kwargs.get("package", "com.zhihu.android"),
                device=first_device.get("name", "default"),
                selectors=kwargs.get("selectors"),
            )
        return conn

    # 降级到 Scrapling
    try:
        from scrapling_provider import route_stealth_crawl
        return route_stealth_crawl(task, url, **kwargs)
    except ImportError:
        pass

    # 再降级到 Firecrawl
    try:
        from firecrawl_provider import route_crawl
        return route_crawl(task, url=url, **kwargs)
    except ImportError:
        pass

    return {"success": False, "error": "No crawl provider available"}


def main():
    if len(sys.argv) < 2:
        print("\nDevice Provider (FreeClaw)")
        print("\nWeChat Spider:")
        print("  wechat-health            Check wechat-spider status")
        print("  wechat-start             Start wechat-spider (Docker)")
        print("  wechat-stop              Stop wechat-spider")
        print("  wechat-add <biz> [name]  Add account to crawl")
        print("  wechat-articles [biz]    Get crawled articles")
        print("\nAndroid:")
        print("  android-health           Check uiautomator2 status")
        print("  android-connect <addr>   Connect to device")
        print("  android-scrape <pkg>     Scrape app screen")
        print("  android-screenshot       Take screenshot")
        print("\nConfig:")
        print("  config                   Show device config")
        print("  init                     Create default config")
        print("  enable-wechat            Enable wechat-spider")
        print("  enable-android           Enable android provider")
        return

    cmd = sys.argv[1]

    if cmd == "config":
        print(json.dumps(load_device_config(), indent=2, ensure_ascii=False))

    elif cmd == "init":
        save_device_config(get_default_config())
        print(f"Config saved to {DEVICE_CONFIG_FILE}")

    elif cmd == "enable-wechat":
        config = load_device_config()
        config["wechat_spider"]["enabled"] = True
        save_device_config(config)
        print("WeChat spider enabled")

    elif cmd == "enable-android":
        if len(sys.argv) < 3:
            print("Usage: device_provider.py enable-android <device_addr>")
            sys.exit(1)
        config = load_device_config()
        config["android"]["enabled"] = True
        config["android"]["devices"].append({
            "name": "default",
            "addr": sys.argv[2],
        })
        save_device_config(config)
        print(f"Android enabled with device: {sys.argv[2]}")

    elif cmd == "wechat-health":
        provider = WeChatSpiderProvider()
        print(json.dumps(provider.check_health(), indent=2, ensure_ascii=False))

    elif cmd == "wechat-start":
        provider = WeChatSpiderProvider()
        print(json.dumps(provider.start(), indent=2, ensure_ascii=False))

    elif cmd == "wechat-stop":
        provider = WeChatSpiderProvider()
        print(json.dumps(provider.stop(), indent=2, ensure_ascii=False))

    elif cmd == "wechat-add":
        if len(sys.argv) < 3:
            print("Usage: device_provider.py wechat-add <biz> [name]")
            sys.exit(1)
        provider = WeChatSpiderProvider()
        name = sys.argv[3] if len(sys.argv) > 3 else ""
        print(json.dumps(provider.add_account(sys.argv[2], name), indent=2, ensure_ascii=False))

    elif cmd == "wechat-articles":
        provider = WeChatSpiderProvider()
        biz = sys.argv[2] if len(sys.argv) > 2 else None
        result = provider.get_articles(biz=biz)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    elif cmd == "android-health":
        provider = AndroidProvider()
        print(json.dumps(provider.check_health(), indent=2, ensure_ascii=False))

    elif cmd == "android-connect":
        if len(sys.argv) < 3:
            print("Usage: device_provider.py android-connect <addr>")
            sys.exit(1)
        provider = AndroidProvider()
        print(json.dumps(provider.connect(sys.argv[2]), indent=2, ensure_ascii=False))

    elif cmd == "android-screenshot":
        provider = AndroidProvider()
        config = load_device_config()
        devices = config.get("android", {}).get("devices", [])
        if not devices:
            print("No devices configured. Run: device_provider.py enable-android <addr>")
            sys.exit(1)
        d = devices[0]
        provider.connect(d["addr"], d.get("name", "default"))
        print(json.dumps(provider.screenshot(), indent=2, ensure_ascii=False))

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
