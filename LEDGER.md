# 智能营销桌面 Agent — 项目总台账

> 2026-07-10 说明：本文件保留 2026-07-01 冻结时的产品宪法与历史快照，其中工具数、进度百分比和“下一步”不再代表当前代码。实时状态与唯一执行入口见 `docs/ledgers/00-current-product-status.md`。

> 冻结基线：2026-07-01（抖音登录与自动公共热点已真人验收；MCP 浏览器重构进入实施；后续执行状态只更新 `docs/ledgers/` 子台账）
>
> 统一进度口径：完整产品约 `61%`；桌面端第一版可试用约 `72%`。沿用 2026-06-29 的同一分母，不因远期 Web 模块临时改变权重。
>
> 用户确认的冻结口径：桌面 Agent 基础架构 85%、对话/任务/审批/记忆 72%、抖音登录与热点采集 75%、长期学习与账号 DNA 40%、自动发布与指标复盘 20%、打包交付 60%、Web 视频仅接口契约。后续统一按这一分母计算。
>
> 计分规则：数据库字段、状态机、接口、Fake/单元测试和 UI 占位只算工程地基；必须接入真实 Agent 主链并完成相应真人/跨重启/平台验收后，才能计入产品完成度。P1-06 等局部闭环先作为 75% 模块内部质量提升记录，不单独改变四舍五入后的 61%/72%。
>
> 口径：只记录与 `docs/architecture/REBUILD_BASELINE.md`、`docs/research/` 和 `AGENT_CORE_LEDGER.md` 一致的实现。旧插件、CLI 采集、后端秘密存储和伪完成记录不再保留。本文件在本次定版后不再承载逐日任务流水或 Claude 回填。
>
> 视频生成本轮只保留 `VIDEO_WEB_CONTRACT.md`，不计入桌面主链完成度。

## 一、唯一目标架构

| 层 | 唯一责任 | 当前代码 |
|---|---|---|
| React | 目标、进度、证据、任务恢复和业务页面 | `src/` |
| Electron | 桌面窗口、秘密、Keychain、本机进程生命周期和外部副作用 host | `electron/` |
| MCP 浏览器层 | 每账号独立 Playwright 进程/profile、首次可见登录、后台页面观察与受控操作 | `engine/agent_core/mcp_broker.py` + account-scoped manager（待实现） |
| Agent Core | Hermes adapter、稳定 session、AgentTask、事件、策略、审批/effect 数据模型 | `engine/agent_core/` |
| 营销引擎 | 只提供结构化营销领域能力，不拥有浏览器和秘密 | `engine/marketing-os/marketing_tools/` |
| Hermes Runtime | 固定上游源码与确有必要的 fork patch，不存业务数据 | `runtime/hermes-agent/` |
| Web 视频工作台 | 通过既定契约共享同一任务、上下文与事件流，不建立第二个 Agent | `VIDEO_WEB_CONTRACT.md` |

数据边界：Cookie 只留在账号专属 Playwright profile，Token/Key 留在 Electron/系统 Keychain；Agent 只能看登录状态、脱敏指标和业务结果。Agent 不拥有任意 Shell、安装程序、任意文件或系统设置能力。

## 二、当前代码实况

