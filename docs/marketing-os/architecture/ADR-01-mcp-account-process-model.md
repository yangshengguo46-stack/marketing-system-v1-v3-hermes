# ADR-01：账号级 MCP 浏览器进程模型

> 状态：已接受 | 日期：2026-07-01（v2，已按本地 `@playwright/mcp@0.0.77` CLI 复核）
> MCP-01 冻结交付物；后续实现偏离本 ADR 时必须先新增 superseding ADR

## 一、决策摘要

每个 `(platform, account_id)` 拥有独立的 Playwright MCP 进程和持久 `--user-data-dir`。首次登录时 Playwright 直接启动独立 headed Chromium 窗口；后续复用同一 profile 以 `--headless` 模式运行。同平台多账号绝不共享进程、profile、Cookie、目录或结果缓存。

## 二、已通过本地 CLI 核验的参数（v0.0.77）

以下参数来自 `./node_modules/.bin/playwright-mcp --help`（2026-07-01），版本 `@playwright/mcp@0.0.77`：

| 参数 | 存在 | 本 ADR 使用 | 备注 |
|---|---|---|---|
| `--headless` | ✅ | ✅ 后台模式 | 不带 `--headless` 默认 headed |
| `--user-data-dir <path>` | ✅ | ✅ 每账号独立目录 | 持久 profile |
| `--browser <browser>` | ✅ | ❌ 不传 | 接受默认（chromium）；有效值：`chrome, firefox, webkit, msedge`（无 `chromium` 字符串） |
| `--headed` | ❌ **不存在** | ❌ | 不带 `--headless` 即 headed；不可运行时切换 |
| `--tools <list>` | ❌ **不存在** | ❌ | CLI 无工具白名单参数；工具管控由 `ProductMCPBroker` 负责 |
| `--isolated` | ✅ | ❌ 不传 | 持久 profile 必须落盘 |
| `--port <port>` | ✅ | ❌ | 使用 stdio（不启用 SSE/HTTP） |
| `--save-session` | ✅ | ❌ 禁用 | 机制保留但产品禁止 |
| `--storage-state <path>` | ✅ | ❌ 禁用 | 机制保留但产品禁止 |
| `--cdp-endpoint <endpoint>` | ✅ | ❌ 禁用 | 禁止连接外部 CDP |
| `--extension` | ✅ | ❌ 禁用 | 禁止连接外部浏览器 |
| `--caps <caps>` | ✅ | ❌ 禁用 | devtools 禁止 |
| `--executable-path <path>` | ✅ | 可选 | 指向构建期准备的浏览器二进制 |

### 从 `@playwright/mcp` README 确认的工具全集（`tools/list` 返回 55+ 工具）

章节六定义产品 allowlist 与 Broker 隐藏规则。

## 三、实例键与身份

### 3.1 唯一实例键

| 字段 | 来源 | 示例 |
|---|---|---|
| `platform` | 小写平台名，来自 `mcp-servers.json` role 路由 | `douyin` |
| `account_id` | Electron 在打开登录窗口**之前**生成，经 `accounts.json` 持久化 | `acct_a1b2c3d4` |

全局限定实例键：`{platform}:{account_id}`。同 platform 下不同 account_id 互不可见，无默认或 fallback 实例。

### 3.2 account_id 生命周期

1. **预生成**：`openLoginBrowserAndWait` 调用**前** Electron 生成 `acct_{hex12}`，向 Python 后端预先注册 `(platform, account_id, status=pending)`。
2. **确认**：登录成功后 Electron 将 `status` 更新为 `connected`；取消/超时/失败后不删除 account_id，标记 `disconnected` 供重试。
3. **重登**：复用同一 account_id，以新 headed 进程用同一 `user-data-dir` 重新认证；保留历史元数据，覆盖旧认证。
4. **删除**：先 `stop()` 进程→用户确认→按用户选择清理 profile 目录→删除 `accounts.json` 记录。profile 目录**不**自动删除，只按用户明确指令操作。

## 四、进程模型

### 4.1 每账号一个 MCP 进程

```
{platform}:{account_id}
  └─ Playwright MCP Server (stdio JSON-RPC, node_modules/.bin/playwright-mcp)
       └─ Playwright Browser Server
            └─ Browser (headed 或 headless)
```

