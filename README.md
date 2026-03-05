<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=6,11,20&height=180&section=header&text=FreeClaw&fontSize=42&fontColor=fff&animation=fadeIn&fontAlignY=36&desc=%E2%9C%A8%20API%20Hub%20for%2040%2B%20AI%20Providers%20%E2%9C%A8&descSize=16&descAlignY=56" />
</p>

<p align="center">
  <a href="#install"><img src="https://img.shields.io/badge/-Install-ff69b4?style=for-the-badge&logo=hackthebox&logoColor=white" /></a>
  <a href="#features"><img src="https://img.shields.io/badge/-Features-a855f7?style=for-the-badge&logo=sparkles&logoColor=white" /></a>
  <a href="#usage"><img src="https://img.shields.io/badge/-Usage-06b6d4?style=for-the-badge&logo=windowsterminal&logoColor=white" /></a>
  <a href="#architecture"><img src="https://img.shields.io/badge/-Architecture-f59e0b?style=for-the-badge&logo=diagramsdotnet&logoColor=white" /></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-1.2.0-ff69b4?style=flat-square" />
  <img src="https://img.shields.io/badge/python-3.11+-a855f7?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/providers-40%2B-06b6d4?style=flat-square" />
  <img src="https://img.shields.io/badge/savings-30--90%25-10b981?style=flat-square" />
  <img src="https://img.shields.io/badge/license-MIT-f59e0b?style=flat-square" />
</p>

<p align="center">
  <code>( *^-^)p ～ smart routing ～ cost optimization ～ multi-provider ～ q(^-^* )</code>
</p>

---

## `>_ What is FreeClaw?`

> *"From Cost Optimization to Intelligent Orchestration"* ～(^-^～)

FreeClaw manages your AI API keys, monitors costs, and **automatically routes tasks to the cheapest available model** — saving you 30-90% on API spending.

```
                    +-----------+
  Your App  ------> | FreeClaw  | ------> OpenAI
  Claude Code       |  Hub      | ------> Anthropic
  Any Client        | (routing) | ------> Google
                    |  (^_^)    | ------> DeepSeek
                    +-----------+ ------> 40+ more...
```

<br>

## `>_ Features` {#features}

<table>
<tr>
<td width="50%">

### ～ Smart Routing ～
```
Simple task  --> Free models  (100% savings)
Medium task  --> Budget models (50-70% savings)
Complex task --> Premium models (full power)
```
AI complexity prediction auto-selects the tier!

</td>
<td width="50%">

### ～ Cost Tracking ～
```
 Daily spending .... $2.40
 Free tier used .... 847 calls
 Money saved ...... $18.60
 -------------------------
 Efficiency ....... 88.6% (^o^)
```

</td>
</tr>
<tr>
<td>

### ～ Circuit Breaker ～
```
Provider down? No problem!
  openai .... [OPEN]  (healthy)
  anthropic . [OPEN]  (healthy)
  groq ...... [HALF]  (recovering)
  deepseek .. [CLOSED](bypassed)
```
Auto-fallback, zero downtime.

</td>
<td>

### ～ Multi-Interface ～
```
  TUI ......... Textual (SSH)
  Rich ........ Interactive menu
  CLI ......... Scripts & bots
  Hub ......... OpenAI-compatible API
```

</td>
</tr>
</table>

<br>

## `>_ Install` {#install}

```bash
# Standalone (no OpenClaw needed!)
git clone https://github.com/2233admin/freeclaw.git
cd freeclaw
pip install -r requirements.txt

# Or install as package
pip install .                    # core only
pip install ".[tui]"             # + beautiful TUI
pip install ".[mesh]"            # + Redis cluster support
pip install ".[tui,mesh]"        # everything! (>w<)
```

<details>
<summary> <b>As OpenClaw Skill</b> (click to expand) </summary>

```bash
# If you have OpenClaw installed, FreeClaw auto-detects it
# Config priority:
#   $FREECLAW_CONFIG > ~/.openclaw/openclaw.json > ~/.freeclaw/freeclaw.json
```

</details>

<br>

## `>_ Usage` {#usage}

### Quick Start ～

```bash
# Health check
python lib/cost_monitor.py health

# Launch TUI with startup animation
python clawapi-rich.py

# Route a task (returns best model)
python lib/smart_router.py route "translate hello to Japanese"

# Switch primary model
python lib/model_switcher.py list
python lib/model_switcher.py switch 3
```

### CLI Commands ～

```bash
./clawapi status                    # Full status overview
./clawapi providers                 # List all providers
./clawapi models                    # List all models
./clawapi set-primary deepseek/deepseek-chat
./clawapi add-fallback minimax/MiniMax-M2.5
./clawapi validate                  # Check config health
```

