# 稳定可交付产品总台账（2026-07-04）

> 本台账承接已经冻结的主架构。目标不是继续扩功能，而是把现有能力变成普通用户可以长期、稳定使用的产品。
> 独立视频 Web 项目、微信/飞书、更多平台 OAuth 不计入本轮完成度。

## 当前口径

- 主架构代码：已收口；后续只接受闭环缺口和验收缺陷。
- 桌面可试用版：约 70%。
- 稳定可交付产品：约 65%。
- 自动化通过不等于真人通过；占位 Provider 不等于业务完成。
- 2026-07-07 起以 `12-product-closure-control.md` 为收口总控；本台账只承接稳定交付闭环证据。

## 收口顺序

| 顺序 | ID | 闭环 | 完成口径 | 当前状态 |
|---:|---|---|---|---|
| 1 | DELIV-01 | 登录前起号项目绑定真实账号 | 受众、对标、定位、实验及关联内容在单事务迁移；冲突不覆盖；可安全重试；桌面有自然入口 | ✅ code/build verified；真人对话待验收 |
| 2 | DELIV-02 | 自动发现对标账号 | 按行业/受众/平台生成候选，保存来源与筛选理由；拉取代表样本；用户选择正反例 | 🟡 B站真实主链完成；抖音作者搜索源待接 |
| 3 | DELIV-03 | 生命周期真人 E2E | 普通人对话→受众→对标→定位→首轮实验；双账号、断网、进程重启不丢状态 | 🟡 automated E2E 完成；桌面真人对话待验收 |
| 4 | DELIV-04 | 真实发布 Provider | 用户逐次确认后发布；真实 post ID/receipt；failed/unknown 可查询且不重复发布 | 🟡 ADR 与安全附件、prepare、query 反查完成；最终发布动作待真人校准 |
| 5 | DELIV-05 | 指标回收与复盘 | 1h/6h/24h/3d/7d 拉取；未知不写 0；关联 experiment 和发布 receipt | 🟡 checkpoint/snapshot + 调度器 + 创作者中心作品指标 adapter 完成；真人回放待验收 |
| 6 | DELIV-06 | 策略候选类型化应用 | accepted 候选只能生成定位草案/新实验/待审权重修改；拒绝原因进入偏好；全部可回滚 | ⏳ |
| 7 | DELIV-07 | 长期学习与技能治理 | 重复成功流程候选化、评估、用户启用、版本/回滚；禁止静默扩权 | ⏳ |
| 8 | DELIV-08 | 创作者真实受众 adapter | 官方 API 优先、创作者中心 MCP 补充；来源、时间窗、缺失字段完整 | ⏳；粉丝权限不足时自然延期 |
| 9 | DELIV-09 | 干净机与交付 | 断网首启、崩溃恢复、升级回滚、Developer ID 签名、公证、卸载数据策略 | 🟡 本机构建通过；签名/公证未完成 |

## DELIV-01 完成证据

- `AccountLifecycleService.bind_prospect_project` 使用单一 SQLite 事务迁移项目及生命周期子表。
- 仅迁移明确绑定到该项目实验的内容资产，不卷入同一 prospect scope 的无关草稿。
- 目标账号已有 active 项目时返回冲突，不做自动合并；以 `project_id` 支持网络重试幂等。
- Agent 新增 `marketing_draft_bind_prospect_strategy`；必须由用户明确确认后调用。
- Electron 只开放精确 GET/POST 路径；桌面在真实账号尚未起号且存在待绑定项目时展示“继续沿用”。
- 定向 154 项、全量 1117 项测试、TypeScript、Electron syntax、Vite/PyInstaller/Electron build 通过。

## DELIV-02 当前证据

