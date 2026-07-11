# Agent Memory 前沿研究与采用结论（2026）

## 一、结论先行

本项目不采用“完整聊天记录 + 单个向量库 = 记忆”的方案。目标记忆系统由六类数据组成：

| 层 | 回答的问题 | 主要存储 | 是否直接进上下文 |
|---|---|---|---|
| 工作记忆 | 本轮正在做什么 | AgentTask checkpoint、最近消息、当前计划 | 是，受 token 预算约束 |
| 用户记忆 | 用户稳定偏好、禁区和授权边界是什么 | 结构化事实、证据、版本 | 少量热点事实常驻 |
| 账号记忆 | 这个账号是谁、面向谁、现在处于什么阶段 | Account DNA、平台维度状态 | 按账号和任务装配 |
| 情景记忆 | 过去发生过什么、为什么成功或失败 | 事件日志、任务轨迹、反馈、复盘 | 检索后按需注入 |
| 语义知识 | 平台、行业和内容方法论是什么 | 带来源和有效期的知识条目/文档 | 检索后按需注入 |
| 程序性记忆 | 下次遇到相似任务应怎么做 | 版本化技能、适用条件、测试、效果统计 | 命中技能时加载 |

发布指标、实验因果和策略权重不是“记忆文本”，必须进入独立的结果/实验系统。LLM 可以提出假设和复盘，但不能直接改生产策略权重。

## 二、前沿共识与项目含义

### 1. 记忆是 write → manage → read 的闭环

2026 年综述把现代 Agent memory 归纳为写入、管理和读取闭环，并把矛盾处理、隐私、延迟预算和遗忘列为实际工程问题。LongMemEval 与 MemoryAgentBench 也表明，评测不能只问“能否搜到一句话”，还要测跨会话推理、时间推理、知识更新、拒答和选择性遗忘。

项目决定：每一条长期记忆都必须经历候选提取、分类、去重/冲突处理、授权策略、提交、索引和审计；召回结果也必须记录为什么被选中。

### 2. 事实、经历、规则应分开

CoALA 和 LangGraph 的语义/情景/程序性划分很适合我们的业务：用户偏好是语义事实；某条视频从选题到结果是情景；经过多次验证的恢复流程才是程序性技能。

项目决定：禁止把“用户不喜欢这个标题”“这次低播放”“平台抓取失败”都混成一段 `MEMORY.md`。

### 3. 热记忆与归档记忆要分层

Letta 的 memory block 强调少量、重要、始终可见且可设置只读的上下文；大资料通过文件、归档或外部检索按需加载。Anthropic 的 context engineering 同样强调 just-in-time 检索，不要把可能有用的全部材料预先塞进上下文。

项目决定：常驻上下文只保留当前用户、当前账号、当前目标和不可违反的边界；平台知识、历史内容和长轨迹用引用 ID 延迟加载。

### 4. 时间、更新和冲突是一等公民

LongMemEval 专门评估 temporal reasoning 与 knowledge update。Graphiti/Zep 使用时态知识图谱保留事实有效时间和历史关系；A-MEM 允许新记忆触发旧记忆的关联与演化。

项目决定：第一阶段先在关系表中实现 `observed_at / valid_from / valid_to / supersedes_id / confidence`，不急着上图数据库。只有跨账号、人物、品牌、内容和事件的多跳查询证明有收益后，才引入时态图。

### 5. “越记越多”会放大错误

2025 年经验研究发现，高相似度记忆会强烈牵引后续输出，错误经验和过时经验会传播；选择性新增与删除优于无限追加。2026 年 OWASP 进一步把持久记忆视为提示注入和上下文污染的攻击面。

项目决定：

- 外部网页、评论区和抓取内容默认是证据，不是可信记忆。
- 推断偏好至少需要重复证据或用户确认；一次拒绝不形成永久标签。
- 记忆有 TTL、失效原因和用户纠错入口。
- 检索时同时考虑账号、平台、任务、时间、可信度和负反馈，不只看向量相似度。

### 6. 自我改进应沉淀为可验证技能，而不是静默改提示词

Reflexion 把任务反馈写成情景反思，ExpeL 从多次经验提炼可复用知识，Voyager 把经过环境反馈和自验证的行为保存为技能库。共同点是经验要经过反馈与验证，而非一次成功就固化。

项目决定：候选技能至少包含适用条件、步骤、失败分支、权限需求、测试样例和效果证据；默认经过 staging、回放和人工审核后启用。

## 三、写入策略

```text
对话/工具/发布结果
      ↓
生成 MemoryCandidate（不直接写长期记忆）
      ↓
类型分类 + 秘密扫描 + 来源可信度
      ↓
去重 / 矛盾 / supersede / 账号与平台隔离
      ↓
策略决策：自动提交、通知后提交、等待确认、拒绝
      ↓
结构化事实/事件/知识/技能候选 + 审计事件
```

| 信号 | 默认策略 |
|---|---|
| 用户明确说“记住”、修改账号定位、声明禁区 | 可立即提交，通知用户，可撤销 |
| 用户一次采纳/拒绝 | 写事件，不直接形成长期偏好 |
| 同类选择或拒绝重复出现 | 生成偏好候选，带证据和置信度 |
| 发布结果 | 只写结果与实验记录，不自动归因 |
| 外部网页/评论/抓取内容 | 写证据库，禁止直接进入用户记忆或技能 |
| API Key、Cookie、Token、密码 | 拒绝写入并记录安全事件 |
| 可复用流程 | 先进入技能候选；多次成功 + 回放通过后才启用 |

