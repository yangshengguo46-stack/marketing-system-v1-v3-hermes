# 影响力与注意力建模路线图

> 建立日期：2026-07-09
> 关联资料库：`08-data-flywheel-strategy.md`、`09-video-ecosystem-research.md`、`10-creator-data-collection-research.md`、`11-social-account-lifecycle-and-open-source.md`
> 核心判断：预演不是让大模型“猜一下”。预演的底层必须是数据、特征、预测、真实结果和复盘校准。长期目标是沉淀出本项目自己的影响力/注意力评分公式。

## 一、上位定义

内容生产端真正要预测的不是“会不会火”这四个字，而是：

1. 这条内容能不能在目标平台获得初始注意力。
2. 它能不能留住用户，不只是被划过去。
3. 它能不能触发互动、收藏、转发、关注或咨询。
4. 它是否符合当前账号定位，而不是偶然蹭到一波无效流量。
5. 它的表现是否能反过来修正账号 DNA、选题策略、镜头策略和写作风格。

因此先把三个概念拆开：

| 概念 | 含义 | 典型指标 |
|---|---|---|
| 注意力 `Attention` | 用户是否停下来、看下去 | 曝光/播放、3 秒留存、5 秒完播、平均观看时长、完播率 |
| 信任 `Trust` | 用户是否觉得内容可信、值得保存或继续看这个账号 | 收藏、转发、正向评论、主页访问、关注率、负反馈率 |
| 影响力 `Influence` | 内容是否改变用户行为或账号长期势能 | 涨粉、私信/咨询、转化动作、复看、系列追更、账号标签强化 |

短期爆款只有 Attention，不一定有 Influence。我们的产品不能只优化播放量，否则会把账号带向垃圾流量。

## 二、数据从哪里来

数据来源按可信度和用途分层，不能混在一起。

| 数据层 | 来源 | 用途 | 可信度 | 边界 |
|---|---|---|---|---|
| 第一方账号数据 | 创作者中心、官方 API、用户授权导出、MCP 可见页面 | 账号真实表现、粉丝画像、单条内容指标 | 最高 | 只采用户自己的账号；缺字段必须标 `dataGap` |
| 发布回执与指标 checkpoint | 发布任务、post_id、URL、1h/6h/24h/3d/7d 指标回收 | 训练预测模型、复盘偏差 | 高 | 没有真实 post_id/URL 不算已验证发布 |
| 内容资产数据 | 标题、脚本、正文、镜头表、EDL、素材、配音、封面、版本 | 抽取内容特征 | 高 | 完整草稿不进长期记忆，只进内容资产 |
| 盲预测与评分 | 发布前 Agent/用户/盲评 Agent 的预测和 rubric 分 | 校准“判断是否准确” | 高 | 预测写入后不可修改 |
| 用户反馈数据 | 用户采纳/拒绝、修改点、审稿意见、发布前否决原因 | 学会用户偏好和禁忌 | 高 | 必须区分用户审美偏好和平台真实结果 |
| 对标账号样本 | 对标账号公开作品、标题、结构、互动、评论样本 | 冷启动 anchor、行业基线 | 中 | 只能作外部观察，不能当用户账号事实 |
| 平台热点与搜索数据 | 抖音/B站/知乎/小红书/TikTok 等热点与搜索结果 | 选题时效性、话题供给 | 中 | 热度不等于适合当前账号 |
| 素材与生成数据 | 授权素材、代码生成视觉、AI 生图/生视频、TTS、BGM | 判断生产质量、成本、版权和复用效果 | 中 | 必须记录来源、license/hash/参数 |
| 公共行业资料 | Firecrawl、网页、报告、新闻、产品页 | 软文证据、行业观点、可信背书 | 中 | 没 URL 的事实不能作为强结论 |
| 脱敏聚合数据 | 多用户授权后的行业统计 | 平台/行业基准 | 可变 | 必须明确授权、脱敏、不可反推个人 |

第一阶段只需要把第一方账号数据、内容资产、发布回执、盲预测、用户反馈打通；对标和热点用于冷启动；脱敏聚合是规模化后的事情。

## 三、每条内容都要变成一条训练样本

每次由 Marketing OS 生产的软文或不露脸视频，都应该落成一个可训练样本。独立视频产品的结果只有通过未来正式 Port/API 回传后，才能作为外部观测样本进入本系统，不能在这里复制它的生产状态。

