# 影响力预演引擎执行台账

> 建立日期：2026-07-09
> 关联资料库：`docs/research/12-influence-attention-model.md`、`docs/research/08-data-flywheel-strategy.md`、`docs/research/09-video-ecosystem-research.md`、`docs/research/11-social-account-lifecycle-and-open-source.md`
> 当前判断：内容生产端真正的壁垒不是“能生成内容”，而是“生成前能判断值不值得做、为什么值得做、发布后能否校准下一次判断”。预演引擎是产品大脑，不是一个 UI 小功能。

## 一、今天对话沉淀的核心共识

按由深到浅排序：

1. **最深层：营销建模人类社会注意力。**
   我们不是只做自动写稿或自动剪视频，而是试图建立一个能理解“人为什么停下、为什么相信、为什么转发、平台为什么继续推”的预演系统。

2. **第二层：预演不是模型瞎猜，而是数据闭环。**
   预演必须建立在账号数据、内容资产、对标样本、平台指标、用户拒绝/采纳、发布前预测和发布后结果之上。

3. **第三层：注意力、信任、行动、账号适配必须分开。**
   播放量只代表注意力，不代表信任、转化或长期账号价值。系统不能把“火”当成唯一目标。

4. **第四层：人类心理、群体传播、平台推荐三层叠加。**
   个体层判断停留和行动；群体层判断扩散和从众；平台层判断分发闸门和二次推荐。

5. **第五层：公式先可解释，再逐步学习。**
   第一版用规则权重和可解释分数，后续用真实发布结果校准权重，最终沉淀为私有 InfluenceOS Score。

6. **第六层：预演必须前置到内容生产。**
   软文、不露脸视频、高级视频都要先通过 Preflight：证据、素材、预测、风险、成本、账号适配，过关后再写稿/渲染/开机/发布。

7. **最浅层：UI 只展示判断，不展示复杂公式。**
   用户看到的是“预计注意力、信任、行动、账号适配、最大风险、建议修改”，专业用户可点开依据。

## 二、由深到浅的产品架构

```text
社会注意力理论
  ↓
数据闭环与证据来源
  ↓
特征工程与标签体系
  ↓
InfluenceOS Score v0
  ↓
Preflight 预演引擎
  ↓
内容生产三条 lane
  ↓
工作台 / 内容工厂 UI
  ↓
用户点击：生成、修改、开机、发布
```

这个顺序很重要。不能从“按钮怎么放”开始想，否则产品会退化成普通内容工具。

## 三、预演引擎的三层社会模型

### 3.1 个体注意力层

问题：用户刷到内容时会不会停、会不会看完、会不会行动。

初始变量：

- `HookSalience`：开头是否有冲突、反常识、痛点、悬念。
- `PersonalRelevance`：是否和目标受众眼前问题有关。
- `Novelty`：是否有新信息、新角度、新表达。
- `EmotionalArousal`：是否激发情绪，但不过度消耗信任。
- `CognitiveLoad`：是否过难、过乱、过长、信息密度失控。
- `TrustRisk`：是否像标题党、营销号、伪科学或低质 AI 文。

对应输出：

- 停留概率。
- 完播/读完概率。
- 收藏/转发/关注/咨询概率。

### 3.2 群体传播层

问题：内容是否会被讨论、转发、模仿、带入群体情绪。

初始变量：

- `SocialProof`：是否容易形成“大家都在看/都在讨论”的信号。
- `IdentitySignal`：用户转发它是否能表达身份。
- `GroupConflict`：是否有可讨论的立场，但不伤害账号长期信任。
- `ShareUtility`：分享给别人是否有用、有面子、有情绪价值。
- `ReputationRisk`：用户公开转发/评论是否有社交风险。

对应输出：

- 评论意愿。
- 转发意愿。
- 二次传播潜力。
- 负反馈风险。

### 3.3 平台分发层

问题：平台是否会给初始流量、是否会进入下一轮推荐。

初始变量：

- 停留/播放。
- 完播/平均观看时长。
- 点赞、评论、分享、收藏。
- 关注、主页访问。
- 不感兴趣、划走、举报、拉黑。
- 原创、质量、安全、版权、重复度。

对应输出：

- 初始曝光潜力。
- 通过留存闸门概率。
- 通过互动闸门概率。
- 二次推荐概率。

## 四、InfluenceOS Score v0

第一版公式不追求神秘，追求可解释、可回放、可校准。

```text
InfluenceOS_Score
  = PlatformReachPotential
  * HumanAttentionKernel
  * RetentionDesign
  * PersuasionScore
  * SocialPropagation
  * AccountFit
  * BusinessValue
  - RiskPenalty
```

拆开看：

| 分量 | 含义 | 对应产品问题 |
|---|---|---|
| `PlatformReachPotential` | 平台是否可能给分发 | 平台会不会推 |
| `HumanAttentionKernel` | 人是否会停下来 | 开头有没有抓住人 |
| `RetentionDesign` | 人是否愿意看完 | 中段会不会塌 |
| `PersuasionScore` | 人是否相信 | 证据/案例/表达是否可信 |
| `SocialPropagation` | 人是否愿意互动/转发 | 有没有群体传播势能 |
| `AccountFit` | 是否适合当前账号 | 会不会带偏账号 |
| `BusinessValue` | 是否服务商业目标 | 能否带来咨询/转化/信任 |
| `RiskPenalty` | 风险扣分 | 违规、标题党、版权、低质 AI 味 |

