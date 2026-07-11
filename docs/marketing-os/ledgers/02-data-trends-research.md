# 数据、热点与行业研究执行台账

## 完成目标

公共热点自动刷新，登录态平台数据作为增强；Agent 能把真实来源整理成行业证据、候选选题和解释，不伪造平台指标，不因某一数据源失败清空页面。

## 任务清单

| ID | 任务 | 具体执行 | 完成证据 | 状态 |
|---|---|---|---|---|
| DATA-01 | SourceContract | 统一 `source/platform/url/title/author/published_at/collected_at/rank/metrics/query/account_scope/raw_ref` | ✅ code done：`SourceContract` dataclass + `from_dict` 校验/归一化 + `validate_source_batch` + `to_evidence_dict`；11 测试通过；接线到 `trending/import` |
| DATA-02 | 开源源评审 | 对 TrendRadar/RSSHub/TikHub/MediaCrawler/下载 API 分别写 ADR；核验许可证、数据外发、费用、稳定性和卸载 | ✅ code done：`docs/research/06-open-source-candidate-adr.md` — 9 候选逐一核验(A/B/C/D/不采用)含许可证、数据外发、费用和阻断项 |
| DATA-03 | 公共热点 adapter | 把 HotTopics、B站等现有源放入统一 adapter；单源超时、重试、熔断和健康度 | 断一源仍保留缓存和其他源 | 🟡 现有能力可用，待契约化 |
| DATA-04 | 来源均衡 | 定义平台配额、重复簇和时间衰减，避免一个平台占满结果；不得伪造“跨平台” | 固定数据集确定性测试 | 🟡 已有 8/8/7/7，待泛化 |
| DATA-05 | MCP 抖音搜索 adapter | 产品能力映射到账号专属 MCP；搜索词、时间窗、滚动上限和停止条件确定化 | snapshot fixture + 真人搜索结果 | ⏳ 依赖 MCP-03~09 |
| DATA-06 | 页面结构适配 | 选择器优先可访问性结构和语义证据；保存脱敏 fixture；页面变更明确报 degraded | 三版 fixture 回放；禁止空结果冒充成功 | ⏳ |
| DATA-07 | 证据去重与聚类 | URL canonicalize、标题/作者/内容近重复、同事件跨平台聚类；保留各来源 | ✅ code done：`dedup.py` — URL canonicalize(去tracking params/fragment/lower host)、trigram Jaccard title similarity、`deduplicate_items`(同平台去重)+`cross_platform_clusters`(跨平台聚类)；13 测试通过 |
| DATA-08 | 行业查询规划 | 将”美妆/餐饮/AI教育”等目标拆成关键词、同义词、排除词、平台差异和时间窗；允许用户修正 | ✅ code done：`query_planner.py` — 5 industries 关键词库 + `plan_queries`(keyword×platform 展开+去重+排序) | 🔄 |
| DATA-09 | 证据简报 | Hermes 只能引用 evidence ID；区分事实、推断、建议和未知；每条选题可回到来源 | 真人行业对话 + 忠实度 eval | 🟡 代码地基，待真人闭环 |
| DATA-10 | 自动刷新调度 | App 打开后按 TTL 自动刷新；空闲/休眠/唤醒处理；避免多窗口重复任务 | 跨休眠、断网、重启测试 | 🟡 15 分钟刷新已有，待任务化 |
| DATA-11 | 缓存与陈旧提示 | 保存最后成功结果、来源健康和采集时间；失败显示陈旧，不清空；账号 cache 隔离 | 断网 UI 验收 | 🟡 部分已有 |
| DATA-12 | 限流与平台友好 | 并发、滚动、请求频率、退避和每日上限；遇风控停止并请求人工，不尝试绕过 | ✅ code done：`rate_limiter.py` — per-platform 4-window sliding limits + `allow()` 返回 (ok, wait) + `remaining()`；5 测试通过 |
| DATA-13 | 数据质量评分 | 完整性、新鲜度、来源可信度、交叉印证、异常指标；低质量不能进入强结论 | ✅ code done：`quality.py` — `score_quality()`(completeness 25%+freshness 25%+source 40%+anomaly 10%) + 4-tier quality ranking + `QUALITY_THRESHOLD=0.5`；5 测试通过 |
| DATA-14 | 注入与恶意内容防护 | 网页文本永远是数据；移除指令式污染，限制长度，保留原文引用 | ✅ code done：`guard.py` — 6 类注入 pattern(ignore instructions/forget/you are now/override/system prompt/DAN jailbreak) + `filter_injection` + `guard_content`(保留 provenance) + `is_safe_text`；14 测试通过 |
| DATA-15 | 数据保留与删除 | 公共证据、账号指标、页面 fixture、下载媒体分别定义 TTL 和删除路径 | ✅ code done：`retention.py` — 7 类数据 TTL + `is_expired` + `retention_policy` | 🔄 |

