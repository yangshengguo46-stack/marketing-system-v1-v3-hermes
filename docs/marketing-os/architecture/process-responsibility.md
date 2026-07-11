# DESK-01: Process Responsibility Diagram

> Architecture diagram and lifecycle specification for all processes in marketing-os-desktop.
> Verified against health endpoints and source code on 2026-07-02.

## Process Topology

```
┌─────────────────────────────────────────────────────────────┐
│                    Electron Main Process                     │
│  (electron/main.js — PID: main)                             │
│                                                             │
│  Responsibilities:                                          │
│  • Window management (mainWindow, loginWindows)             │
│  • Tray icon and menu                                       │
│  • API token generation & persistence (0o600)               │
│  • IPC allowlist enforcement (renderer ↔ backend)           │
│  • Backend process lifecycle (spawn, monitor, restart)      │
│  • Channel bridge (optional WeChat/Feishu)                  │
│  • Trend refresh & intelligence schedulers                  │
│                                                             │
│  Token: userData/secrets/api-token (random 32 bytes hex)    │
│  Port: 19519 (auto-migrate +1 if occupied, up to 19569)     │
└──────────┬──────────────┬──────────────────┬────────────────┘
           │              │                  │
           │ spawn        │ spawn            │ load URL
           ▼              ▼                  ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────┐
│  Backend Server  │ │  Channel Bridge │ │   Renderer Process   │
│  (Python/uvicorn)│ │  (Python)       │ │   (Chromium/Blinken) │
│                  │ │                 │ │                     │
│  server.py       │ │  channel_       │ │  Vite dev server     │
│  FastAPI         │ │  bridge.py      │ │  (dev: :5173)        │
│  127.0.0.1:PORT  │ │                 │ │  or built dist/      │
│                  │ │  Optional,      │ │                     │
│  /health         │ │  per-channel    │ │  React UI            │
│  /api/*          │ │  subprocess     │ │  AgentPanel          │
│  /agent/*        │ │                 │ │  SSE event stream    │
│                  │ └─────────────────┘ └─────────────────────┘
│  ┌────────────┐ │
│  │ Agent Core │ │
│  │ (store.py) │ │
│  │ SQLite DB  │ │
│  └─────┬──────┘ │
│        │        │
│        │ thread │
│        ▼        │
│  ┌────────────┐ │
│  │  Hermes    │ │
│  │  Agent     │ │
│  │  Runtime   │ │
│  │ (threading)│ │
│  └────────────┘ │
│                  │
│  ┌────────────┐ │
│  │ MCP Manager│ │
│  │ (per-acct) │ │
│  └─────┬──────┘ │
│        │ spawn  │
│        ▼        │
│  ┌────────────┐ │
│  │ MCP CLI    │ │
│  │ (@play-    │ │
│  │  wright/   │ │
│  │  mcp)      │ │
│  │ + Chromium │ │
│  └────────────┘ │
└─────────────────┘
```

## Process Inventory

| Process | Binary | Lifecycle Owner | Port/IPC | Health Check |
|---------|--------|-----------------|----------|--------------|
| **Electron Main** | `electron` | OS (user launch) | N/A | `app.isReady()` |
| **Renderer** | Chromium (embedded) | Electron Main | Vite :5173 (dev) / dist/ (prod) | `webContents.on('did-finish-load')` |
| **Backend Server** | `marketing-os-server` (PyInstaller) or `python3 server.py` (dev) | Electron Main (spawn) | `127.0.0.1:19519` (auto-migrate) | `GET /health` → `{"status":"ok"}` |
| **Hermes Agent** | In-process thread | Backend Server | N/A (thread) | Task status in DB |
| **MCP CLI** | `@playwright/mcp` via Node | Backend MCP Manager (spawn) | stdio | `session.initialize()` + `list_tools()` |
| **Chromium** | Playwright bundled | MCP CLI (spawn) | CDP (internal) | MCP `session.send_ping()` |
| **Channel Bridge** | `channel_bridge.py` | Electron Main (spawn) | stdio | `getChannelStatus()` |

## Startup Sequence

