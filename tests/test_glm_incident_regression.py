"""Regression guards for the 2026-07-03 MCP sync incident."""

from __future__ import annotations

import json
import inspect
from pathlib import Path

from agent_core.mcp_broker import PLAYWRIGHT_FORBIDDEN_TOOLS, PLAYWRIGHT_MINIMAL_TOOLS
from agent_core.mcp_browser_policy import BrowserActionContext, validate_browser_call
from agent_core.mcp_process_manager import AccountScopedMCPManager


ROOT = Path(__file__).resolve().parents[1]


def _account_sync_context() -> BrowserActionContext:
    return BrowserActionContext(
        platform="douyin", account_id="acct_000000000001", capability="marketing_accounts_sync",
        user_id="user-1", approved=True,
    )


def test_arbitrary_javascript_remains_permanently_denied():
    assert "browser_evaluate" in PLAYWRIGHT_FORBIDDEN_TOOLS
    assert "browser_evaluate" not in PLAYWRIGHT_MINIMAL_TOOLS
    decision = validate_browser_call(
        _account_sync_context(), "browser_evaluate",
        {"function": "() => fetch('https://example.com')"},
    )
    assert not decision.allowed


def test_account_sync_clicks_exclude_download_and_ambiguous_confirmation():
    for label in ("导出数据", "导出", "下载", "确定"):
        decision = validate_browser_call(
            _account_sync_context(), "browser_click",
            {"element": label, "target": "e42"},
        )
        assert not decision.allowed, label
    assert validate_browser_call(
        _account_sync_context(), "browser_click",
        {"element": "我知道了", "target": "e42"},
    ).allowed


def test_manifest_does_not_reintroduce_browser_evaluate():
    manifest = json.loads(
        (ROOT / "engine/marketing-os/config/mcp-servers.json").read_text()
    )
    included = manifest["servers"]["playwright_browser"]["tools"]["include"]
    assert "browser_evaluate" not in included


def test_server_never_writes_raw_snapshot_debug_files_or_uses_fake_store_singleton():
    source = (ROOT / "engine/marketing-os/server.py").read_text()
    assert "mcp_snapshot_debug.txt" not in source
    assert "mcp_snapshot_content_debug.txt" not in source
    assert "mcp_snapshot_data_debug.txt" not in source
    assert "AgentCoreStore.instance()" not in source


def test_browser_start_does_not_unlink_chromium_singleton_files():
    source = inspect.getsource(AccountScopedMCPManager._run_transport)
    assert "SingletonLock" not in source
    assert "SingletonCookie" not in source
    assert "SingletonSocket" not in source


def test_electron_ipc_matches_allowlist_against_pathname_not_query_string():
    source = (ROOT / "electron/main.js").read_text()
    assert "canonicalLocalApiPath(path)" in source
    assert "pattern.test(pathname)" in source
    assert "callLocalApi(normalizedMethod, requestPath" in source
    assert "/%(?:2f|5c)/i" in source
