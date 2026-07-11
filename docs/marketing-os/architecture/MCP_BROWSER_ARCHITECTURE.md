# 浏览器与抖音 MCP 架构

## 决策

浏览器控制不再继续堆叠 Electron DOM 选择器。最终链路为：

```text
用户目标
  → Hermes Agent 的稳定 marketing_* 能力
  → L0-L4 策略与用户审批
  → ProductMCPBroker
  → Microsoft Playwright MCP / 专项抖音 MCP
  → 结构化证据或 effect receipt
```

模型不能直接看到第三方 MCP 的全部工具，也不能自行安装、启用或修改 MCP 配置。MCP 只是能力适配器，不是第二个 Agent。

## 四类服务器

| MCP | 产品责任 | 默认等级 | 约束 |
|---|---|---:|---|
| Microsoft Playwright MCP Server | 通用导航、页面快照、受控点击与结构回放 | L2 | 连接账号专属浏览器上下文；只允许白名单工具 |
| 抖音数据分析 MCP | 作品数据、用户画像、互动指标、高频词和结构化 JSON | L2 | 账号级隔离；输出必须含来源与采集时间 |
| douyin-chat-mcp-server | 私信搜索/同步与回复 | 读取 L2、发送 L3 | 发送逐次审批；必须写 effect receipt 和审计 |
| 抖音内容提取 MCP | 分享链接文案、媒体信息、音频转写 | 读取 L0、下载 L1 | 只接受用户提供或公开分享链接；遵守版权与平台规则 |

## 会话与秘密边界

1. Cookie、Token 和登录二维码仍由本机账号会话层持有。
2. 最终形态由 Playwright MCP 为每个 `account_id` 启动独立持久 profile：`userData/mcp-browser/{accountId}`；不得让多个账号共享 profile。
3. 账号管理的“登录/重新登录”调用该账号自己的 Playwright MCP，以 headed 模式展示官方页面；后续采集复用同一 profile，不导出 Cookie。
4. 不把 Playwright MCP 连接到包含所有账号窗口的全局 Electron CDP 端点；这会破坏账号隔离。若调试阶段临时使用 CDP，只能绑定 loopback、显式启用并在任务结束后关闭。
5. Python 营销后端只接收结构化结果，不接收 Cookie 值。
6. 不允许两个账号共用 browser profile、storage state 或 MCP server session。

## 工具暴露原则

- Agent 继续调用 `marketing_trending_search`、`marketing_accounts_sync` 等稳定产品能力。
- ProductMCPBroker 将产品能力映射到经过核验的 MCP server/tool。
- MCP server 必须配置 `tools.include`，并关闭 `resources`、`prompts`。
- npm/Python 包必须固定审核过的版本；禁止 `latest`、`npx -y` 和运行时自动安装。
- MCP 连接失败时返回明确失败或公共数据降级，不得让模型补造结果。

## 当前安装与核验状态

`@playwright/mcp@0.0.77` 已作为正式依赖固定，来源为 Microsoft 官方仓库，许可证 Apache-2.0。真实 stdio discovery 已确认 23 个基础工具，六项最小 schema 冻结在 `engine/marketing-os/config/playwright-mcp-tools.snapshot.json`。`engine/marketing-os/config/mcp-servers.json` 已写入最小 allowlist，但所有服务器仍保持 `enabled=false`。

Account-scoped Manager、SDK 与打包地基已经完成；当前继续禁用的原因是 MCP-05 参数级权限尚未完成。工具级白名单仍不足以阻止 `browser_snapshot.filename` 写文件、`browser_tabs.new` 导航、右键/双击或无限等待。首批只考虑 `browser_navigate`、`browser_snapshot`、`browser_click`、`browser_wait_for`、`browser_tabs`、`browser_close`，并继续禁止任意 JavaScript、Cookie/storage-state 导出、文件上传和 DevTools。

抖音专项 MCP 核验结果：

- 数据分析：只找到 `kk520879/undoom-douyin-data-analysis` 近似候选（0.1.3、MIT）。其浏览器 profile 不可注入、DOM 选择器脆弱且部分指标不完整，只允许隔离 PoC。
- 私信：未找到名称完全匹配且可信的 `douyin-chat-mcp-server`，继续禁用。
- 内容提取：只找到 `yangbuyiya/yby6-crawling-short-video-mcp` 近似候选（1.0.2、MIT）。启动 stdout 有协议风险，音频转写还涉及本地下载和第三方数据外发，必须 fork 审核后再接。

后续按以下顺序启用：

1. 实现 account-scoped MCP 进程管理器，按账号创建和销毁独立 profile。
2. 用一个测试账号完成导航、快照和受控点击验收，再用两个账号验证零串号。
3. 分别核验三个抖音项目；同名或无许可证项目不接入。
4. 先接数据分析和公开内容读取，再接私信读取；L3 私信发送最后接入。
5. 完成真人回放、Cookie 失效、验证码、限流和断线恢复后，才能替换旧 Electron DOM 采集。
