# Marketing OS 文档入口

> **所有执行入口的强制前提：** 默认先改原生 owner；禁止因为怕碰上游，就在外围再加适配层。只有上游确实无法承担、且证据充分时，才允许新增边界。Electron 只负责显示和交互，不参与其它任何东西。

## 当前产品

执行工作只允许从 [`current/`](./current/) 开始：

1. [产品哲学](./current/PRODUCT_PHILOSOPHY.md)
2. [Hermes 原生架构](./current/NATIVE_ARCHITECTURE.md)
3. [Durable Multi-Agent Harness 架构](./current/HARNESS_ARCHITECTURE.md)
4. [当前执行台账](./current/EXECUTION_LEDGER.md)

## 其它区域

- [`research/`](./research/)：论文、开源方案、平台和产品研究，只提供证据。
- [`reference/`](./reference/)：仍有效的工程审计与 ADR，只帮助实现当前任务。
- [`verification/`](./verification/)：必须由真人执行的验收清单。
- [`security/`](./security/)：安全与供应链要求。
- [`sbom/`](./sbom/)：生成的依赖和许可证清单。
- [`deferred/`](./deferred/)：明确暂停、不能进入当前桌面主线的项目；包括可追溯但未进入执行顺序的[高级视频方案](./deferred/high-end-video-volcengine.md)。

旧总台账、Claude/GLM 任务、套壳架构、FastAPI/AgentCoreStore 路线和阶段事故日志已从工作树删除。需要追溯时使用 Git 历史，不得把历史文件恢复为任务入口。

裁决顺序：产品哲学 → 当前代码和验证事实 → 原生架构 → Harness 架构 → 当前执行台账 → ADR/Research。
