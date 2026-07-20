# Marketing OS Durable Multi-Agent Harness 架构

> 状态：当前重构目标基线
> 日期：2026-07-18
> 上位约束：`PRODUCT_PHILOSOPHY.md`、`NATIVE_ARCHITECTURE.md`

## 一、裁决

Marketing OS 不引入第二个 Agent 产品、第二套业务数据库或由 Electron 拥有的流程状态。重构目标是在 Hermes Python 本体中建立一个可恢复的执行 Harness：领域 Repository 继续拥有业务事实，Harness 只拥有执行事实，多个 Agent 只是受边界约束的 Worker。

这不是全仓推倒重写，也不是把 LangGraph、Temporal、AutoGen 或 A2A 整套搬进来。现有 Hermes Agent、Session、Skill、MCP、Memory、Cron、领域 Repository、Video IR、渲染器和 Receipt 底座继续保留；错误的自由 prompt 编排按纵切逐条迁移、验证、删除。

```text
Desktop / Messaging / Cron
        │ structured command / query / approval
        ▼
Hermes Durable Harness
  Goal → Workflow → Step DAG → Attempt
    │        │          │          │
    │        │          │          ├─ lease / heartbeat / retry
    │        │          ├─ artifact / approval / receipt
    │        └─ event log / checkpoint / budget / policy
    └─ bounded coordinator + specialist workers
        │ typed domain commands only
        ▼
Marketing domain owners
  Entity / Evidence / Topic / Preflight / Content / Media / Video /
  Draft / Publish / Metric / Retro / Learning
        │
        ▼
Hermes state.db + artifact store + platform facts
```

Electron 永远只负责显示、输入和承接审批交互。账号、Cookie、浏览器 profile 和平台执行属于 AccountRegistry、Browser MCP、Provider 与 Python owner；Harness 不改变这条铁律。

## 二、已核实的当前缺口

### 2.1 产品动作没有真正的 durable task

当前 `marketing.operation.start` 在 Gateway 中创建隐藏 `desktop-product` Session，再把结构化输入翻译为自然语言 prompt 交给自由 Agent turn。`marketing_operations` 只有 `working / waiting / complete / error` 四态，没有 Step、Attempt、Lease、Heartbeat、幂等键或恢复游标；Gateway 重启后未完成 turn 会被直接结算为 error。

结果归属还依赖运行前后扫描领域对象 ID 的差集。在两个同作用域任务并行时，一个任务可能把另一个任务创建的对象认成自己的结果。该投影只能作为迁移期兼容读模型，不能继续承担工作流 owner。

### 2.2 通用多智能体能力与产品任务没有接通

Hermes 已有两类可复用能力：

- `delegate_task`：隔离上下文、限制 toolset、并行子 Agent、事件投影；但活跃 child 主要是进程内记录，不是产品级可恢复 DAG。
- Kanban `tasks / task_runs / task_events`：已有 WAL + CAS claim、依赖门、Attempt、Lease、Heartbeat、stale reclaim、失败熔断和结构化 handoff；但当前产品运行库中的 Kanban 没有真实任务，Marketing operation 也不使用它。

Harness 应提炼并复用这些原生执行原语，而不是再建第五套任务概念。Kanban 面板不成为营销业务 owner；共享的是内核和状态转移语义，不是把产品事实塞进用户 Kanban 卡片。

### 2.3 视频主链边界错误

当前未提交实现仍以 `cross_platform_campaign / article script → storyboard → video` 为主要路径，视频 production 需要接受后的图文 campaign 或脚本。用户要求的正确边界是：预演通过的 TopicBrief 同时派生图文和视频两个兄弟分支；Video Director 自己完成平台视频策划、脚本/旁白、shot plan、素材检索、版权判断、声音、渲染和 QA，不等待图文产物。

### 2.4 副作用状态机不可恢复

视频渲染和 TTS 目前在 RPC/进程内同步执行，常见状态是 `approved → running → completed/failed`。进程在 `running` 中死亡时，没有租约回收与安全续跑合同。通用危险命令审批也主要是进程内队列和阻塞 Event；它不能充当跨小时、跨重启的产品审批。

### 2.5 owner 仍有漂移

