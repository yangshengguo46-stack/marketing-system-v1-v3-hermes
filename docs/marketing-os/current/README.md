# 当前产品文档

> **执行前必须确认：** 默认先改原生 owner；禁止因为怕碰上游，就在外围再加适配层。只有上游确实无法承担、且证据充分时，才允许新增边界。Electron 只负责显示和交互，不参与其它任何东西。

只按以下顺序阅读：

1. `PRODUCT_PHILOSOPHY.md`：产品为什么存在，以及不能妥协什么。
2. `NATIVE_ARCHITECTURE.md`：哲学如何成为 Hermes 本体的一部分。
3. `EXECUTION_LEDGER.md`：当前唯一任务和完成证据。

冲突裁决顺序：产品哲学 → 当前代码/测试事实 → 原生架构 → 执行台账。Research、Reference、Deferred 和 Git 历史不能覆盖这四份当前文档。
