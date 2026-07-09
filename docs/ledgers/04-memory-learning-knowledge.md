# 记忆、知识、自我学习与技能执行台账

## 完成目标

系统长期学会用户偏好、账号适配、拒绝模式、平台差异、失败恢复和有效流程；所有学习都有证据、范围、时间、冲突、撤销和效果验证，不能静默改权限、生产代码或全局提示词。

## 任务清单

| ID | 任务 | 具体执行 | 完成证据 | 状态 |
|---|---|---|---|---|
| MEM-01 | 记忆事件协议 | 采纳/拒绝/修改/明确陈述/发布结果/失败恢复分别建 typed event；保存 provenance | ✅ code done：9 种 typed event + 5 种 provenance + `add/update/delete_memory` 自动发射事件到 `task_events`；9 测试通过 |
| MEM-02 | Candidate 管线 | Agent 只写 pending；抽取事实、scope、valid time、confidence、source event；秘密扫描 | 未确认候选不进入上下文 | 🟡 地基已有 |
| MEM-03 | 多证据晋升 | 明确陈述可直接请求确认；行为偏好需多次独立证据；阈值按 kind 配置 | ✅ code done：per-kind 阈值(USER 0.5/ACCOUNT 0.6/EPISODIC 0.6/SEMANTIC 0.7/PROCEDURAL 0.8) + 多源 bonus(每额外源-0.05, max 0.2) + 单次拒绝不永久化；5 测试通过 |
| MEM-04 | 冲突与 supersede | 新旧事实比较适用范围/时间/证据；保留历史和撤销，不物理覆盖 | ✅ code done：2026-07-02 补 `superseded→verified` 回滚转换（原为终态，违反"保留历史和撤销"）；`tests/test_memory_supersede.py` 9 项通过：冲突链保留历史不物理覆盖、三版本链可追溯、跨账号 scope 不误伤、用户纠正内容+MODIFIED 事件、纠正含秘密/空内容拒绝、回滚恢复旧事实且事件可审计、superseded 不可跳 locked/rejected、恢复后可再次被 supersede；待真人 UI 纠正/回滚验收 | � |
| MEM-05 | 时间衰减 | 平台规则、短期偏好、账号阶段分别定义 TTL/衰减；locked 事实不自动失效 | ✅ code done：`MemoryKind.default_ttl_days`(user=90/episodic=180/semantic=365/account=None/procedural=None) + `memory_is_expired()`(locked 永不/无 TTL 永不/过期判定/created_at 回退)；14 测试通过 |
| MEM-06 | Scope 隔离 | user/workspace/project/platform/account/content_type；召回必须显式 scope | 跨账号/项目/平台污染测试 | 🟡 user/account 已有 |
| MEM-07 | 账号 DNA | 定位、受众、人设、内容支柱、风格、禁区、阶段；字段级锁定和证据 | 真人创建、纠正、切账号 | 🟡 schema 地基 |
| MEM-08 | 用户拒绝模式 | 记录拒绝原因、替代选择和上下文；无原因只记事件，不强推断 | ✅ code done：`update_memory_candidate(rejection_reason=...)` 持久化 + `_emit_memory_event` 携带 reason + rejected→verified 自动清除；4 测试通过 |
| MEM-09 | 平台知识 | 规则/用户/表达/注意力条目带来源、地区、版本、生效失效时间 | ✅ code done：`knowledge.py` — `create_knowledge_entry(source/region/version/valid_from/valid_to)` + `knowledge_is_expired` + `supersedes_knowledge`(version compare)；5 测试通过 |
| MEM-10 | 行业资料库 | 用户资料与公共资料分权；引用、版本、权限和删除；文档不自动变偏好 | ✅ code done：`documents.py` — user/public scope + `can_read`/`can_modify` 权限控制 + tags；7 测试通过 |
| MEM-10A | Firecrawl 公开网页研究 | 搜索公开行业/竞品网页并返回 URL、摘要与正文证据；支持免费云 Key 或本机自托管地址；不接管平台登录、不抓私域数据 | 🟡 Provider code done（2026-07-06）：新增 `marketing_research_web_search` 只读工具与 Firecrawl v2 兼容 Provider；云端只允许 `https://api.firecrawl.dev`，自托管只允许 loopback 3002/3003；应用设置可用 safeStorage 加密保存免费云 Key。官方 MCP `3.22.2` tarball integrity 已核验，但 npm 依赖因网络/缓存失败未安装，最终未写入 package/lock；本机无 Docker，故自托管未启动；真实搜索待 Key 验收 |
| MEM-11 | 检索基线 | 先结构化过滤 + FTS；记录 recall/precision/latency；不足再接 sqlite-vec | ✅ code done：`retrieval.py` — `filter_by_scope`(user/account/platform/kind/workspace) + `rank_by_confidence` + `retrieve` pipeline(→ filter→rank→limit)；返回 metrics |
| MEM-12 | 开源 memory 对照 | 用同一脱敏数据集比较 Mem0/LangMem；参考 Letta blocks/Graphiti temporal，不写生产库 | PoC 报告含错误写入率和成本 | ⏳ |
| MEM-13 | 结果记忆 | 发布 receipt、指标窗口、用户反馈和外部因素形成 result event，不直接成为策略 | 🟡 workflow wired：指标回收后自动生成 `publish_result` provenance、published_result classification 的 pending episodic candidate；真实 post 指标源和用户确认 UI 待 PUB |
| MEM-14 | 实验模型 | hypothesis/variant/control/metric/window/result/alternative explanation；避免只看播放量 | A/B 或准实验回放 | ⏳ |
| MEM-15 | 策略候选 | 指标服务计算权重候选、置信度和衰减；LLM 只解释，不直接改权重 | 可审核、可撤销、离线回放 | ⏳ |
| MEM-16 | 恢复策略学习 | 失败事件不直接成技能；同类故障经恢复成功和回放后形成 candidate | 故障 replay 通过 | ⏳ |
| MEM-17 | 技能 staging | 生成技能先写 staging；声明输入、输出、平台、账号范围、所需工具和权限 | 未审批技能不可调用 | ⏳ |
| MEM-18 | 技能安全扫描 | 禁 shell/安装/秘密/扩权/未知网络；权限 diff；prompt injection 检查 | 恶意技能样本全部拒绝 | ⏳ |
| MEM-19 | 脱敏回放与 promotion | 历史任务脱敏；比较成功率/副作用；用户审批后版本化启用 | candidate→test→approve→rollback E2E | ⏳ |
| MEM-20 | 用户治理 UI | 查看证据、确认、纠正、锁定、解锁、遗忘、导出；说明推荐为何受其影响 | 真人可理解性验收 | 🟡 CRUD/UI 地基 |
