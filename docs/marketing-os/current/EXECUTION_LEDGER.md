# Marketing OS 当前执行台账

> 日期：2026-07-17
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
| Public content natural experiments | Playwright MCP 采集公域作品与聚合反馈；Hermes 保存同作品延迟快照，用内容/受众/需求投影/认知投影/存在策略/社会反应模型解释并生成内容与对标学习候选 | automated | 真实抖音/公众号/小红书 selector 验收、跨日调度、样本治理 UI 与大规模重复证据校准 |
| Central knowledge core | 匿名贡献 wire contract、安全服务与隐私聚合签名；Hermes 原生 Provider 上传 consented outbox、验签安装先验；撤回授权按 pending 本地扣留、submitted 中央删除，处理上传竞态和崩溃恢复 | automated | TLS/反向代理、凭据签发运维、签名私钥轮换演练与真实多用户规模 |
| New-media operating model | 创作者资产、赛道路线、行为受众、七角色对标图谱、定位、内容系统和可证伪实验进入 Hermes 原生领域 owner；关键版本需用户确认 | automated | 真实赛道研究、对标采集、自然对话真人验收 |
| Human/social model | `human-projection-model-v0.2` 将存在固定为不可直接观测/打分的本体前提；创作者与行为受众保存马斯洛需求投影、荣格认知投影和 `preserve/confirm/expand/continue` 存在策略软假设；诊断键、永久人格标签和高于 `0.7` 的伪确定性被原生 owner 拒绝 | automated | 真实长期对话校准、用户纠错体验、跨场景有效期复查 |
| Agent perception layer | `vision_analyze`、`browser_vision`、`video_analyze` 作为 Marketing Agent 的原生底层感知能力；主业务 toolset、受约束媒体代码 worker、默认委派和文件读取引导均已贯通，视频能力在产品运行时不可被渐进披露隐藏 | automated | 真人长视频、多格式/损坏文件、音频转写联动与跨模型视觉一致性验收 |
| Four knowledge bases | Platform/Market/Account/Content 四库进入 Hermes `state.db`；赛道库接收真实证据和签名聚合规律；账号知识只接收 Receipt-backed accepted learning；用户/模型写入被拒绝 | automated | 海量采集、规则与市场时效巡检、候选治理 UI |
| Desktop | `apps/desktop` 唯一 UI/Electron | automated build | 干净机安装和真实连续对话 |
| Session/account scope | SessionDB、AccountRegistry、会话级 MCP pool 与 Playwright contextGetter 已贯通；新会话自动获得稳定 `prospect_*` 作用域；MCP 真实登录验证后原子迁移经营事实，旧 session 不变、successor 从首轮绑定真实账号；`accounts.json` 仅一次迁移 | automated | 真人二维码/验证码校准、successor UI 切换、多账号恢复、冲突合并审查与打包浏览器策略 |
| Account lifecycle | Hermes AccountRegistry 已拥有注册、真实登录验证、认证状态、断开、删除、会话绑定和 BrowserContext 租约；MCP owner 自动释放登录窗口，后续以同一持久 profile 后台恢复；删除时清理 profile | automated | 真人多平台登录/退出、Cookie 信号随平台变更的巡检 |
| Owned account diagnosis | 微信公众号已验证最近 9 篇逐篇内容分析指标；抖音已验证公开 3 条、私密 1 条的作品口径；Hermes 将作品、指标、EvidenceRecord、透明执行基线和数据缺口按账号写入 `state.db`；Desktop 只读展示 | dev-runtime | 新空 profile 真人扫码、多账号恢复、分页完整性巡检；评分继续区分执行基线、内容解释和受众反馈 |
| EvidencePack | `web_extract` 后自动固化 | automated | 多源交叉核验、来源语义、时效治理 |
| Content plan/assets | 图文与不露脸素材视频双 lane policy、图文质量门、不可变版本资产、显式真人审核回执与发布门；计划固化结构化受众模型 | automated | 真实高质量内容与素材生产；公众号成品和重启后审核状态待最终 human-loop |
| Preflight | InfluenceOS + 不可变记录 + draft gate；草稿自动把 Preflight 多维结果、匿名评论人群/主题/立场、需求投影、认知投影、存在策略、个体注意、群体扩散、平台分发和商业行动固化为 hash-bound `social_system_simulation` | automated | 真实账号历史校准、评论聚类 Provider、平台竞争/时段/投流先验 |
| Receipt/Learning store | ReceiptRef、LearningCandidate、PublishAction、MetricCheckpoint 状态机；观察后自动执行投影机制链对账和分层 causal reflection，明确区分观察、预测误差、干预身份、反事实不可识别与混杂因素；显式接受后才投影 Account KB | automated | 真实平台指标 Provider、匹配变体与跨天真人数据 |
| Hermes memory/Skill | 1 个产品运行 Skill、23 个原始营销 playbook 和 13 个内容/编剧/视频参考 Skill 已纳入源码；经营写入规则已加入 | automated | 候选治理 UI、重复成功流程沉淀；参考 Skill 升级必须逐项审查 |
| Publishing/metrics | 原生发布 intent、一次性审批、Provider 插槽、unknown 恢复、回执校验、5 段 checkpoint；Hermes Cron 原生触发指标 Provider，支持领取、延期、崩溃恢复和 unavailable 回执 | automated | 缺实际 L3 发布/指标 Provider 和真人跨天验收 |
| Packaging | 自包含 Hermes/Python/Chromium staging 可构建；固定版本 Remotion/HyperFrames 已进入产品 runtime，并在 staged Electron Node + Chromium 中真实出片 | packaged | 正式安装包签名、公证、干净机断网首启与升级回滚 |
| High-end video | 已完整迁入独立 `/Users/yangyucheng/projects/video-studio`；Marketing OS 仅保留边界指针，不保留引擎、运行时、角色、Provider 或内部生产 lane | external product | 不计 Marketing OS 桌面完成度；未来接入必须等待独立产品稳定 Port/API |