| ID | 能力 | 当前实现 | 状态 |
|---|---|---|---|
| DESK-01 | 桌面壳与本机服务 | Electron 管理窗口、托盘、FastAPI 生命周期、崩溃拉起和带令牌 IPC | ✅ code |
| DESK-02 | 平台登录 | 每个账号使用独立 `persist:marketing-os-platform-{platform}-{accountId}` session；弹出完整官方登录浏览器，由用户自行扫码/验证；只以真实认证 Cookie 判定成功 | ✅ 抖音双账号真人登录、隔离、退出与删除已通过 |
| DESK-03 | 浏览器窗口边界 | 平台登录按当前决策使用完整独立窗口；平台自身新弹窗仍被约束在同一窗口；后台采集不显示窗口 | ✅ code + boundary test |
| DESK-04 | 会话健康 | Electron 检查认证 Cookie、过期和缺失状态，前端直接读取该结果 | 🟡 平台级规则需逐个平台验收 |
| DESK-05 | 登录态行业采集（增强项） | 抖音搜索复用 Electron session，结构化结果再进入后端；不再作为公共热点主链前置条件 | 🟡 DOM 选择器当前取不到结果，单独列为增强项 |
| DATA-01 | 自动公共热点 | HotTopics 聚合源与 Bilibili 官方公共接口并行；单源 8 秒止损、15 分钟自动刷新、失败保留上次有效缓存 | ✅ 4/4 真人网络通过；120 条原始证据，Top30 按 8/8/7/7 跨平台均衡 |
| DATA-02 | 账号数据 | 后端只保存元信息和 Electron 同步的脱敏指标；每次同步追加监控快照 | ✅ code |
| DATA-03 | 证据整理 | 确定性去重、分类并保留平台、后端、URL、排名、采集时间和失败信息 | ✅ code |
| DATA-04 | 选题候选 | 规则层只生成“待 Agent 判断”的证据候选，不预测流量、不冒充最终策略 | ✅ code |
| AGENT-01 | Hermes 源码接入 | 后端进程直接实例化 `AIAgent`，不再为每条消息启动 CLI | ✅ code |
| AGENT-02 | 稳定会话 | 用户/工作区绑定持久 product session，Hermes transcript 使用独立 SQLite | ✅ code，真实模型连续对话待验收 |
| AGENT-03 | 持久任务与事件 | AgentTask、`task_events`、SSE、暂停/恢复/取消已接入；审批成功、失败和拒绝均会恢复原任务，可见计划仍是启发式而非确定性 checkpoint | 🟡 交互续跑已修，精确续跑未完成 |
| AGENT-04 | 最小工具集 | manifest 当前为 13 个 L0 + 2 个 L1 + 3 个 L2 + 1 个 L3，共 19 个；L3 publish 仅为受审批的本地占位执行器，不代表真实平台发布。Agent 自授权工具已移除 | 🟡 18 个 L0-L2 可作当前主链地基；L3 不计产品完成 |
| AGENT-05 | 权限与秘密 | L0–L4 fail-closed；事件持久化递归脱敏；受控/副作用能力无 bridge 时拒绝 | ✅ foundation |
| AGENT-06 | 审批与 effect | Electron main 先从后端批准并取得 canonical capability/args，再执行并写 receipt；审批卡、session scope、登录完成回执及 worker 续跑已修 | 🟡 自动过期与取消事务已接生产链路；真人 Electron 四路径待验收 |
| AGENT-07 | 自然对话 | 寒暄不自动分析营销数据；营销请求由同一 Hermes 会话决定是否读取工具 | ✅ code，真实模型回归待做 |
| MSG-01 | 微信/飞书 | 仅作为同一 Agent 的沟通 surface；扫码、状态和发送桥代码保留 | 🟡 真人扫码、收发、重连未验收 |
| WEB-01 | Web 视频工作台 | SSO、project/task/event/artifact 契约已预留 | 📐 contract only |
| PKG-01 | 桌面打包 | PyInstaller 收集 `agent_core` 与 `marketing_tools`；Electron 资源路径改为 `engine/` | 🟡 源码 runtime 随包和干净机仍未验收 |

## 三、2026-06-29 架构清理台账

| ID | 已清理内容 | 结果/原因 |
|---|---|---|
| CLEAN-01 | 后端 Chrome/CDP、Agent-Reach、MediaCrawler、小红书 Cookie 后端 | 删除；平台登录态采集只能由 Electron session host 执行 |
| CLEAN-02 | Bitwarden、密码/Cookie/API Key 后端字段和 CLI 路径 | 删除；后端账号模块改为纯元信息边界 |
| CLEAN-03 | 每条消息调用 Hermes CLI、旧 `/assistant/message` | 删除；统一到长驻 `HermesAgentService` 和 `/agent/*` |
| CLEAN-04 | 营销包顶层名称 `tools` | 改为 `marketing_tools`，避免遮蔽 Hermes 自己的 `tools.registry` |
| CLEAN-05 | 旧 Hermes plugin manifest、`register(ctx)` 和 dashboard API | 删除；业务工具只由 Agent Core gateway 注册 |
| CLEAN-06 | 会返回 npx/安装/发布命令的旧 orchestration、视频和发布流水线 | 删除；未接持久审批/effect 的能力不注册 |
| CLEAN-07 | 非预期弹窗和假登录 | 去掉 detached DevTools、页面跳转即成功、取消时强收 Cookie；平台登录按用户最终决策显式打开完整窗口，仅认证 Cookie 可完成登录 |
| CLEAN-08 | `defaultSession` 共用登录态 | 删除；已升级为账号级持久 partition，并完成双抖音账号登录、退出、删除互不污染的真人验收 |
| CLEAN-09 | 后端第二次模型分析 | 删除；结构化证据由领域层整理，语义策略统一交给同一 Hermes session |
| CLEAN-10 | 项目内外部技能包、失效 skill、旧 release/build/cache | 删除；防止 CLI/CDP/自动安装方案被重新引用 |
| CLEAN-11 | 旧打包路径 `hermes-plugins` 和错误的 `collect-submodules tools` | 改为 `engine/`、`agent_core`、`marketing_tools` |
| CLEAN-12 | 架构回归测试 | 新增旧目录、外部采集器、`defaultSession`、detached DevTools、CLI Agent 和命名空间冲突检查 |

## 四、Claude 新增改动复核（2026-06-29 晚间）

### 已确认的有效推进

