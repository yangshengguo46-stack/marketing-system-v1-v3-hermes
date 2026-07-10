# 产品收口总控台账（2026-07-07）

> 用户决策：Codex 接管整体产品、代码、台账和资料库一致性；GLM/Claude 产物不再作为不可改边界。任何已有实现只按“是否服务最终体验、是否有证据、是否可交付”判断保留、修正或回退。

## 一、北极星

本项目不是“营销后台”、不是“自动发布器”、也不是“视频生成器外壳”。桌面端 v0.1 的北极星是：

`自然对话 → 账号方向/目标受众 → 对标证据 → 定位/DNA → 内容实验 → 图文/视频资产 → 授权发布/回执 → 指标回收 → 复盘学习 → 下一轮策略`

用户体验判断标准只有一个：用户是否感觉这是一个会长期经营账号、会记住偏好、会基于真实反馈调整策略的智能体。

## 二、当前唯一产品形态

| 区域 | 当前事实 | 收口规则 |
|---|---|---|
| 工作台 | 数据罗盘、趋势、选题和今日判断的驾驶舱 | 不放大对话框；不再拆回趋势中心/创意中心/数据中心独立主入口 |
| 新对话 | AgentPanel 唯一主对话入口 | 复杂经营任务从自然语言触发，不要求用户先懂模块 |
| 历史会话 | 左侧常驻列表 | 不需要折叠进“更多”；像 Codex/GPT 一样可随时回到旧任务 |
| 内容工厂 | 内容资产、素材、发布准备、真实回执和指标 checkpoint；左侧下设“图文创作 / 视频创作”二级目录 | 原“发布中心”不再作为主导航；发布能力并入内容工厂；图文和视频分流，但仍共享同一内容资产事实库 |
| 账号管理 | 平台登录、托管/接管、多账号隔离、MCP 状态 | 用户首次处理扫码/验证码；后续默认后台无感 |
| 研究数据源 | 顶部右侧工具入口 | Firecrawl/记忆治理等高级配置藏在这里，不进入主导航；右侧工具区不能空 |
| 视频 Web | 独立项目，通过 contract 接入 | 不混入桌面主架构收口 |

## 二点五、前端哲学（2026-07-09）

这套产品不能把底层机制平铺到 UI 上卖弄复杂度。用户要感受到的是“一个长期经营账号的智能体很稳、很准、很有判断”，而不是看到一堆预演门、权重、checkpoint、工具日志和数据库字段。

执行原则：

1. **表层安静，底层强判断。** 预演、回放、证据守门、权重治理、失败恢复默认在 Agent 内部完成。
2. **复杂过程折叠进思考。** 必须可审计，但不作为主页面常驻控件；用户需要时再展开依据。
3. **UI 展示决策和下一步，不展示流水账。** 用户看到“为什么这样做、下一步是什么、风险在哪里”，不直接看到工具调用和内部字段。
4. **高级感来自克制。** 少按钮、少解释、少裸露机制；让用户在自然对话和稳定结果里感知智能。
5. **不能伪装神秘。** 表层可以克制，但底层必须有真实证据、回放、测试和失败降级支撑。

## 三、强制边界

1. 不再横向扩新平台、新页面、新开源组件或第二套 Agent runtime。
2. Hermes 是唯一 Agent runtime；`engine/agent_core` 是业务真相源；MCP/API/公开网页/用户输入只写带 provenance 的证据。
3. 记忆不是事实库，只能由事件生成候选，经冲突、证据、scope 和用户修正治理后召回。
4. 发布成功只看平台 receipt / post_id / verified URL；本地 toast、按钮消失和空 ID 都不是成功。
5. 真实受众、职业、收入等字段没有官方/API/创作者中心来源时必须显示未知，不允许模型补齐。
6. 开源方案先做许可证、数据流、秘密、失败回退和卸载路径复核；AGPL/非商业项目只参考，不复制。
7. 每项状态分开记录 `code`、`automated`、`human`、`delivery`，禁止用测试通过冒充真人可用。

