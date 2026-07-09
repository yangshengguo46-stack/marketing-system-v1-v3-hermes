# External MCP Integration — 开源社媒 + 内容创作 MCP Server 接入方案

## 概述

将开源社区的社媒自动化 + 内容创作 MCP Server 作为下游工具接入我们的 capability 体系。我们负责审批/effect/隔离/崩溃恢复，外部 MCP Server 负责平台 API 调用、浏览器自动化、语音合成、图片生成和视频剪辑。

同时为 Hermes agent 补充了编剧/导演/内容创作的 skill 知识库。

## 架构

```
Agent (Hermes)
  ↓
tool_gateway (policy + approval + effect chain)
  ↓
external_mcp_bridge (参数翻译 + 服务器选择)
  ↓
External MCP Server (stdio)
  ├── huimei-mcp-server → 11 平台社媒发布
  ├── douyin-upload-mcp-skill → 抖音 CDP 自动化
  ├── mcp-voice-clone → TTS + 声音克隆 (Fish Audio / ElevenLabs)
  ├── mcp-image → AI 图片生成 (Gemini / GPT Image)
  └── reap.video → 视频剪辑 + 字幕 + 配音

Skill Knowledge Base (Hermes agent skills/)
  ├── screenwriting/ → 编剧 (McKee/Save the Cat/角色圣经/结构路由/对话)
  ├── video-production/ → 导演 (9-Agent 流水线/镜头设计/分镜/配音规划)
  └── content-creation/ → 内容创作 (短视频脚本/爆款标题/平台适配/内容分析)
```

**核心原则**：外部工具**永远不直接暴露给 Agent**。所有外部工具映射为 `marketing_*` 能力，经过相同的审批/effect 链路。

## 接入的外部 MCP Server

### 1. huimei 慧媒

| 属性 | 值 |
|---|---|
| 包 | `pip install huimei` |
| 命令 | `huimei-mcp-server` |
| 平台 | 抖音、小红书、B站、快手、微博、视频号、TikTok、头条、百家号、微信公众号、知乎 (11) |
| 架构 | CLI(本地 Playwright) + Java Backend(云端调度) |
| MCP 工具 | `huimei_login`, `huimei_status`, `huimei_logout`, `huimei_platforms`, `huimei_accounts`, `huimei_publish` |

### 2. douyin-upload-mcp-skill

| 属性 | 值 |
|---|---|
| 仓库 | `WJZ-P/douyin-upload-mcp-skill` |
| 命令 | `node mcp-server.js` |
| 平台 | 抖音 |
| 架构 | 纯本地 CDP + Daemon 浏览器管理 |
| MCP 工具 | `douyin_publish_video`, `douyin_publish_imagetext`, `douyin_check_login`, `douyin_probe`, `douyin_screenshot`, `douyin_navigate_to`, `douyin_reload_page`, `douyin_browser_info` |

## 工具映射

| 我们的能力 | 外部服务器 | 外部工具 | 级别 | 审批 |
|---|---|---|---|---|
| `marketing_external_login` | huimei | `huimei_login` | controlled | ✅ |
| `marketing_external_status` | huimei | `huimei_status` | read | ❌ |
| `marketing_external_platforms` | huimei | `huimei_platforms` | read | ❌ |
| `marketing_external_accounts` | huimei | `huimei_accounts` | read | ❌ |
| `marketing_external_publish` | huimei | `huimei_publish` | effect | ✅ |
| `marketing_douyin_publish_video` | douyin-upload | `douyin_publish_video` | effect | ✅ |
| `marketing_douyin_publish_imagetext` | douyin-upload | `douyin_publish_imagetext` | effect | ✅ |
| `marketing_douyin_check_login` | douyin-upload | `douyin_check_login` | controlled | ✅ |

## 平台覆盖

| 平台 | huimei | douyin-upload | 我们原生 |
|---|---|---|---|
| 抖音 | ✅ | ✅ | ✅ (Playwright MCP) |
| 小红书 | ✅ | — | — |
| B站 | ✅ | — | — |
| 快手 | ✅ | — | — |
| 微博 | ✅ | — | — |
| 视频号 | ✅ | — | — |
| TikTok | ✅ | — | — |
| 头条 | ✅ | — | — |
| 百家号 | ✅ | — | — |
| 微信公众号 | ✅ | — | — |
| 知乎 | ✅ | — | — |

## 安全边界

1. **审批链路不绕过**：所有 effect 级外部工具必须经过 `create_effect_intent` → `decide_approval` → `record_effect_receipt`
2. **参数翻译**：外部工具参数由 `_translate_params` 统一翻译，Agent 只看到我们的 schema
3. **服务器可用性检查**：`check_server_available` 在调用前验证外部命令存在
4. **进程隔离**：`McpStdioClient` 以子进程方式运行外部 MCP Server，独立生命周期
5. **错误隔离**：外部服务器崩溃返回 error 状态，不影响我们的 task 状态

## 与现有系统的关系

- **tool_manifest.py**：外部工具不直接注册到 manifest，而是通过 `external_mcp_bridge.bridge_call` 在 effect 执行时调用
- **tool_gateway.py**：Agent 调用 `marketing_external_*` 时，gateway 正常执行 policy/approval，审批通过后 bridge 才转发
- **store.py**：effect_intent 和 receipt 正常记录，外部工具的返回值作为 receipt 存入 DB
- **mcp_process_manager.py**：我们的 Playwright MCP 管理器仍用于读取类操作（搜索、采集），外部 MCP Server 用于发布类操作

## 后续路线

1. **huimei 依赖云端后端**：需要评估其 Java Backend 的数据隐私和账号安全
2. **douyin-upload 的 Daemon 模式**：可以借鉴其闲置 30 分钟自动销毁的设计优化我们的 `_lifecycle`
3. **更多平台 MCP**：关注 turbopush-mcp（20+ 平台）和 AmpliPost（Multi-Agent 协作）的发展
4. **MCP Skills 标准化**：关注 MCP 官方 SEP-2640 Skills Extension 提案