- 33 张历史表已经有非空 `entity_id` 和数据库级防错，但不少 Repository 查询仍以 `account_id` 为主，应用层没有真正做到 entity-first。
- 图文输入和视频设定仍有业务草稿进入 Renderer localStorage；这不是权威事实，但重启/跨 surface 不能可靠恢复。
- 中央 `schema.py / SessionDB` 之外，若干 Repository 仍自行 `_ensure_schema`，存在迁移合同漂移风险。
- 写型营销工具大量进入默认 core toolset，Coordinator 和专职 Worker 的最小权限没有分开。
- Cron 仍可能启动自由 Agent；Provider 与产品后台任务仍有进程级全局状态。

## 三、唯一数据边界

| 事实类型 | 唯一 owner | Harness 只保存什么 |
|---|---|---|
| 经营主体、账号、平台绑定 | Operating Entity / AccountRegistry | `entity_id` 与明确的 action `account_id` 引用 |
| 证据、选题、预演、平台蓝图 | 对应 Marketing Repository | 输入版本、对象 ID、内容 hash |
| 图文、视频、素材、草稿 | Content/Video/Media/Draft Repository | 不可变 Artifact 引用与 canonical version |
| 发布、费用、删除、外发 | Effect owner + Provider + Receipt | effect intent、idempotency key、approval、receipt |
| 指标、复盘、学习 | Metric/Retro/Learning owner | 调度游标、结果引用、治理状态 |
| Task、Step、Attempt、Lease | Hermes Harness | 完整执行事实与 append-only Event |
| 页面 tab、筛选、展开状态 | Electron presentation state | 不进入 Harness 或领域事实 |

Agent 不直接写表，只能调用有 schema 的 domain command。Harness 不复制正文、素材元数据或平台指标；它保存对象引用、输入/输出 hash、版本、策略和回执。领域写入与 Step 结算之间使用同事务 outbox 或可重放 settlement，避免“业务成功但任务仍失败”。

## 四、Harness 执行模型

### 4.1 核心对象

| 对象 | 语义 |
|---|---|
| `Workflow` | 一个用户目标或系统目标，绑定 user/entity、来源、预算、策略版本 |
| `Step` | DAG 节点，声明输入/输出 schema、依赖、worker role、toolset、资源范围和重试策略 |
| `Attempt` | Step 的一次领取与执行，固定模型、prompt、tool 和代码版本 |
| `Artifact` | 不可变中间产物；真正结果，不用聊天文字冒充 |
| `Approval` | 可持久等待、可拒绝、可过期、恢复时重新校验的决定 |
| `EffectIntent` | 外部副作用执行前冻结的对象、参数、预算与幂等键 |
| `Receipt` | LLM/tool/provider/effect 的输入 hash、输出、耗时、成本和事实引用 |
| `Event` | append-only 状态变化，供恢复、订阅、审计和 replay |
| `Lease` | `resource_scope` 的限时执行权，配合 heartbeat 与 stale reclaim |

### 4.2 状态

```text
workflow: queued → planning → running → waiting_approval → running
                         ├→ retrying ────────────────┘
                         └→ paused / failed / cancelled / completed

step: blocked → ready → leased → running → succeeded
                         ├→ waiting_approval
                         ├→ retry_wait → ready
                         └→ failed / cancelled
```

每个状态转换由 Python 代码校验并追加 Event。模型可以提出 plan 或 replan，但不能自行把 Step 标为成功、绕过依赖、批准副作用或写 canonical 版本。

### 4.3 并发规则

只并行无写冲突且能独立验收的节点。默认 fan-out 上限 3–5；每个 Worker 必须收到目标、边界、证据范围、允许工具、输出 schema、预算和停止条件。

- 多来源采集、各平台适配、图文/视频兄弟分支、素材搜索、渲染候选、平台指标回收可以并行。
- 同一文章或视频 revision 不允许多 Agent 直接覆盖。
- 采集 Worker 只提交 staging Artifact，由单一 Reducer 去重并调用领域 command。
- Evaluator 只产出评审 Artifact，不偷偷修改产物。
- 写入以 `resource_scope + lease + expected_entity_version + idempotency_key` 保护；冲突后基于最新 canonical version 重做，禁止 last-write-wins。

## 五、首个产品纵切

