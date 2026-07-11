# Git 历史能力保留与原生融合台账

> 日期：2026-07-11  
> 来源分支：`codex/product-architecture-checkpoint-2026-07-09`  
> 原则：恢复产品知识和经过验证的算法，不恢复旧外层运行时、Store、HTTP 或 adapter owner。

## 已恢复并进入 Hermes 原生 Agent

| 历史能力 | 当前落点 | 保留理由 | 当前接入 |
|---|---|---|---|
| `content_feature_snapshot` | `agent/marketing/intelligence/content_feature_snapshot.py` | 发布前冻结可回放特征 | ContentAsset 创建时系统生成 |
| `content_prediction` | `agent/marketing/intelligence/content_prediction.py` | 六维预测合同 | 作为发布前 prediction 内核保留 |
| `content_rubric` | `agent/marketing/intelligence/content_rubric.py` | 可解释内容评分和风险扣分 | Preflight/后续审稿可复用 |
| `influence_score` | `agent/marketing/intelligence/influence_score.py` | InfluenceOS v0 公式 | 内容计划自动预演 |
| `preflight_decision` | `agent/marketing/intelligence/preflight_decision.py` | 把分数转成可执行门 | drafting action 强制消费 |
| `content_retro` | `agent/marketing/intelligence/content_retro.py` | prediction vs actual 纯比较 | 待真实指标 receipt 触发 |
| `learning_governance` | `agent/marketing/intelligence/learning_governance.py` | 多样本后才生成权重候选 | pending candidate 已可创建，不自动生效 |
| `memory_classification` | `agent/marketing/intelligence/memory_classification.py` | 给候选附 source/entity/topic | 只做元数据，不建立第二 memory |
| `receipt_refs / preflight_records / learning_candidates` 合同 | `agent/marketing/intelligence/store.py` | 区分事实、预测、解释 | 使用当前 Marketing domain DB；由 Hermes tool/session 触发 |

## 下一批应重写进原生 owner

| 历史能力 | 不原样恢复的原因 | 新 owner / 处理方式 |
|---|---|---|
| `content_bump` | 旧实现直接围绕固定 rubric | 保留回放、排序一致性和审计思想；接 learning candidate 后再写版本化权重 |
| `blind_eval` | 旧模型/Store 合同已过期 | 作为 Hermes 独立 review turn 或受控 delegate，预测必须先于回执 |
| `content_matrix` | 与账号、平台和实验真相源耦合 | 进入 Agent account/content domain，不另建推荐服务 |
| `experiment_driven_production` | 依赖旧 account experiment schema | 接当前 account lifecycle、ContentAsset 和 preflight ID |
| `platform_stylebook` | 部分规则可能过期 | 进入平台知识/Skill，带来源、地区、版本、生效时间 |
| `content_lane_gate` | 与当前 `ContentProductionPolicy` 重叠 | 合并进 policy + preflight，不保留第二 gate |
| `article_soft_production` | 旧模板化生产可能压低内容质量 | 保留合同和质量门；正文继续由 Hermes Agent 创作 |
| `faceless_video_production` | 旧确定性模板像 PPT | 只保留素材清单、EDL、授权、回执和可恢复时间线合同 |
| `publishing / metric checkpoints` | 旧 Store 与外层 capability host 已删除 | 接 Hermes action approval、tool/effect receipt 和 scheduler |
| `account strategy candidate` | 当前 lifecycle 只迁入首段 | accepted learning candidate 先停在候选，待原生账号策略版本表接收 |

## 禁止恢复

以下历史代码解决的是旧套壳结构，不属于产品能力：

- `hermes_adapter.py`
- `external_mcp_bridge.py`
- `mcp_broker.py`
- `mcp_process_manager.py`
- `mcp_network.py`
- `tool_gateway.py`
- `tool_manifest.py`
- 旧 `AgentCoreStore` 整体
- 旧 FastAPI server/router
- 旧根 Electron/React 桥

对应能力直接使用或修改 Hermes 原生 Agent、tool registry、MCP、Gateway、SessionDB、cron、memory 和 `apps/desktop`。

## 当前完成门

这一轮只证明第一条纵切：

```text
Hermes session/account scope
  -> native marketing plan tool
  -> production-plan checkpoint
  -> immutable preflight + InfluenceOS decision
  -> draft gate
  -> content asset feature snapshot
```

尚未完成：

1. 真实 publish effect 自动转统一 ReceiptRef。
2. 1h/6h/24h/3d/7d 指标自动生成 metric receipt。
3. `content_retro` 自动结算 prediction 与 actual。
4. 多次结果生成 memory/strategy/weight/skill candidate。
5. 治理通过后由 Hermes memory/Skill 与账号策略 owner 接收，而不是在 intelligence 层直接生效。
