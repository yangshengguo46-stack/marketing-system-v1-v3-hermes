# 高级视频方案与历史执行记录（火山引擎）

> 建立日期：2026-07-02
> 状态：deferred；不计入桌面 v0.1 完成，不得从本文直接发起任务。
> 当前任务入口：[`../current/EXECUTION_LEDGER.md`](../current/EXECUTION_LEDGER.md)
> 资料库：[`../research/07-volcano-video-production-research.md`](../research/07-volcano-video-production-research.md)
> 目标：对标火山剧创工业级多 Agent 协同架构，集成 Seedance 2.0（视频生成）和 Seedream 5.0（图片生成），实现 6 环节视频生产流水线。
> 当前边界：本文只保留 `premium_human_video` 高质量视频 lane 的架构、校准证据和历史记录。软文与不露脸素材视频属于 Hermes 原生内容生产能力，不依赖火山或 Seedance provider。

## 当前状态边界

- 已落地并有自动化证据：`engine/video_core` 的画布 schema、项目存储、成本 hook、火山 adapter、TaskPoller、EDL/renderer 命令生成、共享剪辑协议和解耦边界测试。
- 有开发机真实校准证据：ARK 模型清单、Seedream 图片请求、Seedance fast 视频提交/轮询及结果字段；该证据不等于完整产品闭环。
- 尚未完成真人闭环：8 角色独立 Agent 调度、动态样片审批、真实 FFmpeg 成片、完整参考资产模式、反馈修改、营销接入和成片质量验收。
- 暂停原则：恢复开发前，必须先在当前执行台账重新排入顺序；本文中的历史任务状态不得覆盖当前代码和测试事实。

## 完成目标

用户一句话需求 → 剧组制 8 角色多 Agent 协同（见 ADR v2 决策 1）→ 先出近零成本动态样片，一次审批定稿定预算 → 按时间线规格批量生成正片 → 输出带字幕/配音/贴纸的最终成片 → 用户对成品提反馈，按环节最小代价修改。产品定位：先作营销系统补充，保留独立售卖空间（引擎层零业务依赖）。每个环节有自主决策能力（评估 + 重试），每个 API 调用走审批链路，对标火山剧创的工业级能力，超越 C 端单 Agent 产品（如小云雀）。

## 6 个环节

| # | 环节 | 火山模型/工具 | 输入 | 输出 | API 模式 |
|---|---|---|---|---|---|
| 1 | 文生图 | Seedream 5.0 | 场景描述 + 风格参数 | 场景图/角色图/道具图 | 同步 |
| 2 | 图生视频 | Seedance 2.0 | 首帧图片 + 运镜描述 | 视频片段 | 异步（提交→轮询） |
| 3 | 文生视频 | Seedance 2.0 | 视频描述 prompt | 视频片段 | 异步 |
| 4 | 参考图生视频 | Seedance 2.0 | 参考图 + 视频描述 | 视频片段 | 异步 |
| 5 | 参考视频生视频 | Seedance 2.0 | 参考视频 + 视频描述 | 视频片段 | 异步 |
| 6 | 合成 | 本地 FFmpeg | 视频片段列表 + 字幕 + 配音 + 贴纸 | 最终成片 | 同步 |

## VIDEO-01 架构 ADR v2（2026-07-03 定版，用户已确认）

> 依据：[`../research/07-volcano-video-production-research.md`](../research/07-volcano-video-production-research.md)（火山 API 底层逻辑）、[`../research/09-video-ecosystem-research.md`](../research/09-video-ecosystem-research.md)（ViMax/OpenMontage/LibTV/MoneyPrinterTurbo 等开源生态）。2026-07-03 用户确认按本版执行。
>
> v2 相对 v1 草案的变化：流水线制改为**剧组制（8 角色）**；新增**三个倒置**（时间线先行 / 动态样片两阶段 / 制片人预算制）；新增场记连续性检查；新增可解耦 Agent 层与独立售卖空间；技术栈定案。画布黑板、剪辑两层、反馈闭环保留。

### 决策 0：三条火山模型底层特性锚定架构

