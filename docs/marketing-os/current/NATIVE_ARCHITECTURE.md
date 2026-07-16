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

## Desktop / Gateway 合同审计（2026-07-17）

当前依赖方向是单向的：Desktop 通过 Gateway 读取或提交结构化意图，后端不导入 Desktop；账号、素材、内容、视频、发布和学习事实仍由 Hermes Repository 与 `state.db` 拥有。Renderer 当前消费 21 个 `marketing.*` RPC，Gateway 暴露 31 个；未被 Desktop 使用的 10 个入口可能供消息渠道、后续治理界面或兼容路径使用，未经调用方审计不得按“前端没用”删除。Gateway 注册器已改为重复方法名立即失败，避免后声明静默覆盖前 handler。

仍有一处明确的耦合债务：`desktop-controller.tsx` 与 `video-production-workbench.tsx` 三处重复编排 `marketing.operation.prepare → session.create → prompt.submit`，并由 `marketing-task-tray.tsx` / 视频工作台轮询通用 `session.status`，把 `idle` 推断为经营任务完成。这不会把业务事实写进 Electron，但把任务启动协议和完成语义泄漏给了 UI。短期 UI 任务卡只保留内存中的展示投影，不再写 `localStorage`；长期必须由 Hermes 提供原子的 `marketing.operation.start` 与 operation/run projection（或等价原生 task owner），Desktop 只提交稳定对象 ID、用户输入并展示后端状态。

第二处债务是手写合同与组件体积：Desktop 各页面自行声明 RPC payload，缺少共享的可校验 contract；`desktop-controller.tsx`、`growth-dashboard.tsx`、`video-production-workbench.tsx` 分别约 1.6k、1.2k、2.2k 行，数据加载、任务编排和视图混在同一文件。后续拆分必须按 native owner 的 query/command projection 切，不得借拆组件新建 Electron Store 或第二任务状态机。Electron 直接能力目前只用于用户文件/文件夹选择、拖入路径解析和远程附件读取，仍属于交互输入，不拥有素材导入、授权、复制或生产状态。

## 经营领域

当前原生源码落点（这是现状地图，不是禁止移动的目录清单）：

```text
agent/product.py
agent/marketing/
  domains/
    account_*.py                  # 账号上下文、生命周期、经营策略与组合
    content_*.py / article_drafts.py
    evidence.py / browser_payloads.py
    human_model.py / knowledge_*.py
    media_assets.py / material_sourcing.py / production_audio.py
    public_content_observations.py / short_video_signals.py
    video_ir.py / video_production.py / video_quality.py / video_renderers.py
    publishing.py / storage.py
  intelligence/
    content_*.py / influence_score.py / preflight_decision.py
    audience_reaction_simulation.py / social_system_simulation.py
    learning_governance.py / memory_classification.py / metric_labels.py / store.py
  providers/
    knowledge_sync.py / materials.py / metrics.py / publishing.py
  operation_entrypoints.py
  evidence_capture.py / metric_loop.py / learning.py
tools/marketing_tools.py
tui_gateway/server.py
mcp/marketing-browser/
apps/desktop/src/app/workbench/
```

这些目录是同一 Hermes 产品 fork 内的职责拆分，不是插件、sidecar 或第二个 Agent。能力必须放在真正 owner 附近：平台采集可进入 Provider/MCP，定时触发进入 Cron，记忆投影进入 Memory；不得为了“都放在 `agent/marketing`”而制造反向依赖或重复状态机。

## 唯一业务状态库与数据飞轮

Hermes `state.db` 是会话、账号、受众、内容、预演、回执、指标和学习候选的唯一产品数据库 owner。历史 `agent_core.db` 只允许一次性、可校验迁移，不再接收新写入；Electron 不决定业务数据库路径。

- 私有经营事实保留 user/account scope，驱动本地记忆、账号策略和技能学习。
- 匿名知识贡献必须显式授权、去标识化、结构化并经过最小群组阈值，才能进入未来中央知识库。
- 中央知识以带版本、平台、地区、时间窗、样本量和置信度的知识包返回 Agent，只提供先验；本地 Receipt 永远拥有更高事实权重。
- 本地贡献 outbox 的 owner 是 `agent/marketing/domains/knowledge_flywheel.py`；它只接收治理通过的 learning candidate 和显式 consent_ref，不拥有网络上传或中央聚合。

