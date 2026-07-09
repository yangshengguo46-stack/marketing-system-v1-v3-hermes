"""Account-scoped MCP browser process manager using the official MCP SDK.

Each instance runs inside a dedicated asyncio Task that holds
``stdio_client`` + ``ClientSession`` from open to close.  SDK
context-manager enter, initialize, list_tools, wait-for-stop, and
exit all happen in that single Task.
"""

from __future__ import annotations

import asyncio
import json
import os
import platform as _os_platform
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .mcp_broker import PLAYWRIGHT_MINIMAL_TOOLS

# ── cross-platform file locking ─────────────────────────────────────────────
if _os_platform.system() == "Windows":
    import msvcrt as _lock_mod
else:
    import fcntl as _lock_mod   # type: ignore[no-redef]

# ── SDK (optional — checked at start) ───────────────────────────────────────
try:
    from mcp import ClientSession, StdioServerParameters               # noqa: F401
    from mcp.client.stdio import stdio_client                          # noqa: F401
    _MCP_SDK = True
except ImportError:
    _MCP_SDK = False
    ClientSession = None          # type: ignore[assignment]
    StdioServerParameters = None  # type: ignore[assignment]
    stdio_client = None           # type: ignore[assignment]

# ── constants ────────────────────────────────────────────────────────────────

_PLATFORM_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_ACCOUNT_RE = re.compile(r"^acct_[a-f0-9]{6,32}$")

ALLOWED_TOOLS = PLAYWRIGHT_MINIMAL_TOOLS

DEFAULT_MAX_PER_PLATFORM = 3
DEFAULT_MAX_TOTAL = 6
START_TIMEOUT = 30.0
STOP_GRACE = 5.0
IDLE_HEADLESS = 600
IDLE_HEADED = 1800
CRASH_RETRY_MAX = 3
CRASH_RETRY_BASE = 0.5
CRASH_RETRY_MAX_DELAY = 10.0

# ── validation ───────────────────────────────────────────────────────────────

class MCPManagerError(ValueError):
    pass

def _validate_platform(v: str) -> str:
    v = (v or "").strip().lower()
    if not _PLATFORM_RE.match(v):
        raise MCPManagerError(f"invalid platform: {v!r}")
    return v

def _validate_account(v: str) -> str:
    v = (v or "").strip().lower()
    if not _ACCOUNT_RE.match(v):
        raise MCPManagerError(f"invalid account_id: {v!r}")
    return v

def _safe_subpath(root: Path, *segments: str) -> Path:
    candidate = root.resolve()
    for seg in segments:
        candidate = (candidate / seg).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            raise MCPManagerError(f"path escapes root: {seg!r}")
    return candidate

# ── instance data ────────────────────────────────────────────────────────────

@dataclass
class InstanceMeta:
    platform: str
    account_id: str
    pid: int | None = None
    status: str = "absent"
    headless: bool = True
    started_at: str | None = None
    last_active_at: str | None = None
    retry_count: int = 0
    tools: list[str] = field(default_factory=list)
    instance_token: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

@dataclass
class _InstanceHandle:
    meta: InstanceMeta
    task: asyncio.Task | None = None
    started: asyncio.Event = field(default_factory=asyncio.Event)
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    session: Any = None
    session_ready: bool = False
    lock_fh: Any = None
    stderr_fh: Any = None
    crash_count: int = 0
    exit_reason: str = ""  # "stop" | "idle" | "transport_error"
    _call_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

# ── manager ──────────────────────────────────────────────────────────────────

