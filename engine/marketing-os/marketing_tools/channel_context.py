"""Messaging-channel context for the Marketing OS desktop product."""

from __future__ import annotations

import os


SUPPORTED = {"weixin", "feishu"}
HOME_KEYS = {"weixin": "WEIXIN_HOME_CHANNEL", "feishu": "FEISHU_HOME_CHANNEL"}
ALLOWED_KEYS = {"weixin": "WEIXIN_ALLOWED_USERS", "feishu": "FEISHU_ALLOWED_USERS"}
SET_HOME_PHRASES = {"设为通知窗口", "设为我的通知窗口", "把这里设为通知窗口", "绑定通知", "绑定通知窗口"}


def _allowed_user(platform: str, user_id: str) -> bool:
    allowed = {
        value.strip()
        for value in os.getenv(ALLOWED_KEYS[platform], "").split(",")
        if value.strip()
    }
    return bool(user_id and user_id in allowed)


def pre_gateway_dispatch(event, gateway=None, **_kwargs):
    """Auto-designate the first trusted DM as its notification destination.

    This runs before normal authorization, so it only acts when the sender was
    explicitly recorded by the desktop QR flow. Unknown senders can never make
    themselves a delivery target through this hook.
    """
    source = getattr(event, "source", None)
    platform_obj = getattr(source, "platform", None)
    platform = getattr(platform_obj, "value", platform_obj)
    if platform not in SUPPORTED or getattr(source, "chat_type", None) != "dm":
        return None

    text = str(getattr(event, "text", "") or "").strip()
    home_key = HOME_KEYS[platform]
    current_home = os.getenv(home_key, "").strip()
    user_id = str(getattr(source, "user_id", "") or "")
    chat_id = str(getattr(source, "chat_id", "") or "")

    if not current_home and chat_id and _allowed_user(platform, user_id):
        from hermes_cli.config import save_env_value
        from gateway.config import HomeChannel, PlatformConfig

        save_env_value(home_key, chat_id)
        os.environ[home_key] = chat_id
        if gateway is not None and platform_obj is not None:
            platform_config = gateway.config.platforms.setdefault(
                platform_obj,
                PlatformConfig(enabled=True),
            )
            platform_config.home_channel = HomeChannel(
                platform=platform_obj,
                chat_id=chat_id,
                name=str(getattr(source, "chat_name", "") or chat_id),
                thread_id=None,
            )
        return None

    if text in SET_HOME_PHRASES:
        return {"action": "rewrite", "text": "/sethome"}
    return None
