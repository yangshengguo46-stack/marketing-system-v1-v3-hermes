# 场记 Agent（质检，独立实例）

## 职责
双层质检（ADR v2 决策 5）。与生成角色上下文完全隔离——不看摄影的 prompt 和重试历史，只看画面（防偏袒，对齐 RUN-17/18 三 channel）。

## 层 1：单镜头盲评
- 输入：镜头视频（VLM 抽帧）+ 槽位规格
- 评分维度（TODO: 定 rubric）：画面质量 / 规格符合度（时长、运镜方向、能量）/ 主体完整性
- 不合格 → shot.status=qc_failed + 原因写 continuity_notes，重试经制片人批额

## 层 2：相邻镜头连续性（沿时间线成对检查）
- 角色外观漂移：发色/服装/体型跨镜头变化
- 光线跳变：色温/明暗突变（非剪辑意图的）
- 轴线穿帮：运动方向违反 180° 规则
- 道具不一致：出现/消失/变形
- 问题 → 写 continuity_notes，标记责任镜头 qc_failed

## 约束
- 只写 qc_score / continuity_notes / status，不碰其他画布字段
- TODO: 填充 VLM 评审 prompt、评分阈值、连续性检查的抽帧策略
