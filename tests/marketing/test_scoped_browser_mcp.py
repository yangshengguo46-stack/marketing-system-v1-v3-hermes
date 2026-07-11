from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil

import pytest

from tools import mcp_tool


def test_scoped_mcp_config_replaces_discovery_mode_with_account_lease():
    lease = {
        "session_id": "session-1",
        "user_id": "default",
        "account_id": "acct_ab3145",
        "platform": "douyin",
        "profile_key": "douyin:acct_ab3145",
        "auth_state": "authenticated",
        "issued_at": 1.0,
    }
    result = mcp_tool._scoped_server_config(
        {
            "command": "/usr/bin/node",
            "args": ["server.js", "--schema-only"],
            "scoped_args": ["server.js"],
            "session_scope": "marketing_account",
            "env": {"HERMES_BROWSER_PROFILE_ROOT": "/profiles"},
        },
        lease,
    )

    assert result["args"] == ["server.js"]
    assert "scoped_args" not in result
    assert "session_scope" not in result
    assert result["dynamic_tool_refresh"] is False
    assert result["env"]["HERMES_BROWSER_PROFILE_ROOT"] == "/profiles"
    assert json.loads(result["env"]["HERMES_MARKETING_ACCOUNT_LEASE"]) == lease
    assert "HERMES_BROWSER_HEADED" not in result["env"]


def test_pending_account_opens_the_mcp_owned_browser_in_headed_mode():
    result = mcp_tool._scoped_server_config(
        {"scoped_args": ["server.js"]},
        {
            "session_id": "session-login",
            "user_id": "default",
            "account_id": "acct-login",
            "platform": "zhihu",
            "profile_key": "zhihu:acct-login",
            "auth_state": "unauthenticated",
        },
    )

    assert result["env"]["HERMES_BROWSER_HEADED"] == "1"


def test_scoped_mcp_config_requires_an_execution_command():
    try:
        mcp_tool._scoped_server_config({}, {"account_id": "acct"})
    except ValueError as exc:
        assert "scoped_args" in str(exc)
    else:
        raise AssertionError("schema-only MCP must not be used for account execution")


@pytest.mark.asyncio
async def test_scoped_pool_reuses_one_owner_per_account_and_isolates_accounts(monkeypatch):
    created = []

    class FakeServer:
        def __init__(self, name):
            self.name = name
            self.session = None

        async def start(self, config):
            self.config = config
            self.session = object()
            created.append(self)

    monkeypatch.setattr(mcp_tool, "MCPServerTask", FakeServer)
    mcp_tool._scoped_servers.clear()
    mcp_tool._scoped_connect_locks.clear()
    config = {
        "command": "node",
        "args": ["server.js", "--schema-only"],
        "scoped_args": ["server.js"],
    }
    first_lease = {
        "session_id": "session-1",
        "user_id": "default",
        "account_id": "acct-1",
        "platform": "zhihu",
        "profile_key": "zhihu:acct-1",
        "auth_state": "authenticated",
    }
    second_lease = {**first_lease, "session_id": "session-2", "account_id": "acct-2", "profile_key": "zhihu:acct-2"}

    first = await mcp_tool._get_scoped_server("marketing-browser", config, first_lease)
    repeated = await mcp_tool._get_scoped_server("marketing-browser", config, first_lease)
    second = await mcp_tool._get_scoped_server("marketing-browser", config, second_lease)

    assert first is repeated
    assert first is not second
    assert len(created) == 2
    assert json.loads(first.config["env"]["HERMES_MARKETING_ACCOUNT_LEASE"])["account_id"] == "acct-1"
    assert json.loads(second.config["env"]["HERMES_MARKETING_ACCOUNT_LEASE"])["account_id"] == "acct-2"

    watchers = list(mcp_tool._scoped_watch_tasks.values())
    for watcher in watchers:
        watcher.cancel()
    await asyncio.gather(*watchers, return_exceptions=True)
    mcp_tool._scoped_servers.clear()
    mcp_tool._scoped_connect_locks.clear()
    mcp_tool._scoped_watch_tasks.clear()


@pytest.mark.asyncio
async def test_scoped_account_watcher_closes_and_purges_deleted_account(monkeypatch):
    stopped = asyncio.Event()
    purged = []

    class FakeServer:
        async def shutdown(self):
            stopped.set()

    async def fake_purge(config, lease):
        purged.append((config, lease))

    monkeypatch.setattr(mcp_tool, "_SCOPED_ACCOUNT_WATCH_INTERVAL", 0.001)
    monkeypatch.setattr(
        mcp_tool,
        "_read_scoped_account_lifecycle",
        lambda lease: {"may_run": False, "purge_profile": True},
    )
    monkeypatch.setattr(mcp_tool, "_purge_scoped_account_data", fake_purge)
    key = ("marketing-browser", "default", "acct-deleted")
    server = FakeServer()
    lease = {
        "user_id": "default",
        "account_id": "acct-deleted",
        "platform": "zhihu",
        "profile_key": "zhihu:acct-deleted",
    }
    mcp_tool._scoped_servers[key] = server
    mcp_tool._scoped_connect_locks[key] = asyncio.Lock()

    await asyncio.wait_for(
        mcp_tool._watch_scoped_account(key, server, {"scoped_args": ["server.js"]}, lease),
        timeout=1,
    )

    assert stopped.is_set()
    assert purged == [({"scoped_args": ["server.js"]}, lease)]
    assert key not in mcp_tool._scoped_servers
    assert key not in mcp_tool._scoped_connect_locks


@pytest.mark.asyncio
async def test_python_mcp_owner_invokes_native_browser_profile_purge(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for the bundled browser MCP")
    entry = (
        Path(__file__).resolve().parents[2]
        / "mcp"
        / "marketing-browser"
        / "src"
        / "server.js"
    )
    profile_root = tmp_path / "profiles"
    output_root = tmp_path / "output"
    profile = profile_root / "zhihu" / "acct-delete"
    output = output_root / "zhihu" / "acct-delete"
    profile.mkdir(parents=True)
    output.mkdir(parents=True)
    lease = {
        "session_id": "session-1",
        "user_id": "default",
        "account_id": "acct-delete",
        "platform": "zhihu",
        "profile_key": "zhihu:acct-delete",
        "auth_state": "authenticated",
    }

    await mcp_tool._purge_scoped_account_data(
        {
            "command": node,
            "scoped_args": [str(entry)],
            "env": {
                "HERMES_BROWSER_PROFILE_ROOT": str(profile_root),
                "HERMES_BROWSER_OUTPUT_ROOT": str(output_root),
            },
        },
        lease,
    )

    assert not profile.exists()
    assert not output.exists()