## 五、数据来源与权重顺序

按优先级排序：

1. **用户自己账号的一方数据**：最高权重。
   创作者中心、官方 API、发布回执、1h/6h/24h/3d/7d 指标。

2. **内容资产与生产过程数据**：高权重。
   标题、脚本、正文、EDL、素材、配音、封面、用户修改、审片意见。

3. **发布前盲预测与评分**：高权重。
   用来校准 Agent 的判断能力，禁止事后改写。

4. **用户偏好与拒绝记录**：高权重。
   用户经常拒绝什么，采纳什么，觉得哪里“不像自己”。

5. **对标账号数据**：冷启动权重高，后续逐渐降低。
   没有自己的数据时用来建 prior，有真实数据后退居辅助。

6. **热点与公共平台数据**：中等权重。
   用来判断时效和话题供给，不直接判断适合当前账号。

7. **行业资料和公开证据**：中等权重。
   用来支撑可信内容，尤其是知乎/公众号软文。

8. **脱敏聚合数据**：未来能力。
   只有用户授权、脱敏、不可反推时才能进入行业基线。

## 六、数据标签体系

平台原始指标不能直接混用，需要转成训练标签。

| 标签 | 目的 | 原始指标 |
|---|---|---|
| `attention_label` | 是否停下 | 3 秒留存、播放、曝光点击、初始播放率 |
| `retention_label` | 是否看完 | 完播率、平均观看时长/内容长度、跳出点 |
| `trust_label` | 是否相信 | 收藏率、转发率、正向评论、低负反馈 |
| `action_label` | 是否行动 | 关注率、主页访问、私信、咨询、点击 |
| `fit_label` | 是否吸对人 | 粉丝画像变化、评论关键词、目标受众匹配度 |
| `risk_label` | 是否伤害账号 | 举报、不感兴趣、争议过载、掉粉、违规提示 |

后续所有预测都不应只输出 `expected_views`，而应输出：

```json
{
  "attention": {},
  "retention": {},
  "trust": {},
  "action": {},
  "account_fit": {},
  "risk": {}
}
```

## 七、和内容生产端的关系

预演引擎不单独卖弄模型，它服务内容生产三条 lane：

| Lane | 预演重点 |
|---|---|
| `article_soft` | 证据是否够、读者是否明确、信任是否成立、知乎/公众号哪个更适合 |
| `faceless_video` | 开头是否抓人、镜头节奏是否能留人、素材是否贴题、是否有廉价素材味 |
| `premium_human_video` | 样片叙事是否成立、开机预算是否值得、镜头是否支撑传播和商业目标 |

执行原则：

1. 先预演，再生产。
2. 先预测，再发布。
3. 先用样片/草稿暴露结构风险，再花钱/开机。
4. 预测必须能被后续真实指标打脸。
5. 被打脸不是失败，是模型进化的燃料。

## 八、产品表现

用户不看公式，用户看判断：

```text
开机前预演

预计注意力：72 / 100
预计留存：58 / 100
预计信任：44 / 100
账号适配：62 / 100
商业价值：中
最大风险：证据不足，可能像泛泛 AI 观点

建议：
1. 前 3 秒改成目标用户痛点。
2. 补一个真实案例或数据来源。
3. CTA 不要泛泛“关注我”，改成“评论行业，我给你拆一版账号定位”。
```

专业模式可展开：

- 使用了哪些历史内容样本。
- 哪些对标账号支持判断。
- 哪些平台字段缺失。
- 哪些权重拉高/拉低了分数。
- 预计在哪些指标窗口验证。

## 九、推进任务

| ID | 任务 | 具体执行 | 完成口径 | 状态 |
|---|---|---|---|---|
| IPE-01 | 研究资料入库 | 整理影响力/注意力建模资料，明确人类注意力、群体传播、平台推荐和营销公式 | `docs/research/12-influence-attention-model.md` 已建立并登记资料依据 | ✅ docs |
| IPE-02 | 内容特征快照 | 新建 `content_feature_snapshots` 协议：每条内容发布前保存标题、结构、证据、素材、账号、平台和风险特征 | 同一内容预测可回放；后续改稿生成新版本特征 | ⏳ |
| IPE-03 | 预测结构 v2 | 从单一 `expected_views` 升级为 attention/retention/trust/action/account_fit/risk 六组预测 | 软文和视频资产都写入 v2 prediction | ⏳ |
| IPE-04 | 指标标签化 | 将发布后原始指标映射为 attention/retention/trust/action/fit/risk 标签 | 指标回收后自动生成 label，不混用未知值和 0 | ✅ code |
| IPE-05 | InfluenceOS Score v0 | 用可解释权重计算第一版分数，并保留权重版本 | 同一资产能输出总分、分项分和 why | ✅ code |
| IPE-06 | PreflightDecision | 把分数转成产品决策：可生产、先改稿、补证据、换素材、不开机、可发布 | Agent 和 UI 都消费同一决策结构 | ✅ code |
| IPE-07 | 接入内容生产三 lane | `article_soft`、`faceless_video`、`premium_human_video` 生产前均调用预演 | 内容生产不再绕过预演 | ⏳ |
| IPE-08 | 对话思考折叠与预演去噪 | 预演门保持底层能力；计划、工具、证据流水折叠到“思考与执行”；主回复只交付结论和下一步 | 用户不被底层流水账打扰，但可展开核查过程 | ✅ code |
| IPE-09 | 校准与权重升级 | 发布后对账预测与真实结果，生成权重候选；升级前全量回放历史样本 | 不允许 Agent 静默改权重 | 部分 code：权重候选已落地，回放升级待做 |
| IPE-10 | 冷启动对标 prior | 新账号用对标账号和行业基线生成初始权重；真实数据回来后逐步退权重 | 无账号/新号也能预演，但明确置信度和来源 | ⏳ |