## 内容生产当前边界

Marketing OS 内容生产只保留两种内部交付形态，共享同一条 Hermes 原生经营闭环：

| 交付形态 | 当前原生能力 | 主要缺口 | 当前证据 |
|---|---|---|---|
| `article_soft` 软文 | 账号/实验绑定、EvidencePack、父稿与平台变体、质量门、版本资产、Preflight 和发布资格约束 | 真实账号调性、主张级多源核验、配图版权与真人审稿 | automated |
| `faceless_video` 不露脸素材视频 | 账号/实验绑定、内容计划、素材需求、声音计划、特征快照、Preflight、不可变 Video IR/EDL、scene/IR/render-plan hash、能力路由、显式渲染批准、固定版本 Remotion/HyperFrames 镜头执行、真实 FFmpeg 规格化与合成、场景缓存、派生最终素材、不可变成品版本、失败重试与 Render Receipt；黑场/冻结/响度/技术规格自动 QA；用户素材优先的 Provider 中立检索、Pexels 官方视频适配、来源/许可证审查后下载与稳定身份去重；一次性批准后复用 Hermes TTS 并把真实输出导入素材库；授权 BGM 与旁白已通过真实 FFmpeg 混音和音轨 QA；原生视频理解支持 direct/sampled/auto；Desktop 已有真实 production/镜头/素材/时间线/成片/回执工作台和人工审片入口 | 配置真实 Pexels Key 后的在线下载、当前 Volcengine TTS 的一次性费用授权、真人认可整片 | automated（渲染器已达 packaged） |
两种内部形态共同消费账号上下文、当前定位和内容系统、EvidencePack、ContentProductionPolicy、Preflight、ContentAsset、发布 Receipt、指标 checkpoint、Retro 与受治理学习候选。完整草稿和生产状态进入 Hermes `state.db` 的领域 owner；Electron 只展示状态、收集输入和承接人工确认，不拥有生产、素材、浏览器、发布或学习事实。

当前不能宣称“内容制作已完成”。不露脸视频自动化链已证明用户/Provider 素材候选、许可证确认、TTS 意图批准、真实音频导入、BGM 混音、渲染、QA、版本与回执可以贯通；但没有擅自调用当前可能计费的 `volcengine-speech`，也没有在未配置 Pexels Key 时伪造在线下载。仍缺真实账号输入、在线 Provider、真人认可成品、发布回执和跨天指标学习的 `human-loop` 证据。高级视频是独立产品，不属于本台账完成范围；迁移指针见 [`../deferred/high-end-video-volcengine.md`](../deferred/high-end-video-volcengine.md)。

