# MCP 浏览器与账号会话执行台账

## 完成目标

首次登录展示账号专属官方浏览器；后续任务复用该账号的持久 profile 并尽量无感运行。所有浏览器动作经过稳定营销能力、ProductMCPBroker 和 L0-L4 policy；两个同平台账号绝不共享进程、profile、Cookie、trace 或结果缓存。

## 任务清单

| ID | 任务 | 具体执行 | 完成证据 | 状态 |
|---|---|---|---|---|
| MCP-01 | 账号级进程模型 ADR | 定义 `(platform, account_id)` 实例键、状态机、目录、端口/stdio、并发、崩溃、空闲回收、App 退出和升级迁移；说明 Electron 与后端职责 | ✅ 已复核接受：`docs/architecture/ADR-01-mcp-account-process-model.md` v2；仅代表架构决策完成，不代表 Manager 或浏览器主链完成 |
| MCP-02 | 固定供应链 | 固定 `@playwright/mcp@0.0.77`、lockfile、可执行入口；记录 Apache-2.0、hash、SBOM；禁止 `npx -y/latest` | ✅ 已复核接受：版本/integrity/license/CLI/fail-closed/audit 均通过；隔离目录 `npm ci --offline --ignore-scripts` 真离线安装通过；⚠️ CycloneDX SBOM 因 npm `fsevents` optional mismatch 受阻，作为 DESK-08 前必须关闭的显式交付阻断保留 |
| MCP-03 | AccountScopedMCPManager | 实现 start/get/health/stop/restart；每账号一个进程和 `userData/mcp-browser/{accountId}`；路径防穿越，不能调用 shell | ✅ 已复核接受（工程地基）：官方 Python MCP SDK `1.26.0`、单 lifecycle Task、账号 profile、生命周期文件锁、原子容量预留、idle、有限崩溃恢复、超时清理和 fail-closed 已实现；34 项定向测试、254 项全量测试、PyInstaller 构建和打包后二进制健康启动通过；未启用服务器、未接 Electron、未做真人双账号 |
| MCP-04 | 最小工具发现 | 启动后核验真实 tool schema；只允许 navigate/snapshot/click/wait_for/tabs/close；发现额外工具不自动暴露 | ✅ 已复核接受：真实 `@playwright/mcp@0.0.77` stdio 返回 23 个基础工具，6 个入选工具 schema 已冻结；其余 17 个隐藏；真实发现、schema 漂移、缺失工具和禁用状态测试通过 |
| MCP-05 | 权限分级 | navigate/snapshot/read 与 click 分开；跨域、提交、上传、下载、发布分别升级；Cookie/JS/devtools/storage export 永久拒绝 | ✅ 已复核接受：browser context 强制、真实 capability 映射、批准一致性、严格类型/长度、抖音 HTTPS origin、参数级拒绝、深度/循环/总量脱敏均在 register/dispatch 前执行；generic click 继续全禁，服务器继续 disabled |
| MCP-06 | Headed 登录体验 | 账号管理触发专属 headed 窗口；二维码、短信、滑块由用户处理；成功自动收起，取消/超时清晰返回 | 🔄 复核中：已修复 Manager 类结构破坏、策略绕过和前端未接线；账号页现由 flag 切 MCP/旧 Electron 回退，account-scoped Broker 在 Manager 前执行 MCP-05 policy，超时会停止实例；自动化回归通过。❌ 真实 Chromium、扫码/短信/滑块/取消/超时仍待真人验收；❌ 登录成功识别属 MCP-07；✅ `docs/verification/MCP-06-headed-login-checklist.md` |
| MCP-07 | 登录状态健康 | 按平台定义可信认证信号；区分已登录、过期、风控、网络失败、页面改版，不以 URL 跳转冒充成功 | 固定页面回放 + 真人失效重登 | 🔄 主成功链真人通过：抖音创作者中心采用 accessibility snapshot 双条件识别（至少 2 个后台功能标识、无扫码/手机号/验证码标识），连续两次命中才认证；真人检测到作品管理/内容管理/数据中心/互动管理后自动关窗，账号 `acct_16646b260407` connected，原 profile 重开免扫码。已修复新增账号每次生成新 profile：pending account ID 本地保留至认证成功。343 项全量测试通过；失效、风控、页面改版样本仍待补齐，故暂不完全关闭。 |
| MCP-08 | 后台无感模式 | 已登录 profile 以后台/最小干扰方式运行；需要人工接管时切 headed，不重建 profile | 运行时不抢焦点；接管后任务可继续 | 🔄 主干已实现：Manager `ensure_mode` 复用匹配实例、模式不符时在同一账号 profile 上重启；后端提供 background/takeover/status/stop 高层接口；Electron narrow IPC 与账号页“接管”入口已接通。内置 runtime 已用 Electron-as-Node + 固定 MCP CLI + 指定 Chromium executable 实测 headless healthy，未借用系统 Chrome。待把热点/账号同步从旧 Electron 执行器切流后完成。 |
| MCP-09 | 双账号零串号 | 同时启动两个抖音账号，分别读取身份/主页证据；切换、退出、删除一个账号不影响另一个 | 真人双账号矩阵 + 自动目录/进程隔离测试 | ✅ 自动化已过：17 项测试覆盖独立 data_dir/lock_dir/log_dir/lock_file、独立 instance_token、停一个不影响另一个、重启已停账号不影响另一个、stop_all 停全部、health 精确返回对应账号、路径穿越拒绝（_safe_subpath + _ACCOUNT_RE 双层防护）、不同平台独立目录、源码级验证（user-data-dir 绑定 account_id、_handles 按 platform:account_id 键、无 shell 执行）；待真人双账号扫码验收 |
| MCP-10 | 生命周期清理 | 退出只清该账号 profile；删除前确认；残留进程回收；崩溃后锁文件恢复；卸载策略明确 | ✅ code done：`mcp_lifecycle_cleanup.py` — `delete_account_profile`(profile+lock+log 三重清理, dry_run) + `recover_stale_locks`(PID 检测+僵尸锁清理)；2026-07-02 修复删除路径未做 platform/account 校验与路径穿越防护的缺口（复用 `_validate_platform/_validate_account/_safe_subpath`）；`tests/test_mcp_lifecycle_cleanup.py` 14 项通过：单账号三重删除不影响邻账号、dry_run 不落盘、7 组穿越/畸形 ID 拒绝、死 PID/损坏锁清理、活 PID 与 manager_pid 保留；待进程/目录/DB 三方一致性测试与真人删除确认 | 🔄 |
| MCP-11 | Trace 与脱敏 | 仅调试显式启用；DOM/截图/日志去 Cookie、手机号、私信；保留最短期限和手动删除 | ✅ code done：`mcp_trace_sanitizer.py` — `MARKETING_OS_MCP_TRACE` 显式启用 + 7 类秘密 pattern(session/phone/id/api_key/jwt/cookie/auth) + `sanitize_line`/`sanitize_snapshot_content`；`tests/test_mcp_trace_sanitizer.py` 14 项通过：9 组秘密 pattern 逐项断言、业务内容保真、2000 字符行截断、100KB snapshot 上限、trace 仅在 env 精确为 "1" 时启用；待真人删除测试 | 🔄 |
| MCP-12 | 网络与代理 | 子进程明确继承或配置系统代理；区分直连失败、代理 503、DNS、平台限流；不静默切未知代理 | ✅ code done：`mcp_network.py` — `proxy_env()` 继承系统代理 + `classify_network_error`(proxy/dns/503/429/conn_refused/reset/timeout/tls/unknown 9类)；待 MacPacket 开/关、断网测试 | 🔄 |
| MCP-13 | 旧执行器双跑 | 先 shadow 读取比较结果，不执行双重点击；新链稳定后按能力切流 | 比较报告、功能开关、可回滚 | 🔄 抖音读取能力已切流：热点与账号同步现在 MCP 主跑，旧 Electron session/DOM 只在 MCP 明确失败时回退并记录 `mcp:*:fallback`。真人无头验证：账号身份与粉丝/获赞/最新播放读取成功；创作者中心返回 15 条热点且不弹窗。公共搜索触发“验证码中间页”，已明确不作为无头主链；关键词无命中时返回个性化热点并标记 `matched_keyword=false`，不伪造匹配。已修复同账号同步/热点导航竞态（完整操作串行、有限快照重试）和两条数据链互相覆盖（公共底座 + 持久 MCP session overlay）；刷新后实测 30 条中抖音 8/微博 8/B站 7/知乎 7，其中 8 条为 MCP 账号证据。待连续运行、双账号和结果对比后关闭 fallback。 |
| MCP-14 | 删除旧 DOM 主链 | 所有迁移能力真人通过后删除 Electron DOM/CDP 旧路径及测试假设 | 静态反查 + 全量回归 | ⏳ |

