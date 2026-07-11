# Agent Runtime、长任务与审批执行台账

## 完成目标

Hermes 是唯一推理 Runtime；产品 AgentTask 是任务真相源。计划、工具调用、审批、effect、重启恢复和取消均为确定性状态，不靠模型文本猜测。

## 任务清单

| ID | 任务 | 具体执行 | 完成证据 | 状态 |
|---|---|---|---|---|
| RUN-01 | 结构化 Plan 协议 | 定义 plan/version/step/dependencies/status/input/output/effect_key；计划先于执行事件 | `plan_protocol.py` (validate/merge/bind/complete) + `marketing_plan_declare` tool + `policy.py` prefix rule + adapter callbacks use deterministic binding; 21 tests in `test_plan_protocol.py` + 63 in `test_agent_core.py` | ✅ code done |
| RUN-02 | Step checkpoint | 每步开始/完成/失败原子写入；checkpoint 引用 artifact/evidence/effect，不存秘密 | ✅ code done：`on_tool_start`/`on_tool_complete` 均原子写 checkpoint；失败步骤标记 `failed` 并写入 `failed_steps`；checkpoint 含 `last_tool_ref`（tool_call_id/tool_name/result_status）；resume 将 failed 步骤列为可重试；store 层已脱敏；6 个 RUN-02 回归测试通过 |
| RUN-03 | Effect 幂等 | intent 在执行前落库；`idempotency_key`、receipt、unknown outcome、补偿策略 | ✅ code done：已有 `create_effect_intent`（UNIQUE idempotency_key 去重）+ `record_effect_receipt`（已执行返回原 receipt 不覆盖）；17 项测试覆盖 intent 落库(pending)、idempotency_key 去重(同 key 返回同 effect)、跨重启去重、receipt 记录+事件、双提交幂等(不覆盖)、unknown outcome(pending 检测+恢复完成)、重启安全(executed 持久化)、审批前置(拒绝审批阻止 effect)、无审批路径、补偿(取消任务作废审批)、DB 级 UNIQUE 约束 |
| RUN-04 | 跨进程恢复 | 杀后端、关窗口、重启 App 后从精确 step 恢复；pending approval 保留 | ✅ 自动化已过：4 个 RUN-04 测试覆盖 checkpoint 存活、failed 步骤可重试、effect 重放守卫、完整崩溃恢复周期；真人 E2E 待做 |
| RUN-05 | 目标修改与重规划 | 保留完成产物和 receipt，废止未执行步骤，创建 plan v2；不重放副作用 | ✅ 真人通过：`replan_task` 中断旧线程→保留 completed steps→pause→resume with new objective；前端执行中可发消息自动路由 replan；2026-07-02 真人验证 AI热点→新能源汽车热点切换成功 |
| RUN-06 | 错误分类 | retryable/permanent/auth/approval/network/rate_limit/schema_change/unknown；每类明确策略 | ✅ code done：`ErrorCategory` enum 8 值（含 `retryable`/`default_retry_delay`） + `classify_error()` 22 模式匹配 + `tool_gateway` 接线；12 测试通过 |
| RUN-07 | Retry policy | 只重试可重试读操作；副作用先查询 receipt；指数退避、上限和用户可见 | ✅ code done：`decide_retry()` 指数退避(上限120s)、副作用守卫(RATE_LIMIT 例外)、max_attempts、`hermes_adapter` 接线；22 测试(12分类+10策略)通过 |
| RUN-08 | 持久审批 | once/session/permanent 绑定 user/platform/account/action/content_type/expiry；过期与取消同事务 | ✅ 真人通过 3/4 路径：成功（批准→执行）、拒绝（拒绝→降级输出）、session授权（批准后同session不再弹）；超时路径自动化已覆盖；2026-07-02 真人验证 |
| RUN-09 | 授权管理 | 用户查看、缩窄、撤销；Agent 只能请求不能授予；历史执行可审计 | UI + policy 绕过测试 | 🟡 部分已有 |
| RUN-10 | 暂停/恢复/取消 | 停止 worker、释放 MCP/下载等资源；保留产物；取消 pending intent | 资源泄漏和竞态测试 | 🟡 API/UI 地基 |
| RUN-11 | 后台与托盘 | 窗口隐藏任务继续；托盘显示运行/等待数；系统休眠后恢复 | macOS 真人验收 | ⏳ |
| RUN-12 | Session/context 隔离 | user/workspace/project/account 每轮明确绑定，不把隐藏 context 写 transcript | ✅ 自动化已过：5 个测试覆盖双项目计划隔离、事件隔离、双账号隔离、双用户隔离、检查点隔离 |
| RUN-13 | 工具最小化 | 稳定 `marketing_*` 能力映射多个 backend；禁止模型看原始社区 MCP 全工具 | ✅ 自动化已过：10 个测试覆盖工具名快照、计数、级别分布、未登记工具拒绝、system_ 拒绝、非 marketing_ 拒绝、schema 校验 |
| RUN-14 | 可观测事件 | task/step/tool/approval/effect/artifact/evidence 统一关联 ID、延迟、错误和脱敏 | ✅ 自动化已过：4 个测试覆盖完整事件 timeline 关联 ID、时间戳存在性、序列顺序、秘密脱敏 |
| RUN-15 | Agent 回归评测 | 建 promptfoo/自有 runner 数据集：寒暄、行业研究、拒答、证据、审批、恢复、注入 | ✅ code done：`tests/eval/regression_dataset.json` — 7 类 18 case 覆盖寒暄(3)/行业研究(3)/拒答(3)/证据(2)/审批(2)/恢复(2)/注入(3)；`tests/eval/run_regression.py` 自有 runner 验证数据集结构完整性、各类别行为契约一致性、注入防护、拒答无工具调用、证据必须含来源；25 项测试通过 |
| RUN-16 | 上游升级策略 | Hermes 固定 commit；adapter 契约测试；升级先 shadow/eval 后切换 | ✅ code done：`scripts/upgrade_strategy.py` — Hermes commit pin 验证（4488fe1）、adapter 契约提取（tool name/level/approval/schema_properties）、契约 diff（检测 added/removed/changed，breaking 判定）、shadow eval 框架（新旧 adapter 并行对比）、`evaluate_upgrade` 综合推荐（proceed/investigate/block）、contract snapshot 持久化；23 项测试覆盖 commit pin、契约稳定性、diff 检测、shadow eval、推荐策略、rollback 路径 |
| RUN-17 | 内容评分协议 | 9 维度评分 rubric（7 正向 + 2 风险）；Agent 发布前对脚本/成片打分 | ✅ workflow wired：`marketing_draft_content_review` 已作为 L1 稳定能力接入 Agent；`learning_pipeline.review_content_asset` 将评分绑定资产版本、账号和 task，风险项参与发布评审；尚未强制拦截发布 |
| RUN-18 | 盲预测机制 | Agent 发布前写预测（预计播放量/完播率/互动率区间）；预测写入后 immutable；发布后 T+3d 对账 | ✅ workflow wired：内容评审可同步写入资产版本级不可变预测；发布成功自动设置 72h 指标回收时间；真实平台指标采集器仍待 PUB-10 |
| RUN-19 | T+3d 复盘对账 | 发布后回收指标；预测 vs 实际对账；偏差记录写入记忆系统 | 🟡 workflow wired：指标写入会自动对账并生成带发布证据、账号 scope 和 classification 的 pending 结果记忆；真实平台指标采集与连续偏差 bump 提示待接 |
| RUN-20 | Rubric 进化协议 | rubric 权重升级：全量重打校准池 + 4/5 一致性检验 + 跨模型独立审核；不通过则拒绝升级 | 🟡 算法底座：校准和一致性检查已有；缺版本化权重存储、独立模型审核接入及用户可撤销流程 |
| RUN-21 | 对标账号 cold-start | 新用户无历史数据时导入对标账号 5-10 条样本；派生初始 rubric anchor；解决飞轮冷启动 | 🟡 数据底座：表、CRUD、anchor 派生已有；缺真实导入入口、来源证据和账号级应用 |
| RUN-22 | 发布节奏警戒 | 按发布频率派生 buffer 阈值；断更预警；拍了未发状态追踪 | 🟡 workflow wired：资产进入 approved 自动增加 buffer，真实发布完成自动减少并记录 last_published_at；`marketing_read_learning_status` 可查询，托盘提醒待接 |
| RUN-23 | 受众画像派生 | 从评论数据聚类派生受众画像（年龄段/兴趣点/语言）；写入账号 DNA | 🟡 算法底座：本地聚类和序列化已有；缺合规评论数据源、DNA 候选确认与字段级锁定接线 |
