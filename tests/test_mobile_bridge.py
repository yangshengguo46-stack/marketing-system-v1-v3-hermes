import asyncio
import sys
from enum import Enum
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, "runtime/hermes-agent")

from gateway import marketing_os_bridge  # noqa: E402


class Platform(Enum):
    FEISHU = "feishu"


def event(text="帮我分析今天热点", user_id="owner", chat_id="chat-1"):
    return SimpleNamespace(
        text=text,
        source=SimpleNamespace(
            platform=Platform.FEISHU,
            user_id=user_id,
            chat_id=chat_id,
            chat_type="dm",
        ),
    )


def test_mobile_bridge_routes_allowed_feishu_message(monkeypatch, tmp_path):
    monkeypatch.setenv("MARKETING_OS_MOBILE_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("FEISHU_ALLOWED_USERS", "owner")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    calls = []

    def fake_request(method, path, payload=None, timeout=20):
        calls.append((method, path, payload))
        if method == "POST" and path == "/agent/sessions":
            return {"session_id": "session-1"}
        if method == "POST" and path == "/agent/messages":
            return {"task_id": "task-1", "session_id": payload["session_id"]}
        if method == "GET" and path == "/agent/runs/task-1":
            return {"task_id": "task-1", "status": "completed"}
        if method == "GET" and path == "/agent/sessions/session-1/messages":
            return {"messages": [{"role": "assistant", "task_id": "task-1", "content": "营销回复"}]}
        raise AssertionError((method, path, payload))

    monkeypatch.setattr(marketing_os_bridge, "_request_json", fake_request)
    adapter = SimpleNamespace(send=AsyncMock())
    gateway = SimpleNamespace(adapters={Platform.FEISHU: adapter})

    handled = asyncio.run(marketing_os_bridge.maybe_handle_marketing_os(event(), gateway))

    assert handled is True
    adapter.send.assert_awaited_once_with("chat-1", "营销回复")
    assert calls[0] == (
        "POST",
        "/agent/sessions",
        {"user_id": "mobile:feishu:owner", "workspace": "mobile:feishu:chat-1"},
    )


def test_mobile_bridge_ignores_unknown_sender(monkeypatch):
    monkeypatch.setenv("MARKETING_OS_MOBILE_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("FEISHU_ALLOWED_USERS", "owner")
    adapter = SimpleNamespace(send=AsyncMock())
    gateway = SimpleNamespace(adapters={Platform.FEISHU: adapter})

    handled = asyncio.run(marketing_os_bridge.maybe_handle_marketing_os(event(user_id="stranger"), gateway))

    assert handled is False
    adapter.send.assert_not_awaited()


def test_mobile_bridge_handles_natural_set_home(monkeypatch):
    monkeypatch.setenv("MARKETING_OS_MOBILE_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("FEISHU_ALLOWED_USERS", "owner")
    monkeypatch.delenv("FEISHU_HOME_CHANNEL", raising=False)
    adapter = SimpleNamespace(send=AsyncMock())
    gateway = SimpleNamespace(adapters={Platform.FEISHU: adapter})

    handled = asyncio.run(marketing_os_bridge.maybe_handle_marketing_os(event(text="设为我的通知窗口"), gateway))

    assert handled is True
    assert "chat-1" == __import__("os").environ["FEISHU_HOME_CHANNEL"]
    adapter.send.assert_awaited_once()
