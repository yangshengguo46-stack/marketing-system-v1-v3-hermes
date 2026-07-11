# Marketing OS 原生融合与去重基线

> 日期：2026-07-11  
> 裁决原则：Hermes 已有、能力更成熟的 owner，直接沿用或修改 Hermes；Marketing OS 只保留营销经营领域独有的状态、规则和能力。

## 1. 本轮事实

`marketing_os/` 当前约 2,800 行、110KB。旧 FastAPI、外层 Agent service、根 Electron/React 壳、嵌套 Hermes、补丁回放和双消息运行时已经删除。因此当前问题不是“又有一套大系统”，而是少数职责仍没有完全归还给 Hermes 原生 owner。

不能以去重为名删除账号经营、证据、内容资产和平台运营知识。这些是产品差异化领域，不是 Hermes 通用 Agent 已有能力。真正需要去掉的是重复 owner、兼容数据源和第二套基础设施。

## 2. 所有权裁决

| 能力 | 当前代码 | 裁决 | 目标 owner |
|---|---|---|---|
| Agent loop、计划、长任务、checkpoint、审批 | Hermes 原生 | 禁止复制 | Hermes runtime |
| Session 与会话继承 | `hermes_state.py` | 账号 scope 继续并入 SessionDB；领域层只校验账号存在性 | SessionDB |
| MCP、Skill、Plugin、Provider、密钥 | Hermes 原生 | 禁止 Marketing OS 再造 catalog、loader 或 secret owner | Hermes ecosystem/config |
| 飞书/微信 home channel | Hermes gateway 已有 `/sethome`、授权与路由 | 保留中文短语和首次可信私聊自动绑定这一小段产品 UX；持久化与路由必须调用 Hermes 原生实现 | Gateway |
| 产品身份与升级政策 | `marketing_os/product.py` | 保留产品差异；升级状态最终收口为一个 release policy，不在 Electron/Python 双写 | Hermes product fork |
| 账号生命周期、受众、定位、对标 | `marketing_os/domains` | 保留 | Marketing domain |
| EvidencePack 与内容引用约束 | `marketing_os/domains/evidence.py` | 保留并接入 Hermes 工具结果中间件；不复制通用 tool verification | Marketing domain + Hermes middleware |
| 内容资产、平台变体与质量门 | `marketing_os/domains` | 保留 | Marketing domain |
| 内容生产“Planner” | `content_production.py` | 只允许做确定性 lane/policy/spec；不得发展成第二个自主 Agent planner | Marketing policy called by Hermes |
| 业务 SQLite 连接、事务、迁移 | 三个 repository 各自复制 | 立即合并 | `MarketingDomainRepository` |
| `accounts.json` 与旧 `agent_core.db` 兼容读取 | `data_paths.py`、`account_context.py` | 迁移期只读；完成 schema migration 后删除 | 单一产品 SQLite truth |

## 3. 删除顺序

### 第一批：已开始，低风险

1. 合并营销仓储的 SQLite 连接和事务基础设施。
2. 每个领域类只保留 schema、状态机和业务查询。
3. 测试证明账号 scope、EvidencePack 和内容资产语义不变。

### 第二批：会话与渠道归位

1. 将账号 scope 的读取、继承和原子绑定收口进 SessionDB 原生 API。
2. `marketing_os/session_scope.py` 最终只保留账号领域校验与 prompt projection，或者在调用点足够清晰时完全消失。
3. 把中文“设为通知窗口”和可信 DM 自动 home 行为变为 Gateway 产品 policy hook；删除重复的 env/config 写入代码，统一复用 `/sethome` handler。

### 第三批：删除旧数据兼容

1. 建立可重复、可回滚的 accounts/account lifecycle/content/evidence schema migration。
2. 将 `accounts.json` 和历史 `agent_core.db` 数据一次导入当前产品库并记录 migration version。
3. UI、Agent 工具和领域仓储均从同一个真相库读取后，删除兼容 reader 和环境变量旁路。

### 第四批：发布与学习闭环归一

1. 删除 `publishing.json`，只保留 SQL task/receipt/checkpoint。
2. 指标、复盘、记忆候选从真实 receipt 继续推进，不复制 Hermes memory engine。
3. Marketing OS 只定义“什么经营事实值得学”；存储、召回、压缩和治理继续使用 Hermes 原生记忆机制。

## 4. 禁止事项

- 不再新增第二个 Agent API、sidecar、bridge 或 Provider 管理器。
- 不把领域业务表硬塞进 SessionDB；SessionDB 管会话，Marketing domain 管经营事实，但共用一套经过治理的存储基础设施。
- 不把确定性内容 policy 命名或扩张成自主 Agent planner。
- 不为暂时兼容而形成永久双写。
- 不因为源码目录仍叫 `marketing_os` 就判定它是外挂；判断标准是执行链和 owner 是否唯一。

## 5. 完成门

去重完成不是 `marketing_os/` 文件归零，而是满足：

1. 一个 Agent loop。
2. 一个 session owner。
3. 一个 Provider/密钥/MCP/Skill/Plugin owner。
4. 一个账号与业务事实真相源。
5. 一个发布回执真相源。
6. 营销目录只剩通用 Hermes 不具备的经营领域模型、状态机和产品策略。
