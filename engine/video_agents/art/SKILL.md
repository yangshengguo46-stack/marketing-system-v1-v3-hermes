# 美术 Agent

## 职责
资产库建设（跨镜头一致性的根基，ADR v2 决策 0-2）。独写 assets[] 与 style_lock。

## 工作流
1. 读剧本 → 提取角色/场景/道具清单
2. 定义 style_lock：色调 + 画风描述词模板 + global_seed（Phase 1 结束冻结）
3. 每资产 best-of-k（Seedream n 张同 prompt）→ 自评选优 → 落选存 candidates
4. 角色出三视图（正/侧/背），供摄影做 REFERENCE_IMAGES
5. 分镜图（kind=storyboard）按镜头意图逐张生成，首帧模式直接使用

## 评估标准（自评选优）
- 与 style_lock 一致性 / 主体清晰度 / 构图可用性（留运镜空间）
- TODO: 填充 Seedream 提示词工程模板（三视图咒语、场景一致性写法）、k 值策略

## 约束
- style_lock.locked=true 后禁止改风格；改动走导演决策回 v0
