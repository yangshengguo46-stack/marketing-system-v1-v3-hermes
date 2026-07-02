# Hermes upstream boundary

- Repository: `https://github.com/NousResearch/hermes-agent.git`
- Baseline: `4488fe134b1de4359f3a4f1f8368576413e6e268`
- Baseline date: 2026-06-28
- Local checkout: `runtime/hermes-agent`
- Adaptation branch: `codex/marketing-os-runtime`

Keep product-owned code in `engine/agent_core`, `engine/marketing-os`, Electron, and React. Patch the Hermes fork only when an adapter cannot enforce a required runtime or security invariant.

## 2026-06-29 decision

No fork patch is currently required. The upstream `AIAgent` callbacks, `SessionDB`, `interrupt()` and tool registry/toolset extension points are sufficient for the current persistent-session and read-only P0 foundation. Product code uses those extension points directly; any future fork patch must name the missing invariant and include a regression test.

## 2026-07-02 decision (user-authorized)

Direct modification of the Hermes fork is now permitted. Rules:

- Adapter/gateway remains the first choice; patch the fork only for runtime invariants an adapter cannot enforce (e.g. deterministic plan/step checkpoints, structured plan events for RUN-01/02/04).
- Every patch must be minimal, carry a regression test, and be listed in the patch registry below.
- Business logic stays in `engine/agent_core`; the fork carries no product data or marketing semantics.
- Upstream upgrades follow RUN-16: replay patches on the new baseline, run contract tests, keep rollback possible.

### Patch registry

| # | Date | Files | Invariant | Regression test |
|---|---|---|---|---|
| (none yet) | | | | |