## 四、收口执行顺序

| 顺序 | ID | 目标 | 完成口径 | 当前状态 |
|---:|---|---|---|---|
| 1 | CLOSE-01 | 台账/资料库/代码事实对齐 | README、09、11 和本总控台账一致；旧“发布中心/中央 Agent 栏/Claude 领取”语义清理 | ✅ code + automated verified |
| 2 | CLOSE-02 | 真人自然对话起号主链 | 普通人无需登录也能通过对话形成目标受众草案；绑定账号后可迁移到真实账号 | 🟡 code foundation strengthened，human 待验 |
| 3 | CLOSE-03 | 对标证据主链 | 对标候选必须有作者 ID、样本 URL、选择理由；热点标题不能冒充对标账号 | 🟡 B站主链，抖音作者源待稳定 |
| 4 | CLOSE-04 | 定位与首轮实验 | 已确认受众 + 对标证据 → 定位版本 → 可证伪实验 → 内容资产 | 🟡 automated E2E，真人待验 |
| 5 | CLOSE-05 | 图文优先发布闭环 | 图文资产 → 用户授权 → 平台执行/查询 → verified receipt → checkpoint | 🟡 prepare/query/素材 foundation，最终动作待真人 |
| 6 | CLOSE-06 | 指标回收与复盘 | 1h/6h/24h/3d/7d 回收；未知不写 0；生成 retro 与 strategy candidate | 🟡 scheduler/adapter foundation，跨天真人待验 |
| 7 | CLOSE-07 | 策略学习治理 | accepted candidate 类型化应用为定位草案/新实验/权重修改；拒绝原因进入偏好 | ⏳ |
| 8 | CLOSE-08 | 干净机交付 | 断网首启、升级回滚、崩溃恢复、签名/公证、卸载/数据策略 | ⏳ |

## 五、当前第一批整改

1. 先清理文档和 UI 语义：发布中心从主体验消失，旧入口只作为兼容回落到内容工厂。
2. 跑 `tsc --noEmit`、`vite build`、关键 Python 测试，拿到当前接管基线。
3. 如果构建或关键测试失败，优先修阻断；不继续扩能力。
4. 构建通过后，下一轮只做 CLOSE-02/CLOSE-04 的真人主链体验，不再新开模块。

### CLOSE-01 接管基线（2026-07-07）

- 新增本总控台账，并在 `docs/ledgers/README.md` 登记为当前执行入口。
- 修正 `09-main-architecture-closure.md`：当前主导航为工作台、新对话、内容工厂、账号管理；AgentPanel 只在新对话中出现；发布/趋势/选题/自动化不再是主导航语义。
- 修正 `11-stable-product-delivery.md`：稳定产品进度口径调整为桌面可试用约 70%、稳定交付约 65%；明确当前唯一主体验。
- 清理 UI 文案：创意页加入队列提示改为“内容工厂”；隐藏兼容发布页标题改为“发布管道”，避免恢复独立发布中心心智。
- 验证通过：`npx tsc --noEmit`、`npx vite build`、`git diff --check`。
- 关键主链测试通过：`tests/test_account_lifecycle.py`、`tests/test_benchmark_discovery.py`、`tests/test_publishing.py`、`tests/test_learning_pipeline_integration.py`、`tests/test_server.py` 共 98 项通过，1 个 Starlette/httpx deprecation warning。

### CLOSE-02 入口防跑偏修复（2026-07-07）