```json
{
  "content_id": "asset_xxx",
  "account_id": "acct_xxx",
  "platform": "douyin",
  "content_type": "faceless_video",
  "topic": "...",
  "features": {
    "hook_type": "反常识/痛点/悬念",
    "topic_freshness": 0.82,
    "audience_fit": 0.74,
    "evidence_quality": 0.68,
    "creator_fit": 0.61,
    "platform_fit": 0.77,
    "visual_density": 0.7,
    "rhythm_score": 0.66,
    "trust_signal": 0.58,
    "risk_penalty": 0.12,
    "data_gap_penalty": 0.05
  },
  "pre_publish_prediction": {
    "expected_views": {"low": 100, "mid": 800, "high": 3000},
    "expected_completion_rate": {"low": 0.18, "mid": 0.32, "high": 0.48},
    "confidence": "medium"
  },
  "actual_metrics": {
    "views_1h": 0,
    "views_24h": 0,
    "completion_rate": 0,
    "like_rate": 0,
    "comment_rate": 0,
    "share_rate": 0,
    "save_rate": 0,
    "follow_rate": 0,
    "negative_rate": 0
  },
  "retro": {
    "bias_direction": "over_predicted|under_predicted|calibrated",
    "likely_causes": [],
    "strategy_candidate": {}
  }
}
```

这条样本的价值不只是“保存结果”，而是让系统知道：

- 什么样的标题在这个账号上有效。
- 什么样的选题会吸来无效流量。
- 哪些素材/镜头/封面提升完播。
- 哪些用户总是拒绝。
- 哪些平台需要更短、更强冲突、更生活化或更证据化。
- Agent 哪些预测长期偏高，哪些长期偏低。

## 四、特征工程：影响注意力的变量

初始版本不用上来就搞复杂机器学习，先把影响力拆成可解释特征。

| 特征组 | 特征 | 说明 |
|---|---|---|
| 账号特征 | 账号阶段、粉丝量、历史完播、历史互动、粉丝画像、账号定位版本 | 同一内容放在不同账号上结果不同 |
| 受众特征 | 目标受众、真实受众、对标受众、受众缺口 | 判断是不是“吸对人” |
| 选题特征 | 热点强度、时效性、行业相关度、争议度、稀缺度 | 热点只是原料，不是答案 |
| 内容结构 | hook 类型、信息密度、反转点、证明链、CTA、情绪曲线 | 对应短视频/软文的叙事结构 |
| 平台适配 | 平台、时长、标题风格、标签、封面、发布时间 | 不同平台注意力机制不同 |
| 视觉/剪辑 | 镜头数、平均镜头时长、字幕密度、BGM、素材贴合度、代码视觉质量 | 视频内容必须有剪辑特征 |
| 信任信号 | 证据 URL、案例、真实经历、专业身份、评论情绪 | 影响收藏、转发、关注 |
| 风险信号 | 标题党、争议过载、违规风险、版权风险、低质素材味 | 需要负向扣分 |
| 生产信号 | 生成成本、重试次数、用户修改次数、审片通过率 | 影响可规模化程度 |
| 外部环境 | 发布时间、平台当天热点、同类话题拥挤度、节假日 | 用来解释异常波动 |

每个特征都必须保留来源：来自平台、内容资产、用户输入、模型推断还是对标观察。模型推断不能伪装成事实。

## 五、v0 公式：可解释的注意力潜力分

第一版不追求神秘，先追求可解释、可校准、可回放。

对某条内容 `c`，账号 `a`，平台 `p`，发布时间 `t`：

```text
AttentionPotential(c,a,p,t)
  = sigmoid(
      β0
    + β1 * HookStrength
    + β2 * TopicMomentum
    + β3 * AudienceFit
    + β4 * PlatformFit
    + β5 * RetentionDesign
    + β6 * EvidenceTrust
    + β7 * VisualRhythm
    + β8 * CreatorFit
    + β9 * TimingFit
    - γ1 * RiskPenalty
    - γ2 * DataGapPenalty
    - γ3 * FatiguePenalty
  )
```

影响力不能只等于注意力，因此再定义：

```text
InfluenceScore
  = AttentionPotential
  * TrustMultiplier
  * ActionMultiplier
  * AccountFitMultiplier
  * LongTermValueMultiplier
```

其中：