## 参考 Skill 迁移结论

- 用户提供的 `marketing-skills` `0.1.2` 原始快照共 23 个模块，已完整保存在 `skills/marketing-playbooks/`，不再依赖 WorkBuddy 本机目录。
- 此前只存在于已安装运行时、没有进入仓库的 13 个模块已补入源码：内容创作 4 个、编剧 5 个、视频制作 4 个。
- Skill 不等于 Tool。方法论、清单和创作框架保留为 Skill；账号事实、浏览器、采集、草稿、发布、指标、回执和学习继续由 Hermes 原生工具及领域 owner 承担。
- 逐项状态、功能重叠和产品边界见 [`../reference/skills/reference-skill-inventory.md`](../reference/skills/reference-skill-inventory.md)。

## 当前唯一主线

### FACELESS-01 不露脸素材视频成品

`CONTENT-UI-01` 的自动化纵切已经完成：Electron 读取 bounded asset summary，只有点开单篇时才请求全文；审核页展示母稿、平台变体、EvidencePack、质量门、视觉版权要求和匿名评论反应场。真人确认与修改意见通过 Gateway 写入 Hermes `ContentAssetRepository`，发布 owner 拒绝未确认的当前版本；提出修改只把明确意见交回 Agent，由原生创作工具创建 `revision_of` 新版本，不在 Electron 覆盖正文。旧数据库启动后会自动补齐人审字段，既有资产默认 `pending`。

按用户决定，真实公众号成品、多轮修改和重启恢复的 `human-loop` 不在此时单独打断主线，保留到其它纵切完成后的 `E2E-01` 统一执行；因此 `CONTENT-UI-01` 证据等级是 `automated`，不能宣称真人闭环完成。

`FACELESS-01` 自动化纵切已收口，当前按既定顺序推进 `PUBLISH-01`：

1. 复用 Hermes 已有 `faceless_video` 内容计划、素材需求、声音计划、特征快照、Preflight 与 ContentAsset，不另建 Electron/外围 owner。
2. 接入有来源和授权状态的素材下载与排序；来源证明进入原生素材库和不可变版本。
3. 已完成原生不可变 Video IR/EDL、稳定 scene hash、能力 render plan、显式批准、固定版本 Remotion/HyperFrames scene executor、真实 FFmpeg 规格化/合片、场景缓存、派生最终素材、不可变成品版本、失败重试、hash-bound Render Receipt，以及黑场/冻结/响度/技术规格自动 QA；原生 `video_analyze` 已从视频管线专项工具提升为 Agent 底层感知能力，支持小视频直读、长视频/时间段采样和带时间戳视觉证据。
4. 已完成用户素材优先的 Provider 中立候选、Pexels 官方 API 适配、来源/作者/许可证快照、显式版权审查后下载和稳定 Provider 身份去重；API Key 不进入候选、回执或业务库。
5. 已完成 TTS `prepared → approved → running → completed/failed` 状态机，复用用户配置的 Hermes TTS Provider，真实输出进入声音素材及脚本哈希回执；授权 BGM 与旁白已通过实际 FFmpeg 混音和 48kHz 音轨 QA。当前 Provider 为可能计费的 `volcengine-speech`，未获得本次费用确认前不执行真人调用。
6. Electron 视频工作台已按真实 production 投影展示项目、镜头、素材授权、横竖/方屏及自定义画幅、执行器、时间线、声音/字幕轨、渲染状态、最终视频和 Render Receipt；确认成片或提出局部修改均写回原生审核 owner，修改继续生成不可变新版本。Electron 不拥有生产状态或执行。
7. 自动化纵切完成，进入 `PUBLISH-01 → METRIC-01 → LEARNING-UI-01 → DELIVERY-01 → E2E-01`。

完成口径：账号上下文 → 有授权来源的素材与声音 → 实际 EDL/渲染 → 可恢复版本 → 人工审片入口；最终真人认可仍在 `E2E-01` 统一验收。

### ARCH-01 数据飞轮与学习闭环收口（本地底层完成，部署项后置）

在 UI 和真人平台验收前，先完成所有不会因界面变化而改变的 owner、状态机和数据合同：