- `HermesAgentService._build_initial_plan` 新增对“变现、账号方向、起号方向、做账号、个人 IP、赛道”等普通人探索语义的识别；此类请求走生命周期主线，不触发热点证据守门。
- 未登录起号/变现探索时，产品层自动预取 `marketing_read_account_lifecycle`，并通过 `__user_id` / `__task_id` 稳定落到 `prospect_<user>` 待绑定项目。
- 起号类请求无明确账号时不再顺手预取账号 context，避免把已有账号数据误带进普通人探索；有 `account_id` 时仍会读取账号上下文。
- turn context 新增生命周期摘要：`project_id/stage/next_action/data_gaps/benchmark_missing/audience_hypothesis`，并明确“未建立项目不等于必须先登录，可自然对话建立待绑定项目”。
- 测试新增：普通人不知道变现的首轮消息会生成生命周期计划、不会触发热点计划；prospect 生命周期预取参数和上下文文案均被覆盖。
- 验证通过：`tests/test_agent_core.py` 70 项、主链 98 项、`npx tsc --noEmit`、`npx vite build`、`git diff --check`。

### CLOSE-02 对话会话体验修复（2026-07-07）

- “新对话”不再复用 `localStorage.agent-session-id`。进入新对话会清空当前 session，首次发送时创建唯一 `workspace=chat:<timestamp>:<random>` 的 Hermes session。
- 历史会话常驻左侧列表，不挂在“新对话”主入口下面，也不折叠进“更多”；标题来自真实 `agent_tasks.objective`，状态来自最新任务。
- 新增后端接口：`GET /agent/sessions`、`GET /agent/sessions/{session_id}/messages`，从 `agent_sessions`、`agent_tasks`、`task_events` 还原历史列表和消息摘要，不依赖前端假缓存。
- Electron API allowlist 已开放上述两个只读历史接口。
- 前端 `AgentPanel` 支持受控 `sessionId`：新建会话、切换历史会话、加载消息摘要和继续活动任务分离；发送消息后刷新左侧历史。
- 任务生命周期不再绑死在对话页面：离开对话页只断开前端事件流，不取消 Hermes 后台任务；从“更多/历史会话”回到该 session 时，会重新检查 `active_task_id` 并恢复“任务仍在后台运行”的事件流。
- “记忆与知识”从左侧导航移除，作为“研究数据源”弹层里的高级入口保留；主导航不再出现“更多”。
- “研究数据源”入口回到顶部右侧工具区，保持右侧视觉平衡；新对话容器加宽加高，避免像被圈进小盒子。
- 新增白天/夜间主题切换，主题写入 `localStorage.marketing-theme`；白天模式先覆盖主框架、工作台、对话、卡片、表单等高频区域，后续按真人观感继续精调。
- 工作台的“开始今日任务 / AI 今日判断 / 趋势 / 选题 / 查看全部任务”不再跳旧创意中心，而是打开新对话并预填当前热点/选题上下文；旧创意中心“开始创作”也改为进入对话打磨，避免管线断在页面里。
- 上述入口已从散文本 `chat-prompt` 升级为结构化 `CreativeBrief` / `chat-brief`：包含 `kind/title/source/heat/rank/audience/angles/evidence/recommended_action`；2026-07-08 体验修订：`CreativeBrief` 不再作为可见“作战卡”渲染，只作为内部上下文注入输入框，用户点击趋势/选题后直接进入新对话打磨。
- 选题打磨对话新增输出约束：禁止原样倾倒工具名、数据库字段和证据流水账；默认按“一句话结论 / 为什么 / 3 个可做角度 / 需要补充什么”四块短结构回复。前端 `AgentMessageContent` 已支持标题、列表和简单表格渲染，避免 markdown 被压成一整坨；普通新对话已移除旧生命周期提示卡，避免历史遗留的“让 Agent 继续”误导用户。
- 白天模式同步覆盖 shadcn/Tailwind 主题变量，兼容旧页面卡片，不再出现旧创意中心黑底。
- 2026-07-08 平台范围收口：微博从产品目标平台中移除。账号管理不再展示微博入口；趋势中心/工作台/选题建议过滤旧微博缓存；默认热点采集、HotTopics 后端、Agent 平台枚举、登录授权入口、发布/拆条目标平台和内容矩阵均不再包含微博。保留 `weibo` 过滤闸门用于屏蔽历史缓存，不物理删除用户旧数据。
- 测试新增：真实 store 中的 session/task/task.completed event 可被列表接口和消息接口正确还原。
- 验证通过：`tests/test_server.py` + `tests/test_agent_core.py` 共 128 项、`npx tsc --noEmit`、`npx vite build`、`git diff --check`。
- 本轮增量验证：`npx tsc --noEmit`、`npx vite build`、`git diff --check` 均通过。

