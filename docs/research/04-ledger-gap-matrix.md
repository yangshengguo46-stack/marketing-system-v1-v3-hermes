# 资料库与 Agent Core 台账对照

## 一、原则与运行时

| 台账 ID | 研究结论 | 实施决定 | 优先级 |
|---|---|---|---|
| CORE-P-01 | Agent 必须有持久 session/harness，不是单轮 CLI | Hermes loop 服务化，桌面绑定稳定 session | P0 |
| CORE-P-02 | 桌面应成为 capability boundary | Electron 持有秘密和外部副作用，Agent 只见业务工具 | P0 |
| CORE-P-03 | 权限由确定性 policy 执行 | L0–L4 在 tool dispatch 前裁决，技能不可扩权 | P0 |
| CORE-P-04 | 长期运营依赖 task、memory、experiment 循环 | 建立 AgentTask + 结果/实验 + 学习候选 | P0/P1 |
| CORE-P-05 | Memory 和建议必须可追溯 | evidence、source、valid time、confidence 全链路 | P1 |
| CORE-P-06 | 长期记忆是控制面也是攻击面 | 用户可查改删；写入候选化；外部内容不自动信任 | P0 |
| CORE-H-01 | Session 是追加式事实日志 | 采用 Hermes SQLite/FTS，增加产品 scope | P0 |
| CORE-H-02 | 长任务必须可 checkpoint/resume | 自有 AgentTask，不把进程活性当任务状态 | P0 |
| CORE-H-03 | Cron 只适合 trigger | Cron → TaskTrigger → 恢复 AgentTask | P1 |
| CORE-H-04 | Flat memory 只适合热点事实 | 新建结构化 Memory Service，保留兼容层 | P1 |
| CORE-H-05/06 | 自动技能修改容易过拟合 | candidate → replay → approve → versioned promotion | P1 |
| CORE-H-07 | 文件回滚不足以覆盖外部副作用 | effect intent/receipt/idempotency/compensation | P0 |
| CORE-H-08 | 子 Agent 是可选优化 | 研究任务可用；共享最小上下文且不继承 L3 权限 | P2 |
| CORE-H-09 | 审批必须可持久暂停/恢复 | ApprovalRequest 存库，Electron 展示业务卡片 | P0 |
| CORE-H-10 | 工具越多不等于更智能 | `marketing-desktop` 最小 toolset + namespace + eval | P0 |

## 二、任务、记忆与学习

| 台账 ID | 资料库补强 | 新验收点 |
|---|---|---|
| TASK-01/02/03 | durable task 与 UI 生命周期分离 | 隐藏窗口、退出 UI、升级 runtime 后均可恢复 |
| TASK-04 | 持久 interruption | 等待数小时/跨重启后审批仍落在原 tool call |
| TASK-05 | 事件溯源式重规划 | 已完成产物保留，未执行 step 产生新 plan version |
| TASK-06 | retryability + recovery skill | 只对可重试错误自动重试，副作用前查 receipt |
| TASK-07 | 取消是状态和清理协议 | 停止 worker、释放浏览器、保留审计与产物 |
| LEARN-01/03 | 一次反馈写事件，多次证据才形成偏好 | 展示证据次数、置信度、撤销与失效 |
| LEARN-02/04 | account/platform 是记忆 namespace | 跨账号污染测试、跨平台差异测试 |
| LEARN-05 | 失败不是技能，验证成功的恢复才是 | 故障回放必须通过才 promotion |
| LEARN-06 | 技能是程序性记忆 | staging、静态扫描、脱敏回放、版本、rollback |
| LEARN-07 | LLM 不直接调策略权重 | 指标/实验服务计算更新；LLM 只生成解释和假设 |
| KB-01/02 | 知识条目需要来源和有效期 | 过期平台规则不会覆盖当前规则 |
| KB-03 | Account DNA 是结构化热记忆 | 用户可锁定字段，Agent 不可静默覆盖 |
| KB-04/05 | 内容资产与实验独立于聊天记忆 | 内容版本、发布任务、指标、假设可关联 |
| KB-06 | 拒绝原因比 yes/no 更有价值 | 无原因时不做强推断 |
| KB-07 | 技能带适用范围和效果证据 | 可回答“在哪些账号/平台有效” |