1. 私有事实、预演、发布、指标、复盘、候选和学习投影全部留在 Hermes 原生 owner。
2. 只有用户授权且去标识化的结构贡献可以形成中央 outbox。
3. 中央服务必须独立执行最小群组、稀疏抑制、时间衰减和签名；客户端独立验签。
4. 全局知识只进入先验层，本地 Receipt、用户明确偏好和账号事实拥有更高权重。
5. 完成 metric checkpoint → retro → candidate → memory/strategy/skill projection 后，才冻结底层合同进入 UI。

当前落地：匿名 contribution 不含 user/account/consent/source candidate；中央服务边界会再次拒绝嵌套身份字段、URL/邮箱/电话形态和过度具体值。`CentralKnowledgeStore` 已用独立 SQLite 持久化匿名贡献，保证相同引用同内容幂等、相同引用不同内容拒绝；删除后只保留最小 tombstone，原 payload 物理删除且不可重放。贡献新增或删除会立即使全部派生知识包失效，聚合与重签在同一写事务快照内完成，避免并发把旧结论重新放回服务。`services/marketing_knowledge/api.py` 已提供认证 HTTP surface：每个安装实例使用独立高熵 token，服务端只存哈希；时间戳、一次性 request nonce 和 SQLite 窗口计数分别阻断过期重放和突发滥用。贡献归属不保存 client ID，而保存按 `client + contribution` 计算的不可关联 HMAC proof；只有原认证客户端能删除，删除 key-ring 支持新旧密钥平滑轮换并在成功访问时迁移 proof。客户端 token 也可独立轮换或吊销，凭据签发只允许离线管理，不存在公共注册接口。聚合内核继续执行 k-anonymity 门槛、类别稀疏抑制和时间衰减；知识包使用 Ed25519 签名。`agent/marketing/providers/knowledge_sync.py` 作为 Hermes 原生同步 owner：只导出 accepted learning + 显式 consent 生成的 outbox；上传采用 `pending → uploading → submitted` claim，陈旧 claim 可恢复，服务已收件但本地崩溃靠 contribution_ref 幂等补结算；下载 pack 必须先通过内置信任 key-ring 验签才进入 `state.db` 和四库先验。用户撤回未上传贡献时立即 `withheld` 且清空本地 aggregate payload；已经或可能上传的贡献进入 `delete_pending`，中央返回删除成功或 404 后才结算 `deleted`。撤回与 in-flight upload 并发时，submit settlement 不得覆盖 delete_pending；新 consent_ref 会创建新贡献而非复活旧记录。Gateway 只在 `confirmed=true` 时调用 owner，Electron 未来只展示并收集确认。Cron 只非阻塞触发，同步服务 URL、安装级 client token 和公钥 ring 即使在 multiplex 模式也不属于任何用户 profile。尚未完成 TLS 部署、凭据签发服务和真实多租户压测，不能宣称云端已上线。

LOOP-02/03/04 的本地底层已收口：`cron/product_tasks.py` 只提供 Hermes Cron 的非阻塞触发；`agent/marketing/providers/metrics.py` 是平台观察 seam；`PublishingRepository` 原子领取、延期、恢复并结算 checkpoint；`metric_loop.py` 把真实观察写为 Receipt、映射标签、执行 Retro 并生成幂等 pending candidate。单次结果永远不能自动改策略；只有 `AccountLearningGovernance.accept_and_project` 的显式治理动作才能进入 Account KB。

四类知识库已进入 Hermes 原生 owner：平台库维护 source/region/version/valid time 与平台 stylebook；赛道与市场库维护品类、需求、竞争和商业路径的时效规律；内容库维护个体注意力、认知负荷、情绪、信任、身份与群体传播的可观察模型；账号库只允许真实 Receipt 支持且已 accepted 的 LearningCandidate 晋升。`memory_classification` 只是记忆候选分类器，用户/模型陈述不具有知识写权限。内容计划与 Preflight 已读取四库覆盖度及 entry IDs，公式为 `content-production-preflight-v0.6`。