```text
Daily signals / evidence fan-out
  → candidate reducer
  → platform fit fan-out
  → preflight + prediction reducer
  → recommended TopicBrief
      ├─ per-platform Article Writer
      │   → platform-native final draft → ArticleDraft Preflight
      │   → bounded rewrite (max 2) → Draft Box
      └─ per-platform Video Showrunner
          → VideoTreatment (hook/voice/beat/claim/shot/sound contract)
          → Treatment Preflight → bounded revision (max 2)
          → library search + rights-cleared web search in parallel
          → playable proxy/previs → audio/captions
          → Remotion / HyperFrames / FFmpeg render activities
          → technical QA + observed-cut review (`video_analyze`)
          → Cut Preflight → Draft Box
  → human review
  → publish approval/effect
  → cross-day metrics fan-out
  → retro + governed learning
```

`TopicBrief` 必须带原始选题、EvidencePack、预演/预测、实际推荐平台、各平台匹配、目标账号绑定和平台蓝图。图文与视频只共享这个上游事实，不共享彼此的脚本、分镜或生命周期。缺个人/账号样本时，公开平台、市场、基准和内容信息作为冷启动 prior 继续支持可逆草稿，同时降低置信且禁止精确流量承诺。中央 Topic Workflow 到视频只保留一个 `video.official_kanban` 提交 Step；提交后由官方 `kanban-video-orchestrator` 独占执行图。Remotion、HyperFrames、FFmpeg、TTS、素材 Provider 和 `video-use` 都是该官方团队的执行工具，不是另一个项目 owner。

## 六、审批与恢复

| 风险层 | 默认处理 |
|---|---|
| 本地读取、分析、生成不可变候选 | 自动 |
| 白名单素材源、已授权素材、预算内本地渲染 | 策略允许时自动 |
| 版权不明、付费超预算、账号权限变化 | 持久审批 |
| 正式发布、不可逆删除、敏感数据外发 | 永远逐 effect 审批 |

恢复时必须先读取已有 Artifact、Receipt 和 EffectIntent，再决定续跑；禁止简单重放整个 Agent 对话。所有网络、模型、下载、TTS、渲染和发布调用都作为可回执 Activity，按错误类型区分瞬态重试、等待输入和永久失败。Pending Approval 同时保存 agent/tool/contract 版本；恢复时版本不兼容则要求重新计划或重新审批。

## 七、框架取舍

- 保留并改造 Hermes AIAgent 作为 `AgentRunner`；现有 delegate 作为 bounded worker adapter。
- 提炼 Kanban 的 CAS/lease/attempt/reclaim 原语，形成可在 `state.db` 产品作用域使用的原生执行内核；不直接复用共享 Kanban board 作为业务库。
- OpenAI Agents SDK 可作为未来可选 runner；其 manager/handoff、HITL 和 trace 语义是参考，不成为业务 owner。
- LangGraph 只参考 checkpoint、pending writes 和 interrupt；不新增另一套 checkpoint 数据库。
- Temporal 只参考 Workflow/Activity、durable retry 和 Signal 语义；本地桌面阶段不引入常驻 Temporal 服务。未来多机执行可实现可插拔 backend。
- MCP 是 Agent 到工具/能力的边界，不负责多 Agent 业务协调。
- A2A 的 Task/Message/Artifact 合同可作为未来远程 Worker 接口；内部第一阶段不开放网络 A2A。

## 八、迁移台账

| 批次 | 目标 | 删除门 | 证据要求 |
|---|---|---|---|
| `H0` | 冻结新功能，保存 Git/DB/运行基线，标出当前未提交改动中的保留与弃用路径 | 无 | owner map、脏变更清单、台账对账 |
| `H1` | 原生 Harness schema/repository/event log/lease；现有 operation 先以单 Step 兼容运行 | operation 仍保留 | schema、CAS、并发、断电、重复执行测试 |
| `H2` | `workflow.list/get/subscribe/cancel/retry/approve`，Desktop 改读后端 projection | 删除内存任务 owner 与轮询猜测 | Renderer reload、Gateway 重启、长等待恢复 |
| `H3` | Daily Topic DAG 与 TopicBrief；图文、视频成为兄弟分支 | 删除 campaign/script → video 主入口 | 同选题并行产出两个独立 branch |
| `H4` | 官方 Hermes 视频 Kanban、可信素材、真实旁白/时间码、renderer/editor/reviewer、Draft Box 结算 | 删除 Marketing 内部视频 DAG、旧音频/IR/质量/renderer 执行模块和直调 RPC | 官方七 profile 独立完成真实素材/旁白/渲染/局部返工到草稿箱 |
| `H5` | entity-first Repository 与 schema 单 owner | 逐表删除 trigger 推断和 repo `_ensure_schema` | 双主体/多平台隔离、迁移回滚 |
| `H6` | Cron 只 enqueue；Provider/effect 进入 leased Activity + outbox | 删除进程级后台任务 owner | 限流、崩溃、unknown effect、幂等恢复 |
| `H7` | 最小 role toolsets、trace/eval/replay、旧 operation prompt 编排清理 | 删除自由 prompt 工作流和写型默认 core 工具 | outcome + trajectory + recovery + cost eval |