## 十、短期代码落点建议

优先顺序：

1. `engine/agent_core/influence_features.py`
   从内容资产、账号上下文、素材、证据和平台生成可解释特征。

2. `engine/agent_core/influence_score.py`
   第一版 `InfluenceOS Score v0`，纯函数、可测试、无副作用。

3. `engine/agent_core/production_preflight.py`
   聚合特征、预测、风险和建议，输出 `PreflightDecision`。

4. `engine/agent_core/learning_pipeline.py` 扩展
   发布后指标回收时，写入 label 和 calibration。

5. `src/pages/Creator.tsx` / 内容工厂 UI
   生产前由 Agent 内部完成工单和预演，主回复不暴露预演流水账。

## 十一、边界纪律

1. 心理学模型只做变量拆解，不伪装成确定性读心术。
2. 《乌合之众》等群体心理只作启发，落地必须转成可观测变量。
3. 平台推荐机制只能模拟公开已知抽象，不逆向、不抓私有算法。
4. 没有真实指标时只输出低置信预测，不冒充训练完成。
5. 用户自己的账号数据权重永远高于公共热点和泛行业经验。
6. 播放量不是唯一目标；账号适配和商业价值必须进入总分。
7. 所有权重升级必须可回放、可解释、可撤销。

## 十二、一句话方向

由深到浅推进：先建社会注意力模型，再建数据闭环，再建可解释分数，再接预演决策，最后才是内容工厂按钮和 UI。

这条线如果做成，Marketing OS 就不是“套壳内容生成器”，而是一个会长期学习账号、平台和人群注意力规律的智能运营系统。

## 十三、与记忆系统和回执系统的闭环关系

2026-07-09 追加结论：预演引擎不是孤立模块。它必须和早期已经建设的复杂记忆系统、数据回执机制串成三核循环：

```text
Memory -> Preflight -> Action -> Receipt -> Retro -> Candidate -> Governance -> Memory
```

详细架构见：

- `docs/architecture/three-core-loop-memory-receipt-preflight.md`

核心边界：

1. 记忆提供历史，但不冒充事实。
2. 回执提供现实，但不自动解释因果。
3. 预演提供未来假设，但必须接受真实指标打脸。
4. 复盘只能生成候选，不能静默改账号策略或公式权重。

## 十四、2026-07-09 工程落地记录：三核闭环第一阶段

状态：`CORE-LOOP-01/02/03 code done / automated verified`

已完成：

1. `PreflightRecord`
   - 表：`preflight_records`
   - 方法：`create_preflight_record`、`get_preflight_record`、`list_preflight_records`、`mark_preflight_used`
   - 用途：保存行动前预测、分数、决策和上下文快照，后续可被真实指标打脸。

2. `ReceiptRef`
   - 表：`receipt_refs`
   - 方法：`create_receipt_ref`、`get_receipt_ref`、`list_receipt_refs`
   - 自动接入：
     - effect receipt
     - publish receipt
     - metric snapshot
   - 特性：按 `source_kind + source_id + receipt_type` 幂等；摘要走脱敏。

3. `LearningCandidate`
   - 表：`learning_candidates`
   - 方法：`create_learning_candidate`、`get_learning_candidate`、`list_learning_candidates`、`decide_learning_candidate`
   - 用途：把回执、预演、预测聚合成待治理候选；不会自动写入正式记忆。

代码路径：

- `engine/agent_core/store.py`
- `engine/agent_core/migrations.py`
- `engine/agent_core/policy.py`
- `tests/test_core_loop_three_engines.py`

验证：

```text
.venv/bin/python -m pytest tests/test_core_loop_three_engines.py -q
4 passed

.venv/bin/python -m pytest tests/test_run18_blind_prediction.py tests/test_learning_pipeline_integration.py tests/test_publishing.py tests/test_desk_09_migrations.py -q
56 passed

.venv/bin/python -m pytest -q
1255 passed, 1 warning
```

下一领取任务：

- `CORE-LOOP-04 / IPE-03` 已进入代码落地；具体记录见下一节。

## 十五、2026-07-09 工程落地记录：内容生产总预演与高阶视频片子预演分离

状态：`CORE-LOOP-04 code done / automated verified`

本轮确认一个关键边界：内容生产前必须有总预演，但高阶视频生成的“片子预演 Agent”必须独立存在。它不是总预演引擎的子分数，也不是账号经营判断的一部分。

### 15.1 两层预演分工