| 项目 | 复核结论 |
|---|---|
| 构建与测试 | Python `111 passed`；TypeScript、Electron 语法、Vite、PyInstaller 与完整 Electron 构建均通过 |
| Agent 数据地基 | 新增持久授权、memory candidate、content asset 与状态流转，结构和测试地基可继续使用 |
| 产品交互地基 | 新增审批卡、记忆管理页、内容资产页、账号选择及 `account_id` 消息参数 |
| 策略地基 | L2 在 gateway 创建持久审批；effect intent/receipt 具备幂等数据结构 |
| 架构边界 | 未重新引入外部 Chrome/CDP；Hermes 上游仍为干净基线，产品适配继续放在项目自有 adapter/gateway |

### 阻断与修正项

| 级别 | 问题 | 代码真相 / 修正标准 |
|---|---|---|
| 已修 | Agent 可自行授予永久授权 | 自授权 grant/revoke 已从 Agent manifest 和 server action 移除；当前 19 个 manifest 工具中只保留 2 个产品内可逆写入工具 |
| 已修 | capability 在校验审批前执行 | renderer 只提交 approval ID 与 scope；Electron main 从后端获取 canonical capability/args 后执行，不能由 renderer 拼接能力和参数 |
| 已修 | 审批卡无法稳定完成 | `task.waiting_user` 不再移除卡片；审批事件携带持久化原始参数，reject/effect receipt 才收起卡片 |
| 已修 | receipt 后任务不会续跑 | receipt 写入后调用 `resume_after_effect`，等待旧 worker 退出再恢复原任务；线程清理不会误删新 worker |
| 已修 | 登录 receipt 早于真实登录成功 | capability 登录等待认证 Cookie 确认；取消、加载失败、超时写失败 receipt，不再打开窗口即报成功 |
| 已修 | session / permanent 授权过宽 | session_id 已传递；持久和会话授权按稳定参数约束，例如平台及账号，不能从账号 A 扩张到账号 B |
| P1 | plan/checkpoint 仍是启发式 | `checkpoints_enabled=False`；计划从模型编号文本猜测，步骤按工具调用推断，`pending_approval` 也会被标完成。完成标准是结构化计划、确定性 step/effect checkpoint 和不重复副作用的重启回放测试 |
| 已修 | 账号与记忆隔离不完整 | 每轮通过不落入 transcript 的 turn context 重新绑定当前账号；memory 工具按内部 user/task provenance 和 account 过滤，已补跨用户/跨账号测试 |
| 已修地基 | 记忆质量守卫未闭环 | Agent 写入只形成 pending candidate，不能进入上下文；用户可确认、纠正、锁定、解锁或删除，只有 verified/locked 会被读取。自动证据晋升和 supersede 仍待补 |
| P1 | 内容资产不等于发布闭环 | 当前可创建、本地改状态，并注册了 1 个 L3 publish 占位工具；它只生成本地成功回执，没有真实平台发布、平台 post ID、指标回收或复盘关联 |
| 已修 | 状态数字相互矛盾 | 当前 manifest 实际为 19 个工具（13 L0 + 2 L1 + 3 L2 + 1 L3 占位）；Agent 面板读取 runtime `tool_count`。产品能力口径必须单独注明真实 L3 仍未闭环 |
| P1 | 测试未覆盖真实主链 | 99 个测试通过是好进展，但缺少“审批事件→卡片→main 预校验→执行→receipt→worker 恢复→任务结束”的端到端测试 |

### 用户授权自动化的产品规则

- 自动发布等低敏外部动作，可以在用户明确授权后按单次、本次会话或持久范围执行。
- 持久授权必须绑定用户、平台、账号、动作、内容类型和可选有效期；可随时撤销，每次执行都有请求、结果与失败 receipt。
- 授权只能由用户界面或用户明确确认产生；Agent 可以请求授权，但不能给自己授权、扩大范围或绕过校验。
- 删除、付费、广泛对外发送、账号安全与权限变更等高影响动作，继续使用更窄范围或逐次确认。

## 五、当前真实缺口

### P0：下一步必须打通

