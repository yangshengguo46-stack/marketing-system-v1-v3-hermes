# Agent Core 资料库

> 建立日期：2026-06-29  
> 研究范围：长期 Agent memory、harness、持久任务、技能沉淀、自我学习、安全与评测。

这里不是链接收藏夹，而是本项目重建 Agent Core 的证据库。每项结论必须能落到架构选择、台账条目或验收测试。

## 文档索引

| 文档 | 作用 |
|---|---|
| `01-agent-memory-frontier-2026.md` | 记忆前沿、系统分层、写入/召回/遗忘与评测方案 |
| `02-agent-harness-frontier-2026.md` | Agent 执行循环、持久任务、审批、权限、上下文与可观测性 |
| `03-hermes-source-audit.md` | 新下载 Hermes 源码的能力盘点和采用/改造/替换决策 |
| `04-ledger-gap-matrix.md` | 研究结论与 `AGENT_CORE_LEDGER.md` 的逐项映射 |
| `05-open-source-capability-landscape-2026.md` | 浏览器、短视频、营销、记忆、长任务、发布、评测和视频能力的开源候选与采用边界 |
| `07-volcano-video-production-research.md` | 火山引擎视频生成能力调研：小云雀/火山剧创/ArkClaw 架构、Seedance/Seedream API、架构方案讨论 |
| `08-data-flywheel-strategy.md` | 数据飞轮策略：系统推向市场后的数据复用路径、内容生产闭环、数据结构与推进顺序 |
| `09-video-ecosystem-research.md` | 视频生态调研：MoneyPrinterTurbo、素材搜索 MCP、音效放置方案、LibTV 技术路径 |
| `10-creator-data-collection-research.md` | 创作者中心账号数据采集候选、风险与事故复盘 |
| `11-social-account-lifecycle-and-open-source.md` | 起号到持续经营的完整生命周期、官方数据边界、开源方案和底层改造结论 |
| `12-influence-attention-model.md` | 影响力与注意力建模路线图：数据来源、特征工程、预演公式、独家算法演进路径 |
| `../ledgers/README.md` | 冻结总台账之后，各子板块唯一可更新的执行台账索引 |
| `../architecture/REBUILD_BASELINE.md` | 新架构的可执行基线与首轮实施顺序 |

## 证据等级

1. `A`：官方源码、官方技术文档、同行评审论文或作者原始论文。
2. `B`：官方工程博客、正式基准说明、可复现实验仓库。
3. `C`：厂商宣传数据或二手总结，只能作为候选线索，不能单独决定架构。

## 采用规则

- 论文中的 benchmark 分数不直接等于产品收益；必须通过我们的账号运营场景回放。
- 不因某个框架有“memory”功能就把它当业务记忆系统。
- 供应商实现可替换；用户事实、账号 DNA、实验、发布结果和技能版本必须掌握在本地数据模型中。
- 任何自动学习都必须保留来源、时间、适用范围、置信度、修订关系和撤销路径。
- 原始 Cookie、密码、Token、API Key 永不进入记忆、向量索引、轨迹或技能。
