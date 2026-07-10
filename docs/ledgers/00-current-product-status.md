# Marketing OS 当前产品总控

> 基线日期：2026-07-10
> 当前分支：`codex/product-architecture-checkpoint-2026-07-09`
> 作用：这是唯一的实时执行入口。`LEDGER.md` 与 `AGENT_CORE_LEDGER.md` 保留第一版产品宪法；其余编号台账是领域历史和实现证据，不再各自宣布“当前主线”。
> **2026-07-10 内核纠偏（最高优先级）：Marketing OS 必须是 Hermes 源码的产品化 fork，不是一个调用 Hermes 的外层应用。** 本条覆盖历史资料中“业务差异优先放 adapter/插件”“产品业务逻辑仍留在 `engine/agent_core`、Hermes 只承载少量 runtime patch”“改动最小化”等旧约束。`run_agent.py`、SessionDB、model tools、gateway、cron、memory、skills、plugins、TUI 和 `apps/desktop` 均可按产品体验深度重构；上游可重放/可 rebase 不再高于产品正确性。

## 一、第一版没有变的目标

Marketing OS 不是“营销页面加一个聊天框”，也不是一组热点、写作、发布工具。第一版真正要交付的是一个受控、持续、会学习的账号经营 Agent：

1. Marketing OS 直接从 Hermes 源码演化；Hermes 的 Agent loop、harness、session、长任务、记忆、技能和渠道能力是产品自身代码，不是被外层服务调用的第三方内核。
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

## 二、产品目标没有跑偏，但内核归属和工程顺序都跑偏了

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

结论：没有跑偏的是“做一个长期经营账号的真 Agent”；有两处根本偏差：一是先把未来能力、公式、工具和台账做得很满，再补真实内容与交付闭环；二是把 Hermes 当成 `AIAgent` 依赖，由外部 `HermesAgentService` 接管产品 harness，结果变成“Marketing OS 壳 → adapter → Hermes”。

## 三、2026-07-10 代码事实

以下数字只描述工程规模，不代表产品完成：

| 事实 | 当前证据 |
|---|---|
| 主仓库 | 298 个跟踪文件；外层 Git 以本文档所在提交为当前产品基线 |
| Agent 工具 | 60 个：29 L0、25 L1、5 L2、1 L3 |
| 本机 API | `engine/marketing-os/server.py` 约 4598 行、126 个 FastAPI 路由 |
| 状态仓库 | `engine/agent_core/store.py` 约 2969 行，任务、记忆、内容、发布、账号经营和学习集中在单类 |
| Electron host | `electron/main.js` 约 2427 行，窗口、浏览器、渠道、文件、API 代理、发布和进程生命周期集中在单文件 |
| Agent adapter | `engine/agent_core/hermes_adapter.py` 约 1757 行，session、任务、计划、证据、回复修复和工具事件集中在单类 |
| 两套桌面 UI | 当前产品壳为根目录 `src/` + `electron/`；Hermes fork 自身已有 `apps/desktop/`（Electron + React、原生 chat/session/skills/messaging/cron/approval/settings，约 437 个 src 文件）。继续维护前者会形成第二套壳 |
| 自动化 | 2026-07-10 当前工作树全量 Python：1325 passed，TypeScript `tsc --noEmit` 通过，秘密扫描通过；1 个已知 Starlette/httpx 弃用警告 |
| 构建 | backend 43MB、Hermes 发行源树 39MB、MCP+Chromium 407MB；Electron x64 DMG 约 352MB（未签名） |
| Hermes fork | 嵌套产品分支 `codex/marketing-os-runtime` 已提交至 `40df58bd5`；上游 SHA + 产品 tree `ef138cf55c86` + 八个 checksummed patch 已锁定，nested repo clean，bootstrap/verifier 可得到同一 tree |
| 打包验收 | 包内 Hermes manifest/source、MCP CLI/Chromium 均通过结构 hard gate；冻结 backend 真实创建 Agent session 并调用 L0，未调用外部模型 |

