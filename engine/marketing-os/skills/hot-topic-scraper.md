# hot-topic-scraper

## 目标
每日自动抓取主流内容平台热搜榜，返回结构化热点数据。

## 触发方式
- Cron 定时: 每天 08:00
- 手动: `/hot-topic-scraper`

## 执行流程

### 第一步：并行抓取各平台热搜
使用以下工具并行抓取（平台根据配置可调整）：
1. `scrape_douyin_trending(count=30)` — 抖音热搜
2. `scrape_weibo_trending(count=50)` — 微博热搜
3. `scrape_bilibili_popular(count=30)` — B站热门
4. `scrape_xiaohongshu_trending(cookie=...)` — 小红书（需登录）

### 第二步：等待结果
各平台返回结构化 JSON，包含榜单排名、标题、热度值。

### 第三步：聚合输出
调用 `aggregate_all_trending(platforms=["douyin", "weibo", "bilibili"])` 统一聚合。

## 输出格式
```json
{
  "douyin": [{"rank": 1, "title": "...", "heat": "..."}],
  "weibo": [{"rank": 1, "title": "...", "heat": "..."}],
  "bilibili": [{"rank": 1, "title": "...", "play": "..."}]
}
```

## 注意事项
- 抖音 DOM 选择器可能变化，如果抓取失败，尝试用 page.content() 全文解析
- 小红书需要 cookie 登录态，没有则跳过
- B站 API 需要带 Referer: https://www.bilibili.com header
- 抓取间隔不少于 30 秒，避免被反爬