### HYGIENE-01 工作区清理与重塑（2026-07-08）

- 新增 `docs/ledgers/13-workspace-hygiene-reshape.md` 作为脏工作区整理入口，明确保留/隔离/删除口径。
- 清理本地生成产物：`.playwright-mcp/`、Python bytecode、pytest 缓存、`release/`、`backend/build/`、`backend/dist/`。
- 新增 `scripts/clean-local-artifacts.sh` 与 `npm run clean:local`，后续只清可再生成产物，不碰 `.venv`、`node_modules`、`runtime/hermes-agent` 和用户数据。
- 明确视频骨架 `engine/video_core` / `engine/video_agents` 为独立项目合同，不计入桌面主架构完成度；SBOM/许可证清单作为交付审计快照保留。
- 验证通过：Python 编译检查、`npx tsc --noEmit`、`git diff --check`。

### CLOSE-01/02 Renderer 边界收口（2026-07-08）

- 当前 renderer 不再暴露旧 `api → hermes:api` 兼容别名；前端 `src/api/client.ts` 只调用 `runtimeApi` 和 native `/api/marketing-os` 路径。
- Electron main 仍保留 `hermes:api`、`hermes:status`、`hermes:restart` 兼容 handler，用于旧打包 renderer 平滑过渡；该兼容层不再进入当前 preload 类型面。
- 账号管理“同步指标”从 renderer 直连 `session:sync-account(platform, username, account_id)` 改为 `account:sync(account_id)`；前端只提交 accountId，Electron main 读取账号元数据后执行 MCP → Electron session fallback。当前 UI 不直接调用 `/mcp-sync`；后端 `POST /api/marketing-os/accounts/{account_id}/mcp-sync` 作为 main/Agent/服务内部能力继续保留。
- `session:scrape-industry` 与 `session:sync-account` 不再暴露给 preload；营销 Agent 执行受控能力仍经 `agent:execute-approved-capability`，由主进程读取 approval capability 与 canonical arguments。
- 新增 `tests/test_product_closure_guard.py`：自动守住主导航四入口、native runtime 命名、微博不作为产品目标平台、旧微博缓存只过滤、视频骨架不反向依赖桌面主 runtime。
- 验证通过：`tests/test_product_closure_guard.py tests/test_architecture_boundaries.py` 18 项、`npx tsc --noEmit`。

### CLOSE-03 热点质量展示收口（2026-07-08）

- 后端已有 `rank_trends_for_context`：无账号定位时返回公共探索池；有账号 DNA/禁忌词时按 `audience/persona/content_pillars/goals/promise/taboos` 做确定性匹配、过滤和排序，不让模型编造“适合你”的理由。
- 工作台趋势行开始展示 `relevance_label + match_reasons + heat`，例如“适合当前账号 · AI教育 · 8.82亿人在看”；没有定位时继续显示探索池语义，避免用户误以为系统已经理解了账号。
- 通用垃圾话题（`#fyp`、`#搞笑`、`#短剧推荐`、热门挑战泛标签等）继续在后端质量门过滤；旧微博缓存继续过滤不展示。
- 验证通过：`npx tsc --noEmit`；相关后端过滤已有 `tests/test_content.py`、`tests/test_server.py` 覆盖。

### CLOSE-05/06 内容发布指标闭环收口（2026-07-08）