### 自动化不能证明的事情

- `tests/test_e2e_01_internal_chain.py` 明确不启动 Hermes，外部 MCP 使用 mock。
- 没有真实 Electron UI E2E、干净机持续对话、真实发布、自动指标回收或跨天经营验收。
- packaged smoke 尚未在一台没有本项目、Python、Node/Hermes 的干净 macOS 上执行，也未覆盖真实 Provider 对话。
- 1325 个测试证明工程地基较强，不证明用户已经拿到完整产品闭环。

## 四、已确认的结构性问题

### P0-00 当前仍是 Hermes 套壳，不是 Hermes 产品 fork

当前主对话由 `engine/marketing-os/server.py` 创建 `engine/agent_core/hermes_adapter.py::HermesAgentService`；这个约 1757 行的外层类拥有产品 session、AgentTask、计划推断、证据守门、工具事件、暂停恢复和回复修复，再在内部 import `runtime/hermes-agent/run_agent.py::AIAgent`。营销工具、审批和业务 prompt 也主要位于外层 `engine/agent_core`。Hermes fork 当前产品提交只有渠道 bridge 等极少改动。这证明代码“运行了 Hermes 源码”，但不等于“从 Hermes 源码改造成 Marketing OS”。

纠偏目标：Hermes fork 成为唯一 Agent Runtime 和产品 harness 的代码归属。Agent 身份、系统上下文装配、结构化计划、step checkpoint、工具注册与中间件、审批/effect、长任务恢复、记忆检索/沉淀、技能选择/生成、渠道路由和事件流必须在 fork 的原生执行链里完成。Electron 仍负责系统秘密、窗口、账号 profile 和外部副作用；账号/内容/发布等领域模型仍可保持独立模块和 SQL 真相源，但它们必须作为 Hermes 产品 fork 的领域能力被调用，不能再由一个外层 adapter 反过来拥有 Agent。

UI 同样必须纠偏。`runtime/hermes-agent/apps/desktop` 已经拥有 Hermes 原生 Electron/React 桌面端、JSON-RPC gateway、会话历史、聊天流、工具审批、skills、messaging、cron 和 settings；它应成为 Marketing OS 唯一桌面前端母体。根目录现有 `src/` + `electron/` 只作为账号罗盘、内容工厂、平台登录等已验证交互的迁移来源，不能继续作为永久主壳。迁移达到功能对等后删除旧入口和旧构建链，不长期维护两套 UI、两套 session 和两套 IPC。

“可以爆改”代表源码所有权，而不是把代码写成新的巨石。仍需保留确定性状态机、领域边界、安全审批、可迁移数据和回归测试；但只要最终体验需要，就直接改 Hermes 的原生执行路径，不再先造一层 adapter、bridge、sidecar 或代理来回避修改。

这也不是一场单向的“把 Marketing OS 搬进 Hermes”。Hermes 继承代码和当前 Marketing OS 代码都允许拆分、删除和重写：前者提供成熟的 Agent/harness/session/desktop 骨架，后者提供账号经营、证据、内容、预演、发布回执和学习闭环。迁移按最终能力边界重新组合，不按任一旧目录原样照搬。唯一不可丢的是产品设计哲学：围绕一个用户和一组账号长期经营，用真实证据行动，用真实结果学习，最终表现为同一个超级营销 Agent。

2026-07-10 原生切入基线已落地：fork 内新增唯一产品身份 `marketing_os/product.py`，默认 Agent identity 和系统指导直接由 fork 装配；`tui_gateway` 原生暴露产品状态；`apps/desktop` 根路由成为原生工作台，对话迁至 `/chat` 并兼容旧会话路由；安装包、窗口、协议、导航、通知和多语言用户文案统一为 Marketing OS。生产构建、类型检查、lint、3 个 Python 契约、10 个定向 UI 契约、14 个二级窗口路由契约均通过。该基线证明 fork 已可直接承载产品，但账号、证据、内容、发布和学习领域能力仍在迁移前，不能写成“套壳已经全部清除”。