## 禁止提前宣称

- 安装 MCP 包不等于浏览器能力完成。
- 单账号登录不等于多账号隔离完成。
- 页面 snapshot 成功不等于热点采集完成。
- 自动化测试不替代二维码、验证码、失效重登和双账号真人验收。

---

## MCP-01 交付证据（2026-07-01）

### 当前代码证据

| 文件 | 状态 | 说明 |
|---|---|---|
| `engine/agent_core/mcp_broker.py` | 存在 | `ProductMCPBroker` + `MCPServerSpec` + `load_mcp_manifest` 已实现，含 shell 注入防护、only pinned versions、stdio/HTTP 验证 |
| `engine/marketing-os/config/mcp-servers.json` | 存在，version=1 | 5 个 server 登记，全部 `enabled=false`，均有 blocked_reason |
| `docs/architecture/MCP_BROWSER_ARCHITECTURE.md` | 存在 | 四类 MCP server、会话/秘密边界、工具暴露原则、启用顺序 |
| `tests/test_server.py::test_mcp_status_is_fail_closed_until_reviewed_servers_are_installed` | 自动化 | 验证所有 server disabled、ready=false、fail-closed |

### ADR 交付

| 交付物 | 路径 |
|---|---|
| 账号级进程模型 ADR | `docs/architecture/ADR-01-mcp-account-process-model.md` |