| 项 | 含义 |
|---|---|
| `AttentionPotential` | 停留/播放/完播潜力 |
| `TrustMultiplier` | 证据、专业性、真实感、正向评论倾向 |
| `ActionMultiplier` | 关注、收藏、转发、咨询、点击等行动倾向 |
| `AccountFitMultiplier` | 是否强化账号定位，而不是带偏账号 |
| `LongTermValueMultiplier` | 是否能形成系列、复用素材、沉淀技能、推动商业目标 |

这个公式不是最终真理，而是 v0 工作台。它必须被真实发布结果不断校准。

## 六、从公式到独家算法的演进路径

### 阶段 0：规则评分

用当前 RUN-17 rubric、负面信号、证据质量、数据质量、素材适配分先跑起来。目标不是准确预测绝对播放量，而是把坏内容、无证据内容、不适合账号的内容拦住。

### 阶段 1：账号内校准

同一账号发布 20-50 条后，开始学习该账号自己的权重：

- 哪类 hook 对这个账号有效。
- 哪些选题吸粉，哪些只带来泛流量。
- 哪些标题用户不喜欢。
- 软文和短视频哪个更能转化。
- 发布时段是否影响初始流量。

这一阶段适合用简单可解释模型：线性回归、逻辑回归、贝叶斯更新、排序模型，而不是一上来黑盒大模型。

### 阶段 2：平台/行业校准

同一行业、同一平台积累足够样本后，建立平台/行业基线：

- 抖音更重开头停留和完播。
- B站更重标题、内容密度和用户收藏。
- 知乎/公众号更重证据、可信度和结构。
- 小红书更重封面、场景感和实用性。

这里要做的是“平台差异权重”，不是一个公式套所有平台。

### 阶段 3：对标迁移

新用户没有历史数据时，用 5-10 个对标账号样本生成初始 anchor：

```text
NewAccountPrior = IndustryBaseline + BenchmarkAnchor + UserGoalConstraint
```

等用户自己的真实数据回来后，逐步降低对标权重，提高一方数据权重：

```text
FinalWeight = λ * OwnAccountData + (1 - λ) * BenchmarkPrior
```

其中 `λ` 随样本量、数据质量、时间新鲜度增长。

### 阶段 4：私有注意力算法

当系统有足够多经过授权和脱敏的数据后，可以形成自己的多层模型：

```text
AttentionModel =
  AccountModel
  + PlatformModel
  + ContentStructureModel
  + TrendTimingModel
  + MaterialQualityModel
  + UserPreferenceModel
  - RiskModel
```

这时“公式”不一定是一个单行数学表达式，而是一组可解释模型和权重协议。对外可包装成一个产品概念，例如：

```text
InfluenceOS Score = f(注意力, 信任, 行动, 账号适配, 长期价值, 风险)
```

它的真正壁垒不是公式本身，而是数据闭环：预测写在发布前，结果来自真实平台，复盘能改权重，用户能纠正，账号能长期积累。

## 七、必须避免的伪智能

1. 只拿热点热度当预测依据。
2. 只用大模型主观打分，不保存后验结果。
3. 发布后看到数据再修改预测。
4. 把不同平台指标简单相加。
5. 把播放量当唯一成功指标。
6. 把对标账号结论直接套到用户账号。
7. 数据缺失时用 0 或模型脑补。
8. 只优化爆款，不优化账号定位和商业目标。

这些都会让系统看起来聪明，但长期会把账号带歪。

## 八、产品呈现方式

用户不需要看到一堆数学公式。用户应该看到的是：

```text
开机前判断

预计注意力：中高
预计信任/收藏：中
账号适配：偏弱，需要补真实经历
最大风险：热点过泛，可能吸来无效流量
建议动作：先改成“AI 教育 × 普通人转型”的账号主线版本，再开机
```

专业用户可以点开“为什么这么判断”，看到：

- 参考了哪些历史样本。
- 哪些对标账号支持这个判断。
- 哪些数据字段缺失。
- 哪些权重拉高/拉低了分数。
- 如果发布，系统会在什么时间点回收哪些指标。

## 九、落地任务建议