第一条领域纵切也已启动：fork 内的 `AccountContextRepository` 不回调 FastAPI、不复制数据，直接以只读方式消费现有 `accounts.json + agent_core.db` 真相源；原生 Gateway 提供 `marketing.accounts.list` 与 `marketing.account.context`，原生工作台已读取真实账号数量。6 个定向 Python 契约通过，并在本机真实数据上读到 1 个抖音账号；该账号当前生命周期仍为 `not_started`、没有 DNA/真实受众快照，这是真实数据缺口，不做 UI 伪填充。写入所有权和 schema migration 尚未迁入 fork。

同一投影已注册为 Hermes 原生 `marketing` toolset：`marketing_read_accounts` 与 `marketing_read_account_context` 默认进入桌面、消息渠道和 cron 的核心工具集。真实工具 dispatcher 已在本机读取账号 `acct_194dedab3145` 并返回 `not_started → draft_audience_hypothesis`，不经过外层 `HermesAgentService/tool_manifest/FastAPI`。这完成了“UI 能看”到“Agent 自己能取证”的第一步；会话级账号绑定见下一段，账号领域写入仍待迁移。

会话级账号绑定已经进入 fork 原生 SessionDB，而不是 UI 临时状态：`sessions` 直接保存 `marketing_user_id/marketing_account_id`，新对话从工作台选中账号后随 `session.create` 一次绑定，历史恢复、分支和压缩后继会话自动继承。账号作用域只把稳定路由 ID 放入缓存友好的会话提示，动态 DNA、受众、生命周期和指标仍必须调用原生账号工具取最新事实；首次模型调用后禁止在原会话偷换账号，避免多账号串记忆。没有账号的用户绑定 `prospect_*` 作用域，可从自然对话建模。该纵切通过 303 个 SessionDB/产品定向测试、75 个 Gateway protocol 测试、19 个 UI 定向测试、完整 Desktop lint/typecheck/production build；尚未完成真实用户点击与跨重启人工验收，其余账号领域写入仍在旧业务层。

账号写入的第一段所有权也已进入 fork：`AccountLifecycleRepository` 原生初始化并写入版本化 `account_strategy_projects/audience_hypotheses`，支持经营目标、受众草案和显式用户确认；`marketing_update_account_lifecycle` 只有一个动作入口，不接受模型提供的账号 ID，dispatcher 按 SessionDB 强制写当前会话绑定账号，跨账号 read/write 会被拒绝。确认前不推进生命周期，确认后从同一真相库读回 `audience_hypothesis_ready`。本段 380 个 SessionDB/产品/Gateway 回归通过；定位、对标、实际受众、实验等剩余 schema 的写入所有权与旧库升级迁移仍待逐段接管，不能宣称 Account 领域已全部迁完。

Hermes 生态兼容被明确保留：原生 MCP catalog/自定义 MCP、MCP 动态工具发现，Hub Skill 安装更新、用户 Skill、Skill 自我生成治理，以及插件安装更新仍沿用 Hermes 合同。核心代码升级与生态包升级分离：Marketing OS 运行时禁止直接执行原地 `hermes update` 覆盖产品 fork，核心上游变化必须进入 Marketing OS 版本并经过产品回归；MCP server、Hub Skill、用户 Skill 和插件继续独立更新。Gateway 产品状态和 dashboard update API 会返回该政策，CLI 产品运行时也 fail-safe 阻断 raw apply。48 个 Hermes 原 updater/产品 updater 回归通过，证明非产品 Hermes 模式未被破坏；尚待建立定期 upstream merge/rebase CI，把“可升级”从人工纪律提升为自动维护流水线。