- Electron allowlist 新增 `POST /api/marketing-os/publishing/sql-tasks/{task_id}/metrics`，当前 renderer 可通过 native runtime 写入真实指标，但仍不能绕过后端 Store。
- 内容工厂的真实发布回执卡片新增“补录指标”：播放、点赞、评论、转发、完播率、互动率。未知指标留空，不能用 `0/null/unknown` 冒充。
- 补录时默认绑定下一个 scheduled metric checkpoint，provenance 固定为 `manual_entry/content_factory_manual_metrics`；后端写入 `publishing_metric_snapshots`、更新 checkpoint、同步 content asset metrics，并触发 `learning_pipeline.reconcile_published_metrics`。
- 如果资产有发布前 prediction，补录指标会生成 retro 与 pending memory candidate；如果没有 prediction，只记录真实指标，不伪造学习结论。
- 新增 server 回归：`test_sql_publishing_metrics_endpoint_collects_checkpoint_and_learning`，验证 API 端点会 collected checkpoint 并触发 learning。
- 验证通过：`tests/test_server.py tests/test_publishing.py tests/test_learning_pipeline_integration.py` 79 项、`npx tsc --noEmit`。

### CLOSE-04/05 内容生产到工作台驾驶舱收口（2026-07-08）

- `dashboard_overview` 新增 `content_pipeline` 与 `publishing_receipts`：工作台可直接看到草稿数、可发布库存、已验证回执、待验证回执、指标 checkpoint 总数/已回收/到期数和下一次回收时间。
- 工作台数据罗盘下方新增经营状态卡：内容生产、发布回执、指标回收、内容库存。发布回执不再只藏在内容工厂，用户打开工作台即可看到“内容有没有产出、发布有没有证据、指标有没有回收”。
- 内容工厂顶部新增“让 Agent 生产草稿”入口，直接进入新对话，并明确要求 Agent 在证据足够时调用 `marketing_draft_content_create` 保存内容资产草稿；手动“新建草稿”也支持正文/脚本正文，不再只能创建空标题。
- 工作台趋势/选题进入对话的 `CreativeBrief` 提示新增落库纪律：足够成稿时使用 `marketing_draft_content_create` 保存，不足时不要伪造草稿。
- 新增/更新回归：`test_overview_uses_persisted_counts` 覆盖工作台内容库存、发布回执和指标 checkpoint 摘要。
- 驾驶舱读摘要不再初始化完整 Hermes Agent 服务：已有 `_agent_service` 时复用 Store；否则只打开 `agent_core.db` 读业务事实，避免工作台读取触发运行时副作用。
- 验证通过：`tests/test_server.py tests/test_product_closure_guard.py tests/test_publishing.py tests/test_learning_pipeline_integration.py` 85 项、`npx tsc --noEmit`、`npx vite build`、全量 `pytest` 1207 项（1 个 Starlette/httpx deprecation warning）。

### CLOSE-04/05 软文平台入口收口（2026-07-08）

- 知乎入口保持开放：账号管理、趋势入口和内容矩阵继续保留 `zhihu`，并新增产品守卫防止被误删。
- 新增独立 `wechat_official` 平台，前端显示为“公众号”；它不是 `wechat_channels` 视频号，也不是微信/飞书沟通接口。
- 账号管理新增公众号入口，Electron 登录目标为 `https://mp.weixin.qq.com/`，会话继续走按 `platform + account_id` 隔离的持久 Electron session。
- 内容矩阵新增公众号软文规则：`long_article`、标题上限 64 字、0-3 个标签、无 hashtag 前缀、CTA 走信任/转化语气。
- Draft decompose / variants / Agent tool manifest 均允许 `wechat_official`，用于把一个选题拆成知乎长文与公众号软文等多平台版本。
- 当前边界：已支持入口、登录会话和草稿/拆条适配；真实群发/发布回执仍需后续接公众号官方接口或手动回执，不在本轮冒充完成。

### CLOSE-01/02 账号登录体验统一（2026-07-08）

