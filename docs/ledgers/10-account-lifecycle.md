# 账号起号与全生命周期执行台账

> 建立：2026-07-03。执行依据：`docs/research/11-social-account-lifecycle-and-open-source.md` 与 `docs/architecture/account-lifecycle-architecture.md`。

## 目标

把现有账号、受众、对标、定位、内容、发布、指标和记忆模块串成可跨天运行、可解释、可修订的经营闭环。禁止用新页面或画像文案冒充完成。

## v0.1 收口冻结线（2026-07-04）

从本节建立起停止扩能力面，不再新增平台、开源组件、独立页面或业务模块。v0.1 只剩：

1. LIFE-10：安全自动续跑与生命周期 next action；
2. LIFE-11：复用现有 AgentPanel 做最小引导和状态展示，不建独立“起号工作台”；
3. LIFE-12：旧库迁移、跨重启/跨账号/断网自动化与真人 smoke。

以下明确延期，不阻塞桌面主架构代码收口：抖音 `fans.data` OAuth adapter、真实评论入口、专用 evidence drawer、accepted strategy 的自动权重应用、更多平台、独立视频 Web 项目、签名与公证。完成 LIFE-10~12 后只修验收 bug，不再继续扩功能。

## 执行顺序

| ID | 任务 | 最小交付 | 验收 | 状态 |
|---|---|---|---|---|
| LIFE-01 | 生命周期领域模型 | migration、repository、`AccountLifecycleService`、stage/next_action；扩展 benchmark scope | ✅ code + automated verified（2026-07-03）：schema v12；`engine/agent_core/account_lifecycle.py`；单账号单 active project、user/account/project 三重 scope、受众草案/确认/版本保留、确定性 stage/next_action；旧 benchmark 新增归属字段并保留历史数据。定向 29 项、全量 1090 项、TypeScript、Electron syntax、PyInstaller、Vite、MCP runtime 和完整桌面构建通过；尚无 UI/Agent tool/真人流程，后续属于 LIFE-02+ | ✅ |
| LIFE-02 | 目标受众假设 | 草案/确认/修订 API 与 Agent tool；需求、场景、反画像、数据缺口 | ✅ code + automated verified（2026-07-03）：新增生命周期读取、受众草案、受众确认 3 个 Agent tools；新增本地生命周期/草案/确认 API；首次草案可建立经营项目，后续草案形成新版本，未确认草案不推进阶段；新号读取无写入副作用。Hermes 产品计划识别起号/定位/目标受众并先读生命周期，桌面对话强制绑定账号。定向 156 项、全量 1092 项、TypeScript、Electron syntax、diff check 通过；真人对话体验待验收 | 🟡 |
| LIFE-03 | 对标工作流 | 候选→选择→样本→观察→空位分析；绑定 project/account | ✅ code + automated verified（2026-07-03）：schema v15；候选/选中/拒绝状态、direct/adjacent/aspirational/negative 关系、具体内容样本、结构化观察与 gap 维度；样本和观察强制 provenance，未选候选不能成为证据。2026-07-03 复核 Cheat on Content 后加入 readiness gate：至少 2 个选中对标、每个至少 5 条样本、覆盖 audience/positioning/content_pillar/format/engagement，并至少有一个 negative 对标，全部满足才推进 `benchmark_evidence_ready`。新增读取、添加、选择、样本、观察 Agent/API 能力；user/account/project 三重隔离。readiness 定向 133 项、全量 1096 项、TypeScript、Electron syntax、diff check 通过；真人对标研究体验待验收 | 🟡 |
| LIFE-04 | 定位与 DNA 版本 | positioning draft/approve/rollback；投影到旧 DNA 读取接口 | ✅ code + automated verified（2026-07-03）：定位草案强制 `benchmark_readiness.ready`、已确认受众假设和本账号 observation IDs；promise/differentiation/persona/content_pillars/tone/taboos 结构化；批准后旧版 superseded，回滚创建新版本而非覆盖；输出兼容 `ACCOUNT_DNA_FIELDS` 的只读投影。新增定位读取/草案/批准/回滚 Agent/API 能力，Hermes 计划先读生命周期、对标证据和现有定位。定向 162 项、全量 1098 项、TypeScript、Electron syntax、diff check 通过；尚待真人对话确认和旧内容生成链的产品级验收 | 🟡 |
| LIFE-05 | 真实受众快照 | 标准 snapshot adapter；优先抖音官方 `fans.data`，MCP 为补充 | 🟡 标准快照真相层 + API + Agent read 已完成（2026-07-03）：只接受 `official_api` / `creator_center_mcp`，保存 platform/window/captured_at/source_ref/data_gaps 时间序列；gender/age/region/active_days/interests/device/growth 白名单，模型推断、公开网页和无官方依据的 occupation/income 写入硬拒绝。Hermes 对真实受众请求先读快照并区分目标假设/评论推断。定向 165 项、全量 1101 项、TypeScript、Electron syntax、diff check 通过。未完成：抖音 OAuth `fans.data` 真实 adapter、MCP 页面字段 adapter 和真人数据验收 | 🟡 |
| LIFE-06 | 推断安全降级 | 将 comment persona 改为 inference candidate；不长期保存代表评论正文 | ✅ code + automated verified（2026-07-03）：`audience_persona.py` 输出改为 pending `audience_inference_candidate`；删除 representative comments 的聚类保留和序列化，长期结果仅含聚合关键词/样本量；明确 comment sample 偏差、规则推断和不得覆盖真实快照/目标受众；旧 `personas_to_dna` 仅为兼容别名且返回受治理推断候选。真实快照层拒绝 model inference。定向 58 项、全量 1101 项、TypeScript、Electron syntax、diff check 通过；尚未接真实评论采集源，不以无数据链冒充闭环 | ✅ |
| LIFE-07 | 内容实验贯通 | experiment_id 串联选题、资产、评分、预测、发布、结果、复盘 | ✅ code + automated verified（2026-07-03）：schema v16，content asset 增加 experiment_id；实验强制已批准定位、可证伪 hypothesis、单一 variable、发布前 prediction、success criteria；资产绑定严格 user/account/project scope 且不可跨实验。timeline 回放资产、评分、不可变盲预测、真实发布 receipt、指标和 retro；指标回收自动推进 `review_due`，但不自动宣布归因或成功。新增实验读取/创建/绑定 Agent/API，Hermes 识别实验请求并要求账号上下文。定向 171 项 + 自动 review_due 37 项、全量 1103 项、TypeScript、Electron syntax、diff check 通过；真人发布闭环仍依赖平台验收 | 🟡 |
| LIFE-08 | 目标—实际—对标差距 | gap service + Agent tool + UI evidence drawer | 🟡 gap service + API + Agent tool 已完成（2026-07-03）：比较已确认 target hypothesis、最新 first-party snapshot、benchmark audience observations；只对两边都有结构化分布的维度判断 aligned/partial_overlap/mismatch_candidate，任一侧缺失即 unknown；结果保留 benchmark observation IDs，并明确 mismatch 不是事实、只可转为实验候选，绝不自动改定位/DNA。Hermes 识别受众差距请求并要求账号上下文。定向 169 项、全量 1105 项、TypeScript、Electron syntax、diff check 通过。未完成：前端 evidence drawer、从 gap 一键起草实验和真人体验验收 | 🟡 |
| LIFE-09 | 策略修订闭环 | strategy candidate、用户确认、权重更新、回滚 | 🟡 candidate + decision 主链完成（2026-07-04）：schema v17；experiment retro 自动生成 pending candidate，保留 publishing/prediction/memory evidence refs；audience_gap/user_feedback/failure_recovery 也可提议。Agent/API 可读取、提议、接受/拒绝；拒绝强制填写原因且决定不可静默反转；接受仍不能绕过 positioning version 审批或直接改权重。定向 174 项、全量 1106 项、TypeScript、Electron syntax、diff check 通过。未完成：accepted candidate 转定位草案/实验/权重变更的类型化 apply、拒绝偏好投影到长期学习、真人确认 UI | 🟡 |
| LIFE-10 | Agent 主动经营 | 生命周期 next_action 接入长期任务、定时复盘、异常恢复 | 🟡 safe auto-resume code done（2026-07-04）：Hermes 启动时将进程中断任务持久化为 paused；Python scheduler 每轮最多自动恢复一个带 `runtime_interrupted_at` 的任务，并写 attempt checkpoint 防重复。用户主动暂停、待审批、pending/unknown effect、已有运行线程或模型未配置时一律不自动恢复；resume 继续复用 plan/checkpoint/effect replay guard。安全门 + scheduler 定向测试通过；生命周期 next_action 已进入现有 AgentPanel。真人杀进程恢复待 LIFE-12 验收 | 🟡 |
| LIFE-11 | 现有 AgentPanel 最小引导 | 不建新工作台；在现有对话中展示 lifecycle stage、缺口与下一步 | 🟡 code + build verified（2026-07-04）：账号选择后读取 lifecycle API，在现有侧栏显示阶段、下一步、证据缺口和“让 Agent 继续”。真人验收修订：起号/定位/兴趣/变现探索不再要求登录账号；零账号或多账号未选择时使用稳定 `prospect_<user>` 待绑定项目，自然对话每轮只问 1~2 个关键问题；只有粉丝/播放/发布结果等一方事实要求已连接账号。前端和后端双重门槛已同步。TypeScript、Vite、Electron syntax、相关 109 项测试通过；待真人从普通人探索走到方向假设 | 🟡 |
| LIFE-12 | 端到端与升级 | 旧 YAML/benchmark/stats 迁移、干净机和升级机验收 | 🟡 automated/code closure（2026-07-04）：真实用户库 v11→v17，迁移前备份存在，`integrity_check=ok`，6 张生命周期主表齐全；全量 1107 项、TypeScript、Electron syntax、diff check、PyInstaller、Vite、MCP runtime、macOS zip/DMG 完整构建通过。自动恢复安全门覆盖用户暂停、待审批、未决 effect 和防重复。未完成仅剩真人 smoke：空账号起号对话、杀进程续跑、双账号隔离、断网降级；签名/公证属于交付，不阻塞主架构代码收口 | 🟡 |
| LIFE-13 | 待绑定项目接入真实账号 | prospect 项目整体迁移；冲突保护、幂等重试、Agent/桌面自然入口 | ✅ code/build verified（2026-07-04）：生命周期主表、对标和实验关联内容在单事务内迁移；目标账号已有 active 项目时拒绝覆盖；以 project_id 支持安全重试。新增 Agent 工具、REST API、Electron allowlist 和桌面“继续沿用”提示。定向 154 项、全量 1117 项、TypeScript、Electron syntax、完整桌面构建通过；真人点击→Agent 执行→切换账号待验收 | 🟡 |
| LIFE-14 | 对标自动发现 | 真实作者证据→候选排序→样本入库→用户选择；拒绝不复活 | 🟡 B站主链 code/live/build verified（2026-07-04）：公共关键词搜索保留作者与作品 provenance，真实 `AI 教育` smoke 得到 20 条作品/5 个候选；候选可存样本但不可形成定位观察，重复发现幂等，rejected 候选被抑制。新增 Agent/API 能力。定向 160 项、全量 1123 项和完整构建通过。抖音作者发现仍缺稳定来源，不使用创作者热点标题或验证码 DOM 冒充完成 |