| ID | 任务 | 目标 |
|---|---|---|
| IAM-01 | 建立 `content_feature_snapshots` | 每条内容发布前保存特征快照，保证预测可回放 |
| IAM-02 | 建立 `attention_predictions` v2 | 从简单 expected_views 扩展为 attention/trust/action/account_fit/risk 五组预测 |
| IAM-03 | 建立 `metric_labels` | 把 1h/6h/24h/3d/7d 指标转成统一标签，区分注意力、信任、行动 |
| IAM-04 | 建立 `prediction_calibration` | 按账号/平台/内容类型统计预测偏高、偏低和置信度 |
| IAM-05 | 建立 `influence_score_v0` | 用可解释权重输出第一版 InfluenceOS Score |
| IAM-06 | 接入 Preflight UI | 在内容生产前展示预计注意力、信任、行动、风险和依据 |
| IAM-07 | 引入对标 prior | 新账号用对标账号样本做冷启动，真实数据回来后逐步退权重 |
| IAM-08 | 权重升级协议 | 学习到新权重后不直接生效，必须全量回放历史样本并通过审核 |

## 十、一句话总结

预演的核心不是“生成前看一眼”，而是建立一个长期校准的注意力模型。

短期我们做的是评分、盲预测、发布回执和复盘；中期我们做账号内权重校准；长期我们做平台/行业/账号三层融合的 InfluenceOS Score。最终壁垒不是某个 API 或某个视频模型，而是用户自己的数据越用越多，系统对这个账号的判断越来越准。

## 十一、人类注意力机制 × 群体心理 × 平台推荐

> 2026-07-09 追加：预演引擎不应只模拟平台，也不应只模拟用户心理。它应该模拟一条内容进入社会注意力场后的三重过滤：个体注意、群体扩散、平台分发。

### 11.1 AI 注意力机制只能作类比，不能直接等同人脑

Transformer 的 scaled dot-product attention 可以写成：

```text
Attention(Q,K,V) = softmax(QKᵀ / √d_k) V
```

它的启发是：一个 token 会根据 query 与 key 的相似度，把注意力权重分配给不同 value。

人类注意力也有“选择性分配”，但底层不是同一个机制。人类注意力至少受以下因素影响：

- 新奇：反常识、冲突、未完成信息。
- 情绪：恐惧、愤怒、希望、归属、羞耻、爽感。
- 奖赏：收益、机会、省钱、省力、变美、变强、被认可。
- 威胁：损失、错过、被淘汰、身份受损。
- 社会证明：别人都在看、都在讨论、都在转发。
- 身份认同：这是不是“我这种人”会关心的事。
- 认知负荷：是否太难、太乱、太费脑。

因此我们的建模不应该叫“模拟大脑”，而应该叫：

```text
HumanAttentionKernel = Salience + Emotion + Reward + SocialProof + IdentityFit - CognitiveLoad - RiskDisgust
```

### 11.2 个体层：人为什么停下来

个体层负责预测“用户刷到这一条时会不会停、会不会看完、会不会行动”。

可落地公式：

```text
StopProbability
  = sigmoid(
      w1 * HookSalience
    + w2 * PersonalRelevance
    + w3 * Novelty
    + w4 * EmotionalArousal
    + w5 * SocialProofCue
    - w6 * CognitiveLoad
    - w7 * TrustRisk
  )
```

```text
ContinueProbability
  = sigmoid(
      v1 * NarrativeTension
    + v2 * InformationGap
    + v3 * PacingFit
    + v4 * VisualRhythm
    + v5 * ExpectedReward
    - v6 * Boredom
    - v7 * Confusion
  )
```

```text
ActionProbability
  = sigmoid(
      a1 * Motivation
    + a2 * Ability
    + a3 * PromptStrength
    + a4 * Trust
    + a5 * IdentityFit
    - a6 * Friction
  )
```

其中 `ActionProbability` 借鉴 Fogg Behavior Model：行为发生需要 Motivation、Ability、Prompt 同时满足。

### 11.3 说服层：用户为什么相信

营销不是把人骗住，而是降低用户理解和行动的阻力。

可拆成：

```text
PersuasionScore
  = CentralRouteScore * Involvement
  + PeripheralCueScore * (1 - Involvement)
```

借鉴 ELM 精细加工可能性模型：

- 高涉入用户看证据、逻辑、案例、专业度。
- 低涉入用户看情绪、权威、社会证明、包装、熟悉感。

内容生产时可以用它判断表达方式：

| 用户状态 | 更有效的内容 |
|---|---|
| 高涉入、高决策成本 | 证据链、对比、案例、数据、反方观点 |
| 低涉入、刷到即走 | 强 hook、短结论、情绪、符号、熟悉场景 |
| 已有需求但犹豫 | 风险解除、信任背书、步骤化方案 |
| 没有需求 | 先造问题意识，不直接卖方案 |