ADR 覆盖：
- ✅ `(platform, account_id)` 实例键定义 + account_id 生命周期（预生成→确认→重登→删除）
- ✅ 每账号独立 `--user-data-dir` 路径隔离
- ✅ 完整状态机（7 状态、12 转换，含触发条件）
- ✅ 健康检查协议（tools/list + allowlist 匹配）
- ✅ 并发上限 + 目录锁 + 残留进程回收
- ✅ 空闲回收（headless 10min / headed 30min）
- ✅ 停止、App 退出、升级迁移
- ✅ Electron/Python/MCP Broker 职责边界
- ✅ 数据流威胁图（秘密边界明确）
- ✅ Cookie/日志/trace 脱敏规则
- ✅ `AccountScopedMCPManager` 完整接口契约（13 方法）
- ✅ 已知风险（内存、headed 独立窗口、旧路径共存）

### 未完成风险（不得在 MCP-01 阶段宣称完成）

- MCP-02 供应链锁死未验证（SBOM、离线安装、hash）
- MCP-03 在 MCP-01 交付当时尚未实现；现已完成工程地基，真实工具/登录验收仍属 MCP-04 以后
- MCP-09 双账号零串号真人未验证
- 旧 Electron DOM 采集路径仍为主链

### MCP-01 v2 修订记录（2026-07-01，基于复核意见 15 项修正）

| # | 修正 | ADR 章节/行 |
|---|---|---|
| 1 | 启动入口固定为 `node_modules/.bin/playwright-mcp`，禁止 npx/latest/运行时下载 | §4.1, §4.3 |
| 2 | 删除无效参数 `--headed false`、`--tools ...`、`--browser chromium` | §2 (参数表), §4.3 |
| 3 | 模式切换：不带 `--headless` 默认 headed；`--headless` 后台；不可原地切换；`restart_mode(headless)` 替换 `set_headless()` | §4.4, §5 (状态机), §14 (接口) |
| 4 | CLI 无工具白名单参数；`ProductMCPBroker` 只注册 allowlist 工具；额外官方工具不判 degraded | §11, §6 |
| 5 | `--user-data-dir` 自行持久化；删除"停止前保存/恢复 storage state"；`browser_storage_state` 系列禁止 | §8, §10.3, §11.2 |
| 6 | 首次登录直接展示 Playwright headed Chromium 独立窗口；删除 Electron 透明代理/BrowserView 嵌入 | §12.1, §13.1 |
| 7 | 删除 `npx playwright install chromium` 运行时；浏览器二进制构建期准备，缺失 fail closed | §4.3, §9.3 |
| 8 | 禁止自动删除旧 profile；只在用户明确退出/删除/卸载时清理 | §3.2, §9.4 |
| 9 | 删除扫描 profile 目录 cookies/password/keyring 逻辑；Manager 禁止读取/复制/导出 profile | §10.3 |
| 10 | 锁文件+PID 元数据迁至 `{userData}/mcp-runtime/locks/{platform}/{account_id}.lock` | §4.2, §7.1 |
| 11 | 进程终止使用跨平台抽象 `terminate()→timeout→kill()`，不写死 SIGTERM/SIGKILL | §7.3 |
| 12 | account_id 在打开登录窗口**之前**生成 | §3.2 |
| 13 | Cookie 只在 Playwright profile；`login:cookies` IPC 不再是目标架构组成部分 | §10.1, §13.1 |
| 14 | 登录成功判断不依赖 Python 读 Cookie；由平台适配器根据页面 UI 信号判断 | §10.2 |
| 15 | 健康检查：进程存活+initialize+tools/list+allowlist 工具均在；额外工具由 Broker 隐藏，不是健康失败 | §6 |

