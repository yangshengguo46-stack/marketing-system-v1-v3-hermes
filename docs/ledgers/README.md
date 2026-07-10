# 产品台账索引

> 2026-07-10 重塑：[`00-current-product-status.md`](./00-current-product-status.md) 是唯一实时执行入口。

`LEDGER.md` 和 `AGENT_CORE_LEDGER.md` 保留第一版产品宪法和历史判断；编号子台账保留领域设计、测试证据与事故记录。任何旧文件中的“当前入口”“下一领取任务”“完成百分比”如果与 00 总控冲突，以 00 总控和当前代码为准。

当前执行原则：先完成可复现 runtime 和一条真实内容经营闭环，再扩平台、视频和未来学习能力。

## 执行纪律

1. 一次只执行 00 总控中的一个 R-ID；完成后附代码路径、自动化证据、开发机证据、打包证据和真人证据。
2. 不以新增字段、页面、Fake、单测数量或本地占位执行器冒充产品完成。
3. 先核验开源方案；采用前记录版本/commit、许可证、数据流、秘密、失败回退和卸载路径。
4. 不恢复已删除的旧插件、外部 Chrome/CDP、后端 Cookie、CLI 单轮 Agent 或运行时自动安装。
5. （2026-07-10 用户纠偏）Marketing OS 是 Hermes 的产品 fork；UI、Agent loop、SessionDB、tools、gateway、cron、memory、skills、plugins 等源码均可深度改造。禁止为保持上游纯净而另造 adapter/bridge/sidecar 主链；改动仍须附回归测试、数据迁移和安全审计。
6. Hermes 上游代码与 Marketing OS 既有代码都只是可拆解的材料，不是不可变边界。迁移按能力域重新组合，不按旧目录照搬；保留的是全周期经营、证据驱动、长期学习和真实回执闭环的设计哲学。
7. 结构重塑必须服务同一纵向闭环；禁止另造第二套 Agent、数据库、浏览器身份或发布真相源。
8. 统一使用 `designed / code / automated / dev-runtime / packaged / human-loop` 六级证据。

## 当前入口与历史台账

| 顺序 | 文档 | 作用 | 执行地位 |
|---:|---|---|---|
| 0 | `00-current-product-status.md` | 当前产品事实、第一版对照、重塑顺序 | 唯一实时入口 |
| H0 | `00-gap-overview.md` | 2026-07-02 差距快照 | historical |
| 1 | `01-mcp-browser-account.md` | MCP 浏览器、登录、多账号隔离 | domain evidence |
| 2 | `02-data-trends-research.md` | 公共热点、登录态采集、行业研究与证据 | domain evidence |
| 3 | `03-agent-runtime-tasks.md` | Hermes、计划、长任务、审批与恢复 | domain evidence |
| 4 | `04-memory-learning-knowledge.md` | 记忆、账号 DNA、知识、实验、技能 | domain evidence |
| 5 | `05-content-publishing-feedback.md` | 内容资产、发布、指标、复盘 | domain evidence |
| 6 | `06-desktop-security-delivery.md` | Electron、安全、打包、升级、可观测 | domain evidence |
| 7 | `07-surfaces-web-video-channels.md` | Web 视频、微信/飞书等 surface | deferred evidence |
| 8 | `08-video-generation-volcano.md` | 独立高阶视频项目 | feature-gated evidence |
| H9 | `09-main-architecture-closure.md` | 2026-07-03 架构收口快照 | historical |
| 10 | `10-account-lifecycle.md` | 起号、受众、对标、定位、实验与持续经营闭环 | domain evidence |
| H11 | `11-stable-product-delivery.md` | 旧稳定交付总线 | historical |
| H12 | `12-product-closure-control.md` | 2026-07-07 收口过程与事故记录 | historical |
| H13 | `13-workspace-hygiene-reshape.md` | 2026-07-08 工作区清理记录 | historical |
| 14 | `14-content-production-factory.md` | 内容生产共享能力池和三种 lane | domain evidence |
| 15 | `15-influence-preflight-engine.md` | 预演、回执、记忆三核研究与落地日志 | domain evidence；未校准预测不得对外承诺 |

## 执行提示

```text
只执行 docs/ledgers/00-current-product-status.md 中的一个 R-ID。
先读该总控、LEDGER.md、AGENT_CORE_LEDGER.md 和 docs/architecture/REBUILD_BASELINE.md；
再按需要读取对应领域台账，不从旧台账领取“当前任务”。
不得修改两个冻结总台账，不得扩大任务范围，不得把测试或占位实现标记为真人完成。
先给出当前代码证据和纵向闭环影响，再实现；结束时回填代码路径、自动化、开发机、
打包、真人证据和未完成风险。不得以单测数量、mock、占位 provider 或页面展示冒充用户可用。
```
