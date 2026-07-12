# Marketing OS 当前执行台账

> 日期：2026-07-12
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
| State/data owner | 经营项目、受众、证据、内容、预演、回执和学习表已进入 Hermes `state.db`；旧 `agent_core.db` 一次迁移后只读保留 | dev-runtime | 删除兼容路径、中央匿名知识服务尚未实现 |
| Short-video sound intelligence | Playwright MCP 原生短视频/BGM 结构化采集；Sound/Observation/Evidence 入 `state.db`；预演、草稿快照和发布回执携带声音身份 | automated | 真人 selector 验收冻结到账号登录 UI 完成后；再做跨日速度与匹配样本归因 |
| Central knowledge core | 匿名贡献 wire contract、服务端 SQLite 持久化、引用重放/碰撞防护、删除 tombstone、派生包失效、最小群组门槛、稀疏值抑制、时间衰减、Ed25519 签名知识包和 Hermes 验签落库 | automated | HTTP 传输认证、限流、删除授权、密钥轮换、运维与真实多用户规模 |
| New-media operating model | 创作者资产、赛道路线、行为受众、七角色对标图谱、定位、内容系统和可证伪实验进入 Hermes 原生领域 owner；关键版本需用户确认 | automated | 真实赛道研究、对标采集、自然对话真人验收 |
| Four knowledge bases | Platform/Market/Account/Content 四库进入 Hermes `state.db`；赛道库接收真实证据和签名聚合规律；账号知识只接收 Receipt-backed accepted learning；用户/模型写入被拒绝 | automated | 海量采集、规则与市场时效巡检、候选治理 UI |
| Desktop | `apps/desktop` 唯一 UI/Electron | automated build | 干净机安装和真实连续对话 |
| Session/account scope | SessionDB、AccountRegistry、会话级 MCP pool 与 Playwright contextGetter 已贯通；新会话自动获得稳定 `prospect_*` 作用域；MCP 真实登录验证后原子迁移经营事实，旧 session 不变、successor 从首轮绑定真实账号；`accounts.json` 仅一次迁移 | automated | 真人二维码/验证码校准、successor UI 切换、多账号恢复、冲突合并审查与打包浏览器策略 |
| Account lifecycle | Hermes AccountRegistry 已拥有注册、真实登录验证、认证状态、断开、删除、会话绑定和 BrowserContext 租约；MCP owner 自动释放登录窗口，后续以同一持久 profile 后台恢复；删除时清理 profile | automated | 真人多平台登录/退出、Cookie 信号随平台变更的巡检 |
| EvidencePack | `web_extract` 后自动固化 | automated | 多源交叉核验、来源语义、时效治理 |
| Content plan/assets | 三 lane policy、图文质量门、版本资产 | automated | 真实高质量内容与素材生产 |
| Preflight | InfluenceOS + 不可变记录 + draft gate | automated | 真实账号历史校准、发布前版本链 |
| Receipt/Learning store | ReceiptRef、LearningCandidate、PublishAction、MetricCheckpoint 状态机；观察后自动 Retro 和幂等 pending candidate；显式接受后投影 Account KB | automated | 真实平台指标 Provider 与跨天真人数据 |
| Hermes memory/Skill | 原生能力保留，经营写入规则已加入 | automated | 候选治理后投影、重复成功流程沉淀 |
| Publishing/metrics | 原生发布 intent、一次性审批、Provider 插槽、unknown 恢复、回执校验、5 段 checkpoint；Hermes Cron 原生触发指标 Provider，支持领取、延期、崩溃恢复和 unavailable 回执 | automated | 缺实际 L3 发布/指标 Provider 和真人跨天验收 |
| Packaging | 自包含 staging 可构建 | automated | 精简依赖、签名、公证、干净机断网首启 |
| High-end video | 独立项目/合同 | deferred | 不计桌面 v0.1 完成 |

## 内容生产当前边界

内容生产按三种主要交付形态组织，但共享同一条 Hermes 原生经营闭环，不建设三套彼此隔离的产品或状态：

| 交付形态 | 当前原生能力 | 主要缺口 | 当前证据 |
|---|---|---|---|
| `article_soft` 软文 | 账号/实验绑定、EvidencePack、父稿与平台变体、质量门、版本资产、Preflight 和发布资格约束 | 真实账号调性、主张级多源核验、配图版权与真人审稿 | automated |
| `faceless_video` 不露脸素材视频 | 账号/实验绑定、内容计划、素材需求、声音计划、特征快照、Preflight 和内容资产协议 | 授权素材下载与排序、TTS/BGM、EDL 实际填充、真实渲染和人工审片 | automated |
| `premium_human_video` 高级视频 | 独立 `engine/video_core` 合同、火山 adapter/poller、画布、成本 hook、EDL/renderer 命令与 8 角色职责骨架 | 独立 Agent 调度、动态样片审批、真实成片、反馈闭环和真人质量验收 | deferred |