### 复核要求

复核者应确认 v2 ADR 中的 CLI 参数表与 `node_modules/.bin/playwright-mcp --help` 一致，状态机允许 restart_mode 切换，接口契约与需求对齐，秘密边界和数据流图正确。复核通过后 MCP-02 方可启动。

---

## MCP-02 交付证据（2026-07-01）

### code done

| 文件 | 改动 |
|---|---|
| `package.json` | `@playwright/mcp` 依赖为精确 `"0.0.77"`（无 ^/~/>/<） |
| `package-lock.json` | lockfile 包含 version=0.0.77、resolved=registry.npmjs.org、integrity=sha512-...、license=Apache-2.0、传递依赖固定 |
| `scripts/verify-playwright-mcp.mjs` | **新建** — 6 项自动检查（package.json 精确版本、lockfile integrity+resolved+license、本地安装包版本、CLI binary、CLI --version、禁止 npx/latest） |
| `docs/security/MCP_PLAYWRIGHT_SUPPLY_CHAIN.md` | **新建** — 来源身份、依赖树、禁止项、构建/运行边界、升级回滚步骤、SBOM 阻断记录 |
| `tests/test_architecture_boundaries.py` | 新增 `test_playwright_mcp_supply_chain_pinned` — 静态检查版本、license、integrity、CLI binary、CLI --version |

### automated verified

| 检查 | 结果 |
|---|---|
| `node scripts/verify-playwright-mcp.mjs` | ALL CHECKS PASSED |
| `pytest test_playwright_mcp_supply_chain_pinned` | 1 passed |
| `npm audit --omit=dev` | 0 vulnerabilities |
| `git diff --check` | OK |
| Full test suite `pytest tests/` | 220 passed |

### offline verified

| 检查 | 结果 |
|---|---|
| 隔离目录 `npm ci --offline --ignore-scripts`（复制 package.json + lockfile） | 复核者重跑成功安装 `@playwright/mcp@0.0.77`，未使用网络回退 |
| installed version | `0.0.77` ✅ |
| 缺失依赖 fail closed | 无 `node_modules` 隔离副本运行验证脚本退出码 `1`，未自动安装或回退全局 CLI |

### blocked

| 阻断 | 说明 |
|---|---|
| `npm sbom --sbom-format cyclonedx` | fsevents optional dependency mismatch 导致 npm sbom 无法完整生成（npm 已知工具链限制）。`npm ls` 和 lockfile integrity 替代验证已通过。完整 SBOM 延至 DESK-08 打包验收时重新生成。 |
| 浏览器二进制离线打包 | Chromium 的构建期安装、跨平台路径和打包属于 DESK-08，不在 MCP-02 完成范围。 |

---

## MCP-03 交付证据（2026-07-01，Codex 收口）

| 类别 | 证据 |
|---|---|
| Python SDK | `backend/requirements.txt` 固定 `mcp==1.26.0`；Hermes bootstrap 安装 `[mcp]` extra；两个虚拟环境均实际 import 通过 |
| 生命周期 | `AccountScopedMCPManager` 用官方 `stdio_client` + `ClientSession`，同一 Task 持有 context；停止、idle、transport error 分流 |
| 隔离与锁 | `(platform, account_id)` 独立 profile；runtime lock handle 持续持有；第二 Manager 不能取得同实例锁；释放时避免误删新锁 |
| 并发与恢复 | Manager 级启动锁保护总量/平台容量；transport ping 暴露断线；有限退避；用户停止和 idle 不重启 |
| 自动化 | `tests/test_mcp_process_manager.py` 34 passed；全量 `254 passed`；TypeScript、Electron 语法和 `git diff --check` 通过 |
| 打包 | PyInstaller 显式收集 MCP client 模块并成功生成；归档包含 `mcp-1.26.0`；打包后二进制 `/health` 与 `/mcp/status` 实际响应正常 |
| 尚未完成 | `mcp-servers.json` 继续全部 disabled；真实工具 schema 属 MCP-04；权限属 MCP-05；登录和双账号真人验收属 MCP-06~09 |

---

## MCP-04 交付证据（2026-07-01）