### P0-00 迁移映射（当前 → 唯一目标）

| 当前旁路 | 目标归属 | 收口条件 |
|---|---|---|
| 根目录 `src/` + `electron/` | Hermes fork `apps/desktop` | 迁入工作台、账号管理、内容工厂和平台 profile 后删除旧应用入口 |
| `engine/agent_core/hermes_adapter.py` | fork 的原生 Agent/gateway runtime | session、stream、plan、checkpoint、interrupt、resume 不再由外层类代理 |
| `engine/agent_core/tool_manifest.py` + 动态 import `server.py` | fork 原生 tool registry/middleware + typed domain ports | 工具注册、审批、effect 和结果契约在 Hermes dispatch 链内生效 |
| 外置 AgentTask/plan/checkpoint 解释层 | fork SessionDB/agent loop 的结构化任务协议 | 不再从模型文本猜计划，不再靠 resume prompt 冒充精确恢复 |
| 独立 channel bridge | fork gateway/platforms | 微信、飞书和桌面对话进入同一 Marketing OS session/harness |
| `engine/marketing-os/server.py` 巨型控制器 | fork gateway RPC + 薄领域服务 API | server 不再拥有 Agent 生命周期，只保留必要的平台/领域端口 |
| Account/Content/Publishing/Feedback SQL | 保持独立领域真相，但由 fork 内建能力直接消费 | 不复制数据、不建立第二套记忆/任务库 |

迁移期间允许旧链只读兼容，但禁止再向旧 UI、旧 adapter 或旧 JSON 状态源增加新功能。每完成一条纵向能力就切换默认入口并删除对应旧写路径，避免“新架构完成了、旧架构也永远留着”。

### P0-01 Hermes 源码与包内运行时已形成 packaged smoke，干净机仍待验

此前开发机依赖一个被主仓库忽略且自身 dirty 的 `runtime/hermes-agent`。2026-07-10 已将真实 fork 改为“固定上游 commit + 产品 tree + checksummed patch series”，bootstrap 遇 dirty/未知 revision hard fail，自动化可从 baseline 重建相同 tree；未接入且无来源的泛化 skill 草稿已清除。构建现会生成 39MB 受校验发行源树，并把 Hermes 核心依赖编入冻结 backend；包内 backend 已真实创建 session 和调用 L0。剩余阻断是干净机、代码签名、真实 Provider 对话和 Electron UI 验收。

### P0-02 工具结果与审批状态契约（已完成 automated 修复）

旧实现会把业务 handler 的 `blocked/error` 再包装成顶层 `status=ok`，并把 `pending_approval` 计划步骤误写为 `failed`；审批后的 effect 回执也不会完成原步骤。2026-07-10 已修复为统一顶层 `ToolOutcome`，增加 `running → waiting_approval → completed/failed/skipped` 确定性投影、旧任务修复、精确 `approval_id/effect_id` 绑定和未知外部结果禁止自动重试。相关 83 个定向测试和 1325 个全量测试通过；真实 Electron 审批续跑仍属于 R4 人工验收。

### P0-03 内容工厂还不是高质量内容生产系统

不露脸脚本和部分镜头仍来自确定性模板；固定播放区间和启发式常数会制造“数学上很专业”的错觉。软文路线已完成第一轮边界修复：Hermes 必须提供真实父稿和知乎/公众号改写，确定性代码只校验结构、证据引用、平台差异并保存资产；缺正文只保存 scaffold，复制父稿冒充平台改写会被阻断，未校准时不自动写评分或流量区间。真实 Provider 写稿和真人审稿仍待 R4 验收。

### P0-04 发布存在双真相源

旧 `publishing.json` 与新 SQL publishing task/receipt/checkpoint 同时存在。部分 UI 创建和分析仍读旧 JSON，真实 SQL 回执反而没有完整进入分析。必须一次迁移后停止写旧路径。