每个批次必须先落只读历史投影，再迁移写入，再跑对账，最后删除旧执行路径。兼容只允许读取历史成品，不允许保留第二个生产 owner；不得用“新框架能启动”替代真实业务状态与断点恢复证明。

### 8.1 H0 脏工作树裁决

H0 以重构开始前的 28 个 tracked 修改为基线。下列裁决只决定代码意图，不等于允许把它们混成一个提交；每组必须在对应 Harness 纵切中独立迁移和验收。

| 裁决 | 当前改动 | 处理方式 |
|---|---|---|
| 保留 | 草稿箱汇总、待发布统一进入草稿箱、发布前人审与 fail-closed 门禁 | 作为 `Draft/Approval/EffectIntent` 领域合同保留；改由 Workflow projection 展示 |
| 保留 | renderer 可用性、真实成片、真实素材、旁白、版权状态的发布阻断 | 保留为领域 validator 和 QA Step，不由 UI 或模型自行判断 |
| 已迁移并删除旧执行 | 素材检索、候选物化、声音任务、Video IR、renderer plan、版本与 receipt | 生产执行迁入官方 `kanban-video-orchestrator` 七 profile；Marketing 只保留锁定合同、Reviewer 结算与历史读投影 |
| 迁移 | Gateway 的草稿、素材、视频、发布 RPC 与 Desktop 工作台 | RPC 改为 Workflow command/query；Desktop 改读后端 projection 和真实可播放 proxy |
| 已删除 | `cross_platform_campaign → prepare_from_campaign / prepare_from_script → local storyboard` 主路径 | Desktop/Gateway/Tool/Repository 实现与固化旧行为的测试均已删除；由 `TopicBrief → official video Kanban` 替代 |
| 已删除暴露 | `marketing_prepare_video_from_script` 默认 core/marketing tool | schema、registry 与 toolset 已移除；H3 由 Video Worker typed command 承担 |
| 重写测试 | 固化“接受图文 campaign 后才能启动视频”与 storyboard 占位物的测试 | 改为同一 TopicBrief fan-out、分支独立恢复、真实素材门禁和可播放 proxy 测试 |

任何保留项都不拥有新的架构豁免：如果仍由自由 prompt、进程内任务或 Electron 状态驱动，也必须迁入 Harness。

### 8.2 当前实施回执

2026-07-18 已完成第一批原生内核，不再只是设计稿：