| ID | 缺口 | 当前真相 | 完成标准 |
|---|---|---|---|
| P0-01 | 真人抖音主链 | ✅ 登录和自动公共热点已通过；🟡 Hermes 行业筛选与证据化选题尚未真人闭环 | 用户扫码 → 自动公共热点 → Hermes 按行业筛选真实证据 → 给出可追溯选题 |
| P0-02 | 可见计划 | 🟡 产品执行器已在任务创建前生成结构化 PlanStep，plan.ready/updated 驱动 UI；工具完成确定性更新，未执行步骤标 skipped，综合输出标 completed | 真人复测计划先于工具可见；再与真实 checkpoint/跨重启恢复统一验收 |
| P0-03 | 精确任务恢复 | 当前是 resume prompt + 文本计划推断，`checkpoints_enabled=False`；虽然已有 completed_steps/executed_effects/pending_approval_id 字段与测试脚手架，但没有真实 Hermes step checkpoint 与跨重启回放闭环 | 结构化计划由执行器产生；每步持久 checkpoint；真实进程中断后从精确位置恢复，并证明不重复副作用 |
| P0-04 | Electron capability bridge | 🟡 执行前校验、canonical 参数、main host 与失败 receipt 已完成并有边界测试 | 真人 Electron 中完成“审批→登录态搜索/同步→receipt→Agent 续答” |
| P0-05 | 持久审批/effect 闭环 | 🟡 卡片、once/session/permanent、参数约束、登录真实回执和 worker 续跑已完成自动化验证 | 真人执行成功/拒绝/取消/超时四条路径，任务均进入正确终态 |
| P0-06 | 打包 runtime | 完整构建已生成 macOS ZIP/DMG；尚未证明干净机无需外置环境 | 干净 macOS 无外置 Hermes/Python 也能连续对话和调用当前 manifest 工具；L3 另按真实平台闭环验收 |
| P0-07 | 登录交互兜底 | ✅ 按当前产品决策使用独立完整浏览器窗口；二维码、短信、滑块均由用户在官方页面完成，成功后窗口自动关闭并保留本机会话 | 真人覆盖二维码、短信验证、滑块、取消及登录成功收起 |
| P0-08 | Agent 上下文账号绑定 | 🟡 单账号自动绑定、多账号强制选择、服务端二次校验；context/account 工具按 task account_id 过滤，memory 按 user/account 隔离 | 真人复测任务 account_id 非空；再切换两个账号确认历史、指标与建议不串号；补 project scope |
| P0-09 | 记忆内容质量守卫 | 🟡 pending 与有效记忆已分离；用户控制、supersede/证据晋升函数和测试地基存在；内部 task provenance 不再信任模型自报 evidence | 接入真实采纳/拒绝/发布指标；多次证据后才晋升；冲突、时间衰减和撤销在真实主链可验证 |

### P1：长期智能的核心

| ID | 缺口 | 完成标准 |
|---|---|---|
| P1-01 | 用户/账号/项目/结果记忆 | 🟡 五种 MemoryKind、治理 UI、workspace/account 过滤、supersede 与证据晋升函数/测试已存在 | 尚未由真实采纳、拒绝、发布结果和失败恢复持续驱动；不能把测试数据晋升当长期学习完成 |
| P1-02 | 账号 DNA 与用户决策 | 🟡 6 字段 schema、upsert/get、字段 supersede 与采纳/拒绝记录已有代码地基 | 尚未接真实账号运营多轮反馈、平台差异和发布表现；当前仍按 40%长期学习口径 |
| P1-03 | 内容资产、发布状态机和指标回收 | 🟡 本地 CRUD、SQL 状态机和 L3 占位工具已有测试地基 | 尚无真实平台发布、真实 receipt/post ID、定时指标回收、实验归因和下一轮策略调整；当前仍按 20% |
| P1-04 | 实验与策略权重 | 基于真实结果、时间衰减和替代解释更新，不由模型直接改权重 |
| P1-05 | 技能候选治理 | 重复成功流程经 staging、扫描、脱敏回放、审批和版本化后启用 |
| P1-06 | 账号级会话隔离与注销 | 同平台多账号独立 partition，切换、退出、删除和本地清理可控 | ✅ 双抖音账号真人完成登录隔离、无感指标同步、单账号退出与删除；另一账号全程保持认证和数据不受影响 |

### P2：扩展 surface

- 微信/飞书真人收发、解绑、重连与投递审计。
- Web 视频工作台按既定契约接入同一 AgentTask 和 artifact 流。
- macOS 签名/公证、Windows、升级/卸载与干净机矩阵。

## 六、验证基线

| 检查 | 当前结果 |
|---|---|
| Electron 主进程/预加载语法 | 通过 |
| TypeScript | `tsc --noEmit` 通过 |
| Python 自动化 | 当前测试集 `219 passed`；其中包含未采纳分支留下的工程测试，数量不计作产品进度；有效验收以本台账逐项真人证据为准 |
| 前端生产构建 | TypeScript + Vite build 通过 |
| 完整桌面构建 | PyInstaller + Electron builder 通过，生成 macOS ZIP/DMG；未签名/公证 |
| 旧路径静态反查 | 生产代码无外部 Chrome/CDP、Bitwarden、Agent-Reach、MediaCrawler、单轮 Hermes CLI |
| Hermes 上游工作树 | 基线 `4488fe1`，当前无需 fork patch；已存在的 session/callback/interrupt/tool registry 扩展点足够 P0 地基 |

## 七、统一进度与资料库对照（2026-06-30）

### 统一进度

| 模块 | 当前进度 | 资料库完成口径 | 主要差距 |
|---|---:|---|---|
| 桌面 Agent 基础架构 | 85% | Electron capability boundary + 持久 Agent service | 干净机 runtime、崩溃/升级恢复 |
| 对话、任务、审批、记忆 | 72% | durable task、持久 interruption、可治理 memory | 自动过期与取消事务已收口；精确 checkpoint 和真人 E2E 仍待验收 |
| 抖音登录与热点采集 | 75% | 登录、真实身份与指标同步可用；双账号隔离、退出和删除真人闭环 | 行业定向采集改走 MCP；补长期页面结构回放与失效重登测试 |
| 长期学习与账号 DNA | 40% | write→manage→read；结果/实验独立；技能候选治理 | 现有 schema/supersede/DNA 只是地基；缺真实反馈聚合、发布结果驱动、平台差异和技能 promotion |
| 自动发布与指标复盘 | 20% | effect intent/receipt/idempotency + publication/metrics/experiment | 无真实 L3 发布、无指标回收和归因 |
| 打包交付 | 60% | 干净机无外置依赖、签名、公证、升级回滚 | 仅本机构建通过 |
| Web 视频应用 | 契约阶段 | 同一 task/context/artifact/event，不建立第二 Agent | 尚未实现 |

