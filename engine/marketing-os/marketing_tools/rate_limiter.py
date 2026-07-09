"""DATA-12: Rate limiting and platform-friendly scheduling.

Per-platform concurrency caps, request throttling, backoff, and daily quotas.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

DEFAULT_RATE_LIMITS: dict[str, dict[str, float]] = {
    "douyin": {"max_per_second": 1, "max_per_minute": 20, "max_per_hour": 500, "max_per_day": 2000},
    "bilibili": {"max_per_second": 2, "max_per_minute": 50, "max_per_hour": 1000, "max_per_day": 3000},
    "zhihu": {"max_per_second": 1, "max_per_minute": 15, "max_per_hour": 300, "max_per_day": 1000},
    "default": {"max_per_second": 1, "max_per_minute": 20, "max_per_hour": 400, "max_per_day": 1500},
}


@dataclass
class RateLimiter:
    platform: str
    limits: dict[str, float] = field(default_factory=dict)
    _counters: dict[str, list[float]] = field(default_factory=dict)

    def __post_init__(self):
        self.limits = DEFAULT_RATE_LIMITS.get(self.platform, DEFAULT_RATE_LIMITS["default"])

    def _prune(self, window: str, max_age: float) -> None:
        now = time.monotonic()
        self._counters.setdefault(window, [])
        self._counters[window] = [t for t in self._counters[window] if now - t < max_age]

    def allow(self) -> tuple[bool, float]:
        now = time.monotonic()
        windows = {"per_second": 1, "per_minute": 60, "per_hour": 3600, "per_day": 86400}
        for window, secs in windows.items():
            cap_key = f"max_{window}"
            if cap_key not in self.limits:
                continue
            self._prune(window, secs)
            if len(self._counters[window]) >= self.limits[cap_key]:
                wait = self._counters[window][0] + secs - now
                return False, max(0.1, wait)
        for w in windows:
            self._counters.setdefault(w, []).append(now)
        return True, 0.0

    def remaining(self) -> dict[str, int]:
        now = time.monotonic()
        r: dict[str, int] = {}
        windows = {"per_second": 1, "per_minute": 60, "per_hour": 3600, "per_day": 86400}
        for window, secs in windows.items():
            cap_key = f"max_{window}"
            if cap_key not in self.limits:
                continue
            self._prune(window, secs)
            r[window] = max(0, int(self.limits[cap_key]) - len(self._counters[window]))
        return r