三种形态共同消费账号上下文、当前定位和内容系统、EvidencePack、ContentProductionPolicy、Preflight、ContentAsset、发布 Receipt、指标 checkpoint、Retro 与受治理学习候选。完整草稿和生产状态进入 Hermes `state.db` 的领域 owner；Electron 只展示状态、收集输入和承接人工确认，不拥有生产、素材、浏览器、发布或学习事实。

当前不能宣称“内容制作已完成”。软文与不露脸视频停在自动化合同和草稿能力，高级视频停在独立引擎地基与开发机 provider 校准；三者都缺少从真实账号输入到真人认可成品、发布回执和跨天指标学习的 `human-loop` 证据。高级视频的完整历史方案与校准记录只保存在 [`../deferred/high-end-video-volcengine.md`](../deferred/high-end-video-volcengine.md)，恢复开发前必须先在本台账重新排入顺序。

## 当前唯一主线

### ARCH-01 数据飞轮与学习闭环收口

在 UI 和真人平台验收前，先完成所有不会因界面变化而改变的 owner、状态机和数据合同：

1. 私有事实、预演、发布、指标、复盘、候选和学习投影全部留在 Hermes 原生 owner。
2. 只有用户授权且去标识化的结构贡献可以形成中央 outbox。
3. 中央服务必须独立执行最小群组、稀疏抑制、时间衰减和签名；客户端独立验签。
4. 全局知识只进入先验层，本地 Receipt、用户明确偏好和账号事实拥有更高权重。
5. 完成 metric checkpoint → retro → candidate → memory/strategy/skill projection 后，才冻结底层合同进入 UI。

当前落地：匿名 contribution 不含 user/account/consent/source candidate；中央服务边界会再次拒绝嵌套身份字段、URL/邮箱/电话形态和过度具体值。`CentralKnowledgeStore` 已用独立 SQLite 持久化匿名贡献，保证相同引用同内容幂等、相同引用不同内容拒绝；删除后只保留最小 tombstone，原 payload 物理删除且不可重放。贡献新增或删除会立即使全部派生知识包失效，聚合与重签在同一写事务快照内完成，避免并发把旧结论重新放回服务。聚合内核继续执行 k-anonymity 门槛、类别稀疏抑制和时间衰减；知识包使用 Ed25519 签名，Hermes 验签后写入 `state.db` 并标记为 `global_prior_below_local_receipt`。尚未实现 HTTP 传输认证、删除请求授权、限流和密钥轮换，不能宣称云端已上线。

LOOP-02/03/04 的本地底层已收口：`cron/product_tasks.py` 只提供 Hermes Cron 的非阻塞触发；`agent/marketing/providers/metrics.py` 是平台观察 seam；`PublishingRepository` 原子领取、延期、恢复并结算 checkpoint；`metric_loop.py` 把真实观察写为 Receipt、映射标签、执行 Retro 并生成幂等 pending candidate。单次结果永远不能自动改策略；只有 `AccountLearningGovernance.accept_and_project` 的显式治理动作才能进入 Account KB。

四类知识库已进入 Hermes 原生 owner：平台库维护 source/region/version/valid time 与平台 stylebook；赛道与市场库维护品类、需求、竞争和商业路径的时效规律；内容库维护个体注意力、认知负荷、情绪、信任、身份与群体传播的可观察模型；账号库只允许真实 Receipt 支持且已 accepted 的 LearningCandidate 晋升。`memory_classification` 只是记忆候选分类器，用户/模型陈述不具有知识写权限。内容计划与 Preflight 已读取四库覆盖度及 entry IDs，公式为 `content-production-preflight-v0.5`。

账号经营世界模型已按今天定稿重写，不恢复旧 Electron/FastAPI 生命周期：`AccountStrategyRepository` 原生拥有创作者经营画像、赛道路线假设、多角色对标经营图谱、版本化定位、内容系统和可证伪实验；`AccountLifecycleRepository` 维护项目与行为受众版本。顺序固定为创作者资产 → 赛道路线 → 行为受众 → 对标图谱 → 定位 → 内容系统 → 实验 → Receipt/Retro。没有真实市场证据的路线置信度封顶 `0.45`；对标必须保留多维匹配向量和 EvidenceRecord，粉丝数及不透明总分不能解锁定位。

内容生产已消费经营模型版本：缺少或过期定位/内容系统时，`ContentProductionPolicy` 与 Preflight 进入 `exploratory_draft`，允许用户首日试写和打磨，但 `publish_eligible=false`；`PublishingRepository` 在原生 owner 内拒绝把探索草稿送入发布审批。只有已连接账号、当前定位和当前内容系统同时成立，正式发布闭环才可继续。

实验 ID 链已贯通原生经营事实：运行中 `account_experiment` 可绑定生产计划，所有草稿自动继承 `experiment_id` 并回写实验的 `asset_ids`；发布回执和指标回执由 Receipt owner 根据 plan 自动携带 experiment。后续 Retro 可以从真实结果稳定反查行动前假设，不再依赖标题、时间或模型猜测。