1. **Seedance 2.0 是异步任务队列**（提交→`task_id`→轮询，超时上限 48h）：并行点在 API 任务层，不在 Agent 进程层。镜头级并发 = fan-out 批量提交 + 共享 TaskPoller 收割 + fan-in 评估。
2. **跨镜头一致性靠参考资产，不靠 seed**：Seedance 2.0 支持最多 12 个参考资产（9 图 + 3 视频 + 3 音频）。资产库（角色三视图/场景/道具）必须先于镜头生成产出，同一批参考图保证一致性，seed 仅辅助。
3. **Seedream 同步（快/便宜）+ Seedance 异步（慢/贵）= 两段式 DAG**：资产阶段可低成本 best-of-k 多试；镜头阶段前必须过成本预估 + 审批门，`task_id` 落 effect intent 支持崩溃恢复。

### 决策 1：剧组制 —— 8 角色多 Agent（多 Agent 形态为硬性要求）

按职能划分角色，不按流水线阶段；4 种 Seedance 生成模式（文生/图生/参考图/参考视频）是同一 API 的 `content` 四种组合，收敛为摄影 Agent 的参数策略。

| 角色 | 职责 |
|---|---|
| 导演 Agent | 创意决策 + 反馈定位（不干活，只做判断） |
| 制片人 Agent | 预算案/进度/重试审批，**唯一有权花钱的角色**（见倒置 C） |
| 编剧 Agent | 剧本 + 叙事结构（复用已有 screenwriting skills） |
| 剪辑师 Agent | 时间线骨架（**先行**，见倒置 A）+ 最终 EDL + 重渲染循环 |
| 美术 Agent | 资产库：角色三视图/场景/道具，Seedream 并行 + best-of-k |
| 摄影 Agent | 按槽位规格生成镜头（4 种模式自选，带资产参考图，fan-out + TaskPoller） |
| 场记 Agent | 跨镜头连续性检查（见决策 5）+ 单镜头盲评（与生成者上下文隔离） |
| 音效师 Agent | TTS 配音 + 音效搜索（Freesound MCP）+ BGM 卡点 |

**多 Agent 执行形态硬性要求**（调度机制的验收标准）：

- 每角色是**独立实例（轻量 Hermes）+ 独立会话与上下文窗口**，不是一个大 Agent 换帽子；摄影 Agent 上下文里只有分镜和资产，不背全部对话史
- 每角色内部自带"执行→自评→重试"决策循环，重试不占导演注意力
- **两层并行叠加**：Agent 层（多角色同时活跃，摄影可多实例）+ 任务层（每 Agent 内部批量异步任务）
- **黑板协作**：子 Agent 互不直接通信，全部通过画布读写；质检角色与生成角色上下文隔离（三 channel，与 RUN-17/18 对齐）
- 所有 API 调用走审批/成本 hook（见决策 7）

### 决策 2：三个倒置（对标剧创/LibTV 威力的深层机制）

**倒置 A：时间线先行，镜头填坑。** 剪辑师 Agent 最先工作，产出空时间线骨架：每个槽位带硬约束（时长/运镜方向/能量等级/情绪/BGM 卡点）。镜头是**带规格生成**的，为剪辑服务——避免"每个镜头单看都好，剪在一起不成片"。BGM 若有，节拍点直接决定槽位边界（短视频卡点逻辑）。

**倒置 B：动态样片（animatic）两阶段，一次审批定生死。**

```
Phase 1（成本≈几毛钱，全 Seedream 同步 + 本地合成）：
  剧本 → 资产图 → 分镜图 → 按时间线骨架 + Ken Burns 缩放 + TTS 配音
  → 粗合成"草稿全片"（画布版本 v0）
  → 用户/导演看草稿判断整体：叙事通不通、节奏对不对
  → 唯一一次重审批：确认草稿 + 确认预算（session scope 授权承接）
Phase 2（真正花钱）：
  按已锁定时间线规格批量提交 Seedance，逐槽位替换草稿
```