| 类别 | 证据 |
|---|---|
| 真实发现 | 使用官方 Python MCP SDK 连接固定 `@playwright/mcp@0.0.77` stdio，`initialize`、`tools/list` 和停止均成功，无残留进程 |
| 全量工具 | 当前基础工具共 23 个，完整顺序冻结在 `engine/marketing-os/config/playwright-mcp-tools.snapshot.json` |
| 最小白名单 | 仅 `browser_navigate/snapshot/click/wait_for/tabs/close` 六项写入 manifest；服务器仍为 `enabled=false` |
| 默认拒绝 | `evaluate`、`run_code_unsafe`、上传、表单、键盘、截图、网络读取等未入 allowlist；额外工具只进入审计列表，不注册给 Hermes |
| 漂移检测 | 固定版本的真实工具名称和六项输入 schema 每次测试与 snapshot 比较；缺少任一审核工具即 invalid |
| 参数风险 | snapshot 已记录 `snapshot.filename`、`tabs.new/url`、click 按键/修饰符、wait 时间和 navigate URL 风险；必须由 MCP-05 参数级策略关闭后才可启用 |
| 自动化 | MCP Broker + Process Manager 定向 `45 passed`；真实 discovery 测试不打开页面、不使用账号 profile |

---

## MCP-05 交付证据（2026-07-01，Codex 收口）

| 类别 | 证据 |
|---|---|
| Context | browser role 缺 `BrowserActionContext` 立即拒绝；platform/account/capability/user-or-task/approved 全部 fail-closed |
| Capability | 仅真实 manifest 中的 `marketing_trending_search/session_login/accounts_sync` 可用于只读浏览器工具；任意非空伪 capability 不再有效；generic click allowlist 为空 |
| 参数 | snapshot 禁 filename、boxes=true、非整数 depth；wait 限 0–10 秒；tabs 禁 new/url；click 禁双击/修饰键/非左键；未知参数和类型转换全部拒绝 |
| Origin | 只允许规范化后的 HTTPS `douyin.com` 受控域；userinfo、私网、localhost、非法端口、尾点、控制字符、Unicode/百分号/反斜杠伪装均拒绝 |
| 调用顺序 | 策略和批准检查发生在 `register/get_entry/dispatch` 之前；拒绝路径测试证明注册调用次数为 0 |
| 输出 | Cookie、Authorization、Token、密码等递归脱敏；深度、循环和 256KB 总预算均有边界 |
| 权限 | `browser_close` 为 L1；navigate/snapshot/wait/tabs 为 L2；Broker 返回最终 effective level，不再与 server 级别矛盾 |
| 状态 | `mcp-servers.json` 仍全部 disabled；未接 Electron、未弹浏览器、未开始 MCP-06 |

## MCP-05 策略扩展（2026-07-03，accounts_sync click 开放）

**变更原因**：创作者中心数据采集需要点击「导出数据」按钮和切换分析 tab（总览/流量分析/观众分析/评论热词），参考 TzFilm-Douyin-Tool 和 autody 开源方案。

**变更内容**：
- `browser_click` 的 capability 白名单新增 `marketing_accounts_sync`
- 新增 `_ACCOUNT_SYNC_CLICK_LABELS` element 白名单：投稿列表、内容管理、作品管理、总览、流量分析、观众分析、评论热词、导出数据、导出、下载、粉丝数据、作品数据、直播数据、互动数据、下一页、上一页
- 仍保持：仅左键单击、禁双击/修饰键、target 必须是 snapshot ref

**未变更**：
- 永久禁用列表不变（`browser_run_code_unsafe`、`file_upload`、`cookie`、`storage`、`network` 等仍禁）
- navigate/snapshot/wait/tabs 的参数约束不变
- 输出脱敏和 256KB 预算不变

### browser_evaluate 条件开放（2026-07-03）

**变更原因**：创作者中心数据采集需要执行页面内 JS 来读取动态加载的图表数据、调用页面内部 API（参考 MediaCrawler 方案），以及后续视频模块衔接。

**变更内容**：
- `browser_evaluate` 从 `PERMANENTLY_DENIED_TOOLS` 移除
- 仅允许 `marketing_accounts_sync` capability（trending_search 和 session_login 仍禁）
- 要求 `approved=True`（L3 CONTROLLED_RESOURCE）
- script 参数：必须为字符串、非空、≤50KB、无控制字符（允许换行和 Tab）
- 输出仍走递归脱敏（Cookie/Token/Authorization/Secret 等自动脱敏）
- `browser_run_code_unsafe` 仍永久禁用（不受此变更影响）
