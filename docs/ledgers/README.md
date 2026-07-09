# 子板块执行台账索引

> 基线冻结：2026-07-01。

`LEDGER.md` 和 `AGENT_CORE_LEDGER.md` 从本基线起是产品目标、架构边界和完成口径的冻结总台账。后续不再追加逐日流水、随意修改完成度或重写历史；实际执行只更新本目录对应子台账。只有用户明确改变产品目标或要求重新定版，才能建立新的总台账基线。

> 2026-07-07 接管修订：项目进入产品收口期，执行入口改为 `12-product-closure-control.md`。GLM/Claude 既有产物不再作为边界，按代码证据、台账纪律和最终体验统一裁剪。

## 执行纪律

1. 一次只领取一个明确 Task ID；开始前写 `in_progress`，完成后附代码路径、自动化证据和真人验收状态。
2. 不以新增字段、页面、Fake、单测数量或本地占位执行器冒充产品完成。
3. 先核验开源方案；采用前记录版本/commit、许可证、数据流、秘密、失败回退和卸载路径。
4. 不恢复已删除的旧插件、外部 Chrome/CDP、后端 Cookie、CLI 单轮 Agent 或运行时自动安装。
5. （2026-07-02 用户修订）允许直接修改 Hermes fork 源码；仍优先 adapter/gateway，确需 patch 时改动最小化、附回归测试并登记 `runtime/HERMES_UPSTREAM.md`；约束详见 `00-gap-overview.md` 第四节。
6. 不跨模块顺手重构。发现关联问题只在相应台账新增阻断证据，等待复核后再排期。
7. `code done`、`automated verified`、`human verified` 三种证据分开记录。

## 子台账

| 顺序 | 文档 | 模块 | 当前入口任务 |
|---:|---|---|---|
| 0 | `00-gap-overview.md` | 差距总览与补齐路线（2026-07-02） | — |
| 1 | `01-mcp-browser-account.md` | MCP 浏览器、登录、多账号隔离 | MCP-01 |
| 2 | `02-data-trends-research.md` | 公共热点、登录态采集、行业研究与证据 | DATA-01 |
| 3 | `03-agent-runtime-tasks.md` | Hermes、计划、长任务、审批与恢复 | RUN-01 |
| 4 | `04-memory-learning-knowledge.md` | 记忆、账号 DNA、知识、实验、技能 | MEM-01 |
| 5 | `05-content-publishing-feedback.md` | 内容资产、发布、指标、复盘 | PUB-01（需 RUN/MCP 前置） |
| 6 | `06-desktop-security-delivery.md` | Electron、安全、打包、升级、可观测 | DESK-01 |
| 7 | `07-surfaces-web-video-channels.md` | Web 视频、微信/飞书等 surface | SURF-01（后置） |
| 8 | `08-video-generation-volcano.md` | 视频生产引擎（营销系统补充 + 可独立售卖，不计入桌面主架构完工） | VIDEO-02（ADR v2 已定版） |
| 9 | `09-main-architecture-closure.md` | 桌面智能体主架构收口（2026-07-03） | ARCH-01 |
| 10 | `10-account-lifecycle.md` | 起号、受众、对标、定位、实验与持续经营闭环 | LIFE-01 |
| 11 | `11-stable-product-delivery.md` | 主架构冻结后的稳定产品交付总线 | DELIV-02 |
| 12 | `12-product-closure-control.md` | 产品收口总控：唯一体验主线、禁止扩项和真人闭环顺序 | CLOSE-01 |
| 13 | `13-workspace-hygiene-reshape.md` | 工作区清理、模块边界重塑、保留/隔离/删除口径 | HYGIENE-02 |
| 14 | `14-content-production-factory.md` | 内容生产端：共享能力池 + 软文、不露脸素材视频、真人/数字人高质量视频三种交付形态 | CPF-08F |
| 15 | `15-influence-preflight-engine.md` | 影响力预演引擎：社会注意力建模、数据闭环、InfluenceOS Score 与 Preflight 决策 | CORE-LOOP-09 / IPE-09 |

## 外部模型/执行代理领取任务的固定提示

```text
优先执行 docs/ledgers/12-product-closure-control.md 中的一个 CLOSE-ID；
如确需落到子台账，只执行 docs/ledgers/<对应文件> 中的一个 Task ID。先读取 LEDGER.md、
AGENT_CORE_LEDGER.md、docs/architecture/REBUILD_BASELINE.md、
docs/research/05-open-source-capability-landscape-2026.md 和该子台账。
不得修改两个冻结总台账，不得扩大任务范围，不得把测试或占位实现标记为真人完成。
先给出当前代码证据和最小变更计划，再实现；结束时运行任务指定验证，回填代码路径、
测试结果、未完成风险和是否需要真人验收。遇到架构冲突立即停止并记录，不自行另造主链。
```
