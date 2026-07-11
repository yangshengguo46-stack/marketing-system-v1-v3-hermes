# Marketing OS 当前产品总控

> 基线日期：2026-07-11
> 当前分支：`codex/marketing-os-product-source`
> 作用：这是唯一的实时执行入口。`LEDGER.md` 与 `AGENT_CORE_LEDGER.md` 保留第一版产品宪法；其余编号台账是领域历史和实现证据，不再各自宣布“当前主线”。
> **2026-07-10 内核纠偏（最高优先级）：Hermes 源码是产品主干，Marketing OS 是直接写入这套主干的原生营销增强，不是一个调用 Hermes 的外层应用，也不是第二套 Agent。** 本条覆盖历史资料中“业务差异优先放 adapter/插件”“产品业务逻辑仍留在 `engine/agent_core`、Hermes 只承载少量 runtime patch”“改动最小化”等旧约束。`run_agent.py`、SessionDB、model tools、gateway、cron、memory、skills、plugins、TUI 和 `apps/desktop` 均可按产品体验深度重构；上游可重放/可 rebase 不再高于产品正确性。唯一目标架构、所有权矩阵和旧路径删除门见 `docs/marketing-os/architecture/REBUILD_BASELINE.md`。
>
> **本次重构的最高裁决原则：原本 Hermes 就有的东西，然后我们跟它重叠了，人家方案还比我们优秀的情况下，我们就不要画蛇添足。** 有缺口时修改 Hermes 的原生 owner；只有确实不存在的营销领域能力才新增。不得以 Marketing 名义复制 Provider、密钥、Session、Profile、MCP、Skill、记忆、更新或 UI owner。
>
> **2026-07-11 源码归一已经完成：主仓库根目录直接追踪完整 Hermes 派生源码和 Marketing OS 增强；`runtime/hermes-agent` 嵌套仓库、`hermes-patches` 补丁回放、旧 React/Electron 壳、旧 FastAPI、旧构建副本和历史安装包均已删除。上游只作为 `hermes-upstream` 工程 remote，由 Marketing OS 团队吸收、回归并发布产品版本；用户端禁止直接执行 raw `hermes update`。**

## 一、第一版没有变的目标

Marketing OS 不是“营销页面加一个聊天框”，也不是一组热点、写作、发布工具。第一版真正要交付的是一个受控、持续、会学习的账号经营 Agent：

1. 产品以 Hermes 源码为主干；Agent loop、harness、session、长任务、记忆、技能和渠道保持为唯一内核，Marketing OS 领域能力原生增强这些路径，不从外层反向接管它们。
2. 用户只需要表达目标；Agent 负责建立计划、读取证据、调用能力和说明下一步。
3. 任务跨页面、窗口隐藏和进程重启仍能恢复，外部动作不能因重试而重复执行。
4. 同一账号沿着“受众与定位 → 内容 → 发布 → 指标 → 复盘 → 下一轮”长期经营。
5. 建议、预测和学习都有来源、时间、账号范围、置信度和用户控制。
6. 微信、飞书、Web 视频工作台只是同一个 Agent 的 surface，不拥有第二套记忆或任务系统。

第一条真正的验收样板仍然是：

```text
一句自然目标
  → 建立用户/账号上下文
  → 生成稳定计划
  → 读取真实证据
  → 产出可审阅内容资产
  → 用户确认
  → 发布或记录可靠回执
  → 回收指标
  → 形成待治理复盘候选
  → 下一轮内容明显更懂用户和账号
```

## 二、产品目标与内核归属已经纠正，业务闭环仍待收口