完整产品约 `61%`；桌面端第一版可试用约 `72%`。今天的真实增量来自抖音真人登录、自动公共热点、跨平台均衡和 Hermes 只读证据检索；checkpoint、发布闭环和长期学习没有实质完成。

### 对照资料库后的工程判断

| 资料库原则 | 当前实现 | 判断 |
|---|---|---|
| Session 与 Harness 分离 | Hermes 持久 session + `HermesAgentService` + Product Event API | 🟡 运行地基已成，真实连续对话与重启恢复待验收 |
| Durable task 不能依赖进程活性 | AgentTask/Event/Pause/Resume 与 checkpoint 字段已存库 | 🔴 字段和单测不等于恢复闭环；仍是 resume prompt + 文本计划，Hermes `checkpoints_enabled=False` |
| 审批是可序列化 interruption | ApprovalRequest、卡片、effect receipt 已存在 | 🟡 Electron 模式生产调度会自动过期；取消任务与废止 pending approval 同事务；真人四路径仍待验收 |
| Effect receipt 是副作用真相源 | intent/receipt/idempotency 与 L3 占位执行器存在 | 🟡 占位成功回执不是平台事实；真实发布与指标回收仍为 0 |
| Memory 是 write→manage→read | pending→verified/locked、纠正/遗忘、scope/supersede/DNA 函数已存在 | 🟡 缺真实运营反馈和发布结果持续写入、冲突评估、时间衰减及策略消费闭环 |
| 外部内容是证据，不是记忆 | 热点只进 evidence cache，不自动写用户偏好 | ✅ 当前边界正确 |
| 技能必须 candidate→replay→approve→version | 仅有 Hermes 原生能力和原则文档 | 🔴 产品技能治理未实现 |
| 评测必须覆盖真实任务 | 自动化、Vite/TS/Electron 语法通过；双账号登录、同步、退出和删除真人通过 | 🟡 仍缺 MCP 行业数据进入真实模型回答、精确跨重启 checkpoint、真实发布和平台结构变化回放 |

## 八、2026-06-30 阶段验收

| 验收项 | 结论 | 当前证据 | 不包含的范围 |
|---|---|---|---|
| 抖音登录 | ✅ 阶段完成 | 创作者中心完整窗口真人扫码；双账号独立 partition；登录、公开身份与指标同步、退出、删除互不污染 | 其他平台未逐一验收 |
| 自动热点采集 | ✅ 阶段完成 | App 启动自动刷新、每 15 分钟更新；4 平台并行；单源 8 秒止损；失败保留旧缓存；真实刷新 4/4 成功 | 当前不是行业定向搜索；独立公共来源数量仍需逐步增加 |
| 登录态抖音行业搜索 | 🟡 待 MCP 重构 | Electron 会话已能提供账号隔离与授权边界；旧 DOM/网络硬编码不作为最终浏览器方案 | 使用 Playwright MCP 和专项抖音 MCP 后重新真人验收 |
| Hermes 热点智能 | 🟡 公共证据地基 | 公共热点缓存与只读工具存在 | MCP 数据接入、真实模型回答和证据追溯仍待验收 |

## 九、Claude 已完成任务复核

### CLAUDE-NEXT-01：公共热点 → Hermes 行业证据简报（🟡 代码完成，真人验收待做）

**目标**

用户在 Agent 对话中说“整理 AI 行业今天值得关注的热点，并给我 3 个适合抖音的选题”时，Hermes 必须直接读取已经自动更新的公共热点缓存，按行业筛选并输出可追溯证据；不得要求用户再点刷新、重新登录或批准登录态搜索。

**只允许修改的范围**

- `engine/marketing-os/server.py`：增加只读的缓存检索函数；不得发起浏览器或第二次模型调用。
- `engine/agent_core/tool_manifest.py`：增强现有 `marketing_read_trends` 的只读参数和描述；优先保持工具总数不变。
- `engine/agent_core/hermes_adapter.py`：只允许补证据优先的 system prompt/工具选择规则，不得重写 session、worker、审批或 checkpoint。
- `tests/test_server.py`、`tests/test_agent_core.py`、必要时 `tests/test_content.py`：增加本任务回归测试。
- 如确实需要，可小改 `scripts/run-agent-e2e.py` 以执行真人对话验收；不得改登录和趋势页面视觉。

**必须实现**