### 11.4 群体层：内容为什么扩散

《乌合之众》这类群体心理学给我们的启发不是“操纵群众”，而是：个体在群体语境中会受到感染、暗示、身份和从众影响。现代实现上应转成可观测变量：

```text
SocialPropagation
  = Contagion
  + SocialProof
  + IdentitySignal
  + GroupConflict
  + ShareUtility
  - ReputationRisk
```

可用三个经典模型做底座：

#### 1. 阈值模型

用户是否参与转发/评论，取决于他看到多少人已经参与，以及这件事是否符合身份。

```text
Join_i = 1 if ObservedAdoptionRate >= Threshold_i
```

产品上对应：

- 早期评论质量很重要。
- 标题和评论区要降低“第一个表态”的心理风险。
- 争议内容扩散快，但可能伤账号长期信任。

#### 2. Bass 扩散模型

新内容/新观点的扩散可用创新系数 `p` 和模仿系数 `q` 近似：

```text
f(t) = (p + q * F(t)) * (1 - F(t))
```

- `p`：用户因为内容本身新奇/有用而采纳。
- `q`：用户因为别人看了、转了、讨论了而采纳。

短视频里，`q` 常常比 `p` 更像平台放大后的社会证明效应。

#### 3. 病毒系数 K

```text
K = invites_per_user * conversion_rate
```

对内容系统可改写为：

```text
ContentK
  = ShareRate
  * ShareAudienceConversion
  * PlatformRefeedMultiplier
```

如果 `ContentK > 1`，内容具备自扩散潜力；如果小于 1，就主要依赖平台初始推荐。

### 11.5 平台层：内容为什么被继续推荐

平台推荐通常可以抽象为多目标排序：

```text
PlatformScore
  = Σ weight_i * P(user_action_i | user, content, context)
  - RiskPenalty
  - QualityPenalty
  - FatiguePenalty
```

不同平台的 action 权重不同，但一般都会包括：

- 停留/播放。
- 完播/观看时长。
- 点赞、评论、分享、收藏。
- 关注、主页访问。
- 不感兴趣、划走、举报、拉黑等负信号。
- 内容质量、安全、原创、版权、重复度。

这和 YouTube 论文里“候选生成 + 排序”、TikTok 官方说明里的“用户互动、视频信息、设备/账号设置”是一致的抽象。X/Twitter 开源算法也能看到类似思想：预测多种行为概率，再加权排序。

我们的实现不需要复制平台算法，而是建立平台模拟器：

```text
PlatformSimulator(platform)
  -> expected_initial_exposure
  -> expected_retention_gate
  -> expected_interaction_gate
  -> expected_second_wave_distribution
```

也就是模拟一条内容通过平台分发闸门的概率。

## 十二、营销公式库：从心理到业务结果

### 12.1 AIDA 内容漏斗

```text
Attention -> Interest -> Desire -> Action
```

对应我们的指标：

| AIDA | 内容指标 |
|---|---|
| Attention | 停留、播放、3 秒留存 |
| Interest | 平均观看时长、完播、展开全文 |
| Desire | 收藏、转发、主页访问、评论询问 |
| Action | 关注、私信、表单、购买、咨询 |

### 12.2 行为发生公式

```text
Behavior = Motivation × Ability × Prompt
```

产品转写：

```text
ConversionLikelihood
  = MotivationScore
  * EaseScore
  * PromptClarity
  * TrustScore
```

这能解释很多内容“播放不错但没转化”的问题：注意力有了，但动机、信任或行动路径没打通。

### 12.3 注意力到影响力总公式

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

它不是一开始就靠机器学习拟合出来，而是先作为可解释规则；后续每次发布后，用真实数据校准各项权重。

### 12.4 指标标签化

平台返回的是原始指标，我们要转成训练标签：

| 训练标签 | 原始指标 |
|---|---|
| `attention_label` | 3 秒留存、播放、曝光点击、平均观看时长 |
| `retention_label` | 完播率、5 秒完播、平均播放时长/视频长度 |
| `trust_label` | 收藏率、转发率、正向评论率、低负反馈 |
| `action_label` | 关注率、私信率、咨询率、主页访问 |
| `fit_label` | 粉丝画像是否接近目标受众、评论关键词是否贴合定位 |
| `risk_label` | 举报、不感兴趣、低质评论、异常掉粉 |