### TUI Preview ～

```
  ______              _____ _
 |  ____|            / ____| |
 | |__ _ __ ___  ___| |    | | __ ___      __
 |  __| '__/ _ \/ _ \ |    | |/ _` \ \ /\ / /
 | |  | | |  __/  __/ |____| | (_| |\ V  V /
 |_|  |_|  \___|\___|\_____|_|\__,_| \_/\_/

  API Hub for 40+ AI Providers

  ok Config       openclaw.json
  ok Providers    2 loaded
  ok Primary      claude-proxy/claude-sonnet-4
  ok Fallbacks    0 models
  ok Router       ready
  ok Breaker      ready

  2 providers  |  4 models  |  0 fallbacks
```

<br>

## `>_ How It Saves Money`

| Task | Example | Before | After | Savings |
|:-----|:--------|-------:|------:|--------:|
| Simple | "what time is it?" | $0.015 | **$0.00** | `100%` |
| Medium | "summarize this PR" | $0.30 | **$0.10** | `67%` |
| Complex | "architect a microservice" | $1.50 | **$1.50** | `0%` |

> Average savings: **30-90%** depending on task mix (o^-^o)b

<br>

## `>_ Supported Providers`

<p>
  <img src="https://img.shields.io/badge/OpenAI-412991?style=flat-square&logo=openai&logoColor=white" />
  <img src="https://img.shields.io/badge/Anthropic-191919?style=flat-square&logo=anthropic&logoColor=white" />
  <img src="https://img.shields.io/badge/Google-4285F4?style=flat-square&logo=google&logoColor=white" />
  <img src="https://img.shields.io/badge/DeepSeek-0A0A0A?style=flat-square" />
  <img src="https://img.shields.io/badge/Groq-F55036?style=flat-square" />
  <img src="https://img.shields.io/badge/Moonshot-000000?style=flat-square" />
  <img src="https://img.shields.io/badge/OpenRouter-6366f1?style=flat-square" />
  <img src="https://img.shields.io/badge/Ollama-000000?style=flat-square" />
  <img src="https://img.shields.io/badge/VolcEngine-3370FF?style=flat-square" />
  <img src="https://img.shields.io/badge/MiniMax-FF6B6B?style=flat-square" />
  <img src="https://img.shields.io/badge/...and%2030%2B%20more-gray?style=flat-square" />
</p>

<br>

## `>_ Architecture` {#architecture}

```
freeclaw/
  ├── clawapi                # Unified CLI entrypoint
  ├── clawapi-rich.py        # Rich TUI (with startup animation!)
  ├── clawapi-tui.py         # Textual TUI (full interactive)
  │
  ├── lib/
  │   ├── constants.py       # Config path resolution
  │   ├── config_manager.py  # Provider/model/fallback management
  │   ├── model_switcher.py  # Safe model switching
  │   ├── smart_router.py    # Three-tier intelligent routing
  │   ├── cost_monitor.py    # Usage tracking & reports
  │   ├── circuit_breaker.py # Provider health & auto-fallback
  │   ├── provider_adapter.py    # Unified provider adapter
  │   ├── builtin_providers.py   # 40+ provider templates
  │   ├── ai_complexity_predictor.py  # AI task analysis
  │   └── mesh_bridge.py    # FSC-Mesh Redis bridge
  │
  ├── .claude-plugin/        # Claude Code plugin metadata
  ├── skills/freeclaw/       # OpenClaw skill definition
  ├── config/                # Configuration templates
  └── data/                  # Runtime data
```

### Config Resolution ～

```
$FREECLAW_CONFIG          # env var (highest priority)
  └─> ~/.openclaw/openclaw.json   # OpenClaw integration
       └─> ~/.freeclaw/freeclaw.json  # standalone (auto-created)
```

<br>

## `>_ Troubleshooting`

<details>
<summary>Common issues</summary>

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for:
- Protocol mismatch errors
- Config file corruption recovery
- API key expiration detection
- Circuit breaker status

</details>

<br>

## `>_ Links`

<p>
  <a href="https://github.com/openclaw/openclaw"><img src="https://img.shields.io/badge/OpenClaw-main%20project-ff69b4?style=flat-square" /></a>
  <a href="https://openrouter.ai"><img src="https://img.shields.io/badge/OpenRouter-free%20models-6366f1?style=flat-square" /></a>
</p>

<br>

---

<p align="center">
  <code>made with mass mass love by mass mass people ～(=^-^)ノ</code>
</p>

<p align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=6,11,20&height=100&section=footer" />
</p>
