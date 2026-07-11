# Hermes 原生营销 Agent 架构

> 状态：当前唯一架构基线
> 上位原则：`PRODUCT_PHILOSOPHY.md`

## 唯一运行时

```text
Desktop / Messaging / Future Web surfaces
                    │
                    ▼
        Marketing OS Hermes Product Fork
                    │
 ┌──────────────────┼──────────────────┐
 │                  │                  │
 ▼                  ▼                  ▼
Session/Task     Agent/Tools       Gateway/Cron
Memory/Skill     Marketing domain  MCP/Channels
                    │
                    ▼
 Account / Evidence / Content / Preflight / Receipt / Candidate
                    │
                    ▼
       SQLite truth + artifact store + platform facts
```

不存在“Marketing OS 调用 Hermes”。Marketing OS 就是这套被改造后的 Hermes 产品源码。

## 原生 owner

| 职责 | 唯一 owner | 营销改造方式 |
|---|---|---|
| 对话与自主规划 | Hermes Agent loop | 注入长期经营身份、证据边界和闭环目标 |
| 会话与账号绑定 | `hermes_state.SessionDB` | 会话固定 user/account scope，分支与恢复继承 |
| 长任务与恢复 | Hermes task/checkpoint | 内容经营步骤写 checkpoint，外部动作防重复 |
| 工具执行 | Hermes tool registry/middleware | 原生注册账号、证据、内容能力；预演在 action 前自动发生 |
| 外部副作用 | Hermes approval/effect boundary | 发布、付费、敏感账号动作必须生成可验证回执 |
| 记忆 | Hermes memory/Skill ecosystem | 只接收治理通过的候选；不保存草稿和瞬时热点 |
| 消息渠道 | Hermes Gateway | 飞书/微信只是同一会话 surface |
| 定时任务 | Hermes cron/scheduler | 指标 checkpoint、复盘和异常提醒 |
| 产品界面 | `apps/desktop` | 展示结论、资产、回执和控制，不拥有第二业务状态机 |

## 经营领域

当前原生源码落点：

```text
agent/product.py
agent/marketing/
  domains/
    account_context.py
    account_lifecycle.py
    evidence.py
    content_policy.py
    content_assets.py
  intelligence/
    content_feature_snapshot.py
    content_prediction.py
    content_rubric.py
    influence_score.py
    preflight_decision.py
    production_preflight.py
    content_retro.py
    learning_governance.py
    memory_classification.py
    store.py
gateway/product_messaging.py
tools/marketing_tools.py
```

这些目录是一个 Agent 内部的职责拆分，不是插件、sidecar 或第二个 Agent。

## 唯一业务状态库与数据飞轮

Hermes `state.db` 是会话、账号、受众、内容、预演、回执、指标和学习候选的唯一产品数据库 owner。历史 `agent_core.db` 只允许一次性、可校验迁移，不再接收新写入；Electron 不决定业务数据库路径。

- 私有经营事实保留 user/account scope，驱动本地记忆、账号策略和技能学习。
- 匿名知识贡献必须显式授权、去标识化、结构化并经过最小群组阈值，才能进入未来中央知识库。
- 中央知识以带版本、平台、地区、时间窗、样本量和置信度的知识包返回 Agent，只提供先验；本地 Receipt 永远拥有更高事实权重。
- 本地贡献 outbox 的 owner 是 `agent/marketing/domains/knowledge_flywheel.py`；它只接收治理通过的 learning candidate 和显式 consent_ref，不拥有网络上传或中央聚合。

### 短视频声音信号

`mcp/marketing-browser` 原生增加 `browser_extract_short_video_signals`，从真实账号浏览器页面提取作品指标和平台声音身份。工具结果经 Hermes post-tool seam 固化为 EvidenceRecord、Sound 和 ShortVideoObservation，Electron 不采集、不解析也不保存这些数据。

`ShortVideoSignalRepository` 以平台声音 ID 去重，使用真实观察计算覆盖、重复出现、使用规模、新鲜度、目标内容匹配和版权安全。它向预演提供声音先验，向草稿提供受证据约束的 `sound_plan`；发布回执继续携带 `sound_id`，后续只能通过匹配样本或 A/B 变体提高因果归因。

## 三核数据合同

### PreflightRecord

- action 前创建。
- 绑定 user/account/platform/session/plan。
- 保存输入快照、公式版本、分项分数、缺失维度和决策。
- action 后禁止修改；重新预演产生新版本。

### ReceiptRef

- 指向真实平台、工具、素材、模型、渲染或审批事实。
- `source_kind + source_id + receipt_type` 幂等。
- 摘要脱敏；Cookie、Token、Key 不得进入。
- 不做因果解释。

### LearningCandidate

- 类型：memory / strategy / weight / skill。
- 引用 preflight、receipt、指标和用户反馈。
- 默认 pending。
- accepted 也只代表候选通过治理，不等于已经改写永久策略。

## 内容动作链