### P1-01 浏览器存在两个身份世界

前台登录主要使用 Electron partition，后台托管使用 Playwright MCP profile，失败时还可能回退 Electron DOM。用户登录一次却仍被要求再次扫码，根因就在这里。目标是每个平台账号一个持久 profile，需要交互时 headed，后台时复用同一身份执行。

### P1-02 巨石模块与反向依赖

Tool Manifest 通过动态 import 调用 FastAPI `server.py` 内部函数，领域层反向依赖接口层；server、store、Electron main 和 adapter 都已成为巨石。后续只按纵向闭环拆 service/repository，不重建第二套数据库或第二个 Agent。

### P1-03 台账不再是事实源

旧总台账仍写 19 个工具、61%/72% 和不同“当前入口”；15 号台账已超过千行且章节乱序。以后工具数、版本、启用能力和测试事实由代码生成；手工台账只记录产品判断、验证等级、阻断和下一步。

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

边界：Hermes fork 的 `apps/desktop` 是唯一 UI/Electron 入口；FastAPI 若保留只做薄领域传输和 DTO；Electron 只持有宿主能力；Marketing OS Hermes fork 自己拥有 Agent/harness；领域服务负责可测试的业务状态机；SQLite/Artifact Store 是唯一业务真相源。不是把所有营销逻辑塞进 `run_agent.py`，也不是保护现有 `engine/agent_core` 的文件形态，而是同时拆解两边代码，让账号、证据、内容、预演、发布、回执和学习成为原生 Agent 的内建能力，取消外层 adapter 对 Agent 生命周期的控制权。

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
| 1 | R0-00 | Hermes 产品 fork 纠偏 | `apps/desktop` 成为唯一 UI；fork 成为一等产品源码；Agent 生命周期不再由外层 `HermesAgentService` 拥有；建立逐段迁移与兼容测试，最终删除根目录旧 UI/IPC/adapter 主路径 | code + automated baseline：原生身份/gateway/workbench/chat route/branding 已完成；领域迁移与旧主路径删除 pending |
| 2 | R0-01 | Hermes fork 可复现基线 | 当前 lock/patch 可复现；下一步改成可直接开发、提交、构建的产品 fork 源码边界 | automated complete：nested commit + tree lock + 8-patch replay；verifier/bootstrap 及 reproducibility tests passed；upstream integration CI pending |
| 3 | R0-02 | 打包 runtime 闭环 | Hermes/MCP 缺失 hard fail；冻结 backend 真实创建 session + L0；真实 Provider 对话和干净机待验 | packaged partial（结构、session、L0、MCP CLI 已通过） |
| 4 | R1-01 | 统一 ToolOutcome | blocked/error 不再被标 completed；审批等待/回执按 approval_id 投影；未知外部结果不自动重试 | automated complete（迁入 fork 后必须重验） |
| 5 | R1-02 | 图文真实生产纵切 | Agent 正文/双平台变体进入 ContentAsset；缺正文、缺引用、复制/重复变体均阻断；不自动评分 | automated partial（迁入 fork 后必须重验） |
| 6 | R2-01 | 发布单真相源 | 已确认 JSON/UI/SQL 双路径；暂不继续改，待 R0-00 迁移骨架确定后在新边界完成 | audit complete，implementation paused |
| 7 | R2-02 | 未校准预测降级 | 软文已只给 uncalibrated readiness；不露脸视频及其他生产路线仍需清除固定区间 | automated partial（soft article only） |
| 8 | R3-01 | 领域服务接入 fork | 取消 Tool Manifest → FastAPI server 反向依赖；Account/Content/Publishing 作为 fork 内建领域端口 | code + automated + dev-runtime partial：Account 只读投影、Gateway、原生 toolset、SessionDB 会话作用域、工作台选账号，以及经营目标/受众草案/确认写入已接入；真实账号读取已验。其余 Account 写入、Content、Publishing pending |
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