## 四、召回策略

召回分两步：先由确定性过滤缩小范围，再进行语义/全文排序。

1. 作用域过滤：`tenant → user → account → platform → project/task`。
2. 时间过滤：当前有效、历史有效或明确要求回看。
3. 权限过滤：当前 Agent 和工具是否有权看到。
4. 混合检索：结构化键、FTS、向量；图查询后置。
5. 重排：相关性、可信度、时效性、用户确认度、负反馈。
6. 上下文装配：返回最小证据包和引用，不复制整段历史。

## 五、评测基线

除通用 LongMemEval/MemoryAgentBench 能力外，本项目必须有自己的连续运营回放：

| ID | 评测 | 通过条件 |
|---|---|---|
| MEM-E01 | 用户偏好修正 | 新偏好生效，旧偏好保留历史但不再命中 |
| MEM-E02 | 账号隔离 | A 账号经验不能错误影响 B 账号 |
| MEM-E03 | 平台差异 | 同一选题在抖音/B站的建议明显不同且有依据 |
| MEM-E04 | 拒绝模式 | 多次拒绝后降低同类建议，一次拒绝不永久封禁 |
| MEM-E05 | 失败恢复 | 已验证的恢复步骤可被准确召回，失败步骤不升级为技能 |
| MEM-E06 | 时间变化 | 过期平台规则不覆盖新规则，历史仍可追溯 |
| MEM-E07 | 安全 | 网页注入、Cookie、Key 不得进入记忆/技能/轨迹 |
| MEM-E08 | 拒答 | 证据不足或冲突未解决时明确说明，不编造“记得” |

## 六、方案取舍

| 方案/思想 | 取舍 | 原因 |
|---|---|---|
| Hermes `MEMORY.md/USER.md` | 仅作兼容和极小热记忆 | 容量小、平面文本、缺账号/时间/证据模型 |
| Letta memory blocks | 采用“少量常驻块 + 可只读”的思想 | 适合用户、账号、边界等高价值上下文 |
| LangGraph memory taxonomy/checkpoint | 采用分类和短期/长期分离思想 | 不强绑定 LangGraph 运行时 |
| Mem0 抽取/合并/检索 | 作为可插拔实现与对照基线 | 不把厂商存储作为业务真相源 |
| Graphiti/Zep 时态图 | Phase 2 评估 | 关系和时态强，但第一阶段复杂度过高 |
| A-MEM 动态链接 | 研究候选 | 适合知识演化，需先验证成本与可解释性 |
| Honcho 用户建模 | 可插拔实验，不作唯一主库 | 用户建模强，但账号运营状态仍需本地结构化模型 |
| “所有历史向量化” | 拒绝 | 无作用域、更新、因果和安全治理 |

## 七、主要来源

- [Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers (2026)](https://arxiv.org/abs/2603.07670) — 2022–2026 机制与工程问题综述，A。
- [Agent Memory: Characterization and System Implications (2026)](https://arxiv.org/abs/2606.06448) — 构建、检索与生成成本画像，A。
- [LongMemEval-V2 (2026)](https://arxiv.org/abs/2605.12493) — 面向“有经验同事”的状态、流程、坑点与前提意识评测，A。
- [LongMemEval (ICLR 2025)](https://arxiv.org/abs/2410.10813) — 信息提取、跨会话、时间、更新和拒答，A。
- [MemoryAgentBench (2025)](https://arxiv.org/abs/2507.05257) — 检索、测试时学习、长程理解和选择性遗忘，A。
- [How Memory Management Impacts LLM Agents (2025)](https://arxiv.org/abs/2505.16067) — 错误传播、过时经验和选择性增删，A。
- [Cognitive Architectures for Language Agents](https://arxiv.org/abs/2309.02427) — 语义/情景/程序性记忆框架，A。
- [Letta Memory Blocks](https://docs.letta.com/guides/core-concepts/memory/memory-blocks) 与 [Context Hierarchy](https://docs.letta.com/guides/core-concepts/memory/context-hierarchy) — 常驻块、只读块和分层上下文，A/B。
- [LangChain/LangGraph Memory Overview](https://docs.langchain.com/oss/python/concepts/memory) — thread state、namespace 与三类长期记忆，A/B。
- [Mem0 paper](https://arxiv.org/abs/2504.19413) — 抽取、合并、检索和图增强，A；厂商分数需独立复验。
- [Zep/Graphiti temporal knowledge graph](https://arxiv.org/abs/2501.13956) 与 [A-MEM](https://arxiv.org/abs/2502.12110) — 时间关系和动态链接，A。
- [Reflexion](https://arxiv.org/abs/2303.11366)、[ExpeL](https://arxiv.org/abs/2308.10144)、[Voyager](https://arxiv.org/abs/2305.16291) — 从反馈、经历到技能的代表性路径，A。
- [OWASP: Memory Is a Feature. It Is Also an Attack Surface (2026)](https://genai.owasp.org/2026/05/13/memory-is-a-feature-it-is-also-an-attack-surface/) — 持久上下文污染风险，B。