| 当前能力 | 与第一版关系 | 当前判断 |
|---|---|---|
| 持久 session、AgentTask、审批、effect、checkpoint | 原始核心 | 方向正确；真实 Hermes、跨重启和外部副作用验收不足 |
| 多账号、MCP、登录会话 | 桌面身体 | 方向正确；Electron 与 Playwright 两套 profile 尚未统一 |
| Account DNA、受众、对标、定位、生命周期、onboarding | 长期账号经营 | 产品差异化核心；onboarding 目前主要是后端计划协议，尚未成为真实首轮体验 |
| 内容资产、回执、指标、复盘 | 业务闭环 | 应成为当前主线；现有内容质量和真实发布仍不足 |
| 记忆、三核循环、InfluenceOS、Preflight | 证据和学习深化 | 方向正确；部分评分与预测先于真实样本，必须降级为未校准启发式 |
| 软文、不露脸视频 | 内容交付形态 | 可保留；先完成图文真实闭环，再继续视频 |
| 高阶视频剧组、多 Agent、Provider 框架 | 独立视频项目 | 保留合同和隔离代码，暂停扩建，不计桌面 v0.1 完成 |
| 微信/飞书 | 后置沟通 surface | 保留，不抢主线 |
| 60 个模型可见工具 | 内部能力暴露方式 | 明显偏离“最小工具集”；后续按任务能力包收口 |

结论：源码和运行时已经回到“一个 Hermes 派生产品本体”；当前风险不再是外层套壳，而是账号、内容、发布、回执和学习这些领域闭环还没有全部达到真人可长期使用的质量。

## 三、2026-07-11 代码事实

以下数字只描述工程规模，不代表产品完成：

| 事实 | 当前证据 |
|---|---|
| 主仓库 | 5842 个跟踪文件；根目录就是完整产品源码，不存在子仓库或源码补丁回放 |
| 上游维护 | `hermes-upstream` 仅供内部 fetch/merge/rebase；用户只接收 Marketing OS 产品版本 |
| Agent/runtime | `run_agent.py`、`agent/marketing/`、`hermes_state.py`、`gateway/`、`skills/`、`plugins/` 同仓同执行链 |
| 桌面 UI | `apps/desktop` 是唯一 React/Electron 产品入口；旧根 `src/`、`electron/` 已删除 |
| 本机服务 | 旧 `engine/marketing-os/server.py`、PyInstaller backend 与外层 `HermesAgentService` 已删除；桌面直接启动同仓 Hermes dashboard/gateway |
| 产品运行时 | 根 `.venv` 已通过锁文件改绑当前仓库；Node 依赖也与当前根 `package-lock.json` 对齐 |
| 自动化 | Marketing OS 定向 Python 110 项通过；桌面平台 260 项通过、1 项按平台跳过；TypeScript/Vite production build 通过 |
| 打包 | 自包含 Python/产品源码 staging 与 manifest/resolver 已实现并有测试；真实签名安装包和干净机断网首启仍待验收 |

### 自动化不能证明的事情

- `tests/test_e2e_01_internal_chain.py` 明确不启动 Hermes，外部 MCP 使用 mock。
- 没有真实 Electron UI E2E、干净机持续对话、真实发布、自动指标回收或跨天经营验收。
- packaged smoke 尚未在一台没有本项目、Python、Node/Hermes 的干净 macOS 上执行，也未覆盖真实 Provider 对话。
- 1325 个测试证明工程地基较强，不证明用户已经拿到完整产品闭环。

## 四、已确认的结构性问题

### P0-00 外层 Agent 主路径和双源码结构已删除

2026-07-11 已把改造后的 Hermes 历史提升为主仓库产品分支，主目录直接拥有 Agent、Gateway、SessionDB、MCP、Skill、Plugin、渠道、桌面和 Marketing domains。旧 `engine/`、根 `electron/`、根 `src/`、FastAPI/PyInstaller backend、嵌套 Git 和构建副本均已物理删除，不再存在第二套可启动 Agent 主路径。

纠偏目标：增强后的 Hermes 成为唯一 Agent Runtime 和产品 harness。Agent 身份、系统上下文装配、结构化计划、step checkpoint、工具注册与中间件、审批/effect、长任务恢复、记忆检索/沉淀、技能选择/生成、渠道路由和事件流必须在 Hermes 原生执行链里完成。Electron 仍负责系统秘密、窗口、账号 profile 和外部副作用；账号/内容/发布等领域模型可保持独立模块和 SQL 真相源，但只是 Hermes 调用的能力边界，不能由外层 adapter 反过来拥有 Agent。

