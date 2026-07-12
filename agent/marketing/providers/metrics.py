"""Native provider seam for observing post-publish platform metrics.

The provider owns platform access and extraction.  It never writes Hermes
state, interprets performance, or changes account strategy.  Those concerns
belong to the receipt and learning owners.
"""

from __future__ import annotations

import threading
from typing import Any, Protocol


class MetricProvider(Protocol):
    """Observe one due metric checkpoint from the real platform."""

    name: str

    def collect_metrics(
        self,
        action: dict[str, Any],
        checkpoint: dict[str, Any],
    ) -> dict[str, Any]: ...


_PROVIDERS: dict[str, MetricProvider] = {}
_LOCK = threading.RLock()


def register_metric_provider(provider: MetricProvider) -> None:
    name = str(getattr(provider, "name", "") or "").strip()
    if not name:
        raise ValueError("metric provider requires a stable name")
    if not callable(getattr(provider, "collect_metrics", None)):
        raise TypeError("metric provider must implement collect_metrics()")
    with _LOCK:
        _PROVIDERS[name] = provider


def get_metric_provider(name: str) -> MetricProvider:
    with _LOCK:
        provider = _PROVIDERS.get(str(name or "").strip())
    if provider is None:
        raise KeyError(f"metric provider is unavailable: {name}")
    return provider


def has_metric_provider(name: str | None = None) -> bool:
    with _LOCK:
        if name is None:
            return bool(_PROVIDERS)
        return str(name or "").strip() in _PROVIDERS


def clear_metric_providers() -> None:
    """Test/lifecycle cleanup; production providers re-register at startup."""

    with _LOCK:
        _PROVIDERS.clear()
