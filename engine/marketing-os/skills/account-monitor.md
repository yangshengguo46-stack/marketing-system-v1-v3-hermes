# account-monitor

## 目标

基于 Electron 登录会话已经同步并脱敏的账号指标，生成可追溯的变化报告和告警。

## 边界

- Cookie、Token 和登录窗口只由 Electron 持有。
- 本技能不得启动外部浏览器、调用 CDP、读取环境变量中的 Cookie 或执行 Shell。
- Cron 只创建 `TaskTrigger`；`AgentTask` 才是任务状态真相源。
- 数据缺失、过期或平台页面结构变化时必须明确报告，不能把账号标成“在线”。

## 流程

1. 调用 `marketing_read_accounts` 读取脱敏账号状态与最近同步时间。
2. 调用 `marketing_read_intelligence_report` 检查最近一次巡检的步骤、错误和来源。
3. 只比较已经持久化的指标快照；保留前值、当前值、时间和统计口径。
4. 把异常写成候选判断，不把一次变化直接归因为某条内容或策略。
5. 需要重新登录或同步时，说明需要 Electron capability host；不得自行索取 Cookie。

## 输出要求

- 账号、平台、快照时间和来源。
- 指标变化及计算依据。
- 数据质量和替代解释。
- 建议的下一步验证动作。
