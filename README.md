# ClawAPI Manager

Professional API management and cost optimization for OpenClaw deployments.

## What It Does

Manages API keys, monitors costs, and routes tasks to the most cost-effective models automatically. Saves 30-90% on API costs through intelligent routing and free model integration.

## Key Features

- **Smart Routing**: Automatically routes simple tasks to free models (Qwen, Llama) via OpenRouter
- **Cost Tracking**: Real-time monitoring of API usage and spending
- **Multi-Provider**: Supports OpenAI, Anthropic, Google, and 40+ providers
- **Budget Alerts**: Get notified before you exceed spending limits
- **Key Health**: Automatic detection of expired or rate-limited keys
- **Multi-Channel Alerts**: Telegram, Discord, Slack, Feishu, QQ, DingTalk

## Quick Start

```bash
# Install
cd ~/.openclaw/workspace/skills
git clone https://github.com/2233admin/clawapi-manager.git
cd clawapi-manager
pip install -r requirements.txt

# Configure notifications (optional)
cp config/notify.json.example config/notify.json
# Edit with your webhook URLs

# Test
python3 lib/cost_monitor.py health
```

## How It Saves Money

The system analyzes each task and routes it intelligently:

- **Simple tasks** (search, weather, translate) → Free models (100% savings)
- **Medium tasks** (summaries, basic code) → Cost-effective models (50-70% savings)
- **Complex tasks** (architecture, analysis) → Premium models (Opus, GPT-4)

### Example Savings

| Task Type | Before | After | Savings |
|-----------|--------|-------|---------|
| Weather check | $0.015 | $0.00 | 100% |
| Code review | $0.30 | $0.10 | 67% |
| Architecture design | $1.50 | $1.50 | 0% |

**Average savings: 30-90%** depending on your task mix.

## Configuration

### OpenRouter (Optional, for free models)

Add your OpenRouter key to `config/openrouter.json`:

```json
{
  "api_key": "sk-or-v1-YOUR_KEY_HERE"
}
```

Get a free key at [openrouter.ai](https://openrouter.ai)

### Notifications

Edit `config/notify.json`:

```json
{
  "telegram": {
    "enabled": true,
    "bot_token": "YOUR_BOT_TOKEN",
    "chat_id": "YOUR_CHAT_ID"
  }
}
```

## Usage

```bash
# Check system health
python3 lib/cost_monitor.py health

# Generate cost report
python3 lib/daily_report.py

# Route a task (returns recommended model)
python3 lib/task_delegation.py route "search weather in Tokyo"

# Check key health
python3 lib/key_health.py status

# Test notifications
python3 lib/notifier.py test
```

## Automation

Add to cron for automated monitoring:

```cron
# Daily cost report at 1 AM
0 1 * * * cd /path/to/clawapi-manager && python3 lib/daily_report.py

# Health check every 15 minutes
*/15 * * * * cd /path/to/clawapi-manager && python3 lib/cost_monitor.py health
```

## Architecture

```
ClawAPI Manager
├── lib/                    # Core modules
│   ├── cost_monitor.py     # Cost tracking
│   ├── task_delegation.py  # Smart routing
│   ├── notifier.py         # Alerts
│   ├── budget_alert.py     # Budget monitoring
│   └── key_health.py       # Key health checks
├── config/                 # Configuration
└── data/                   # Runtime data
```

## Requirements

- Python 3.8+
- OpenClaw (any recent version)
- Optional: OpenRouter API key (for free model routing)

## Security

- API keys are encrypted at rest (AES-256)
- Never commit keys to version control
- Use environment variables for production
- Review config examples before deployment

## License

MIT License - Free for personal and commercial use.

## Links

- [OpenClaw](https://github.com/openclaw/openclaw)
- [OpenRouter](https://openrouter.ai)
- [ClawHub](https://clawhub.com)

---

**Version**: 1.0.1  
**Last Updated**: 2026-03-02

## 模型切换（新功能）

集成自 openclaw-switch，提供安全的模型切换功能。

### 查看当前模型

```bash
python3 lib/model_switcher.py status
```

### 列出所有模型

```bash
python3 lib/model_switcher.py list
```

### 切换模型

```bash
# 通过编号切换
python3 lib/model_switcher.py switch 6

# 或通过模型 ID
python3 lib/model_switcher.py switch minimax/MiniMax-M2.5
```

### 特性

- ✅ 安全的 JSON 修改（防止格式错误）
- ✅ 显示 Fallback 链
- ✅ 自动重启 daemon
- ✅ 支持编号和 ID 两种方式


## 使用场景

### 场景 1：SSH/终端（推荐）
完整的 Textual TUI，支持鼠标和键盘交互。

```bash
ssh user@server
cd ~/.openclaw/workspace/skills/clawapi-manager
python3 clawapi-tui.py
```

### 场景 2：受限终端
Rich 交互式菜单，只支持键盘。

```bash
python3 clawapi-rich.py
```

### 场景 3：QQ/飞书等纯文字
使用 CLI 命令。

```bash
./clawapi status
./clawapi providers
./clawapi add-provider openai https://api.openai.com/v1 sk-xxx
```

### 场景 4：智能自动选择
自动检测环境并选择合适的界面。

```bash
python3 clawapi-ui.py
```

---

## 环境检测

| 环境 | 检测方式 | 使用界面 |
|------|---------|---------|
| SSH/终端 | `termios.tcgetattr()` | Textual TUI |
| 受限终端 | `sys.stdin.isatty()` | Rich 菜单 |
| QQ/飞书 | 非 TTY | CLI |