- 启动入口固定为本地已安装的 `node_modules/.bin/playwright-mcp`。禁止 `npx`、`latest` 和运行时下载。
- 每个实例一个操作系统子进程，通过 stdio JSON-RPC 与 Python 后端通信。
- 禁止 MCP 进程间互相连接或共享 CDP endpoint。
- 禁止将 Playwright MCP 连接到全局 Electron `BrowserWindow` 或 session。

### 4.2 目录隔离

| 用途 | 路径 |
|---|---|
| 每账号 browser profile | `{userData}/mcp-browser/{platform}/{account_id}/` |
| 锁文件与运行时 PID 元数据 | `{userData}/mcp-runtime/locks/{platform}/{account_id}.lock` |
| 滚动日志 | `{userData}/mcp-runtime/logs/{platform}/{account_id}.log` |

- 路径构造时拒绝 `..`、`/` 开头、符号链接跟随；启动前校验落点必须在规定根目录内。
- 锁文件和 PID 元数据**不与** Chromium profile 混在同一目录。

### 4.3 进程启动命令

```bash
node_modules/.bin/playwright-mcp \
  --user-data-dir <{userData}/mcp-browser/{platform}/{account_id}> \
  --headless \
  --timeout-action 10000 \
  --timeout-navigation 30000
```

- `--headless`：后台模式。不带此参数时默认 headed（用于首次登录和登录交互）。
- `--timeout-action` / `--timeout-navigation`：按平台调整。
- 浏览器二进制必须在构建/安装阶段预先准备；运行时缺失应 **fail closed**（进程启动失败→absent），不得触发下载。

### 4.4 headed ↔ headless 模式切换

- **不带** `--headless` 时 Playwright MCP 启动 headed 浏览器窗口。
- **带** `--headless` 时 Playwright MCP 以 headless 模式运行。
- **运行中的进程不能原地切换模式**。模式变化必须 `stop()` 后以同一 `--user-data-dir` 和相反 `--headless` 标志重新 `start()`。

## 五、状态机

每实例状态：

```
                start(headless=True/False)
  absent ──────────────────────────────→ starting
    ↑                                        │
    │ crash / kill                           ↓ MCP initialize 成功 + tools/list 成功
    │                                  ┌─ healthy ──────────────┐
    │                                  │    │                    │
    │                    health check fails  │  restart_mode(h)  │
    │                                  │    │  (= stop + start  │
    │                                  ↓    │   with same dir,  │
    │                               degraded─→  different --headless)
    │                                  │
    │                           unrecoverable
    │                           (all retries exhausted)
    │                                  │
    └──────────────────────────────────┘
                                       │
                                  stopping ──→ absent
                                       ↑
                                stop() / idle timeout / app quit
```

转换触发：

| 转换 | 触发 | 说明 |
|---|---|---|
| absent→starting | `start(platform, account_id, headless)` | 分配目录、校验路径、启动 `node_modules/.bin/playwright-mcp` |
| starting→healthy | `initialize` 成功 + `tools/list` 成功 + 产品所需工具均在返回值中 | 连续 3 次检查通过 |
| starting→degraded | 超时(30s)、进程退出、或产品所需工具缺失 | 自动 retry，最多 3 次 |
| healthy→degraded | 连续 2 次健康检查失败或进程退出 | 自动 restart() |
| healthy→healthy | `restart_mode(headless)` | stop + 以反转的 `--headless` 重 start |
| degraded→starting | 自动 retry | 最多 3 次后→absent |
| *→stopping | `stop()` / idle 超时 / app quit | 进程终止→锁释放 |
| stopping→absent | 进程终止确认 | 元数据清理 |

## 六、健康检查

- **步骤**：①进程存活 ②MCP `initialize` 成功 ③`tools/list` 成功 ④产品 allowlist 中工具均在返回值中。
- **额外工具**：`tools/list` 返回的官方工具超出产品 allowlist 的，由 `ProductMCPBroker` 隐藏（不注册到 Hermes tool registry），**不**构成健康失败。
- **频率**：healthy 状态每 30s；degraded 状态每 5s。
- **降级**：连续 2 次失败→degraded；degraded 持续 60s 无恢复→absent。

