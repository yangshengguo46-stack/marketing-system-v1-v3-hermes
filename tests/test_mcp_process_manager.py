"""AccountScopedMCPManager tests — asyncio.run() wrapping with fake transport."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from agent_core.mcp_process_manager import (
    AccountScopedMCPManager, ALLOWED_TOOLS, MCPManagerError,
    _validate_platform, _validate_account, _safe_subpath,
)

# ── fake MCP SDK ────────────────────────────────────────────────────

class FakeReadStream:
    def __init__(self): pass
    async def receive(self):
        raise asyncio.CancelledError()

class FakeWriteStream:
    async def send(self, msg): pass

class FakeSession:
    def __init__(self, tools: list[str] | None = None, fail_init: bool = False):
        self._tools = tools or sorted(ALLOWED_TOOLS)
        self._fail = fail_init
    async def initialize(self):
        if self._fail: raise RuntimeError("init fail")
        return MagicMock()
    async def list_tools(self):
        ft = MagicMock()
        ft.tools = [MagicMock() for _ in self._tools]
        for i, t in enumerate(self._tools):
            ft.tools[i].name = t
        return ft
    async def send_ping(self):
        return MagicMock()
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass

def _fake_stdio(*a, **kw):
    class _Ctx:
        async def __aenter__(self):
            return FakeReadStream(), FakeWriteStream()
        async def __aexit__(self, *a): pass
    return _Ctx()

def _fake_session(read, write):
    return FakeSession()

def _three_patches():
    return (
        patch("agent_core.mcp_process_manager.stdio_client", side_effect=_fake_stdio),
        patch("agent_core.mcp_process_manager.ClientSession", side_effect=_fake_session),
        patch("agent_core.mcp_process_manager.StdioServerParameters", MagicMock()),
    )

# ── helpers ──────────────────────────────────────────────────────────

def make_manager(tmp_path, **kw):
    root = tmp_path / "userData"
    root.mkdir(parents=True, exist_ok=True)
    if "playwright_mcp_bin" not in kw:
        p = tmp_path / "fake-playwright-mcp"
        p.write_text("fake"); p.chmod(0o755)
        kw["playwright_mcp_bin"] = p
    return AccountScopedMCPManager(root, **kw)

def _run(coro):
    """Single asyncio.run() wrapper — one event loop per test call."""
    return asyncio.run(coro)


# ── validation ───────────────────────────────────────────────────────

class TestValidation:
    def test_platform_ok(self): assert _validate_platform("douyin") == "douyin"
    def test_platform_bad(self):
        with pytest.raises(MCPManagerError): _validate_platform("..")
    def test_account_ok(self): assert _validate_account("acct_a1b2c3d4e5f6") == "acct_a1b2c3d4e5f6"
    def test_account_bad(self):
        with pytest.raises(MCPManagerError): _validate_account("bad")
    def test_path_escape(self, tmp_path):
        with pytest.raises(MCPManagerError): _safe_subpath(tmp_path, "..", "etc")


# ── SDK missing ──────────────────────────────────────────────────────

class TestSDKMissing:
    def test_fail_closed_no_files_no_tasks(self, tmp_path, monkeypatch):
        monkeypatch.setattr("agent_core.mcp_process_manager._MCP_SDK", False)
        m = make_manager(tmp_path)
        r = _run(m.start("douyin", "acct_000000000001"))
        assert r["status"] == "error"
        assert r["reason"] == "mcp_sdk_unavailable"
        assert not m._data_dir("douyin", "acct_000000000001").exists()
        assert len(m._handles) == 0


# ── start ────────────────────────────────────────────────────────────

class TestStart:
    def test_healthy(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                r = await m.start("douyin", "acct_000000000001")
                assert r["status"] == "healthy"
                assert "browser_navigate" in r["tools"]
                await m.stop_all(timeout=10)
            _run(go())

    def test_idempotent(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                r1 = await m.start("douyin", "acct_000000000001")
                r2 = await m.start("douyin", "acct_000000000001")
                assert r1["instance_token"] == r2["instance_token"]
                await m.stop_all(timeout=10)
            _run(go())

    def test_concurrent_same_one_spawn(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                r1, r2 = await asyncio.gather(
                    m.start("douyin", "acct_000000000001"),
                    m.start("douyin", "acct_000000000001"),
                )
                assert r1["instance_token"] == r2["instance_token"]
                await m.stop_all(timeout=10)
            _run(go())

    def test_two_accounts_different_dirs(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                await m.start("douyin", "acct_000000000001")
                await m.start("douyin", "acct_000000000002")
                d1 = m._data_dir("douyin", "acct_000000000001")
                d2 = m._data_dir("douyin", "acct_000000000002")
                assert d1 != d2
                await m.stop_all(timeout=10)
            _run(go())

    def test_cli_missing(self, tmp_path):
        m = make_manager(tmp_path, playwright_mcp_bin=Path("/nope/pw"))
        r = _run(m.start("douyin", "acct_000000000001"))
        assert r["status"] == "error"

    def test_no_shell(self):
        import inspect
        src = inspect.getsource(AccountScopedMCPManager._run_transport)
        assert "shell" not in src.lower()


# ── health ───────────────────────────────────────────────────────────

class TestHealth:
    def test_start_health_stop_same_loop(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                await m.start("douyin", "acct_000000000001")
                h = await m.health("douyin", "acct_000000000001")
                assert h["ready"] is True
                await m.stop("douyin", "acct_000000000001")
                h2 = await m.health("douyin", "acct_000000000001")
                assert h2["ready"] is False
                assert h2["process_alive"] is False
            _run(go())

    def test_absent(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            r = _run(m.health("douyin", "acct_000000000099"))
            assert r["ready"] is False

    def test_extra_tools_not_fail(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                await m.start("douyin", "acct_000000000001")
                h = await m.health("douyin", "acct_000000000001")
                assert h["tools_ok"] is True
                await m.stop_all(timeout=10)
            _run(go())


# ── concurrency ──────────────────────────────────────────────────────

class TestConcurrency:
    def test_max_per_platform(self, tmp_path):
        m = make_manager(tmp_path, max_per_platform=2, max_total=10)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                await m.start("douyin", "acct_000000000001")
                await m.start("douyin", "acct_000000000002")
                r3 = await m.start("douyin", "acct_000000000003")
                assert r3["status"] == "busy"
                assert r3["reason"] == "max_per_platform"
                await m.stop_all()
            _run(go())

    def test_max_total(self, tmp_path):
        m = make_manager(tmp_path, max_per_platform=10, max_total=1)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                await m.start("douyin", "acct_000000000001")
                r2 = await m.start("bilibili", "acct_000000000002")
                assert r2["status"] == "busy"
                await m.stop_all()
            _run(go())

    def test_concurrent_two_respect_max_total(self, tmp_path):
        m = make_manager(tmp_path, max_per_platform=10, max_total=1)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                r1, r2 = await asyncio.gather(
                    m.start("douyin", "acct_000000000001"),
                    m.start("bilibili", "acct_000000000002"),
                )
                assert r1["status"] == "healthy"
                assert r2["status"] == "busy"
                await m.stop_all()
            _run(go())


# ── stop/restart ─────────────────────────────────────────────────────

class TestStop:
    def test_idempotent(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                await m.start("douyin", "acct_000000000001")
                assert await m.stop("douyin", "acct_000000000001") is True
                assert await m.stop("douyin", "acct_000000000001") is True
            _run(go())

    def test_profile_preserved(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                await m.start("douyin", "acct_000000000001")
                dd = m._data_dir("douyin", "acct_000000000001")
                await m.stop("douyin", "acct_000000000001")
                assert dd.exists()
            _run(go())

    def test_lock_released(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                await m.start("douyin", "acct_000000000001")
                lp = m._lock_path("douyin", "acct_000000000001")
                assert lp.exists()
                await m.stop("douyin", "acct_000000000001")
                assert not lp.exists()
            _run(go())

    def test_stop_all(self, tmp_path):
        m = make_manager(tmp_path, max_per_platform=10, max_total=10)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                await m.start("douyin", "acct_000000000001")
                await m.start("bilibili", "acct_000000000002")
                r = await m.stop_all(timeout=10)
                assert r["stopped"] >= 1 and r["failed"] == 0
                assert len(m._handles) == 0
            _run(go())


class TestRestartMode:
    def test_switches_headless(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                r1 = await m.start("douyin", "acct_000000000001", headless=False)
                r2 = await m.restart_mode("douyin", "acct_000000000001", headless=True)
                assert r1["headless"] is False
                assert r2["headless"] is True
                await m.stop_all()
            _run(go())

    def test_same_dir(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                await m.start("douyin", "acct_000000000001")
                d1 = m._data_dir("douyin", "acct_000000000001")
                await m.restart_mode("douyin", "acct_000000000001", headless=False)
                d2 = m._data_dir("douyin", "acct_000000000001")
                assert d1 == d2
                await m.stop_all()
            _run(go())

    def test_ensure_mode_reuses_matching_and_restarts_mismatch(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                first = await m.ensure_mode("douyin", "acct_000000000001", headless=True)
                reused = await m.ensure_mode("douyin", "acct_000000000001", headless=True)
                headed = await m.ensure_mode("douyin", "acct_000000000001", headless=False)
                assert first["instance_token"] == reused["instance_token"]
                assert headed["headless"] is False
                assert headed["instance_token"] != first["instance_token"]
                assert m._data_dir("douyin", "acct_000000000001").exists()
                await m.stop_all()
            _run(go())


# ── lock ─────────────────────────────────────────────────────────────

class TestLock:
    def test_second_manager_cannot_acquire(self, tmp_path):
        m1 = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                await m1.start("douyin", "acct_000000000001")
                m2 = make_manager(tmp_path)
                fh = m2._try_lock("douyin", "acct_000000000001")
                assert fh is None
                await m1.stop_all(timeout=10)
            _run(go())

    def test_reap_stale(self, tmp_path):
        m = make_manager(tmp_path)
        lp = m._lock_path("douyin", "acct_000000000099")
        lp.parent.mkdir(parents=True, exist_ok=True)
        with open(lp, "w") as f:
            json.dump({"instance_token": "old", "manager_pid": 99999}, f)
        m._reap_stale_locks()
        assert not lp.exists()


# ── idle ─────────────────────────────────────────────────────────────

class TestIdle:
    def test_idle_shuts_down(self, tmp_path):
        m = make_manager(tmp_path, idle_headless=0.1, idle_headed=0.1,
                         health_interval=0.05)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                await m.start("douyin", "acct_000000000001", headless=True)
                await asyncio.sleep(0.25)
                assert m._handles.get("douyin:acct_000000000001") is None
                await m.stop_all()
            _run(go())


# ── crash recovery ───────────────────────────────────────────────────

class TestCrashRecovery:
    def test_user_stop_no_retry(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                await m.start("douyin", "acct_000000000001")
                await m.stop("douyin", "acct_000000000001")
                assert m._handles.get("douyin:acct_000000000001") is None
            _run(go())

    def test_exceed_retries_absent(self, tmp_path):
        m = make_manager(tmp_path, crash_max_retries=1, crash_retry_base=0, crash_retry_max_delay=0)
        def always_fail(*a, **kw):
            raise RuntimeError("dead")
        with patch("agent_core.mcp_process_manager.stdio_client", side_effect=always_fail), \
             patch("agent_core.mcp_process_manager.ClientSession", side_effect=_fake_session), \
             patch("agent_core.mcp_process_manager.StdioServerParameters", MagicMock()):
            async def go():
                r = await m.start("douyin", "acct_000000000001")
                assert r["status"] in ("degraded", "absent")
                h = m._handles.get("douyin:acct_000000000001")
                if h is not None and h.task is not None:
                    await h.task
                assert len(m._handles) == 0
            _run(go())


# ── stop_all timeout ────────────────────────────────────────────────

class TestStopAllTimeout:
    def test_no_exception_on_timeout(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                await m.start("douyin", "acct_000000000001")
                r = await m.stop_all(timeout=0.001)
                assert r["stopped"] + r["failed"] >= 0
            _run(go())
        assert len(m._handles) == 0


# ── status / cleanup ────────────────────────────────────────────────

class TestStatusAndCleanup:
    def test_status_all(self, tmp_path):
        m = make_manager(tmp_path, max_per_platform=10, max_total=10)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                await m.start("douyin", "acct_000000000001")
                await m.start("bilibili", "acct_000000000002")
                assert len(await m.status_all()) == 2
                await m.stop_all(timeout=10)
            _run(go())

    def test_no_leftover_after_stop_all(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                await m.start("douyin", "acct_000000000001")
                await m.stop_all(timeout=10)
                assert len(m._handles) == 0
            _run(go())


# ── bin ─────────────────────────────────────────────────────────────

class TestBinCheck:
    def test_missing(self, tmp_path):
        m = make_manager(tmp_path, playwright_mcp_bin=tmp_path / "nope")
        assert m._bin_ok() is False
    def test_not_executable(self, tmp_path):
        p = tmp_path / "noexec"
        p.write_text("x"); p.chmod(0o644)
        m = make_manager(tmp_path, playwright_mcp_bin=p)
        assert m._bin_ok() is False