`apps/desktop` 现在是唯一可启动、可构建、可打包桌面母体，继续承载 Hermes 原生 JSON-RPC gateway、会话历史、聊天流、工具审批、skills、messaging、cron 和 settings。后续 UI 和领域能力只在这套源码继续开发。

“可以爆改”代表源码所有权，而不是把代码写成新的巨石。仍需保留确定性状态机、领域边界、安全审批、可迁移数据和回归测试；但只要最终体验需要，就直接改 Hermes 的原生执行路径，不再先造一层 adapter、bridge、sidecar 或代理来回避修改。

这也不是一场单向的“把 Marketing OS 搬进 Hermes”。Hermes 继承代码和当前 Marketing OS 代码都允许拆分、删除和重写：前者提供成熟的 Agent/harness/session/desktop 骨架，后者提供账号经营、证据、内容、预演、发布回执和学习闭环。迁移按最终能力边界重新组合，不按任一旧目录原样照搬。唯一不可丢的是产品设计哲学：围绕一个用户和一组账号长期经营，用真实证据行动，用真实结果学习，最终表现为同一个超级营销 Agent。

2026-07-10 原生切入基线已落地，2026-07-11 又将当时的 `marketing_os/product.py` 迁为 `agent/product.py`：默认 Agent identity 和系统指导直接由 Hermes prompt builder 装配；`tui_gateway` 原生暴露产品状态；`apps/desktop` 根路由成为原生工作台，对话迁至 `/chat` 并兼容旧会话路由；安装包、窗口、协议、导航、通知和多语言用户文案统一为 Marketing OS。该基线证明营销经营哲学已经进入 Hermes 主干，不再由顶层营销包提供。

第一条领域纵切也已启动：fork 内的 `AccountContextRepository` 不回调 FastAPI、不复制数据，直接以只读方式消费现有 `accounts.json + agent_core.db` 真相源；原生 Gateway 提供 `marketing.accounts.list` 与 `marketing.account.context`，原生工作台已读取真实账号数量。6 个定向 Python 契约通过，并在本机真实数据上读到 1 个抖音账号；该账号当前生命周期仍为 `not_started`、没有 DNA/真实受众快照，这是真实数据缺口，不做 UI 伪填充。写入所有权和 schema migration 尚未迁入 fork。

同一投影已注册为 Hermes 原生 `marketing` toolset：`marketing_read_accounts` 与 `marketing_read_account_context` 默认进入桌面、消息渠道和 cron 的核心工具集。真实工具 dispatcher 已在本机读取账号 `acct_194dedab3145` 并返回 `not_started → draft_audience_hypothesis`，不经过外层 `HermesAgentService/tool_manifest/FastAPI`。这完成了“UI 能看”到“Agent 自己能取证”的第一步；会话级账号绑定见下一段，账号领域写入仍待迁移。

会话级账号绑定已经进入 fork 原生 SessionDB，而不是 UI 临时状态：`sessions` 直接保存 `marketing_user_id/marketing_account_id`，新对话从工作台选中账号后随 `session.create` 一次绑定，历史恢复、分支和压缩后继会话自动继承。账号作用域只把稳定路由 ID 放入缓存友好的会话提示，动态 DNA、受众、生命周期和指标仍必须调用原生账号工具取最新事实；首次模型调用后禁止在原会话偷换账号，避免多账号串记忆。没有账号的用户绑定 `prospect_*` 作用域，可从自然对话建模。该纵切通过 303 个 SessionDB/产品定向测试、75 个 Gateway protocol 测试、19 个 UI 定向测试、完整 Desktop lint/typecheck/production build；尚未完成真实用户点击与跨重启人工验收，其余账号领域写入仍在旧业务层。

