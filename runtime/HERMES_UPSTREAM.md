# Hermes upstream boundary

- Repository: `https://github.com/NousResearch/hermes-agent.git`
- Baseline: `4488fe134b1de4359f3a4f1f8368576413e6e268`
- Baseline date: 2026-06-28
- Local checkout: `runtime/hermes-agent`
- Adaptation branch: `codex/marketing-os-runtime`
- Product tree: `226d83bda3781b91e2b40c5eda493cfca2a8ae0c`
- Reproducible lock: `runtime/hermes-runtime.lock.json`
- Patch series: `runtime/hermes-patches/*.patch`

Hermes fork 是产品唯一 Agent/desktop 主干，不是冻结依赖。重构首先审计 Hermes 原生能力：重叠且更成熟的直接复用；有缺口的在原 owner 内增强或重写；只有确实不存在的营销领域能力才新增。禁止为回避修改 Hermes 而另造 adapter、bridge、sidecar、第二套设置或第二份状态 owner。

## 2026-06-29 decision（历史）

当时不需要 fork patch；上游 `AIAgent` callbacks、`SessionDB`、`interrupt()` 和 tool registry 足够完成最初 P0。该判断只描述当时，不再代表当前 fork 状态。

## 2026-07-02 decision (historical)

Direct modification of the Hermes fork is now permitted. Rules:

- 当时仍倾向把产品语义放在 adapter/gateway。该限制已被 2026-07-10 的 Hermes-native 重建基线覆盖。
- Every patch must be minimal, carry a regression test, and be listed in the patch registry below.
- 账号、内容、证据、发布等领域事实逐段迁入 Hermes 源码树中的原生 domain；每段完成后删除旧 owner，不长期双写。
- Upstream upgrades follow RUN-16: replay patches on the new baseline, run contract tests, keep rollback possible.

### Patch registry

这里仅登记 `runtime/hermes-agent` 内的真实 fork patch；`engine/agent_core` 的产品 adapter 变更不再混入本表。

| # | Date | Patch | Invariant | Regression test |
|---|---|---|---|---|
| 1 | 2026-07-10 | `0001-feat-gateway-route-mobile-messages-to-Marketing-OS-a.patch` | 飞书/微信只是同一个 Marketing OS Agent 的 communication surface；入站消息转入本机 Agent session/task，不再落回 Hermes 默认 persona；Feishu SOCKS 依赖随 extra 声明 | `tests/test_mobile_bridge.py`、`tests/test_channels.py` |
| 13 | 2026-07-10 | `0013-feat-web-add-native-extraction-fallback.patch` | Hermes 原生 `web_extract` 在没有收费 Provider Key 时仍能安全读取公开 HTML；已配置的成熟 Provider 继续优先 | `tests/test_marketing_os_native_web_extract.py` 及 Web tool 回归 |
| 14 | 2026-07-10 | `0014-refactor-desktop-make-Hermes-own-provider-configurat.patch` | Provider Catalog、模型设置和 `/api/env` 保持 Hermes 唯一 owner；旧 Marketing 密钥仓只迁移一次，随后退出 | `legacy-provider-migration.test.cjs`、desktop platform、Hermes env/provider 回归 |
| 15 | 2026-07-10 | `0015-fix-desktop-preserve-original-app-identity.patch` | Hermes-native 桌面继续使用旧 Electron 内部身份和 appId，保住 macOS Keychain safeStorage、浏览器数据和既有系统权限；对外产品名仍为 Marketing OS | `legacy-provider-migration.test.cjs`、desktop platform 回归 |
| 16 | 2026-07-10 | `0016-feat-content-enforce-claim-support-and-revision-hist.patch` | 高风险主张必须同段引用、数量 token 必须能在证据摘要中匹配；文章修订生成不可变版本链，不覆盖旧稿 | `tests/test_marketing_os_content_production.py`、真实 Provider v2→v4 E2E |
| 17 | 2026-07-10 | `0017-fix-web-expose-native-extraction-error-types.patch` | 原生网页抽取即使异常文本为空，也返回可诊断的异常类型，不再只显示空错误 | `tests/test_marketing_os_native_web_extract.py` |
| 18 | 2026-07-11 | `0018-refactor-desktop-make-Marketing-OS-the-only-product-.patch` | Hermes-native `apps/desktop` 是唯一产品壳；macOS/Windows/Linux 包元数据、Windows exe stamp、卸载路径和打包测试统一为 Marketing OS，旧 Hermes 安装名仅作迁移兼容 | `product-identity.test.cjs`、desktop platform、typecheck/lint/build |

## Reproduction contract

`runtime/hermes-agent` 继续作为被外层 Git 忽略的嵌套 checkout，但不再是隐藏事实源：

1. `runtime/hermes-runtime.lock.json` 锁定上游 URL、baseline commit、产品 tree 和每个 patch 的 SHA-256。
2. `scripts/bootstrap-hermes-runtime.sh` 在 checkout 缺失时 clone baseline，再按顺序 `git am` 产品补丁；发现本地 dirty 或未知 revision 时 hard fail，不覆盖用户工作。
3. `scripts/verify-hermes-runtime.py` 在测试和 release build 前验证 patch checksum、nested clean 和 product tree。
4. `tests/test_hermes_runtime_reproducibility.py` 从 baseline 在临时目录重放 patch，证明可以重建相同 tree。

2026-07-10 清理：移除了未接入执行链、无来源/许可证说明且写死平台发布时间和算法权重的泛化 content/screenwriting/video skill 草稿。领域知识必须进入可追溯资料库或受治理技能候选，不能因为文件存在就算已学会。