中央知识服务是唯一有充分证据新增的产品边界：多用户聚合不可能由任一用户本机 Hermes 正确拥有。它只接收 `marketing.knowledge-contribution.v1` 匿名 wire envelope，不接收本地 user/account/consent/source candidate。`services/marketing_knowledge` 独立执行最小群组、稀疏类别抑制和时间衰减，并用 Ed25519 签署 `marketing.knowledge-pack.v1`。Hermes 必须使用内置信任公钥独立验签后才能落库；Electron 不参与贡献、上传、聚合、验签或安装。

中央服务的持久 owner 是 `services/marketing_knowledge/storage.py`：它只存匿名 envelope、内容哈希、时间和最小删除 tombstone，不存本地账号身份。引用重试必须内容一致，删除后的引用永不允许复活；任何 corpus 变化都会使旧签名包失效，重聚合与落包共享一个 SQLite 写事务。

网络入口由同一服务边界的 `services/marketing_knowledge/api.py` 拥有。每个产品安装实例使用独立可轮换 token，服务端只存 token 哈希；请求必须带短时效时间戳和一次性 nonce，限流与 nonce 都持久化。贡献表不保存 client ID，而保存按 client 与 contribution 生成的不可关联删除 owner proof；删除 HMAC key-ring 支持轮换，旧 proof 在成功访问后迁移到当前 key。Provisioning 只能走离线运维，不提供公共注册接口。

Hermes 客户端 owner 是 `agent/marketing/providers/knowledge_sync.py`：它只读取 `KnowledgeFlywheelRepository` 的 pending consented outbox，上传成功后结算 submitted；下载结果必须经 Ed25519 信任 key-ring 验证，篡改或未知签名包不能进入本地知识库。`cron/product_tasks.py` 只决定何时调用 provider，不解析 envelope、签名或知识。服务地址、安装级 token 与公钥 ring 通过 `MARKETING_KNOWLEDGE_*` 部署作用域读取，即使 Gateway multiplex 多个用户 profile 也不会借用其中任何人的 credential。Desktop/Electron 永不持有中央同步逻辑或全局服务密钥。

Consent 撤回属于同一 Repository 状态机：未上传记录直接 withheld 并清空 aggregate payload；已上传或上传中的记录生成稳定 deletion_ref，进入 delete_pending，由 Provider 请求中央删除，成功或确认不存在后结算 deleted。上传先 claim 为 uploading，因此用户在 HTTP in-flight 时撤回也不会被随后 submitted 覆盖；崩溃遗留 claim 自动回到 pending。Gateway 只暴露带明确 `confirmed=true` 的本地撤回交互入口，不执行网络删除；Electron 只收集确认和显示审计状态。

```text
Hermes local facts
→ governed contribution outbox
→ anonymous wire envelope
→ central threshold/decay aggregation
→ signed knowledge pack
→ Hermes checksum/signature verification
→ global prior (below local Receipt)
```

### 短视频声音信号

`mcp/marketing-browser` 原生增加 `browser_extract_short_video_signals`，从真实账号浏览器页面提取作品指标和平台声音身份。工具结果经 Hermes post-tool seam 固化为 EvidenceRecord、Sound 和 ShortVideoObservation，Electron 不采集、不解析也不保存这些数据。

同一 MCP 原生提供 `browser_verify_account_login`：认证信号只在账号持久 BrowserContext 内解析，Cookie 值和登录 URL 查询参数不会离开浏览器 owner。Hermes 只接受注册名为 `mcp_marketing_browser_browser_verify_account_login` 的真实 post-tool 结果来激活 AccountRegistry、继承 prospect 并切换到后台 profile；Electron 仍只显示扫码、等待与成功状态。

`ShortVideoSignalRepository` 以平台声音 ID 去重，使用真实观察计算覆盖、重复出现、使用规模、新鲜度、目标内容匹配和版权安全。它向预演提供声音先验，向草稿提供受证据约束的 `sound_plan`；发布回执继续携带 `sound_id`，后续只能通过匹配样本或 A/B 变体提高因果归因。