- 账号管理中所有平台的“点图标/重新登录”入口统一走 Electron 官方登录窗口：`openLoginBrowser(platform, accountId)`。
- 抖音不再在登录入口特殊走 `mcpLoginStart`；MCP 只作为后台采集、托管和受控工具执行能力保留，避免用户感知到两套登录体验。
- 新增产品守卫：`startLogin` 不允许针对抖音写特殊分支，防止后续外部模型又把登录入口改回 MCP 流程。

### CLOSE-02 随身助手扫码连接收口（2026-07-08）

- 微信/飞书作为沟通接口保留在账号管理的“随身助手”区，不属于内容平台账号；与 `wechat_channels` 视频号、`wechat_official` 公众号严格区分。
- 当前扫码连接链路：前端 `connectChannel(platform)` → Electron `channels:connect` → `electron/channel_bridge.py` → Hermes gateway 微信/飞书适配器。
- 本轮补齐 Hermes runtime 依赖安装：`scripts/bootstrap-hermes-runtime.sh` 从 `[mcp]` 调整为 `[mcp,feishu]`，并固定 `aiohttp==3.13.4`、`python-socks[asyncio]==2.8.2`，确保飞书 SDK、二维码渲染包和 SOCKS 代理支持随 runtime 安装。
- 当前本机 runtime 已通过 `uv pip install --python runtime/hermes-agent/.venv/bin/python -e 'runtime/hermes-agent[mcp,feishu]'`、`uv pip install --python runtime/hermes-agent/.venv/bin/python aiohttp==3.13.4`、`uv pip install --python runtime/hermes-agent/.venv/bin/python 'python-socks[asyncio]'` 补齐 `qrcode`、`lark-oapi`、`aiohttp`、`python-socks` 等依赖。
- `channel_bridge.py` 不再因缺少 `qrcode` 直接崩溃：正常情况下向前端推送二维码图片；极端缺包时仍推送授权 URL，前端显示“打开授权链接”兜底。
- 微信二维码不显示根因修复：`connect_weixin()` 为拦截 Hermes 终端二维码临时替换 `builtins.print`，但 bridge 的 `emit("qr")` 也使用 `print`，导致 QR 事件被自己的拦截器吞掉；现改为 `sys.stdout.write + flush`，并新增回归测试保证 print monkey-patch 下仍能输出 JSON 事件。
- 扫码连接不允许无限转圈：Electron `channels:connect` 对微信二维码生成设置 45 秒超时、飞书设置 60 秒超时；前端忙碌态按钮变为“取消”，可主动终止当前 bridge 子进程。
- 当前边界：扫码、授权和 Hermes gateway 重启链路已就绪；真实可用性仍取决于微信 bot QR 服务/飞书注册服务是否可访问，以及扫码人是否在平台侧完成授权。

### CLOSE-02 账号管理页排版收口（2026-07-08）

- 账号管理页从纵向散落段落改为紧凑控制台：`NetworkDiagnostic` 与 `MessagingChannels` 进入 `account-command-grid`，诊断是紧凑状态卡，随身助手是独立面板。
- 随身助手内部重排：微信/飞书渠道卡在左侧，二维码/连接提示固定在右侧；未连接时显示“等待扫码”占位，出 QR 时不再把页面撑散。
- 已连接账号行重构为 `平台标识 / 账号身份 / 指标组 / 状态 / 操作组`，修复抖音多一个“托管”按钮时把在线状态和操作按钮挤在一起的问题。
- 白天模式同步补齐 `account-panel`、`channel-onboarding`、`diagnostic-item`、`connected-list`、`account-stat` 的背景、边框和文字颜色。
- 当前验证：微信扫码辅助进程复测 1.7 秒返回 `liteapp.weixin.qq.com` QR URL 和 `qr_image`；二维码事件回归、`npx tsc --noEmit`、`npx vite build`、`git diff --check` 通过。消息进入 Agent 后的路由已由下节 2026-07-10 原生收口方案接管。

### CLOSE-02 随身助手消息路由原生收口（2026-07-10，覆盖 07-08 HTTP 转发方案）