## 七、并发、锁与残留进程

### 7.1 锁文件

锁文件放在独立 runtime 目录：`{userData}/mcp-runtime/locks/{platform}/{account_id}.lock`。

- 启动前获取排他文件锁（`fcntl.flock` / Windows `msvcrt.locking` / 跨平台抽象）。
- 锁持有整个进程生命周期。写入当前 PID 和时间戳元数据。
- 同 `(platform, account_id)` 的重复 `start()` 检测到锁→返回已有实例（幂等）。
- 进程崩溃后 OS 自动释放锁；Manager 启动时扫描残留锁文件，对 PID 不存活者清理。

### 7.2 残留进程回收

- Manager 启动时扫描 `mcp-runtime/locks/`，检查 PID 存活→存活者保留锁；不存活者清理锁+元数据。
- `stop_all()` 按依赖顺序：先对所有实例 `terminate()`→等待 grace_period(5s)→`kill()`→等待 2s→强制清理锁。
- App 退出调用 `stop_all()` 同步等待。

### 7.3 进程终止（跨平台抽象）

Manager 暴露统一接口，内部根据 `sys.platform` 选择实现：

| 接口 | POSIX | Windows |
|---|---|---|
| `terminate(pid)` | `SIGTERM` | `TerminateProcess` (非强制) |
| `kill(pid)` | `SIGKILL` | `TerminateProcess` (强制) |
| `is_alive(pid)` | `kill(pid, 0)` | `WaitForSingleObject(0ms)` |

调用方只使用 `terminate()` / `kill()` / `is_alive()`，不直接依赖信号。

### 7.4 并发上限

- 默认**同平台最多 3 个**、**全局最多 6 个** MCP 子进程（可配置）。
- 超出上限时 `start()` 调用排队，最先空闲时启动。

## 八、空闲回收

- **headless 模式**：最后工具调用后 10 分钟无活动→`stop()`。
- **headed 模式**：最后交互后 30 分钟无活动→`stop()`。
- 可配置 `MCP_IDLE_TIMEOUT_MINUTES`（0 禁用）。
- `--user-data-dir` 持久 profile 由 Chromium 自行管理，停止前**不**做显式 storage state 保存（无需恢复步骤）。

## 九、停止、App 退出、升级与 profile 管理

### 9.1 单实例停止

1. `terminate(pid)`，等待最多 5s。
2. 超时后 `kill(pid)`，等待 2s。
3. 关闭子进程 stdio pipe。
4. 释放 `.lock` 文件。
5. 状态→absent。

### 9.2 App 退出

1. Electron `before-quit` → IPC `mcp:prepare-shutdown` → Python `stop_all(timeout=30)`。
2. 所有实例按 headed→stopping→absent 顺序关闭。
3. 总超时 30s；超时后强制终止所有子进程 + 清理锁。

### 9.3 升级迁移

- `@playwright/mcp@0.0.77` 版本升级需变更 `package.json` lockfile，经复核后统一更新 `mcp-servers.json` 的 `source.package` 和 `source.sha256`。
- 浏览器二进制（Chromium）在构建/安装阶段通过 `npx playwright install chromium` 准备，打包进桌面应用资源目录。运行时使用 `--executable-path` 指向固定路径。**运行时禁止触发下载**，依赖缺失 fail closed。
- `user-data-dir` 的 Chromium profile 格式跨小版本兼容。不兼容时由构建阶段校验，不留给运行时。

### 9.4 Profile 生命周期

- `user-data-dir` 下的 Chromium profile 持久保留。
- **禁止自动删除**旧 profile。Profile 只在以下情况清理：
  - 用户在账号管理中明确执行"退出并清理"。
  - 用户删除账号并选择"同时删除浏览器数据"。
  - 用户卸载应用并选择完全清理。
- 升级前备份和失败回滚路径另行设计（不在本 ADR 内定义）。

## 十、Cookie、认证与秘密边界

### 10.1 Cookie 边界

