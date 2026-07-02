# Agent Runtime、长任务与审批执行台账

## 完成目标

Hermes 是唯一推理 Runtime；产品 AgentTask 是任务真相源。计划、工具调用、审批、effect、重启恢复和取消均为确定性状态，不靠模型文本猜测。

## 任务清单

| ID | 任务 | 具体执行 | 完成证据 | 状态 |
|---|---|---|---|---|
| RUN-01 | 结构化 Plan 协议 | 定义 plan/version/step/dependencies/status/input/output/effect_key；计划先于执行事件 | schema + UI + 非编号文本测试 | 🟡 地基已有，待统一 |
| RUN-02 | Step checkpoint | 每步开始/完成/失败原子写入；checkpoint 引用 artifact/evidence/effect，不存秘密 | ✅ code done：`on_tool_start` 增加 `update_task_progress(checkpoint=...)` 写入，与 `on_tool_complete` 现有写入互补；步骤开始/完成均原子 checkpoint |
| RUN-03 | Effect 幂等 | intent 在执行前落库；`idempotency_key`、receipt、unknown outcome、补偿策略 | 重启不重复发布/登录/写入 | 🟡 数据地基，真实 effect 待做 |
| RUN-04 | 跨进程恢复 | 杀后端、关窗口、重启 App 后从精确 step 恢复；pending approval 保留 | 真实进程 E2E，不用 Fake worker | ⏳ |
| RUN-05 | 目标修改与重规划 | 保留完成产物和 receipt，废止未执行步骤，创建 plan v2；不重放副作用 | ✅ code done：`replan_task` — 保留 completed steps + checkpoint + emit replanned event + 递增 plan_version；待真人修改目标场景 |
| RUN-06 | 错误分类 | retryable/permanent/auth/approval/network/rate_limit/schema_change/unknown；每类明确策略 | ✅ code done：`ErrorCategory` enum 8 值（含 `retryable`/`default_retry_delay`） + `classify_error()` 22 模式匹配 + `tool_gateway` 接线；12 测试通过 |
| RUN-07 | Retry policy | 只重试可重试读操作；副作用先查询 receipt；指数退避、上限和用户可见 | ✅ code done：`decide_retry()` 指数退避(上限120s)、副作用守卫(RATE_LIMIT 例外)、max_attempts、`hermes_adapter` 接线；22 测试(12分类+10策略)通过 |
| RUN-08 | 持久审批 | once/session/permanent 绑定 user/platform/account/action/content_type/expiry；过期与取消同事务 | 成功/拒绝/取消/超时真人四路径 | 🟡 自动化已过，真人待做 |
| RUN-09 | 授权管理 | 用户查看、缩窄、撤销；Agent 只能请求不能授予；历史执行可审计 | UI + policy 绕过测试 | 🟡 部分已有 |
| RUN-10 | 暂停/恢复/取消 | 停止 worker、释放 MCP/下载等资源；保留产物；取消 pending intent | 资源泄漏和竞态测试 | 🟡 API/UI 地基 |
| RUN-11 | 后台与托盘 | 窗口隐藏任务继续；托盘显示运行/等待数；系统休眠后恢复 | macOS 真人验收 | ⏳ |
| RUN-12 | Session/context 隔离 | user/workspace/project/account 每轮明确绑定，不把隐藏 context 写 transcript | 双用户/双账号/双项目污染测试 | 🟡 user/account 已测，project 待补 |
| RUN-13 | 工具最小化 | 稳定 `marketing_*` 能力映射多个 backend；禁止模型看原始社区 MCP 全工具 | manifest 快照 + 未登记工具拒绝 | 🟡 Broker 地基 |
| RUN-14 | 可观测事件 | task/step/tool/approval/effect/artifact/evidence 统一关联 ID、延迟、错误和脱敏 | 一次任务完整 timeline | ⏳ |
| RUN-15 | Agent 回归评测 | 建 promptfoo/自有 runner 数据集：寒暄、行业研究、拒答、证据、审批、恢复、注入 | CI 阈值和失败报告 | ⏳ |
| RUN-16 | 上游升级策略 | Hermes 固定 commit；adapter 契约测试；升级先 shadow/eval 后切换 | 可重复构建 + rollback | ⏳ |