- 新增确定性 creator-evidence ranking：只有同时带稳定作者 ID 和来源 URL 的内容才能生成候选；热点标题不能冒充账号。
- B站公共热门和关键词搜索均保留作者 ID、作者主页、作品 ID、作品 URL 和公开指标；不需要用户 Cookie。
- 匹配分由 query 命中、目标受众信号、样本深度和来源质量组成，只用于排序；`direct` 关系需要更严格的命中和样本门槛。
- 候选阶段允许保存可追溯样本，但不能写定位观察；用户选中后才成为研究证据，negative 对标仍必须由用户明确选择。
- 重复发现不重复建账号或导入样本；用户已拒绝的候选不会被重新推荐或复活。
- Agent 新增 `marketing_draft_benchmark_discover`，当前共 45 个产品工具。
- 真实网络 smoke：`AI 教育` 返回 20 条 B站作品并聚合出 5 个作者候选；412 风控会明确降级到缓存并报告 source error。
- 定向 160 项、全量 1123 项、TypeScript、Electron syntax、完整桌面构建通过。
- 未完成：抖音创作者中心热点没有第三方作者身份；`www.douyin.com` 公共搜索存在独立登录/验证码边界，未以不稳定 DOM 方案冒充完成。

## 禁止扩项

1. DELIV-01~09 未收口前，不新增第二套真相源、第二套 Agent runtime 或新的主导航业务入口。
2. 视频 Web 只保持 contract 边界，不把视频实现混入本台账。
3. 微信/飞书只是后置消息 surface，不作为 Agent 核心闭环依赖。
4. 每项必须分别记录 code、automated、human、delivery 四级证据。
5. 工作台、新对话、内容工厂、账号管理是当前唯一主体验；发布、趋势、选题、数据中心只作为其中的能力区块或兼容入口。

## DELIV-03 当前证据

- 真实用户库核查：当前一个抖音账号 connected，生命周期业务表为空，`integrity_check=ok`；验收前已做 SQLite online backup 和账号配置备份。
- 新增完整 API E2E：普通人 prospect 受众草案/确认→绑定真实账号→发现两个候选→用户指定 direct 与 negative→每个 5 条样本→五维观察→定位草案/批准→首轮实验→内容资产绑定。
- 候选在“选中”动作中可显式修订 relation；拒绝动作不能夹带 relation 修改，避免静默改写用户判断。
- 同一 E2E 关闭并重新打开 `AgentCoreStore` 后，项目仍处于 `experiment_running`；另一账号读取为 `not_started`，未发生 scope 泄漏。
- 网络不可用时对标发现返回空候选、明确 `source_errors` 和下一动作，不把未知填成结果。
- 双账号 MCP 隔离、checkpoint/crash recovery 与生命周期组合定向 83 项通过。
- 全量 1125 项、TypeScript、Electron syntax、Vite/PyInstaller/Electron build 通过。
- 未完成：真实桌面自然对话和点击体验；Codex 内置浏览器与宿主本地端口不在同一网络命名空间，不能替代 Electron 真机验收。

## DELIV-04 当前证据

- ADR-02 已定版：首版复用现有 account-scoped Playwright MCP；官方 API 保留为长期替换 adapter；未安装且会产生第二套登录的 huimei/CDP 不进入主链。
- schema v18 新增 MediaAttachment；真实用户库 v17→v18 迁移成功，自动备份存在，`integrity_check=ok`。
- 用户通过系统文件选择器导入媒体；App 复制到自己的 `userData/media`，记录大小、MIME 和 SHA-256，用户原文件不被移动或删除。
- Agent/后端任意 `file_path/local_path/media_path` 被发布校验硬拒绝；跨账号、跨资产、非法 MIME、路径穿越、符号链接和 5 GiB 以上文件均被拒绝。
- 内容页支持为视频/图片选择已连接账号，导入和更换视频；已移除不带 receipt 的“手工标记已发布”。
- 全量 1136 项、TypeScript、Electron main/preload syntax 和完整桌面构建通过。
- 当前真实阻塞：已补 `marketing_publish_prepare` 安全探测，只允许点击创作者中心的“发布视频”，不上传、不填表、不提交；需用真人账号拿到上传页脱敏控件标记并验收稳定 DOM。验收前仍不放开 `browser_file_upload`、表单填写或最终发布按钮。
- 2026-07-06 调整：发布闭环优先以图文验收。schema v19 已支持 1–9 张有序图片，桌面端可逐张导入；安全探测同时允许且仅允许“发布图文/发布视频”两个导航入口。自动找图 MCP 仍是调研项，不算运行能力。
- 2026-07-06 续：自动找图首个可运行 Provider 已选 Pexels 官方 API，schema v20 保存来源凭证，应用内可加密配置 Key、搜索、署名预览并受控导入。因本机暂无 `PEXELS_API_KEY`，代码/模拟响应已验收，真人联网搜索尚未完成；不要把它记录成端到端完成。
- 2026-07-07 续：新增发布结果 `query` 反查端点。它从创作者中心作品指标缓存/MCP 刷新结果中按 receipt URL、post_id、标题和资产标题匹配作品；只有匹配到稳定平台 URL 或 post_id 时才写入 verified receipt 并把发布任务置为 `published`，否则返回 `found_unverified`/`not_found`，不冒充成功。Electron API allowlist 已开放该精确路径，前端按钮待接。
- 2026-07-07 续二：Agent 工具层新增 `marketing_publish_query`（L2 受控资源，需审批）。`marketing_read_publishing_tasks` 会对未验证发布任务返回 `recommended_next_action=marketing_publish_query`，让 Agent 能按权限模型处理 unknown outcome，而不是口头猜测发布是否成功。
- 2026-07-07 续三：内容工厂/内容资产 UI 新增“真实发布回执”区，读取 SQL 发布链路，展示 verified/未验证、官方证据、指标 checkpoint 完成度和下一次回收点；用户可点击“反查官方作品”触发 query。独立“发布中心”不再作为主导航入口，旧 `publish` 导航会回落到内容工厂；真实成功口径以 SQL receipt 为准。