## 三、原台账需修正的假设

1. “Hermes 原生可用”不等于“产品可直接交付”。上游能力要经过数据隔离、权限、持久任务和 UI 语义适配。
2. 记忆管理页不是最后补的设置页，而是长期智能可信度的一部分。
3. 微信/飞书不建立第二套 Agent 和记忆；它们只是同一个 runtime 的输入输出 surface。
4. Web 视频应用不建立第二套智能体；通过 capability contract 接受 task/context/artifact，并把结果写回同一事件流。
5. “自我学习”不允许静默改生产 prompt、权限或代码；它产出可检查的事实、策略候选和技能候选。

## 四、重建顺序

1. P0：源码/数据边界、AgentTask/Event/Approval/Effect 数据模型。
2. P0：Hermes loop service adapter、稳定 session、事件流与取消。
3. P0：`marketing-desktop` 最小工具集和 L0–L4 policy。
4. P0：一句目标 → 计划 → 只读研究 → 证据 → 等待确认的样板。
5. P1：用户/账号热记忆、事件候选和修订机制。
6. P1：内容资产、发布结果、实验与策略权重。
7. P1：技能候选、回放、审核和 promotion。
8. P2：微信/飞书、Web 视频 surface、多 Agent 优化和时态图评估。

## 五、2026-06-30 统一进度口径复核

> 本节只做“研究完成标准 → 当前产品证据”的映射，不用代码行数或测试数量重算分母。用户确认的统一基线为：完整产品约 `61%`，桌面端第一版可试用约 `72%`。

| 模块 | 冻结进度 | 对照资料库后的判断 |
|---|---:|---|
| 桌面 Agent 基础架构 | 85% | capability boundary、持久 service 和本机生命周期地基已成；干净机 runtime、升级恢复和真实连续运行仍缺 |
| 对话、任务、审批、记忆 | 72% | session/task/event/approval 已有；精确 checkpoint、真实模型主链与跨重启 interruption 尚未完成 |
| 抖音登录与热点采集 | 75% | 真人登录、双账号隔离、公开身份与创作者中心指标同步已通过 | 行业定向采集改走 MCP；页面结构回放和 Agent 最终证据回答仍缺 |
| 长期学习与账号 DNA | 40% | schema、治理 UI、scope、supersede、DNA 函数和测试只是地基；没有真实反馈/发布结果持续驱动的学习循环 |
| 自动发布与指标复盘 | 20% | intent/receipt/状态机及 L3 占位执行器存在；没有真实平台发布、post ID、指标回收、实验归因和策略更新 |
| 打包交付 | 60% | 本机构建通过；干净机、签名、公证、升级和卸载矩阵未验收 |
| Web 视频应用 | 契约阶段 | 只保留同一 AgentTask/context/artifact/event 的接口契约，不计入桌面主链完成度 |

### 防止进度虚高的统一解释

1. `checkpoint_json`、completed_steps 和重启单测存在，不等于真实 Hermes 执行器可从精确 step 恢复；当前仍按未完成处理。
2. supersede、证据晋升、结构化 DNA 的函数和测试存在，不等于 Agent 已从长期账号运营结果中学习；长期学习维持 40%。
3. manifest 中存在 `marketing_effect_publish`，但当前只返回本地模拟成功回执；真实 L3 产品能力仍按 0，发布与复盘维持 20%。
4. 当前自动化测试证明工程地基没有明显回归，但数量不替代真实模型、Electron、跨重启和平台副作用验收。
5. 双账号隔离等局部真人闭环记录在对应模块内部；在其余关键缺口未关闭前，不单独推动四舍五入后的 61%/72%。