- Cookie 和认证数据**只存在**账号专属 Playwright profile（`--user-data-dir`）中。
- Python 后端**不读取、不接收、不返回**任何 Cookie 值。
- Python `AccountScopedMCPManager` 管理进程生命周期和接收脱敏页面结果，但绝不访问 profile 内的认证数据。
- 目标架构中，`login:cookies` IPC 不再是登录状态的主通道。

### 10.2 登录成功判断

登录成功**不**依赖把 Cookie 传给 Python。平台适配器根据以下程序化信号判断：

1. 导航到平台已登录状态页面（如 `https://www.douyin.com/creator/content`），检查页面是否展示已登录 UI（非登录页/非二维码页）。
2. `browser_snapshot` 中是否存在平台特定的已登录标识（如用户头像链接、昵称元素、发布按钮）。
3. 导航未跳转到登录页。

具体平台适配规则留给 MCP-07 定义；本 ADR 只规定"不能依赖 Python 读取 Cookie"。

### 10.3 Profile 访问禁令

- Manager **禁止**读取、复制、导出或遍历 Chromium profile 目录内的任何文件。
- `browser_storage_state`、`browser_cookie_get`、`browser_cookie_list`、`browser_cookie_set`、`browser_set_storage_state` 等工具**永久禁止**注册到 Hermes tool registry（不在产品 allowlist 中）。
- 禁止通过 `--storage-state <path>` 导出/导入认证状态。

### 10.4 日志与 trace

- MCP 进程 stderr→滚动日志：`{userData}/mcp-runtime/logs/{platform}/{account_id}.log`。
- 保留 7 天，最大 10MB/文件，最多 3 个滚动文件。
- `MARKETING_OS_MCP_TRACE=1` 显式启用 Playwright trace；默认关闭。
- 日志写入前过滤手机号、身份证号、私信内容、Cookie header。

## 十一、工具暴露与 allowlist

### 11.1 CLI 层

`playwright-mcp` CLI **没有**单工具白名单参数。`tools/list` 返回官方基础工具全集（55+ 工具）。

### 11.2 Broker 层

`ProductMCPBroker` 维护产品 allowlist。只有以下工具注册到 Hermes tool registry：

| 工具 | 用途 |
|---|---|
| `browser_navigate` | 页面导航 |
| `browser_snapshot` | 可访问性快照 |
| `browser_click` | 受控点击 |
| `browser_wait_for` | 等待文本/时间 |
| `browser_tabs` | 标签页管理（列出/创建/关闭/选择） |
| `browser_close` | 关闭页面 |

以下工具类别**永久禁止**注册：

| 类别 | 示例 | 原因 |
|---|---|---|
| JavaScript 执行 | `browser_evaluate`, `browser_run_code_unsafe` | RCE 等效 |
| Cookie 操作 | `browser_cookie_*`, `browser_set_storage_state`, `browser_storage_state` | 秘密边界 |
| Storage 操作 | `browser_localstorage_*`, `browser_sessionstorage_*` | 秘密边界 |
| 文件操作 | `browser_file_upload`, `browser_pdf_save` | 文件系统边界 |
| 网络拦截 | `browser_route`, `browser_network_*` | 流量操纵 |
| DevTools | `browser_start_tracing`, `--caps devtools` | 调试能力 |
| 截图/标注 | `browser_take_screenshot`, `browser_annotate` | 视觉路径 |
| 键盘/鼠标级别 | `browser_press_key`, `browser_mouse_*`, `browser_drag`, `browser_drop` | 误操作风险 |
| 表单/选中 | `browser_fill_form`, `browser_select_option`, `browser_type` | 暂不开放，后续按需评估 |
| 其他未列工具 | `browser_console_messages`, `browser_resize`, `browser_handle_dialog` 等 | 默认拒绝 |

### 11.3 工具发现验证（MCP-04 前置）

`tools/list` 返回的工具中，产品 allowlist 工具必须全部存在。缺少→health degraded。

## 十二、登录交互流程

### 12.1 首次登录

