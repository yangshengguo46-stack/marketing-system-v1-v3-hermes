from types import SimpleNamespace
from unittest.mock import MagicMock

from gateway.config import Platform, PlatformConfig
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from gateway.product_messaging import prepare_inbound_message


def _event(text="帮我分析今天热点", user_id="owner", chat_id="chat-1"):
    return MessageEvent(
        text=text,
        source=SessionSource(
            platform=Platform.FEISHU,
            user_id=user_id,
            chat_id=chat_id,
            chat_name="我的飞书",
            chat_type="dm",
        ),
    )


def _gateway():
    return SimpleNamespace(
        config=SimpleNamespace(
            platforms={Platform.FEISHU: PlatformConfig(enabled=True)},
        ),
    )


def _enable_product(monkeypatch, tmp_path):
    monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(tmp_path / "marketing-os"))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))


def test_trusted_first_dm_becomes_home_and_stays_in_native_message_flow(
    monkeypatch, tmp_path
):
    _enable_product(monkeypatch, tmp_path)
    monkeypatch.setenv("FEISHU_ALLOWED_USERS", "owner")
    monkeypatch.delenv("FEISHU_HOME_CHANNEL", raising=False)
    save = MagicMock()
    monkeypatch.setattr("hermes_cli.config.save_env_value", save)
    event = _event()
    gateway = _gateway()

    prepared = prepare_inbound_message(event, gateway)

    assert prepared is event
    assert __import__("os").environ["FEISHU_HOME_CHANNEL"] == "chat-1"
    save.assert_called_once_with("FEISHU_HOME_CHANNEL", "chat-1")
    assert gateway.config.platforms[Platform.FEISHU].home_channel.chat_id == "chat-1"


def test_natural_set_home_phrase_uses_native_hermes_command(monkeypatch, tmp_path):
    _enable_product(monkeypatch, tmp_path)
    monkeypatch.setenv("FEISHU_ALLOWED_USERS", "owner")
    monkeypatch.setenv("FEISHU_HOME_CHANNEL", "chat-1")

    prepared = prepare_inbound_message(_event(text="设为我的通知窗口"), _gateway())

    assert prepared.text == "/sethome"


def test_unknown_sender_cannot_claim_home_or_rewrite_command(monkeypatch, tmp_path):
    _enable_product(monkeypatch, tmp_path)
    monkeypatch.setenv("FEISHU_ALLOWED_USERS", "owner")
    monkeypatch.delenv("FEISHU_HOME_CHANNEL", raising=False)
    save = MagicMock()
    monkeypatch.setattr("hermes_cli.config.save_env_value", save)
    event = _event(text="设为我的通知窗口", user_id="stranger")

    prepared = prepare_inbound_message(event, _gateway())

    assert prepared is event
    save.assert_not_called()
    assert "FEISHU_HOME_CHANNEL" not in __import__("os").environ


def test_regular_hermes_runtime_is_unchanged(monkeypatch):
    monkeypatch.delenv("MARKETING_OS_USER_DATA", raising=False)
    monkeypatch.delenv("MARKETING_OS_CONFIG_DIR", raising=False)
    monkeypatch.delenv("MARKETING_OS_AGENT_DB", raising=False)
    event = _event(text="设为我的通知窗口")

    assert prepare_inbound_message(event, _gateway()) is event