```text
User goal
→ Session account scope
→ AccountContext
→ EvidencePack
→ ContentProductionPolicy
→ production plan checkpoint
→ feature extraction + InfluenceOS
→ PreflightDecision
→ draft gate
→ ContentAsset + immutable feature snapshot
→ approval/effect
→ publish ReceiptRef
→ metric checkpoints and receipts
→ content_retro(prediction, actual)
→ learning candidate
→ replay/user governance
→ Hermes memory / account strategy / Skill
```

## InfluenceOS 在架构中的位置

公式是 Agent 的内部判断内核，不拥有自己的工作流：

```text
Preflight_t = f(Content_t, Account_t, Memory_t, ReceiptHistory_t, Platform_t, Sound_t)
Retro_t = compare(Preflight_t, Receipt_t)
Candidate_t = interpret(Retro_t, repeated evidence, user feedback)
```

权重有版本，预测有时间，结果有来源。没有足够数据时输出缺失维度和低置信，不输出伪精确流量承诺。

## 内容与平台分层

- ContentOps：受众价值、钩子、结构、证据、信任、情绪、行动路径。
- PlatformOps：格式、分发闸门、合规、标签、时长、编辑器和平台表达。
- 同一父内容生成平台变体，但共享同一事实、受众目标和经营假设。
- 平台知识必须带来源、地区、版本、生效/失效时间。

## 账号浏览器是原生 MCP

Marketing OS 不再为每个平台堆一套 Electron IPC、Provider 和脚本补丁。账号真相由 Hermes
原生 AccountRegistry 拥有，浏览器上下文由改造后的 Playwright MCP 原生 owner 拥有；MCP 通过
`createConnection(config, contextGetter)` 直接取得当前 Hermes 账号上下文。

- Hermes AccountRegistry 负责账号注册、绑定、切换、授权、退出、删除和 BrowserContext 租约。
- 改造后的 Playwright MCP 同时是 BrowserContext owner，负责 Cookie/profile、登录页面和受控浏览器上下文，并保留上游完整工具能力。
- 平台 Skill 只描述平台语义和操作流程，不重复实现浏览器、会话或账号存储。
- Electron 只显示和交互，不拥有账号、Cookie、profile、浏览器执行或自动化业务真相。
- 上游 Playwright MCP 的成熟工具原封不动保留；不建立 MCP 代理、子进程路由或 Electron browser-host。
- 同一账号 profile 同时只允许一个执行 owner；切换账号不复制 Cookie，也不共享 profile。
- AccountRegistry 的断开/删除直接驱动 MCP owner 释放；MCP 同时定期复核账号权限，防止绕过 owner 的旧写入留下活跃上下文。只有删除才清理该账号 profile/output。
- stdio 关闭必须先等待 persistent BrowserContext 落盘，禁止依靠父进程强杀，否则重启后可能丢失登录态。
- 未认证或需重新验证的账号由 MCP owner 自动创建 headed context；已认证账号才允许恢复为后台 context，Electron 不选择浏览器模式。

原生账号生命周期落在 `agent/account_registry.py` 与 `hermes_state.SessionDB.marketing_accounts`。
AccountRegistry 签发的 BrowserContext lease 只包含 session、user、account、platform、profile_key
和 auth_state，不包含任何认证秘密；pending/stale 账号只能用同一上下文完成登录或重新验证，
断开或删除的账号不能再获得执行租约。

Playwright MCP 官方 `createConnection(config, contextGetter)` 要求 `contextGetter` 在同一个 Node
进程中返回真实 JavaScript `BrowserContext`；Python AccountRegistry 不能跨语言伪造该对象。这是
新增 `mcp/marketing-browser` 进程边界的充分证据。该入口只消费 Hermes 签发的租约并创建上下文，
不拥有账号注册、绑定、切换、授权或删除，也不代理、改写或复制 Playwright MCP 工具。

## 视频边界

- 图文、不露脸视频、高阶视频共享账号、证据、素材、音频、版权、回执和复盘合同。
- 高阶视频片子预演独立判断剧本到画面、镜头、连续性、节奏、声音和预算。
- 总营销预演不能把电影制作维度塞进一个总分。
- 视频 Web 工作台是未来 surface，不拥有第二 Agent、记忆或任务系统。

## 禁止架构

- 外层 FastAPI Agent。
- `HermesAgentService` 或 HTTP 回调同机 Agent。
- 第二 Session/Task/Memory owner。
- 在 Hermes/Playwright 已有能力更优秀时另造重复 Provider、MCP、Skill、Plugin 或 Secret 管理器。
- 为账号隔离牺牲 Playwright MCP 的成熟工具，或在 MCP 外堆一条平台脚本补丁链。
- Electron UI 直接修改业务真相。
- `publishing.json` 与 SQL 双写。
- Electron profile 与 Playwright profile 永久并存为两个身份世界。
- 模型直接修改永久权重或把一次结果写成账号真理。

## 迁移纪律

1. 先查 Hermes 原生 owner。
2. 已有能力直接修改原生 owner。
3. 只有通用 Hermes 不具备的经营领域状态才新增。
4. 从 Git 历史只恢复纯算法、合同和验证规则，不恢复旧壳。
5. 每条纵切必须同时包含代码、迁移、自动化、开发机和真人证据等级。