1. Electron 预生成 `account_id` → 注册到 `accounts.json`（status=pending）。
2. Electron 通过 IPC 请求 Python 后端 `AccountScopedMCPManager.start(platform, account_id, headless=False)`。
3. MCP 进程以**不带 `--headless`**（默认 headed）启动 Playwright Chromium。
4. Playwright 启动的 Chromium 窗口作为独立系统窗口直接展示给用户。Electron 不嵌入、不代理该窗口。
5. `browser_navigate` 到平台官方登录页。用户自行完成二维码扫描、短信验证或滑块验证。
6. 登录成功后 MCP-07 的平台适配器通过页面 UI 信号判断认证成功。
7. Electron 将 `accounts.json` 中该 account_id 的 `status` 更新为 `connected`。
8. 登录窗口自动关闭或由用户关闭。Profile 已持久保存在 `--user-data-dir` 中。

### 12.2 重新登录

1. 复用同一 account_id。
2. `start(platform, account_id, headless=False)` 使用同一 `user-data-dir`（继承旧 profile，可直接到已登录状态或需重新认证）。
3. 如需重新登录，适配器导航到登录页，用户完成认证。旧认证被覆盖。

### 12.3 取消/超时

- 用户关闭 Chromium 窗口→Electron 检测进程退出→标记 `disconnected`，保留 account_id。
- 超时（默认 120s）：`stop()`→`disconnected`。

## 十三、职责边界

### 13.1 Electron（`electron/`）

- 拥有：`accounts.json` CRUD、account_id 预生成、IPC 通信、App 生命周期、窗口管理。
- 迁移后：`openLoginBrowser` 改为向 Python 后端发 `start(headless=False)`，**不再**自己创建 `BrowserWindow` 管理登录页。Playwright headed Chromium 作为独立窗口直接展示。
- `executeApprovedCapability` 逐步改为经由 `ProductMCPBroker.call()` 路由（MCP-13 shadow 双跑期间保留旧路径）。

### 13.2 Python 后端（`engine/agent_core/` + `engine/marketing-os/`）

- `AccountScopedMCPManager`：拥有进程生命周期（start/stop/health/restart_mode）、崩溃恢复、空闲回收、并发控制、锁管理。
- `ProductMCPBroker`：拥有 MCP server/tool 注册、allowlist 执行、工具调用路由。
- `engine/marketing-os/server.py`：暴露 `/api/plugins/marketing-os/mcp/status`、内部 start/stop/health 端点。
- MCP tool 结果经 `tool_gateway._wrap_handler` 的 L0-L4 policy 和脱敏后返回 Agent。

### 13.3 MCP Broker（`engine/agent_core/mcp_broker.py`）

- 静态配置加载和验证（`load_mcp_manifest`）。
- Hermes tool registry 注册（`ProductMCPBroker.register`）：只注册 allowlist 工具，不注册额外工具。
- 单次工具调用路由（`ProductMCPBroker.call`）：经 `(platform, account_id)` 路由到正确进程→转发 JSON-RPC→返回结构化结果。

## 十四、AccountScopedMCPManager 接口契约

```python
class AccountScopedMCPManager:
    """Per-account MCP browser process lifecycle.

    Uses node_modules/.bin/playwright-mcp (pinned @0.0.77) via stdio.
    """

    def __init__(self, user_data_root: Path, broker: ProductMCPBroker, *,
                 max_per_platform: int = 3, max_total: int = 6,
                 idle_timeout_minutes: int = 10,
                 headed_idle_minutes: int = 30,
                 playwright_mcp_bin: Path | None = None):
        """playwright_mcp_bin defaults to <project>/node_modules/.bin/playwright-mcp."""

    # ── lifecycle ──

    async def start(self, platform: str, account_id: str, *,
                    headless: bool = True) -> dict[str, Any]:
        """幂等启动。返回 {status, pid, data_dir, headed, started_at}.

        若实例已存在返回已有元数据。headless=False 用于首次登录。
        """

    async def get(self, platform: str, account_id: str
                  ) -> dict[str, Any] | None:
        """实例元数据：{status, pid, data_dir, headless, started_at, last_active_at}."""

    async def health(self, platform: str, account_id: str
                     ) -> dict[str, bool]:
        """{process_alive, mcp_initialized, tools_ok, ready}."""

    async def stop(self, platform: str, account_id: str) -> bool:
        """幂等停止；terminate→timeout→kill。返回 True 表示已停止或已不存在。"""

    async def restart_mode(self, platform: str, account_id: str,
                           headless: bool) -> dict:
        """stop() + start(headless=headless)；同一 user-data-dir。

        用于登录（headless=False）和登录完成后切回后台（headless=True）。
        """

    # ── global ──

    async def stop_all(self, timeout: float = 30) -> dict[str, int]:
        """停止所有实例；返回 {stopped, failed} 计数。"""

    async def status_all(self) -> list[dict[str, Any]]:
        """所有活跃实例的状态列表。"""

    # ── internal ──

    async def _reap_stale_locks(self) -> None:
        """启动时扫描 mcp-runtime/locks/，清理僵尸 PID 的残留锁文件。"""

    async def _garbage_collect_idle(self) -> None:
        """后台定时器：回收达到空闲超时的实例。"""

    async def _crash_recovery(self, platform: str, account_id: str) -> None:
        """degraded→retry→absent 的自动恢复循环。"""
```