class AccountScopedMCPManager:
    """Per-account MCP browser lifecycle using the official MCP Python SDK."""

    def __init__(
        self, user_data_root: Path, *,
        playwright_mcp_bin: Path | None = None,
        max_per_platform: int = DEFAULT_MAX_PER_PLATFORM,
        max_total: int = DEFAULT_MAX_TOTAL,
        crash_max_retries: int = CRASH_RETRY_MAX,
        crash_retry_base: float = CRASH_RETRY_BASE,
        crash_retry_max_delay: float = CRASH_RETRY_MAX_DELAY,
        idle_headless: float = IDLE_HEADLESS,
        idle_headed: float = IDLE_HEADED,
        health_interval: float = 5.0,
    ):
        self._root = Path(user_data_root).resolve()
        env_cli = os.environ.get("MARKETING_OS_MCP_CLI")
        self._playwright_bin = Path(playwright_mcp_bin or env_cli) if (playwright_mcp_bin or env_cli) else self._default_bin()
        self._node_executable = Path(os.environ["MARKETING_OS_NODE_EXECUTABLE"]) if os.environ.get("MARKETING_OS_NODE_EXECUTABLE") else None
        self._browser_executable = Path(os.environ["MARKETING_OS_BROWSER_EXECUTABLE"]) if os.environ.get("MARKETING_OS_BROWSER_EXECUTABLE") else None
        self._max_per_platform = max_per_platform
        self._max_total = max_total
        self._crash_max = crash_max_retries
        self._crash_retry_base = crash_retry_base
        self._crash_retry_max_delay = crash_retry_max_delay
        self._idle_headless = idle_headless
        self._idle_headed = idle_headed
        self._health_interval = max(0.05, health_interval)
        self._handles: dict[str, _InstanceHandle] = {}
        self._start_lock = asyncio.Lock()
        self._reaped_locks = False

    @staticmethod
    def _default_bin() -> Path:
        project = Path(__file__).resolve().parents[2]
        return project / "node_modules" / ".bin" / "playwright-mcp"

    # ── public ───────────────────────────────────────────────────────────

    async def start(self, platform: str, account_id: str, *, headless: bool = True) -> dict[str, Any]:
        platform = _validate_platform(platform)
        account_id = _validate_account(account_id)
        key = f"{platform}:{account_id}"

        if not _MCP_SDK:
            return {"status": "error", "reason": "mcp_sdk_unavailable", "key": key}

        if not self._bin_ok():
            return {"status": "error", "reason": "playwright-mcp CLI missing or not executable", "key": key}

        async with self._start_lock:
            if not self._reaped_locks:
                self._reap_stale_locks()
                self._reaped_locks = True
            existing = self._handles.get(key)
            if existing is not None and existing.meta.status in ("starting", "healthy", "degraded"):
                waiter = existing
            else:
                active = [h for h in self._handles.values()
                          if h.meta.status in ("starting", "healthy", "degraded")]
                if len(active) >= self._max_total:
                    return {"status": "busy", "reason": "max_total", "key": key}
                platform_active = sum(h.meta.platform == platform for h in active)
                if platform_active >= self._max_per_platform:
                    return {"status": "busy", "reason": "max_per_platform", "key": key}

                data_dir = self._data_dir(platform, account_id)
                data_dir.mkdir(parents=True, exist_ok=True)
                self._lock_dir(platform, account_id).mkdir(parents=True, exist_ok=True)
                self._log_dir(platform, account_id).mkdir(parents=True, exist_ok=True)
                lock_fh = self._try_lock(platform, account_id)
                if lock_fh is None:
                    return {"status": "error", "reason": "lock_held", "key": key}
                try:
                    stderr_fh = open(self._log_dir(platform, account_id) / "stderr.log",
                                     "a", encoding="utf-8", errors="replace")
                except Exception:
                    self._close_fh(lock_fh)
                    raise
                meta = InstanceMeta(platform=platform, account_id=account_id,
                                    status="starting", headless=headless,
                                    started_at=datetime.now(timezone.utc).isoformat(),
                                    last_active_at=datetime.now(timezone.utc).isoformat())
                waiter = _InstanceHandle(meta=meta, lock_fh=lock_fh, stderr_fh=stderr_fh)
                self._handles[key] = waiter
                waiter.task = asyncio.create_task(self._lifecycle(key, waiter),
                                                  name=f"mcp:{key}")

        try:
            await asyncio.wait_for(waiter.started.wait(), timeout=START_TIMEOUT)
        except asyncio.TimeoutError:
            waiter.meta.status = "degraded"
        return self._to_dict(waiter.meta)

    async def get(self, platform: str, account_id: str) -> dict[str, Any] | None:
        h = self._handles.get(f"{_validate_platform(platform)}:{_validate_account(account_id)}")
        return self._to_dict(h.meta) if h else None

    async def health(self, platform: str, account_id: str) -> dict[str, bool]:
        h = self._handles.get(f"{_validate_platform(platform)}:{_validate_account(account_id)}")
        if h is None:
            return {"process_alive": False, "session_ready": False, "tools_ok": False, "ready": False}
        task_alive = h.task is not None and not h.task.done()
        session_ok = h.session_ready and h.session is not None and task_alive
        tools_ok = bool(h.meta.tools) and all(t in h.meta.tools for t in ALLOWED_TOOLS)
        return {"process_alive": task_alive, "session_ready": session_ok,
                "tools_ok": tools_ok, "ready": task_alive and session_ok and tools_ok}

    async def stop(self, platform: str, account_id: str) -> bool:
        key = f"{_validate_platform(platform)}:{_validate_account(account_id)}"
        h = self._handles.get(key)
        if h is None:
            return True
        h.meta.status = "stopping"
        h.exit_reason = "stop"
        h.stop.set()
        await self._wait_done(h)
        if self._handles.get(key) is h:
            self._handles.pop(key, None)
        return True

    async def restart_mode(self, platform: str, account_id: str, headless: bool) -> dict[str, Any]:
        await self.stop(platform, account_id)
        return await self.start(platform, account_id, headless=headless)

    async def ensure_mode(self, platform: str, account_id: str, *, headless: bool) -> dict[str, Any]:
        """Reuse a healthy matching instance or restart the same profile in-place."""
        existing = await self.get(platform, account_id)
        if existing and existing.get("status") in ("starting", "healthy", "degraded"):
            if existing.get("headless") == headless:
                return existing
            return await self.restart_mode(platform, account_id, headless=headless)
        return await self.start(platform, account_id, headless=headless)

    async def stop_all(self, timeout: float = 30) -> dict[str, int]:
        if not self._handles:
            return {"stopped": 0, "failed": 0}
        items = list(self._handles.items())
        handles = []
        for _, h in items:
            h.meta.status = "stopping"
            h.exit_reason = "stop"
            h.stop.set()
            handles.append(h)

        async def _one(h: _InstanceHandle) -> bool:
            try:
                await self._wait_done(h)
                return True
            except Exception:
                return False

        try:
            outcomes = await asyncio.wait_for(
                asyncio.gather(*(_one(h) for h in handles)), timeout=timeout)
        except asyncio.TimeoutError:
            outcomes = [False] * len(handles)
            for h in handles:
                if h.task is not None and not h.task.done():
                    h.task.cancel()
            await asyncio.gather(*(h.task for h in handles if h.task is not None),
                                 return_exceptions=True)
            await asyncio.gather(*(self._final_cleanup(h) for h in handles),
                                 return_exceptions=True)
        for key, h in items:
            if self._handles.get(key) is h:
                self._handles.pop(key, None)
        return {"stopped": sum(1 for o in outcomes if o), "failed": sum(1 for o in outcomes if not o)}

    async def status_all(self) -> list[dict[str, Any]]:
        return [self._to_dict(h.meta) for h in self._handles.values()]

    # ── account-scoped tool call ─────────────────────────────────────────

    async def call_tool(
        self, platform: str, account_id: str, tool_name: str, arguments: dict[str, Any],
        *, timeout: float = 30,
    ) -> dict[str, Any]:
        """Route a browser tool call to this account's MCP session.

        Uses ``ClientSession.call_tool`` — never Hermes register/dispatch.
        Serialized per instance via an internal lock.
        """
        key = f"{_validate_platform(platform)}:{_validate_account(account_id)}"
        h = self._handles.get(key)
        if h is None:
            return {"status": "error", "reason": "no_instance", "key": key}
        if not h.started.is_set() or h.meta.status != "healthy":
            return {"status": "error", "reason": "instance_not_healthy", "key": key}
        if h.task is None or h.task.done():
            return {"status": "error", "reason": "lifecycle_task_dead", "key": key}
        session = h.session
        if session is None:
            return {"status": "error", "reason": "no_mcp_session", "key": key}
        if tool_name not in h.meta.tools:
            return {"status": "error", "reason": f"tool {tool_name!r} not discovered", "key": key}
        if tool_name not in ALLOWED_TOOLS:
            return {"status": "error", "reason": f"tool {tool_name!r} not in product allowlist", "key": key}

        async with h._call_lock:
            try:
                result = await asyncio.wait_for(
                    session.call_tool(tool_name, arguments),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                return {"status": "error", "reason": "call_timeout", "key": key}
            except Exception as e:
                return {"status": "error", "reason": _sanitize_error(str(e)), "key": key}

        h.meta.last_active_at = datetime.now(timezone.utc).isoformat()
        content = []
        for c in getattr(result, "content", []) or []:
            d = getattr(c, "text", None)
            if d is not None:
                content.append({"type": "text", "text": str(d)[:50000]})
        return {"status": "ok", "content": content, "tool": tool_name}

    # ── lifecycle Task ───────────────────────────────────────────────────

    async def _lifecycle(self, key: str, h: _InstanceHandle) -> None:
        meta = h.meta
        while not h.stop.is_set():
            try:
                await self._run_transport(key, h)
            except asyncio.CancelledError:
                h.exit_reason = h.exit_reason or "stop"
                break
            except Exception:
                h.exit_reason = "transport_error"
                h.session = None
                h.session_ready = False
                meta.status = "degraded"
                h.started.set()

            if h.exit_reason == "transport_error" and h.crash_count < self._crash_max and not h.stop.is_set():
                h.crash_count += 1
                meta.retry_count = h.crash_count
                delay = min(self._crash_retry_base * (2 ** (h.crash_count - 1)),
                            self._crash_retry_max_delay)
                await asyncio.sleep(delay)
                meta.status = "starting"
                continue
            break

        if h.exit_reason in ("stop", "idle") or h.stop.is_set():
            meta.status = "absent"
        elif h.exit_reason == "transport_error":
            meta.status = "degraded"
        await self._final_cleanup(h)
        if self._handles.get(key) is h:
            self._handles.pop(key, None)

    async def _run_transport(self, key: str, h: _InstanceHandle) -> None:
        meta = h.meta
        cli = str(self._playwright_bin.resolve())
        command = str(self._node_executable.resolve()) if self._node_executable else cli
        args = ([cli] if self._node_executable else []) + [
                "--user-data-dir", str(self._data_dir(meta.platform, meta.account_id)),
                "--timeout-action", "10000", "--timeout-navigation", "30000"]
        if self._browser_executable:
            args.extend(["--executable-path", str(self._browser_executable.resolve())])
        if meta.headless:
            args.append("--headless")

        child_env = {**os.environ, "NODE_OPTIONS": ""}
        if self._node_executable:
            child_env["ELECTRON_RUN_AS_NODE"] = "1"
        server_params = StdioServerParameters(command=command, args=args, env=child_env)

        async with stdio_client(server_params, errlog=h.stderr_fh) as (read, write):
            async with ClientSession(read, write) as session:
                init = await asyncio.wait_for(session.initialize(), timeout=15)
                _ = init
                tools_resp = await asyncio.wait_for(session.list_tools(), timeout=10)
                meta.tools = [t.name for t in tools_resp.tools]
                meta.status = "healthy"
                h.session = session
                h.session_ready = True
                h.started.set()

                idle_sec = self._idle_headless if meta.headless else self._idle_headed
                deadline = asyncio.get_running_loop().time() + idle_sec
                while not h.stop.is_set():
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        h.exit_reason = "idle"
                        return
                    try:
                        await asyncio.wait_for(h.stop.wait(),
                                               timeout=min(self._health_interval, remaining))
                    except asyncio.TimeoutError:
                        # Ping makes transport death observable while no tool call is active.
                        await session.send_ping()
                h.exit_reason = "stop"
        h.session = None
        h.session_ready = False

    async def _wait_done(self, h: _InstanceHandle) -> None:
        if h.task is None:
            return
        if h.task.done():
            return
        try:
            await asyncio.wait_for(asyncio.shield(h.task), timeout=STOP_GRACE)
        except asyncio.TimeoutError:
            h.task.cancel()
            try:
                await asyncio.wait_for(h.task, timeout=2)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        except asyncio.CancelledError:
            pass

    async def _final_cleanup(self, h: _InstanceHandle) -> None:
        h.started.set()
        h.session = None
        h.session_ready = False
        lock_path = self._lock_path(h.meta.platform, h.meta.account_id)
        self._close_fh(h.lock_fh)
        h.lock_fh = None
        self._close_fh(h.stderr_fh)
        h.stderr_fh = None
        try:
            self._unlink_if_unlocked(lock_path)
        except OSError:
            pass

    # ── file locking ─────────────────────────────────────────────────────

    def _try_lock(self, platform: str, account_id: str):
        lp = self._lock_path(platform, account_id)
        fh = None
        try:
            fh = open(lp, "w")
            if _os_platform.system() == "Windows":
                fh.write("0")
                fh.flush()
                fh.seek(0)
                _lock_mod.locking(fh.fileno(), _lock_mod.LK_NBLCK, 1)
            else:
                _lock_mod.flock(fh.fileno(), _lock_mod.LOCK_EX | _lock_mod.LOCK_NB)
            fh.seek(0)
            fh.truncate()
            json.dump({"instance_token": uuid.uuid4().hex[:8],
                        "manager_pid": os.getpid(), "key": f"{platform}:{account_id}",
                        "started_at": datetime.now(timezone.utc).isoformat()}, fh)
            fh.flush()
            return fh
        except (IOError, OSError):
            self._close_fh(fh)
            return None

    def _reap_stale_locks(self) -> None:
        locks_root = self._lock_dir_root()
        if not locks_root.exists():
            return
        for lock_file in list(locks_root.rglob("*.lock")):
            try:
                fh = open(lock_file, "r+")
                if _os_platform.system() == "Windows":
                    _lock_mod.locking(fh.fileno(), _lock_mod.LK_NBLCK, 1)
                else:
                    _lock_mod.flock(fh.fileno(), _lock_mod.LOCK_EX | _lock_mod.LOCK_NB)
                # got the lock → old holder is gone → clean up
                fh.close()
                lock_file.unlink()
            except (IOError, OSError):
                # can't get lock → still held → skip
                try:
                    fh.close()
                except Exception:
                    pass

    def _unlink_if_unlocked(self, lock_file: Path) -> None:
        """Delete only a lock file that is not owned by another instance."""
        if not lock_file.exists():
            return
        fh = open(lock_file, "r+")
        try:
            if _os_platform.system() == "Windows":
                fh.seek(0)
                _lock_mod.locking(fh.fileno(), _lock_mod.LK_NBLCK, 1)
            else:
                _lock_mod.flock(fh.fileno(), _lock_mod.LOCK_EX | _lock_mod.LOCK_NB)
            lock_file.unlink(missing_ok=True)
        except (IOError, OSError):
            return
        finally:
            fh.close()

    # ── helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _close_fh(fh: Any) -> None:
        if fh is None:
            return
        try:
            fh.close()
        except Exception:
            pass

    @staticmethod
    def _is_process_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, OSError):
            return False

    def _bin_ok(self) -> bool:
        p = self._playwright_bin
        cli_ok = p.exists() and p.is_file() and (
            self._node_executable is not None or os.access(str(p), os.X_OK)
        )
        if not cli_ok:
            return False
        if self._node_executable is None:
            node_ok = True
        else:
            node = self._node_executable
            node_ok = node.exists() and node.is_file() and os.access(str(node), os.X_OK)
        if not node_ok:
            return False
        if self._browser_executable is None:
            return True
        browser = self._browser_executable
        return browser.exists() and browser.is_file() and os.access(str(browser), os.X_OK)

    # ── paths ────────────────────────────────────────────────────────────

    def _data_dir(self, platform: str, account_id: str) -> Path:
        return _safe_subpath(self._root, "mcp-browser", platform, account_id)

    def _lock_dir(self, platform: str, account_id: str) -> Path:
        return _safe_subpath(self._root, "mcp-runtime", "locks", platform, account_id)

    def _log_dir(self, platform: str, account_id: str) -> Path:
        return _safe_subpath(self._root, "mcp-runtime", "logs", platform, account_id)

    def _lock_path(self, platform: str, account_id: str) -> Path:
        return self._lock_dir(platform, account_id) / "instance.lock"

    def _lock_dir_root(self) -> Path:
        return self._root / "mcp-runtime" / "locks"

    def _to_dict(self, meta: InstanceMeta) -> dict[str, Any]:
        return {
            "key": f"{meta.platform}:{meta.account_id}",
            "platform": meta.platform, "account_id": meta.account_id,
            "pid": meta.pid, "status": meta.status, "headless": meta.headless,
            "started_at": meta.started_at, "last_active_at": meta.last_active_at,
            "retry_count": meta.retry_count, "tools": meta.tools,
            "instance_token": meta.instance_token,
        }


def _sanitize_error(msg: str) -> str:
    """Truncate errors before they cross the local API boundary."""
    return msg[:500]