1. `marketing_read_trends` 支持可选 `query`、`platform`、`limit`，只搜索本机已缓存的真实热点；不访问 Cookie，不触发 L2 审批。
2. 检索结果保留 `title`、`source_platform`、`source_backend`、`url`、`rank`、`collected_at/cached_at`、缓存新鲜度和来源错误。
3. 行业无匹配时返回明确空结果；不拿无关娱乐热点凑数，不生成假热点。
4. Hermes 回答每个判断都能指向返回证据；至少说明数据时间、平台和标题，URL 存在时保留 URL。
5. 公共缓存为 `stale` 时可以继续分析，但必须明确“使用上次有效缓存”；`no_data/error` 时必须坦白没有依据。
6. 普通“行业热点/趋势”请求优先使用 L0 `marketing_read_trends`；只有用户明确要求“搜索抖音站内内容”时，才允许请求 L2 `marketing_trending_search`。
7. 不影响“你好”等寒暄；不得自动跑营销分析或创建任务副作用。

**明确禁止**

- 不得修改抖音登录 URL、Cookie 规则、Electron partition、登录窗口或 `scrapeIndustryWithSession`。
- 不得引入 Playwright、Puppeteer、CDP、外部 Chrome、MediaCrawler、Agent-Reach、CLI 或 Cookie 后端存储。
- 不得恢复已删除的 `engine/marketing-os/tools/`、plugin manifest 或旧 orchestration。
- 不得修改 `runtime/hermes-agent` 上游源码；产品适配留在 `engine/agent_core`。
- 不得增加第二个模型分析器；领域层只做确定性筛选，语义判断只由同一个 Hermes session 完成。
- 不得写演示/假热点，不得用固定模板冒充模型结果，不得把测试通过写成真人验收完成。
- 工作树已有大量用户改动；不得 reset、checkout、覆盖或顺手重构任务之外文件。

**自动化验收**

- 查询 `AI` 只返回标题/分类中真实匹配的缓存项，并保留证据字段。
- `platform=weibo` 不得返回其他平台。
- `limit` 生效且限制在 1–30；非法参数安全归一化或明确拒绝。
- 无匹配、stale、no_data、部分来源失败均有测试。
- “分析热点趋势”映射到 `marketing_read_trends`；“搜索抖音站内内容”才映射到 `marketing_trending_search`。
- 执行：`.venv/bin/python -m pytest -q`、`npx tsc --noEmit`、`node --check electron/main.js`、`node --check electron/preload.js`。

**真人验收口令**

> 整理 AI 行业今天值得关注的热点，并给我 3 个适合抖音账号的选题。每个判断写明证据标题、平台和数据时间；没有依据就直说。

完成标准：不弹登录、不出现审批卡、不手动刷新；Agent 使用当前缓存证据作答，回答可追溯且不混入无关热点。

**复核结论**

- ✅ `query_trending_cache`、工具 schema、热点优先规则、证据提示和边界测试已实现。
- ✅ 当时全量 `139 passed`，TypeScript、Electron 语法与 Vite build 通过；这是该阶段历史记录，当前验证基线见第六节 `196 passed`。
- 🟡 尚未运行真实模型验收口令，因此不得将本任务标成产品完成。
- ⚠️ Claude 未等待真人验收便提前新增 `tests/test_approval_e2e.py` 和 P0-04/05 清单，超出上一任务最窄范围。
- ⚠️ 新审批测试使用 `FakeAgentService`，只能证明 API/store 状态转换，不能证明 Electron capability、真实 Hermes worker 或 UI 卡片闭环。
- 🔴 清单声称“等待 5 分钟会自动过期”，但 `expire_stale_approvals()` 当前没有生产调度调用；这是未完成项，不是已完成能力。

## 十、历史 Claude 任务记录（已归档，非当前执行入口）

### CLAUDE-NEXT-02：持久审批生命周期收口

**任务目标**

按照资料库的 durable interruption 原则，把 Claude 已提前写下但未闭环的审批“超时、取消、重启后状态”收口。只修审批生命周期，不进入 checkpoint、发布、抖音 DOM、记忆或 UI 重构。

**开始前必须做**

1. 阅读本台账第七至第十节、`docs/research/02-agent-harness-frontier-2026.md` 和 `docs/architecture/REBUILD_BASELINE.md`。
2. 承认 `tests/test_approval_e2e.py` 是 API/store integration，不得再命名或描述为真人 Electron E2E。
3. 工作树已有大量用户改动；不得 reset、checkout、覆盖或整理任务外文件。

**只允许修改**

- `engine/agent_core/store.py`
- `engine/agent_core/hermes_adapter.py`（仅审批恢复/过期所需，能不改则不改）
- `engine/marketing-os/server.py`（仅生产调度和审批 API 状态约束）
- `tests/test_approval_e2e.py`、`tests/test_agent_core.py`、`tests/test_server.py`
- `docs/verification/P0-04-05-manual-checklist.md`（只能纠正事实与记录真人结果）
- 本 `LEDGER.md` 仅允许在任务结束后追加实际测试结果，不得自行改进度百分比或完成状态。