| 层级 | 模块/Agent | 负责 | 不负责 |
|---|---|---|---|
| 内容生产总预演 | `engine/agent_core/production_preflight.py` / `marketing_draft_content_preflight` | 当前内容是否值得进入生产：受众、证据、平台适配、生产可行性、成本安全、记忆支撑 | 镜头调度、美术连续性、样片节奏、表演和声音时序 |
| 高阶视频片子预演 | `engine/video_core/high_end_preflight.py` / `high_end_video_previsualization_agent` | 这条片子作为影像作品是否成立：剧本到画面、镜头可行性、连续性、节奏、声音、预算门 | 账号定位、平台注意力总分、发布决策、长期记忆晋升 |

### 15.2 已落地代码

- `engine/agent_core/production_preflight.py`
  - 新增内容生产总预演。
  - 写入 `preflight_records`。
  - premium human video 只委派高阶视频片子预演，不把镜头分数混进总分。
- `engine/video_core/high_end_preflight.py`
  - 新增独立片子预演纯模块。
  - 保持 video core 边界，不 import `agent_core`、不写营销数据库。
- `engine/agent_core/tool_manifest.py`
  - 新增工具：`marketing_draft_content_preflight`。
- `engine/marketing-os/server.py`
  - 新增 API：`POST /api/marketing-os/content/production/preflight`。
- `src/api/client.ts`、`electron/main.js`、`src/pages/Creator.tsx`
  - 前端/原生桥/内容工厂提示词接入预演链路。

### 15.3 验证证据

```text
.venv/bin/python -m pytest tests/test_production_preflight.py tests/test_content_production.py tests/test_product_closure_guard.py -q
相关测试通过

.venv/bin/python -m pytest tests/test_run_12_13_14.py tests/test_production_preflight.py tests/test_content_production.py tests/test_product_closure_guard.py -q
53 passed

.venv/bin/python -m pytest -q
1261 passed, 1 warning
```

### 15.4 下一领取任务

- `CORE-LOOP-06 / IPE-04` 已进入代码落地；具体记录见下一节。
- `CORE-LOOP-08/09`：工作台和内容工厂保留三核状态，但预演过程默认折叠到对话思考里。

## 十六、2026-07-09 工程落地记录：指标标签化与自动复盘候选

状态：`CORE-LOOP-06 / IPE-04 code done / automated verified`

### 16.1 已落地代码

- `engine/agent_core/learning_pipeline.py`
  - 新增 `build_metric_labels`。
  - 将真实指标映射为 `attention / retention / trust / action / fit / risk`。
  - 缺失维度只记录在 `missing_dimensions`，不把未知写成 0。
- `engine/agent_core/content_retro.py`
  - `engagement_rate` 纳入 prediction vs actual 对账指标。
- `engine/agent_core/store.py`
  - `collect_metrics` 在写入 `publishing_metric_snapshots` 后，把 snapshot 交给学习管线。
- `engine/agent_core/tool_manifest.py`
  - 新增只读工具：`marketing_read_learning_candidates`。
- `engine/marketing-os/server.py`
  - 新增函数/接口：`learning_candidates`、`GET /api/plugins/marketing-os/learning/candidates`。

### 16.2 产品边界

1. 发布前 prediction 不可改写。
2. 发布后 retro 只能追加到 prediction。
3. 指标标签只来自真实 metric snapshot。
4. 没有指标的维度不补 0、不推断。
5. 复盘结果先成为 pending `learning_candidate`，不能静默晋升正式记忆或策略权重。

### 16.3 验证证据

```text
.venv/bin/python -m pytest tests/test_learning_pipeline_integration.py tests/test_server.py::test_sql_publishing_metrics_endpoint_collects_checkpoint_and_learning tests/test_publishing.py::test_publishing_task_lifecycle tests/test_run18_blind_prediction.py tests/test_run19_retro_reconciliation.py tests/test_run_12_13_14.py tests/test_agent_core.py::test_tool_manifest_all_have_valid_levels tests/test_agent_core.py::test_only_implemented_tools_are_registered tests/test_agent_core.py::test_controlled_tools_count -q
65 passed, 1 warning
```

### 16.4 下一领取任务

- `CORE-LOOP-07 / IPE-05` 已进入代码落地；具体记录见下一节。

## 十七、2026-07-09 工程落地记录：候选治理与 InfluenceOS Score v0

状态：`CORE-LOOP-07 / IPE-05 code done / automated verified`

### 17.1 已落地代码

- `engine/agent_core/influence_score.py`
  - 新增 `build_influence_score` 纯函数。
  - 新增 `build_asset_influence_score` 只读聚合入口。
  - 公式版本：`influenceos-score-v0.1`。
  - 输出总分、分项、来源、原因、缺失维度、置信度和决策建议。
- `engine/agent_core/learning_governance.py`
  - 新增 `summarize_learning_patterns`。
  - 新增 `propose_weight_candidate_from_recent_retros`。
  - 默认至少 3 条同类复盘信号才创建 `weight` 候选。
  - 对同类 pending 权重候选做去重，避免每次指标回收都刷候选。
- `engine/agent_core/learning_pipeline.py`
  - `reconcile_published_metrics` 写入 retro 时同步写 `influence_score`。
  - 指标回收后调用候选治理器。
  - 未达阈值返回 `insufficient_evidence`。
  - 达阈值创建 pending `weight` learning candidate。
