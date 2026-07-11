from __future__ import annotations

import json

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

    mcp_tool._scoped_servers.clear()
    mcp_tool._scoped_connect_locks.clear()