账号写入的第一段所有权也已进入 fork：`AccountLifecycleRepository` 原生初始化并写入版本化 `account_strategy_projects/audience_hypotheses`，支持经营目标、受众草案和显式用户确认；`marketing_update_account_lifecycle` 只有一个动作入口，不接受模型提供的账号 ID，dispatcher 按 SessionDB 强制写当前会话绑定账号，跨账号 read/write 会被拒绝。确认前不推进生命周期，确认后从同一真相库读回 `audience_hypothesis_ready`。本段 380 个 SessionDB/产品/Gateway 回归通过；定位、对标、实际受众、实验等剩余 schema 的写入所有权与旧库升级迁移仍待逐段接管，不能宣称 Account 领域已全部迁完。

Hermes 生态兼容被明确保留：原生 MCP catalog/自定义 MCP、MCP 动态工具发现，Hub Skill 安装更新、用户 Skill、Skill 自我生成治理，以及插件安装更新仍沿用 Hermes 合同。核心代码升级与生态包升级分离：Marketing OS 运行时禁止直接执行原地 `hermes update` 覆盖产品 fork，核心上游变化必须进入 Marketing OS 版本并经过产品回归；MCP server、Hub Skill、用户 Skill 和插件继续独立更新。Gateway 产品状态和 dashboard update API 会返回该政策，CLI 产品运行时也 fail-safe 阻断 raw apply。48 个 Hermes 原 updater/产品 updater 回归通过，证明非产品 Hermes 模式未被破坏；尚待建立定期 upstream merge/rebase CI，把“可升级”从人工纪律提升为自动维护流水线。

消息渠道的双运行时旁路已经删除：原 `gateway/marketing_os_bridge.py` 会把飞书/微信消息通过 HTTP 送回外层 FastAPI 并创建第二类会话；当前 `gateway/product_messaging.py` 只做可信通知窗口准备，随后继续进入 Gateway 原生授权、session、memory、task 与工具循环。产品状态明确为 `hermes-native-marketing / single-runtime`；真实飞书/微信连续对话仍待人工复验。

内容生产的第一段所有权也已进入 Hermes：原生 `ContentProductionPolicy` 负责三条互通 lane 和共享能力池，`content_production_plans` 把工单变成账号级持久 checkpoint；`marketing_draft_content_create` 必须引用当前账号真实 `plan_id`，模型不能传 `account_id`，跨账号、跨管线或跨平台草稿会被拒绝；`marketing_read_content_assets` 可恢复当前账号草稿。完整内容仍写入现有 `content_assets` 真相源，不复制数据库、不塞入长期记忆。

EvidencePack 的首个真实采集纵切也已进入 Hermes 主调度器：`web_search` 仍只发现候选来源，成功的 `web_extract` 在工具结果返回模型前自动按 SessionDB 当前账号固化 `evidence_records`，系统计算 URL、采集时间、原始抓取内容 SHA-256、摘要来源、session/tool call 和 source-integrity 状态，再把不可伪造的 `evidence_id` 返回模型；没有任何模型可调用的 evidence-create 工具。生产计划和草稿只接受当前账号的 verified EvidencePack ID，原始 URL、`source:` 字符串、跨账号 ID 和失败抓取均被拒绝。这里的 verified 仅证明来源完整性，不宣称网页每个主张为真；多源交叉验证、真实父稿/平台变体、素材/渲染和发布仍待完成，不能宣称内容闭环完成。

图文父稿也不再通过通用 JSON 草稿绕过质量门：`marketing_draft_article_create` 原生保存一个 ArticleBundle，包含 Agent-authored 父稿、计划中每个平台的独立变体、EvidencePack 引用、平台 stylebook、封面/插图需求和未校准预测声明。父稿不足 800 有效字符、缺章节/证据、引用未知 ID，或知乎/公众号版本缺失、太短、复制父稿、彼此近似，都会保存为可恢复的 `needs_revision` 草稿而不是 `review_ready`；通用草稿工具明确拒绝 `article_soft`。stylebook 同时区分平台编辑器事实和仍需账号数据校准的运营建议，不把“最佳字号”包装成官方硬规则。该实现证明确定性质量门已原生化，仍未证明真实 Provider 写稿质量或真人愿意发布。

### P0-00 删除与所有权结果

