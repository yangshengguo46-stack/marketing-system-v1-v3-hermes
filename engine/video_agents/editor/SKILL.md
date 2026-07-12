# 剪辑师 Agent

## 职责
贯穿首尾（ADR v2 倒置 A + 决策 4）：最先产出时间线骨架，最后产出最终 EDL；只改 EDL 即可零成本重渲染。

## 阶段 1：时间线骨架（剧本定稿后立即执行）
1. 读剧本 + 配音台词，TTS 时长反推每槽位 duration_sec
2. 每槽位定：camera_direction / energy / mood；有 BGM 则节拍点定槽位边界（beat_locked=true）
3. 节奏原则（TODO: 填充短视频节奏知识——开头 3s 钩子、能量曲线、对比剪辑点）
4. 产出后必须调 EDL.validate_skeleton()，问题清零才算完成

## 阶段 2：最终 EDL（镜头齐一批就开始预排，不等全齐）
1. 按槽位填 ClipEntry（入出点微裁至槽位时长）、转场、字幕时间戳+样式（renderer.SUBTITLE_STYLES）
2. 音轨：voice 对齐、sfx 放置点、BGM volume_curve（ducking：voice 出现时降 -12dB）
3. 渲染后 VLM 自检：卡点准不准、音画同步、字幕溢出 → 不满意只改 EDL 重渲染

## 约束
- EDL 是人类可读的剪辑方案，notes 字段写给用户看的方案说明
- TODO: 填充自检 checklist、转场使用规范、字幕样式选择规则
