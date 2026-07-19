# 新媒体经营世界模型

> 日期：2026-07-12
> 状态：当前账号经营模型唯一基线
> 执行禁令：默认修改原生 owner；Electron 只负责显示和交互。

## 定义

Marketing OS 不是先替用户“找几个对标、写几个选题”，而是先建立一个能被真实数据持续修正的经营世界模型。模型回答五个问题：

1. 这个创作者真实拥有什么、能长期做什么？
2. 哪些赛道路线值得验证，为什么？
3. 哪类人在什么场景下，愿意为哪种结果停留、信任和行动？
4. 哪些账号分别值得学习、避开或跨界借鉴？
5. 当前定位和内容系统，下一轮应该验证哪个变量？

## 原生经营顺序

```text
自然对话与创作者资产建模
→ 生成多个赛道路线假设
→ 用户选择一条待验证路线
→ 行为受众模型
→ 多角色对标经营图谱
→ 版本化账号定位
→ 版本化内容系统
→ 可证伪内容实验
→ Preflight / Action / Receipt / Retro
→ 账号知识、赛道知识与内容知识候选
```

顺序不是页面流程，而是 Hermes Agent 的认知依赖。没有创作者资源，就不能判断路线可持续性；没有路线，就没有受众参照；没有受众和证据，就不能把同赛道大号当作有效对标。

新会话即使没有登录平台账号，也由 Hermes `SessionDB` 自动绑定稳定的 `prospect_*` 经营作用域，因此自然对话建模、赛道研究和定位不会被登录阻断。登录后只能通过原生账号 owner 在会话仍可安全切换时绑定真实账号；Electron 不创建、保存或解释 prospect。

登录继承不是前端复制对象。目标账号通过真实登录验证且尚无独立经营事实时，`AccountRegistry → SessionDB` 在一个事务内把 prospect 的项目、画像、赛道、受众、对标、定位、内容系统、实验、证据、资产、预演和学习事实迁移到真实账号。已经开始的旧对话仍保留 prospect 作用域，随后创建一个继承历史、从第一条模型调用起就绑定真实账号的 successor session。目标账号已有事实时禁止自动覆盖，必须进入显式合并审查。

Preflight 输入、内容 feature snapshot 等历史不可变 JSON 保留行动发生时的 prospect 标识；SQL 事实作用域和后续经营切到真实账号，`marketing_account_adoptions` 负责可审计映射。继承不能以“清理字段”为理由改写过去。

“登录成功”也不是模型判断或 Electron 状态。只有账号隔离的 `marketing-browser` MCP 能读取其持久 Context，并用平台域名与第一方登录信号给出 secret-free 验证结果；Hermes 收到真实工具结果后才允许 AccountRegistry 进入 `authenticated`。UI 可以引导扫码和显示进度，但无权提交 Cookie、认证布尔值或触发经营事实迁移。

## 七类原生战略工件

### 1. 创作者经营画像

包括身份、经历、技能、证据资产、强观点、表达能力、生产资源、约束、禁区、动机、未知项和持续性。它是用户确认后的经营输入，不是知识库事实。

### 2. 赛道路线假设

包括赛道、细分方向、目标受众、紧迫问题、内容承诺、创作者优势、候选平台、变现路径、持续性、竞争假设、风险和数据缺口。无证据路线的置信度上限为 `0.45`，防止模型把想象包装成市场结论。

### 3. 行为受众模型

人口属性只是描述，不足以指导内容。核心字段是任务、痛点、触发场景、现有替代方案、信任障碍、期望结果、可观察行为信号、排除人群和数据缺口。

“存在”不是 Marketing OS 可以写死的哲学真理，也不是可以从评论或点击中直接测量、分类或打分的变量。Marketing 只保存用于经营研究的兼容投影；独立 Human Observation Core 把“存在策略”注册为可被反证、替换或拒绝的研究 seed。当前产品观察链为：

```text
人的主体性（伦理前提，不作为模型变量）
→ 环境与身体约束
→ 需求投影（马斯洛：行为试图满足或恢复什么）
→ 认知投影（荣格八维：信息如何被感知与判断）
→ 存在策略
→ 可观察行为
→ 匿名群体机制投影
→ 平台分配
→ 延迟结果与跨天校准
```

四种枚举因此命名为“存在策略”，而不是“存在方向”：

- `preserve`：维持安全、资源、关系和可控状态。
- `confirm`：确认身份、经验、归属和社会价值。
- `expand`：扩展能力、资源、自由和影响力。
- `continue`：延续作品、事业、关系、意义或长期影响。