2026-07-15 社会实验闭环审计与本体校正形成三层合同。第一，`human-projection-model-v0.2` 明确“存在”只作为不可直接观测和打分的哲学根前提；马斯洛需求、荣格认知和存在策略才是可证伪投影。第二，每版草稿自动固化 `social-system-simulation-v0.2`，沿需求投影 → 认知投影 → 存在策略 → 可观察行为机制链覆盖个体注意、群体扩散、平台分发和商业行动。第三，指标与匿名评论回执生成 `causal-reflection-v0.2`，明确记录预测误差、实验身份、反事实不可识别和潜在混杂因素。单条作品只允许形成相关性反思，只有预注册变体、稳定回执、可比时间窗与重复/匹配样本才具备升级干预判断的资格。

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
5. `LEARNING-UI-01`：候选证据、接受/拒绝、最终 Skill/策略 diff 与二次确认。
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

### LEARNING-UI-01 候选治理

- Electron 展示 Retro、支持/反例、候选类型和最终 diff，只收集接受、拒绝、理由与二次确认。
- 单次结果不得自动改策略、权重、Account KB 或 Skill。

### FLYWHEEL-02 中央服务工程化

- 聚合签名、持久化、安全 HTTP、Hermes 原生同步和 consent 撤回/删除 outbox 已贯通；上传、撤回和崩溃竞态均由本地状态机与中央幂等合同处理；服务没有公共 provisioning endpoint。
- 架构内下一步只剩真实部署凭据签发、TLS/密钥轮换演练与多租户隐私压测；每个安装实例领取独立凭据，不得把一个全局密钥打进客户端安装包。
- 真实部署前用合成多租户数据做隐私攻击与稀疏重识别测试。

### LOOP-02 指标回收（底层完成，真实 Provider 待接）

- 到期 checkpoint 由 Hermes cron 扫描。
- 未知指标留空，不写 0。
- 原始平台字段保留，另映射 attention/retention/trust/action/fit/risk 标签。
- checkpoint 使用 `pending → collecting → observed → settled`；暂未出数回到 pending 并设置下一次尝试时间，永久不可用生成事实回执，进程中断的 collecting 可恢复。
- Cron 只触发，不解析平台和不写业务解释；只有已注册真实 MetricProvider 时才运行产品任务。

### LOOP-03 自动复盘（底层完成）

- `content_retro` 比较发布前 prediction 与真实 metric receipt。
- 输出偏差、缺失字段、替代解释，不自动宣布因果。
- 生成 pending memory/strategy/weight/skill candidate。
- 没有校准预测时明确记录 `prediction_unavailable`，只学习真实标签，禁止把全零范围伪装成预测偏差。
- `source_key=metric-retro:{checkpoint_id}` 保证崩溃恢复和重放不重复创建候选。

### LOOP-04 学习投影（治理合同完成）