价值：结构性风险在花钱前暴露（镜头级重试救不了叙事崩坏）；审批从"每次 API 弹一下"收敛为一次有意义的决策。

**倒置 C：成本不是门，是制片人 Agent。**

- 开拍前出预算案：总预算 → 镜头生成 70% / 重试储备金 20% / 机动 10%
- **替身试拍**：便宜模型（seedance fast/lite）先试拍选构图，赢家 prompt 再用 2.0 正片——试错成本降一个量级
- 重试向制片人申请：储备金内自动批，超了升级用户
- 杀预算黑洞：某镜头重试 3 次仍不合格 → 制片人叫停，改替代方案（换分镜/样片图救场）

### 决策 3：画布 = 内部结构化项目状态（黑板模式），不做用户端 UI

对标火山剧创"全局风格锁定 + 素材资产库"的实现本质：所有子 Agent 共享读写一个项目状态对象。参考 ArkClaw 项目目录（project.json + script + frames/ + videos/ + audio/ + final/），schema 按 LibTV 三级解耦（场景→镜头→帧）组织：

```
Project
 ├─ style_lock   全局风格：色调/画风描述词/seed/参考资产 ID
 ├─ assets[]     角色三视图/场景/道具（跨镜头复用）
 ├─ scenes[] → shots[]  每镜头：分镜图/运镜/Seedance task_id/状态/结果/评分/重试次数
 ├─ tracks      配音轨/音效轨/BGM 轨（带时间戳）
 ├─ timeline    时间线骨架（槽位规格，剪辑师最先写入）→ 最终 EDL
 └─ budget      预算案/已花费/储备金状态（制片人独写）
```

硬性规则：
- **子 Agent 只通过画布通信**，不互相直接传参；导演 Agent 只看画布状态决定下一步。
- **依赖图**：shot 记录引用的 asset ID，timeline 条目记录引用的 shot——支撑"改一张资产图需级联重投哪些镜头"的计算。
- **版本化**：动态样片为 v0，成片 v1/v2 递增，保留每版 EDL 与 shot 版本，可回退。
- 画布不暴露给用户；用户只见成品。effect receipt 携带 `project_id`（LibTV 项目交付模式），为未来人工接管预留。

### 决策 4：剪辑两层 —— EDL 决策 + 确定性渲染

剪辑是全流程决策密度最高的环节（小云雀"智能成片"的核心即在此），剪辑师 Agent 贯穿首尾（骨架先行 + 最终 EDL），且拆两层（借鉴 Resound 的声明式编排）：

> 2026-07-09 与内容生产端对齐：本高级视频 lane 不再另写一套剪辑器。`premium_human_video` 与 `faceless_video` 共用 `engine/video_core/editing_engine.py` 的 EDL 骨架、素材/镜头填坑、审片交接摘要；区别只在素材/镜头来源，最终都进入同一条 EDL/renderer 路径。

```
剪辑师 Agent（SKILL.md：剪辑领域知识）
   ↓ 读画布全量状态，产出 timeline.json（EDL）：
     片段顺序/入出点/节奏裁剪、转场、字幕逐条时间戳+参数化样式、
     配音对齐、音效放置点、BGM 音量曲线
   ↓
确定性渲染器（FFmpeg）：timeline.json → mp4（纯函数，可测试；同一条路径支持样片粗合成）
   ↓
剪辑师 Agent VLM 自检（卡点/音画同步/字幕溢出）→ 不满意只改 EDL 重渲染
```

好处：重渲染零 API 成本、渲染器可写确定性测试、审批节点上用户看到的是人类可读的剪辑方案而非 FFmpeg 命令。

### 决策 5：质检双层 —— 盲评（单镜头）+ 场记（跨镜头连续性）

- **盲评**：独立实例对单镜头质量打分（与生成者上下文隔离，防自评偏袒），不合格触发重试（经制片人批额）。
- **场记**：沿时间线成对读相邻镜头做连续性检查——角色外观漂移、光线跳变、运动方向穿帮（180° 轴线）、道具不一致，在合成前拦住。单镜头盲评查不出这类问题，这是工业级良品率的关键一环。

