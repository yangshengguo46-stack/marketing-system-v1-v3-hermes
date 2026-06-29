# account-monitor

## 目标
定期拉取所有已连接平台账号的数据，生成监控报告，异常指标即时告警。

## 触发方式
- Cron 定时: 每天 09:00, 18:00
- 手动: `/account-monitor`

## 前置条件
- 账号已在营销系统中添加 (通过 `add_account` 工具)
- Bitwarden 已解锁 (BW_SESSION 环境变量有效)

## 执行流程

### 第一步：列出所有账号
调用 `list_accounts()` 获取所有已添加账号。

### 第二步：并行拉取数据
对每个 active 状态的账号调用 `get_account_stats(account_id=...)` 获取：
- 粉丝数
- 近期播放量
- 互动率
- 新增关注趋势

### 第三步：对比上次数据
对比上次监控记录，计算变化：
- 粉丝增长量/增长率
- 播放量趋势 (上涨/持平/下降)
- 互动率变化

### 第四步：异常检测
- 粉丝暴涨 (>50%日增长) → 标记为 viral
- 粉丝下降 → 标记为 warning
- 播放量骤降 (>30%) → 标记为 alert
- 连续3天数据下降 → 标记为 critical

### 第五步：生成报告
```json
{
  "report_time": "2026-06-27T09:00:00",
  "summary": {
    "total_accounts": 5,
    "total_followers": 52300,
    "follower_growth_24h": 230,
    "total_views_24h": 125000
  },
  "accounts": [
    {
      "platform": "douyin",
      "label": "公司主号",
      "followers": 23000,
      "growth_24h": 150,
      "status": "healthy"
    }
  ],
  "alerts": [
    {
      "account": "B站副号",
      "level": "warning",
      "message": "近3天播放量累计下降35%",
      "suggestion": "检查内容质量和发布时间"
    }
  ]
}
```

## 告警通知
- warning/critical 级别告警通过 Hermes 通知推送到所有已连接平台
- 正常报告仅存入 Dashboard，不推送