**必须实现**

1. 生产运行时必须周期调用 pending approval 过期逻辑；默认超时 5 分钟，可通过受限配置调整，App 关闭/重启后仍以持久时间判断。
2. 过期必须原子完成：approval=`expired`、原 task=`paused`、追加 `approval.decided` 和 `task.paused` 事件；返回结果必须是已提交后的真实状态。
3. 修复 `expire_stale_approvals()` 在写事务内再次开启连接读取的问题；不得依赖 `timeout_seconds=-1` 这种测试技巧证明生产正确。
4. task 被 `cancelled` 后，其 pending approval 必须同步失效，之后 approve 返回 409，不能产生 authorization/effect。
5. 已 approved/rejected/expired 的审批重复操作必须幂等或明确 409，不得悄悄改变 task。
6. 重启时：未到期的 `waiting_user` 保持等待；已到期的审批在调度首轮被过期并暂停 task；不得启动重复 worker。
7. 前端不新增页面；沿用现有持久事件流，让 `approval.decided` 驱动卡片消失。若现有 UI 无法处理，只记录明确阻断，不得顺手重写 AgentPanel。
8. 日志与事件不得包含 Cookie、Token、API Key 或模型私有推理。

**明确禁止**

- 不得修改 Electron 登录、平台 session、热点、趋势 UI、抖音采集或公共数据源。
- 不得修改 `runtime/hermes-agent`，不得引入新框架、队列、数据库或第二套 Agent。
- 不得开始 plan/checkpoint、自动发布、账号 DNA、技能生成、微信/飞书或 Web 视频任务。
- 不得用更多 Fake 测试掩盖缺少生产调用；每条完成结论必须能指出生产入口。
- 不得把自动化通过写成“真人验收通过”。

**自动化验收**

- 使用可注入的 `now` 或明确构造的历史时间测试未到期/刚好到期/已到期；禁止以负超时替代。
- 覆盖 pending→expired、cancel→不可 approve、重启首轮过期、重复 approve/reject、expired 不可 effect。
- 验证事件顺序、task 状态和 approval 状态来自同一持久事务。
- 验证生产调度确实调用过期函数，而非只有单元测试直接调用。
- 执行 `.venv/bin/python -m pytest -q`、`npx tsc --noEmit`、`node --check electron/main.js`、`node --check electron/preload.js`、`npx vite build`。

**完成后停手并汇报**

只汇报修改文件、生产调用入口、测试结果和仍需人工点击的路径；不得自动进入下一任务。真人 Electron 成功/拒绝/取消/超时由用户或复核者按清单执行后才能勾选。

**2026-06-30 Codex 复核收口**

- ✅ `expire_stale_approvals()` 支持确定性时间注入，审批状态、任务暂停与事件在同一事务提交。
- ✅ 新增单次生产调度入口 `_run_scheduler_cycle()`；Electron orchestrator 模式仍执行审批过期，只跳过 Python 每日工作流。
- ✅ `cancel_task_and_void_approvals()` 原子完成任务取消、pending approval 废止及持久事件；真实 `HermesAgentService` 覆盖 `waiting_user` 取消。
- ✅ 覆盖 299/300 秒边界、受限超时配置和 Electron 调度分支；全量 `186 passed`，TypeScript、Electron 语法及 Vite build 通过。
- 🟡 自动化收口完成；真人 Electron 成功、拒绝、取消、超时四路径仍必须按清单验收，不得标为产品完成。
- ⏸️ 按任务要求停在此处，未继续 P1-06。

### P1-06：账号级会话隔离与注销（2026-06-30 Codex 实施）