- `engine/agent_core/tool_manifest.py`
  - 新增只读工具：`marketing_read_influence_score`。
- `engine/marketing-os/server.py`
  - 新增函数/接口：`influence_score`、`GET /api/plugins/marketing-os/influence/score`。

### 17.2 产品边界

1. InfluenceOS Score 是可解释规则，不伪装成神秘黑盒模型。
2. 缺失维度记录为缺失，不补假分。
3. 权重候选只在多条同类证据后生成。
4. 权重候选仍是 pending，不会静默改变正式策略。
5. 这一步只完成“发现规律并提出候选”，还没有完成“历史回放后正式升级权重”。

### 17.3 第一批治理信号

- 有注意力但留存弱：提高 `RetentionDesign` 权重候选。
- 有注意力但行动弱：提高 `BusinessValue` 权重候选。
- 信任/互动强：提高 `PersuasionScore` prior 候选。
- 风险持续出现：提高 `RiskPenalty` 候选。
- 预测连续过度乐观：下调分发 prior 候选。
- 预测连续偏保守：上调分发 prior 候选。

### 17.4 验证证据

```text
.venv/bin/python -m pytest tests/test_influence_score_governance.py tests/test_learning_pipeline_integration.py tests/test_server.py::test_sql_publishing_metrics_endpoint_collects_checkpoint_and_learning tests/test_server.py::test_influence_score_endpoint_reads_asset_features tests/test_run_12_13_14.py tests/test_agent_core.py::test_tool_manifest_all_have_valid_levels tests/test_agent_core.py::test_only_implemented_tools_are_registered tests/test_agent_core.py::test_controlled_tools_count -q
32 passed, 1 warning
```

### 17.5 下一领取任务

- `CORE-LOOP-09 / IPE-06` 已进入代码落地；具体记录见下一节。

## 十八、2026-07-09 工程落地记录：统一 PreflightDecision

状态：`CORE-LOOP-09 / IPE-06 code done / automated verified`

### 18.1 已落地代码

- `engine/agent_core/preflight_decision.py`
  - 新增 `build_preflight_decision` 纯函数。
  - 新增 `build_asset_preflight_decision` 只读资产入口。
  - 新增 `build_score_preflight_decision` 无状态入口。
  - 合约版本：`preflight-decision-v0.1`。
- `engine/agent_core/influence_score.py`
  - 生产前分数补充读取 `production_feasibility` 与 `evidence_strength`。
  - 让没有发布后指标的内容生产阶段也能得到可解释分数。
- `engine/agent_core/production_preflight.py`
  - 内容生产总预演现在同时返回：
    - `scores`
    - `influence_score`
    - `preflight_decision`
    - 兼容旧 UI 的 `decision`
  - 持久化到 `preflight_records.decision` 时也写入统一决策。
- `engine/agent_core/tool_manifest.py`
  - 新增只读工具：`marketing_read_preflight_decision`。
- `engine/marketing-os/server.py`
  - 新增函数：`preflight_decision`。
  - 新增接口：
    - `GET /api/plugins/marketing-os/preflight/decision`
    - `POST /api/plugins/marketing-os/preflight/decision`
- `electron/main.js`
  - 放行桌面桥接：
    - `GET /api/marketing-os/preflight/decision`
    - `POST /api/marketing-os/preflight/decision`
    - `GET /api/marketing-os/influence/score`
- `src/api/client.ts`
  - 新增 `api.influenceScore(...)`
  - 新增 `api.preflightDecision(...)`

### 18.2 产品决策合约

统一决策输出包含：

- `version`
- `stage`
- `status`
- `go`
- `action`
- `selected_lane`
- `score`
- `score_decision`
- `risk_value`
- `primary_reason`
- `next_action`
- `required_next_steps`
- `blockers`
- `warnings`
- `watch_metrics`
- `missing_score_dimensions`
- `ui`

第一版状态集合：

- `ready_for_asset_draft`
- `ready_for_render_prepare`
- `ready_for_publish_review`
- `ready_for_action`
- `needs_audience_context`
- `needs_evidence`
- `replace_or_license_materials`
- `blocked_by_risk`
- `needs_revision`
- `do_not_open_or_publish_yet`
- `delegate_to_video_previsualization`

### 18.3 产品边界

1. `InfluenceOS Score` 只负责算分和解释，不直接决定产品动作。
2. `PreflightDecision` 负责把分数、硬性门槛和阶段转成产品动作。
3. 内容生产、渲染准备、发布审批、正式执行共用同一个决策结构。
4. 旧 `decision.status/go/next_action` 保留兼容，但未来 UI 应优先读 `preflight_decision`。
5. premium human video 仍强制委派独立高阶视频片子预演，不允许总预演替代镜头/美术/节奏判断。

### 18.4 验证证据

