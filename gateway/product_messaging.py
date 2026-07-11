"""Marketing-aware message preparation inside the native Hermes gateway.

This module deliberately does not call another Agent API. It only adds product
conveniences to the normal Hermes inbound pipeline, then returns the message to
the same gateway session, memory and task loop used by every other surface.
"""

from __future__ import annotations

import dataclasses
import os
from typing import Any

from agent.product import is_product_runtime


SUPPORTED_PLATFORMS = {"feishu", "weixin"}
SET_HOME_PHRASES = {
    "设为通知窗口",
    "设为我的通知窗口",
    "把这里设为通知窗口",
    "绑定通知",
    "绑定通知窗口",
}
TRUTHY = {"1", "true", "yes", "on"}


def _platform_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _allowed_user(platform: str, user_id: str) -> bool:
    if not user_id:
        return False
    prefix = platform.upper()
    if str(os.getenv(f"{prefix}_ALLOW_ALL_USERS", "")).strip().lower() in TRUTHY:
        return True
    allowed = {
        item.strip()
        for item in os.getenv(f"{prefix}_ALLOWED_USERS", "").split(",")
        if item.strip()
    }
    return "*" in allowed or user_id in allowed


def _save_home_channel(platform: str, platform_obj: Any, source: Any, gateway: Any) -> None:
    chat_id = str(getattr(source, "chat_id", "") or "").strip()
    if not chat_id:
        return

    env_key = f"{platform.upper()}_HOME_CHANNEL"
    from hermes_cli.config import save_env_value

    save_env_value(env_key, chat_id)
    os.environ[env_key] = chat_id

    if gateway is None or platform_obj is None:
        return

    from gateway.config import HomeChannel, PlatformConfig

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


def prepare_inbound_message(event: Any, gateway: Any = None) -> Any:
    """Add native Marketing OS channel behavior and return the same event flow.

    Trusted first-party DMs become notification destinations automatically.
    Natural Chinese notification-window phrases are normalized to Hermes'
    built-in ``/sethome`` command. Every other message continues through the
    regular authorization, session, prompt, memory and Agent execution path.
    """

    if not is_product_runtime():
        return event

    source = getattr(event, "source", None)
    platform_obj = getattr(source, "platform", None)
    platform = _platform_value(platform_obj)
    if platform not in SUPPORTED_PLATFORMS or getattr(source, "chat_type", None) != "dm":
        return event

    user_id = str(getattr(source, "user_id", "") or "")
    chat_id = str(getattr(source, "chat_id", "") or "")
    trusted = bool(chat_id and _allowed_user(platform, user_id))
    home_key = f"{platform.upper()}_HOME_CHANNEL"
    if trusted and not str(os.getenv(home_key, "")).strip():
        _save_home_channel(platform, platform_obj, source, gateway)

    text = str(getattr(event, "text", "") or "").strip()
    if trusted and text in SET_HOME_PHRASES:
        return dataclasses.replace(event, text="/sethome")
    return event
