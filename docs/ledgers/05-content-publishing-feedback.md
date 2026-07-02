# 内容资产、发布与复盘执行台账

## 完成目标

从选题、脚本、素材、版本、审批、发布到指标回收和复盘形成真实闭环；任何平台副作用都以平台 receipt/post ID 为准。

## 任务清单

| ID | 任务 | 具体执行 | 完成证据 | 状态 |
|---|---|---|---|---|
| PUB-01 | ContentAsset 模型 | topic/hook/script/title/cover/media/platform variant/version/parent/status/account/project | ✅ code done：加 `parent_id`(FK)+`topic`+`hook` 列 + 迁移 + `create_content_asset` 版本链(parent→version+1, 不存在→NULL)；4 测试通过 |
| PUB-02 | Artifact 血缘 | 每个内容版本关联 evidence、memory、prompt/model、用户修改和生成时间 | ✅ code done：`create_content_asset` 新增 `memory_ids`/`evidence_ids`/`prompt_model`→存入 `content_json._provenance_*` |
| PUB-03 | 平台变体 | 同一创意按抖音/B站/小红书等生成独立版本；不覆盖原稿 | ✅ code done：`variants.py` — `create_variants`(platform validate+dedup+parent link) + `is_variant_of`；5 测试通过 |
| PUB-04 | 发布 provider contract | prepare/validate/publish/query/delete/metrics；provider 不泄露 Cookie | ✅ code done：`publish_contract.py` — `PublishProvider` Protocol + `ValidationResult` + `validate_publish_asset`(title/platform/status/content checks) |
| PUB-05 | 抖音发布可行性 ADR | 官方接口、创作者中心 MCP、人工确认三路比较；账号类型、审核、风控和条款 | ADR 经用户确认 | ⏳ |
| PUB-06 | 发布前校验 | 账号、素材、时长、格式、标题、合规、授权 scope、计划时间 | ✅ code done：`publish_validate.py` — platform constraints(title_max/tags) + status check + account_id required + video duration check |
| PUB-07 | 真实 L3 effect | intent→审批/grant→执行→receipt；unknown outcome 查询后再决定重试 | 真人发布测试内容并取得 post ID | ⏳ |
| PUB-08 | 排期与队列 | timezone、休眠/离线、重试、取消、错过窗口；借鉴 Postiz 但自有 contract | 时间旅行和重启测试 | ⏳ |
| PUB-09 | 发布状态同步 | local draft/scheduled/publishing/published/failed/deleted 与平台事实对齐 | 平台状态漂移测试 | ⏳ |
| PUB-10 | 指标窗口 | 发布后 1h/6h/24h/3d/7d 拉取播放、留存、互动、关注、转化和评论质量 | 定时任务 + source timestamp | ⏳ |
| PUB-11 | 指标缺失语义 | 不可得、未授权、延迟、0 分开；禁止用 0 填未知 | schema/test/UI | ⏳ |
| PUB-12 | 评论与反馈摘要 | 只读拉取、隐私脱敏、主题/问题/情绪作为证据，不自动私信 | 真人数据 + 注入防护 | ⏳ |
| PUB-13 | 实验归因 | 关联假设、变体、账号阶段、发布时间和外部热点；输出替代解释 | 一次真实复盘报告 | ⏳ |
| PUB-14 | 策略回写 | 复盘只生成 memory/strategy candidate；多次结果后晋升 | 不因单条爆款改全局策略 | ⏳ |
| PUB-15 | 删除与高风险动作 | 删除、批量发送、付费逐次确认；保留审计和平台结果 | 真人 sandbox/测试账号验收 | ⏳ |

