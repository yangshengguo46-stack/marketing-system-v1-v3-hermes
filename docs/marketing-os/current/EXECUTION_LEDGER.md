# Marketing OS 当前执行台账

> 日期：2026-07-19
> 分支：`codex/marketing-os-product-source`
> 本文件是唯一任务入口。研究资料、ADR 和 Git 历史不得直接发任务。

## 不得遗忘的执行禁令

1. **默认先改原生 owner；禁止因为怕碰上游，就在外围再加适配层。只有上游确实无法承担、且证据充分时，才允许新增边界。**
2. **Electron 只负责显示和交互，不参与其它任何东西。** Electron 不拥有账号、Cookie、profile、浏览器、任务、记忆、业务状态、自动化或执行。
3. **“在 Hermes 里面”不等于固定目录。** 目录服从真正 owner：Cron 触发、Provider/MCP 采集、领域层结算事实、Memory/Knowledge 治理学习；如果目录冲突就移动或重写。

每个纵切、任务和完成口径都必须同时满足这两条；否则任务不得开始。它们优先于局部实现计划、上游同步便利和已经写完的代码。

## 证据等级

`designed → code → automated → dev-runtime → packaged → human-loop`

只有达到 `human-loop` 才能宣称用户闭环完成；单测、页面、mock、占位 provider 和本地成功 toast 都不是产品完成。

## 当前代码事实

| 领域 | 当前状态 | 证据 | 主要缺口 |
|---|---|---|---|
| Hermes 产品本体 | 完整源码已成为主仓库根 | code + automated | 上游吸收 CI、正式签名发布 |
| State/data owner | 经营项目、受众、证据、内容、预演、回执和学习表已进入 Hermes `state.db`；旧 `agent_core.db` 一次迁移后只读保留 | dev-runtime | 删除旧兼容读取路径；中央服务仍待部署运维 |
| Short-video sound intelligence | Playwright MCP 原生短视频/BGM 结构化采集；Sound/Observation/Evidence 入 `state.db`；预演、草稿快照和发布回执携带声音身份 | automated | 真人 selector 验收冻结到账号登录 UI 完成后；再做跨日速度与匹配样本归因 |
| Public content natural experiments | Playwright MCP 采集公域作品与聚合反馈；Hermes 保存同作品延迟快照，用内容/受众/需求投影/认知投影/存在策略/社会反应模型解释并生成内容与对标学习候选 | automated | 真实抖音/公众号/小红书 selector 验收、跨日调度与大规模重复证据校准 |
| Central knowledge core | 匿名贡献 wire contract、安全服务与隐私聚合签名；Hermes 原生 Provider 上传 consented outbox、验签安装先验；撤回授权按 pending 本地扣留、submitted 中央删除，处理上传竞态和崩溃恢复 | automated | TLS/反向代理、凭据签发运维、签名私钥轮换演练与真实多用户规模 |
| New-media operating model | 创作者资产、赛道路线、行为受众、七角色对标图谱、定位、内容系统和可证伪实验进入 Hermes 原生领域 owner；用户只确认自己的身份、偏好、经营方向和外部动作；Gateway 每次模型调用前从原生 owner 重建实时个人 IP 上下文 | automated | 真实赛道研究、对标采集、自然对话真人验收 |
| Human Observation Core | 已从 Marketing OS 拆成 source-agnostic AGI 研究基础设施；原始观察、时间图谱、版本理论、竞争解释、假设、封存预测、结果和模型修订各有独立 owner；“人不可被还原成标签”是伦理/产品公理，具体存在策略是 `fixed_axiom=false` 的可修订研究 seed；Marketing Receipt 与用户已确认的个人 IP 自述/经营选择通过两个单向连接器进入伪名化观察，后者不自动心理解释 | automated | 合法多源长期样本、代表性/偏差审计、跨语境校准、研究者评审与安全评估 |
| Agent perception layer | `vision_analyze`、`browser_vision`、`video_analyze` 作为 Marketing Agent 的原生底层感知能力；主业务 toolset、受约束媒体代码 worker、默认委派和文件读取引导均已贯通，视频能力在产品运行时不可被渐进披露隐藏 | automated | 真人长视频、多格式/损坏文件、音频转写联动与跨模型视觉一致性验收 |
| Four knowledge bases | Platform/Market/Account/Content 四库进入 Hermes `state.db`；Cron 静默执行时效淘汰、显式冲突隔离、重复公域样本聚合、Receipt-backed 账号学习和历史回放校准；候选读取/决策 RPC 已从产品面删除，知识写入必须持有系统能力 | automated | 更大规模真实采集、官方平台规则原生刷新源、中央服务真实部署 |
| Desktop | `apps/desktop` 唯一 UI/Electron；首轮经营、图文和视频动作提交结构化意图后由 Gateway 原子启动 Agent，结果回到原经营对象，不再跳新对话或要求二次发送；一级草稿箱只投影 Hermes 半成品并回到原图文/视频管线 | automated | 开发机真人首半小时、Gateway 重启后的 operation 恢复、草稿箱真人视觉验收、干净机安装 |
| Session/account scope | SessionDB 新增稳定经营主体 scope；一个 creator/brand 可关联多个平台账号，Agent 读取账号上下文、内容资产和证据时按主体聚合，登录/浏览器/发布仍固定 action account；新会话自动获得稳定 `prospect_*` 作用域；MCP 真实登录验证后原子迁移经营事实 | automated | 真人二维码/验证码校准、多经营主体显式建组/拆组 UI、历史账号误分组审查、successor UI 切换与打包浏览器策略 |
| Account lifecycle | Hermes AccountRegistry 已拥有注册、真实登录验证、认证状态、断开、删除、会话绑定和 BrowserContext 租约；MCP owner 自动释放登录窗口，后续以同一持久 profile 后台恢复；删除时清理 profile | automated | 真人多平台登录/退出、Cookie 信号随平台变更的巡检 |
| Owned account diagnosis | 微信公众号已验证最近 9 篇逐篇内容分析指标；抖音已验证公开 3 条、私密 1 条的作品口径；Hermes 将作品、指标、EvidenceRecord、透明执行基线和数据缺口按账号写入 `state.db`；Desktop 只读展示 | dev-runtime | 新空 profile 真人扫码、多账号恢复、分页完整性巡检；评分继续区分执行基线、内容解释和受众反馈 |
| EvidencePack | `web_extract` 后自动固化 | automated | 多源交叉核验、来源语义、时效治理 |
| Content plan/assets | 图文、不露脸素材视频与 `cross_platform_campaign` 三 lane policy；同一内容内核按任意国内/海外平台集合生成不同受众、开头、结构、互动、CTA、视觉与格式合同；未知平台保留明确调研缺口；不可变版本、人审与草稿归档继续复用原 owner | automated | 真实模型五平台成品质量、人审与发布；平台画像时效来源；草稿归档/恢复真人验收 |
| Preflight | InfluenceOS + 不可变记录 + draft gate；每个平台保存独立适配评估；经营优先级/选题推荐必须先产生 plan + preflight，返回 `recommended` 或 `research_only`，阻断候选不得伪装成推荐 | automated | 真实账号历史校准、自动推送任务真人验收、评论聚类 Provider、平台竞争/时段/投流先验 |
| Receipt/Learning store | ReceiptRef、LearningCandidate、PublishAction、MetricCheckpoint 状态机；观察后自动执行投影机制链对账和分层 causal reflection；系统门禁静默晋级/等待/淘汰，用户与对话不能操作候选 | automated | 更多平台一方指标采集器、真实跨天规模数据 |
| Hermes memory/Skill | 1 个产品运行 Skill、23 个原始营销 playbook 和 13 个内容/编剧/视频参考 Skill 已纳入源码；用户自述/偏好进入 USER/MEMORY，系统学习候选按证据与回放门禁静默投影 | automated | 重复成功流程沉淀；参考 Skill 升级必须逐项审查 |
| Publishing/metrics | 原生发布 intent、一次性审批、Provider 插槽、unknown 恢复、回执校验、5 段 checkpoint；Hermes Cron 原生触发指标 owner；抖音/公众号已接账号隔离浏览器一方作品采集，支持领取、延期、7d 淘汰、崩溃恢复和 unavailable 回执 | automated | 其余平台真实发布/指标 Provider 和真人跨天验收 |
| Packaging | 自包含 Hermes/Python/Chromium staging 可构建；固定版本 Remotion/HyperFrames 已进入产品 runtime，并在 staged Electron Node + Chromium 中真实出片 | packaged | 正式安装包签名、公证、干净机断网首启与升级回滚 |
| High-end video | 已完整迁入独立 `/Users/yangyucheng/projects/video-studio`；Marketing OS 仅保留边界指针，不保留引擎、运行时、角色、Provider 或内部生产 lane | external product | 不计 Marketing OS 桌面完成度；未来接入必须等待独立产品稳定 Port/API |

## 内容生产当前边界

Marketing OS 内容生产保留三种内部交付形态，共享同一条 Hermes 原生经营闭环：

| 交付形态 | 当前原生能力 | 主要缺口 | 当前证据 |
|---|---|---|---|
| `article_soft` 软文 | 账号/实验绑定、EvidencePack、父稿与平台变体、质量门、版本资产、Preflight 和发布资格约束 | 真实账号调性、主张级多源核验、配图版权与真人审稿 | automated |
| `faceless_video` 不露脸素材视频 | 账号/实验绑定、内容计划、素材需求、声音计划、特征快照、Preflight、不可变 Video IR/EDL、scene/IR/render-plan hash、能力路由、显式渲染批准、固定版本 Remotion/HyperFrames 镜头执行、真实 FFmpeg 规格化与合成、场景缓存、派生最终素材、不可变成品版本、失败重试与 Render Receipt；黑场/冻结/响度/技术规格自动 QA；TopicBrief 直接 fan-out 到独立 Video Director，不再依赖或复制图文脚本；素材按用户库 → Wikimedia Commons/Pexels 等零费用开放来源 → 本地缓存检索，拒绝付费生成；Desktop 已真实加载并播放成片 | 首条端到端证明片只复用了一条开放素材，部分 Remotion 大字存在裁切；后续运行已加素材相关性与多查询/多来源策略，但仍需真实模型多平台人审、发布和跨天数据回收 | dev-runtime（成片与播放已验；未达 publish-grade/human-loop） |
| `cross_platform_campaign` 全平台 campaign | 一个内容内核绑定任意目标平台集合；内置抖音、公众号、视频号、知乎、小红书、B站、快手、TikTok、YouTube、Instagram、LinkedIn、X 的版本化内容画像，非内置安全平台 ID 以 `generic_unverified_requires_platform_research` 降级；每个平台变体必须内容实质不同并说明受众、开头、结构和 CTA 适配依据 | 真实模型成品、平台画像的证据/有效期治理、账号级效果校准、各平台发布 Provider | automated |

三种内部形态共同消费经营主体上下文、当前定位和内容系统、EvidencePack、ContentProductionPolicy、Preflight、ContentAsset、发布 Receipt、指标 checkpoint、Retro 与系统门禁治理的学习候选。完整草稿和生产状态进入 Hermes `state.db` 的领域 owner；Electron 只展示状态、收集输入和承接用户自身选择与外部动作授权，不拥有生产、素材、浏览器、发布或学习事实。

当前不能宣称“内容制作已完成”。不露脸视频自动化链已证明用户/Provider 素材候选、许可证确认、TTS 意图批准、真实音频导入、BGM 混音、渲染、QA、版本与回执可以贯通；但没有擅自调用当前可能计费的 `volcengine-speech`，也没有在未配置 Pexels Key 时伪造在线下载。仍缺真实账号输入、在线 Provider、真人认可成品、发布回执和跨天指标学习的 `human-loop` 证据。高级视频是独立产品，不属于本台账完成范围；迁移指针见 [`../deferred/high-end-video-volcengine.md`](../deferred/high-end-video-volcengine.md)。

## 参考 Skill 迁移结论

- 用户提供的 `marketing-skills` `0.1.2` 原始快照共 23 个模块，已完整保存在 `skills/marketing-playbooks/`，不再依赖 WorkBuddy 本机目录。
- 此前只存在于已安装运行时、没有进入仓库的 13 个模块已补入源码：内容创作 4 个、编剧 5 个、视频制作 4 个。
- Skill 不等于 Tool。方法论、清单和创作框架保留为 Skill；账号事实、浏览器、采集、草稿、发布、指标、回执和学习继续由 Hermes 原生工具及领域 owner 承担。
- 逐项状态、功能重叠和产品边界见 [`../reference/skills/reference-skill-inventory.md`](../reference/skills/reference-skill-inventory.md)。

## 当前唯一主线

### EPISTEMIC-01 分级认识论与个人 IP Agent 合同（automated，2026-07-19）

- **产品身份。** Marketing OS 的前台第一身份固定为长期运行的个人 IP 经营 Agent：先理解用户的身份、偏好、目标、边界和经营方向，再完成研究、选题、制作、发布授权、回执和复盘。Human Observer 是后台研究底座，不得取代产品任务，也不以诊断面板暴露给用户。
- **六级认识论合同。** 新增 `USER_SELF_REPORT`、`STRATEGIC_CHOICE`、`EXTERNAL_ACTION`、`OBSERVED_FACT`、`DERIVED_KNOWLEDGE`、`HUMAN_RESEARCH` 六类权威矩阵。前三类分别由用户修订、确认或授权；后三类由来源、Receipt、冲突/时效/回放门禁和系统研究流程治理，用户陈述只能成为新证词或反证，不能成为事实真值投票。
- **代码级能力边界。** Knowledge/Account Strategy/Learning Candidate/Human Observer 写路径必须持有进程内 `SystemAuthority`；Human Observer writer 已私有化，公共包只暴露 reader 与维护 runner。普通对话、Gateway 和 Electron 不持有该能力。该能力是当前单进程产品的 API 边界；未来若允许不可信插件或多租户代码同进程执行，仍必须升级为独立进程/OS 级隔离。
- **产品面收口。** 删除 `marketing.learning.candidates.list`、`marketing.learning.candidate.decide` 和 `learning.review` 入口；工作台不再展示学习候选数量，也不要求用户治理模型。用户仍能修改自己的偏好、身份与 IP 方向，并必须授权发布、付费、账号变更等外部动作。
- **静默闭环。** 指标/公域观察先产生候选；后台维护按不可变证据、时效、冲突和历史回放决定等待、淘汰或投影到 Account KB、权重、策略和系统 Skill。Skill 投影也走系统能力，不复用用户写入批准。
- **“存在”分层。** “人是主体、不能被模型完全还原”为不可让渡的伦理/产品公理；“保存、确认、扩展、延续”等存在策略只是可证伪、可替换的研究 seed。项目不再把二者写成同一层真理。
- **权利不等于真值投票。** 同意、撤回、删除、导出与保留期属于数据主体权利，始终保留；它们不等于接受或拒绝系统知识结论。完整合同见 [`PRODUCT_CONSTITUTION.md`](./PRODUCT_CONSTITUTION.md)、[`PRODUCT_PHILOSOPHY.md`](./PRODUCT_PHILOSOPHY.md) 与 [`ARCHITECTURE_DOCTRINE.md`](./ARCHITECTURE_DOCTRINE.md)。
- **自动化证据。** Marketing/Human Observer/产品合同相关全量 `230 passed, 1 skipped`；Desktop 定向 `10/10`，TypeScript、ESLint、Ruff、Python compile 与 `git diff --check` 通过。定向测试同时证明伪造 system capability 失败、repository 无 capability 不能裁决、Gateway 两个旧方法不存在、Human Observer 公共包无 writer、Skill 重放幂等。