### 决策 6：用户反馈驱动的修改闭环（四级定位）

用户只看成品，用自然语言指出问题；导演 Agent 负责**反馈定位**并按最小代价分派：

| 反馈类型 | 定位 | 修改代价 |
|---|---|---|
| 节奏/字幕/音效问题 | timeline EDL | 只改 EDL 本地重渲染，零 API 成本 |
| 镜头内容问题 | scenes[].shots[n] | 只重投该 1 个 Seedance 任务（沿用同批参考资产） |
| 资产问题（角色不像） | assets[] | 重生成资产 → 按依赖图级联标记受影响 shots 重投 |
| 结构性问题（叙事/整体节奏） | 回样片层 v0 | 重排时间线骨架 → 重出草稿重审批，几乎免费，不直接烧正片 |

- 修改成本分级由制片人报价（免费 / 单镜头 X 元 / 级联 Y 元），贵的走审批。
- 反馈三元组（自然语言反馈 → 定位环节 → 修改后满意度）落库，作为数据飞轮素材（哪类问题高频 = 哪个 SKILL.md 该进化），接 RUN-19 复盘链路。

### 决策 7：可解耦 Agent 层与独立售卖空间

三层拆分，依赖方向：营销系统消费视频引擎，不拥有它。

```
入口层  A. 营销系统桥（现在做）：tool_manifest/gateway 注册引擎工具，
          Hermes 主链直接加载 skills，子 Agent 由主链孵化——系统是通的，
          审批/记忆/账号上下文/数据飞轮全部继承
        B. MCP Server（引擎稳定后）：验证独立售卖的第一形态
        C. REST API（有 B 端客户再做）
智能层  video_agents：SKILL.md × 8 角色 + 工具 function-call schema，
        纯资产包无 runtime 代码。多 Agent 是执行形态，SKILL 包是分发形态；
        解耦解的是宿主，不是智能（角色数/自治性/并行度两种宿主下一致）
引擎层  video_core：画布 schema/adapter/TaskPoller/渲染器/成本估算，
        零业务依赖，随时可抽出单独成品
```

两条强制边界（写进架构回归测试）：
1. `video_core`/`video_agents` 禁止 import `agent_core`、`marketing_tools`、Electron 相关任何模块（静态检查）。
2. 审批/成本门是 **hook 接口**：引擎只定义卡点；营销系统模式注入 tool_gateway，独立模式注入自带确认器。
3. skills 只准引用画布和引擎工具，禁止引用 Hermes 私有 API 或营销系统表。

### 决策 8：技术栈定案（全部固定版本）

| 组件 | 选型 | 理由 |
|---|---|---|
| 引擎包 | Python 3.11，`engine/video_core/`（独立包） | 与现有 engine 同栈，PyInstaller 链路已验证 |
| 数据模型 | Pydantic v2 | 画布/EDL schema 校验 + 序列化，schema 即产品协议 |
| HTTP | httpx（async） | Ark 视频任务 API 是专有 REST，统一 httpx，不引入 openai SDK 版本绑定 |
| 模型适配 | 自写 `VideoModelAdapter` 基类 + `VolcengineAdapter` 首实现（含 fast/lite 替身档位） | 不锁死单模型；不用 LangChain 类编排框架 |
| 异步轮询 | asyncio TaskPoller（营销模式挂 FastAPI lifespan，独立模式自带循环） | 两宿主复用 |
| 画布存储 | 项目目录 + JSON（project.json + frames/ + videos/ + audio/ + final/）+ SQLite 任务索引 | 文件即项目，可拷走/备份/迁移——卖点 |
| 渲染器 | FFmpeg CLI（subprocess 编排 filtergraph，随包分发 DESK-08 模式） | MoviePy 慢且给 PyInstaller 添乱；接口固定可换实现 |
| 成本估算 | 表驱动定价（版本化价格表） | 制片人与审批 hook 共用 |
| 新增依赖 | 仅 httpx、pydantic>=2；外部二进制 ffmpeg | 不引入 openai SDK/编排框架/MoviePy |

