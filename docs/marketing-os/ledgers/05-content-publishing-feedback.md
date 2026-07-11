# 内容资产、发布与复盘执行台账

## 完成目标

从选题、脚本、素材、版本、审批、发布到指标回收和复盘形成真实闭环；任何平台副作用都以平台 receipt/post ID 为准。

## 任务清单

| ID | 任务 | 具体执行 | 完成证据 | 状态 |
|---|---|---|---|---|
| PUB-01 | ContentAsset 模型 | topic/hook/script/title/cover/media/platform variant/version/parent/status/account/project | ✅ code done：加 `parent_id`(FK)+`topic`+`hook` 列 + 迁移 + `create_content_asset` 版本链(parent→version+1, 不存在→NULL)；4 测试通过 |
| PUB-02 | Artifact 血缘 | 每个内容版本关联 evidence、memory、prompt/model、用户修改和生成时间 | ✅ code done：`create_content_asset` 新增 `memory_ids`/`evidence_ids`/`prompt_model`→存入 `content_json._provenance_*` |
| PUB-03 | 平台变体 | 同一创意按抖音/B站/小红书等生成独立版本；不覆盖原稿 | ✅ code done：`variants.py` — `create_variants`(platform validate+dedup+parent link) + `is_variant_of`；5 测试通过 |
| PUB-04 | 发布 provider contract | prepare/validate/publish/query/delete/metrics；provider 不泄露 Cookie | ✅ code done：`publish_contract.py` — `PublishProvider` Protocol + `ValidationResult` + `validate_publish_asset`(title/platform/status/content checks) |
| PUB-05 | 抖音发布可行性 ADR | 官方接口、创作者中心 MCP、人工确认三路比较；账号类型、审核、风控和条款 | ✅ ADR-02 accepted（2026-07-04）：首版复用 account-scoped Playwright MCP；用户导入安全附件，逐次 approval 后最终发布，作品列表反查真实 receipt。官方 API 为长期 adapter；未安装的 huimei/CDP 不进入主链 |
| PUB-06 | 发布前校验 | 账号、素材、时长、格式、标题、合规、授权 scope、计划时间 | 🟡 基础校验已有；ADR-02 新增 PUB-06A：不得接受 Agent 任意 file_path，需用户文件选择器导入 MediaAttachment 并校验 scope/hash |
| PUB-06A | 安全媒体附件 | 用户文件选择器→App 管理目录→attachment_id/hash；替换、删除、跨账号隔离 | ✅ code/build verified（2026-07-04）：schema v18；Electron 文件选择器只接受 mp4/mov/webm/jpg/jpeg/png/webp，拒绝符号链接和越界/超限文件，复制到 userData/media 并记录 SHA-256；业务层隐藏 storage_key，raw file_path 发布硬拒绝；替换清旧副本，删除资产先清附件。内容页可选择账号并导入/更换视频，移除“手工标记已发布”假入口。定向 156 项、全量 1136 项和完整构建通过；真人选择大文件/取消/替换待验收 |
| PUB-06B | 发布页安全探测 | 同账号 Playwright MCP 会话只允许从创作者中心点击一次“发布视频”并读取上传页可见控件；禁止选择文件、填写表单和点击“发布/确认发布” | ✅ code/build verified（2026-07-06）：新增 `marketing_publish_prepare` 独立受控能力、参数级 click allowlist、`publish-prepare` API 并接入 Electron 发布入口；只返回 `ready/blocked` 与脱敏控件标记，不返回完整页面快照；134 项相关测试与完整构建通过，真人页面结构待验收；全量 pytest 巡检在约 18% 后未退出，已终止重复巡检进程，需单独定位测试基础设施卡点 |
| PUB-06C | 图文优先验证 | 视频素材管道未收口前，先用抖音图文验证“资产→审批→上传→确认→回执”闭环；一个图文资产支持 1–9 张有序图片 | 🟡 foundation verified（2026-07-06）：schema v19 移除单附件限制；视频仍为单文件替换，图文支持逐张添加、指定位置替换、账号隔离与统一清理；Creator UI 展示图片集合；`marketing_publish_prepare` 可只读探测“发布图文”上传页，仍禁止上传/填表/最终发布；168 项相关测试与 TypeScript/语法检查通过。待接素材搜索 Provider、真人 DOM 验收和受控上传 |
| PUB-06D | 自动找图与来源凭证 | 从授权素材源搜索候选图，保留 provider、source URL、作者、许可证、检索词、下载时间和文件 hash；用户/Agent 选择后才进入图文资产 | 🟡 Pexels Provider code verified（2026-07-06）：直接对接官方 REST API，不依赖未经审计的第三方 MCP；Creator 内搜索竖图、展示摄影师与 Pexels 回链，用户选图后由 Electron 仅从 `images.pexels.com` 下载，限制 25MB/图片 MIME/30s，SHA-256 后进入 App 托管目录；schema v20 将 provider/source/author/license 随附件保存；API Key 通过 Electron safeStorage 加密写入并重启本地后端，前端不可回读。196 项相关测试、TS/JS 检查通过；当前设备尚未配置 Key，真实搜索/下载待用户 Key 验收；Pixabay/Unsplash 仍为后续 Provider，不算已接入 |
| PUB-07 | 真实 L3 effect | intent→审批/grant→执行→receipt；unknown outcome 查询后再决定重试 | 真人发布测试内容并取得 post ID | ⏳ |
| PUB-08 | 排期与队列 | timezone、休眠/离线、重试、取消、错过窗口；借鉴 Postiz 但自有 contract | 时间旅行和重启测试 | ⏳ |
| PUB-09 | 发布状态同步 | local draft/scheduled/publishing/published/failed/deleted 与平台事实对齐 | 🟡 query + UI foundation verified（2026-07-07）：新增 SQL 发布任务 query 反查；按 creator-center 作品 URL/post_id/title/资产标题匹配；只有稳定 URL/post_id 才写 verified receipt 并转 published，标题命中但无稳定 ID 返回 found_unverified。Agent 新增 L2 `marketing_publish_query`，发布任务读取会提示 recommended_next_action；内容工厂已展示真实回执、官方证据、checkpoint 进度和反查按钮，独立发布中心不再作为主导航入口。最终发布后真人回放待验收 |
| PUB-10 | 指标窗口 | 发布后 1h/6h/24h/3d/7d 拉取播放、留存、互动、关注、转化和评论质量 | 🟡 creator-center adapter wired（2026-07-07）：发布完成自动生成 1h/6h/24h/3d/7d checkpoint；后台调度器扫描到期 checkpoint；优先用 receipt 显式指标，其次用创作者中心作品列表缓存/MCP 刷新后按 URL/post/title/title 匹配写入 `creator_center_mcp` snapshot；无 adapter 时记录 `adapter_missing` 并延后重试。真人跨天回放待验收 |
| PUB-11 | 指标缺失语义 | 不可得、未授权、延迟、0 分开；禁止用 0 填未知 | 🟡 code verified（2026-07-07）：`collect_metrics` 拒绝 null/unknown/未知/n-a 占位；未知字段必须缺省；默认 `manual_entry` 来源只为兼容旧调用。UI 展示缺失原因、未授权/延迟语义待做 |
| PUB-12 | 评论与反馈摘要 | 只读拉取、隐私脱敏、主题/问题/情绪作为证据，不自动私信 | 真人数据 + 注入防护 | ⏳ |
| PUB-13 | 实验归因 | 关联假设、变体、账号阶段、发布时间和外部热点；输出替代解释 | 一次真实复盘报告 | ⏳ |
| PUB-14 | 策略回写 | 复盘只生成 memory/strategy candidate；多次结果后晋升 | 🟡 首段闭环：单次复盘只生成 pending 结果记忆，不直接改权重；连续样本晋升与 rubric bump 审核待做 |
| PUB-15 | 删除与高风险动作 | 删除、批量发送、付费逐次确认；保留审计和平台结果 | 真人 sandbox/测试账号验收 | ⏳ |
