# Agent Harness 前沿研究与采用结论（2026）

## 一、Harness 是什么

Harness 不是模型，也不是一套页面。它是围绕模型的执行系统：接收目标、装配上下文、运行 model/tool 循环、持久化状态、约束权限、处理中断和审批、恢复失败、输出事件并接受评测。

Anthropic 2026 年的工程拆分很适合作为本项目边界：

- `Session`：发生过什么的追加式日志。
- `Harness`：调用模型并把工具请求路由到基础设施的循环。
- `Sandbox / capability boundary`：Agent 真正可以动手的环境。

对本项目而言，Electron 只负责显示、输入和承接审批交互，不是 capability owner。原始 Cookie、浏览器 profile 和登录执行归 AccountRegistry / Browser MCP，发布权限与 effect 归 Python Provider / Repository；Agent 只看到被 Tool Gateway 授权的业务能力、结构化结果和审批状态。

## 二、目标 Harness 的九个组成部分

| 模块 | 职责 | 本项目选择 |
|---|---|---|
| Session log | 对话、工具、审批和产物的追加式记录 | SQLite 事件日志，按 user/account/task 隔离 |
| Agent loop | 计划→行动→观察→调整→结束/询问 | 复用 Hermes 核心循环，外包一层事件 API |
| Durable task | 长任务状态、检查点、重试和恢复 | 业务 `AgentTask`，不以聊天进程是否活着为准 |
| Context engine | 稳定前缀、热记忆、检索证据、当前状态 | just-in-time 装配，严格 token 预算 |
| Tool gateway | 名称空间、schema、结果与错误 | `marketing.*` 业务工具，不暴露任意 Shell |
| Policy/approval | L0–L4 权限、持久中断和用户确认 | 规则先于模型；审批可序列化、可恢复 |
| Effect executor | 发布、发送、付费等真实副作用 | 幂等键、预览、确认、回执、补偿 |
| Observability | trace、step、证据、成本、错误、重试 | 用户可读进度 + 开发者结构化 trace |
| Evaluation | 任务、工具、记忆、权限和恢复回放 | 每次技能/提示/模型升级前跑场景集 |

## 三、长任务的正确模型

单纯保留一段很长的对话并不等于长任务。Anthropic 的 long-running harness 经验表明，跨上下文窗口必须留下明确环境状态和交接产物，并让每个工作周期做增量进展。LangGraph 与 OpenAI Agents SDK 的持久中断也说明：等待用户审批时应序列化运行状态，而不是占着进程等消息。

本项目 `AgentTask` 应遵守：

```text
queued → planning → running → waiting_user → running
                  ↘ retrying ↗
                  ↘ paused / failed / completed / cancelled
```

- 每个 step 完成后写 checkpoint 和事件。
- step 只记录可公开的执行摘要，不保存模型私有推理。
- 外部副作用前创建 effect intent；执行时使用 idempotency key。
- 重启后从 checkpoint 恢复，先查 effect receipt，禁止重复发布/重复扣费。
- 用户修改目标时保留已完成产物，只重规划未执行步骤。

## 四、Agent 与 Workflow 的分工

Anthropic 区分固定代码路径的 workflow 与模型动态决定过程的 agent。账号运营需要二者混合：

| 场景 | 控制方式 |
|---|---|
| 登录、同步、发布、删除、付费、审批 | 确定性 workflow |
| 行业研究、选题发散、原因分析、策略规划 | Agent 自主循环 |
| 日常巡检 | 固定外层流程 + Agent 分析节点 |
| 失败恢复 | 已验证恢复规则优先，未知失败交给 Agent 诊断 |

这能避免两个极端：把所有步骤硬编码成呆滞应用，或把登录/发布等高风险操作完全交给模型自由发挥。

## 五、上下文工程

上下文按稳定性分层：

1. 稳定前缀：身份、产品规则、工具 schema、安全边界。
2. 热状态：当前用户、账号 DNA 摘要、任务目标、计划和 checkpoint。
3. 检索证据：平台知识、历史事件、实验、相关技能，仅在需要时加载。
4. 易变状态：时间、工具结果、审批和错误。

只在系统里保留引用 ID 和摘要，需要细节时让 Agent 调工具读取。这既控制 token，也减少过时信息污染。

## 六、工具与权限

Anthropic 的工具工程经验强调清晰 namespace、少而明确的工具、好 schema 和基于真实任务的 eval。MCP 安全规范强调最小 scope、禁止 token passthrough、本地服务最小权限和安全 IPC。

项目规则：

- 工具按 `marketing.read.* / marketing.draft.* / marketing.effect.*` 命名并版本化。
- 工具结果返回 `status / data / evidence / retryability / user_message`，不把异常字符串扔给模型猜。
- Agent 无权读取原始 Cookie、Token、Keychain 或任意文件。
- 发布、删除、对外发送、费用动作使用 L3 effect executor，每次确认。
- 技能只能组合已有工具，不能扩大 scope。
- 外部 MCP 是不可信供应链；新 server 默认只读、沙箱和显式授权。

## 七、审批、可观测与评测

OpenAI Agents SDK 和 LangGraph 都把审批建模为可序列化 interruption：运行暂停，外部决定后恢复同一个 state。我们采用同样语义，但使用自有业务模型，避免锁定框架。

用户看到的不是“tool call JSON”，而是：Agent 正在做什么、依据是什么、下一步将造成什么影响、需要他确认什么。开发者 trace 则记录模型/工具/耗时/成本/重试/产物 ID，并默认脱敏。

每次模型、prompt、tool schema、memory 策略或技能升级，都要回放：

- 寒暄不误触发营销流程。
- 一句目标能产生计划并完成只读研究。
- 页面切换、窗口隐藏、App 重启可恢复。
- 审批等待数小时后仍能继续。
- 断网、验证码、平台结构变化会真实降级。
- 发布动作不会因重试重复执行。
- 恶意网页文本不能诱导 Agent 扩权或写入记忆。

## 八、主要来源

- [Anthropic: Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — 增量工作、跨上下文交接和 long-running harness，B。
- [Anthropic: Scaling Managed Agents](https://www.anthropic.com/engineering/managed-agents) — session/harness/sandbox 拆分与稳定接口，B。
- [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) — workflow/agent 边界、简单可组合模式和 ACI，B。
- [Anthropic: Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — just-in-time context，B。
- [Anthropic: Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents) — 工具 namespace、schema 与工具评测，B。
- [Anthropic: Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) — 多步 Agent 评测，B。
- [LangGraph Persistence](https://docs.langchain.com/oss/javascript/langgraph/persistence) 与 [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) — checkpoint、故障恢复和持久中断，A/B。
- [OpenAI Agents SDK: Human-in-the-loop](https://openai.github.io/openai-agents-python/human_in_the_loop/) 与 [Tracing](https://openai.github.io/openai-agents-python/tracing/) — 可序列化审批状态和 trace 结构，A/B。
- [MCP Security Best Practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices) — scope、授权、token 与本地服务边界，A。
- [NIST AI Agent Identity and Authorization concept paper](https://csrc.nist.gov/pubs/other/2026/02/05/accelerating-the-adoption-of-software-and-ai-agent/ipd) — agent identity、least privilege、审计和不可抵赖，A/B。
- [Anthropic: Trustworthy agents in practice](https://www.anthropic.com/research/trustworthy-agents) — 人类控制、透明、安全和隐私，B。