### ADR 风险

- API 请求体字段为推断（07 调研第八节），adapter 动手前必须用真实 ARK API Key 校准字段。
- 样片渲染路径（Ken Burns + TTS 粗合成）比线性流水线多一轮工程，但是结构风险前置的代价，接受。
- 制片人的预算策略需真实价格数据喂养；替身（fast/lite）与正片（2.0）存在风格差异，替身只选构图不定画面细节。
- 复用地基清单：plan_protocol（DAG 编排）、tool_gateway（审批）、effect intent（崩溃恢复）、content_assets（资产库）、RUN-17/18（评分/盲预测）、secret store（Key）。

## 任务清单

> 2026-07-03 按 ADR v2 重写：引擎层先行（VIDEO-02~05）→ 角色 Agent（VIDEO-06~12）→ 闭环与验收（VIDEO-13~17）。旧编号废弃，以本表为准。

| ID | 任务 | 具体执行 | 完成证据 | 状态 |
|---|---|---|---|---|
| VIDEO-01 | 架构定版 | ADR v2（剧组制 + 三倒置 + 可解耦 + 技术栈） | 本台账 ADR v2 | ✅ 2026-07-03 用户确认 |
| VIDEO-02 | 画布 schema（产品协议） | Pydantic：Project/style_lock/assets/scenes.shots/tracks/timeline（骨架+EDL）/budget + 依赖图 + 版本化（v0 样片）；项目目录布局 | `tests/test_video_core_schema.py` 23 测试通过（依赖级联/崩溃恢复查询/骨架校验/存储往返） | ✅ 2026-07-06 |
| VIDEO-03 | video_model_adapter + 火山实现 | 基类 + VolcengineAdapter（鉴权、Seedream 同步、Seedance 异步提交+轮询、fast 替身档、429/5xx 退避重试、4xx 快速失败） | 真实字段校准记录（见下节）+ `tests/test_video_core_adapter.py` 9 测试（MockTransport） | ✅ 2026-07-12（校准 07-11 真实 Key 实测；reference 角色名待首用验证） |
| VIDEO-04 | TaskPoller + 崩溃恢复 | asyncio 批量轮询 + 指数退避（10s×1.5→120s 封顶）；下载器可注入；终态整读整写画布；recover() 扫 pending 续轮询；Provider 终态异常不会无限退避，下载失败回调不冒充成功 | `tests/test_video_core_poller.py` 9 测试（成功/远端失败/终态异常/下载失败/去重/恢复/退避/回调/启停） | ✅ automated 2026-07-10；真实 Provider 未验收 |
| VIDEO-05 | 确定性渲染器 | EDL → mp4 纯函数（FFmpeg）：拼接/转场/字幕/配音/音效/BGM；同路径支持样片粗合成（Ken Burns + TTS） | 命令生成纯函数测试在 `tests/test_video_core_schema.py`（build_final/animatic_command）；真实 ffmpeg 出片待集成测试 | 🟡 实现已填（2026-07-10 验证命令生成测试通过），真实渲染验收待做 |
| VIDEO-06 | 子 Agent 调度机制 | 轻量 Hermes 实例孵化；验收三件事：多实例并行 + 上下文隔离 + 质检角色独立 | 并行/隔离/盲评独立测试 | ⏳ |
| VIDEO-07 | 剪辑师 Agent | SKILL.md（剪辑决策知识）：时间线骨架先行（槽位规格/BGM 卡点）+ 最终 EDL + VLM 自检重渲染循环 | 骨架生成 + EDL + 自检测试 | ⏳ |
| VIDEO-08 | 编剧 + 美术 Agent | 编剧复用 screenwriting skills；美术 SKILL.md（Seedream 提示词 + 风格锁定 + best-of-k）写 assets[] | mock 生成 + 评估测试 | ⏳ |
| VIDEO-09 | 摄影 Agent | SKILL.md：按槽位规格生成（4 种模式参数策略 + 参考资产传入规范 + 替身试拍→正片）；读 assets[]/timeline 写 shots[] | mock 生成 + 槽位约束测试 | ⏳ |
| VIDEO-10 | 制片人 Agent | 预算案（70/20/10）+ 替身/正片策略 + 重试批额 + 叫停逻辑 + 成本 hook 对接；表驱动价格表 | 预算分配/批额/叫停测试 | ⏳ |
| VIDEO-11 | 场记 Agent | 单镜头盲评（独立实例）+ 相邻镜头连续性检查（外观漂移/光线/轴线/道具） | 盲评 + 连续性检查测试 | ⏳ |
| VIDEO-12 | 音效师 Agent | TTS 配音 + Freesound MCP 音效搜索 + BGM 卡点，写 tracks | mock 音轨生成测试 | ⏳ |
| VIDEO-13 | 导演编排 + 样片两阶段 | plan_protocol 编排：Phase 1 草稿→一次审批（草稿+预算，session scope）→ Phase 2 正片替换；画布状态驱动 | 两阶段 E2E 编排测试 | ⏳ |
| VIDEO-14 | 反馈定位闭环 | 四级定位（EDL/镜头/资产/结构回 v0）+ 制片人报价 + 级联重投 + 反馈三元组落库 | 定位分派 + 级联重投测试 | ⏳ |
| VIDEO-15 | 营销系统接入 + 解耦回归 | tool_manifest/gateway 注册；架构回归：video_core/video_agents 禁止 import 业务模块（静态检查） | manifest 快照 + 边界回归测试 | ⏳ |
| VIDEO-16 | E2E 测试 | 全链路：一句话 → 草稿 → 审批 → 正片 → 质检 → 成片 → 反馈修改一轮 | E2E 测试通过 | ⏳ |
| VIDEO-17 | 真人验收 | 真实 API Key 生成一条成片 + 一轮反馈修改 | 真人确认成片质量 | ⏳ |