## 十五、数据流图（威胁模型）

```text
┌─────────────────────────────────────────────────┐
│ Electron                                         │
│  accounts.json                                  │
│  account_id 预生成                                │
│  App 生命周期 (before-quit→stop_all)              │
│  IPC: mcp:start/stop/status                      │
└────────────────────────┬────────────────────────┘
                         │ IPC (account_id, platform, headless)
                         │ 不传 Cookie
┌────────────────────────▼────────────────────────┐
│ Python Backend                                   │
│                                                  │
│  AccountScopedMCPManager                         │
│  per (platform, account_id):                     │
│  ├─ start/stop/health/restart_mode               │
│  ├─ idle GC / crash recovery                     │
│  └─ lock management (mcp-runtime/locks/)         │
│                                                  │
│  ProductMCPBroker                                │
│  ├─ allowlist → register only 6 tools            │
│  ├─ hide extra tools from tools/list             │
│  └─ call(server, tool, args) → route per account │
│                                                  │
│  Cookie boundary ──────────────── 不跨越此线      │
└────────────────────────┬────────────────────────┘
                         │ stdio JSON-RPC (only allowlisted tools)
┌────────────────────────▼────────────────────────┐
│ Playwright MCP Server (子进程)                    │
│ node_modules/.bin/playwright-mcp                │
│ --user-data-dir=<per-account>                    │
│ --headless (或默认 headed)                        │
│ PID + lock at mcp-runtime/locks/                 │
│ Log at mcp-runtime/logs/                         │
└────────────────────────┬────────────────────────┘
                         │ CDP (browser-internal)
┌────────────────────────▼────────────────────────┐
│ Chromium (headed / headless)                     │
│ Per-account profile at mcp-browser/{p}/{aid}/    │
│ Cookie/Storage 永远在 profile 内                  │
└─────────────────────────────────────────────────┘
```

**秘密边界**：Cookie/Token 永不跨越 Python↔MCP 的 stdio 线。Python 只接收脱敏页面快照和结构化结果。

## 十六、先决条件与未解决风险

### 16.1 MCP-01 交付后仍需后续 MCP 任务完成的条件

- [ ] MCP-02：`@playwright/mcp@0.0.77` lockfile hash + SBOM + 离线安装验证
- [ ] MCP-03：`AccountScopedMCPManager` 代码实现
- [ ] MCP-04：真实 `tools/list` 发现 + allowlist 回归测试
- [ ] MCP-05：工具权限分级（navigate/snapshot/click 分开）+ policy 测试
- [ ] MCP-06：Headed 登录真人验收（成功/取消/短信/滑块/超时）
- [ ] MCP-07：平台认证信号定义 + 失效重登验证
- [ ] MCP-09：双账号零串号真人验证
- [ ] MCP-10：进程/目录/DB 三方一致性测试

### 16.2 已知风险

1. **Chromium 内存**：每实例约 200-400MB；6 实例上限≈2.4GB。
2. **Headed Chromium 独立窗口**：非 Electron 内嵌，窗口管理（z-order/任务栏分组）依赖 OS。
3. **旧 Electron DOM 采集共存**：MCP-13 要求 shadow 双跑比较；新链稳定前不能删旧路径。
4. **跨平台 terminate/kill**：Windows `TerminateProcess` 语义与 POSIX `SIGTERM` 不完全等价；MCP-03 实现中需平台测试。