| 已删除旁路 | 当前唯一归属 | 状态 |
|---|---|---|
| 根 `src/` + 根 `electron/` | `apps/desktop` | 已删除 |
| `HermesAgentService` + Tool Manifest | 原生 Agent/Gateway/tool registry | 已删除 |
| FastAPI/PyInstaller backend | 原生 dashboard/gateway + typed domains | 已删除 |
| `runtime/hermes-agent` 子仓库 | 主仓库根产品源码 | 已删除 |
| checksummed patch replay | 产品 Git 历史 + `hermes-upstream` remote | 已删除 |
| 用户端 raw `hermes update` | Marketing OS 产品发布通道 | 已阻断；内部吸收上游后发布 |

迁移期间允许旧链只读兼容，但禁止再向旧 UI、旧 adapter 或旧 JSON 状态源增加新功能。每完成一条纵向能力就切换默认入口并删除对应旧写路径，避免“新架构完成了、旧架构也永远留着”。

### P0-01 Hermes 源码与包内运行时已形成 packaged smoke，干净机仍待验

嵌套源码和补丁回放已在 2026-07-11 退役。当前安装包 staging 会从主仓库根复制经过测试的产品 tree、Python 基础运行时和精选依赖，并由 manifest 校验平台、架构和路径边界。剩余阻断是生成正式签名安装包，并在没有本项目、Python、Node、Chrome 或全局 Hermes 的干净机器完成断网首启、真实 Provider 对话和一个 L0 营销工具验收。

### P0-02 工具结果与审批状态契约（已完成 automated 修复）

旧实现会把业务 handler 的 `blocked/error` 再包装成顶层 `status=ok`，并把 `pending_approval` 计划步骤误写为 `failed`；审批后的 effect 回执也不会完成原步骤。2026-07-10 已修复为统一顶层 `ToolOutcome`，增加 `running → waiting_approval → completed/failed/skipped` 确定性投影、旧任务修复、精确 `approval_id/effect_id` 绑定和未知外部结果禁止自动重试。相关 83 个定向测试和 1325 个全量测试通过；真实 Electron 审批续跑仍属于 R4 人工验收。

### P0-03 内容工厂还不是高质量内容生产系统

不露脸脚本和部分镜头仍来自确定性模板；固定播放区间和启发式常数会制造“数学上很专业”的错觉。软文路线已完成第一轮边界修复：Hermes 必须提供真实父稿和知乎/公众号改写，确定性代码只校验结构、证据引用、平台差异并保存资产；缺正文只保存 scaffold，复制父稿冒充平台改写会被阻断，未校准时不自动写评分或流量区间。

2026-07-10 已使用 Hermes 原生 SessionDB、DeepSeek Provider、营销工具集和真实账号运行一轮图文 E2E。首稿因为出现“90%以上”“每半年”“三个月后只剩三成”等证据未支持主张，被新 `article_validation.v2` 降回 `needs_revision`；Agent 随后通过同一原生会话和 `revision_of` 工具生成 v3、v4，最终把就近引用缺失与数字证据错配均降为 0，资产进入 `ready_for_human_review`。这证明 Provider、会话、工具、内容资产和修订循环已经在 Hermes 主干内贯通；但 `claim_truth_verified=false`，来源语义、账号匹配、视觉版权与政策合规仍必须真人审稿，不能把确定性门通过写成“事实已核验”。

### P0-04 发布存在双真相源

旧 `publishing.json` 与新 SQL publishing task/receipt/checkpoint 同时存在。部分 UI 创建和分析仍读旧 JSON，真实 SQL 回执反而没有完整进入分析。必须一次迁移后停止写旧路径。

### P1-01 浏览器存在两个身份世界

前台登录主要使用 Electron partition，后台托管使用 Playwright MCP profile，失败时还可能回退 Electron DOM。用户登录一次却仍被要求再次扫码，根因就在这里。目标是每个平台账号一个持久 profile，需要交互时 headed，后台时复用同一身份执行。

### P1-02 继承巨石仍需按体验拆分

