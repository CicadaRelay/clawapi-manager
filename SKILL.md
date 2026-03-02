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
