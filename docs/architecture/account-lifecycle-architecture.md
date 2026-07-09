# Account Lifecycle Architecture

## 1. 决策

新增一个项目自有的 `AccountLifecycleService`，但不新增第二套 Agent Runtime。Hermes 负责计划和执行，Lifecycle Service 管理业务真相，MCP/API 负责取数与动作，memory 负责受控召回。Hermes fork 可以为体验修改；边界保护的是单一真相、权限和可升级性，不是文件目录。

```text
Agent / UI
    │
    ▼
AccountLifecycleService ─── lifecycle stage + next action
    ├── Strategy repository ─ audience hypotheses / positioning versions
    ├── Evidence repository ─ benchmark observations / audience snapshots
    ├── Experiment repository ─ content hypothesis / prediction / result / retro
    └── Domain events ──────── memory candidate / task / approval / notification
             ▲
     official API / MCP / public source / user input
```

## 2. 领域边界

建议的第一版表结构：

| 表 | 关键字段 | 规则 |
|---|---|---|
| `account_strategy_projects` | user_id, account_id, business_goal, stage, status | 一个账号可有多个历史项目，只有一个 active |
| `audience_hypotheses` | project_id, version, segments_json, pains_json, scenarios_json, exclusions_json, status | 用户确认后生效，旧版不可覆盖 |
| `benchmark_accounts`（扩展） | project_id, target_account_id, relation, selection_reason, source_ref | 不再只按 user_id 孤立存在 |
| `benchmark_observations` | benchmark_account_id, dimension, value_json, provenance_json | 样本与分析结论分开 |
| `audience_snapshots` | account_id, platform, dimensions_json, provenance_json, window_start/end | 时间序列；禁止 latest blob 覆盖历史 |
| `positioning_versions` | project_id, version, promise, differentiation, persona, pillars_json, tone_json, taboos_json, evidence_refs_json, status | 决策有证据、审批和回滚 |
| `account_experiments` | project_id, hypothesis, variable, asset_ids_json, prediction_json, success_criteria_json, status | 与现有 content prediction/retro 关联 |
| `strategy_candidates` | project_id, trigger, proposal_json, evidence_refs_json, confidence, status | Agent 只能先提案，不能静默改定位 |

所有可观察记录采用统一 provenance：

```json
{
  "source_kind": "official_api | creator_center_mcp | public_web | user_input | model_inference",
  "source_ref": "scope-safe reference",
  "captured_at": "ISO-8601",
  "window_start": "ISO-8601 or null",
  "window_end": "ISO-8601 or null",
  "confidence": 0.0,
  "data_gaps": ["occupation_unavailable"]
}
```

## 3. 状态机

```text
goal_defined
  → audience_hypothesis_ready
  → benchmark_evidence_ready
  → positioning_approved
  → experiment_running
  → evidence_collecting
  → review_due
  → experiment_running ...
```

状态只表示“下一步可以做什么”，不表示策略永远完成。账号数据不足时允许带 `data_gaps` 前进，但 Agent 必须把补数列为任务。

## 4. Agent 工具契约

首批工具：

- `marketing_read_account_lifecycle(account_id)`：读阶段、有效版本、缺口和下一步。
- `marketing_draft_audience_hypothesis(...)`：生成草案，不直接生效。
- `marketing_add_benchmark_account(...)`：写入选择理由和来源。
- `marketing_draft_positioning(...)`：引用证据生成定位候选。
- `marketing_compare_audience_gap(...)`：比较目标、对标与实际，不混淆类型。
- `marketing_propose_account_experiment(...)`：创建可证伪内容实验。

写工具必须带 user/account/project scope；重要定位变更需要显式确认。读工具不返回原始 Cookie、Token、完整原评论或越权账号数据。

## 5. 数据流与现有模块衔接

1. 用户对话创建经营目标和受众假设草案。
2. 热点/搜索/MCP 产生对标候选；用户选择后进入 benchmark repository。
3. Agent 基于证据起草定位；批准后投影为兼容的 account DNA 供现有内容工具读取。
4. 内容模块创建资产、评分和盲预测，同时关联 experiment_id。
5. 发布模块保存真实 post_id/receipt；调度回收指标。
6. 官方 API 或 MCP 写 `audience_snapshots`；评论分析只写 inference candidate。
7. learning pipeline 生成 strategy candidate 和 memory candidate；用户确认重要修订。

## 6. 迁移原则

- 不立即删除 `ACCOUNT_DNA_FIELDS`；先把它变成当前有效 `positioning_version` 的只读投影。
- 不立即删除旧 benchmark 表；通过兼容迁移增加 project/scope/provenance，再迁数据。
- `user-profiles.yaml` 首次启动时导入为未确认草案，之后不双写。
- 旧 account stats JSON 保留读取兼容，但新采集只写 versioned snapshot。
- `audience_persona.py` 输出改名为 inference，去除长期保存代表性评论正文。

## 7. 架构验收

- 同一用户两个账号的假设、对标、快照、定位和实验零串号。
- 能回放“为什么在某天改变定位”，包括证据、批准人和旧版本。
- 平台未提供职业时，任何响应都不得声称已知职业分布。
- 新号无粉丝画像时仍可完成假设—对标—定位—首轮实验。
- 老号能比较目标受众与实际受众，并把差距转成实验而非直接改写事实。
- 重启后生命周期阶段和 next action 一致，不重复创建实验或发布 effect。
