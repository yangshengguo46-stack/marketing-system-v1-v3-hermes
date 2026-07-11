# Hermes-native Marketing OS 重建基线

> 状态：active / superseding
>
> 2026-07-10 起，本文件取代此前的“Marketing Agent Service + Hermes loop adapter”架构。Hermes 源码是产品主干，不是依赖、插件、子进程里的黑盒或需要保护不动的上游内核。Marketing OS 是直接长在这套主干里的原生营销能力。
>
> 2026-07-11 已完成源码归一：本文中的 `runtime/hermes-agent/...` 历史路径统一改为主仓库根路径。产品桌面是 `apps/desktop`，营销领域是 `marketing_os`；不存在嵌套产品仓库和补丁回放。

## 零、这次重构的核心宗旨

> **原本 Hermes 就有的东西，然后我们跟它重叠了，人家方案还比我们优秀的情况下，我们就不要画蛇添足。**

这是本次重构的最高裁决原则。它约束的不是某一个接口，而是所有代码所有权、数据所有权、运行路径和 UI 所有权；与之冲突的历史台账、适配层和“为了少改上游而新增一层”的做法一律失效。

所有重构任务开始前必须先完成一次原生能力审计，并按以下顺序决策：

1. **直接复用**：Hermes 已经具备且合同、体验、稳定性满足产品目标，Marketing OS 只提供营销领域数据和策略，不复制 owner。
2. **原地增强**：Hermes 已有主干但存在产品缺口，直接修改该原生实现、状态模型或 UI，使它成为最终实现。
3. **替换重写**：Hermes 现有实现妨碍正确性或体验，可以在原位置拆除重写，但仍保持一个 owner 和兼容所需生态合同。
4. **新增领域能力**：只有 Hermes 确实没有的营销能力，才在同一源码树内新增原生 domain；新增后不得再保留平行旧 owner。

这条宗旨优先适用于 Provider/密钥、模型选择、Session/Profile、长任务、记忆、MCP、Skill、Plugin、Channel、更新机制和桌面 UI。禁止为了显示“我们做了很多”而给成熟能力再包 adapter、bridge、sidecar、第二套设置页或第二份状态仓。

## 一、产品只有一个 Agent

```text
桌面 / 飞书 / 微信 / Cron / Web surface
                    │
                    ▼
┌────────────────────────────────────────────────────┐
│ Marketing OS — Hermes product fork                │
│                                                    │
│ conversation loop / sessions / long tasks         │
│ plans / checkpoints / interrupt / resume           │
│ tool registry / middleware / approvals / effects   │
│ memory / skills / MCP / plugins / channels         │
│ apps/desktop / gateway / event stream              │
└────────────────────────┬───────────────────────────┘
                         │ account-scoped domain ports
                         ▼
┌────────────────────────────────────────────────────┐
│ Native marketing domains                           │
│ Account | Evidence | Content | Publishing          │
│ Receipt | Metrics | Learning | Platform profiles   │
└────────────────────────┬───────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────┐
│ Canonical data and artifacts                       │
│ SessionDB + business SQLite + artifact store       │
└────────────────────────────────────────────────────┘

Electron capability host (inside the same product)
  └─ secret / window / account profile / file / L3 side effect
```

这里没有第二个 `Marketing Agent Service`，也没有 `Hermes loop adapter`。桌面、消息渠道和定时任务只是同一个 Agent 的不同入口。FastAPI 如果迁移期仍存在，只能是薄 DTO/平台能力传输层，不能创建另一类 session、task、plan、approval、memory 或 event。

## 二、源码所有权

| 能力 | 唯一目标 owner | 允许的配合边界 | 必须删除的旧 owner |
|---|---|---|---|
| 对话、会话、历史、流式事件 | Hermes conversation loop + SessionDB + gateway | surface 只渲染事件 | 外层 `HermesAgentService` 会话循环 |
| 长任务、计划、checkpoint、恢复 | Hermes native task/session state | 领域仓储保存业务 checkpoint | 通过 prompt 猜计划、resume prompt 冒充恢复 |
| 工具、审批、effect | Hermes registry/middleware/approval chain | Electron 执行获批的宿主副作用 | Tool Manifest 动态 import FastAPI handler |
| 记忆、Skill、MCP、Plugin | Hermes 原生生态合同 | Marketing 治理规则原生增强 | 第二套记忆/技能/MCP 注册表 |
| 账号作用域 | SessionDB 中的 `marketing_user_id/account_id` | Account domain 读取当前事实 | UI 临时选中值、模型传入 account_id |
| 证据 | Hermes 工具结果捕获 + Evidence repository | Web/MCP/API 是采集器 | 模型提供 URL 即视为已验证 |
| 内容 | Content domain + canonical ContentAsset | Agent 负责创作，确定性代码负责校验/版本 | 完整草稿塞进长期记忆、旧 JSON 草稿 |
| 发布、回执、指标 | Publishing/Receipt/Metrics domains | Electron/MCP/API 是 provider | `publishing.json` 与 SQL 双写 |
| 产品 UI | `apps/desktop` | Electron 宿主能力与原生 Gateway | 第二套根 `src/` + `electron/` |

`marketing_os/domains` 是产品源码树中的原生领域包，不是外部业务插件。若现有 Hermes 文件形态阻碍体验或状态正确性，可以拆分、重写或删除；约束保护的是单运行时、单真相源、安全审批和生态合同，不是旧目录。

## 三、一次请求的真实路径