FastAPI、外层 adapter 和旧 store 反向依赖已经随旧源码删除。当前仍有继承的 `apps/desktop/electron/main.cjs`、Agent loop 和 Gateway 大文件；后续只沿真实账号、内容、发布闭环拆模块，不为“看起来分层”重建 wrapper、第二套数据库或第二个 Agent。

### P1-03 台账不再是事实源

旧总台账仍写 19 个工具、61%/72% 和不同“当前入口”；15 号台账已超过千行且章节乱序。以后工具数、版本、启用能力和测试事实由代码生成；手工台账只记录产品判断、验证等级、阻断和下一步。

### P1-04 Hermes 产品化裁剪必须先缩运行时，禁止误删代码能力

2026-07-11 完成首轮源码与打包体积审计，结论见 `docs/marketing-os/architecture/HERMES_PRODUCT_PRUNING.md`。当前 staged runtime 447MB，其中 Agent 源码仅 40MB，site-packages 达 304MB；Google、开发调试和未交付消息平台依赖是主要浪费。隔离 profile 实测核心依赖 88MB、核心加飞书 139MB，说明首阶段无需阉割 Agent 即可把 staged runtime 降到约 231–282MB。

裁剪红线：terminal/file/patch/execute_code、coding context、browser/web/vision、MCP/Skill/Plugin 和 p5.js/HyperFrames/Manim/信息图能力必须保留，因为内容端需要它们生成可复现图片、动态图表、UI 演示和视频 clip。下一步先建立干净的产品构建 venv 与 extras allowlist，再讨论删除 `infographic/website/bootstrap-installer` 等仓库资产。

### P1-05 Marketing OS 增强层必须继续去重，但不能误删营销领域

2026-07-11 核对发现原顶层 `marketing_os/` 仅约 2,800 行、110KB，旧壳和第二 Agent 已经不在；剩余风险是 owner 重叠和“营销哲学只存在于工具层”，不是代码体积。裁决清单与删除顺序见 `docs/marketing-os/architecture/MARKETING_OS_DEDUPLICATION.md`。

第一批已把 AccountLifecycle、EvidencePack、ContentAsset 三个 repository 重复的 SQLite connection/transaction 基础设施合并为一个 `MarketingDomainRepository`，随后物理删除顶层 `marketing_os/`：产品身份进入 `agent/product.py`，账号经营、受众、证据、内容资产和平台表达进入 `agent/marketing/`，消息策略进入 `gateway/`，模型工具进入原生 `tools/`。原生 memory guidance 也已加入“用户偏好—账号模型—业务记录—技能候选”分层学习规则，避免营销哲学只停留在外挂工具说明里。下一批将把 session scope 进一步归还 SessionDB、通知窗口统一复用 `/sethome`，再淘汰 `accounts.json + agent_core.db` 兼容读取。Agent loop、Provider、密钥、MCP、Skill、Plugin、记忆存储与渠道路由禁止再造。

### P1-06 三核闭环算法开始回归 Hermes 原生执行链

2026-07-11 已从旧分支恢复 feature snapshot、六维 prediction、content rubric、InfluenceOS Score、PreflightDecision、prediction-vs-actual retro、learning governance 和 memory classification 的纯算法，当前路径统一为 `agent/marketing/intelligence/`。旧 `AgentCoreStore/FastAPI/HermesAdapter/tool manifest` 没有复活。

`marketing_plan_content_production` 现在会在 Hermes 原生工具调用中自动保存 production plan checkpoint、运行总内容预演并写不可变 preflight record；内容草稿入口必须消费可执行 preflight，通过后才创建资产并把记录标记为 `used_for_action`。每个资产同时写入系统生成的 feature snapshot。ReceiptRef 与 LearningCandidate 已恢复为幂等脱敏事实和待治理解释，但真实发布 effect/指标回收尚未接入它们；候选即使 accepted 也不会直接进入 Hermes memory 或永久账号策略。