```text
.venv/bin/python -m pytest tests/test_preflight_decision.py tests/test_production_preflight.py tests/test_server.py::test_preflight_decision_endpoints_share_unified_contract tests/test_server.py::test_influence_score_endpoint_reads_asset_features tests/test_run_12_13_14.py tests/test_agent_core.py::test_tool_manifest_all_have_valid_levels tests/test_agent_core.py::test_only_implemented_tools_are_registered tests/test_agent_core.py::test_controlled_tools_count -q
33 passed, 1 warning

./node_modules/.bin/tsc --noEmit && node --check electron/main.js && node --check electron/preload.js
passed

.venv/bin/python -m pytest -q
1271 passed, 1 warning
```

### 18.5 下一领取任务

- `CORE-LOOP-09 / IPE-07`：三条内容生产 lane 全部以 `PreflightDecision` 为入口。
  - 软文、不露脸素材视频、高阶视频都不能绕过统一预演。
  - 创建草稿、准备渲染、发布审批都要携带决策依据。
  - UI 后续不新增预演卡；预演、工具调用、证据流水应折叠到对话“思考与执行”。

## 十九、2026-07-09 落地记录：三条内容生产 lane 接入 PreflightDecision

状态：`CORE-LOOP-09 / IPE-07 code done / automated verified`

本轮把“预演引擎”从一个可调用工具，推进成内容生产入口的硬边界。

### 19.1 本轮改动

- 新增 `engine/agent_core/content_lane_gate.py`
  - 统一封装 `content-lane-gate-v0.1`。
  - 每条具体生产 lane 在创建资产前都先调用 `create_content_production_preflight(...)`。
  - 将 `preflight_id`、`status`、`go`、`primary_reason`、`required_next_steps`、`blockers`、`warnings`、`influence_score` 写入资产内容的 `preflight_gate`。
  - 在 `quality_gates` 末尾追加 `总预演门`，不破坏原有事实门、版权门、渲染诚实门顺序。
- 更新 `engine/agent_core/article_soft_production.py`
  - `create_soft_article_asset(...)` 先跑 `PreflightDecision`。
  - 通过时才写内容评分和盲预测。
  - 不通过时只保存阻断草稿，`article_status` 写入如 `needs_audience_context` / `needs_evidence`，不制造“可发布”错觉。
- 更新 `engine/agent_core/faceless_video_production.py`
  - `create_faceless_video_asset(...)` 先跑 `PreflightDecision`。
  - 通过时才写内容评分和盲预测。
  - 不通过时只保存阻断视频草稿，`video_status` 写入总预演状态；仍不下载素材、不注册假附件、不渲染成片。
- 更新 `engine/agent_core/tool_manifest.py`
  - 明确软文和不露脸视频创建工具都会先运行统一总预演。
  - 增补 `audience_context` / `memory_refs` 等上下文字段，减少 Agent 绕过账号定位的概率。

### 19.2 三条 lane 的边界

| lane | 现在入口 | PreflightDecision 作用 | 通过后 | 不通过时 |
|---|---|---|---|---|
| `article_soft` | `marketing_draft_soft_article_create` | 判断受众、证据、平台、生产可行性 | 保存长文资产、平台变体、配图需求、评分、盲预测 | 只保存阻断草稿，不写盲预测 |
| `faceless_video` | `marketing_draft_faceless_video_create` | 判断受众、证据、平台、成本、安全和素材提醒 | 保存脚本、镜头、素材检索包、EDL 草案、评分、盲预测 | 只保存阻断草稿，不进入素材/渲染 |
| `premium_human_video` | `marketing_draft_content_preflight` | 只做账号/商业/生产总预演 | 委派高阶视频片子预演 Agent | 必须返回 `delegate_to_video_previsualization`，不能由总预演替代镜头/美术/节奏判断 |

### 19.3 产品原则

1. 总预演不是“页面提示”，而是创建生产资产前的统一决策门。
2. 阻断不是失败；阻断草稿是为了让用户/Agent 看见缺什么，然后继续补齐。
3. 评分和盲预测只能在 `go=true` 后写入，否则数据飞轮会被垃圾样本污染。
4. 高阶视频拥有独立片子级预演 Agent；总预演只负责“这件事值不值得开机/缺什么上下文”。

### 19.4 当前验证证据

```text
.venv/bin/python -m pytest tests/test_content_production.py tests/test_production_preflight.py tests/test_preflight_decision.py -q
27 passed

.venv/bin/python -m pytest tests/test_content_production.py tests/test_production_preflight.py tests/test_preflight_decision.py tests/test_agent_core.py::test_tool_manifest_all_have_valid_levels tests/test_agent_core.py::test_only_implemented_tools_are_registered tests/test_agent_core.py::test_controlled_tools_count -q
30 passed

./node_modules/.bin/tsc --noEmit && node --check electron/main.js && node --check electron/preload.js
passed

.venv/bin/python -m pytest -q
1272 passed, 1 warning
```

### 19.5 下一领取任务

- `CORE-LOOP-09 / IPE-08`：对话思考折叠与预演去噪。
  - 不把预演门做成新的主 UI 板块。
  - 计划、工具、预演、证据读取等过程默认收进“思考与执行”。
  - 最终回复只交付：能不能做、为什么、产物/草稿 ID、缺什么、下一步。

## 二十、2026-07-09 落地记录：对话思考折叠与预演去噪

状态：`CORE-LOOP-09 / IPE-08 code done / automated verified`

用户修订：预演门不是一个需要摆在工作台或内容工厂上的 UI 板块，它应该是 Agent 的底层思考机制。用户在对话里需要的是清晰结论，不是一堆工具名、数据库字段、预演流水账和证据过程。

