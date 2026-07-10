# Marketing OS 当前产品总控

> 基线日期：2026-07-10
> 当前分支：`codex/product-architecture-checkpoint-2026-07-09`
> 作用：这是唯一的实时执行入口。`LEDGER.md` 与 `AGENT_CORE_LEDGER.md` 保留第一版产品宪法；其余编号台账是领域历史和实现证据，不再各自宣布“当前主线”。

## 一、第一版没有变的目标

Marketing OS 不是“营销页面加一个聊天框”，也不是一组热点、写作、发布工具。第一版真正要交付的是一个受控、持续、会学习的账号经营 Agent：

1. Hermes 是持续运行的智能内核，桌面应用是账号、数据、内容和外部动作的身体。
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

## 二、当前没有根本跑偏，但工程顺序跑偏了

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

结论：没有跑偏的是“做一个长期经营账号的真 Agent”；跑偏的是“先把未来能力、公式、工具和台账做得很满，再补真实内容与交付闭环”。

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
| 自动化 | 2026-07-10 当前工作树全量 Python：1325 passed，TypeScript `tsc --noEmit` 通过，秘密扫描通过；1 个已知 Starlette/httpx 弃用警告 |
| 构建 | backend 43MB、Hermes 发行源树 39MB、MCP+Chromium 407MB；Electron x64 DMG 约 352MB（未签名） |
| Hermes fork | 外层 Git 忽略的嵌套 checkout；上游 SHA + 产品 tree + checksummed patch series 已锁定，nested repo clean，临时目录重放可得到同一 tree |
| 打包验收 | 包内 Hermes manifest/source、MCP CLI/Chromium 均通过结构 hard gate；冻结 backend 真实创建 Agent session 并调用 L0，未调用外部模型 |

### 自动化不能证明的事情

- `tests/test_e2e_01_internal_chain.py` 明确不启动 Hermes，外部 MCP 使用 mock。
- 没有真实 Electron UI E2E、干净机持续对话、真实发布、自动指标回收或跨天经营验收。
- packaged smoke 尚未在一台没有本项目、Python、Node/Hermes 的干净 macOS 上执行，也未覆盖真实 Provider 对话。
- 1325 个测试证明工程地基较强，不证明用户已经拿到完整产品闭环。

## 四、已确认的结构性问题

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
│ Application Core                                │
│ Conversation | Account | Evidence | Content     │
│ Publishing | Feedback | Learning                │
└────────┬───────────────┬─────────────────────────┘
         │               │
┌────────▼───────┐  ┌────▼─────────────────────────┐
│ Hermes Runtime │  │ SQLite truth + artifact store│
│ reasoning loop │  │ task/memory/content/receipt  │
└────────────────┘  └──────────────────────────────┘
```

边界：FastAPI 只做路由和 DTO；Electron 只持有宿主能力；Hermes 负责推理和工具循环；Application Core 负责业务状态机；SQLite/Artifact Store 是唯一业务真相源。

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
| 1 | R0-01 | Hermes fork 可复现基线 | lock + checksummed patch series；nested dirty hard fail；baseline 临时重放得到相同 product tree | automated complete（待远端 clean clone 网络验收） |
| 2 | R0-02 | 打包 runtime 闭环 | Hermes/MCP 缺失 hard fail；冻结 backend 真实创建 session + L0；真实 Provider 对话和干净机待验 | packaged partial（结构、session、L0、MCP CLI 已通过） |
| 3 | R1-01 | 统一 ToolOutcome | blocked/error 不再被标 completed；审批等待/回执按 approval_id 投影；未知外部结果不自动重试 | automated complete（83 定向 + 1325 全量；待 R4 真人验收） |
| 4 | R1-02 | 图文真实生产纵切 | Agent 正文/双平台变体进入 ContentAsset；缺正文、缺引用、复制/重复变体均阻断；不自动评分 | automated partial（27 内容生产测试 + 1325 全量；真实 Provider/人工审稿待验） |
| 5 | R2-01 | 发布单真相源 | JSON 一次迁移到 SQL；工作台、回执、指标、复盘只读 SQL | pending |
| 6 | R2-02 | 未校准预测降级 | 软文已只给 uncalibrated readiness；不露脸视频及其他生产路线仍需清除固定区间 | automated partial（soft article only） |
| 7 | R3-01 | Application Core 拆分 | Tool Manifest 不再 import server；首批 content/publishing service + repository | pending |
| 8 | R3-02 | 单一账号浏览器 profile | 登录与后台托管复用同一身份，跨重启不重复扫码 | pending |
| 9 | R4-01 | 真人/打包验收门 | Electron UI E2E + 干净机 + 真实内容审稿 + 回执/指标闭环 | pending |

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
