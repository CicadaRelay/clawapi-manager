# API Cockpit

自动化运维与 API Key 管理集成包。

## 项目结构

```
api-cockpit/
├── config/
│   └── .env.example          # 配置模板
├── lib/
│   ├── antigravity.py        # Antigravity 适配器
│   ├── codex.py              # Codex 适配器
│   ├── copilot.py            # Copilot 适配器
│   └── windsurf.py           # Windsurf 适配器
├── logs/                      # 日志目录（自动创建）
├── check_quota.sh            # 统一配额查询入口
├── auto_rotate.sh            # 自动轮换脚本
├── cockpit-admin.sh          # 多节点运维脚本
├── cron.example              # 定时任务配置示例
└── SKILL.md                  # Skill 文档
```

## 功能模块

### 1. cockpit-tools（API Key 管理）

**配置：**
```bash
cd /root/.openclaw/workspace/skills/api-cockpit
cp config/.env.example config/.env
# 编辑 config/.env，填入你的 API Key
```

**查询配额：**
```bash
./check_quota.sh
```

**自动轮换：**
```bash
./auto_rotate.sh
```

### 2. cockpit-admin（多节点运维）

**健康检查：**
```bash
./cockpit-admin.sh health
```

**检查特定节点：**
```bash
./cockpit-admin.sh status central
./cockpit-admin.sh status silicon
./cockpit-admin.sh status tokyo
```

**重启网关：**
```bash
./cockpit-admin.sh restart central
```

**同步技能：**
```bash
./cockpit-admin.sh sync
```

## 定时任务

复制 `cron.example` 到 `/etc/cron.d/api-cockpit` 启用自动监控：

```bash
cp cron.example /etc/cron.d/api-cockpit
systemctl reload cron
```

## 节点列表

| 节点 | IP | 角色 |
|------|-----|------|
| 中央 | 43.163.225.27 | Gateway 主节点 |
| 硅谷 | 170.106.73.160 | 重型计算（本机） |
| 东京 | 43.167.192.145 | 轻量并发 |

## 告警阈值

- **警告**：80% 配额使用
- **严重**：95% 配额使用（触发自动轮换）
- **CPU/内存**：90% 触发告警

## Telegram 告警

在 `config/.env` 中配置：
```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```
