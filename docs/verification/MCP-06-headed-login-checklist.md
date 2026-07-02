# MCP-06 Headed 登录真人验收清单

> 日期：2026-07-01 | 状态：待真人验收
> 前置：`MARKETING_OS_MCP_LOGIN_ENABLED=1`，后端有可用的 `mcp` SDK，`node_modules/.bin/playwright-mcp` 可执行

## 自动化已验证

| 项目 | 状态 |
|---|---|
| `call_tool` 路由到 account-scoped session | ✅ fake transport |
| `call_tool` 在非健康实例 fail closed | ✅ fake transport |
| `call_tool` 工具不在 allowlist 拒绝 | ✅ fake transport |
| account-scoped Broker 在 Manager 前执行 MCP-05 policy | ✅ 自动化测试 |
| 非抖音 origin 在触达 Manager 前拒绝 | ✅ 自动化测试 |
| server `mcp-login/start` 拒绝 renderer 传 URL/command/tool | ⚠️ 代码复核；待补 API 定向测试 |
| 同账号重复 start 幂等、不同账号不同实例 | ⚠️ Manager 已测；API 层待补定向测试 |
| cancel attempt_id 匹配 | ⚠️ 代码复核；待补 API 定向测试 |
| Electron IPC `mcp-login:*` 存在 | ✅ 代码路径 |
| preload 暴露 `mcpLoginStart/Status/Cancel` | ✅ 代码路径 |
| `MARKETING_OS_USER_DATA` 传入后端 | ✅ 代码路径 |
| feature flag 关闭时 409 | ✅ API test |
| MCP-05 策略仍在 browser_navigate 调用前执行 | ✅ Broker 定向测试 |
| 账号页在 flag 开启时触发 MCP，关闭时回退旧路径 | ✅ TypeScript + 代码复核；待真人点击 |
| 超时任务实际停止对应 MCP 实例 | ⚠️ 已实现；待定向计时测试与真人验收 |
| generic click 仍拒绝；仅 `marketing_trending_search` 的热门话题/热门挑战/热点榜单 tab 允许单击 | ✅ 参数级 policy tests |

## 必须真人验证（MCP-06 不声称完成）

- [ ] 启动桌面应用，设置 `MARKETING_OS_MCP_LOGIN_ENABLED=1`
- [x] 打开账号管理页面（2026-07-01 真人验证）
- [x] 点击"添加抖音账号" → Playwright 独立 Chromium 窗口打开
- [x] 窗口显示 `https://creator.douyin.com/`
- [x] 用户自行扫码完成登录
- [x] 登录后连续检测到作品管理/内容管理/数据中心/互动管理，Chromium 自动关闭，账号状态写为 connected
- [ ] 取消按钮工作正常
- [ ] 超时后进程停止
- [x] 重登复用同一 profile（`acct_16646b260407` 无需再次扫码）
- [ ] App 退出时 MCP 进程全部停止
- [ ] feature flag 关闭时回退旧 Electron 登录
- [ ] **不自动写 connected** 状态

## 暂不可验证（后续 MCP）

| 项目 | 对应任务 |
|---|---|
| 登录状态自动识别和收起 | MCP-07 |
| 双账号零串号 | MCP-09 |
| 旧登录路径删除 | MCP-13/14 |

## 已知 gap

- `browser_close`、`browser_snapshot`、`browser_click` 等工具在 MCP-06 阶段暂不开放用于登录流程
- 登录成功判断属于 MCP-07，本阶段只确认窗口打开和交互流程