## 三核数据合同

四类知识库与对标经营图谱的详细边界见 `KNOWLEDGE_ARCHITECTURE.md`：

- Platform KB 保存带地区、版本和有效期的平台“术”。
- Market KB 保存带品类、样本口径、地区和时间窗口的市场环境规律。
- Account KB 只接收 Receipt-backed、Retro 后已接受的账号经验。
- Content KB 保存可检验的人类注意力、信任和群体传播“道”。
- Benchmark Operating Graph 保存当前账号与外部样本的证据关系，不冒充公共知识。
- Hermes 用户记忆保存偏好与拒绝，不是知识真相；用户/模型不能直接写四类知识库。

内容计划会在 Preflight 前检索四库并只保存知识 entry ID 和覆盖度；知识原文不复制进不可变预演记录。权威顺序为本地账号回执知识、有效平台知识、赛道与市场知识、内容原理、签名聚合先验，模型推断只能成为候选。

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

## 公域自然实验链

`mcp/marketing-browser` 的 `browser_capture_public_content` 只负责从真实公开页面读取作品、创作者公开身份和当前聚合反馈。post-tool seam 将结果固化为 EvidenceRecord、PublicContentCase 和可重复的 FeedbackObservation；Electron 不采集、不解释也不保存公域数据。

`PublicContentObservationRepository` 负责同作品时间序列、指标增量、匿名反应解释和因果边界。解释结果进入 Receipt，并分别形成内容模型 memory candidate 与对标 strategy candidate。对标 strategy candidate 被用户接受后，新账号仍只成为 `candidate`；正式 `selected` 必须再次明确确认。

## 代码能力为营销生产服务

Hermes 的代码、终端和文件能力继续保留，但不与营销经营争夺主 Agent 的决策权。产品运行时采用三层硬边界：

1. 主 Marketing Agent 的默认工具面不展示 `terminal`、`read_file`、`write_file`、`patch`、`execute_code` 和 Project 工具；源码目录不能触发 Coding posture。
2. 主 Agent 即使通过旧轨迹或工具搜索请求上述工具，原生执行器仍会阻断。不得用代码、项目文件或生成脚本补造账号数据、证据、受众、定位和策略。
3. 只有已经存在 `production_plan_id` 或 `content_asset_id` 时，主 Agent 才能用原生 `delegate_task` 创建 `marketing_code` 叶子任务。该 worker 只负责代码生成素材、内容渲染或结构化内容数据转换，不能决定营销事实、策略和发布。

```text
Marketing goal / evidence / plan
              │
              ├─ normal marketing work ─→ native marketing tools
              │
              └─ code artifact required
                    │ durable plan/asset binding
                    ▼
             marketing_code leaf worker
                    │ implementation only
                    ▼
             ContentAsset / verifiable output
                    │
                    ▼
          main Marketing Agent review + next gate
```

`marketing_code` 不是第二套 Agent，也不是外围代码服务；它是 Hermes 原生 delegation 和 tool registry 内的受限姿态。MCP、Skill、浏览器、搜索和记忆仍按各自原生 owner 工作，Electron 不参与工具授权。

定时触发与业务执行严格分离：`cron/product_tasks.py` 仅在已注册真实 MetricProvider 时非阻塞唤醒 `metric_loop.py`；Provider 只观察平台，Publishing 只结算 checkpoint，OperatingLoop 只保存 Receipt/Candidate。缺失指标不补 0，未校准预测不制造偏差，pending candidate 不自动进入账号知识。

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