### 20.1 本轮改动

- 更新 `src/components/AgentPanel.tsx`
  - 删除对话顶部裸露的“执行计划”和“任务进度”区块。
  - 新增默认收起的 `agent-thinking` 区域。
  - 标题为“思考中 / 思考与执行”，只展示简短状态和完成步数。
  - 展开后才显示计划、工具/读取/预演等过程。
- 更新 `src/index.css`
  - 新增深色/白天模式下的思考折叠条样式。
  - 避免白天模式里过程区文字发灰不可读。
- 更新 `src/pages/Creator.tsx`
  - 仍要求 Agent 内部调用 `marketing_draft_content_preflight`。
  - 但明确最终回复不要暴露工具名、数据库字段、预演流水账或完整证据列表。
  - 最终回复只交付：能不能做、为什么、草稿 ID、还缺什么、下一步。
- 更新 `tests/test_product_closure_guard.py`
  - 增加守卫：`AgentPanel` 必须有 `agent-thinking` / “思考与执行”。
  - 禁止再把“执行计划”“任务进度”裸露回主对话区域。

### 20.2 产品边界

1. 预演门仍然是强制底层门禁，不因为不上 UI 而弱化。
2. 用户主视线只看自然语言结论和产物。
3. 过程透明性通过“可展开”保留，而不是默认打扰。
4. Agent 内部可以知道工具和数据库字段，但回复应像真人运营总监，而不是日志系统。

### 20.3 当前验证证据

```text
.venv/bin/python -m pytest tests/test_product_closure_guard.py -q
13 passed

./node_modules/.bin/tsc --noEmit
passed

node --check electron/main.js && node --check electron/preload.js
passed

.venv/bin/python -m pytest -q
1273 passed, 1 warning
```

### 20.4 下一领取任务

- `CORE-LOOP-09 / IPE-09`：权重候选历史回放与审批升级。
  - 复盘生成的权重候选不能直接影响正式策略。
  - 升级前要能回放历史样本，确认不会让旧案例变差。

## 二十一、2026-07-09 落地记录：权重候选历史回放与审批升级

状态：`CORE-LOOP-09 / IPE-09 code done / automated verified`

本轮把“连续复盘发现规律”推进成“可接受/可拒绝的治理候选”，但仍然不让候选直接改永久权重。

### 21.1 本轮改动

- 更新 `engine/agent_core/learning_governance.py`
  - 新增 `WEIGHT_REPLAY_VERSION = weight-candidate-replay-v0.1`。
  - 新增 `replay_weight_candidate(...)`。
  - 新增 `decide_weight_candidate_with_replay(...)`。
  - 回放检查：
    - 历史支持样本数量。
    - 反例比例。
    - 是否可能误伤过去成功内容。
  - 接受前必须 `replay.status == passed`。
  - 接受后只改变 learning candidate 状态，不修改正式策略权重。
- 更新 `engine/agent_core/tool_manifest.py`
  - 新增只读工具 `marketing_read_weight_candidate_replay`。
  - 新增可逆写工具 `marketing_draft_weight_candidate_decide`。
- 更新 `engine/marketing-os/server.py`
  - 新增 `GET /api/plugins/marketing-os/learning/weight-replay`。
  - 新增 `POST /api/plugins/marketing-os/learning/weight-decision`。
- 更新 `electron/main.js` 与 `src/api/client.ts`
  - 放行并预留 native desktop 调用口。
  - 补上 `learning/candidates` allowlist，避免前端后续读取候选时看起来像断联。

### 21.2 产品边界

1. 权重候选是学习建议，不是自动变更。
2. replay 是底层审计机制，不做主 UI 板块。
3. 用户/Agent 可以接受候选，但接受也只进入“已治理候选”状态。
4. 真正生效必须进入下一层策略候选/实验候选。

### 21.3 验证证据

```text
.venv/bin/python -m pytest tests/test_influence_score_governance.py tests/test_server.py::test_weight_candidate_replay_and_decision_endpoints_guard_learning tests/test_product_closure_guard.py tests/test_run_12_13_14.py::test_manifest_snapshot_tool_names tests/test_run_12_13_14.py::test_manifest_snapshot_tool_count tests/test_run_12_13_14.py::test_manifest_snapshot_level_distribution tests/test_run_12_13_14.py::test_manifest_snapshot_gateway_names_by_level tests/test_agent_core.py::test_tool_manifest_all_have_valid_levels tests/test_agent_core.py::test_only_implemented_tools_are_registered tests/test_agent_core.py::test_controlled_tools_count -q
26 passed, 1 warning

./node_modules/.bin/tsc --noEmit
passed

node --check electron/main.js && node --check electron/preload.js
passed

.venv/bin/python -m pytest -q
1276 passed, 1 warning
```

## 二十三、2026-07-09 落地记录：accepted 策略候选转实验草案

状态：`CORE-LOOP-09 / IPE-11 code done / automated verified`

本轮继续后端主线，把 IPE-10 生成的 `calibrate_influence_weight` 策略候选接到账号实验系统。

### 23.1 本轮改动