### EPISTEMIC-02 实时个人 IP Agent 与用户观察纵切（automated，2026-07-19）

- **每轮而非开场快照。** `agent/marketing/session_scope.py` 新增有界、抗提示注入的实时个人 IP 投影；`tui_gateway/server.py` 在每次 `run_conversation` 前重新读取当前经营实体、创作者画像、路线、受众、定位、内容系统、平台快照和数据缺口。人格或系统提示切换只更新 base overlay，下一轮仍会重新合成稳定路由与实时经营模型。
- **字段级认识论。** 用户确认画像中的 `human_projection_model`、受众需求/认知/存在策略投影不会跟随画像外壳进入 `user_owned`，而是单独进入 `system_derived.human_projection_hypotheses`；混合来源的 `account_dna` 也不再冒充客观观察。真实受众和平台指标保留在 `observed` 并携带可用的观测时间。
- **用户也是观察主体。** `MarketingPersonalIPConnector` 静默摄取已经确认的创作者自述、赛道/受众/定位/内容系统选择和实验授权，建立稳定伪名 subject；直接身份、user/account/entity/project ID、URL/邮箱/手机号以及已有心理投影在跨入研究 owner 前删除。事件明确标记 `not_objective_fact` 与 `not_psychological_interpretation`，只证明“主体曾这样陈述或选择”。
- **结果可纵向对账。** Marketing Receipt 连接器现在同时绑定同一用户的伪名 subject 和账号/平台匿名 cohort；选择与后续真实结果可以在 Human Observer 内按主体纵向研究，但两个连接器都只有系统 capability、保持幂等且没有 Gateway/Tool/Desktop 写入口。
- **代码路径。** `agent/marketing/session_scope.py`、`tui_gateway/server.py`、`agent/human_observer/marketing_connector.py`、`agent/human_observer/runner.py`；架构合同同步更新 `PRODUCT_CONSTITUTION.md`、`PRODUCT_PHILOSOPHY.md`、`ARCHITECTURE_DOCTRINE.md`、`NATIVE_ARCHITECTURE.md` 和 `docs/human-observer/ARCHITECTURE.md`。
- **自动化证据。** 不重复计数的当前回归共 `544 passed, 1 skipped`：全 Marketing/Human Observer/实时 AccountContext/认识论/Cron/产品身份/经营循环 `243 passed, 1 skipped`，完整 Gateway `301 passed`。Python compile、Ruff 与 `git diff --check` 进入提交前总门。当前证据为 automated；尚未宣称 Human Core 已学会人类模型，仍需要合法长期样本、跨语境反证、偏差审计和安全评估。

### HARNESS-00 全项目 Durable Multi-Agent Harness 重构（H1～H4 首条端到端 dev-runtime 已验，2026-07-18）