- 架构校准：Hermes 是唯一主运行时；Marketing OS 的账号、证据、内容、发布和学习模块是写入 Hermes 源码与工具链的原生增强，不拥有第二套 Agent 生命周期。
- 删除 `gateway/marketing_os_bridge.py`。飞书/微信消息不再短路到本机 FastAPI 的 `/agent/sessions` 和 `/agent/messages`，也不再维护 `marketing_os_mobile_sessions.json` 映射。
- 入站消息现在继续走同一条 Hermes gateway 原生链：授权 → Hermes session → Marketing OS 系统指导与账号工具 → 原生 memory/task/tool loop → 原平台回发。桌面、飞书、微信只是不同行为 surface，不再是不同 Agent。
- `marketing_os/messaging.py` 只在原生入站管线前增加产品便利：可信首个私聊自动设为通知窗口；中文“设为通知窗口”转换为 Hermes 内建 `/sethome`。它不发 HTTP、不创建会话、不执行模型。
- Electron 不再注入或持久化 `MARKETING_OS_MOBILE_BRIDGE_ENABLED`，`channel_bridge.py configure` 也不再把 API 地址和 token 写入 Hermes 配置；仅同步营销数据目录。扫码辅助进程仍负责二维码和 gateway 启停，不参与 Agent 推理。
- 自动化证据：原生产品身份、消息准备、Gateway 产品状态 10 项通过；未知用户不能认领通知窗口，普通 Hermes 环境不受产品便利逻辑影响。真实飞书/微信连续对话仍需重启新版 gateway 后人工复验。

### CLOSE-04/05 内容生产端三线工单收口（2026-07-08）

- 新增 `docs/ledgers/14-content-production-factory.md` 作为内容生产端执行台账。产品判断更新：没有可审稿/可配图/可渲染/可发布/可回收指标的内容资产，前面的账号定位、热点、发布和学习都闭不了环。
- 内容生产端拆成三条 lane：`article_soft`（知乎/公众号软文）、`faceless_video`（授权素材拼接的不露脸视频）、`premium_human_video`（真人/数字人/AI 人高质量视频）。`08-video-generation-volcano.md` 只负责第三条高级视频 lane。
- 新增 `engine/agent_core/content_production.py`：确定性生成内容生产工单，包含步骤、工具序列、证据门、版权门、成本门和降级方案；不写库、不下载素材、不调用付费视频 API。
- Agent 新增只读工具 `marketing_plan_content_production`；系统提示和初始计划已要求内容生产请求第一步先生成工单，再决定读证据、写草稿、找素材或进入视频项目。
- 后端新增 `POST /api/plugins/marketing-os/content/production/plan`，Electron API allowlist 已同步放行；内容工厂顶部入口改为“写软文 / 不露脸视频 / 数字人视频”，点击后进入新对话并要求按工单推进，足够成稿时使用 `marketing_draft_content_create` 保存资产。
- 当前验证：`python3 -m pytest tests/test_content_production.py -q` 5 passed, 1 skipped（系统 Python 无 FastAPI 跳过端点）；`.venv/bin/python -m pytest tests/test_content_production.py -q` 6 passed；`tests/test_content_production.py tests/test_run_12_13_14.py tests/test_product_closure_guard.py` 35 项通过；`node --check electron/main.js && node --check electron/preload.js && npx tsc --noEmit && npx vite build && git diff --check` 通过。

## 六、外部模型任务规则

如果后续仍让外部模型执行，复制本段即可：

```text
只执行 docs/ledgers/12-product-closure-control.md 中的一个 CLOSE-ID。
先读该台账、docs/ledgers/11-stable-product-delivery.md、docs/architecture/account-lifecycle-architecture.md。
不得新增主导航、第二套 Agent runtime、第二套事实库或未复核开源组件。
不得把 mock、占位 provider、测试通过或页面展示标记为 human verified。
结束时只回填：代码路径、自动化证据、真人待验点、风险和下一步。
```
