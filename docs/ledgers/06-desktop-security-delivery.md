# 桌面、安全与交付执行台账

## 完成目标

在干净电脑上可安装、运行、升级、恢复和卸载；秘密只在本机受控 host；所有 Agent、MCP、网络和副作用都有最小权限与脱敏审计。

## 任务清单

| ID | 任务 | 具体执行 | 完成证据 | 状态 |
|---|---|---|---|---|
| DESK-01 | 进程责任图 | Electron/backend/Hermes/MCP/renderer 生命周期、端口、令牌、崩溃和退出顺序 | ✅ code done：`docs/architecture/process-responsibility.md` — 完整进程拓扑图（Electron Main→Backend→Hermes Agent→MCP CLI→Chromium + Renderer + Channel Bridge）、启动顺序、关停顺序、崩溃恢复矩阵、端口分配（19519 自迁移）、令牌存储（api-token 0o600 + providers.env）、IPC allowlist（90+ 条目）、健康端点（/health）、数据路径（macOS）；27 项测试验证文档与代码一致性（健康端点、启动/关停序列、崩溃恢复、IPC allowlist、令牌安全、数据路径） |
| DESK-02 | IPC 最小面 | renderer 只能调用 allowlist；参数 canonicalize；禁止任意 URL/命令/文件路径 | 攻击面测试 | 🟡 有地基 |
| DESK-03 | 秘密存储 | Cookie 仅 profile，API key 用 Keychain；DB/event/log/trace 不落原值 | 🟡 自动化完成、真人待验：Electron `safeStorage` 自动把旧 `providers.env` 迁移为 Keychain/系统安全存储支持的加密文件并删除明文；store/trace 脱敏和真实目录扫描通过。待在已配置 API Key 的桌面 App 上重启一次，确认迁移后模型仍可用 |
| DESK-04 | 本地服务认证 | 随机令牌、loopback、来源校验、端口冲突与重放防护 | 未授权请求全部拒绝 | 🟡 有地基 |
| DESK-05 | CSP/导航/窗口 | renderer CSP；外链白名单；登录窗口限制；阻止恶意新窗口和协议 | 🟡 code done：主 renderer 已启用 CSP、sandbox、禁止新窗口并限制主窗口导航；平台登录窗口仍需按 OAuth/验证域名完成白名单真人回归 |
| DESK-06 | 依赖供应链 | lockfile、SBOM、许可证清单、audit、固定 MCP/Python/runtime commit | ✅ code done：`scripts/dependency_audit.py` — 生成 SBOM（Python 5 + NPM 100+ 依赖）、许可证清单（Python+NPM；NPM 许可证依赖本地 `license-checker`，缺失时离线快速降级，不隐式联网）、验证全部 Python 依赖 `==` 精确锁定、Hermes commit SHA 固定（4488fe1）、`@playwright/mcp@0.0.77` + `mcp==1.26.0` 双重锁定、package-lock.json integrity hash 覆盖率 >50%；`docs/sbom/sbom.json` + `docs/sbom/license-inventory.json`；20 项测试通过 |
| DESK-07 | Python/Hermes 随包 | 不依赖用户全局 Python/Hermes；资源路径和可执行权限正确 | 干净 macOS 安装 E2E | 🟡 本机构建通过 |
| DESK-08 | 自包含桌面运行时 | 干净电脑、断网、无全局 Python/Node/Hermes 也能首启；浏览器、Agent runtime 和必要原生依赖均随包或有明确离线资源策略 | 🔴 未完成：默认构建已切到 Hermes-native Desktop，旧 PyInstaller/FastAPI/MCP fat-package 校验被移除；新 `verify_offline_launch.py` 分开检查“原生 app 结构”和“自包含 runtime”，当前薄安装器会因仍需网络 bootstrap 而明确失败，禁止继续用旧结构测试冒充离线交付。下一步是内嵌固定产品 tree、Python runtime 与必要浏览器资源，再做真实断网机验收 |
| DESK-09 | 数据迁移 | DB/profile/config 版本；升级前备份；失败回滚；跨版本 fixture | ✅ automated verified：迁移已接入 `AgentCoreStore` 实际启动；修复无效 v3/v4 SQL、重复列迁移和 `executescript` 隐式提交；备份改用 SQLite online backup 以包含 WAL；覆盖全新库、无版本旧库、N-1→N、失败恢复和数据保留。profile/config 版本化仍属后续交付项 |
| DESK-10 | 崩溃恢复 | backend/MCP/Electron 单独崩溃不损坏 task/effect/profile；用户看见恢复状态 | 🟡 自动化地基：8 场景模拟和持久化测试已有，但尚未真实 SIGKILL 各进程并验证用户可见恢复状态，不标记真人完成 |
| DESK-11 | 日志与诊断 | 本地脱敏日志、source health、代理、版本、任务 ID；一键导出前预览 | 诊断包无秘密 | ⏳ |
| DESK-12 | macOS 签名公证 | Developer ID、hardened runtime、entitlements、notarization | Gatekeeper 干净机通过 | ⏳ |
| DESK-13 | 更新与回滚 | 签名更新、分阶段、失败回退、数据库兼容；运行任务升级策略 | staging 更新 E2E | ⏳ |
| DESK-14 | 卸载与数据选择 | 用户选择保留/删除账号 profile、DB、模型和缓存；删除可验证 | 干净卸载测试 | ⏳ |
| DESK-15 | Windows 评估 | Keychain 替代、路径、签名、WebView/浏览器、杀软、安装器 | 平台差距报告后再排期 | ⏳ P2 |