Git 历史完整筛选见 `docs/marketing-os/architecture/GIT_HISTORY_CAPABILITY_RECOVERY.md`。恢复白名单是算法、合同和安全边界；`HermesAdapter/FastAPI/AgentCoreStore/tool manifest/MCP broker` 等旧套壳 owner 进入禁止恢复清单。

## 五、v0.1 收口范围

### 必须交付

1. 新用户不用先登录，通过自然对话形成 Account DNA v0 和一个可验证方向。
2. 已登录用户能绑定账号，读取真实/明确未知的账号上下文。
3. Agent 能从真实来源形成 EvidencePack，不用泛热点和虚构指标补数量。
4. 至少产出一篇真正可审稿的知乎/公众号父稿和平台版本，正文由 Agent 创作而不是固定模板。
5. 内容进入统一 ContentAsset，支持用户修改、确认和版本追踪。
6. 发布前通过真实的证据、平台、版权和风险门；未校准预测不得显示为真实流量区间。
7. 首版可以使用人工发布回执，但必须记录平台、账号、内容、时间和 post URL/ID；未知结果不能冒充成功。
8. 指标回收后形成复盘候选，用户确认或多次证据后才改变记忆/策略。
9. App 切页、隐藏和进程重启不丢当前任务，不重复已执行副作用。
10. 干净 macOS 机器无需全局 Hermes、Python 或 Chrome，也能启动、对话和调用一个 L0 业务能力。

### 暂停扩建

- 高阶视频真实 Provider、多 Agent 片场和 GPU 工作流。
- 全平台自动发布、微信/飞书体验扩张、Windows 正式交付。
- 自动生成生产技能；先保留候选、评估和人工启用合同。
- 没有真实样本校准的播放量、完播率、互动率和 InfluenceOS 数字承诺。

## 六、重塑后的唯一代码方向

```text
React / Mobile / Web surfaces
              │
       Product API + Event Stream
              │
┌─────────────▼─────────────┐
│ Electron Capability Host  │
│ window / secret / profile │
│ file / notification / L3  │
└─────────────┬─────────────┘
              │ typed capability
┌─────────────▼────────────────────────────────────┐
│ Marketing OS — Hermes Product Fork              │
│ apps/desktop: 唯一 Electron/React 产品界面       │
│ Agent loop / harness / session / long task      │
│ plan / checkpoint / memory / skills / channels  │
│ tool middleware / approval / effect / events    │
└─────────────┬────────────────────────────────────┘
              │ domain ports
┌─────────────▼────────────────────────────────────┐
│ Marketing Domain Services                       │
│ Account | Evidence | Content | Publishing       │
│ Feedback | Learning | Platform connectors       │
└─────────────┬────────────────────────────────────┘
              │
┌─────────────▼────────────────────────────────────┐
│ SQLite truth + artifact store                   │
│ task / memory / content / receipt / metrics     │
└──────────────────────────────────────────────────┘
```

边界：增强后的 Hermes 自己拥有 Agent/harness，`apps/desktop` 是唯一目标 UI/Electron 入口；FastAPI 若保留只做薄领域传输和 DTO；Electron 只持有宿主能力；领域服务负责可测试的业务状态机；SQLite/Artifact Store 是唯一业务真相源。不是把所有营销逻辑塞进 `run_agent.py`，也不是保护现有 `engine/agent_core` 的文件形态，而是让账号、证据、内容、预演、发布、回执和学习成为 Hermes Agent 的内建能力，取消外层 adapter 对 Agent 生命周期的控制权。

### 内容生产主链

```text
UserGoal
  → CreatorModel / AccountContext
  → EvidencePack
  → ContentBrief
  → Agent Draft
  → PlatformVariant
  → AssetPack
  → PreflightDecision
  → HumanReview
  → PublishReceipt
  → MetricSnapshot
  → RetroCandidate
```

预演、记忆和学习不再是三个独立产品线，而是这条主链上的底层服务。

## 七、执行顺序