## 框架落地记录（2026-07-06）

框架已建，分工：**schema 与纯逻辑已写实带测试；执行类全部 stub + 规格 docstring**，供其它模型填实现（每个 stub 标 `TODO: VIDEO-xx` 并内嵌实现约束）。

| 文件 | 状态 |
|---|---|
| `engine/video_core/schema.py` | ✅ 写实（画布协议 + 依赖图查询） |
| `engine/video_core/edl.py` | ✅ 写实（骨架/EDL 协议 + 校验） |
| `engine/video_core/project_store.py` | ✅ 写实（目录布局 + 原子写） |
| `engine/video_core/cost.py` | ✅ 写实（价格数字占位，待真实定价校准） |
| `engine/video_core/hooks.py` | ✅ 写实（CostGate 接口 + BudgetCostGate） |
| `engine/video_core/testing.py` | ✅ 写实（离线 harness，见下） |
| `engine/video_core/adapter.py` | ✅ 写实（2026-07-12，字段已真实校准，9 测试） |
| `engine/video_core/poller.py` | ✅ automated（2026-07-10，9 测试；真实 Provider 未验收） |
| `engine/video_core/renderer.py` | ✅ 实现已填（命令生成测试通过；真实 ffmpeg 出片待集成验收） |
| `engine/video_core/editing_engine.py` | ✅ 写实（共享剪辑引擎：faceless/premium 共用 EDL 骨架、素材填坑、审片摘要） |
| `engine/video_agents/`（8 角色 SKILL.md + tools.json） | 🟡 骨架（领域知识待填） |
| `tests/test_video_core_boundary.py` | ✅ 解耦边界回归（禁 import 业务模块 + video_agents 纯资产包） |

**Harness 决策：加。** `engine/video_core/testing.py` 提供离线三件套：MockAdapter（确定性假模型，含失败路径）、make_demo_project（标准三镜头画布）、ScriptedGate（剧本式审批门）。约定：单测只用 harness 禁真实网络；渲染器只测命令生成纯函数；真实 API/渲染放集成测试（无 Key/ffmpeg 时跳过）。填代码的模型用它自证，无需 API Key。

## VIDEO-03 真实字段校准记录（2026-07-11，真实 ARK Key 实测）