- `agent/harness/` 已提供 Workflow、Step DAG、Attempt、Artifact、Approval、Receipt、Event 与 Lease Repository；schema 由 `SessionDB/state.db` 单 owner 声明。
- 领取使用 `BEGIN IMMEDIATE + version CAS`，租约 token 只返回执行者、库内只存 hash；支持 heartbeat、过期回收、强制进程恢复、重试预算、显式追加尝试和跨 Workflow `resource_scope` 写冲突门。
- 相同 Attempt/相同输出的结算幂等；Receipt 的相同 idempotency key 若输入不同会 fail closed。
- 旧 `marketing.operation` 已映射为一个兼容 Workflow/Step；Gateway 重启后不再直接标错，而是结束旧 Attempt、追加 reclaim Event 并把 Step 放回可重试队列。
- Gateway 已提供 workflow list/get/events/cancel/retry/approvals/respond RPC；取消、追加重试和审批决定均要求明确用户动作并校验 owner。Desktop task tray 已优先读取 Workflow，并在页面重载后从后端恢复活跃任务 projection，不再把 operation Session 当唯一任务事实。
- `marketing.topic_production.start` 从预演通过的 candidate 创建幂等 TopicBrief DAG。中央任务只生产实际 `recommended_platforms`，并为每个平台绑定真实目标账号或明确公域冷启动。图文按平台直接写最终交付并运行 ArticleDraft Preflight；视频分支只保留一个 `video.official_kanban` 提交 Step，不再在 Marketing Harness 中复制 Showrunner/素材/TTS/渲染/审片子图。
- 视频提交后由官方 Kanban Dispatcher 和七个 Hermes profile 提供 task/parent、lease、heartbeat、retry、共享 workspace 与结构化 handoff；Marketing Harness 不领取或结算这些视频子任务，也不镜像其 task graph。
- 素材解析顺序已固定为：账号素材库 → 零费用开放许可 Provider 搜索/下载（默认 Wikimedia Commons 官方 API；已有免费 Key 时可叠加 Pexels）→ 已安装 `media-use` 的项目/全局本地缓存。自动流程硬禁付费云生成，`media-use` 强制 `--local-only`，返回 generated 也拒绝采用；所有零费用来源仍未命中时 Step 明确失败并允许重试，不生成占位素材。每次命中都冻结成本地文件并写入 `MediaAssetRepository` 来源、许可证/生成状态与 resolver receipt；发布仍单独复核人物、物权、商标与使用场景。
- Desktop 工作台“制作选题”已直连 `marketing.topic_production.start`，任务托盘按 workflow Event 增量恢复进度、审批、停止和重试；结果统一进入草稿箱。图文审核页已删除“拿平台图文稿制作视频”的入口，视频不再等待或复制图文脚本。

当前证据：Topic/素材顺序与开放 Provider 专项 `13/13`；Harness/Marketing/Gateway 宽回归 `210/210`；Desktop 全量 `138` 文件、`1,022/1,022`，TypeScript、ESLint、Ruff、Python compile 与 `git diff --check` 通过。真实 Wikimedia 搜索命中 3 条开放许可视频，并下载/FFprobe 验证一条 `CC BY 3.0`、VP9+Opus、1920×1080、92.241 秒、7,592,791 字节的 WebM。HeyGen OAuth/API 网络超时不再是产品阻断，因为自动管线已排除该云 Provider；真实模型五平台产出和真人播放验收仍不能升级为 `human-loop`。

## 九、保留、迁移与删除

### 保留

- Hermes conversation loop、SessionDB、Memory、Skill、MCP、Browser owner、Cron 触发能力。
- Operating Entity、Evidence、Topic/Preflight、Content、Media、Rights、Publishing、Metric、Retro、Learning、Knowledge owner；Reviewer 通过后的 Video IR/Receipt 是交付事实，不是执行图。
- 官方 Kanban/Dispatcher/Profile；Remotion、HyperFrames、FFmpeg、`video-use`、素材 Provider 与 TTS 作为 profile 工具。
- Kanban 已验证的 CAS、Attempt、Lease、Heartbeat、stale reclaim 和熔断思想及可提炼代码。

### 已删除或必须删除

- `marketing.operation.start` 的自然语言 prompt 编排、对象前后快照猜结果和重启即失败合同。
- 以图文 campaign/script 为视频唯一上游的产品路径，以及 Marketing 内部第二套视频 DAG/Worker/Audio/IR/QA/Renderer 执行器。
- Electron localStorage 中的业务草稿、人物/道具/场景/声音选择和内存任务 owner。
- 只切本地 tab 的假阶段、无事件的假播放器、没有 revision owner 的 V1/V2、未接通按钮。
- 把 storyboard/derived 占位包装为素材或成品的兼容路径。
- Repository 私有 schema owner、进程级后台任务 owner、默认 core 中无最小授权的写型营销工具。

## 十、完成定义

Harness 重构不能以“多了几个 Agent”完成，必须同时证明：

1. App/Gateway/Worker 在任意 Step 被终止后可从最后成功边界恢复。
2. 一个 effect 重试一百次也只发布、扣费或删除一次。
3. 并行 Worker 不会串主体、串平台、覆盖同一 revision 或抢走别的任务结果。
4. 页面刷新、窗口关闭和跨天等待不丢 Task/Approval/Artifact。
5. 用户能看到目标、进度、证据、成本、等待原因、产物和回执，而不是 tool JSON。
6. 每个 Agent、prompt、toolset、模型和 contract 版本可追溯并可回放评测。
7. 图文和视频从同一个预演选题独立完成到草稿箱；发布仍经过明确的人审和 effect approval。