- 用户明确偏好进入 USER/MEMORY。
- 账号策略候选进入版本化 account strategy。
- 多次成功并有失败恢复的流程进入 Skill candidate。
- 权重候选必须有至少三个支持样本并通过历史回放。
- 单次 Retro 只生成 pending candidate；显式接受后才允许投影 Account KB。自动接受、自动改永久权重和把用户陈述写成账号真相仍被禁止。
- 已打通 `memory → Account KB` 与 `weight → 历史回放 → pending strategy → 二次确认 → 版本化 account influence calibration`；校准按账号隔离、幂等、可被后续 Preflight 与指标复盘读取，单次结果不能绕过两层门禁。
- Gateway 已提供账号作用域的候选列表与显式决策 RPC；Electron 后续只展示候选并收集 `confirmed + reason`，不拥有学习或策略状态。
- 用户稳定偏好继续由 Hermes 原生 USER/MEMORY owner 管理，不把账号发布结果污染成全局个人记忆。
- 发布恢复 Skill 已完成真实证据门：同一平台/Provider 至少三组不同 action 都必须存在 `publish_unknown → 作品列表反查 → verified publish` 双回执，才能生成 pending Skill candidate；用户确认后才由 Hermes 原生 Skill owner 写入或进入原生 write-approval，重复确认幂等且保留 agent-created provenance。其他流程类型仍需各自的失败/恢复事实 owner，禁止拿最终成功行反推过程。
- 学习候选治理 UI 仍待前端纵切；Electron 只展示候选、证据摘要和最终 Skill diff，并收集确认。

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
- 一级导航改为工作台、新对话、内容工厂、素材库、账号管理和托管；内容工厂下固定图文创作与视频创作两个子入口。Skills、MCP、消息通道、Cron 等仍由 Hermes 原生 owner 管理，但不再以开发者概念占据用户一级入口。
- 工作台读取 `AccountContextRepository`、账号平台统计、内容资产和 learning candidate；只展示真实快照，缺数据时明确等待回执，不生成装饰性假曲线。
- 内容工厂首页只负责选择创作方式和查看最近内容；图文审核与视频生产进入独立原生路由。视频页使用同一张连续导演工作台完成 `设定 → 分镜 → 动态 → 剪辑 → 成片`，左侧对象/镜头、中央主预览与当前目标自然语言修改框、右侧角色/场景/道具/声音/素材职责固定，剪辑和成片阶段在中央展开多轨时间线。纯素材视频复用同一套工作台；高阶视频已迁出，不保留无法执行的假入口。
- 素材库把 Hermes 既有统一资产 owner 投影为本地素材与云端素材两栏。本地素材支持 Electron 原生文件/文件夹选择和拖入，只有显式版权确认后才由 Gateway 交给 `MediaAssetRepository` 复制入受控库；账号/全局作用域、SHA-256 去重、来源授权、引用删除保护和成片回执继承均有产品说明，原始绝对路径不进入业务投影。火山云端素材当前保持诚实空状态，未接 Provider、未放假数据、不会产生调用费用。
- 发布 action、稳定作品身份、unknown 恢复和指标回执从内容工厂移到总工作台；视频成片必须先在导演工作台完整审片并写入原生审核 owner，之后才由 Agent 准备发布。Electron 只展示状态和收集意图，不执行平台动作。
- 会话侧栏过滤 `<marketing-turn-context>` 等内部上下文，不再把系统会话泄漏为历史对话；外部消息渠道线程不再混入桌面历史列表。
- 移除空置顶区、开发状态栏、面板换位、触感和快捷键等开发者标题栏入口；设置和左右栏折叠保留。
- 视觉品牌改为 Marketing OS 珊瑚色体系，Hermes 主题能力继续提供明暗模式，但不能覆盖产品主品牌色。
- 新安装默认简体中文，语言切换能力保留；默认值同时修改 Hermes 原生配置和 Desktop i18n owner。
- 当前验证：Desktop TypeScript typecheck、目标 ESLint、Ruff、`git diff --check` 和正式 Vite build 通过；新导航/导演台/素材库/回执边界 React 定向 `16 passed`，素材库领域 `10 passed`，视频生产与经营闭环组合 `41 passed, 1 skipped`。这些是 automated 证据，不替代真人视觉、真实素材文件夹和整片审查。
- 仍需真人视觉验收工作台、内容工厂、账号管理、托管与新对话五个入口；后续只根据真实使用反馈打磨信息密度，不恢复 Hermes 开发者控制台式信息架构。

### REPO-AUDIT-01 台账、Git、UI 与边界收敛（2026-07-17）

