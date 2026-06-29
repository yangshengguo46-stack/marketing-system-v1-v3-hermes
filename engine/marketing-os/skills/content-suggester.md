# content-suggester

## 目标
结合用户画像和热点趋势，生成个性化的短视频选题建议。

## 前置条件
- `user_profile`: 用户画像数据
- `trends`: trend-analyzer 的分析结果

## 用户画像字段
```yaml
category: "内容领域"        # 科技 / 财经 / 生活 / 娱乐 / 教育 / 游戏
niche: "细分赛道"           # AI编程教学 / 美食探店 / 手机评测
profession: "身份标签"      # 程序员 / 创业者 / 设计师 / 学生
interests: "兴趣关键词"     # Python, 开源, 独立开发
platforms: ["douyin", "bilibili"]  # 主要发布平台
style: "内容风格"           # 教学型 / 娱乐型 / 共鸣型 / 解说型
audience: "目标受众"        # 25-35岁科技从业者
```

## 执行流程

### 第一步：匹配筛选
从 trend-analyzer 的输出中筛选与用户画像匹配的热点：
- 关键词匹配：热点标题中出现用户领域/赛道/兴趣关键词
- 平台匹配：优先关注用户主要发布平台的热点
- 匹配度评分 1-10

### 第二步：选题生成
为每个匹配热点生成 3 种角度：
1. **专业解读向**: 从用户专业视角分析热点背后的逻辑/趋势/影响
2. **教学知识向**: 把热点拆解成知识点，建立专业认知
3. **情感共鸣向**: 热点对普通人的影响，引发讨论和共鸣

### 第三步：难度和流量预估
- 难度: 简单 / 中等 / 困难
- 预估流量: 高 / 中 / 低
- 建议时长: 15s / 30s / 60s

## 输出格式
```json
{
  "suggestions": [
    {
      "trend": "热点标题",
      "trend_source": "微博热搜 #3",
      "hot_level": "🔥",
      "match_score": 8,
      "angles": ["角度1", "角度2", "角度3"],
      "difficulty": "简单",
      "estimated_traffic": "高",
      "suggested_duration": "30s",
      "target_audience": "..."
    }
  ]
}
```