- ✅ `account_id` 在打开登录窗口前生成，首次导航即使用 `persist:marketing-os-platform-{platform}-{accountId}`；缺失 ID 时 fail-closed，不再回落公共 partition。
- ✅ Electron 登录结果、`accounts.json`、AgentTask、审批 canonical arguments、工具上下文、账号同步、行业采集和自动巡检统一使用同一 ID。
- ✅ 同平台允许继续添加账号；Agent 账号选择持久化；账号支持重新登录、退出但保留资料、删除并清理 Cookie/storage/cache。
- ✅ 旧公共 partition 不复制秘密；新账号专属登录成功后清理旧共享存储，现有账号可通过“重新登录”迁移。
- ✅ 永久/session 授权约束包含 `account_id`，切换账号不会沿用另一账号的受控操作授权。
- ✅ 新增账号 ID 保持、重连、真实身份冲突、占位身份多账号、状态切换、Agent 工具注入与架构边界测试；全量 `195 passed`，TypeScript、Electron 语法、Vite build、`git diff --check` 通过。
- ✅ 真人首次双账号尝试发现两个创作者中心均返回 `douyin_session`，旧去重逻辑误清第二个 partition；已改为占位身份以 Electron `account_id` 为准，只有真实稳定用户名才执行冲突保护。
- ✅ 同次验收发现后端退出后恢复器受 `serverReady=false` 条件阻断；已增加单次重启锁并修复自动拉起，减少桌面端间歇性 `ECONNREFUSED`。
- 🟡 尚需真人使用两个抖音账号依次登录，确认 Cookie、健康检查、同步、退出和删除互不影响；完成前不得标产品完成。
- ✅ 2026-06-30 真人双账号登录复核：`acct_3b76732a3f21` 与 `acct_a1f55c3a3d95` 均独立落库；专属 partition 分别持有 31/34 个 Cookie，双方均有 3 个认证标志，旧公共 partition Cookie 为 0；未读取或记录 Cookie 内容。
- 🟡 尚未执行会改变用户状态的退出/删除验收；同步、退出一个账号不影响另一个账号、删除后本地存储清理仍待用户操作确认。
- ✅ 2026-06-30 真人单账号退出复核：`acct_a1f55c3a3d95` 状态变为 `disconnected`，Cookie 及认证标志均归零；`acct_3b76732a3f21` 仍保持 31 个 Cookie 与 3 个认证标志，证明退出未污染另一个账号。
- 🟡 剩余验收：连接账号指标同步，以及删除 disconnected 账号后元数据和本地 partition 数据同时清理。
- ✅ 2026-06-30 无感同步复核：应用启动后使用在线账号自己的 Electron partition 打开创作者中心，读取公开可见指标并写回脱敏快照；实测粉丝 4、获赞 56、播放 193。Cookie 未传给 Python。
- ✅ 2026-06-30 删除复核：已退出的 `acct_a1f55c3a3d95` 从账号元数据移除且认证数据保持为零；`acct_3b76732a3f21` 仍保持认证、登录和指标快照，删除未污染另一账号。
- ✅ P1-06 真人闭环完成；全量 `196 passed`，TypeScript、Electron 语法、Vite build 与 `git diff --check` 通过。
- ✅ 后续无感身份回填已在真实创作者中心验证：从公开页面文本提取昵称“杨炎昭”和抖音号 `66867825385`，指标快照保持 4/56/193；定位期间的页面文本诊断已从生产代码移除。
- ✅ 连续冷启动验证 renderer 请求会等待后端 ready，未再出现启动期 `ECONNREFUSED`；该阶段验证通过，当前全量基线见第六节。

### 2026-07-01 跑偏分支清理与 MCP 浏览器重构

- ✅ 删除跑偏验收分支的 4 个 AgentTask、73 条 task events 与 Hermes 消息 ID 44–66 共 23 条；全文索引已优化，会话计数重算为 41 条消息/11 次工具调用。
- ✅ `memory_candidates` 原本即为 0；正常账号、指标、更早聊天和账号 DNA 未删除。清理后任务、消息、全文索引和 memory candidate 四项匹配均为 0。
- ✅ 删除分支追加的“真人 Agent 主链首轮复核”段落，撤销 43 条登录态采集、证据白名单、自动重写和 209/210 产品完成口径；同步恢复 `AGENT_CORE_LEDGER.md`、研究差距矩阵和审批真人清单。
- ✅ 新增 `ProductMCPBroker`：第三方 MCP 不直接暴露给模型，必须经过产品工具白名单、L0-L4 等级和审批后调用。
- ✅ 建立 Microsoft Playwright MCP、抖音数据分析、私信读/写、内容提取五类服务器清单；私信发送单独定为 L3，资源与 prompts 默认关闭，禁止 shell、`latest` 和运行时 `npx -y` 安装。
- ✅ 新增只读 `/mcp/status` 与架构文档；全量 `219 passed`，TypeScript、Electron 语法、Vite build、`git diff --check` 通过。
- ✅ 已核验 Microsoft 官方 Playwright MCP，固定 `@playwright/mcp@0.0.77`、Apache-2.0；40 项 MCP/server 定向测试通过，生产依赖 audit 为 0。
- 🟡 Playwright MCP 仍保持 `enabled=false`：当前 Broker 是静态单实例，必须先完成 account-scoped 进程/profile 管理与双账号零串号验收。
- 🟡 两个抖音数据/内容项目仅为近似候选，私信项目无可信唯一仓库；风险与禁用原因见 `docs/research/05-open-source-capability-landscape-2026.md`。

## 十一、冻结后的执行入口

1. 总台账与 `AGENT_CORE_LEDGER.md` 的目标、边界、进度分母从 2026-07-01 起冻结。
2. 开源方案核验与采用边界统一见 `docs/research/05-open-source-capability-landscape-2026.md`。
3. Claude/Codex 的唯一任务入口为 `docs/ledgers/README.md`；一次只执行一个子台账 Task ID。
4. 当前首任务是 `MCP-01`：先定 account-scoped MCP 进程模型 ADR，再实施 manager，不能直接把静态 Playwright server 打开。
5. 子任务完成只更新对应子台账；不得在本文件追加测试数量、每日记录或自行修改完成百分比。
6. 只有用户明确改变产品目标或要求重新定版，才允许创建下一版总台账基线。
