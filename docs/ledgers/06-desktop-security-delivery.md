# 桌面、安全与交付执行台账

## 完成目标

在干净电脑上可安装、运行、升级、恢复和卸载；秘密只在本机受控 host；所有 Agent、MCP、网络和副作用都有最小权限与脱敏审计。

## 任务清单

| ID | 任务 | 具体执行 | 完成证据 | 状态 |
|---|---|---|---|---|
| DESK-01 | 进程责任图 | Electron/backend/Hermes/MCP/renderer 生命周期、端口、令牌、崩溃和退出顺序 | 架构图与健康接口一致 | ⏳ |
| DESK-02 | IPC 最小面 | renderer 只能调用 allowlist；参数 canonicalize；禁止任意 URL/命令/文件路径 | 攻击面测试 | 🟡 有地基 |
| DESK-03 | 秘密存储 | Cookie 仅 profile，API key 用 Keychain；DB/event/log/trace 不落原值 | secret scanner + 迁移测试 | ⏳ |
| DESK-04 | 本地服务认证 | 随机令牌、loopback、来源校验、端口冲突与重放防护 | 未授权请求全部拒绝 | 🟡 有地基 |
| DESK-05 | CSP/导航/窗口 | renderer CSP；外链白名单；登录窗口限制；阻止恶意新窗口和协议 | Electron 安全测试 | ⏳ |
| DESK-06 | 依赖供应链 | lockfile、SBOM、许可证清单、audit、固定 MCP/Python/runtime commit | CI artifact + 0 未解释高危 | ⏳ |
| DESK-07 | Python/Hermes 随包 | 不依赖用户全局 Python/Hermes；资源路径和可执行权限正确 | 干净 macOS 安装 E2E | 🟡 本机构建通过 |
| DESK-08 | Playwright 浏览器随包 | 明确浏览器二进制下载/体积/升级/离线策略；不在运行时偷偷下载 | 离线首次启动 | 🔄 macOS 打包主干完成：构建期固定 `@playwright/mcp@0.0.77`、Playwright `1.62.0-alpha-2026-06-29`、Chromium 1229；`prepare-mcp-runtime.mjs` 生成约 375MB runtime，Electron 自身以 Node 模式执行 CLI，并显式传内置 Chromium executable。真实 staged runtime headless 启动 healthy。待 DMG 构建、断网干净机首次启动、Windows runtime 与 SBOM 验收。 |
| DESK-09 | 数据迁移 | DB/profile/config 版本；升级前备份；失败回滚；跨版本 fixture | N-1→N 和失败恢复 | ⏳ |
| DESK-10 | 崩溃恢复 | backend/MCP/Electron 单独崩溃不损坏 task/effect/profile；用户看见恢复状态 | 故障注入矩阵 | ⏳ |
| DESK-11 | 日志与诊断 | 本地脱敏日志、source health、代理、版本、任务 ID；一键导出前预览 | 诊断包无秘密 | ⏳ |
| DESK-12 | macOS 签名公证 | Developer ID、hardened runtime、entitlements、notarization | Gatekeeper 干净机通过 | ⏳ |
| DESK-13 | 更新与回滚 | 签名更新、分阶段、失败回退、数据库兼容；运行任务升级策略 | staging 更新 E2E | ⏳ |
| DESK-14 | 卸载与数据选择 | 用户选择保留/删除账号 profile、DB、模型和缓存；删除可验证 | 干净卸载测试 | ⏳ |
| DESK-15 | Windows 评估 | Keychain 替代、路径、签名、WebView/浏览器、杀软、安装器 | 平台差距报告后再排期 | ⏳ P2 |
