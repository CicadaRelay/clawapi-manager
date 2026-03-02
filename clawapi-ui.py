#!/usr/bin/env python3
"""
ClawAPI Manager - 智能入口
自动检测环境并选择合适的界面
"""

import sys
import os

def is_interactive_terminal():
    """检测是否在交互式终端"""
    return sys.stdin.isatty() and sys.stdout.isatty()

def has_full_tty():
    """检测是否支持完整 TTY（Textual 需要）"""
    try:
        import termios
        termios.tcgetattr(sys.stdin)
        return True
    except:
        return False

def main():
    # 检测环境
    if len(sys.argv) > 1:
        # 有命令行参数：使用 CLI 模式
        print("Using CLI mode...")
        from clawapi import main as cli_main
        cli_main()
    
    elif has_full_tty():
        # 完整 TTY：使用 Textual TUI
        print("Starting Textual TUI...")
        import time
        time.sleep(0.5)
        from clawapi_tui import ClawAPITUI
        app = ClawAPITUI()
        app.run()
    
    elif is_interactive_terminal():
        # 受限终端：使用 Rich 菜单
        print("Starting Rich TUI...")
        import time
        time.sleep(0.5)
        from clawapi_rich import ClawAPIRichTUI
        tui = ClawAPIRichTUI()
        tui.run()
    
    else:
        # 非交互环境（QQ/飞书）：显示帮助
        print("""
ClawAPI Manager - Configuration Management Tool

Environment: Non-interactive (QQ/Feishu/etc)

Usage:
  clawapi status              Show configuration status
  clawapi providers           List all providers
  clawapi models              List all models
  clawapi channels            List all channels
  
  clawapi add-provider <name> <url> <key>
  clawapi set-primary <model_id>
  clawapi add-channel <name> <type> <token>

For interactive UI, run from SSH terminal:
  ssh user@host
  cd ~/.openclaw/workspace/skills/clawapi-manager
  python3 clawapi-ui.py
""")

if __name__ == "__main__":
    main()
