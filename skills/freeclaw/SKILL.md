---
name: freeclaw
version: 1.2.0
description: API key management, cost optimization, and smart routing for 40+ AI providers
read_when:
  - "API key management"
  - "model switching"
  - "cost optimization"
  - "provider routing"
  - "freeclaw"
  - "clawapi"
allowed-tools:
  - Bash
  - Read
  - Edit
---

# FreeClaw Skill

FreeClaw manages API keys, cost optimization, and smart routing for 40+ AI providers.

## Quick Commands

```bash
# Check status
python lib/config_manager.py status

# Health check
python lib/cost_monitor.py health

# List/switch models
python lib/model_switcher.py list
python lib/model_switcher.py switch <number>

# Smart routing test
python lib/smart_router.py

# Mesh connectivity (requires redis)
python lib/mesh_bridge.py ping
```

## Configuration

FreeClaw resolves config in this order:
1. `$FREECLAW_CONFIG` environment variable
2. `~/.openclaw/openclaw.json` (OpenClaw integration)
3. `~/.freeclaw/freeclaw.json` (standalone, auto-created)

## Key Modules

| Module | Purpose |
|--------|---------|
| `lib/config_manager.py` | Provider/model/fallback management |
| `lib/model_switcher.py` | Safe model switching with daemon restart |
| `lib/smart_router.py` | Three-tier routing with complexity prediction |
| `lib/cost_monitor.py` | Usage tracking and cost reports |
| `lib/circuit_breaker.py` | Provider health and circuit breaker |
| `lib/mesh_bridge.py` | FSC-Mesh Redis bridge |
