import sys
from enum import Enum
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

from marketing_tools.channel_context import pre_gateway_dispatch


class Platform(Enum):
    FEISHU = "feishu"


class PlatformConfig:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.home_channel = None


class HomeChannel:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def runtime_modules():
    gateway = ModuleType("gateway")
    config = ModuleType("gateway.config")
    config.HomeChannel = HomeChannel
    config.PlatformConfig = PlatformConfig
    gateway.config = config
    hermes_cli = ModuleType("hermes_cli")
    hermes_config = ModuleType("hermes_cli.config")
    hermes_config.save_env_value = MagicMock()
    hermes_cli.config = hermes_config
    return {
        "gateway": gateway,
        "gateway.config": config,
        "hermes_cli": hermes_cli,
        "hermes_cli.config": hermes_config,
    }


def event(user_id="owner", chat_id="chat-1", text="你好", chat_type="dm"):
    return SimpleNamespace(
        text=text,
        source=SimpleNamespace(
            platform=Platform.FEISHU,
            user_id=user_id,
            chat_id=chat_id,
            chat_name="我的飞书",
            chat_type=chat_type,
        ),
    )


def test_first_trusted_dm_becomes_home_channel(monkeypatch):
    monkeypatch.setenv("FEISHU_ALLOWED_USERS", "owner")
    monkeypatch.delenv("FEISHU_HOME_CHANNEL", raising=False)
    gateway = SimpleNamespace(config=SimpleNamespace(platforms={Platform.FEISHU: PlatformConfig(enabled=True)}))
    modules = runtime_modules()
    with patch.dict(sys.modules, modules):
        result = pre_gateway_dispatch(event(), gateway=gateway)
    assert result is None
    modules["hermes_cli.config"].save_env_value.assert_called_once_with("FEISHU_HOME_CHANNEL", "chat-1")
    assert gateway.config.platforms[Platform.FEISHU].home_channel.chat_id == "chat-1"


def test_unknown_sender_cannot_claim_home_channel(monkeypatch):
    monkeypatch.setenv("FEISHU_ALLOWED_USERS", "owner")
    monkeypatch.delenv("FEISHU_HOME_CHANNEL", raising=False)
    gateway = SimpleNamespace(config=SimpleNamespace(platforms={}))
    modules = runtime_modules()
    with patch.dict(sys.modules, modules):
        pre_gateway_dispatch(event(user_id="stranger"), gateway=gateway)
    modules["hermes_cli.config"].save_env_value.assert_not_called()


def test_natural_chinese_set_home_phrase_is_rewritten(monkeypatch):
    monkeypatch.setenv("FEISHU_HOME_CHANNEL", "old-chat")
    result = pre_gateway_dispatch(event(text="设为我的通知窗口"))
    assert result == {"action": "rewrite", "text": "/sethome"}
