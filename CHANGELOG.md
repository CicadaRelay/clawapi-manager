# Changelog

## v1.2.0 (2026-03-03)

### 新增功能
- ✅ 协议识别与管理
  - 支持 anthropic-messages、openai-chat、openai-compatible
  - 自动读取现有配置中的 api 字段
  - 显示 provider 的协议类型
  - 支持手动设置协议

- ✅ 故障排查指南
  - 常见错误码对照表（401/403/404/429/500/503）
  - 详细的排查步骤和解决方案
  - 500/503 错误详解
  - 自动 Fallback 配置建议

- ✅ 配置修复功能
  - 自动检测空的 provider 配置
  - 一键删除损坏的配置
  - 从备份恢复配置
  - 配置验证

### 改进
- 📊 Provider 列表显示协议类型
- 🔧 添加 provider 时支持指定协议
- 📝 完善文档（TROUBLESHOOTING.md、HIGHLIGHTS.md）
- 🛡️ 增强配置安全性

### 修复
- 🐛 修复空 provider 导致的验证错误
- 🐛 修复协议类型不匹配的问题

---

## v1.1.0 (2026-03-03)

### 新增功能
- ✅ Textual TUI（完整交互界面）
- ✅ Rich 菜单（受限终端）
- ✅ 对话式接口（QQ/飞书）
- ✅ 智能环境检测
- ✅ Channel 管理

### 核心功能
- 📦 Models 管理（Providers、API keys、Primary & Fallback）
- 🔗 Channels 管理（QQ、企业微信、飞书、钉钉等）
- 🎯 Skills 管理（查看已安装 skills）
- 🌐 多界面支持（TUI、Rich、CLI、对话式）

---

## v1.0.0 (2026-03-02)

### 初始版本
- ✅ 基础配置管理
- ✅ Provider 管理
- ✅ Model 管理
- ✅ 自动备份
- ✅ API key 脱敏

## v1.3.0 (2026-03-03)

### 新增功能
- ✅ **API Key 轮换**
  - 支持配置多个 API Key
  - 自动轮换（rate-limit 时切换到下一个 Key）
  - Cooldown 机制（1分钟 → 5分钟 → 25分钟 → 1小时）
  - Billing disable（余额不足时禁用 5 小时）
  - 显示 Key 状态和统计信息

- ✅ **余额查询**
  - 支持 OpenAI 余额查询
  - 支持 Anthropic 余额查询
  - 余额不足警告（< $5）
  - 格式化输出

- ✅ **Cooldown 状态管理**
  - 显示 Cooldown 状态
  - 显示 Billing disable 状态
  - 显示错误次数
  - 显示最后使用时间
  - 支持手动重置统计

### 核心模块
- `lib/key_rotation.py`: API Key 轮换管理器
- `lib/balance_checker.py`: 余额查询器

### 使用示例

#### API Key 轮换
```python
from lib.key_rotation import KeyRotationManager

manager = KeyRotationManager()

# 添加多个 Key
manager.add_keys('openai', ['sk-key-1', 'sk-key-2', 'sk-key-3'])

# 获取当前 Key
current = manager.get_current_key('openai')

# 模拟 rate-limit 错误，自动轮换
manager.rotate_key('openai', 'rate_limit')

# 查看统计
stats = manager.get_key_stats('openai')
```

#### 余额查询
```python
from lib.balance_checker import BalanceChecker

checker = BalanceChecker()

# 查询 OpenAI 余额
result = checker.check_openai('sk-xxx')
print(checker.format_balance_result(result))

# 查询 Anthropic 余额
result = checker.check_anthropic('sk-xxx')
print(checker.format_balance_result(result))
```


## v1.4.1 (2026-03-03)

### Bug 修复
- ✅ 修复内置 Provider 模板中的协议配置
  - `openai-chat` → `openai-responses`（OpenAI、OpenRouter、Groq）
  - `openai-compatible` → `openai-responses` / `ollama`
  - 统一使用 `baseUrl`（小写 U）而不是 `baseURL`

### 新增
- ✅ 添加火山引擎（VolcEngine）内置 Provider
  - 协议：anthropic-messages（兼容 Anthropic 接口）
  - 模型：doubao-seed-2.0-code

### 支持的协议
OpenClaw 支持的有效协议：
- `openai-completions`
- `openai-responses`
- `openai-codex-responses`
- `anthropic-messages`
- `google-generative-ai`
- `github-copilot`
- `bedrock-converse-stream`
- `ollama`