| 顺序 | ID | 工作 | 完成证据 | 状态 |
|---:|---|---|---|---|
| 1 | R0-00 | Hermes 主运行时原生增强 | `apps/desktop` 成为唯一 UI；Hermes 保持唯一 Agent 主干；Marketing OS 领域能力直接进入其工具和状态链；最终删除根目录旧 UI/IPC/adapter 主路径 | code + automated partial：原生身份/gateway/workbench/chat route/branding、账号读写首段、移动消息 HTTP 旁路删除已完成；其余领域迁移与旧主路径删除 pending |
| 2 | R0-01 | Hermes 增强分支可复现基线 | 当前 lock/patch 可复现；保持可直接开发、提交、构建的 Hermes 主源码边界 | automated complete：nested commit + tree lock + 12-patch replay；verifier/bootstrap 及 reproducibility tests passed；upstream integration CI pending |
| 3 | R0-02 | 打包 runtime 闭环 | Hermes/MCP 缺失 hard fail；冻结 backend 真实创建 session + L0；真实 Provider 对话和干净机待验 | packaged partial（结构、session、L0、MCP CLI 已通过） |
| 4 | R1-01 | 统一 ToolOutcome | blocked/error 不再被标 completed；审批等待/回执按 approval_id 投影；未知外部结果不自动重试 | automated complete（迁入 fork 后必须重验） |
| 5 | R1-02 | 图文真实生产纵切 | 原生工单 checkpoint、账号级 EvidencePack、ArticleBundle 和 ContentAsset 写入已接管；下一步用真实 Provider 生成一篇父稿/知乎与公众号变体并真人审稿，再建立主张级多源核对 | automated partial（plan→evidence capture→validated article bundle complete；real provider/human quality pending） |
| 6 | R2-01 | 发布单真相源 | 已确认 JSON/UI/SQL 双路径；暂不继续改，待 R0-00 迁移骨架确定后在新边界完成 | audit complete，implementation paused |
| 7 | R2-02 | 未校准预测降级 | 软文已只给 uncalibrated readiness；不露脸视频及其他生产路线仍需清除固定区间 | automated partial（soft article only） |
| 8 | R3-01 | 领域服务接入 Hermes | 取消 Tool Manifest → FastAPI server 反向依赖；Account/Evidence/Content/Publishing 成为 Hermes 内建领域端口 | code + automated + dev-runtime partial：Account 读写首段、SessionDB 账号作用域、移动消息原生路由、EvidencePack 首个 web collector、Content 工单 checkpoint/草稿资产已接入；Content 质量、Publishing pending |
| 9 | R3-02 | 单一账号浏览器 profile | 登录与后台托管复用同一身份，跨重启不重复扫码 | pending |
| 10 | R4-01 | 真人/打包验收门 | Electron UI E2E + 干净机 + 真实内容审稿 + 回执/指标闭环 | pending |

任何新功能在上述主链未闭环前，只能进入研究或独立 feature gate，不得进入默认产品路径。

## 八、证据等级

| 等级 | 含义 |
|---|---|
| designed | 有方案或台账，没有代码 |
| code | 有实现，尚未证明主链消费 |
| automated | 自动化覆盖真实模块边界，但外部系统可能是 fake/mock |
| dev-runtime | 当前开发机真实 runtime 验收 |
| packaged | 打包产物在无开发依赖环境验收 |
| human-loop | 用户用真实账号/内容完成端到端闭环 |

以后不再使用单一百分比掩盖不同证据等级。某模块只有 `code/automated` 时，不得写成“用户可用”。

## 九、如果由 Codex 全盘负责

我会冻结横向扩功能，以“每周完成一条可重复纵向闭环”为节奏：

1. 先保证 Agent 真正在客户机里存在并可恢复。
2. 再让它写出一篇用户愿意修改和发布的真实内容。
3. 再让一次发布拥有可靠回执和指标。
4. 再让下一篇内容真正消费上一次的反馈。
5. 最后才扩平台、视频质量、自动发布和技能自动沉淀。

产品价值不再用“有多少页面、工具、表和公式”衡量，而用两个问题衡量：用户是否得到真实可用的结果；系统下一次是否比上一次更懂这个用户和账号。