- Marketing OS 只拥有图文和不露脸素材视频两条内容生产 lane；二者共享账号、证据、素材、音频、版权、回执和复盘合同。
- Hermes 原生感知层由 `vision_analyze`、`browser_vision` 和 `video_analyze` 组成，是 Marketing Agent 在研究、采集、创作、预演、审片与普通对话中共享的底层能力，不属于某个视频工作台。产品 `marketing` 与受约束的 `marketing_code` toolset 都直接携带图片/视频理解；渐进工具披露不得隐藏这些能力，通用 Hermes 的 `video` toolset 仍保持 opt-in。小视频可直接交给视频模型，长视频或指定时间段由本机 ffprobe/FFmpeg 生成带时间戳联系表后分析；采样模式必须区分可见事实与推断，不得声称听到未转写音频或覆盖未采样连续性。读取视频二进制文件时也必须引导到 `video_analyze`，禁止按文本猜测内容。
- 不露脸视频的业务真相由 Hermes 原生 `VideoProductionRepository` 拥有：账号隔离、不可变 EDL、渲染任务、人工批准、输入输出素材引用、最终 ContentAsset 版本与 Receipt 均进入原生状态链。Electron 只展示素材、时间线、渲染状态和审片意见。
- 产品拥有 `ffmpeg_timeline_v1`、`remotion_scene_v1` 和 `hyperframes_scene_v1` 三个可恢复执行器。renderer-neutral `marketing.video.ir.v1`、稳定 scene/IR hash 和 `marketing.video.render_plan.v1` 位于 Hermes 原生领域层；旧 EDL 自动升级并保持原幂等键。Hermes 按镜头路由，FFmpeg 统一规格化、拼接、字幕、混音和交付；不是整条视频二选一，也不把 JSX/HTML 当作业务真相。
- capability matrix 只开放运行时健康证据完整的 renderer。Remotion `4.0.488`、HyperFrames `0.7.57`、GSAP `3.14.2` 和 React `19.2.4` 固定进入独立离线依赖闭包，复用产品 Playwright Chromium；Node/浏览器/版本/入口任一缺失都在批准前 fail closed，不运行浮动 `npx`，不静默下载 Chromium。
- 场景缓存绑定 scene hash、canvas、renderer 和模板源码指纹；高级 renderer 输出先转为统一 H.264 mezzanine 再合片。Render Receipt 记录每幕实际 renderer、缓存命中、输出 hash 以及整片 IR/plan hash。借鉴 Video Studio 的仅是镜头局部 hash、能力证据门、effect 前持久化审批和整片审查/最小返工思想，不导入其黑板、角色、连续性、Provider session、预算或项目 owner。
- Electron 只把已打包的 renderer root、Electron-as-Node 路径和 Chromium 路径注入 Hermes，并展示状态；renderer 选择、素材沙箱、缓存、执行、回执和失败恢复都不在 Electron。
- Video Use、Generative Media、Cheat on Content 和 DBSkill 只提供剪辑、质检、盲测与复盘方法，不拥有任务和状态；OpenMontage 仅作 AGPL 研究样本，DBSkill 仅作 CC BY-NC 个人研究样本，代码不得进入商业产品运行时。
- Seedance 2 只补齐缺失镜头，不拥有时间线；生成镜头与火山 TTS 等付费效果必须经过单独明确批准，保留 Provider、成本、来源、版权和回执。UI-TARS 不属于视频渲染核心链路，只能在没有稳定 API 的界面操作中作为受控兜底候选。
- 真人、数字人和 AI 电影级生产由独立 `/Users/yangyucheng/projects/video-studio` 产品拥有，Marketing OS 不保存其项目画布、角色调度、Provider、预算、审批或预演状态。
- 当前没有 Marketing OS → Video Studio 运行时接入；在独立产品提供稳定 Port/API 前，不保留假入口、host adapter 或内部 `premium_human_video` 计划。
- 通用 TTS、平台 BGM 情报和素材版权仍服务不露脸视频，不能因为高阶视频迁出而删除。素材检索由 Hermes 原生 `MaterialSourcingRepository` 统一用户素材和已配置 Provider 候选；首个 Pexels 适配器只负责官方 API 访问，来源、许可证、下载哈希和选择状态归 `state.db`。旁白由 `ProductionAudioRepository` 固化脚本哈希并在一次性确认后复用 Hermes TTS，真实输出作为 MediaAsset 进入同一 Video IR/Render Receipt；Electron 不保存 Provider 密钥、下载地址或生成状态。
- 五层剪辑 Agent、统一 IR、渲染路由和构建顺序见 [`VIDEO_EDITING_AGENT.md`](VIDEO_EDITING_AGENT.md)。

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