马斯洛需求层次描述“存在当前通过行为解决什么缺口或实现什么成长”，荣格八维描述“存在通过什么信息加工路径理解并回应环境”。两者都是投影层的可证伪软假设，不是存在本身，也不是对真人内心的直接读取。荣格层只接受 `Se/Si/Ne/Ni/Te/Ti/Fe/Fi/unknown`，不得使用 MBTI 类型、永久人格标签或心理诊断。

当前 `marketing-human-projection-adapter-v0.4` 同时作用于创作者和行为受众，但只属于 Marketing 兼容层：`need_projection_hypotheses`、`cognitive_projection_hypotheses`、`existence_strategy_hypotheses` 与 `collective_projection_hypotheses` 都是候选解释，不是 Human Observation Core 的真相。群体层允许社会认同、去个体化、规范涌现、模仿、极化、权威转移与信息级联等竞争解释；`乌合之众` 只作为历史视角。所有投影都必须保存语境、可观察信号、依据、反证与数据缺口，置信度上限为 `0.7`，并且不能影响 Preflight 内容分。

### 4. 对标经营图谱

对标不是第五个知识库，也不是粉丝榜单。它是当前账号与外部账号之间带证据、带时间、带角色的关系图。

七类角色：

- `direct`：直接竞争者。
- `topic`：议题与选题来源。
- `format`：表达形式与制作效率样本。
- `trust`：建立可信度的样本。
- `business`：商业路径与行动设计样本。
- `cross_lane`：跨赛道可迁移方法。
- `negative`：明确不该复制的反例。

匹配必须保留多维向量：受众重合、商业模式、生命周期、形式适配、创作者资源、平台和当前表现相关性。禁止把它压成一个不透明总分。粉丝数不能解锁定位。

### 公域内容是自然实验，不是爆款答案库

公域创作者发布的作品及其公开反馈，是校准受众、内容模型和对标关系的重要学习样本。观察链必须保存“谁在什么平台发布了什么、何时发布、何时观察、当时可见什么反馈”，同一作品重复观察后形成时间序列，而不是只截取最终点赞数。

浏览器 owner 只采集公开作品、创作者公开身份、内容快照和聚合指标；不保存评论者身份与逐条原话。Hermes 用与自有作品相同的内容特征、匿名人群、立场、需求投影、认知投影、存在策略、提问/反对模式和反证信号解释样本，并生成 Receipt 与 pending learning candidate。

公域结果只能说明相关性。创作者历史、平台分发、发布时间、投流、粉丝基础和不可见流量都是潜在混杂变量。单条爆款不能直接改写内容规律或对标图谱；新创作者先进入对标候选，已有对标的新观察也必须通过系统的重复样本、来源、时效、冲突和历史回放门禁。用户与对话不能决定系统学习结论。用户仍然决定自己的 IP 方向、表达边界和是否采用某个经营方案；这种决定只使战略版本生效，不把方案升级为客观市场事实。

```text
公开作品页
→ browser_capture_public_content
→ EvidenceRecord + PublicContentCase + 延迟 FeedbackObservation
→ Agent 按内容/受众/存在/社会反应模型解释
→ public natural-experiment Receipt
→ 内容模型 learning candidate
→ 对标新增/修正 strategy candidate
→ 系统静默门禁晋级、等待或淘汰
```

### 5. 版本化定位

至少包含内容承诺、差异化、人设、受众摘要、证据机制、内容支柱、语气、禁区、固定形式、商业路径和变现边界。定位是阶段性决策，不是永恒真理；必须由用户明确批准。

### 6. 版本化内容系统

区分获客、信任、行动三类内容轨道，定义固定栏目、平台表达、生产工作流、发布节奏、指标计划、探索比例和商业边界。它负责把定位变成可持续生产，而不是列一批孤立选题。

### 7. 可证伪内容实验

每次实验只控制一个变量，至少两个变体，提前写预测、主指标和成功标准。发布后的回执不是“证明 Agent 对了”，而是用来修正路线、受众、对标关系、定位、内容系统和预演权重。

未完成或已过期的定位/内容系统不会阻止首日试写，但产物只能标记为 `exploratory_draft`。它可以继续研究、生成和人工打磨，不能进入发布审批。正式经营内容必须绑定当前 `positioning_id`、`content_system_id` 和已连接账号。

实验链必须可从结果反查到行动前假设：`account_experiment → content_production_plan → content_asset → preflight → publish/metric receipt → retro`。计划绑定运行中的 `experiment_id` 后，草稿自动继承并回写实验资产列表；Receipt owner 根据 plan 自动携带同一 experiment，禁止事后靠标题猜测哪条内容属于哪个实验。

## 发布前社会反应预演

内容草稿除了指标预测，还必须固化 `social_reaction_simulation`。每个匿名场景至少包含：