| 项 | 实测结果 |
|---|---|
| 模型清单 API | GET /api/v3/models 可用（Bearer 鉴权） |
| 图片模型 | `doubao-seedream-5-0-260128`（另有 5-0-pro-260628） |
| 视频模型 | 正片 `doubao-seedance-2-0-260128`，替身 `doubao-seedance-2-0-fast-260128`，另有 mini-260615；均支持 MultimodalToVideo/VideoExtension/VideoEditing，输入 text+image+video+audio |
| 图片请求 | POST /images/generations；size 下限 1920x1920（≥3,686,400 像素，低于此报 InvalidParameter）；响应 data[].url（24h 签名 URL）+ usage.output_tokens（实测 14400 token/张） |
| 视频提交 | POST /contents/generations/tasks，{model, content[]}；text 项支持 `--resolution 720p --duration 4` 后缀（响应回显）；首帧 `{"type":"image_url","image_url":{"url":…},"role":"first_frame"}` 实测有效；响应仅 `{"id":"cgt-…"}` |
| 视频轮询 | GET /contents/generations/tasks/{id}；status 小写 running/succeeded；成功后 content.video_url + usage.completion_tokens（fast 4s/720p = 87300 token）+ seed/resolution/duration/framespersecond；fast 4s/720p 实测约 108s 完成；`generate_audio` 默认 true（**Seedance 2.0 自带音频生成**）；`execution_expires_after: 172800`（2 天过期） |
| 取消 | DELETE /contents/generations/tasks/{id}；running 任务返回 409 InvalidAction.RunningTaskDeletion（adapter 按 no-op） |
| 未实测 | 多参考图/视频/音频的 role 名（按 reference_image 等推断）；首次真实使用参考模式时验证 |
| 花费 | 校准共耗：图 2 张 + fast 视频 2 条（均 4s/720p），token 计价待对照账单后更新 cost.py 价格表 |

### 同 Key 可用的配套模型盘点（2026-07-12）

- **场记 VLM（质检）**：`doubao-seed-2-1-pro-260628` / `doubao-seed-2-0-pro-260215`（输入支持 video，可直接喂镜头视频做盲评）；便宜档 `2-1-turbo` / `2-0-mini`
- **TTS 缺位**：Ark v3 模型列表无 TextToSpeech（只有 seed-2-0 mini/lite 的 SpeechToText）。音效师两条路：① Seedance 2.0 自带音频生成（generate_audio 默认开，可在 prompt 里描述台词/音效）；② 独立 TTS 要接火山语音合成服务（openspeech，非 Ark v3，另套鉴权），样片 TTS 路径需据此重评（影响 VIDEO-12）
- **3D**：`doubao-seed3d-2-0-260328`（ImageTo3D，本项目暂不用）

## 前置条件

- [x] E2E-01 内部链路端到端测试通过（plan→approval→effect→bridge）
- [x] DESK-03 秘密存储（API Key 安全读取）
- [x] 用户确认火山方舟 API Key 已开通（2026-07-11 用户提供，存 .env 未入 git；包含全部火山模型）
- [x] 架构方案审核通过（VIDEO-01，ADR v2 于 2026-07-03 用户确认）

## 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| API 请求体字段未完全确认 | adapter 可能需要调整 | 先用 mock 测试，拿到 Key 后对照官方文档校准 |
| 异步任务超时（最长 48h） | 用户体验 | 轮询 + 进度展示 + 用户可取消 |
| 风格一致性跨镜头不稳定 | 成片质量 | 参考资产为主 + 场记连续性检查 + 制片人批额重试 |
| API 调用成本 | 用户成本 | 制片人预算制（VIDEO-10）+ 替身试拍 + 样片两阶段（结构风险前置） |
| 替身与正片风格差异 | 试拍结论失真 | 替身只选构图不定细节；关键镜头可跳过替身直接正片 |
| 样片路径额外工程量 | 进度 | 与渲染器同一条路径（VIDEO-05），不另建链路 |
| FFmpeg 依赖 | 桌面端打包 | 随包分发或引导安装（DESK-08 模式） |
