# nonebot-plugin-deepseek-chat

NoneBot2 AI 智能对话插件，支持 openai兼容 API，提供多轮对话、人设系统、预算控制、Token 统计等完整功能。

> 即装即用 — `.env` 一行配置即可启动，WebUI 全量管理配置与人设。

## 特性

-  **双 API 兼容** — DeepSeek / SiliconFlow 自动检测，一键切换
-  **多轮对话** — 上下文记忆 + 会话超时管控，6 轮/24h 默认可调
-  **人设系统** — 公开 + 隐藏人设，独立白名单，支持 WebUI 在线增删改
-  **Token 统计** — 每日用量追踪 + 费用估算，WebUI 仪表盘 14 天柱状图
-  **预算控制** — 每日消费封顶 + Token 价格自定义，白名单用户免限
-  **全配置热管理** — `.env` 全覆盖 + WebUI 插件管理在线编辑 + config.py 兜底
-  **图片渲染** — PIL 生成人设预览卡 & 调用统计卡，渐变紫蓝风
-  **黑白名单 & 封禁词** — 用户/群聊级管控，持久化 JSON 存储

## 功能

- 多轮对话 + 上下文记忆
- 人设系统（公开 + 隐藏，可选白名单）
- 切分输出 / 完整输出切换
- 白名单 / 黑名单 / 封禁词管理
- 每日预算控制 + Token 费用统计
- API 额度查询（自动检测 DeepSeek / SiliconFlow）
- WebUI 管理（配置编辑 + 人设管理 + Token 图表）
- 人设预览 / 调用统计图片渲染（PIL）

## 效果预览

### 人设预览

<img src="https://raw.githubusercontent.com/sangonomiya249/nonebot_plugin_aichat_baize/main/screenshots/persona.png" width="400" alt="人设预览">


### WebUI 人设编辑

> 需安装配套 [WebUI 插件](https://github.com/sangonomiya249/nonebot_plugin_webui_baize) 才能使用管理面板、在线编辑配置和人设。

<img src="https://raw.githubusercontent.com/sangonomiya249/nonebot_plugin_aichat_baize/main/screenshots/dashboard.png" width="600" alt="Token仪表盘">

## 安装

```bash
pip install git+https://github.com/sangonomiya249/nonebot_plugin_aichat_baize.git
```

在 bot 项目的 `pyproject.toml` 注册：

```toml
[tool.nonebot]
plugins = ["nonebot_plugin_aichat_baize"]
```

## 配置

三种方式，任选其一：

### 1. `.env` 配置（推荐，无需改代码）

```env
AICHAT_API_KEY=sk-xxx              # API 密钥（必填）
AICHAT_MODEL_ID=deepseek-chat      # 模型名称
AICHAT_API_URL=https://api.deepseek.com/chat/completions  # API 地址
AICHAT_MAX_HISTORY=6               # 保留最近 N 轮对话
AICHAT_SESSION_TIMEOUT=86400       # 会话超时（秒）
AICHAT_REQUEST_TIMEOUT=140         # 请求超时（秒）
AICHAT_MAX_RETRIES=3               # 请求失败重试次数
AICHAT_DAILY_BUDGET=3.0             # 每日预算（元）
AICHAT_INPUT_TOKEN_PRICE=0.000001   # 输入 Token 单价（¥1/百万Token）
AICHAT_OUTPUT_TOKEN_PRICE=0.000004  # 输出 Token 单价（¥4/百万Token）
AICHAT_ADMIN_IDS=123456,789012      # 管理员 QQ（逗号分隔）
所有配置项都以 `AICHAT_` 为前缀，见 [config.py](nonebot_plugin_aichat_baize/config.py)。

### 2. WebUI 插件管理

侧边栏 → 插件管理 → 找到插件 → 点击编辑，在线修改所有配置项。

### 3. 直接改 config.py

编辑 `nonebot_plugin_aichat_baize/config.py` 中的 `CONFIG` 字典。

### SiliconFlow 切换

```env
AICHAT_API_URL=https://api.siliconflow.cn/v1/chat/completions
AICHAT_MODEL_ID=deepseek-ai/DeepSeek-V3
```

## 命令

### 对话

| 命令 | 说明 |
|------|------|
| `@机器人 + 消息` | AI 对话 |
| `/切分 开/关` | 分句模式 / 完整输出切换 |
| `/清除记忆` | 清除个人对话记忆 |
| `/清除所有记忆` | 清除全部会话记忆（管理员） |

### 人设

| 命令 | 说明 |
|------|------|
| `/切换人设 <ID>` | 切换个人人设 |
| `/切换全局人设 <ID>` | 切换全局人设（管理员） |
| `/切换群人设 <ID>` | 切换当前群人设（群主/管理员） |
| `/人设预览` | 查看所有人设卡片 |
| `/重载人设` | 从 JSON 重新加载人设（管理员） |

### 管理

| 命令 | 说明 |
|------|------|
| `/额度` | 查询 API 账户余额 |
| `/调用统计` | 查看调用次数 + 费用 |
| `/重置额度` | 手动重置每日预算 |
| `/白名单 添加/移除 <QQ>` | 白名单管理 |
| `/黑名单 用户/群聊 添加/移除 <ID>` | 黑名单管理 |
| `/添加封禁词 <词>` / `/删除封禁词 <词>` | 封禁词管理 |

## 依赖

- `nonebot2 >= 2.2.0`
- `httpx >= 0.23`
- `Pillow >= 9.0`（可选，图片渲染）
