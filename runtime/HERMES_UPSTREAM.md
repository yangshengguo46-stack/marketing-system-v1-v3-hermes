# Hermes upstream boundary

- Repository: `https://github.com/NousResearch/hermes-agent.git`
- Baseline: `4488fe134b1de4359f3a4f1f8368576413e6e268`
- Baseline date: 2026-06-28
- Local checkout: `runtime/hermes-agent`
- Adaptation branch: `codex/marketing-os-runtime`

Product domain truth stays in `engine/agent_core`, but the Hermes fork is an actively maintained part of this product, not a frozen dependency. Patch it whenever the fork-level change materially improves continuity, initiative, context use, recovery or interaction quality and cannot be implemented more cleanly at the product boundary.

## 2026-06-29 decision

No fork patch is currently required. The upstream `AIAgent` callbacks, `SessionDB`, `interrupt()` and tool registry/toolset extension points are sufficient for the current persistent-session and read-only P0 foundation. Product code uses those extension points directly; any future fork patch must name the missing invariant and include a regression test.

## 2026-07-02 decision (user-authorized)

Direct modification of the Hermes fork is now permitted. Rules:

- Choose the layer that produces the cleanest user experience and the least duplicated state. Adapter/gateway is preferred for product semantics; patch the fork for runtime behavior such as planning, context, interruption, recovery, initiative, tool-loop UX or event streaming.
- Every patch must be minimal, carry a regression test, and be listed in the patch registry below.
- Business truth stays in `engine/agent_core`; Hermes may understand product-neutral lifecycle and interaction contracts, but does not own account facts or marketing records.
- Upstream upgrades follow RUN-16: replay patches on the new baseline, run contract tests, keep rollback possible.

### Patch registry

| # | Date | Files | Invariant | Regression test |
|---|---|---|---|---|
| 1 | 2026-07-02 | `engine/agent_core/plan_protocol.py` (new), `engine/agent_core/tool_manifest.py`, `engine/agent_core/policy.py`, `engine/agent_core/hermes_adapter.py` | RUN-01: structured plan protocol — model declares plan via `marketing_plan_declare` tool; deterministic step↔tool binding replaces prose parsing | `tests/test_plan_protocol.py` (21 tests), `tests/test_agent_core.py` (tool count + policy updates) |
| 2 | 2026-07-02 | `engine/agent_core/plan_protocol.py`, `engine/agent_core/hermes_adapter.py` | RUN-02: failure-aware checkpoint — `fail_step_on_tool_error` marks failed steps; `_build_checkpoint` includes `failed_steps` + `last_tool_ref`; `on_tool_complete` handles error/blocked/invalid statuses; resume treats failed as retryable | `tests/test_plan_protocol.py` (6 RUN-02 tests) |
| 3 | 2026-07-02 | `tests/test_plan_checkpoint.py` | RUN-04: cross-process recovery — 4 tests for checkpoint survival across reopen, failed-step retryability, effect replay guard, and full crash recovery cycle | `tests/test_plan_checkpoint.py` (`TestCrossProcessRecoveryRUN04`, 4 tests) |
| 4 | 2026-07-02 | `tests/test_run_12_13_14.py` (new) | RUN-12/13/14: scope isolation (5 tests), manifest snapshot (10 tests), observable timeline (4 tests) — frozen tool name set, dual-project/account/user isolation, full event correlation with secret redaction | `tests/test_run_12_13_14.py` (19 tests) |