未登录到登录的继承合同已落地：`AccountRegistry.adopt_prospect` 只接受已认证且经营事实为空的目标账号，`SessionDB` 按声明式 scope 表映射在单事务中迁移全部 prospect 事实并写审计记录；重复调用幂等，旧 session 永不重绑。目标账号已有项目、证据、资产或学习事实时立即阻断，禁止静默覆盖。Gateway 已提供 `marketing.account.prospect.adopt`。

真实登录事实也已归回浏览器 owner：改造后的 Playwright MCP 提供只读 `browser_verify_account_login`，直接在当前账号持久 Context 内核验平台域名和第一方登录信号，只返回真假、信号数量和已去掉查询参数/片段的页面位置，Cookie 值永不离开 MCP。Hermes post-tool seam 只信任 `mcp_marketing_browser_browser_verify_account_login` 的真实结果；认证成功后激活 AccountRegistry、尝试安全继承 prospect，并关闭有头登录进程，下一次租约以同一 profile 在后台恢复。目标账号已有经营事实时只标记认证成功、继承进入 `review_required`，绝不覆盖。Desktop 仍只待展示状态和创建 successor 会话。

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
- `ShortVideoSignalRepository` 已能按账号/平台/时间窗计算声音候选，评分覆盖真实观看、跨作品重复、报告使用量、新鲜度、目标匹配和版权状态。
- 视频预演公式升级为 `content-production-preflight-v0.2`，`sound_fit` 成为独立维度；没有声音证据会警告但不会伪造阻断，视频草稿将 `sound_plan` 固化进不可变特征快照，发布回执携带 sound_id。

尚未完成：

- Playwright/MCP 的真实发布动作与作品列表反查 Provider 尚未接入；当前不能宣称能自动发布。
- 仍需一条开发机真人图文发布和重启恢复证据，证据等级目前停在 `automated`。

真人纵切依赖账号登录 UI，当前冻结。底层架构收口后统一实现第一阶段前端：账号登录/切换、内容审核、发布确认、执行状态和 unknown 恢复；前端不承载业务或执行真相。随后再用平台 Skill 验收知乎与短视频真人流程。

浏览器二进制口径：开发机先使用后端检测到的系统 Chrome/Edge 验证链路；产品安装包必须在
“单独受控 Chromium”与“首次明确授权后下载”之间完成体积、离线和签名验证。禁止为了省掉
这个决策而复用 Electron 作为自动化宿主，也禁止运行时静默下载。

完成口径：

- 一个 Hermes session 中：资产 → 审批 → action → verified receipt → Agent 续答。
- 重启后能恢复并读取同一 receipt。
- 重放不会重复发布。
- 无 post ID/URL 时状态只能是 pending/unknown/failed。

## 后续顺序（不得并行扩建）

### FLYWHEEL-02 中央服务工程化

- 聚合与签名内核、服务端持久化、贡献引用重放保护、删除 tombstone 和派生包失效已完成；尚未连接上传/下载接口。
- 下一纵切增加传输认证、删除请求授权、限流和密钥轮换；不得把一个全局密钥打进客户端安装包。
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
- Memory/strategy/Skill 的最终原生投影与用户治理界面仍待后续纵切。

### LOOP-05 真人闭环

- 新用户自然对话建模。
- 一篇知乎/公众号真实内容。
- 一次真实授权发布或可靠人工回执。
- 跨天指标回收与下一轮建议明显改变。

### DELIVERY-01 产品交付

- 产品依赖 allowlist。
- macOS 签名、公证。
- 干净机器无全局 Hermes/Python/Chrome 启动。
- 断网首启和升级回滚。

## 暂停项

- 新页面和工作台装饰。
- 全平台自动发布。
- 微信/飞书体验扩张。
- Windows 正式交付。
- 高阶视频 Provider 和多 Agent 片场。
- 抖音/B站/小红书 BGM 真人页面 selector 验收（等待账号登录 UI）。
- 未校准的流量、完播、互动和 InfluenceOS 对外承诺。

## 当前回归基线

- 营销、Agent、Gateway、审批与账号浏览器隔离组合回归：491 passed。
- 当前营销域、经营世界模型、四类知识、中央持久化、内容生产、原生采证、prospect 继承、真实登录激活、SessionDB 与经营闭环主组合回归：375 passed。
- 改造版 Playwright MCP：15 passed；包含账号租约、profile 持久化/清理、浏览器运行时、登录信号、敏感 URL 清洗和 54 项工具 schema。
- TUI/Gateway 会话既有回归：172 passed；本轮新增 Gateway adoption RPC 已包含在营销组合回归。
- Hermes Cron 调度/作业/产品任务组合回归：302 passed；产品任务无 MetricProvider 时静默，有真实 Provider 时调用指标 owner。
- LOOP-01/02/03/04 发布账本、审批、指标回执、缺失值、延期、崩溃领取恢复、Retro、候选和账号知识治理单文件回归：19 passed。
- Desktop runtime staging：5 passed。
- Git 历史恢复白名单：见 `../reference/engineering/git-history-recovery.md`。
- 下一次更新本台账时必须写：代码路径、测试、dev-runtime、packaged、human-loop 和仍未完成的风险。
