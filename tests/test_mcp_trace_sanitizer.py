"""MCP-11: trace opt-in guard and secret redaction coverage."""

import importlib

import pytest

from agent_core import mcp_trace_sanitizer
from agent_core.mcp_trace_sanitizer import sanitize_line, sanitize_snapshot_content


@pytest.mark.parametrize("raw,must_not_contain,must_contain", [
    ("Cookie: sessionid=abc123; path=/", "abc123", "[REDACTED]"),
    ("set-cookie: passport_token=deadbeef", "deadbeef", "[REDACTED]"),
    ("Authorization: Bearer secret-token-value", "secret-token-value", "[REDACTED]"),
    ("access_token=ya29.a0AfH6SMB", "ya29.a0AfH6SMB", "[REDACTED]"),
    ("refresh_token: 1//0eXyZ", "1//0eXyZ", "[REDACTED]"),
    ("联系方式 13812345678 请回电", "13812345678", "[PHONE_REDACTED]"),
    ("身份证 110101199003078515 已核验", "110101199003078515", "[ID_REDACTED]"),
    ("key=sk-abcdefghijklmnop1234", "sk-abcdefghijklmnop1234", "[API_KEY_REDACTED]"),
    (
        "jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9P",
        "eyJhbGciOiJIUzI1NiJ9",
        "[JWT_REDACTED]",
    ),
])
def test_secret_patterns_are_redacted(raw, must_not_contain, must_contain):
    sanitized = sanitize_line(raw)
    assert must_not_contain not in sanitized
    assert must_contain in sanitized


def test_plain_business_content_is_preserved():
    line = "browser_navigate ok url=https://creator.douyin.com/ 热点 30 条"
    assert sanitize_line(line) == line


def test_line_is_truncated_to_max_length():
    line = "a" * 5000 + " Cookie: sessionid=abc"
    sanitized = sanitize_line(line)
    assert len(sanitized) <= 2000
    assert "sessionid=abc" not in sanitized


def test_snapshot_redacts_secrets_and_caps_size():
    snapshot = ("x" * 200_000) + "\nCookie: sessionid=abc123"
    sanitized = sanitize_snapshot_content(snapshot)
    assert len(sanitized) <= 100_000
    assert "abc123" not in sanitized

    small = "textbox 手机号 13812345678\nbutton 登录"
    sanitized_small = sanitize_snapshot_content(small)
    assert "13812345678" not in sanitized_small
    assert "[PHONE_REDACTED]" in sanitized_small
    assert "button 登录" in sanitized_small


def test_empty_snapshot_returns_empty_string():
    assert sanitize_snapshot_content("") == ""


def test_trace_is_disabled_unless_env_flag_is_exactly_one(monkeypatch):
    monkeypatch.delenv("MARKETING_OS_MCP_TRACE", raising=False)
    module = importlib.reload(mcp_trace_sanitizer)
    assert module.trace_enabled() is False

    monkeypatch.setenv("MARKETING_OS_MCP_TRACE", "true")
    module = importlib.reload(mcp_trace_sanitizer)
    assert module.trace_enabled() is False

    monkeypatch.setenv("MARKETING_OS_MCP_TRACE", "1")
    module = importlib.reload(mcp_trace_sanitizer)
    assert module.trace_enabled() is True

    monkeypatch.delenv("MARKETING_OS_MCP_TRACE", raising=False)
    importlib.reload(mcp_trace_sanitizer)