## LIFE-01 固定领取提示

```text
只执行 docs/ledgers/10-account-lifecycle.md 的 LIFE-01。
先读 docs/research/11-social-account-lifecycle-and-open-source.md、
docs/architecture/account-lifecycle-architecture.md、engine/agent_core/store.py、
engine/agent_core/migrations.py、engine/agent_core/learning_pipeline.py。

目标是建立 AccountLifecycle 业务真相层，不做新页面、不接平台抓取。本任务无需改 Hermes；若后续体验目标需要，可修改 Hermes fork，但必须登记上游差异并附回归测试。
实现 account_strategy_projects、audience_hypotheses、audience_snapshots、
positioning_versions、account_experiments、strategy_candidates 的最小可扩展 schema，
并让 benchmark_accounts 可绑定 project_id/target_account_id。每个版本化对象禁止覆盖历史；
所有读写严格 user_id + account_id + project_id scope；migration 必须兼容旧数据库。

提供 AccountLifecycleService：create/get project、read status、draft/confirm audience、
计算 stage 和 next_action。不要提前实现 LIFE-02 之后的业务，不要把 JSON metadata 当完整实现。
结束时运行定向测试、全量测试、类型/语法检查和 git diff --check；台账只回填 LIFE-01
的代码路径、测试数字、风险与真人验收状态，不修改冻结总台账和其他任务状态。
```

## 强制边界

1. 官方 API、MCP、公开数据、用户输入、模型推断来源不可混写。
2. memory 不是生命周期真相源；只能消费领域事件生成候选。
3. 定位与受众版本不可原地覆盖；必须可追溯、可回滚。
4. 职业、收入等无来源字段保持未知。
5. 不复制 AGPL 或非商业许可项目代码；开源项目只按资料库结论参考。
6. 自动发布继续遵循现有授权、effect idempotency 和真实 receipt 规则。