这样以后就不是笼统预测“播放量”，而是分别预测注意力、留存、信任、行动和账号适配。

## 十三、实现方案：社会注意力预演引擎

建议把预演引擎拆成 5 个可替换模块：

```text
ContentFeatures
  -> HumanAttentionModel
  -> CrowdPropagationModel
  -> PlatformSimulator
  -> BusinessImpactModel
  -> PreflightDecision
```

### 13.1 输入

- 账号阶段、账号定位、粉丝画像、历史内容表现。
- 内容标题、脚本、正文、封面、EDL、镜头、素材、证据。
- 平台、发布时间、热点上下文、对标样本。
- 用户目标：涨粉、咨询、种草、建立信任、卖课、招商、私域等。

### 13.2 输出

```json
{
  "attention": {"score": 0.72, "why": ["hook strong", "topic fresh"]},
  "retention": {"score": 0.58, "why": ["middle section may be dense"]},
  "trust": {"score": 0.44, "why": ["needs stronger evidence"]},
  "action": {"score": 0.31, "why": ["CTA weak"]},
  "account_fit": {"score": 0.62, "why": ["topic fits but audience too broad"]},
  "platform_fit": {"score": 0.69, "why": ["douyin short hook ok"]},
  "risk": {"score": 0.18, "why": ["slight title-bait risk"]},
  "decision": "revise_before_publish",
  "recommended_fix": [
    "补一个真实案例",
    "把标题从泛热点改成目标用户痛点",
    "前 3 秒给出冲突而不是背景"
  ]
}
```

### 13.3 学习闭环

```text
发布前：保存 feature_snapshot + prediction
发布后：回收 1h/6h/24h/3d/7d metrics
复盘：prediction vs actual
校准：更新账号内权重候选
审核：通过后升级 influence formula version
回放：新公式重跑历史样本，避免过拟合
```

### 13.4 冷启动

没有用户历史数据时，模型权重来自：

```text
ColdStartPrior
  = GenericHumanAttentionPrior
  + PlatformPrior
  + BenchmarkAccountPrior
  + UserGoalConstraint
```

有真实数据后：

```text
PersonalizedModel
  = λ * OwnAccountEvidence
  + (1 - λ) * ColdStartPrior
```

`λ` 随内容样本量、指标完整度、时间新鲜度上升。

## 十四、资料依据

- Transformer 注意力公式：[Vaswani et al., *Attention Is All You Need*](https://arxiv.org/abs/1706.03762)。
- 行为发生模型：[Fogg Behavior Model](https://behaviormodel.org/)：行为发生需要 Motivation、Ability、Prompt。
- 行为改变系统：[COM-B model](https://implementationscience.biomedcentral.com/articles/10.1186/1748-5908-6-42)：Capability、Opportunity、Motivation 共同驱动 Behavior。
- ELM 精细加工可能性模型：[Petty & Cacioppo, *Communication and Persuasion*](https://psycnet.apa.org/record/1986-98619-000)：高涉入走中央路径，低涉入走外围线索。
- 群体阈值模型：[Granovetter, *Threshold Models of Collective Behavior*](https://www.jstor.org/stable/2778111)：集体行为中的参与阈值。
- 扩散模型：[Bass, *A New Product Growth for Model Consumer Durables*](https://doi.org/10.1287/mnsc.15.5.215)：创新系数 `p` 与模仿系数 `q`。
- 群体心理经典启发：[Le Bon, *The Crowd*](https://www.gutenberg.org/ebooks/445)：感染、暗示、群体身份等概念只作启发，不作硬公式。
- TikTok 官方推荐说明：[How TikTok recommends videos #ForYou](https://newsroom.tiktok.com/en-us/how-tiktok-recommends-videos-for-you)：用户互动、视频信息、设备和账号设置共同影响推荐。
- YouTube 推荐系统论文：[Deep Neural Networks for YouTube Recommendations](https://research.google/pubs/deep-neural-networks-for-youtube-recommendations/)：候选生成与排序的两阶段架构。
- X/Twitter 开源推荐算法：[the-algorithm](https://github.com/twitter/the-algorithm)：多行为预测与加权排序思路。

采用原则：这些公式不是拿来迷信，而是拿来拆变量。真正的产品壁垒来自我们的发布前预测、真实发布结果、账号长期数据和可回放校准。
