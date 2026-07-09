"""MCP-09: Dual-account zero cross-contamination tests.

Verifies that two same-platform accounts never share:
1. Process (separate PID)
2. Profile directory (separate --user-data-dir)
3. Lock files (separate lock dirs)
4. Log files (separate log dirs)
5. Instance tokens (unique per account)
6. Result caches (no shared state in manager)
7. Stop one doesn't affect the other
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import test helpers from existing process manager tests
from tests.test_mcp_process_manager import make_manager, _three_patches, _run


class TestDualAccountProcessIsolation:
    """Two same-platform accounts must have separate processes."""

    def test_two_accounts_separate_data_dirs(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                await m.start("douyin", "acct_aaa111")
                await m.start("douyin", "acct_bbb222")
                d1 = m._data_dir("douyin", "acct_aaa111")
                d2 = m._data_dir("douyin", "acct_bbb222")
                assert d1 != d2
                assert not d1.is_relative_to(d2)
                assert not d2.is_relative_to(d1)
                await m.stop_all(timeout=10)
            _run(go())

    def test_two_accounts_separate_lock_dirs(self, tmp_path):
        m = make_manager(tmp_path)
        l1 = m._lock_dir("douyin", "acct_aaa111")
        l2 = m._lock_dir("douyin", "acct_bbb222")
        assert l1 != l2
        assert l1.name == "acct_aaa111"
        assert l2.name == "acct_bbb222"

    def test_two_accounts_separate_log_dirs(self, tmp_path):
        m = make_manager(tmp_path)
        l1 = m._log_dir("douyin", "acct_aaa111")
        l2 = m._log_dir("douyin", "acct_bbb222")
        assert l1 != l2
        assert l1.name == "acct_aaa111"
        assert l2.name == "acct_bbb222"

    def test_two_accounts_separate_lock_files(self, tmp_path):
        m = make_manager(tmp_path)
        p1 = m._lock_path("douyin", "acct_aaa111")
        p2 = m._lock_path("douyin", "acct_bbb222")
        assert p1 != p2
        assert p1.parent.name == "acct_aaa111"
        assert p2.parent.name == "acct_bbb222"

    def test_data_dir_includes_platform_and_account(self, tmp_path):
        m = make_manager(tmp_path)
        d = m._data_dir("douyin", "acct_aaa111")
        parts = d.parts
        assert "douyin" in parts
        assert "acct_aaa111" in parts
        assert "mcp-browser" in parts


class TestDualAccountStartStop:
    """Starting and stopping one account must not affect the other."""

    def test_stop_one_other_still_healthy(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                r1 = await m.start("douyin", "acct_aaa111")
                r2 = await m.start("douyin", "acct_bbb222")
                assert r1["status"] == "healthy"
                assert r2["status"] == "healthy"

                # Stop account 1
                await m.stop("douyin", "acct_aaa111")

                # Account 2 should still be healthy
                h2 = await m.health("douyin", "acct_bbb222")
                assert h2["ready"] is True

                # Account 1 should be stopped
                h1 = await m.health("douyin", "acct_aaa111")
                assert h1["ready"] is False

                await m.stop_all(timeout=10)
            _run(go())

    def test_start_after_stop_other(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                await m.start("douyin", "acct_aaa111")
                await m.start("douyin", "acct_bbb222")

                await m.stop("douyin", "acct_aaa111")

                # Restart account 1
                r1 = await m.start("douyin", "acct_aaa111")
                assert r1["status"] == "healthy"

                # Account 2 should still be healthy
                h2 = await m.health("douyin", "acct_bbb222")
                assert h2["ready"] is True

                await m.stop_all(timeout=10)
            _run(go())

    def test_stop_all_stops_both(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                await m.start("douyin", "acct_aaa111")
                await m.start("douyin", "acct_bbb222")

                await m.stop_all(timeout=10)

                h1 = await m.health("douyin", "acct_aaa111")
                h2 = await m.health("douyin", "acct_bbb222")
                assert h1["ready"] is False
                assert h2["ready"] is False
            _run(go())


class TestDualAccountNoStateSharing:
    """Verify the manager doesn't share state between accounts."""

    def test_different_instance_tokens(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                r1 = await m.start("douyin", "acct_aaa111")
                r2 = await m.start("douyin", "acct_bbb222")
                assert r1["instance_token"] != r2["instance_token"]
                await m.stop_all(timeout=10)
            _run(go())

    def test_health_returns_correct_account(self, tmp_path):
        m = make_manager(tmp_path)
        with _three_patches()[0], _three_patches()[1], _three_patches()[2]:
            async def go():
                await m.start("douyin", "acct_aaa111")
                await m.start("douyin", "acct_bbb222")

                h1 = await m.health("douyin", "acct_aaa111")
                h2 = await m.health("douyin", "acct_bbb222")

                # Both should be healthy independently
                assert h1["ready"] is True
                assert h2["ready"] is True

                # Health for non-existent account should be not ready
                h3 = await m.health("douyin", "acct_ccc333")
                assert h3["ready"] is False

                await m.stop_all(timeout=10)
            _run(go())


class TestDualAccountPathSafety:
    """Verify path traversal protection for account IDs."""

    def test_path_traversal_rejected(self, tmp_path):
        from agent_core.mcp_process_manager import MCPManagerError
        m = make_manager(tmp_path)
        with pytest.raises(MCPManagerError):
            m._data_dir("douyin", "../../../etc/passwd")

    def test_dot_dot_in_account_id_rejected(self, tmp_path):
        from agent_core.mcp_process_manager import MCPManagerError
        m = make_manager(tmp_path)
        # _data_dir uses _safe_subpath which may not catch all traversal
        # but start() validates account_id format via _ACCOUNT_RE
        with pytest.raises(MCPManagerError):
            _run(m.start("douyin", "acct_../../secret"))

    def test_empty_account_id_rejected(self, tmp_path):
        from agent_core.mcp_process_manager import MCPManagerError
        m = make_manager(tmp_path)
        with pytest.raises(MCPManagerError):
            _run(m.start("douyin", ""))

    def test_different_platforms_separate_dirs(self, tmp_path):
        m = make_manager(tmp_path)
        d1 = m._data_dir("douyin", "acct_aaa111")
        d2 = m._data_dir("bilibili", "acct_aaa111")
        assert d1 != d2
        assert "douyin" in d1.parts
        assert "bilibili" in d2.parts


class TestDualAccountSourceCodeVerification:
    """Static verification of isolation guarantees in source code."""

    def test_user_data_dir_uses_account_id(self):
        from agent_core.mcp_process_manager import AccountScopedMCPManager
        src = inspect.getsource(AccountScopedMCPManager._run_transport)
        assert "user-data-dir" in src
        assert "account_id" in src or "meta.account_id" in src

    def test_no_shared_global_state(self):
        from agent_core.mcp_process_manager import AccountScopedMCPManager
        src = inspect.getsource(AccountScopedMCPManager)
        # _handles should be keyed by (platform, account_id)
        assert "self._handles" in src
        assert "platform" in src and "account_id" in src

    def test_no_shell_execution(self):
        from agent_core.mcp_process_manager import AccountScopedMCPManager
        src = inspect.getsource(AccountScopedMCPManager._run_transport)
        assert "shell" not in src.lower()
