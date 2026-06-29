# 内容生产编排管线 — 七工具协作总纲

## 架构

```
Phase 1: 输入抓取 (Agent Reach / Open CLI / baoyu-url-to-markdown)
     ↓
Phase 2: 深度研究 (NotebookLM / Researcher Persona)
     ↓
Phase 3: 内容创作 (Writer Persona + Humanizer-zh + baoyu-illustrator)
     ↓
Phase 4: 多媒体生成 (Listenhub / Remotion / aPaaS)
     ↓
Phase 5: 发布分发 (baoyu-post-wechat / baoyu-post-weibo)
```

## Phase 1 — 输入抓取层

### 工具选择策略
```
if 平台在Agent Reach覆盖范围 → Agent Reach (pip, 最稳定)
elif 平台在Open CLI适配器列表 → Open CLI (零token)
elif 需要深度网页内容 → baoyu-url-to-markdown (转结构化MD)
else → Browser CDP 兜底
```

### 触发
- 定时: Cron daily 08:00
- 手动: /hot-topic-scraper
- 事件: 突发热点检测 (socialop monitor 发现异常流量)

## Phase 2 — 深度研究层

### NotebookLM 集成

```
输入: Phase 1 的热点URL列表 + 用户画像
动作:
  1. notebooklm-py: 批量导入 URLs/PDFs/YouTube
  2. 执行研究查询: "这个热点背后的行业逻辑是什么"
  3. 生成研究简报 (Deep Research)
  4. 可选: 生成 Audio Overview 播客预览
输出: 研究简报 → 传给 Writer
```

### Researcher Persona 工作流
```
1. 接收 Phase 1 的热点数据
2. 判断是否需要深度研究:
   - 高价值热点 (跨平台上榜, 匹配用户画像 > 3 关键词) → NotebookLM 深度研究
   - 一般热点 → 直接用 analyze_trends 快速分析
3. 输出: 分类/排序/研究简报
```

## Phase 3 — 内容创作层

### Writer Persona + 工具链

```
输入: Phase 2 的研究简报 + 用户画像
流水线:
  1. Writer Persona: 选题角度生成 (3角度法)
  2. Humanizer-zh: 脚本初稿 → 去AI味 → 质量评分
  3. baoyu-cover-image: 生成封面图
  4. baoyu-article-illustrator: 生成配图/信息图
  5. baoyu-translate: 需要多语言时翻译
输出: 可直接发布的图文内容
```

### Humanizer-zh 质量门
```
评分 < 30 → 重新改写, 深度去AI味
评分 30-40 → 局部优化, 针对低分维度修复
评分 > 40 → 通过
```

## Phase 4 — 多媒体生成层

### 视频生成路由
```
if 需要播客/对话形式 → Listenhub podcast create
if 需要解说视频 → Listenhub explain + Remotion 后期
if 需要纯视觉/代码驱动 → Remotion (React组件→视频)
if 需要短视频 (抖音/B站) → aPaaS (ACP 预留接口)
if 需要AI音乐 → Listenhub music
```

### Listenhub 集成
```
listenhub podcast create \
  --query "脚本内容" \
  --language zh \
  --mode deep \
  --speakers cozy-man-chinese

输出: 音频URL → 可嵌入文章或单独分发
```

## Phase 5 — 发布分发层

### baoyu-post 系列
```
发布到微信公众号: baoyu-post-to-wechat
发布到微博: baoyu-post-to-weibo  
发布到X/Twitter: baoyu-post-to-x
发布到小红书: baoyu-xhs-images (配图优化)
```

### SocialOp Persona 监控
```
发布后 1h/6h/24h 回查数据
异常流量 → 即时告警
正常数据 → 每日汇总
```