```text
User goal
  → native Hermes session (bind user/account once)
  → account context (verified facts + explicit gaps)
  → native task/plan/checkpoint
  → evidence acquisition through Hermes tools
  → deterministic capture into EvidencePack
  → Agent-authored parent draft
  → platform variants + asset references
  → deterministic preflight
  → human approval where required
  → provider execution
  → immutable receipt + metric checkpoints
  → governed retrospective candidate
  → next session retrieves accepted learning
```

页面切换、窗口隐藏和渠道切换不能中断这条路径。所有 surface 使用同一 `session_id/task_id`；任何外部副作用使用同一 `approval_id/effect_id/idempotency_key`。

## 四、证据不是一段提示词

EvidencePack 的最低合同：

| 字段 | 含义 |
|---|---|
| `evidence_id` | 系统生成、不可由模型指定的稳定 ID |
| `user_id/account_id` | 与当前 Hermes 会话相同的不可越权作用域 |
| `source_type/provider` | `web_extract`、官方 API、创作者中心 MCP 等真实采集器 |
| `canonical_url/source_ref` | 可回链来源；没有 URL 的一方数据使用稳定 source ref |
| `title/excerpt` | 可审阅内容，不等于模型结论 |
| `captured_at` | 系统时钟写入的采集时间 |
| `content_sha256` | 对捕获内容计算，禁止调用方提交 |
| `status` | `captured / verified / rejected / stale` |
| `tool_call_id/session_id` | 能追溯到真实执行 |
| `verification` | 确定性完整性结果与后续人工/交叉验证记录 |

`web_search` 只产生候选来源；`web_extract` 成功取得正文后才可 `captured`。模型不能通过营销工具提交任意正文并把它标成 verified。首版“verified”只表示来源、内容、时间、哈希和作用域完整且采集器成功，不表示页面中的每个观点客观正确；需要多源交叉验证的主张必须保留该差异。

内容草稿可以有创意表达，但只要声明使用了事实性证据，其 `evidence_refs` 必须解析为当前账号的真实 Evidence 记录。原始 URL、`source:` 字符串和模型自造 ID 不能通过。

## 五、边界与安全

1. Cookie、Token、Key 只在 Electron/profile/provider 能力边界内使用，不写入 prompt、工具结果和业务库。
2. 模型不能选择任意账号；写工具从 SessionDB 强制取得作用域。
3. 发布、删除、发送、付费和敏感账号动作必须持久审批，并以 effect receipt 幂等。
4. 不保存模型私有推理；只保存用户可见计划、证据、决策摘要、产物和回执。
5. 不以向量相似度替代账号隔离、时效、来源可信度和显式用户纠正。
6. 未知结果不写成成功，缺失指标不写成 0，未校准启发式不包装成预测。
7. Hermes MCP、Hub/User Skill、Plugin 和工具中间件合同继续兼容；Hermes core 通过 Marketing OS 产品版本升级，不允许终端用户原地覆盖 fork。

## 六、迁移纪律

每次只迁一条可运行的纵切：

1. 在 Hermes 主干建立原生 owner 和 schema migration。
2. 让原生 desktop/gateway/tool 主链真实消费。
3. 用自动化证明作用域、恢复、失败和兼容合同。
4. 用开发机证明真实数据路径。
5. 切换默认入口。
6. 删除同能力旧写路径、桥接状态和重复测试。
7. 更新 runtime patch lock、台账和可复现验证。

禁止“先留两套以后再说”。兼容期只能读旧数据或执行一次性迁移；不得再给旧 UI、旧 adapter、旧 FastAPI Agent 路由和旧 JSON 真相源加功能。

## 七、删除门

| Gate | 达成条件 | 达成后动作 |
|---|---|---|
| G1 Account | 原生 session 绑定、账号读取和生命周期写入覆盖首轮使用 | 删除旧 Agent 账号上下文装配 |
| G2 Evidence | Hermes 采集结果自动固化，草稿引用强校验 | 删除外层 evidence prompt/URL 守门 |
| G3 Content | 父稿、平台变体、版本、素材引用都由原生链持久化 | 冻结并删除旧 content production owner |
| G4 Publish | 单一 SQL task/effect/receipt/metric 链被原生 Agent 使用 | 停止并迁移 `publishing.json` |
| G5 Desktop | 工作台、账号、内容、审批和设置全部迁入原生桌面 | 删除根 `src/`、`electron/` 和旧构建入口 |
| G6 Agent | 原生桌面/渠道覆盖 create/history/status/interrupt/resume | 删除 `HermesAgentService` 和 FastAPI `/agent/*` |

## 八、v0.1 完成证据

1. 新用户通过自然对话得到可确认的受众假设和账号方向。
2. 已登录用户的建议明确来自真实账号事实或明确的数据缺口。
3. 一篇知乎/公众号父稿和平台变体引用真实 EvidencePack，可审阅、可修改、可恢复。
4. 发布前审批和 preflight 不把未知、无版权或未校准结果包装成完成。
5. 至少一条人工或自动发布拥有不可变回执，指标能按 checkpoint 回收。
6. 回执形成待治理复盘候选，用户拒绝不会被系统偷偷学成偏好。
7. 切页、隐藏和重启不丢任务、不重复副作用。
8. 干净 macOS 不依赖全局 Hermes、Python 或 Chrome，也能完成真实 Provider 对话和一个 L0 营销能力。

只有自动化测试不能把上述条目标成完成；统一使用 `designed / code / automated / dev-runtime / packaged / human-loop` 六级证据。
