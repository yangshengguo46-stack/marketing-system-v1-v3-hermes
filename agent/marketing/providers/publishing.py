"""Provider registry for real platform publishing implementations."""

from __future__ import annotations

import threading
from typing import Any, Protocol


class PublishProvider(Protocol):
    name: str

    def publish(self, action: dict[str, Any]) -> dict[str, Any]: ...

    def query(self, action: dict[str, Any]) -> dict[str, Any]: ...


_PROVIDERS: dict[str, PublishProvider] = {}
_LOCK = threading.RLock()


def register_publish_provider(provider: PublishProvider) -> None:
    name = str(getattr(provider, "name", "") or "").strip()
    if not name:
        raise ValueError("publish provider requires a stable name")
    if not callable(getattr(provider, "publish", None)) or not callable(
        getattr(provider, "query", None)
    ):
        raise TypeError("publish provider must implement publish() and query()")
    with _LOCK:
        _PROVIDERS[name] = provider
    _invalidate_tool_availability()


def get_publish_provider(name: str) -> PublishProvider:
    with _LOCK:
        provider = _PROVIDERS.get(str(name or "").strip())
    if provider is None:
        raise KeyError(f"publish provider is unavailable: {name}")
    return provider


def has_publish_providers() -> bool:
    with _LOCK:
        return bool(_PROVIDERS)


def clear_publish_providers() -> None:
    """Test/lifecycle cleanup; production providers re-register at startup."""

    with _LOCK:
        _PROVIDERS.clear()
    _invalidate_tool_availability()


def _invalidate_tool_availability() -> None:
    try:
        from tools.registry import invalidate_check_fn_cache

        invalidate_check_fn_cache()
    except Exception:
        pass
    try:
        from model_tools import _clear_tool_defs_cache

        _clear_tool_defs_cache()
    except Exception:
        pass
