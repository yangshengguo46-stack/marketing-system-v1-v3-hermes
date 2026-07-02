"""DATA-13: Data quality scoring for ingested source items.

Scores completeness, freshness, source credibility, cross-validation,
and anomaly flags.  Low-quality items should not enter strong conclusions.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

# Source credibility baseline (0.0–1.0)
SOURCE_CREDIBILITY: dict[str, float] = {
    "hot_topics_api": 0.6,        # aggregated public API
    "bilibili_public": 0.7,       # B站官方公开接口
    "electron_session": 0.8,      # 真人登录态采集, richer data
    "playwright_mcp_creator_center": 0.85,  # MCP 创作者中心, richest
    "unknown": 0.3,
}


def _completeness(item: dict[str, Any]) -> float:
    """Score 0–1 based on how many key fields are populated."""
    keys = ("title", "url", "source_platform", "source_backend", "collected_at")
    present = sum(1 for k in keys if item.get(k))
    bonus = 0.0
    if item.get("author"):
        bonus += 0.1
    if item.get("published_at"):
        bonus += 0.1
    if item.get("metrics") and isinstance(item.get("metrics"), dict):
        bonus += 0.1
    return min(1.0, present / len(keys) + bonus)


def _freshness(item: dict[str, Any], *, now: str | None = None) -> float:
    """Score 0–1 based on recency.  <1h = 1.0, >7d = 0.1."""
    collected = item.get("collected_at") or item.get("cached_at")
    if not collected:
        return 0.2
    try:
        collected_dt = datetime.fromisoformat(str(collected))
        ref = datetime.fromisoformat(now) if now else datetime.now(timezone.utc)
        age = (ref - collected_dt).total_seconds()
    except (ValueError, TypeError):
        return 0.2
    if age < 3600:
        return 1.0
    if age < 86400:
        return 0.8
    if age < 259200:  # 3d
        return 0.5
    if age < 604800:  # 7d
        return 0.3
    return 0.1


def _source_cred(item: dict[str, Any]) -> float:
    src = str(item.get("source_backend") or item.get("source") or "unknown").lower()
    return SOURCE_CREDIBILITY.get(src, 0.3)


def _anomaly_penalty(item: dict[str, Any]) -> float:
    """Penalize suspicious items. Returns 0.0 (no penalty) to -0.5."""
    penalty = 0.0
    title = str(item.get("title", ""))
    if len(title) < 4:
        penalty -= 0.3
    if len(title) > 500:
        penalty -= 0.1
    rank = item.get("rank")
    if rank is not None:
        try:
            r = int(rank)
            if r > 200:
                penalty -= 0.2
        except (TypeError, ValueError):
            penalty -= 0.1
    metrics = item.get("metrics")
    if isinstance(metrics, dict):
        for k in ("views", "likes", "comments"):
            v = metrics.get(k)
            if v is not None and (not isinstance(v, (int, float)) or v < 0):
                penalty -= 0.3
    return max(-0.5, penalty)


def score_quality(item: dict[str, Any], *, now: str | None = None) -> dict[str, Any]:
    """Return 0–1 quality score with breakdown."""
    c = _completeness(item)
    f = _freshness(item, now=now)
    s = _source_cred(item)
    p = _anomaly_penalty(item)
    total = max(0.0, min(1.0, (c * 0.25 + f * 0.25 + s * 0.40 + p * 0.10)))
    return {
        "score": round(total, 3),
        "completeness": round(c, 3),
        "freshness": round(f, 3),
        "source_credibility": round(s, 3),
        "anomaly_penalty": round(p, 3),
        "quality_tier": _tier(total),
    }


def _tier(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.5:
        return "medium"
    if score >= 0.3:
        return "low"
    return "unusable"


QUALITY_THRESHOLD = 0.5  # below this, do not enter strong conclusions