## DELIV-05 当前证据

- schema v21 新增 `publishing_metric_checkpoints` 与 `publishing_metric_snapshots`：发布完成后自动生成 1h、6h、24h、3d、7d 五个回收点，并保留每次采集的 task、asset、platform、metrics、provenance、captured_at。
- 旧 `publishing_tasks.next_metrics_at` 继续兼容前端/旧逻辑，但真实计划以 checkpoint 表为准；每采集一个 checkpoint 后自动推进到下一个待采集时间。
- `collect_metrics` 仍兼容旧调用，但内部会写入 `manual_entry` 来源快照；MCP/官方 API/导入报表可显式传 `official_api`、`creator_center_mcp`、`mcp_browser`、`imported_report` 等来源。
- 指标写入拒绝 `null`、`unknown`、`未知`、`n/a` 等占位值；未知字段必须缺省，不能用 0 或字符串补数。
- Agent 工具 `marketing_read_publishing_tasks` 已切到 SQL 发布链，能读取发布回执、指标 checkpoint 和已采集快照；老 JSON 发布任务 API 仅作为前端兼容入口保留。
- 已有学习飞轮保持接通：指标写入后仍触发 blind prediction retro、`review_due` experiment、pending memory candidate 和 strategy candidate，不直接修改策略权重。
- 后台调度器已接入 `list_due_metric_checkpoints`：每轮最多处理一批到期 checkpoint；有明确指标来源时写入 snapshot，没有官方/API/MCP adapter 时只记录 `adapter_missing` 并延后重试，不写假数据。
- 已接首个真实平台 adapter：抖音发布任务到期后，系统先查本账号 `video_metrics` 缓存；若无命中且 MCP 登录可用，则触发 `mcp_sync_account` 刷新创作者中心作品列表，再按 receipt URL/post_id/title 和内容资产标题匹配单条作品。
- 匹配成功后以 `creator_center_mcp` provenance 写入播放、点赞、评论、分享、收藏和 engagement_rate；匹配分、作品标题和 video_metric_id 一并进入 provenance，便于人工复核。
- 兼容 adapter 仍支持发布 receipt 中显式携带的 `metrics` 作为 `imported_report`，用于导入报告/测试；优先级低于真实创作者中心缓存以外的 receipt 显式数据。
- 定向验证：`tests/test_server.py`、`tests/test_publishing.py`、`tests/test_learning_pipeline_integration.py` 共 65 项通过；上一轮发布/生命周期/工具清单组合 104 项通过。
- 未完成：真实账号发布后 1h/6h/24h/3d/7d 跨天回放待验收；官方 API adapter、作品详情页深层留存/转化字段仍待接。
