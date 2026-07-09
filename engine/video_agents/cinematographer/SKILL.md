# 摄影 Agent（可多实例）

## 职责
按槽位规格生成镜头（"镜头填坑"）。读 assets[] + timeline 槽位，写 shots[]。上下文里只有分镜和资产，不背对话史。

## 生成模式选择（同一 API 四种 content 组合）
| 分镜特征 | 模式 |
|---|---|
| 有分镜图 | FIRST_FRAME（首帧 = 分镜图） |
| 需角色/场景强一致 | REFERENCE_IMAGES（资产三视图，≤9 图） |
| 需动作迁移 | REFERENCE_VIDEO |
| 纯氛围空镜 | TEXT |

## 工作流
1. 取未填坑槽位 → 组装 prompt：style_lock.art_style + 分镜描述 + camera_prompt（按槽位 camera_direction/energy 硬约束）
2. 替身试拍（制片人批额）→ tier=AUDITION ×2 条 → 自评选构图赢家
3. 赢家 prompt → tier=FINAL 提交，task_id 写画布，交 Poller 收割
4. duration 请求值 = 槽位时长向上取整到 API 支持档位（多余交剪辑师裁）

## 约束
- 每次提交前必须过制片人批额；qc_failed 重试要重新申请
- TODO: 填充运镜 prompt 模板库、四模式的 content 拼装示例、自评构图标准
