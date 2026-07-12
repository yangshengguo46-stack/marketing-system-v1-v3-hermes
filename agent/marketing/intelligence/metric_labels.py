"""Comparable labels derived only from observed platform metrics.

Missing values remain missing.  In particular, the absence of a metric is
never converted to zero, because that would teach the account the wrong rule.
"""

from __future__ import annotations

from typing import Any


METRIC_LABEL_VERSION = "metric-labels-v0.2"


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _first_number(
    metrics: dict[str, Any], keys: tuple[str, ...]
) -> tuple[str, float] | None:
    for key in keys:
        if key not in metrics:
            continue
        value = _number(metrics.get(key))
        if value is not None:
            return key, value
    return None


def _bucket(value: float, *, low: float, mid: float, high: float) -> str:
    if value <= 0:
        return "zero"
    if value < low:
        return "low"
    if value < mid:
        return "mid"
    if value < high:
        return "high"
    return "spike"


def _rate_bucket(value: float) -> str:
    return _bucket(value, low=0.02, mid=0.08, high=0.18)


def build_metric_labels(metrics: dict[str, Any]) -> dict[str, Any]:
    """Map raw metrics to six explainable learning dimensions."""

    values = metrics if isinstance(metrics, dict) else {}
    labels: dict[str, Any] = {}

    attention = _first_number(values, ("views", "play_count", "impressions", "reach"))
    if attention:
        key, value = attention
        labels["attention"] = {
            "source_metric": key,
            "value": value,
            "bucket": _bucket(value, low=100, mid=1000, high=10000),
            "meaning": "用户是否停下或平台是否给到基础曝光",
        }

    retention = _first_number(
        values,
        ("completion_rate", "avg_completion_rate", "watch_completion_rate"),
    )
    if retention:
        key, value = retention
        labels["retention"] = {
            "source_metric": key,
            "value": value,
            "bucket": _rate_bucket(value),
            "meaning": "内容中段和结构是否撑得住",
        }

    trust = _first_number(
        values, ("engagement_rate", "save_rate", "collect_rate", "share_rate")
    )
    if trust:
        key, value = trust
        labels["trust"] = {
            "source_metric": key,
            "value": value,
            "bucket": _rate_bucket(value),
            "meaning": "内容是否带来信任、收藏、互动或传播",
        }
    elif any(key in values for key in ("likes", "comments", "shares", "collects", "saves")):
        weighted = (
            (_number(values.get("likes")) or 0.0)
            + 2.0 * (_number(values.get("comments")) or 0.0)
            + 3.0 * (_number(values.get("shares")) or 0.0)
            + 3.0 * ((_number(values.get("collects")) or 0.0) + (_number(values.get("saves")) or 0.0))
        )
        labels["trust"] = {
            "source_metric": "weighted_interactions",
            "value": weighted,
            "bucket": _bucket(weighted, low=10, mid=100, high=1000),
            "meaning": "无互动率时用加权互动量近似信任与传播",
        }

    action = _first_number(
        values,
        ("new_followers", "follows", "profile_visits", "leads", "clicks", "conversions"),
    )
    if action:
        key, value = action
        labels["action"] = {
            "source_metric": key,
            "value": value,
            "bucket": _bucket(value, low=1, mid=10, high=100),
            "meaning": "用户是否进一步行动",
        }

    fit = _first_number(
        values,
        ("target_audience_match", "target_comment_ratio", "follower_conversion_rate"),
    )
    if fit:
        key, value = fit
        labels["fit"] = {
            "source_metric": key,
            "value": value,
            "bucket": _rate_bucket(value),
            "meaning": "吸引来的是否是目标受众",
        }

    risk = _first_number(
        values,
        ("negative_feedback", "not_interested", "reports", "unfollows", "complaints"),
    )
    if risk:
        key, value = risk
        labels["risk"] = {
            "source_metric": key,
            "value": value,
            "bucket": _bucket(value, low=1, mid=5, high=20),
            "meaning": "负反馈或伤账号风险",
        }

    return {
        "version": METRIC_LABEL_VERSION,
        "labels": labels,
        "available_metrics": sorted(str(key) for key in values),
        "missing_dimensions": [
            item
            for item in ("attention", "retention", "trust", "action", "fit", "risk")
            if item not in labels
        ],
        "confidence": round(min(1.0, 0.18 * len(labels)), 3),
    }
