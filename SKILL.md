# ClawAPI Manager

An OpenClaw-native API management and cost optimization skill. Provides comprehensive API key management, real-time monitoring, smart routing, and cost savings through OpenRouter integration.

## Overview

ClawAPI Manager is an all-in-one solution for managing API keys, monitoring usage, and optimizing costs for OpenClaw deployments. It integrates monitoring, alerting, key rotation, and intelligent task routing into a unified management system.

**Target Users:** OpenClaw administrators, DevOps engineers, and developers managing multi-node AI agent deployments.

## Features

### 1. API Key Management
- **Multi-Provider Support**: Manage keys for multiple API providers (OpenAI, Anthropic, Google, etc.)
- **Key Pool Management**: Rotate between multiple keys automatically
- **Key Health Monitoring**: Detect expired, rate-limited, or invalid keys
- **Encryption**: AES-256 encryption for sensitive key storage

### 2. Real-Time Monitoring
- **Gateway Status**: Monitor OpenClaw Gateway connectivity and health
- **Cost Tracking**: Track API usage by model, provider, and time period
- **Quota Monitoring**: Monitor remaining quotas and rate limits
- **Session Analytics**: Analyze token consumption per session

### 3. Smart Routing (Cost Optimization)
- **Task Complexity Analysis**: Automatically classify tasks as simple/medium/complex
- **OpenRouter Integration**: Route simple tasks to free models (Qwen, Llama, etc.)
- **Priority-Based Switching**: Configure fallback model priority chains
- **Manual Override**: Force switch to specific models when needed

### 4. Alerting & Reporting
- **Multi-Channel Notifications**: Telegram, Discord, Slack, Feishu, QQ, DingTalk
- **Budget Alerts**: Daily/monthly budget threshold warnings
- **Daily Reports**: Automated cost reports via cron
- **Key Failure Detection**: Automatic 401/403/429 error detection

### 5. Fault Tolerance
- **Circuit Breaker**: Automatic failure detection and recovery
- **Bypass Mode**: Continue operations even if monitoring fails
- **File Locking**: Prevent concurrent modifications

## Architecture

```
ClawAPI Manager
├── lib/                    # Core Python modules
│   ├── cost_monitor.py     # Cost tracking
│   ├── cost_predictor.py  # Cost prediction
│   ├── circuit_breaker.py # Fault tolerance
│   ├── session_quota.py   # Session quotas
│   ├── smart_router.py    # Provider routing
│   ├── notifier.py        # Multi-channel alerts
│   ├── daily_report.py    # Report generation
│   ├── budget_alert.py    # Budget monitoring
│   ├── key_health.py      # Key health checks
│   └── task_delegation.py # OpenRouter delegation
├── config/                # Configuration files
├── data/                   # Runtime data storage
├── logs/                   # Log files
└── scripts/               # Shell automation scripts
```

## Installation

```bash
# Clone or download to your OpenClaw skills directory
cd ~/.openclaw/workspace/skills
git clone https://github.com/your-repo/clawapi-manager.git

# Install dependencies
cd clawapi-manager
pip install -r requirements.txt

# Configure notification channels
cp config/notify.json.example config/notify.json
# Edit with your webhook URLs
```

## Configuration

### Notification Channels

Edit `config/notify.json`:

```json
{
  "telegram": {
    "enabled": true,
    "bot_token": "YOUR_BOT_TOKEN",
    "chat_id": "YOUR_CHAT_ID"
  },
  "discord": {
    "enabled": false,
    "webhook_url": "https://discord.com/api/webhooks/..."
  }
}
```

### Model Priority

Configure default model and priority chain:

```bash
python3 lib/model_router.py set minimax/MiniMax-M2.5
python3 lib/model_router.py priority minimax/MiniMax-M2.5 volcengine aiclauder
```

### OpenRouter Setup (Optional)

For cost optimization, add your OpenRouter key to `config/openrouter.json`:

```json
{
  "api_key": "sk-or-v1-..."
}
```

## Usage

### Basic Commands

```bash
# Health check
python3 lib/cost_monitor.py health

# Cost report
python3 lib/daily_report.py

# Check key health
python3 lib/key_health.py status

# Budget alert check
python3 lib/budget_alert.py check
```

### Smart Routing

```bash
# Route a task (auto-selects model)
python3 lib/task_delegation.py route "search weather"

# Check if free model should be used
python3 lib/model_router.py check "simple task"

# Get next available model
python3 lib/model_router.py next current_model
```

### Alert Testing

```bash
# Test all notification channels
python3 lib/notifier.py test

# Send custom message
python3 lib/notifier.py send "System alert message"
```

## Cron Integration

Add to `/etc/cron.d/clawapi-manager`:

```cron
# Cost report at 1 AM daily
0 1 * * * root cd /path/to/clawapi-manager && python3 lib/daily_report.py >> /var/log/clawapi.log 2>&1

# Health check every 15 minutes
*/15 * * * * root cd /path/to/clawapi-manager && python3 lib/cost_monitor.py health >> /var/log/clawapi.log 2>&1
```

## Cost Optimization Guide

### How It Works