- 审计起点工作树共有 183 个文件条目：93 个 tracked change、90 个 untracked file，其中 61 个路径归 `apps/`、28 个归 `agent/`、20 个归 `tests/`。它们跨后端领域、Gateway/MCP、Desktop、视频 renderer、Skill 与文档，不是可安全丢弃的单一 UI 草稿；禁止用 reset/checkout 清理。
- 当前产品源码分支为 `codex/marketing-os-product-source`，HEAD `4a5d2ea84`，没有 upstream。它的根提交是 `21d80ca6`；本地 `main` 只有 7 个旧产品提交，根提交 `e550ec2d`、HEAD `a65068f82`。两者没有 merge-base，`7/13520` 之类 ahead/behind 数字没有合并语义；禁止 merge、rebase 或批量 cherry-pick。Git 收口顺序固定为：先为当前产品历史建立受控远端并推送备份，再归档旧 `main`，最后通过明确的 ref 替换把产品历史设为默认分支；未完成远端备份前不改写 `main`。
- 当前唯一 remote 是上游代码源 `hermes-upstream`，不是 Marketing OS 产品备份目标。本轮只允许在当前产品分支建立本地 checkpoint；在用户提供或确认产品 remote 前不 push，也不把产品历史误推到上游 remote。
- Desktop 测试入口已限定为 `src/**/*.{test,spec}.{ts,tsx}`，不再把 Electron `node:test`、脚本测试和 `build/product-runtime` 暂存副本误当 Vitest；Node 26 的全局 Storage accessor 由测试专用内存实现隔离。产品新安装仍默认中文，但 Python 与继承的 Desktop 行为测试在模块加载前固定英文，避免开发者本机语言污染基线。
- `@assistant-ui/store` 的安装树曾漂移为 `0.2.19`，与锁定的 `@assistant-ui/tap 0.5.16` 不兼容；根目录 `npm ci` 已恢复 lock/override 指定的 `0.2.13`，`npm ls`、正式构建与类型检查恢复通过。不得用工作区内临时 `npm install` 改写这组版本。
- Gateway 曾重复注册 `marketing.account.context`，后声明会静默覆盖前 handler。重复项已删除，RPC 注册器现在遇到任何重复方法名立即失败；当前 143 个方法名全部唯一。Desktop 使用 21 个 `marketing.*` RPC，Gateway 暴露 31 个；其余入口未完成消息渠道/未来 UI/兼容调用方审计前不删除。
- Electron 经营任务卡已从持久 `localStorage` 改为只存在内存的后端会话展示投影，重启后不再出现无法对应后端 owner 的“幽灵任务”。真正任务、资产、账号、发布和学习状态继续由 Hermes 原生 owner 持久化。
- 当前最主要耦合债务不是 Repository 泄漏，而是任务协议泄漏：Desktop 三处重复执行 `marketing.operation.prepare → session.create → prompt.submit`，再轮询通用 `session.status` 并把 `idle` 推断为经营任务完成。下一轮只能在 Hermes 原生 task/operation owner 增加原子 start/status projection，随后删除 UI 编排；不得用新的 Electron Store 掩盖。
- UI 结构债务集中在 `desktop-controller.tsx`（约 1.6k 行）、`growth-dashboard.tsx`（约 1.2k 行）和 `video-production-workbench.tsx`（约 2.2k 行）。拆分目标是 typed query/command projection、任务启动和纯视图，不是按视觉卡片继续横向造 Store。完整边界记录在 [`NATIVE_ARCHITECTURE.md`](NATIVE_ARCHITECTURE.md)。
- Python 首轮全量回归通过 `36,267` 项并暴露 `44` 项失败；失败全部归入跨平台路径/进程、systemd 能力、宿主代理污染、本机语言、测试替身漂移和三项 Web Provider 旧契约，没有发现营销 Repository 被 UI 反向依赖。每组修复均已定向回归通过；本轮没有为伪造“一次性全绿”再重复运行约 52 分钟的全量扫描。`scripts/run_tests.sh` 现固定英文测试语言，并为 loopback 设置 `NO_PROXY/no_proxy`，避免 macOS 系统代理劫持本地测试服务。
- Desktop 继承测试债务已清零：Vitest `136` 个文件、`1,015/1,015` 通过；Electron/packaging `node:test` 为 `265 passed, 1 skipped`，跳过项是 Windows junction 平台限定。浏览器 MCP `23/23` 通过。Ruff、TypeScript、ESLint、`git diff --check`、正式 Vite production build 与产物断言均通过；npm 锁定树一致，root audit 为 `0 vulnerabilities`。当前 renderer 单 chunk 约 `26.1 MB`，仍有超过 `25 MB` 的构建警告，属于后续 bundle 拆分风险，不影响本轮构建成功。
- 本轮 packaged 证据只到正式 renderer build、runtime staging 测试和产物存在性断言；没有生成签名安装包、没有在干净机安装，也没有替代真人 UI/账号/发布闭环，因此证据等级仍是 `automated build`，不能写成 `human-loop`。

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
- 社会反应预演：`social-reaction-simulation-v0.2` 已进入图文/视频草稿工具、不可变 feature snapshot、发布 action、匿名聚类 Receipt、投影链 Retro、pending learning candidate 与内容审核 UI；界面明确标记匿名人群情景和合成评论样例，禁止具体个人预测、精确概率和可还原逐条评论，真实评论 Provider 仍待接。
- 公域学习：`public-content-natural-experiment-v0.2` 已进入 Browser MCP、Evidence post-tool seam、Hermes 时间序列、Receipt 和双学习候选；公域聚类与自有内容共用需求投影、认知投影和存在策略合同，真实平台 selector、跨日复测任务和治理 UI 仍待接。
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