- **本轮裁决。** 当前主线从 `PUBLISH-01` 和 `MATERIAL-VIDEO-AUDIT-01` 上收为 Harness 重构；此前纵切不删除，但冻结新增功能，只允许作为迁移样本或修复阻断性回归。目标基线见 [`HARNESS_ARCHITECTURE.md`](./HARNESS_ARCHITECTURE.md)。
- **真实根因。** Marketing 产品按钮当前走 `marketing.operation.start → hidden desktop-product Session → prompt.submit → free Agent turn`；operation 只有四态，靠运行前后对象 ID 差猜结果，Gateway 重启后未完成 turn 直接 error。Hermes 虽已有 delegate 并发和 Kanban `task/run/event + CAS/lease/heartbeat/reclaim`，Marketing 产品没有接入。问题不是 Agent 数量少，而是自由 Agent 承担了业务状态机。
- **视频边界冻结。** 当前未提交的 campaign/script 直达视频代码只作为失败实验保留在脏工作树，不进入新主链。正确目标是预演 TopicBrief 同时 fan-out 图文和视频兄弟分支；Video Director 独立策划平台视频、脚本/旁白、shot plan、素材、声音、渲染与 QA，Remotion/HyperFrames/FFmpeg 只作为执行 hands。
- **HARNESS 启动时 Git 基线。** 当时分支为 `codex/marketing-os-product-source`、HEAD `9d9c3c095`，无 upstream tracking，唯一 remote 为 `hermes-upstream`；工作树已有 28 个 tracked 文件未提交、`+2716/-106`，没有 untracked。该段只记录 H0 启动时证据，不代表当前 Git 状态。
- **历史删除核对。** Git 不存在“昨天单次删除一万多行”。可对应总量是三次收敛：`7386e9147` 删除旧文档/台账 `6110` 行，`d098c4ad1` 删除 extracted video engine `3401` 行，`f0aa95d62` 删除内部高阶视频 lane `610` 行，合计 `10121` 行；7 月 17 日两个提交本身只删除 `1752` 行。删除的是旧文档/任务入口、第二套 video engine/adapter/store/poller/renderer/多角色 Skill，以及高阶视频内部 lane，不是 Hermes Agent、Remotion/HyperFrames/FFmpeg 或原生素材视频底座。
- **台账纠错。** `FACELESS-01 已收口、下一步 PUBLISH` 与本文件后部 `MATERIAL-VIDEO-AUDIT-01 P0-1～7` 冲突，前者从本节起不再是当前完成判断；“33 表 entity ownership 完成”只代表列、回填和 trigger 防错完成，不能冒充所有 Repository 已 entity-first。素材、production、草稿和部分 Desktop 查询仍需在 `H5` 迁移。
- **实施顺序。** `H0` 冻结与基线已完成意图级 keep/migrate/drop 裁决，逐组代码迁移尚未提交；接下来是 `H1` Harness schema/event/lease 与单 Step 兼容 → `H2` 后端任务 projection/订阅/恢复并删除 Electron 内存任务 owner → `H3` Daily Topic DAG 和图文/视频兄弟分支 → `H4` 视频 Project/Revision/可信素材/播放器/声音/renderer/QA → `H5` entity-first 和 schema 单 owner → `H6` Cron enqueue + Provider/effect Activity/outbox → `H7` 最小 toolset、trace/eval/replay 和旧 prompt 编排删除。H0 逐组裁决见 [`HARNESS_ARCHITECTURE.md`](./HARNESS_ARCHITECTURE.md#81-h0-脏工作树裁决)。
- **H1 原生内核完成。** 新增 `agent/harness/`，在 Hermes `state.db` 中由 `SessionDB` 统一声明 Workflow、Step DAG、Attempt、Artifact、Approval、Receipt、Event 和 Lease。已经验证原子领取、token hash、heartbeat、过期/进程重启回收、重试预算、跨 Workflow resource scope 排他、DAG 依赖门、持久审批、取消与相同输入幂等 Receipt。旧 `marketing.operation` 已进入单 Step 兼容层，Gateway 重启不再把未完成任务判死。
- **H2 已完成。** Gateway 已接通 `workflow.list/get/events/cancel/retry/approvals/respond`，所有读取校验 Marketing namespace 与 user owner，取消、追加重试、审批均为显式动作；Desktop task tray 已优先按 `workflow_id` 读取后端，在 reload 后恢复活跃 projection，并用 append-only Event cursor 增量刷新而非反复猜 Session 状态。等待审批会展示请求并提供同意/拒绝，失败 Step 可明确追加一次重试，运行中任务可停止且保留已完成 Artifact。
- **H3 typed Worker 已接通。** `marketing.topic_production.start` 从预演 candidate 创建幂等 TopicBrief DAG；工作台“制作选题”已直接调用该入口。图文 Director 与视频 Director 只共同依赖冻结的 TopicBrief，不互相读取稿件；未知海外平台先研究，图文按平台适配后 QA 入草稿箱，视频按平台分别完成 plan/previs/render/QA 后入草稿箱。Gateway 注册全部 Step handler，以三路并发、heartbeat、lease/retry 和 Receipt 结算真实领域 owner。
- **素材 Skill 与费用纠偏。** 素材不是“缺了就生成”，自动管线也不得产生云费用。执行顺序固定为账号素材库 → 零费用开放许可 Provider 搜索/下载（默认 Wikimedia Commons 官方 API；有免费 Key 时叠加 Pexels）→ `media-use` 的项目/全局本地缓存。`media-use` 强制 `--local-only`，不调用 HeyGen、Codex 图像生成或其它云 Provider，并拒绝采用 generated 结果；全部未命中就明确失败并允许重试，不制造占位图。命中结果冻结入 `MediaAssetRepository`，保存 provider、来源、许可证、hash 和 resolver receipt；发布仍复核人物、物权、商标与具体使用场景。
- **旧从属入口已退出产品面。** `marketing_prepare_video_from_script` 已从 schema、registry、默认 core/marketing toolset 删除；Desktop 图文审核页不再出现“制作视频”，Gateway 不再注册 `marketing.video.setup.from_script/from_asset`。手动视频设定 prompt 也改为独立 Video Director 和素材能力顺序。内部 `prepare_from_campaign/prepare_from_script` 兼容实现仍待死代码清理，但已无产品调用入口。
- **H4 首条真实端到端回执。** DeepSeek 余额恢复后，今日候选 `Kimi K3冲击美股——中国AI大模型进入「军备竞赛」下半场` 以 Workflow `workflow_97ccbc92ba164e0398914eb6da9f0d9a` 完成 TopicBrief → 图文 Director 与视频 Director 并行兄弟分支。最终得到图文草稿 `asset_d7c4dc49a75048aebca13abb0e42b5b5`、抖音视频草稿 `asset_f7abca8a15a849d5b1ed5c3c3a445592`、知乎视频草稿 `asset_86068cad54ec461d97ed590d0800a2bf`，全部进入草稿箱，没有执行发布。
- **视频运行证据。** 抖音 production `video_production_bba320ba834c45bfbc9be82d737a7a67` 生成 media `media_f1847c76aa9a43049ec57a6fd0fe360b`（H.264/AAC、1080×1920、30fps、60 秒、11,385,862 字节）；知乎 production `video_production_9935313c208a47ffb7e813e8205d6c8d` 生成 media `media_c7feb3ec9671437dba940c7ab02d4a85`（H.264/AAC、1920×1080、30fps、60 秒、9,658,176 字节）。两条均完整 FFmpeg 解码零错误，技术规格/黑场/冻结 QA 通过；Desktop `hermes-media://stream` 播放元素 `readyState=4`、`duration=60`、`error=null`，实际 `play()` 后播放时间从 0 前进到 2.112417 秒，证明不是静态预览或不可播占位。
- **渲染与素材事实。** 运行时同时启用 `ffmpeg_timeline_v1`、`hyperframes_scene_v1`、`remotion_scene_v1`；本次 20 个镜头由能力路由判定为 Remotion，重试时全部命中 scene cache，不能据此误判 HyperFrames 未接。Wikimedia Commons 实际检索、下载并固化 `CC BY-SA 4.0` 素材，全程未调用付费素材生成，也未安装/下载本地模型。开发机 FFmpeg 缺少 libass `subtitles` filter 时，管线自动改用 Pillow 生成透明字幕图层再由 FFmpeg overlay 烧录，真实竖/横屏成片均成功。
- **Durable 恢复修复。** 任务托盘原先把 cancelled Workflow 当成单 Step retry，无法恢复被取消的下游；现新增原生 `restart_cancelled_workflow`，保留已成功 Artifact/Attempt/审计并从未完成 DAG frontier 续跑，Gateway 暴露 `marketing.workflow.restart`。同时修复并行兄弟 Step 成功后错误覆盖 Workflow failed 状态的问题，后到的成功结果不再掩盖失败分支。
- **质量结论与下一门禁。** 本次已达到可恢复、可成片、可播放、可进草稿箱的 `dev-runtime`，但不是可发布成品：首轮素材检索只选中一条证券市场素材并跨镜头复用，部分 Remotion 标题字号过大产生裁切。相关性过滤、紧凑多查询和限制复用策略已写入后续运行路径；仍须再跑多素材样本并完成人工审片，之后才允许进入发布确认。真实模型五平台人审、平台画像时效/来源、真实发布和跨天指标回收继续保留为未完成项。
- **H4 有声/素材/窄窗修复回执（2026-07-18）。** Topic Workflow 现在从用户配置读取 `marketing.video.auto_voiceover=true`，只授权视频旁白这一项计费效果，素材的付费生成仍保持禁用；`volcengine-speech` 已启用并把既有 Speech X-Api-Key 安全迁入 Desktop 实际使用的独立 `HERMES_HOME`，没有把密钥写入仓库或投影。抖音有声修订 `video_production_6a55c2a66ec6493e8efef40a58a7bcac` 与知乎有声修订 `video_production_ebb1f3f59fd643f7abf6f8f41c0c82c4` 共用幂等 audio job `audio_job_8577786fb4e04d25872d934a75118599`，最终 AAC 单声道 48kHz 音轨均为 60 秒，`mean_volume=-22.1dB`、`max_volume=-7.7dB`。Electron 实际 `<video>` 为 `readyState=4`、`duration=60`、`muted=false`、`volume=1`，播放时间从 0 前进到 1.711 秒后人工暂停。
- **素材多样性门。** Video Director 的每个镜头新增 `media_type=image|video|either` 合同；Wikimedia Commons Provider 已从仅视频扩为无密钥图片/视频双路检索，Pexels 在图片请求中明确跳过。选择器不再在找到 1～2 条素材后停止：每镜头保留独立候选池、按稳定 provider asset 去重、下载失败继续尝试下一授权候选，整条片至少需要 `ceil(shot_count/2)` 个独立素材，单素材最多使用两次；不足时以 `material diversity gate` 明确阻断。真实 Commons 探针 `artificial intelligence data center` 返回 6/6 带许可证候选，同时包含 video 与 image；但尚未用新门禁重新跑一条完整十镜头 Workflow，因此首条证明片仍不能冒充多素材验收。
- **火山声音库。** Gateway 新增 secret-free `marketing.audio.catalog` 与显式 `marketing.audio.voice.set`，Desktop 声音页显示当前 Provider/模型/在线状态、7 个 Seed TTS 2.0 常用中英文音色和语音合成 1.0/2.0、声音复刻 1.0/2.0、声音设计能力族。火山公开目录为 325 个大模型音色，但完整 `ListSpeakers` 枚举使用 OpenAPI AK/SK，当前合成用 X-Api-Key 不能代替管理凭据；UI 因此只把当前默认音色标成已配置，不伪造账户全目录已开通。
- **声音库信息架构归位（2026-07-18）。** 生产阶段删除重复的“项目参考素材”五卡总览和第二层音色弹窗；右侧唯一 `VideoReferenceRail` 点击“声音”后直接打开声音库，Provider、音色与模型在同一临时面板内完成选择，点击“场景/人物/道具”同样直达各自分类库。项目旁白资产仍作为实际音轨回执保留，但不再用成片文件名冒充所选音色；展开库只承载分类素材，作品状态、自动媒体质检、渲染门禁和“确认成片”全部收进常驻窄栏。
- **响应式根因与修复。** Director 的 `ResizeObserver` 原先只在组件首次挂载执行；当首屏先显示 loading/setup、production 稍后出现时 ref 为空，窄窗永远保留 wide 三栏，播放器会缩到 42px 宽。监听现在随 production 列表出现重新绑定，实测 660px 窗口进入 `data-director-layout=stacked`、页面 `scrollWidth=660` 无横向溢出，播放器恢复为 336×597。声音库和项目参考素材转入纵向滚动，不再挤压中央播放器。
- **成品预览画幅约束（2026-07-18）。** `67952845a` 只完成窄窗布局与有声播放，没有把全宽黑色播放器外框锁到 Canvas 比例；因此内部 `<video>` 虽为 16:9，外部媒体视口实测仍是 `968×468（2.07:1）`。本轮把比例和宽度约束提升到整个黑色媒体视口，开发机 Electron 实测视口与视频均为 `830×466.875（1.7778）`，底部旁白/分辨率/FPS 信息条独立置于画幅外。最终媒体继续以 `object-contain + object-center` 完整显示，允许源素材自身留黑边但禁止界面额外拉宽或裁切；成片态不再用单镜头时长角标遮挡原生播放/全屏控制。桌面端画幅专项 `8/8` 与 TypeScript 全量检查通过。
- **导演台右侧工具轨归位（2026-07-18，2026-07-19 收口）。** 生产/成片阶段不再常驻宽版“项目参考素材”详情栏，恢复设定阶段已经确认的 `7rem` 右侧工具轨，固定显示人物、声音、场景、道具四个入口。原本内嵌在 `VideoSetupWorkspace` 的窄轨已抽成唯一 `VideoReferenceRail`，设定与生产阶段共用同一份 `VIDEO_REFERENCE_CATEGORIES`、同一套缩略图与选中态；重复的 `SETUP_CATEGORIES`、`DirectorInspectorRail` 和后续遗留的五卡 `DirectorInspector` 总览路由层已删除。生产态把作品状态、画幅/镜头/时长/制作方式、逐项质检、缺失门禁、生成旁白入口和确认按钮作为 `VideoReferenceRail` 的下半区；分类库面板不再携带生产状态，只显示素材并从 `20rem` 放宽到 `28rem`。点击入口只在工具轨左侧打开对应 `人物库/声音库/场景库/道具库` 临时浮层，不修改 Grid 列宽，也不需要在浮层里重复选择分类；关闭浮层后工具轨仍保持 `7rem`，标题栏按钮只负责显示/隐藏工具轨。目标 React 回归 `15/15`、TypeScript、目标 ESLint 和 `git diff --check` 通过；Electron 实机点击前后 Grid 均为 `240px 1203px 112px`，声音库实测 `447px`、无二次 Dialog，展开库内不再出现作品状态、质检或确认成片。
- **本轮验证与未完成项。** Marketing 全域回归 35 文件约 178 tests 退出码 0；本轮定向 Python `23/23`、Desktop React `7/7`、Volcengine 插件 `4/4`，TypeScript、Ruff、`git diff --check` 通过。开发应用已重启并保持在 Vite `5174` / Electron CDP `9222`；未生成 packaged 安装包，未真人试听并选择全部音色，未取得 OpenAPI AK/SK 做 325 音色账户同步，未以新多样性门重新生产十镜头成片，未发布或写入跨天指标，因此证据仍是 `dev-runtime`，不是 `packaged/human-loop`。
- **本轮验证。** 最终相关 Python 回归为 `50/50`（Harness、Topic Workflow、素材、视频与 Gateway RPC），Ruff 与 `git diff --check` 通过；Desktop 目标回归 `24/24`，TypeScript 与 ESLint 通过。Desktop 全量曾完成 `138` 文件、`1,022/1,022` assertions，但进程退出受既有异步 `window is not defined` timer 干扰；另一次并行全量出现 ElevenLabs 面板时序波动，目标复跑已通过，不能把测试基础设施波动写成业务全量稳定。实现回执和剩余删除门见 [`HARNESS_ARCHITECTURE.md`](./HARNESS_ARCHITECTURE.md#82-当前实施回执)。

### FACELESS-01 不露脸素材视频成品

`CONTENT-UI-01` 的自动化纵切已经完成：Electron 读取 bounded asset summary，只有点开单篇时才请求全文；审核页展示母稿、平台变体、EvidencePack、质量门、视觉版权要求和匿名评论反应场。真人确认与修改意见通过 Gateway 写入 Hermes `ContentAssetRepository`，发布 owner 拒绝未确认的当前版本；提出修改只把明确意见交回 Agent，由原生创作工具创建 `revision_of` 新版本，不在 Electron 覆盖正文。旧数据库启动后会自动补齐人审字段，既有资产默认 `pending`。

按用户决定，真实公众号成品、多轮修改和重启恢复的 `human-loop` 不在此时单独打断主线，保留到其它纵切完成后的 `E2E-01` 统一执行；因此 `CONTENT-UI-01` 证据等级是 `automated`，不能宣称真人闭环完成。

`FACELESS-01` 自动化纵切已收口，当前按既定顺序推进 `PUBLISH-01`：

1. 复用 Hermes 已有 `faceless_video` 内容计划、素材需求、声音计划、特征快照、Preflight 与 ContentAsset，不另建 Electron/外围 owner。
2. 接入有来源和授权状态的素材下载与排序；来源证明进入原生素材库和不可变版本。
3. 已完成原生不可变 Video IR/EDL、稳定 scene hash、能力 render plan、显式批准、固定版本 Remotion/HyperFrames scene executor、真实 FFmpeg 规格化/合片、场景缓存、派生最终素材、不可变成品版本、失败重试、hash-bound Render Receipt，以及黑场/冻结/响度/技术规格自动 QA；原生 `video_analyze` 已从视频管线专项工具提升为 Agent 底层感知能力，支持小视频直读、长视频/时间段采样和带时间戳视觉证据。
4. 已完成用户素材优先的 Provider 中立候选、Pexels 官方 API 适配、来源/作者/许可证快照、显式版权审查后下载和稳定 Provider 身份去重；API Key 不进入候选、回执或业务库。
5. 已完成 TTS `prepared → approved → running → completed/failed` 状态机，复用用户配置的 Hermes TTS Provider，真实输出进入声音素材及脚本哈希回执；授权 BGM 与旁白已通过实际 FFmpeg 混音和 48kHz 音轨 QA。用户已明确要求火山 TTS 常驻，Desktop 独立运行时已持久化 `marketing.video.auto_voiceover=true`，只对视频旁白自动执行；素材付费生成仍禁用，声音调用继续复用脚本哈希避免重复计费。
6. Electron 视频工作台已按真实 production 投影展示项目、镜头、素材授权、横竖/方屏及自定义画幅、执行器、时间线、声音/字幕轨、渲染状态、最终视频和 Render Receipt；确认成片或提出局部修改均写回原生审核 owner，修改继续生成不可变新版本。Electron 不拥有生产状态或执行。
7. 自动化纵切完成，进入 `PUBLISH-01 → METRIC-01 → SYSTEM-LEARNING-01 → DELIVERY-01 → E2E-01`。

完成口径：账号上下文 → 有授权来源的素材与声音 → 实际 EDL/渲染 → 可恢复版本 → 人工审片入口；最终真人认可仍在 `E2E-01` 统一验收。

### HUMAN-OBSERVER-01 Human Observation Core v1（独立基础设施，2026-07-19）

- **审计纠错。** 上一版把未来 AGI 的人类建模底座收窄成 Marketing Preflight 的心理学覆盖因子，是架构错误；`human-projection-model-v0.3` 不能代表独立人类模型，三作品/两快照门槛也只属于市场知识启发式，不能自动晋升为普遍人性规律。
- **独立 owner。** 新增 `agent/human_observer/` 和独立声明式 schema：不可变原始观察、时间图谱、版本理论、候选解释、跨事件假设、事前封存预测、事后结果、模型修订与来源摄取各自分表。Marketing 通过一条 system-only connector 单向贡献 Receipt，不能拥有或修改核心。
- **理论与存在分级。** 马斯洛、荣格、Le Bon、社会认同、去个体化、规范涌现、信息级联和具体存在策略均为带来源、假设和反证条件的竞争 lens；Le Bon 明确是历史争议视角。“人是主体、不能被模型完全还原”属于伦理/产品公理，具体存在策略仍是 `fixed_axiom=false`、`unvalidated_seed` 的模型修订，后续可被替换、争议或拒绝。
- **Preflight 解耦。** `content-production-preflight-v0.8` 只接受显式 `human-observer-read-projection-v1` 作为只读上下文；不扫描 Marketing audience 字段，不产生覆盖度、置信惩罚、加分、扣分或缺失警告。Marketing 兼容结构改名 `marketing-human-projection-adapter-v0.4` 并声明 `source_of_human_truth=false`。
- **静默权限。** Human Observer writer 已私有化且要求 `HUMAN_RESEARCH` 系统能力，不注册 Gateway RPC、Tool 或 UI；公共包只暴露没有写方法的 `HumanObserverReader` 和系统维护 runner。用户和对话不能改观察、理论、候选或模型版本；数据主体的同意、撤回、删除和保留期权利继续保留。
- **迁移与验证。** 真实 `state.db` 已在一致性备份 `state.db.pre-human-observer-v1.20260719.bak` 后从 v24 迁移至 v25，`integrity_check=ok`。真实库当前为 8 个理论 lens、1 个可修订 seed、0 条观察、0 条解释、0 次摄取；零数据证明系统没有伪造学习。Human Core + Marketing + Cron + SessionDB 全量相关回归 `514 passed, 1 skipped`，定向 `20/20`，Ruff、Python compile、`git diff --check` 通过。架构基线见 [`../../human-observer/ARCHITECTURE.md`](../../human-observer/ARCHITECTURE.md)。当前只能宣称研究数据底座完成，不能宣称系统已经学会人类。

### ARCH-01 数据飞轮与学习闭环收口（本地底层完成，部署项后置）

在 UI 和真人平台验收前，先完成所有不会因界面变化而改变的 owner、状态机和数据合同：

1. 私有事实、预演、发布、指标、复盘、候选和学习投影全部留在 Hermes 原生 owner。
2. 只有用户授权且去标识化的结构贡献可以形成中央 outbox。
3. 中央服务必须独立执行最小群组、稀疏抑制、时间衰减和签名；客户端独立验签。
4. 全局知识只进入先验层，本地 Receipt、用户明确偏好和账号事实拥有更高权重。
5. 完成 metric checkpoint → retro → candidate → memory/strategy/skill projection 后，才冻结底层合同进入 UI。

当前落地：匿名 contribution 不含 user/account/consent/source candidate；中央服务边界会再次拒绝嵌套身份字段、URL/邮箱/电话形态和过度具体值。`CentralKnowledgeStore` 已用独立 SQLite 持久化匿名贡献，保证相同引用同内容幂等、相同引用不同内容拒绝；删除后只保留最小 tombstone，原 payload 物理删除且不可重放。贡献新增或删除会立即使全部派生知识包失效，聚合与重签在同一写事务快照内完成，避免并发把旧结论重新放回服务。`services/marketing_knowledge/api.py` 已提供认证 HTTP surface：每个安装实例使用独立高熵 token，服务端只存哈希；时间戳、一次性 request nonce 和 SQLite 窗口计数分别阻断过期重放和突发滥用。贡献归属不保存 client ID，而保存按 `client + contribution` 计算的不可关联 HMAC proof；只有原认证客户端能删除，删除 key-ring 支持新旧密钥平滑轮换并在成功访问时迁移 proof。客户端 token 也可独立轮换或吊销，凭据签发只允许离线管理，不存在公共注册接口。聚合内核继续执行 k-anonymity 门槛、类别稀疏抑制和时间衰减；知识包使用 Ed25519 签名。`agent/marketing/providers/knowledge_sync.py` 作为 Hermes 原生同步 owner：只导出 accepted learning + 显式 consent 生成的 outbox；上传采用 `pending → uploading → submitted` claim，陈旧 claim 可恢复，服务已收件但本地崩溃靠 contribution_ref 幂等补结算；下载 pack 必须先通过内置信任 key-ring 验签才进入 `state.db` 和四库先验。用户撤回未上传贡献时立即 `withheld` 且清空本地 aggregate payload；已经或可能上传的贡献进入 `delete_pending`，中央返回删除成功或 404 后才结算 `deleted`。撤回与 in-flight upload 并发时，submit settlement 不得覆盖 delete_pending；新 consent_ref 会创建新贡献而非复活旧记录。Gateway 只在 `confirmed=true` 时调用 owner，Electron 未来只展示并收集确认。Cron 只非阻塞触发，同步服务 URL、安装级 client token 和公钥 ring 即使在 multiplex 模式也不属于任何用户 profile。尚未完成 TLS 部署、凭据签发服务和真实多租户压测，不能宣称云端已上线。

LOOP-02/03/04 的本地闭环已收口：`cron/product_tasks.py` 只提供 Hermes Cron 的非阻塞触发；`agent/marketing/providers/metrics.py` 和 `owned_browser_metrics.py` 是平台观察 seam；`PublishingRepository` 原子领取、延期、恢复并结算 checkpoint；`metric_loop.py` 把真实观察写为 Receipt、映射标签、执行 Retro 并生成幂等 pending candidate；`knowledge_loop.py` 再按不可变回执、重复样本、时效、冲突和历史回放静默晋级/等待/淘汰。单次结果不能绕过门禁改权重，用户和对话也不能操作候选。

四类知识库已进入 Hermes 原生 owner：平台库维护 source/region/version/valid time 与平台 stylebook；赛道与市场库维护品类、需求、竞争和商业路径的时效规律；内容库维护个体注意力、认知负荷、情绪、信任、身份与群体传播的可观察模型；账号库只允许真实 Receipt 支持且已 accepted 的 LearningCandidate 晋升。`memory_classification` 只是记忆候选分类器，用户/模型陈述不具有知识写权限。内容计划与 Preflight 读取四库覆盖度及 entry IDs；Human Observation Core 不参与内容打分，只能提供只读研究上下文。

2026-07-19 纠错后的社会实验合同：Marketing 可继续固化 `social-system-simulation-v0.3` 和生成 `causal-reflection-v0.3`，但它们只是产品域观察与候选解释。三作品/两快照只够生成 Marketing 市场知识候选，不足以验证人类理论。只有进入独立核心的不可变观察、多个竞争 lens、事前封存预测、稳定回执、跨语境反证与模型版本评估，才有资格推动 Human Observation 模型候选；任何单条作品或单个平台都不能自动晋升。

账号经营世界模型已按今天定稿重写，不恢复旧 Electron/FastAPI 生命周期：`AccountStrategyRepository` 原生拥有创作者经营画像、赛道路线假设、多角色对标经营图谱、版本化定位、内容系统和可证伪实验；`AccountLifecycleRepository` 维护项目与行为受众版本。顺序固定为创作者资产 → 赛道路线 → 行为受众 → 对标图谱 → 定位 → 内容系统 → 实验 → Receipt/Retro。没有真实市场证据的路线置信度封顶 `0.45`；对标必须保留多维匹配向量和 EvidenceRecord，粉丝数及不透明总分不能解锁定位。

内容生产已消费经营模型版本：缺少或过期定位/内容系统时，`ContentProductionPolicy` 与 Preflight 进入 `exploratory_draft`，允许用户首日试写和打磨，但 `publish_eligible=false`；`PublishingRepository` 在原生 owner 内拒绝把探索草稿送入发布审批。只有已连接账号、当前定位和当前内容系统同时成立，正式发布闭环才可继续。

实验 ID 链已贯通原生经营事实：运行中 `account_experiment` 可绑定生产计划，所有草稿自动继承 `experiment_id` 并回写实验的 `asset_ids`；发布回执和指标回执由 Receipt owner 根据 plan 自动携带 experiment。后续 Retro 可以从真实结果稳定反查行动前假设，不再依赖标题、时间或模型猜测。

未登录到登录的继承合同已落地：`AccountRegistry.adopt_prospect` 只接受已认证且经营事实为空的目标账号，`SessionDB` 按声明式 scope 表映射在单事务中迁移全部 prospect 事实并写审计记录；重复调用幂等，旧 session 永不重绑。目标账号已有项目、证据、资产或学习事实时立即阻断，禁止静默覆盖。Gateway 已提供 `marketing.account.prospect.adopt`。

真实登录事实也已归回浏览器 owner：改造后的 Playwright MCP 提供只读 `browser_verify_account_login`，直接在当前账号持久 Context 内核验平台域名和第一方登录信号，只返回真假、信号数量和已去掉查询参数/片段的页面位置，Cookie 值永不离开 MCP。Hermes post-tool seam 只信任 `mcp_marketing_browser_browser_verify_account_login` 的真实结果；认证成功后激活 AccountRegistry、尝试安全继承 prospect，并关闭有头登录进程，下一次租约以同一 profile 在后台恢复。目标账号已有经营事实时只标记认证成功、继承进入 `review_required`，绝不覆盖。Desktop 已能展示状态、创建 successor 会话，并在公众号登录后直接触发历史文章同步与账号诊断。

公众号第一条真实内容诊断纵切已进入开发机运行态：`marketing-browser-mcp` 在账号专属持久 Context 内读取已发布文章列表、公开正文和逐篇内容分析，只返回文章及指标事实，不返回后台 token、Cookie 或密码；Hermes `AccountPortfolioRepository` 将文章固化为 EvidenceRecord 和账号作品快照，按标题执行、正文结构、发布节奏和明确可见的受众反馈生成透明基线。不可见字段保持空缺，Agent 不得猜测。Desktop 只负责把公众号置顶并提供同步入口；现有登录 profile 的真实 selector 已验证，新空 profile 真人扫码、跨账号恢复和后续页面漂移巡检仍待完成，因此不能宣称完整 human-loop。

开发机真实 `state.db` 此前已完成知识 schema 升级并种入 2 条平台 stylebook、8 条内容原理、0 条账号知识；账号库为 0 证明系统没有把用户陈述或模型推断伪装成账号经验。新增赛道库和经营世界模型本轮已完成自动化临时库迁移验证，真实长期数据仍不得在未备份前批量改写。

### LOOP-01 真实发布回执进入三核闭环（底层完成，真人验收冻结）

目标：让一个真实内容 action 从 Hermes 原生审批/执行边界得到可验证 ReceiptRef，并且未知结果不能被当成成功。

执行顺序：

1. 审计 Hermes 当前 approval/tool/effect 事实源，确定唯一 receipt hook。
2. 恢复旧发布合同中仍有效的 idempotency、unknown outcome 和 post ID/URL 规则，不恢复旧 Store/FastAPI。
3. 定义发布 action 与当前 ContentAsset、account scope、preflight ID 的绑定。
4. 成功只接受平台 post ID、稳定 URL 或官方作品列表反查。
5. 失败、取消、超时、未知分别落状态；未知先查询，禁止盲重试。
6. 自动创建 1h/6h/24h/3d/7d metric checkpoints。
7. 至少完成一条开发机真实图文发布回执，再进入下一个任务。

当前落地（2026-07-11）：

- `agent/marketing/domains/publishing.py` 已成为发布经营事实的唯一 owner。
- 同一 `account + asset + version + platform` 使用稳定幂等键；重放只返回原 action。
- `prepared → executing → unknown/failed/cancelled/published` 状态已落库；`unknown` 可查询恢复，不能直接重试。
- 成功只接受目标平台的 `platform_post_id` 或具体 HTTPS 作品 URL，并要求 `verification_source`。
- 发布成功自动固化 ReceiptRef、结算 preflight、更新 ContentAsset/plan，并创建 1h/6h/24h/3d/7d checkpoint。
- `agent/marketing/publish_capture.py` 接入 Hermes 原生 post-tool 路径；只有未来的受信 `marketing_effect_publish` 工具结果能自动结算回执，没有模型可调用的“手填成功”工具。
- `marketing_prepare_publish` 与 `marketing_read_publish_state` 已进入原生 tool registry，负责预写 action 与重启恢复，不负责假装发布。
- Hermes 原生 Camofox 的 account_id 隔离作为兼容能力保留；桌面产品主线已切入 Playwright MCP 的原生 BrowserContext owner。
- `marketing_effect_publish` 已复用 Hermes 原生 MCP elicitation 一次性确认；拒绝、静默或超时不会启动 Provider，也不能永久放行最终发布。
- 发布 Provider 进入 `agent/marketing/providers/` 原生注册器；只有真实 Provider 已注册时 effect/query 工具才会出现在 Agent 工具集中，避免空按钮和占位能力。
- Hermes `state.db` 已新增原生账号注册表；`agent/account_registry.py` 是账号生命周期 owner，Gateway 只调用该 owner，Electron 不保存或修改账号真相。
- 旧 `accounts.json` 仅执行一次无敏感字段迁移；Cookie、token、验证码和 QR 内容禁止进入 SessionDB。
- AccountRegistry 已能为绑定会话签发 secret-free BrowserContext lease；未认证账号只用于登录/验证，断开或删除账号不能获得执行租约。
- `mcp/marketing-browser` 直接调用 Playwright MCP `createConnection(config, contextGetter)`；schema discovery 不启动浏览器，实际工具调用才按账号租约创建上下文。
- Hermes 原生 MCP client 已支持 `session_scope=marketing_account`：账号连接池、RPC 串行、熔断与关闭均在原生 MCP owner 内；不存在外部 Router。
- 开发机真实 Hermes 工具分发已完成 `AccountRegistry → scoped MCP → navigate → snapshot`，52 个 Playwright 工具可见，证据等级为 `dev-runtime`。
- AccountRegistry 在断开/删除时直接通知原生 MCP owner，MCP 也持续复核权限：无论上下文是否活跃都能完成释放；删除只清理该账号的 profile/output，同平台其他账号不受影响。
- 已发现并修复 MCP stdio 关闭时未等待 persistent context 落盘的问题；开发机完成“写入持久 Cookie → 关闭 MCP → 重启同账号 → Cookie 恢复”验证。
- BrowserContext 是否可见由 MCP owner 根据 AccountRegistry 的 auth_state 决定：未登录/需验证自动 headed，认证后可后台运行；Electron 不传浏览器模式。
- Hermes `state.db` 已成为营销领域唯一物理数据库；Electron 不再设置 `MARKETING_OS_*` 业务路径。
- 真实旧库已备份并完成一次迁移：1 个经营项目、1 个受众假设、4 个内容资产、1 个生产计划、1 个证据记录；五类数据源/目标逐表哈希一致。
- 数据飞轮分为用户私有学习和授权后的匿名结构贡献；中央知识只提供版本化先验，不覆盖本地回执。
- `KnowledgeFlywheelRepository` 已建立授权贡献 outbox：只有 accepted learning candidate 能生成贡献，必须有 consent_ref，禁止账号/用户 ID、原文、URL、消息、Cookie/Token 等字段，且幂等、状态受控。
- Playwright MCP 新增 `browser_extract_short_video_signals`，不再把话题标签当作 BGM；真实浏览器结果自动固化作品观察、平台 sound_id 和 EvidenceRecord。
- Playwright MCP 新增 `browser_capture_public_content`；公开作品、创作者公开身份与聚合反馈自动固化为 EvidenceRecord、PublicContentCase 和延迟 FeedbackObservation，不采集评论者身份或逐条原话。
- `PublicContentObservationRepository` 使用同一内容/受众/存在/社会反应模型生成自然实验 Receipt、内容 memory candidate 和对标 strategy candidate；相关性置信度封顶 `0.7`，接受新对标学习也只创建候选，正式选中仍需再次确认。
- `ShortVideoSignalRepository` 已能按账号/平台/时间窗计算声音候选，评分覆盖真实观看、跨作品重复、报告使用量、新鲜度、目标匹配和版权状态。
- 视频预演公式升级为 `content-production-preflight-v0.2`，`sound_fit` 成为独立维度；没有声音证据会警告但不会伪造阻断，视频草稿将 `sound_plan` 固化进不可变特征快照，发布回执携带 sound_id。

尚未完成：

- Playwright/MCP 的真实发布动作与作品列表反查 Provider 尚未接入；当前不能宣称能自动发布。
- 仍需一条开发机真人图文发布和重启恢复证据，证据等级目前停在 `automated`。

账号登录第一条原生纵切已进入工作台：平台目录、pending account、启动登录、自动验证和认证后账号切换均由 Hermes Gateway 调用 `marketing-browser-mcp` 完成；Electron 只展示状态和收集点击，不接触 Cookie、BrowserContext 或认证真相。公众号和抖音现有已登录 profile 已在开发机真实窗口完成作品与指标采集；新空 profile 真人扫码仍待交付验收。内容审核 UI 已达到自动化基线；发布确认、执行状态、verified receipt 和 `unknown` 恢复已进入同一工作台，按钮只把确认或查询意图交回 Agent，Electron 不调用平台、不改发布事实。真实 Provider 或可靠人工发布后的稳定作品身份反查仍待真人纵切。

浏览器二进制口径已确定为安装包内置单独受控 Chromium，不要求用户安装 Chrome，也不在运行时静默下载。打包后的 Hermes 使用 Electron 可执行文件的 `ELECTRON_RUN_AS_NODE` 模式运行 MCP JavaScript，但 Electron/Chromium 渲染进程不拥有账号、Cookie、自动化或业务状态；真正的浏览器 owner 仍是 `marketing-browser-mcp`。当前自包含 runtime staging 为约 917MB，其中 Chromium 约 394MB、浏览器生产依赖约 46MB；已避免额外打包 Node，并保留 Chrome.app 符号链接避免膨胀到 1.7GB，后续继续精简 Python 依赖并验证签名、公证和压缩安装包体积。

完成口径：

- 一个 Hermes session 中：资产 → 审批 → action → verified receipt → Agent 续答。
- 重启后能恢复并读取同一 receipt。
- 重放不会重复发布。
- 无 post ID/URL 时状态只能是 pending/unknown/failed。

## 后续顺序（不得并行扩建）

严格执行顺序如下；下方已经完成底层合同的章节只作为验收依据，不得被重新开成平行架构项目：

1. `CONTENT-UI-01`：自动化 UI、原生审核回执与发布门已完成；公众号真人成品与重启恢复留到 `E2E-01`。
2. `FACELESS-01`：Video IR/EDL、真实渲染、自动媒体 QA、人工审片 UI、Provider 素材与批准式 TTS/BGM 自动化已完成；真实在线 Provider 和真人认可留到 `E2E-01`。
3. `PUBLISH-01`：发布确认 UI、一个真实 Provider 或可靠人工回执、stable ID/URL 反查和 unknown 恢复。
4. `METRIC-01`：把作品级真实指标接入发布 action 的 checkpoint；账号汇总指标不能冒充单篇回收。
5. `SYSTEM-LEARNING-01`：系统静默核验候选证据、冲突、时效、回放、投影与淘汰；不建设候选治理 UI。
6. `DELIVERY-01`：签名、公证、断网首启、升级回滚和干净机安装。
7. `E2E-01`：最后统一跑自然对话 → 内容 → 审核 → 发布/回执 → 跨天指标 → Retro → 学习投影全链路。

`FLYWHEEL-02` 的真实云部署和多租户隐私压测属于上线工程化，不阻塞本地单用户 `E2E-01`，但阻塞中央知识服务对外上线。

### FACELESS-01 不露脸素材视频成品

- 只复用 Marketing OS 已拥有的素材视频 lane，不把 Video Studio 高级引擎搬回 Electron 或 Hermes。
- 原生 Video IR/EDL、scene/IR/render-plan hash、能力路由、真实 FFmpeg/Remotion/HyperFrames 混合渲染、场景缓存、派生素材、不可变成品版本、失败重试和 hash-bound Render Receipt 已有自动化证据；旧 EDL 幂等键和旧表增列可兼容升级。原生视频理解 direct/sampled/auto 已通过定向测试。Hermes 已用 FFprobe/FFmpeg 完成技术规格、黑场、冻结和响度自动 QA，报告随最终媒体、内容版本和 Render Receipt 固化；Desktop 已完成账号作用域的真实视频生产工作台，按 Video IR 自适应 `9:16`、`16:9`、`1:1`、`4:5`、`3:4` 与自定义画幅，并展示自动 QA 和写回审片决定。用户素材优先、Pexels 候选与许可证、批准式 Hermes TTS 导入、授权 BGM 混音已达到 automated；真实在线 Provider 和真人全链路审片仍待 `E2E-01`。
- 参考视频 Skill 只提供方法；素材、声音、渲染输出和审核事实继续归原生 owner。
- 工具实测、许可证边界与冻结管线见 [`../reference/skills/video-pipeline-evaluation.md`](../reference/skills/video-pipeline-evaluation.md)。
- 五层超级剪辑 Agent 的原生边界和构建顺序见 [`VIDEO_EDITING_AGENT.md`](VIDEO_EDITING_AGENT.md)。

### PUBLISH-01 真实发布与可靠回执

- 先完成一个平台，不追求全平台自动发布。
- 发布前必须有一次性确认；成功只接受平台 post ID、稳定作品 URL 或官方作品列表反查。
- 如果暂时采用人工发布，必须通过账号 owner 反查到同一作品并形成 verified receipt，不能手填“成功”。
- Hermes 已提供账号作用域的发布 action/receipt/checkpoint 投影；Desktop 已展示 `prepared/executing/unknown/published/failed`，一次性确认和查询恢复均回到 Agent 原生工具路径，不在 Electron 新增执行 owner。
- 现有 `marketing-browser-mcp` 已能读取抖音自有作品和公众号已发布文章，可作为发布后官方核验源；但没有真实发布动作，也没有足够证据只靠标题安全绑定当前 action，因此不注册会误报成功的占位 Provider。
- 当前唯一阻塞是一次真人授权的平台发布，以及从同一账号 owner 反查到 post ID 或稳定 URL；完成前 `PUBLISH-01` 保持 `automated`，不得进入作品级 `METRIC-01` 真人结算。

### METRIC-01 作品级指标回收

- 将真实作品详情采集接入 `MetricProvider`，按 publish action 和稳定作品身份结算 checkpoint。
- 当前账号卡汇总仅用于诊断，不能写入某篇作品的 1h/6h/24h/3d/7d checkpoint。
- 未知字段保持空值并暴露 data gap；分页或时间窗不完整时不得推导总量。

### SYSTEM-LEARNING-01 静默学习治理

- Electron 不读取学习候选，也不收集接受/拒绝。用户对自己偏好、身份、IP 方向和外部动作的确认走各自 owner，不进入知识真值投票。
- 单次结果只能生成 pending candidate；必须由系统证据、冲突、时效、最小样本与历史回放门禁决定等待、淘汰或版本化投影。
- 用户指出客观结论可能有误时，系统把陈述作为新证词或反证线索重新取证，不直接覆盖事实，也不要求用户审理候选。

### FLYWHEEL-02 中央服务工程化

- 聚合签名、持久化、安全 HTTP、Hermes 原生同步和 consent 撤回/删除 outbox 已贯通；上传、撤回和崩溃竞态均由本地状态机与中央幂等合同处理；服务没有公共 provisioning endpoint。
- 架构内下一步只剩真实部署凭据签发、TLS/密钥轮换演练与多租户隐私压测；每个安装实例领取独立凭据，不得把一个全局密钥打进客户端安装包。
- 真实部署前用合成多租户数据做隐私攻击与稀疏重识别测试。

### LOOP-02 指标回收（抖音/公众号一方采集已接，其余 Provider 待接）

- 到期 checkpoint 由 Hermes cron 扫描。
- 未知指标留空，不写 0。
- 原始平台字段保留，另映射 attention/retention/trust/action/fit/risk 标签。
- checkpoint 使用 `pending → collecting → observed → settled`；暂未出数回到 pending 并设置下一次尝试时间，永久不可用生成事实回执，进程中断的 collecting 可恢复。
- Cron 只触发，不写业务解释；已注册 MetricProvider 优先，抖音和公众号在没有发布 Provider 专属指标实现时会静默调用账号隔离浏览器，从发布回执的稳定作品 ID/URL 定位一方作品指标。1h/6h/24h/3d 未出数继续等待，7d 仍不可见则写 unavailable 事实，不伪造 0。

### LOOP-03 自动复盘（底层完成）

- `content_retro` 比较发布前 prediction 与真实 metric receipt。
- 输出偏差、缺失字段、替代解释，不自动宣布因果。
- 生成 pending memory/strategy/weight/skill candidate。
- 没有校准预测时明确记录 `prediction_unavailable`，只学习真实标签，禁止把全零范围伪装成预测偏差。
- `source_key=metric-retro:{checkpoint_id}` 保证崩溃恢复和重放不重复创建候选。

### LOOP-04 静默学习投影（系统治理完成）

- 用户明确偏好进入 USER/MEMORY。
- 账号策略候选进入版本化 account strategy。
- 多次成功并有失败恢复的流程进入 Skill candidate。
- 权重候选必须有至少三个支持样本并通过历史回放。
- 单次 Retro 先生成 pending candidate；后台系统再核验不可变 Receipt/Evidence。真实复盘自动进入 Account KB；权重必须至少三条支持样本并通过历史支持度、反例比例与伤害回放，失败自动淘汰，样本不足继续等待。
- 已打通 `memory → Account KB` 与 `weight → 历史回放 → versioned account influence calibration`；校准按账号隔离、幂等、可被后续 Preflight 与指标复盘读取，单次结果不能绕过门禁。
- Gateway 候选列表与显式决策 RPC 已删除，调用统一返回 unknown method。Electron、用户和对话都不能读取内部候选队列，也不能接受、拒绝、修改或恢复学习候选。
- 用户稳定偏好继续由 Hermes 原生 USER/MEMORY owner 管理，不把账号发布结果污染成全局个人记忆。
- 发布恢复 Skill 候选不属于客观知识真值，但仍属于系统程序性学习：至少三组不同 action 的 `publish_unknown → 作品列表反查 → verified publish` 双回执，还必须通过平台/Provider/内容类型作用域、有限步骤、重复副作用保护和确定性模板校验，才会由系统能力创建一次；重放只核对同内容并幂等返回。用户、对话和普通 Skill 写入口均不能替它晋级。
- 学习候选无需治理 UI；如未来展示，只允许显示来源、状态、门禁结果和版本链，不提供修改动作。

### LOOP-05 真人闭环

- 新用户自然对话建模。
- 一篇知乎/公众号真实内容。
- 一次真实授权发布或可靠人工回执。
- 跨天指标回收与下一轮建议明显改变。

### DELIVERY-01 产品交付

- 产品依赖 allowlist；marketing-browser 只复制 npm production dependency closure。
- macOS 签名、公证。
- 自包含 Hermes/Python/Chromium staging 与真实 bundled Chromium headless 启动已 automated；仍缺干净机器安装验收。
- 断网首启和升级回滚。

### DESKTOP-UI-01 原生产品壳（第一轮已完成）

- 直接改造 Hermes `apps/desktop` 原生 Shell，没有新建第二套 Electron 前端，也没有增加 UI 适配服务。
- 一级导航改为工作台、新对话、内容工厂、草稿箱、素材库、账号管理和托管；内容工厂下固定图文创作与视频创作两个子入口。Skills、MCP、消息通道、Cron 等仍由 Hermes 原生 owner 管理，但不再以开发者概念占据用户一级入口。
- 工作台读取 `AccountContextRepository`、账号平台统计和内容资产；只展示真实经营快照，缺数据时明确等待回执，不生成装饰性假曲线，也不暴露内部学习候选队列。
- 内容工厂首页只负责选择创作方式和查看最近内容；图文审核与视频生产进入独立原生路由。视频页使用同一张连续导演工作台完成 `设定 → 分镜 → 动态 → 剪辑 → 成片`，左侧对象/镜头、中央主预览与当前目标自然语言修改框、右侧角色/场景/道具/声音/素材职责固定，剪辑和成片阶段在中央展开多轨时间线。纯素材视频复用同一套工作台；高阶视频已迁出，不保留无法执行的假入口。
- 素材库把 Hermes 既有统一资产 owner 投影为本地素材与云端素材两栏。本地素材支持 Electron 原生文件/文件夹选择和拖入，只有显式版权确认后才由 Gateway 交给 `MediaAssetRepository` 复制入受控库；账号/全局作用域、SHA-256 去重、来源授权、引用删除保护和成片回执继承均有产品说明，原始绝对路径不进入业务投影。火山云端素材当前保持诚实空状态，未接 Provider、未放假数据、不会产生调用费用。
- 发布 action、稳定作品身份、unknown 恢复和指标回执从内容工厂移到总工作台；视频成片必须先在导演工作台完整审片并写入原生审核 owner，之后才由 Agent 准备发布。Electron 只展示状态和收集意图，不执行平台动作。
- 会话侧栏过滤 `<marketing-turn-context>` 等内部上下文，不再把系统会话泄漏为历史对话；外部消息渠道线程不再混入桌面历史列表。
- 移除空置顶区、开发状态栏、面板换位、触感和快捷键等开发者标题栏入口；设置和左右栏折叠保留。
- 视觉品牌改为 Marketing OS 珊瑚色体系，Hermes 主题能力继续提供明暗模式，但不能覆盖产品主品牌色。
- 新安装默认简体中文，语言切换能力保留；默认值同时修改 Hermes 原生配置和 Desktop i18n owner。
- 当前验证：Desktop TypeScript typecheck、目标 ESLint、Ruff、`git diff --check` 和正式 Vite build 通过；新导航/导演台/素材库/回执边界 React 定向 `16 passed`，素材库领域 `10 passed`，视频生产与经营闭环组合 `41 passed, 1 skipped`。这些是 automated 证据，不替代真人视觉、真实素材文件夹和整片审查。
- 仍需真人视觉验收工作台、内容工厂、账号管理、托管与新对话五个入口；后续只根据真实使用反馈打磨信息密度，不恢复 Hermes 开发者控制台式信息架构。

### FLOW-01 经营首页与经营对象连续动线（automated，2026-07-17）

- 2026-07-17 真人视觉反馈否决了独占首屏的 First-run Journey 大卡并将其删除。工作台无论是否已有经营目标，都保持原来的三个经营罗盘、真实增长路径和“今天的经营面”布局；首页首先回答浏览、涨粉、互动与作品表现，自动形成的选题/内容对象只进入下方“正在推进”列表，不再重复占据首屏。模型供应商、API Key 和默认模型仍不属于工作台旅程。
- 工作台、图文和视频页面只调用 `marketing.operation.start/status`。账号、资产、生产任务、镜头、阶段、附件和用户输入以结构化意图交给 Gateway；Gateway 内部建立账号作用域 Agent session 并提交后端执行合同。Renderer 已删除 `prepare → session.create → prompt.submit` 编排，不展示或预填 prompt，也不要求用户再点发送。
- 图文创作拥有独立 `/content/article` 工作区，选题/目标草稿按账号保留，任务完成后以 `content_asset` 结果引用回到同一资产列表和审核 Sheet；提出修改创建新版本，确认后可继续推进到发布准备。内容工厂入口不再跳普通 Chat。
- Wayfinding 由稳定一级导航、当前账号标识、内容工厂返回入口、视频返回入口和任务结果路由共同承担。内部 `desktop-product` session 从普通对话列表过滤；Chat 保留为通用能力，不再成为经营按钮的默认目的地。
- 页面返回状态：账号选择、图文 brief、工作台时间范围/平台钻取/曲线模式、素材库 tab/filter/query、视频当前项目/镜头/检查器和左右栏折叠均保留；这些只属于 UI 展示状态，不复制内容、任务或生产事实。
- 死胡同处理：账号空态可明确返回工作台并暂不登录；内容确认后提供继续推进；后台任务卡始终指向工作台、图文资产、视频导演台、素材库或托管对象，不再提供“查看执行”并把用户带回隐藏 Chat。
- 代码路径：`agent/marketing/operation_entrypoints.py`、`tui_gateway/server.py`、`apps/desktop/src/app/desktop-controller.tsx`、`chat/sidebar/index.tsx`、`workbench/{operations,marketing-task-tray,index,article-creation-view,business-surfaces,content-review-sheet,growth-dashboard,material-library-view,video-production-workbench}.tsx` 和 `store/marketing.ts`。
- 自动化证据：结构化入口、缺失结果拒绝、隐藏 Agent 失败态和 Gateway start/status Python 专项已在后续 `REPAIR-01` 扩为 `10 passed`，相邻账号生命周期/内容资产/视频生产/Gateway 回归持续通过；删除首轮大卡并补回轻量目标入口后，Desktop 全量 `137` 个文件、`1,017/1,017` 通过；TypeScript typecheck、目标 ESLint、Ruff、`git diff --check` 与正式 Desktop production build/产物断言通过。构建仍保留单 chunk 约 `26.2 MB` 警告。
- 当前证据只到 `automated`。工作台已在不恢复独占首屏大卡的前提下补回一行式经营目标输入，并直接启动 `account.bootstrap`；operation 产品投影已进入原生 `state.db`，自动化覆盖完成态重读和未完成 turn 重启后 fail-closed。尚未启动开发机真实 Agent 完成首个经营对象，未做 Electron 真人首半小时视觉/操作验收，也未生成本轮安装包。因此 `dev-runtime`、`packaged` 和 `human-loop` 均不得标完成；下一步协议债务是共享可校验 RPC contract，未完成 Agent turn 的自动续跑必须等待 Hermes 通用 task/checkpoint 具备可证明安全的恢复合同。

### REPO-AUDIT-01 台账、Git、UI 与边界收敛（2026-07-17）

- 审计起点工作树共有 183 个文件条目：93 个 tracked change、90 个 untracked file，其中 61 个路径归 `apps/`、28 个归 `agent/`、20 个归 `tests/`。它们跨后端领域、Gateway/MCP、Desktop、视频 renderer、Skill 与文档，不是可安全丢弃的单一 UI 草稿；禁止用 reset/checkout 清理。
- 当前产品源码分支为 `codex/marketing-os-product-source`，HEAD `4a5d2ea84`，没有 upstream。它的根提交是 `21d80ca6`；本地 `main` 只有 7 个旧产品提交，根提交 `e550ec2d`、HEAD `a65068f82`。两者没有 merge-base，`7/13520` 之类 ahead/behind 数字没有合并语义；禁止 merge、rebase 或批量 cherry-pick。Git 收口顺序固定为：先为当前产品历史建立受控远端并推送备份，再归档旧 `main`，最后通过明确的 ref 替换把产品历史设为默认分支；未完成远端备份前不改写 `main`。
- 当前唯一 remote 是上游代码源 `hermes-upstream`，不是 Marketing OS 产品备份目标。本轮只允许在当前产品分支建立本地 checkpoint；在用户提供或确认产品 remote 前不 push，也不把产品历史误推到上游 remote。
- Desktop 测试入口已限定为 `src/**/*.{test,spec}.{ts,tsx}`，不再把 Electron `node:test`、脚本测试和 `build/product-runtime` 暂存副本误当 Vitest；Node 26 的全局 Storage accessor 由测试专用内存实现隔离。产品新安装仍默认中文，但 Python 与继承的 Desktop 行为测试在模块加载前固定英文，避免开发者本机语言污染基线。
- `@assistant-ui/store` 的安装树曾漂移为 `0.2.19`，与锁定的 `@assistant-ui/tap 0.5.16` 不兼容；根目录 `npm ci` 已恢复 lock/override 指定的 `0.2.13`，`npm ls`、正式构建与类型检查恢复通过。不得用工作区内临时 `npm install` 改写这组版本。
- Gateway 曾重复注册 `marketing.account.context`，后声明会静默覆盖前 handler。重复项已删除，RPC 注册器现在遇到任何重复方法名立即失败；当前 148 个方法名全部唯一。Desktop 使用 25 个 `marketing.*` RPC，Gateway 暴露 36 个；其余入口未完成消息渠道/未来 UI/兼容调用方审计前不删除。
- Electron 经营任务卡已从持久 `localStorage` 改为只存在内存的后端会话展示投影，重启后不再出现无法对应后端 owner 的“幽灵任务”。真正任务、资产、账号、发布和学习状态继续由 Hermes 原生 owner 持久化；后续 `REPAIR-01` 又把 operation 产品投影补入 `state.db`，没有把持久化责任放回 Electron。
- 原任务协议泄漏已由 `FLOW-01` 收口：Desktop 不再执行 `marketing.operation.prepare → session.create → prompt.submit`，只消费 Gateway 的原子 start/status 和领域对象结果引用。当时 operation projection 尚未持久化的债务已由后续 `REPAIR-01` 收口为原生终态恢复；未完成 Agent turn 仍 fail-closed 并要求显式重试，不自动重放副作用。
- UI 结构债务集中在 `desktop-controller.tsx`（约 1.6k 行）、`growth-dashboard.tsx`（约 1.2k 行）和 `video-production-workbench.tsx`（约 2.2k 行）。拆分目标是 typed query/command projection、任务启动和纯视图，不是按视觉卡片继续横向造 Store。完整边界记录在 [`NATIVE_ARCHITECTURE.md`](NATIVE_ARCHITECTURE.md)。
- Python 首轮全量回归通过 `36,267` 项并暴露 `44` 项失败；失败全部归入跨平台路径/进程、systemd 能力、宿主代理污染、本机语言、测试替身漂移和三项 Web Provider 旧契约，没有发现营销 Repository 被 UI 反向依赖。每组修复均已定向回归通过；本轮没有为伪造“一次性全绿”再重复运行约 52 分钟的全量扫描。`scripts/run_tests.sh` 现固定英文测试语言，并为 loopback 设置 `NO_PROXY/no_proxy`，避免 macOS 系统代理劫持本地测试服务。
- Desktop 继承测试债务已清零：Vitest `136` 个文件、`1,015/1,015` 通过；Electron/packaging `node:test` 为 `265 passed, 1 skipped`，跳过项是 Windows junction 平台限定。浏览器 MCP `23/23` 通过。Ruff、TypeScript、ESLint、`git diff --check`、正式 Vite production build 与产物断言均通过；npm 锁定树一致，root audit 为 `0 vulnerabilities`。当前 renderer 单 chunk 约 `26.1 MB`，仍有超过 `25 MB` 的构建警告，属于后续 bundle 拆分风险，不影响本轮构建成功。
- 本轮 packaged 证据只到正式 renderer build、runtime staging 测试和产物存在性断言；没有生成签名安装包、没有在干净机安装，也没有替代真人 UI/账号/发布闭环，因此证据等级仍是 `automated build`，不能写成 `human-loop`。

### REPAIR-01 继承一致性、首轮入口与任务恢复（automated，2026-07-17）

- 本轮严格修改原生 owner 和现有产品 surface，没有新增 adapter、外层服务、Electron 业务状态或自动发布占位实现。审计起点已有的首屏大卡删除与工作台简化改动全部保留。
- `PROSPECT_SCOPE_COLUMNS` 已补入 `media_asset_library`、`material_searches`、`material_candidates` 与 `marketing_audio_jobs`。登录继承会在同一事务中移动这些账号作用域事实，并把目标账号已有素材/搜索/音频事实视为显式合并冲突；`media_asset_references` 没有账号列，继续通过素材外键保留，不制造重复归属字段。新增回归覆盖完整迁移、引用保留、幂等和目标素材冲突。
- ContentAsset 的规范持久字段仍为 `_production_kind`；摘要、发布 request 和学习 replay 现统一优先读取该字段并兼容旧 `production_kind`，避免内容类型在发布和后续 cohort 中变成空值。
- 工作台不恢复被真人否决的 First-run Journey 大卡。只有在原生 lifecycle 尚无 `business_goal` 时，经营罗盘上方出现一行式目标输入；提交直接调用 `account.bootstrap`，目标由 `AccountLifecycleRepository` 持久化，Renderer 不保存第二份长期经营事实。
- 新增原生 `marketing_operations` 表和 `MarketingOperationRepository`。start 在启动隐藏 Agent turn 前写入 `working` 投影，Agent 终态写回结果引用或错误；Gateway 重启后已完成 operation 可按原 ID 读取，未完成 turn 结算为保留原始输入的可重试错误，不返回 404、不自动重放发布等外部副作用。Desktop 任务卡仍是内存展示投影。
- 自动化证据：Marketing OS 相关 Python `31` 个文件、`184/184` 通过，其中 operation 入口与重启恢复 `10 passed`；Desktop 全量 `137` 个文件、`1,017/1,017` 通过，工作台轻量首轮入口与原地内容审核定向 `2 passed`。首次 Desktop 全量运行有一个无关 TTS 设置等待用例发生并发抖动，该文件单跑 `7/7` 后立即全量复跑全绿，本轮未修改其源码。TypeScript typecheck、目标 ESLint、Ruff、`git diff --check`、正式 Vite production build 和产物断言通过；构建输出 `4,204` 个模块，单 JS chunk `26,160.56 kB`、gzip `5,396.97 kB`，继续超过 `25,000 kB` 告警线。构建标记为 `DIRTY`，只作为 automated 证据，不得发布。
- 仍未完成：Marketing OS 产品远端备份、共享可校验 Desktop/Gateway RPC contract、真实发布 Provider/可靠人工核验、作品级指标、真人首半小时、签名安装与自然跨天 E2E。唯一 remote 仍是 `hermes-upstream`，用户未提供产品 remote 前禁止 push；真人账号未授权前 `PUBLISH-01` 不得升级证据等级。

### DRAFT-01 内容工厂草稿箱与原管线恢复（automated，2026-07-17）

- 一级 `/drafts` 草稿箱按当前账号统一展示图文 `draft/review_ready/approved` 与视频 `prepared/approved/running/failed/completed`。2026-07-18 起，已验收但尚未发布的图文和视频也统一投影为“待发布”，直接在草稿箱核对发布门；`published`、`superseded` 旧版本和被 production 代表的视频源/输出资产不会混入或重复展示。
- 本机真实库只读核对显示，“AI 教育”最新资产是第 4 版 `review_ready + pending`，第 2/3 版已 `superseded`。它没有丢失，只是原图文列表缺少集中管理入口；新草稿箱会自动把第 4 版投影为“等待审核”，点击“继续”回到 `/content/article?asset=...` 的原审核 Sheet。视频 production 则回到 `/content/video?production=...`；极少数尚未建立 production 的不露脸视频源资产交回原生 `content.resume`，不在 Renderer 续造生产状态。
- `DraftBoxRepository` 只做账号作用域聚合与动作分派，业务真相仍由 `ContentAssetRepository`、`VideoProductionRepository`、`content_production_plans` 和 Hermes `state.db` 拥有。Electron 没有草稿 Store、LocalStorage 或第二生命周期；Gateway 新增 `marketing.drafts.list`、`marketing.draft.archive`、`marketing.draft.restore` 三个 RPC 后，Renderer 消费 25 个 `marketing.*` RPC，Gateway 暴露 36 个，仍无反向依赖。
- 归档是显式确认后的软归档：内容资产、视频 production、关联的 source/output asset 和生产计划在同一原生事务边界内进入 `archived`，保存 `archived_from_status/archived_at`；恢复时回到归档前状态。运行中的视频和已验收待发布作品拒绝归档，后者虽然由草稿箱统一承接，但语义是“待发布”而不是可丢弃的半成品；历史版本、审核记录、EDL、素材引用和回执均不删除。
- 数据库升级继续由 `SessionDB` 声明式 schema reconciliation 拥有；`content_assets` 与 `marketing_video_productions` 只新增归档字段，没有新数据库、JSON 双写或 Electron 迁移。旧图文 validation 迁移也已加生命周期保护，不能在重启时把 archived/superseded/approved/published 资产改回草稿。
- 自动化证据：Marketing OS Python 全量 `168 passed, 1 skipped`；草稿专项、相邻内容/Gateway/视频组合 `22 passed, 1 skipped`，新增专项 `3/3`；Desktop 全量 `138` 个文件、`1,019/1,019` 通过，草稿/路由定向 `5/5`。TypeScript typecheck、变更范围 ESLint、Ruff、Python compile、`git diff --check` 和正式 Desktop production build/产物断言通过；构建输出 `4,205` 个模块，单 JS chunk `26,167.82 kB`、gzip `5,398.52 kB`，仍超过 `25,000 kB` 告警线。构建标记为 `DIRTY`，只作为 automated 证据。
- 当前未做的事：没有替用户自动归档“AI 教育”，没有修改真实业务行，没有运行真人 Electron 视觉/点击验收，也没有提交、推送或生成签名安装包。因此本轮不能升级为 `dev-runtime`、`packaged` 或 `human-loop`；下一步真人验收应覆盖当前账号草稿汇总、继续审核、归档确认、已归档恢复和账号切换隔离。

### SCOPE-06～09 经营主体、全平台生产与推荐预演（SCOPE-06 dev-runtime；SCOPE-08/09 automated，2026-07-17）

- **SCOPE-06 / 致命跨账号读取问题：已修复关键读链。** `marketing_operating_entities` 与成员表成为账号之上的 creator/brand 身份；Session 保存稳定 `marketing_entity_id` 和独立 `marketing_account_id`。Agent 读取账号上下文、内容资产与 EvidencePack 时聚合主体下全部关联账号，公众号等单平台 portfolio 可显式指定任一已关联账号；未关联账号继续 fail-closed。登录、BrowserContext、采集写入、发布与其它外部 effect 仍固定 action account，不能因聚合读取而静默切号。旧单 owner 安装在首次解析时只做一次确定性默认分组；已有多个经营主体时不猜归属。
- **SCOPE-07 / 不执行。** 用户确认现有工作台、内容工厂与草稿箱信息架构工作正常，本 scope 不再改导航、页面层级或现有生产入口；本轮后端管线直接接入现有界面。此前已完成的 `DRAFT-01` 草稿箱保持原样，不撤销也不重复重构。
- **SCOPE-08 / 已从“双平台”改为可扩展全平台。** `platform_catalog.py` 是版本化内容行为目录，不等于登录 connector 白名单。内置 12 个国内/海外平台画像只是当前知识覆盖，不是允许列表；任意安全平台 ID 都能进入计划。未知平台只能获得通用可重排素材包和显式 `platform_guidance_unverified` 警告，不能伪造规则。`cross_platform_campaign` 保存一个共享内容内核、目标平台全集、逐平台 blueprint 与实质不同的 variants；每个变体必须声明格式及 audience/opening/structure/CTA 适配依据。`platforms=['all']` 展开当前经营主体全部已连接渠道，并可同时附加尚未连接的海外目标。
- **SCOPE-09 / 推荐选题先预演，已覆盖主动对话与每日推送。** 历史行为没有硬保证，而且审计确认原实现并不存在正式的“每日抓取 → 建模 → 选题 → 推送”产品管线：`cron/product_tasks.py` 只跑指标 checkpoint 与知识同步，真实 profile 当时也没有 `jobs.json`。现在主动入口 `account.prioritize` 与新增每日入口都必须为每个确切候选建立 durable production plan 和 immutable preflight；`go=false` 只能进入 `research_only` 研究池，不得出现在推荐正文。每日 owner 使用 `marketing_topic_recommendation_batches/candidates` 保存主体、日期、来源会话、候选、`plan_id`、`preflight_id`、决策、规范推送正文与 SHA-256；同一主体同一天重跑复用同一批次，不重复制造推荐。
- **SCOPE-09 / Cron 硬门禁。** `marketing-daily-topics` blueprint 会先读取经营主体全部已关联平台，再核验当日外部信号；搜索摘要不算证据，必须由原生 collector 形成 EvidencePack。Cron 在第一次模型调用前把运行会话绑定到稳定 `marketing_entity_id + marketing_account_id`，最终回复必须逐字等于 `marketing_preflight_daily_topic_recommendations.delivery_markdown`。通用 scheduler 在投递前按当前 Cron session 查询已完成批次并核对 SHA-256；漏调工具、无批次、加前后缀、改写正文或使用未通过候选都会使整个 job fail-closed，模型文案不能绕过产品回执。
- **SCOPE-09 / 本机启用状态。** 开发 profile 已创建 job `9c032a57f7c1`（“每日选题预演推荐”），以已认证抖音动作账号绑定“我的经营主体”，`platforms=all` 会同时覆盖当前已关联抖音与公众号并允许以后追加任意海外平台；每天本地时间 `09:00` 运行，候选上限 5，结果保存在 Desktop 的 Cron 任务/运行会话中。当前没有经用户确认的 Telegram/飞书等外部投递目标，因此 `deliver=local`，不会擅自向外部渠道发消息；需要外部主动消息时只改 delivery 配置，不改变预演门禁。
- **SCOPE-09 / 工作台选题收件箱。** 工作台底部原“今天的经营面/今日判断”占位区已改为“今日选题”：Gateway 按当前账号反查稳定经营主体，只投影最新 completed 批次中 `recommendation_eligible=true` 的候选；未通过项只显示研究池数量，不泄漏为推荐。界面展示预演分、为什么是现在、全平台集合，并可展开每个平台各自的载体、开头、结构、视觉与 CTA；未知平台保留通用方案和未校准提示，不写死国内双平台。工作台每 60 秒轻量刷新，也允许手动刷新；没有批次时诚实提示下一批每天 09:00 到达，不制造演示选题。
- **SCOPE-09 / 通用选题与平台推荐。** 每日任务要求每个候选为每个目标平台提交 `platform_fit_hypotheses`（匹配假设、理由与可选证据），原生预演再用 65% 候选假设 + 25% 全局 InfluenceScore + 10% 平台知识置信度校准为 0–100 的“预演匹配度”；它是制作适配预测，不是真实表现或成功率。如果某平台假设缺失，后端会以 70% 全局预演 + 30% 平台知识置信度保守补分，不会让整批定时任务因单个模型字段漏交而丢失。至少两个平台达到 75 才进“通用选题”；否则进“平台推荐”，以最高分平台为主推，卡片小字展示如“抖音匹配度 91% / 小红书匹配度 60%”。未知平台仍可进入管线，但在完成平台研究前保守封顶 64，不能靠模型自评冒充强匹配。分类、分数、推荐平台和逐平台制作方案一起从 Cron 回执持久化到 Gateway，并原样注入 `content.topic.start`，Renderer 不在前端猜分类。
- **SCOPE-09 / 进入内容工厂。** “交给内容工厂”调用新增结构化 `content.topic.start`，Renderer 只提交 candidate ID。Gateway 在启动 Agent turn 前重新核验候选属于当前经营主体、批次已完成且预演通过，再从原生 owner 注入不可替换的 `plan_id`、`preflight_id`、真实 topic、证据/信号引用、目标平台全集和 platform blueprints；前端标题不能覆盖原生选题。SCOPE-10 完成后 plan/preflight 的规范 owner 已是经营主体，候选记录中的 `execution_account_id` 只作为动作通道继续保留；隐藏 Agent session 不会因工作台偶然停留在另一渠道而切换动作账号，也不会把公众号和抖音事实拆成两个品牌。Agent 必须在已有计划下创建各平台真实草稿，不能重新规划成另一个题，也不能绕过预演；没有落成可见 content asset 的 turn 结算为错误，不假报完成。
- 代表性回归使用“当前的 AI 是泡沫吗？”覆盖抖音、公众号、YouTube、LinkedIn 与未知 `mastodon`：同一 plan 生成五份不同 variant，未知平台诚实降级；中文平台别名与 X/Twitter 归一化也有单测。代码路径：`agent/marketing/platform_catalog.py`、`domains/{operating_entities,account_context,content_policy,content_assets}.py`、`intelligence/production_preflight.py`、`session_scope.py`、`tools/marketing_tools.py`、`operation_entrypoints.py`、`tui_gateway/server.py` 与 `hermes_state.py`。
- SCOPE-10 已在下一节完成；仍未完成的是多品牌用户的显式建组/拆组/冲突审查 UI、平台画像来源/有效期/真实账号效果校准，以及五平台真实模型逐篇真人审稿、发布和跨天回收。后两项继续属于 `PLATFORM-KB calibration` 与 `E2E-01`，不得标成 human-loop。
- 开发机真实 `agent-runtime/state.db` 已完成 schema 与成员迁移：当前“我的经营主体”关联已认证公众号和抖音两个渠道；真实聚合读取返回两个 linked contexts、共享抖音经营策略，并能在同一主体内读取当前内容资产。迁移没有改内容、portfolio、发布或指标事实。Desktop/Gateway 已重启到新代码，Vite `5174`、Electron CDP `9222` 与新的 Hermes dashboard 进程均存活；这只把 SCOPE-06 提升到 `dev-runtime`，不替代真人对话复测。
- 当前自动化证据：新平台目录专项 `4/4`；经营主体、内容生产与 operation 定向 `36/36`；视频/账号相邻修复回归 `22 passed, 1 skipped`；此前 Marketing OS 宽回归 `217 passed, 1 skipped`；新增每日候选、真实跨平台 plan/preflight、批次幂等、规范正文哈希、缺失回执拒绝、Cron 会话绑定与模型改写拒绝均有专项覆盖。通用/平台推荐分类加入后，`tests/marketing + tests/cron` 最新全量为 `735 passed, 1 skipped`，平台匹配与 operation 定向 `17/17`；Desktop 全量复跑 `138` 文件、`1,020/1,020` 通过，工作台分组与匹配度展示 `3/3`。首次 Desktop 全量的旧 i18n 保存回滚用例受并发环境影响失败 1 项，该文件立即单跑 `10/10` 通过，随后全量复跑全绿；本轮未修改 i18n 代码。TypeScript、目标 ESLint、Ruff、Python compile 与 `git diff --check` 通过。`pkg_resources/websockets` 的 8 条第三方弃用 warning 未由本轮引入。

### SCOPE-10 全量历史事实迁移到经营主体 ownership（dev-runtime，2026-07-18）

- **所有权合同已落到数据库。** `ENTITY_OWNED_SCOPE_COLUMNS` 统一登记 33 张核心历史业务表，所有表都有 `entity_id TEXT NOT NULL` 规范 owner 和 `(user_id,entity_id)` 索引；`account_id` / `target_account_id` 不删除，语义收窄为采集来源、执行账号或渠道维度。发布 action、指标 checkpoint、账号 portfolio 等渠道事实因此仍能追溯具体平台账号，但品牌策略、受众、证据、内容、预演、推荐、知识和学习不会再以登录账号作为最终所有者。兼容库里的 `audience_snapshots`、`memory_candidates` 若存在，也会声明式补列并进入同一约束。
- **迁移与新写入都 fail-closed。** schema 版本从 22 升到 23；启动时先按已有成员关系回填，旧单主体用户允许确定性归并，已有明确 `entity_id` 的事实保留原 owner，多主体但账号未分组或 prospect 事实无法唯一判断时直接拒绝启动并要求显式审查。每张表的数据库 trigger 会在同一写语句内解析主体、为明确的真实账号补成员关系，并拒绝空 owner、无效 owner 和跨主体 action account；不能再由某个漏传字段的 Repository 写出“孤儿事实”。`account_strategy_projects` 的唯一活跃约束也从 `(user_id,account_id)` 改成 `(user_id,entity_id)`，同一品牌的抖音与公众号复用一套经营策略。
- **登录继承保持主体不变。** prospect adoption 现在先核对所有源事实只属于一个主体，再把已认证目标账号链接到该主体，最后只迁移渠道 provenance；`entity_id` 全程不变。目标账号已属于另一主体、已存在经营事实或源事实跨多个主体时继续拒绝隐式合并。旧会话仍保留原 prospect 路由，新会话绑定真实 action account，不改既有会话提示前缀。
- **真实库升级证据。** 升级前通过 SQLite 在线 backup 生成 `state.db.pre-entity-v23.20260718-123637.bak` 回滚副本，并先在副本完成 22→23 试迁移。真实 `agent-runtime/state.db` 随后逐表升级：33 张表行数全部保持一致；11 张有数据的业务表分别为策略 `1`、受众 `1`、内容资产 `4`、生产计划 `11`、证据 `16`、账号 portfolio `2`、知识条目 `10`、自有内容观察 `11`、预演 `10`、推荐批次 `1`、推荐候选 `5`；空主体 `0`、无效主体 `0`、外键违规 `0`，`PRAGMA integrity_check=ok`。迁移识别出默认用户主体（关联抖音、公众号两个真实账号）与飞书用户空间的独立主体，没有跨用户混合。Desktop/Gateway 已在升级后重启，Vite `5174` 与 Electron CDP `9222` 正常。
- **自动化证据。** 新增迁移专项 `6/6`，覆盖 33 表列/trigger 合同、旧可选表自动加列回填、重复启动幂等、多主体歧义拒绝、未分配真实账号跨主体写入拒绝，以及双平台账号共享同一主体策略；prospect 回归同时逐表证明 adoption 后 `entity_id` 不变、`account_id` 改为已认证账号。Marketing OS 宽回归首次运行只有旧库 import 的 trigger change 计数暴露 1 项并已修复为逻辑行数，失败文件复跑 `3/3`；随后 37 个营销相关文件全域复跑 `213/213`。SessionDB 与 Cron `876/876`、Desktop Vitest `1,020/1,020`、Electron/packaging `265 passed, 1 skipped`（Windows junction 限定）全部通过；TypeScript、Ruff lint、`git diff --check` 和正式 Desktop production build/产物断言通过，ESLint 为 `0 error` 并保留一个未修改测试文件的既有空行 warning。正式 build 输出 `4,205` 个模块，单 JS chunk `26,171.97 kB`、gzip `5,399.42 kB`，继续超过 `25,000 kB` 告警线，未生成签名安装包。
- **本 scope 不冒充完成的事。** 数据 owner 与运行时约束已完成，但多品牌管理 UI、冲突审查 UI、平台知识时效校准、真实五平台成品人审、真实发布、自然跨天指标回收、签名安装包和产品远端备份仍未完成。当前唯一 remote 仍是 `hermes-upstream`，本轮只做本地 Git checkpoint，不 push。

### E2E-DAILY-01 今日选题到图文发布门、视频失败审计（dev-runtime，2026-07-18，测试视频已清空）

- **真实输入与预演。** 从工作台今日选题 `topic_candidate_f620cefd71994d6c54f1f722` 选择“一人公司生存指南——AI泡沫过后，什么才是真护城河”；原预演 `preflight_5228443102644367a6dee7500d39f317` 覆盖公众号、抖音、知乎，平台适配分分别为 `75/81/75`，综合预演 `73`。本轮复用同一主题、证据和平台蓝图，没有另外编造演示选题。
- **图文链已到发布门。** Agent 生成跨平台 campaign `asset_102fa001dbda4d8bbce69bda2fd7e25f` 第 2 版，包含公众号、抖音、知乎三个实质不同版本并完成真实 Desktop 审核确认；第 1 版已按不可变版本规则 `superseded`。发布准备走确定性 Gateway，而不是自由模型操作；当前预演因账号定位、内容系统和平台连接未齐而保持 `publish_eligible=false`，界面明确阻断，不生成发布 action，更没有外部 effect。
- **旧视频结论纠正为“静态预览”，没有到发布门。** `video_production_51023e2372b447c3b7a9711933bb6159` 的 7 个镜头实际全部引用 `marketing_os_local_storyboard` 标题卡，且没有旁白音轨；`media_4bf...` / `asset_b659...` 只证明本地 FFmpeg 能把占位分镜拼成 75 秒 MP4。此前人工写入的 `accepted` 不再被当作发布资格：草稿投影现在把它标成 `workflow_stage=production_blocked`、`can_prepare_publish=false`，发布 owner 也会再次拒绝占位素材、缺失旁白或不可执行 render plan。
- **内容资产直达视频，不再复制脚本。** `ContentReviewSheet` 在已接受 campaign 的视频平台变体上提供“制作视频”；Gateway 只接收 `asset_id + platform`，由 `ContentAssetRepository` 核验 campaign、人审、平台格式和唯一匹配的已预演 `faceless_video` plan，再交给 `VideoProductionRepository`。普通自由简报仍交给 Agent；旧 `from_script` 只保留兼容入口，产品 UI 不再调用。
- **素材、声音与渲染器真正接入准备链。** `prepare_from_campaign` 逐镜头解析 Visual/VO/On-screen text，为每个镜头建立幂等素材搜索并准备一条 TTS job；用户确认候选来源后才物化素材，明确确认费用后才执行旁白，二者都会创建不可变 IR 新版本。kinetic typography、信息/数据镜头路由 Remotion，设计转场/快切路由 HyperFrames；运行时由原生 backend 发现系统 Chrome 或打包 Chromium，不把浏览器 ownership 移给 Electron。
- **真实开发库复跑暴露素材假象。** 同一 campaign 曾建立 7 镜头准备任务，能力路由确实得到 5 个 Remotion + 2 个 HyperFrames，系统 Chrome 健康检查也为 ready；但当前账号真实素材库为 `0`、Pexels 未配置。界面出现的 49 个 `user_library` 候选全部来自两套 `marketing_os_local_storyboard` 派生分镜，被本地检索错误包装为“用户已确认版权素材”，不是真实素材候选，因此这次复跑判定失败，不能作为生产链 dev-runtime 证据。
- **用户要求后已清空本轮全部视频测试资产。** 删除同 campaign 的 5 条 production、3 个派生内容资产、14 张分镜占位、1 个静态 MP4、7 组素材检索与 49 个候选、3 条未执行旁白任务；原 campaign、选题和预演事实保留。清理前生成 `state.db.pre-video-cleanup.20260718-155521.bak`，清理后目标 production/search/audio 均为 `0`，数据库 `integrity_check=ok`。草稿箱现在只保留图文 `asset_102fa...`，不再展示本轮测试视频。
- **自动化与安全证据。** 本轮变更域后端 `34/34`、发布/经营回归 `25/25`、草稿箱/图文/视频 UI `11/11` 通过；新增覆盖 campaign 直达、每镜头素材请求幂等、Remotion/HyperFrames 路由、不可变素材修订、缺旁白/占位/渲染器门禁，以及“误标 accepted 的静态卡仍不能准备发布”。TypeScript、Python compile 与 `git diff --check` 通过。开发应用已重启在 Vite `5174` / Electron CDP `9222`，本轮没有平台发布、费用调用或跨天指标写入。
- **仍未完成。** 视频板块不再以“逐镜头补素材即可完成”描述；必须先完成下面的产品结构重整，才能再次建立真实 production。图文仍需补齐 publish preflight 所需的账号定位、内容系统和目标平台连接；之后才是一次性发布批准、可靠回执、作品身份反查和跨天数据回收。平台画像来源、有效期和账号效果校准也仍未完成。本节只有图文链与失败审计达到 `dev-runtime`，视频产品闭环没有达到。

### MATERIAL-VIDEO-AUDIT-01 素材视频板块重整（盘点完成，待实施，2026-07-18）

- **现有底座可以保留。** `MediaAssetRepository` 的受控导入、来源/授权、临时与本地层级、引用保护；`Video IR` 的规范化、scene/IR hash 与能力路由；固定版本 Remotion/HyperFrames runtime；FFmpeg 规格化/合成、场景缓存、自动 QA、不可变成片与 Render Receipt；TTS 的一次性批准状态机；草稿箱/发布 owner 的 fail-closed 门禁，均属于正确原生 owner。
- **P0-1 / 素材检索不可信。** 本地搜索按空格拆词，中文视觉描述大多无法匹配；即使完全不匹配也给所有资产固定 `0.55` 语义分，并允许 `storyboard/derived/marketing_os_local_storyboard` 进入 `user_library` 候选。必须先排除占位/派生/已删除素材，改为经营主体范围的真实资产检索，候选必须展示缩略图、来源、作者、授权、时长、画幅和逐镜头匹配理由；无真实候选就明确为空，不能凑数。当前只有 Pexels 一个外部适配器且未配置，不能声称在线素材链可用。
- **P0-2 / 准备态没有播放器。** Desktop 只有 `final_video_asset_id` 存在时才挂载 `<video>`；分镜阶段显示的三角形只是装饰。目标应是同一时间线播放器在“分镜占位 → 已选图片/视频 → 临时旁白/字幕 → 渲染成片”四种状态都可播放、暂停、拖动和逐镜头跳转，并明确标注“预演”或“成片”；正式发布门禁不因此放宽。
- **P0-3 / 项目与版本模型不成立。** 每选一个镜头素材就新建一条独立 production，但表里没有 `project_id/revision_of/current_revision_id`，旧版本继续出现在项目下拉框；UI 的“V1/V2”实际只是当前 IR 中的素材列表，不是 production 版本。需要稳定的视频项目 owner、不可变修订链、唯一当前版本、按镜头差异和可删除/归档的项目生命周期。
- **P0-4 / 阶段与按钮存在假动作。** `设定 → 分镜 → 动态` 主要是 Electron 本地 tab 切换，只有剪辑确认才调用确定性 render；“全自动、导出、新增镜头、生成新版本、选择既有素材、自然语言修改”多数仍只是启动自由 Agent intent，没有对应的 durable owner/回执。未接通前应移除或禁用，接通后每一步都写同一项目状态和不可变修订。
- **P0-5 / 两个高级渲染器只是通用样板。** Remotion 场景硬编码 `MARKETING OS` 和虚构 `37/68/92%` 数据卡，HyperFrames 硬编码 `DESIGNED MOTION / LIVE`；二者只套统一背景、缩放、标题和转场，不消费平台设计系统、账号视觉身份或证据数据。虚构统计必须立即禁止；下一版应由证据绑定的 graphic spec、平台 safe-area/style tokens 和逐镜头 motion recipe 驱动，渲染器只负责执行。
- **P0-6 / 声音不是完整制作链。** 当前把全部 VO 拼成一条 TTS，缺少逐镜头时间对齐、声音选择与试听、费用预估、语速/停顿、BGM/SFX、ducking 与字幕校准；准备任务还曾产生多条同主题 `prepared` job。需要一个项目级 sound plan 与唯一 voice job lineage，所有计费动作继续一次性确认。
- **P0-7 / 经营主体读取未贯通。** 表已具备 `entity_id`，但素材库、检索、production、草稿箱和 Desktop 列表仍主要按 `account_id` 查询，同一品牌另一个平台账号下的真实素材不会自然进入当前视频项目。项目 owner 应是经营主体，`account_id/platform` 只表示目标渠道与执行通道。
- **目标管线。** 已接受的平台视频变体/独立视频 brief → 平台化视频 brief（目标、时长、画幅、hook、旁白、镜头意图）→ 可审的 shot plan → 每镜头真实素材板与授权确认 → 可播放预演（素材、旁白、字幕同步）→ 证据绑定的 Remotion/HyperFrames/FFmpeg 镜头计划 → 一次性渲染 → 自动 QA + 真人审片 → 草稿箱待发布 → 发布/指标/复盘。图文稿只提供内容内核与平台事实，不再要求用户复制“图文脚本”到视频入口。
- **实施顺序。** `MV-01` 项目/修订/删除 owner 与 entity scope；`MV-02` 可信素材检索及候选板；`MV-03` 准备态时间线播放器；`MV-04` 声音/字幕时间线；`MV-05` 证据绑定的 renderer spec 与去演示模板；`MV-06` durable 阶段动作和 UI 去假按钮；`MV-07` 重新跑一条真实素材、真实旁白、混合渲染、QA、人审到草稿箱的纵切。完成 `MV-01～06` 前不再制造测试 production。

## 暂停项

- 非闭环所需的工作台装饰。
- 全平台自动发布。
- 微信/飞书体验扩张。
- Windows 正式交付。
- 抖音/B站/小红书 BGM 真人页面 selector 验收（账号登录 UI 已具备，等待真人账号纵切）。
- 未校准的流量、完播、互动和 InfluenceOS 对外承诺。

## 当前回归基线

- Agent 底层感知层（2026-07-15）：产品身份、图片/视频工具、渐进披露、运行时缓存切换、文件视频引导、显示与上下文压缩组合回归 `428 passed`；真实模型-facing `marketing` schema 在未配置视觉 Provider 时仍保留 `vision_analyze/video_analyze`，调用时才明确报告 Provider 缺失。相邻营销域组合保持 `163 passed, 1 skipped`。
- 社会实验闭环专项（2026-07-15）：存在本体合同、马斯洛需求投影、荣格认知投影、存在策略、公开数据采集、内容预演、匿名社会反应、指标回执、投影链对账、因果反思与内容生产组合回归 `163 passed, 1 skipped`；跳过项为需要显式 `MARKETING_OS_TEST_BROWSER_EXECUTABLE` 的离线 Remotion/HyperFrames 高级渲染集成门。该结果证明自动化合同可串联，不等于真实平台 selector、跨日样本或因果效应已经完成真人验收。
- 营销、Agent、Gateway、审批与账号浏览器隔离组合回归：491 passed。
- 当前营销域、经营世界模型、四类知识、中央服务/同步/撤回、内容生产、原生采证、prospect 继承、真实登录激活、SessionDB 与经营闭环主组合回归：391 passed。
- 中央知识服务专项：15 passed；覆盖嵌套身份拒绝、持久化、内容碰撞、删除失效、认证、过期请求、nonce、限流、客户端 token 轮换/吊销、跨客户端删除拒绝和删除 key-ring 轮换。
- 改造版 Playwright MCP：23 passed；包含账号租约、旧 profile 原生迁移、持久化/清理、浏览器运行时、平台登录启动、登录信号、抖音自有作品采集、公众号内容分析采集、敏感 URL 清洗和 57 项工具 schema。
- TUI/Gateway 会话既有回归：172 passed；本轮新增 Gateway adoption RPC 已包含在营销组合回归。
- Hermes Cron 调度/作业/产品任务组合回归：302 passed；产品任务无 MetricProvider 时静默，有真实 Provider 时调用指标 owner。
- LOOP-01/02/03/04 发布账本、审批、指标回执、缺失值、延期、崩溃领取恢复、Retro、候选和账号知识治理单文件回归：19 passed。
- Desktop 平台/打包回归：262 passed、1 skipped；自包含 runtime staging、MCP 生产依赖闭包、受控 Chromium、Electron-as-Node 与真实 bundled Chromium 启动已验证。
- 通用媒体素材库：65 项营销域回归通过；上传路径隔离、MIME/版权来源强绑定、敏感元数据脱敏、可信素材幂等、引用删除保护和 32MB Gateway 内联上限已进入 Hermes 原生领域 owner。
- 工作台账号连接纵切：TypeScript 生产构建通过，账号 Gateway/Registry/Auth/metrics 组合回归通过；真实已登录账号完成数据纵切验收，新的空 profile 扫码流程仍保留为交付检查项。
- 真实账号指标验收（2026-07-13）：抖音创作者中心返回全部作品 4、公开已发布 3、私密 1、公开播放 5366、累计获赞 56，已写入 `marketing_accounts.stats_json`；公众号最近 9 篇逐篇读取内容分析详情，汇总阅读用户 351、分享用户 28、点赞 11、在看 7，口径为发表后 30 天且阅读/分享单位为去重用户。发表记录列表中的预览数只保留为 `publish_preview`，不得再进入指标评分或账号卡。
- 指标边界：抖音 `videos_count` 只表示公开已发布作品，`all_videos_count` 包含私密作品；公众号账号卡使用“已同步阅读/已同步分享”，不声称是账号历史总量。若作品列表分页未完整加载，公开/私密拆分必须为空并暴露 data gap。
- 内容审核纵切（2026-07-14）：Gateway 提供账号作用域 bounded summary、按需全文与显式审核 RPC；Desktop 展示母稿、平台变体、证据、质量门、版权要求和评论预演，支持确认当前版本或带意见进入 `revision_of` 新版本；发布 owner 拒绝未真人确认资产。迁移/Gateway/经营闭环定向 `30 passed`，营销域宽回归 `140 passed`，UI `2 passed`，ESLint、Ruff、TypeScript 与 Desktop 生产构建通过；真实公众号多轮审稿、重启恢复和真人成品仍待 `E2E-01`。
- Git 历史恢复白名单：见 `../reference/engineering/git-history-recovery.md`。
- Reference Skill 资产审计：23 个营销模块与 13 个内容/编剧/视频模块已逐文件迁入源码；原始快照 diff 为空，110 个 Skill name 全仓无冲突，Skill 文档与打包元数据专项 `7 passed, 1 skipped`。
- 社会反应预演：`social-reaction-simulation-v0.3` 已进入图文/视频草稿工具、不可变 feature snapshot、发布 action、匿名聚类 Receipt、投影链 Retro 与系统静默学习；投影链新增群体机制，禁止具体个人预测、精确概率、可还原逐条评论和对历史群体理论的确定性套用，真实评论 Provider 仍待接。
- 公域学习：`public-content-natural-experiment-v0.3` 已进入 Browser MCP、Evidence post-tool seam、Hermes 时间序列、Receipt 和系统静默学习；满足三条独立作品、每条两次快照后才聚合匿名需求、荣格八维、存在策略和群体机制簇，用户/对话无候选决策入口；真实平台 selector 与跨日规模样本仍待验收。
- 视频管线 Round 2（2026-07-14）：Claude Video `watch` 上游 71 项测试通过并完成本地成片取帧；AI HOT 仅作为候选市场信号源；官方 Remotion Skills 已完成同素材 12 秒竖屏实渲染，视觉组件能力强于本轮 HyperFrames 样例但本机渲染更慢（约 138.4 秒对 55.6 秒），据此冻结“统一 Video IR + 按镜头路由 + FFmpeg 收口”而非二选一方案。Remotion 首次运行下载约 98.4 MB Headless Shell，产品接入前必须固定并预热。
- 视频管线 Round 3（2026-07-14）：`marketing.video.ir.v1`、scene/IR hash、`marketing.video.render_plan.v1` 和 capability fail-closed router 已进入 Hermes；旧 EDL 自动升级再编译回原输入并保持历史幂等键，旧任务可回填派生 IR/plan。当前只启用 FFmpeg；需要 kinetic typography、React/data component、multi-layer 或 designed motion 的 scene 会在批准前阻断。借鉴独立 Video Studio 的镜头局部性、能力证据、effect 前审批和最小返工思想，但未导入其项目 owner 或运行时。
- 视频管线 Round 4（2026-07-14）：代码路径为 `video-renderers/`、`agent/marketing/domains/video_renderers.py` 和 `video_production.py`；固定 Remotion `4.0.488`、HyperFrames `0.7.57`、GSAP `3.14.2`、React `19.2.4`，无运行时 `npx` 或浏览器下载。dev-runtime 已真实渲染两类 360×640/24fps 场景；packaged 组合已把 292 个生产包复制进临时 runtime，并用 Electron Node 24 + staged Chromium 分别真实出片。Hermes 两幕混合测试完成批准、双引擎场景渲染、FFmpeg 规格化/合片、媒体入库、不可变修订和 Receipt，二次渲染两幕缓存命中；抽帧 QA 发现并修复 HyperFrames 短场景转场遮挡。本轮视频 `18 passed, 1 skipped`、相邻链路 `65 passed`、runtime packaging `8 passed`，Ruff/ESLint/Node syntax、固定版本漂移拒绝和 npm production audit 均通过。版本冻结现由 `.npmrc` 精确保存、独立策略文件、源码及安装锁、实际安装包、打包暂存和 Hermes 健康检查共同强制；Remotion 5 只有在用户明确批准、重新审查许可并跑完整渲染回归后才能进入产品。运行时闭包约 647MB，主要为 HyperFrames 硬依赖 `onnxruntime-node`；发行前仍需确认 Remotion 商业许可、干净机安装体积、真人整片审查，并与授权素材/TTS/BGM、发布和指标回收一起跑 `E2E-01`。
- 视频管线 Round 5（2026-07-15）：代码路径为 `agent/marketing/domains/video_production.py`、`media_assets.py`、`tui_gateway/server.py` 和 `apps/desktop/src/app/workbench/video-production-workbench.tsx`。Hermes 新增账号作用域的 bounded production summary 与按需 review projection，只有打开任务时才读取完整 Video IR、镜头、素材、本地可播放路径、成片和 Receipt；跨账号读取返回 404。Desktop 借鉴独立 Video Studio 的阶段/镜头/预览/时间线/素材/审片认知结构，但不导入其角色、Provider 或项目 owner；预览由真实 canvas 驱动，锁定 `9:16`、`16:9`、`1:1`、`4:5`、`3:4` 和自定义比例回归。确认成片写入 ContentAsset 人审回执，局部修改回到 Agent 创建不可变新版本。React 专项 `10 passed`，视频领域 `13 passed, 1 skipped`，Ruff、ESLint、TypeScript、`git diff --check` 与正式 Vite build 通过；本轮结束时仍缺 Provider 授权素材、真实 TTS/BGM、自动媒体 QA 和真人整片审片，自动 QA 在紧随其后的 Round 6 补齐。
- 视频管线 Round 6（2026-07-15）：新增 `agent/marketing/domains/video_quality.py` 原生自动质检 owner。每次成片后用 FFprobe 核验视频/音频流、时长和画布，用 FFmpeg `blackdetect`、`freezedetect`、`loudnorm` 生成带时间段和阈值的结构化检查项，按 `ready/hold/reject` 收敛处置；报告进入最终媒体 metadata、不可变内容版本和 Render Receipt。Desktop 工作台展示技术规格、异常黑场、异常冻结和声音响度，技术拒收不能直接确认成片，旧成片没有报告时明确要求人工审片。视频领域 `15 passed, 1 skipped`，React 专项 `10 passed`，Ruff、ESLint 和 TypeScript 通过；剩余主线为 Provider 授权素材、真实 TTS/BGM 和真人整片审片。
- 视频管线 Round 7 与发布工作台（2026-07-15）：新增 `agent/marketing/providers/materials.py`、`domains/material_sourcing.py`、`domains/production_audio.py` 和 `apps/desktop/src/app/workbench/publishing-workbench.tsx`。素材链用户库优先，Pexels 候选只在显式版权复核后下载，Provider 身份稳定去重且密钥不进入业务投影；TTS 复用 Hermes 已配置 Provider，脚本哈希、一次性批准、真实声音入库和失败恢复均落原生状态机；真实 WAV 旁白和授权 BGM 已通过 FFmpeg 混音、48kHz 音轨及成片 Receipt 集成测试。发布 action、receipt 和 checkpoint 以账号作用域投影给 Desktop，`prepared/executing/unknown/published/failed` 的确认与查询均回到 Agent，不在 Electron 执行平台动作。营销主链组合 `235 passed, 1 skipped`，目标 React `11 passed`，浏览器 MCP `23 passed`，Ruff、ESLint、TypeScript、`git diff --check` 和正式 Vite build 通过。dev-runtime 没有配置真实 Pexels Key，也未在无费用确认时调用可能计费的 `volcengine-speech`；packaged 本轮只验证正式 Desktop 构建，真实在线素材、真人整片认可、平台发布和稳定作品身份反查留到 `E2E-01`。当时记录的 Desktop `55` 个旧失败已在 `REPO-AUDIT-01` 中通过测试隔离、语言状态、DOM 契约和 mock 补齐清零，当前全量为 `1,015/1,015`。
- 视频与素材产品化 Round 8（2026-07-15）：代码路径为 `apps/desktop/src/app/routes.ts`、`chat/sidebar/index.tsx`、`workbench/business-surfaces.tsx`、`video-production-workbench.tsx`、`material-library-view.tsx`、`workbench/index.tsx`、`agent/marketing/domains/media_assets.py` 和 `tui_gateway/server.py`。内容工厂拆出图文/视频原生路由，视频冻结为一张五阶段连续导演台，成片确认前始终可围绕当前镜头自然语言修改；发布与回执归总工作台。素材库展示 Hermes 账号/全局作用域、授权、去重和删除保护，Electron 文件/文件夹选择只提供用户输入，本地导入、受控复制、路径隐藏和复用仍由 Hermes owner 执行；火山云端栏保持未接入空状态。React 定向 `16 passed`，素材库领域 `10 passed`，视频生产与经营闭环 `41 passed, 1 skipped`，TypeScript、目标 ESLint、Ruff、`git diff --check` 和正式 Vite build 通过。当前证据等级为 automated；尚未完成开发机真实文件夹拖入视觉验收、完整真人审片、云端 Provider、平台发布和跨天指标回收，统一留给 `E2E-01`。
- 素材生命周期与视觉收敛 Round 9（2026-07-15）：`MediaAssetRepository` 原生拥有 `temporary/library/cloud` 分层、7 天到期、引用保护、二进制回收和本地库晋升；在线 Provider 素材只有在版权复核后进入临时区，过期候选再次选用会重新物化，不残留失效 ID。`marketing_effect_keep_material` 允许桌面、飞书和微信在同一账号工具作用域内执行明确的“保留这项素材”意图；火山云端 Provider 未连接时仍 fail-closed。Electron 素材中枢真实展示临时/本地数量、到期状态、引用保护、编号素材和保留操作；内容工厂改为有明确差异的图文/视频入口，视频页收敛为炭黑导演台、中央预览与固定目标修改区，不再使用同质白卡后台风格。后端生命周期专项 `18 passed`，React 内容工厂/导演台/素材中枢专项 `14 passed`，Ruff、TypeScript、目标 ESLint 和正式 Desktop build 通过。到期清理由原生素材 owner 在素材读取、搜索和物化生命周期中自动 sweep，不由 Electron 删除文件；当前云端上传、开发机 Electron 真人视觉验收和消息端真实一句话保留仍待 `E2E-01`。
- 导演台结构纠偏 Round 10（2026-07-15）：上一轮“炭黑三栏后台”不符合用户确认的剪辑工作台参考，已撤销该视觉方向。视频创作路由不再套用普通 `ProductPage`，直接进入铺满内容区的暖色导演台：顶部固定项目选择与 `设定 → 分镜 → 动态 → 剪辑 → 成片`，左侧镜头卡读取真实 Video IR 与素材缩略图，中央按播放器 → 真实版本条 → 当前目标自然语言框 → 视频/对白/音乐/字幕四轨时间线连续排列，右侧用角色/场景/道具/声音/素材参考卡承载真实资产，并把阶段确认或成片确认固定在底部。未实现协作能力不放假按钮，版本和参考卡不填演示数据。结构回归与画幅专项 `11 passed`，TypeScript、目标 ESLint 和 Desktop 正式生产构建通过；真实 Electron 视觉验收仍由用户确认。
- 视频设定入口纠偏 Round 11（2026-07-15）：代码路径为 `apps/desktop/src/app/workbench/video-production-workbench.tsx` 与 `business-surfaces.test.tsx`。零生产任务时只显示居中的极简“开始创作”，删除旧空态中的假导演画布、假比例与假镜头区域；点击后留在视频路由进入 `设定`，右栏只保留 `人物 → 声音 → 场景 → 道具` 四个选项，中央整块直接展示当前素材卡片列表，`AI 生成`作为与普通素材同尺寸的第一张卡片。界面不再重复显示库标题、四项 AI 状态、解释文案或无素材黑色预览区。底部文案框支持 Electron 原生文档选择与拖入，附件经 Gateway `file.attach` 进入 Hermes 会话，素材选择、附件引用和文案由隐藏的账号作用域 Agent 任务拆分并创建真实 source asset、production plan 与 prepared Video IR；页面轮询原生 production owner，任务落盘后自动切入连续导演工作台，不再调用 `onNewChat` 跳转对话。目标 React 回归 `12 passed`，TypeScript、目标 ESLint、`git diff --check` 与正式 Desktop build 通过；自动化确认了无假画布、页内设定、素材绑定、附件提交和后台 Agent 路由，真人视觉与真实文档/模型纵切仍留给 `E2E-01`。
- 素材库信息密度纠偏 Round 12（2026-07-15）：删除素材中枢顶部独立的黑色生命周期 Hero、重复导入按钮和展开式导入栏；临时区继续只承载 Agent 下载的 7 天素材，云端区继续保持真实空状态。本地库的素材网格第一张固定为“导入素材”卡片，文件、文件夹、拖入与版权确认全部在该卡完成，后续卡片直接排列真实素材；导入仍经 Electron 原生选择器和 Hermes `marketing.assets.import_paths` owner，成功后刷新本地库。素材库、视频设定与业务表面组合回归 `15 passed`，TypeScript、目标 ESLint、`git diff --check` 与正式 Desktop build 通过。
- 下一次更新本台账时必须写：代码路径、测试、dev-runtime、packaged、human-loop 和仍未完成的风险。