- 评论人群及其与目标受众的关系；
- 支持、经验分享、提问、质疑、反对、行动请求或误入等立场；
- 马斯洛需求投影、荣格八维投影、`preserve / confirm / expand / continue / unknown` 存在策略和匿名群体机制；
- 内容触发点、推理依据和宽泛可能性；
- 可能评论主题和明确标注的合成评论样例；
- 回复机会、风险、证据依据和反证信号。

系统不预测具体个人，也不输出未经校准的精确概率。发布后 Provider 只能提交匿名聚合观察：预测场景命中数、意外立场/主题簇、问题模式、反对模式和数据缺口。昵称、头像、主页、联系方式和逐条评论不得进入学习候选。Retro 比较命中、漏判和意外反应，但不能从评论相关性直接宣布心理或社会因果。

Retro 以 `need_projection → cognitive_projection → existence_strategy → collective_mechanism → observable_reaction` 机制链按匿名聚类对账，分别记录预测场景数、命中场景数、意外聚类数、观察评论数和覆盖率。命中只能校准整条投影假设，不能证明读懂了某个真人的需求、认知过程或“存在”。每次指标结算还生成分层因果反思：事实观察、预测误差、是否绑定预注册实验、反事实是否可识别、可能混杂因素和下一步所需证据。单作品的反事实状态必须是 `unavailable`。

原生链路固定为：

```text
行为受众假设 + 内容触发点 + EvidencePack
→ Agent 提出匿名社会反应场
→ Hermes 校验并固化到 prediction / feature snapshot
→ 发布 action 携带同一不可变预测
→ Provider 返回匿名评论聚类
→ Receipt / Retro 对照命中、漏判和意外反应
→ pending learning candidate
```

## 四类知识与经营图谱的边界

- 平台知识库：平台规则、分发和表达的“术”。
- 赛道与市场知识库：品类、需求、竞争、受众迁移、商业路径和时间窗口。
- 账号知识库：一个账号被真实回执反复支持的经营规律。
- 内容知识库：注意力、信任、情绪、身份和传播的“道”。
- 对标经营图谱：当前账号与外部样本之间的证据关系，不是公共真理。
- 用户记忆：偏好、拒绝和协作习惯，不拥有事实写权限。

## 历史代码使用规则

今天之前基于 Electron、FastAPI、外挂 Store 或旧生命周期的实现不具有架构权威。Git 历史只能帮助发现遗漏的业务问题，禁止直接恢复旧表、旧 API、旧 UI 流程或旧 owner。所有能力必须按本文件重新进入 Hermes 原生领域 owner、工具、任务、记忆和知识循环。

## 当前代码 owner

- `agent/marketing/domains/account_lifecycle.py`：项目与行为受众版本。
- `agent/marketing/domains/account_strategy.py`：创作者画像、赛道路线、对标图谱、定位、内容系统和实验。
- `agent/marketing/domains/public_content_observations.py`：公域作品、延迟反馈快照、同模型解释和公域学习候选。
- `agent/marketing/domains/knowledge_bases.py`：四类受治理知识。
- `agent/marketing/intelligence/audience_reaction_simulation.py`：匿名评论人群预演、聚合观察校验与发布后对照。
- `tools/marketing_tools.py`：Hermes 原生自然对话工具入口。
- `hermes_state.py`：唯一经营事实数据库的 schema 与迁移。

Electron 不拥有上述任何状态或转换。

## 研究依据

本模型不是照搬某一家平台后台，而是把可观察经营问题抽象为跨平台工件。当前研究入口：

- YouTube 官方 Audience：new / casual / regular viewers 与受众行为分层：<https://support.google.com/youtube/answer/13615784?hl=en>
- YouTube 官方 Content performance：内容、受众和回访关系：<https://support.google.com/youtube/answer/16559650?hl=en>
- TikTok Top Ads：按行业、地区、目标和逐帧表现研究样本：<https://ads.tiktok.com/help/article/about-top-ads-insight-in-tiktok-one?lang=en>
- TikTok Audience Insights：兴趣、行为和受众洞察：<https://ads.tiktok.com/help/article/audience-insights>
- 知乎创作手册：平台原生创作与治理入口：<https://www.zhihu.com/knowledge-plan/manual>
- Berger 与 Milkman 关于高唤醒情绪、实用价值和传播的可检验研究：<https://cssh.northeastern.edu/pandemic-teaching-initiative/wp-content/uploads/sites/43/2020/09/What-Makes-Online-Content-Viral.pdf>

平台资料只决定字段与研究方法，不自动成为账号结论。任何市场、对标和内容判断仍需 EvidenceRecord、时间窗口与真实回执校准。
