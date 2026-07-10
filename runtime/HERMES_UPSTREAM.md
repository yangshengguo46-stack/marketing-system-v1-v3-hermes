# Hermes upstream boundary

- Repository: `https://github.com/NousResearch/hermes-agent.git`
- Baseline: `4488fe134b1de4359f3a4f1f8368576413e6e268`
- Baseline date: 2026-06-28
- Local checkout: `runtime/hermes-agent`
- Adaptation branch: `codex/marketing-os-runtime`
- Product tree: `39acd04e2b7d84424ac381c0f77c647127744e24`
- Reproducible lock: `runtime/hermes-runtime.lock.json`
- Patch series: `runtime/hermes-patches/*.patch`

Product domain truth stays in `engine/agent_core`, but the Hermes fork is an actively maintained part of this product, not a frozen dependency. Patch it whenever the fork-level change materially improves continuity, initiative, context use, recovery or interaction quality and cannot be implemented more cleanly at the product boundary.

## 2026-06-29 decision（历史）

当时不需要 fork patch；上游 `AIAgent` callbacks、`SessionDB`、`interrupt()` 和 tool registry 足够完成最初 P0。该判断只描述当时，不再代表当前 fork 状态。

## 2026-07-02 decision (user-authorized)

Direct modification of the Hermes fork is now permitted. Rules:

- Choose the layer that produces the cleanest user experience and the least duplicated state. Adapter/gateway is preferred for product semantics; patch the fork for runtime behavior such as planning, context, interruption, recovery, initiative, tool-loop UX or event streaming.
- Every patch must be minimal, carry a regression test, and be listed in the patch registry below.
- Business truth stays in `engine/agent_core`; Hermes may understand product-neutral lifecycle and interaction contracts, but does not own account facts or marketing records.
- Upstream upgrades follow RUN-16: replay patches on the new baseline, run contract tests, keep rollback possible.

### Patch registry

这里仅登记 `runtime/hermes-agent` 内的真实 fork patch；`engine/agent_core` 的产品 adapter 变更不再混入本表。

| # | Date | Patch | Invariant | Regression test |
|---|---|---|---|---|
| 1 | 2026-07-10 | `0001-feat-gateway-route-mobile-messages-to-Marketing-OS-a.patch` | 飞书/微信只是同一个 Marketing OS Agent 的 communication surface；入站消息转入本机 Agent session/task，不再落回 Hermes 默认 persona；Feishu SOCKS 依赖随 extra 声明 | `tests/test_mobile_bridge.py`、`tests/test_channels.py` |

## Reproduction contract

`runtime/hermes-agent` 继续作为被外层 Git 忽略的嵌套 checkout，但不再是隐藏事实源：

1. `runtime/hermes-runtime.lock.json` 锁定上游 URL、baseline commit、产品 tree 和每个 patch 的 SHA-256。
2. `scripts/bootstrap-hermes-runtime.sh` 在 checkout 缺失时 clone baseline，再按顺序 `git am` 产品补丁；发现本地 dirty 或未知 revision 时 hard fail，不覆盖用户工作。
3. `scripts/verify-hermes-runtime.py` 在测试和 release build 前验证 patch checksum、nested clean 和 product tree。
4. `tests/test_hermes_runtime_reproducibility.py` 从 baseline 在临时目录重放 patch，证明可以重建相同 tree。

2026-07-10 清理：移除了未接入执行链、无来源/许可证说明且写死平台发布时间和算法权重的泛化 content/screenwriting/video skill 草稿。领域知识必须进入可追溯资料库或受治理技能候选，不能因为文件存在就算已学会。
