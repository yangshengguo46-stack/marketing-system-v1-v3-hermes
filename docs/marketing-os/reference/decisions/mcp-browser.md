# 浏览器与 MCP 决策

> 状态：参考决策，不是当前任务台账。当前架构真相以 `../../current/NATIVE_ARCHITECTURE.md` 为准。

## 决策

Marketing OS 不建立第二套 MCP Broker、配置中心或工具注册器。浏览器和专项数据能力直接进入 Hermes 原生 MCP 生态：

```text
用户目标
  → Hermes Agent
  → 原生 marketing_* 工具或经审核的 MCP 工具
  → 原生工具权限、审批和执行记录
  → 浏览器 / 平台能力
  → 结构化证据或真实 effect receipt
```

Hermes 原生实现已经负责：

- `~/.hermes/config.yaml` 中的 `mcp_servers` 配置；
- server discovery、启动、重载和关闭；
- `tools.include` / `tools.exclude`；
- OAuth、远程 URL 校验和安全审计；
- MCP 工具进入统一 Agent tool registry。

营销域只增加平台语义、账号作用域、证据合同和风险规则，不复制上述基础设施。

## 两种工具形态

1. **稳定产品工具**：`marketing_*` 工具表达账号经营、热点、内容、发布和复盘语义。底层可以使用浏览器、公开数据源、官方 API 或经审核 MCP，但调用方不依赖具体 Provider。
2. **原生 MCP 工具**：研究、临时导航和低风险读取可以直接使用 Hermes 注册的 MCP 工具。涉及账号状态或外部副作用时，仍必须经过账号 scope、审批和 receipt 规则。

MCP 是工具生态，不是第二个 Agent，也不是营销业务真相源。

## 账号与浏览器边界

1. 每个 `account_id` 必须拥有独立持久浏览器 profile；不同账号不得共享 cookie、storage state 或 MCP session。
2. 登录时允许 headed 官方页面，由用户完成扫码、验证码或风控确认；登录完成后复用同一 profile 执行后台读取。
3. Cookie、Token 和二维码只留在本机浏览器/安全存储边界，不进入模型上下文、业务数据库或日志。
4. 不把工具连接到包含全部账号的全局 CDP 端点。调试 CDP 只能绑定 loopback、显式启用并及时关闭。
5. 浏览器、MCP 或 Provider 返回的数据必须带来源、采集时间、账号作用域和失败状态；失败时不得由模型补造。

## 工具与供应链约束

- 第三方 server 在进入默认产品能力前必须核验来源、许可证、固定版本、维护活跃度和卸载路径。
- 禁止运行时静默安装 `latest` 或未经审核的包。
- 首批工具采用最小 allowlist；任意 JavaScript、cookie/storage 导出、任意文件上传和 DevTools 默认禁用。
- 参数级约束不能只靠工具名白名单：文件路径、目标域名、等待时间、点击类型和外发数据都需要执行前校验。
- 第三方专项抖音 MCP 只作为候选 Provider；未经双账号隔离、风控、失败恢复和真人回放验收，不进入默认链路。

## 与发布的关系

Playwright 或平台 MCP 可以承担发布 Provider，但不能绕过 Hermes 原生任务、审批、幂等和回执循环。真正发布成功必须由平台侧稳定作品 ID/URL 或等价证据确认；toast、按钮消失和无 ID 成功提示都不构成 receipt。

## 禁止恢复的旧结构

- `ProductMCPBroker`；
- `engine/marketing-os/config/*` 第二套 MCP 配置；
- Python sidecar 代持 cookie；
- 营销模块自己的 server registry、OAuth 或工具审批系统；
- 让模型直接安装、启用或修改第三方 MCP。