- 更新 `engine/agent_core/account_lifecycle.py`
  - 新增权重校准实验指标映射：
    - `PlatformReachPotential` → attention
    - `RetentionDesign` → retention
    - `PersuasionScore` → trust
    - `BusinessValue` → action
    - `RiskPenalty` → risk
  - `decide_strategy_candidate(... decision="accepted")` 接受 `calibrate_influence_weight` 后，自动生成一条 `account_experiments.status=draft`。
  - 实验草案写入：
    - `source_strategy_candidate_id`
    - `source_weight_candidate_id`
    - `rule_key`
    - `component / direction / amount`
    - `test_design`
    - `prediction`
    - `success_criteria`
  - 若账号定位尚未 approved，只返回 `materialization.status=blocked`，不创建实验。
  - 不修改永久定位、不修改永久权重、不自动生成内容。

- 更新 `tests/test_account_lifecycle.py`
  - 覆盖 accepted 策略候选生成 draft 实验。
  - 覆盖缺少 approved positioning 时阻断实验生成。

### 23.2 产品意义

这一步把三大核心循环真正串上了一段：

```text
发布回执 / 复盘
  → learning weight candidate
  → replay gate
  → strategy candidate
  → draft content experiment
  → 下一条内容生产与发布
```

也就是说，Agent 不是“学到一个建议就完了”，而是会把建议转成下一轮可验证的实验。

### 23.3 产品边界

1. 策略候选 accepted 仍然不是永久策略生效。
2. 实验草案只是一张任务单，需要内容生产端生成资产后再进入发布、回执和复盘。
3. 没有 approved positioning 时不造实验，避免未定位账号被系统误带节奏。
4. UI 不新增复杂入口，预演门与实验门继续隐藏在 Agent 思考和后端任务流里。

### 23.4 当前验证证据

```text
.venv/bin/python -m pytest tests/test_account_lifecycle.py::test_accepted_weight_strategy_candidate_creates_draft_experiment tests/test_account_lifecycle.py::test_accepted_weight_strategy_candidate_blocks_experiment_without_positioning -q
2 passed

.venv/bin/python -m pytest tests/test_account_lifecycle.py tests/test_influence_score_governance.py tests/test_server.py::test_weight_candidate_replay_and_decision_endpoints_guard_learning -q
32 passed, 1 warning

.venv/bin/python -m pytest -q
1285 passed, 1 warning
```

## 二十二、2026-07-09 落地记录：accepted 权重候选转策略候选

状态：`CORE-LOOP-09 / IPE-10 code done / automated verified`

本轮把“被接受的权重候选”接入账号生命周期策略候选，但仍然不直接修改账号定位、内容权重或永久策略。

### 22.1 本轮改动

- 更新 `engine/agent_core/account_lifecycle.py`
  - `STRATEGY_TRIGGERS` 新增 `weight_candidate_replay`。
- 更新 `engine/agent_core/learning_governance.py`
  - `decide_weight_candidate_with_replay(...)` 在接受候选后尝试生成 strategy candidate。
  - 有活跃账号项目时，生成 `type=calibrate_influence_weight` 策略候选。
  - 没有活跃账号项目时，只接受 learning candidate，不暗中创建项目。
  - 重复接受已接受候选时保持幂等，不重复生成策略候选。
- 更新 `engine/agent_core/tool_manifest.py`
  - `marketing_draft_strategy_candidate.trigger` 允许 `weight_candidate_replay`。

### 22.2 策略候选内容

生成的策略候选包含：

- `source_weight_candidate_id`
- `rule_key`
- `proposed_adjustment`
- `recommendation`
- `replay_summary`
- `scope`
- `next_action`
- `guardrail`

它的作用是指导下一轮内容实验或定位修订，而不是立即改永久权重。

### 22.3 产品边界

1. `learning_candidate.accepted` 不是“策略已经生效”。
2. `strategy_candidate.pending` 才是面向账号生命周期的下一步。
3. 没有账号项目时不创建空项目，避免把普通对话误升级成账号策略。
4. 这一步继续符合前端哲学：底层闭环变强，UI 不新增复杂入口。

### 22.4 当前验证证据

```text
.venv/bin/python -m pytest tests/test_influence_score_governance.py tests/test_server.py::test_weight_candidate_replay_and_decision_endpoints_guard_learning tests/test_account_lifecycle.py::test_strategy_candidate_rejection_requires_reason_and_preserves_decision tests/test_run_12_13_14.py::test_manifest_snapshot_tool_names tests/test_agent_core.py::test_tool_manifest_all_have_valid_levels tests/test_agent_core.py::test_only_implemented_tools_are_registered -q
10 passed, 1 warning

./node_modules/.bin/tsc --noEmit
passed

node --check electron/main.js && node --check electron/preload.js
passed

.venv/bin/python -m pytest tests/test_influence_score_governance.py tests/test_account_lifecycle.py tests/test_server.py::test_weight_candidate_replay_and_decision_endpoints_guard_learning tests/test_run_12_13_14.py tests/test_agent_core.py::test_tool_manifest_all_have_valid_levels tests/test_agent_core.py::test_only_implemented_tools_are_registered tests/test_agent_core.py::test_controlled_tools_count -q
52 passed, 1 warning

.venv/bin/python -m pytest -q
1276 passed, 1 warning
```