```
1. Electron Main starts
   ├── loadOrCreateApiToken() → userData/secrets/api-token (0o600)
   ├── app.whenReady()
   │   ├── setupIPC()           — register IPC handlers
   │   ├── createWindow()       — load Vite :5173 or dist/index.html
   │   ├── setupTray()          — tray icon with menu
   │   ├── startServerWithRecovery()
   │   │   ├── findAvailablePort(19519)  — try 19519..19569
   │   │   ├── spawn backend (PyInstaller binary or python3)
   │   │   ├── waitForServer()  — poll GET /health (30 retries × 1s)
   │   │   └── setInterval(check, 5000)  — crash monitor
   │   ├── syncChannelDataDirectory()
   │   ├── setupIntelligenceScheduler()
   │   └── setupTrendRefreshScheduler()
   └── Backend starts
       ├── FastAPI lifespan
       ├── _ensure_config()      — create default config files
       ├── _get_agent_service()  — lazy init HermesAgentService
       │   ├── load provider env (secrets/providers.env)
       │   ├── AgentCoreStore(store_path)  — SQLite
       │   └── resume interrupted tasks → PAUSED
       └── uvicorn.listen(127.0.0.1, PORT)
```

## Shutdown Sequence

```
1. User quits (Cmd+Q / tray quit / window close)
   ├── app.isQuitting = true
   ├── clearInterval(intelligenceTimer)
   ├── clearInterval(trendRefreshTimer)
   ├── clearInterval(serverRestartTimer)
   └── stopServer()
       ├── Abort all SSE event streams (agentEventStreams)
       ├── serverProcess.kill('SIGTERM')
       ├── After 5s → SIGKILL if still alive
       └── Backend receives SIGTERM
           ├── FastAPI lifespan finally block
           ├── service.shutdown()       — stop Hermes agent threads
           ├── Cancel MCP login monitors
           ├── manager.stop_all(10s)    — stop all MCP browser instances
           └── uvicorn shutdown
```

## Crash Recovery

| Crash | Detection | Recovery |
|-------|-----------|----------|
| **Backend crash** | `serverProcess.on('exit')` + 5s interval check | Auto-restart after 3s delay; crash count tracked; UI notified via `runtime:status`（同时保留 `hermes:status` 兼容旧 UI） |
| **Hermes agent thread crash** | Exception in task thread | Task → FAILED; checkpoint preserved; user can resume |
| **MCP browser crash** | `session.send_ping()` timeout or transport error | Auto-retry up to `crash_max_retries` (3) with exponential backoff (2s base, 30s cap) |
| **Renderer crash** | `webContents.on('crashed')` | Electron shows crash dialog; user can reload |
| **Electron Main crash** | OS process exit | App terminates; backend child process orphaned (OS reaps) |

## Port Allocation

| Service | Default Port | Range | Binding |
|---------|-------------|-------|---------|
| Backend API | 19519 | 19519–19569 | 127.0.0.1 only |
| Vite dev server | 5173 | 5173 only | localhost |

## Token & Authentication

| Token | Storage | Scope | Generation |
|-------|---------|-------|------------|
| API token | `userData/secrets/api-token` (0o600) | All `/api/*` and `/agent/*` requests | `crypto.randomBytes(32).toString('hex')` on first launch |
| Provider API keys | `userData/secrets/providers.env.encrypted`（Electron `safeStorage`，macOS 由 Keychain 支持） | Backend process env | 首次读取旧明文后自动迁移并删除明文 |
| MCP instance token | In-memory only | Per MCP browser instance | `uuid4().hex` per start |

## IPC Allowlist

Renderer → Main IPC is restricted to `API_ALLOWLIST` (90+ entries in `electron/main.js`).
All API calls from renderer go through `runtimeApi → runtime:api → callLocalApi()` which attaches `X-Marketing-OS-Token` header.
The old `api → hermes:api` bridge remains only as a compatibility alias.
Non-localhost origins are rejected by backend middleware.

## Health Endpoints

| Endpoint | Method | Response | Used By |
|----------|--------|----------|---------|
| `/health` | GET | `{"status":"ok","timestamp":"..."}` | Electron `waitForServer()` |
| `/api/marketing-os/assistant/status` | GET | Agent service status | Network diagnostic |
| `/api/marketing-os/mcp/status` | GET | MCP broker config status | MCP status UI |

## Data Paths (macOS)

| Path | Contents |
|------|----------|
| `~/Library/Application Support/marketing-os-desktop/` | User data root |
| `…/config/` | JSON config files (accounts, trending, etc.) |
| `…/agent-runtime/agent_core.db` | Agent tasks, events, memory, approvals |
| `…/agent-runtime/hermes-state.db` | Hermes session state |
| `…/secrets/api-token` | API token (0o600) |
| `…/secrets/providers.env.encrypted` | Electron `safeStorage` 加密的 Provider API keys；旧 `providers.env` 首次启动后迁移删除 |
| `…/mcp-browser/{platform}/{account_id}/` | Per-account browser profile |
| `…/mcp-runtime/logs/{platform}/{account_id}/` | Per-account MCP logs |
| `…/mcp-runtime/locks/{platform}/{account_id}/` | Per-account instance locks |
