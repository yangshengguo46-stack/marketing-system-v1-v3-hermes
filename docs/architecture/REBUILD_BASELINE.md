# Agent Core 重建基线

## 一、目标架构

```text
React UI / 微信 / 飞书 / Web 视频工作台
                 │
          Product Event API
                 │
┌────────────────▼─────────────────┐
│ Electron Runtime Host            │
│ 登录 session / secrets / L3动作 │
└───────────────┬──────────────────┘
                │ typed capabilities
┌───────────────▼──────────────────┐
│ Marketing Agent Service          │
│ Hermes loop adapter              │
│ AgentTask + approvals + traces   │
│ Context assembler + policy       │
└───────┬───────────────┬──────────┘
        │               │
┌───────▼──────┐  ┌─────▼────────────────────┐
│ Marketing    │  │ State / Memory / Results │
│ Tool Gateway │  │ SQLite first             │
└──────────────┘  └───────────────────────────┘
```

## 二、代码边界

| 路径 | 边界 |
|---|---|
| `runtime/hermes-agent` | 官方上游源码与必要 fork patch，不放业务数据 |
| `engine/agent_core` | 我们的 task/event/policy/memory/effect/harness adapter |
| `engine/marketing-os` | 热点、账号、内容、发布等领域工具 |
| `electron` | 登录会话、秘密、平台副作用和本机生命周期 |
| `src` | 面向用户的目标、进度、证据、审批、记忆和产物体验 |

## 三、第一批稳定接口

### Agent runtime

- `POST /agent/sessions`：创建或恢复用户/工作区 session。
- `POST /agent/messages`：追加用户目标，立即返回 `task_id/run_id`。
- `GET /agent/runs/{id}/events`：SSE/stream，输出计划、步骤、工具、证据、审批、产物和完成事件。
- `POST /agent/tasks/{id}/pause|resume|cancel`。
- `POST /agent/approvals/{id}/approve|reject`。

### Memory

- `POST /memory/candidates`：只创建候选，不允许调用方绕过治理直接写长期记忆。
- `GET /memory?scope=...`：结构化查询和证据。
- `POST /memory/{id}/correct|forget|lock`。

### Effects

- `POST /effects/intents`：创建发布/发送/费用意图和预览。
- `POST /effects/{id}/execute`：仅 Electron capability host 可执行，要求有效 approval 与幂等键。

## 四、数据真相源

- `task_events` 是任务状态重建的真相源；`agent_tasks` 是当前投影。
- `effect_receipts` 是是否已产生外部副作用的真相源。
- `memory_facts` 保存当前/历史事实；`memory_evidence` 保存来源。
- `content_assets / publications / metrics / experiments` 保存业务结果，不塞进 message 文本。
- `skill_candidates / skill_versions / skill_evaluations` 管理程序性记忆。

## 五、不可妥协项

1. Cookie、Token、Key 不跨 Electron capability boundary。
2. Agent 不拥有任意 Shell、sudo、系统设置和任意文件权限。
3. 发布、删除、发送、付费每次走持久审批和 effect receipt。
4. 不把模型私有推理存入用户数据；只保存可解释摘要和证据。
5. 不以向量相似度替代账号隔离、时间有效性、权限和可信度过滤。
6. 不因 UI 关闭或进程重启丢任务；不因重试重复外部动作。

## 六、首轮完成定义

用户输入“帮我整理 AI 教育行业今天适合抖音账号 A 的热点”：

1. Agent 自然理解目标，绑定账号 A 和抖音。
2. 生成可见计划，不触碰 Cookie。
3. Electron 复用账号 A 登录 session 完成只读采集。
4. Agent 返回带来源、时间和置信度的热点与选题。
5. 需要进入草稿或发布时形成审批卡，未确认不产生外部动作。
6. App 隐藏/重启后继续同一 task。
7. 用户采纳、拒绝及原因进入事件；不会立刻形成未经验证的永久规律。
