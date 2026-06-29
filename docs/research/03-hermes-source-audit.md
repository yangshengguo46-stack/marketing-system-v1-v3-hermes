# Hermes 源码基线审计与适配决策

## 一、基线

| 项 | 值 |
|---|---|
| 官方仓库 | `https://github.com/NousResearch/hermes-agent.git` |
| 本地位置 | `runtime/hermes-agent` |
| 固定提交 | `4488fe134b1de4359f3a4f1f8368576413e6e268` |
| 提交日期 | 2026-06-28 |
| 源码版本 | `0.17.0` |
| 许可证 | MIT |

`runtime/hermes-agent` 是独立上游 Git 边界；业务代码不得再写入 Hermes 用户目录。营销引擎已迁回 `engine/marketing-os`。

## 二、当前上游比旧安装多出的重要能力

- 单一 `AIAgent` 服务 CLI、Gateway、ACP、batch 和 API 路径。
- SQLite/WAL/FTS5 session storage，支持 CJK trigram、session lineage、模型与成本字段。
- 稳定/上下文/易变 prompt 分层与 context compression。
- 工具 registry、toolset、环境后端、审批和 plugin 系统。
- Gateway 适配微信、飞书及多种消息平台。
- Cron Agent 任务、后台进程、子 Agent、checkpoints 与技能系统。
- 内置 `MEMORY.md/USER.md`，并可加 Honcho、OpenViking、Mem0、Hindsight、Holographic 等 provider。
- turn 后台 review 可提取记忆和改技能，并有 write approval。

## 三、采用/包裹/替换矩阵

| 子系统 | 决策 | 说明 |
|---|---|---|
| Provider resolution / model adapters | 采用 | 保留多模型和 API 兼容，凭据由产品 secret broker 注入 |
| 核心 model/tool loop | 包裹 | 作为长期 runtime；增加产品事件流、取消、task/checkpoint 绑定 |
| Session SQLite/FTS | 采用并迁移 | 保留对话/工具搜索；增加 user/account/task 范围和隐私保留策略 |
| Tool registry/toolsets | 采用机制，重建清单 | 只暴露营销能力；桌面 profile 永久移除任意系统工具 |
| Gateway 平台适配 | 后置采用 | 微信/飞书只是入口；统一连接到同一 session/task/memory 服务 |
| Cron | 包裹 | 改由 `AgentTask` 调度，Cron 只负责触发，不是真相源 |
| Skills/progressive disclosure | 采用 | 技能必须 staging、测试、版本、适用范围和效果证据 |
| Built-in flat memory | 仅兼容 | 作为极小热记忆，不承担账号运营知识系统 |
| Memory provider plugin | 采用接口思想 | 业务主库在本地；外部 provider 作为索引/实验，不可成为唯一真相源 |
| Background self-improvement review | 重写 | 上游提示倾向“多数会话都更新技能”，会过度学习；改为候选提取 + 证据阈值 + 审批/回放 |
| File checkpoints | 局部采用 | 业务任务、审批和外部 effect 需要独立持久 checkpoint 与幂等回执 |
| Generic local shell/computer use | 桌面 profile 禁用 | 与产品 L4 永久禁止冲突 |
| 原始 reasoning 持久化 | 默认禁用 | 只存用户可解释摘要、工具事件和证据，不把内部推理作为产品数据 |

## 四、必须修正的上游默认行为

### 1. 数据目录耦合

上游默认围绕 `$HERMES_HOME`。产品必须把 runtime code、产品数据、平台 session、secret 和业务知识分开，支持应用卸载/升级而不丢用户业务数据。

### 2. 自我学习过度积极

`agent/background_review.py` 的技能 review 明确鼓励大多数 session 产生技能更新。这适合个人开发助手的实验性自改进，不适合面向客户的营销产品。我们改为：所有 review 只产出 candidate；只有重复证据、回放通过和权限审核后才 promotion。

### 3. Cron 使用 fresh session

上游 Cron 适合独立提醒/任务，但账号运营需要持续任务状态、账号上下文和结果归因。Cron 只能发 `TaskTrigger`，由 AgentTask runtime 恢复长期 task。

### 4. Flat memory 容量和语义不足

内置 memory 只有约 2,200 + 1,375 字符，适合少量常驻事实，不支持账号隔离、事实修订、证据、实验和时态知识。不能把它硬扩成更大的 Markdown 文件来冒充业务记忆。

### 5. 权限语言需要产品化

Hermes 的危险命令审批不能直接暴露给普通用户。桌面端需要业务审批卡：账号、动作、目标平台、费用、可见预览、后果和撤销能力。

## 五、源码适配边界

上游仓库保持可 pull/rebase；业务差异优先放在项目 adapter 和插件层。只有下面三类变化进入 Hermes fork：

1. 上游没有可用扩展点，且是稳定 runtime 接口所必需。
2. 安全边界必须在 tool dispatch 之前强制执行。
3. session/task streaming 或取消/恢复无法通过外层 adapter 正确实现。

每个 fork patch 必须有：上游 commit、原因、影响面、测试和未来是否可 upstream。