1. **Task Analysis**: When a task is submitted, the system analyzes its complexity based on keywords
2. **Model Selection**: 
   - Simple tasks (search, weather, translate) → Free models via OpenRouter
   - Medium tasks → Cost-effective models (Flash, Mini)
   - Complex tasks → Premium models (Opus, GPT-4)
3. **Execution**: Task is delegated to the selected model

### Free Models Available

| Model | Provider | Context |
|-------|----------|---------|
| Qwen 2.5 0.5B | OpenRouter | 32K |
| Llama 3.2 1B | OpenRouter | 128K |
| Gemini Flash | Google | 1M |

### Savings Estimate

- **Simple tasks**: 100% savings (free models)
- **Medium tasks**: 50-70% savings (Flash vs Opus)
- **Overall**: 30-90% cost reduction depending on task mix

## Requirements

- Python 3.8+
- OpenClaw (any recent version)
- Optional: OpenRouter API key (for free model routing)
- Optional: Webhook URLs for notifications

## Dependencies

```
requests
pycryptodome
python-dotenv
```

## Security Notes

- API keys are encrypted at rest using AES-256
- Never commit keys to version control
- Use environment variables or secure vaults for production
- Review `config/notify.json.example` before deployment

## License

MIT License - Free and personal use.

## Related for commercial Projects

- [OpenClaw](https://github.com/openclaw/openclaw) - Core framework
- [OpenRouter](https://openrouter.ai) - Free model routing
- [OpenClaw Dashboard](https://github.com/mudrii/openclaw-dashboard) - Web UI alternative

## Support

For issues and feature requests, please open an issue on GitHub.

---

**Version**: 1.0.0  
**Last Updated**: 2026-03-02
# ClawAPI Manager - 核心亮点

## 与 OpenClaw Switch 的对比

### OpenClaw Switch
> "The missing remote control for your AI Agents."

**定位**：模型切换工具

**核心功能**：
- 🚫 拒绝崩溃：Python 原生解析 JSON
- 📊 可视化 Failover：展示备份链
- 🚀 丝滑切换：数字编号快速切换
- 💓 路由透明：显示心跳和子智能体路由
- 🛡️ 极致安全：本地运行，Key 脱敏

---

### ClawAPI Manager
> "From Cost Optimization to Intelligent Orchestration"

**定位**：完整配置管理平台

## 独特亮点

### 1. 🎯 三合一管理
**OpenClaw Switch**：只管理模型切换  
**ClawAPI Manager**：Models + Channels + Skills 统一管理

### 2. 🌐 多界面适配
**OpenClaw Switch**：只有命令行  
**ClawAPI Manager**：
- Textual TUI（SSH/终端）
- Rich 菜单（受限终端）
- CLI（脚本）
- 对话式接口（QQ/飞书）

### 3. 🤖 AI 驱动
**OpenClaw Switch**：手动输入命令  
**ClawAPI Manager**：
- AI 复杂度预测（Qwen 0.5B）
- 自然语言操作
- 智能路由（自动选免费模型）

### 4. 🔗 通道管理（独有）
**OpenClaw Switch**：无  
**ClawAPI Manager**：
- QQ、企业微信、飞书、钉钉等通道配置
- 一键启用/禁用
- 批量管理

### 5. 📦 任务调度（独有）
**OpenClaw Switch**：无  
**ClawAPI Manager**：
- 多节点负载均衡
- 任务队列
- 失败重试
- 性能追踪

### 6. 💰 成本优化（独有）
**OpenClaw Switch**：无  
**ClawAPI Manager**：
- 智能路由（省钱 30-90%）
- 成本监控
- 预算预警

---

## 功能对比表

| 特性 | OpenClaw Switch | ClawAPI Manager |
|------|----------------|-----------------|
| 定位 | 模型切换工具 | 完整配置管理平台 |
| 功能范围 | 单一（模型） | 三合一（Models + Channels + Skills） |
| 界面 | CLI | TUI + Rich + CLI + 对话式 |
| 智能化 | 无 | AI 预测 + 自动路由 |
| 成本优化 | 无 | 监控 + 优化 |
| 多节点协作 | 无 | 任务调度 + 负载均衡 |
| 通道管理 | 无 | QQ/飞书/企业微信等 |
| 环境适配 | 终端 | SSH/QQ/飞书/脚本 |

---

## 核心差异

**OpenClaw Switch 是螺丝刀，ClawAPI Manager 是瑞士军刀。**

- **OpenClaw Switch**：专注于模型切换，简单高效
- **ClawAPI Manager**：全方位配置管理，智能协作

---

## 适用场景

### 选择 OpenClaw Switch
- 只需要切换模型
- 喜欢简单的命令行工具
- 不需要成本优化和多节点协作

### 选择 ClawAPI Manager
- 需要管理 Models、Channels、Skills
- 需要多种界面（TUI/CLI/对话式）
- 需要成本优化（省钱 30-90%）
- 需要多节点协作和任务调度
- 需要在 QQ/飞书等环境中使用

---

## 总结

ClawAPI Manager 不只是模型切换工具，而是：
- ✅ 完整的配置管理平台
- ✅ 智能的成本优化系统
- ✅ 强大的多节点协作框架
- ✅ 灵活的多界面适配方案

**从成本优化到智能编排，一站式解决方案。**
