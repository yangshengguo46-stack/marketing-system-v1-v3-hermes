"""Pre-publish prediction contracts for content assets.

Legacy prediction fields such as ``expected_views`` are still kept for the
existing retrospective reconciler.  This module adds the product-level v2
language that matches the learning labels emitted after publishing:

attention / retention / trust / action / account_fit / risk.

The point is not to pretend we have a trained model.  The point is to make the
blind prediction structurally comparable with the receipt labels that will
arrive later, so misses can calibrate the right part of the system.
"""

from __future__ import annotations

from typing import Any


PREDICTION_V2_VERSION = "prepublish-prediction-v2.0"

DIMENSIONS = ("attention", "retention", "trust", "action", "account_fit", "sound", "risk")


def _bounded(value: float, *, low: float = 0.0, high: float = 1.0) -> float:
    return round(max(low, min(high, value)), 4)


def _scale_score(scores: dict[str, Any], *keys: str, fallback: float = 0.5) -> float:
    values: list[float] = []
    for key in keys:
        value = scores.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            values.append(max(0.0, min(10.0, float(value))) / 10.0)
    if not values:
        return fallback
    return round(sum(values) / len(values), 4)


def _range(mid: float, *, spread: float = 0.35, floor: float = 0.0, cap: float | None = None) -> dict[str, float]:
    low = mid * (1.0 - spread)
    high = mid * (1.0 + spread)
    if cap is not None:
        low = min(low, cap)
        mid = min(mid, cap)
        high = min(high, cap)
    return {
        "low": round(max(floor, low), 4),
        "mid": round(max(floor, mid), 4),
        "high": round(max(floor, high), 4),
    }


def _confidence_value(confidence: str) -> float:
    return {
        "none": 0.0,
        "low": 0.32,
        "medium": 0.58,
        "high": 0.78,
    }.get(str(confidence or "").lower(), 0.32)


def build_prediction_dimensions(
    *,
    kind: str,
    confidence: str,
    platforms: list[str],
    scores: dict[str, Any],
    evidence_ready: bool,
    legacy_metrics: dict[str, Any],
    basis: list[str],
) -> dict[str, Any]:
    """Return six-dimensional v2 prediction while preserving legacy metrics."""

    confidence_score = _confidence_value(confidence)
    hook = _scale_score(scores, "hook", "topic", "emotion", fallback=0.45)
    retention = _scale_score(scores, "pacing", "density", fallback=0.42)
    trust = _scale_score(scores, "viewpoint", "density", fallback=0.42)
    action = _scale_score(scores, "cta", "viewpoint", fallback=0.38)
    fit = _scale_score(scores, "topic", "viewpoint", fallback=0.45)
    sound = _scale_score(scores, "sound_fit", "bgm_fit", "sound", fallback=0.0)
    risk_raw = _scale_score(scores, "title_bait_risk", "controversy_overload_risk", fallback=0.25)
    evidence_factor = 1.0 if evidence_ready else 0.45

    expected_views = legacy_metrics.get("expected_views") or {"low": 0, "mid": 0, "high": 0}
    expected_completion = (
        legacy_metrics.get("expected_completion_rate")
        or legacy_metrics.get("expected_read_completion_rate")
        or _range(retention * evidence_factor, spread=0.28, cap=0.95)
    )
    expected_trust_rate = (
        legacy_metrics.get("expected_save_or_share_rate")
        or legacy_metrics.get("expected_engagement_rate")
        or _range(trust * 0.08 * evidence_factor, spread=0.45, cap=0.35)
    )
    expected_action_rate = legacy_metrics.get("expected_action_rate") or _range(action * 0.025 * evidence_factor, spread=0.5, cap=0.18)
    expected_fit_rate = legacy_metrics.get("expected_target_audience_fit") or _range(fit * 0.45 * evidence_factor, spread=0.35, cap=0.95)
    expected_risk_rate = legacy_metrics.get("expected_negative_feedback_rate") or _range(max(0.002, risk_raw * 0.025), spread=0.55, cap=0.2)

    platform_note = "、".join(platforms) if platforms else "未指定平台"
    return {
        "version": PREDICTION_V2_VERSION,
        "kind": kind,
        "dimensions": {
            "attention": {
                "label": "能不能让用户停下/平台给初始曝光",
                "expected_metric": "views",
                "range": expected_views,
                "score_hint": _bounded(hook * evidence_factor),
                "drivers": ["hook", "topic", "platform_format"],
                "platforms": platforms,
            },
            "retention": {
                "label": "内容结构能不能撑住阅读/完播",
                "expected_metric": "completion_rate",
                "range": expected_completion,
                "score_hint": _bounded(retention * evidence_factor),
                "drivers": ["pacing", "density", "structure"],
            },
            "trust": {
                "label": "用户会不会相信、收藏、转发或认真互动",
                "expected_metric": "save_or_share_rate" if kind == "article_soft" else "engagement_rate",
                "range": expected_trust_rate,
                "score_hint": _bounded(trust * evidence_factor),
                "drivers": ["evidence", "viewpoint", "source_traceability"],
            },
            "action": {
                "label": "用户会不会关注、私信、访问主页或进入下一步",
                "expected_metric": "action_rate",
                "range": expected_action_rate,
                "score_hint": _bounded(action * evidence_factor),
                "drivers": ["cta", "business_relevance", "promise_clarity"],
            },
            "account_fit": {
                "label": "是否服务当前账号受众和长期定位",
                "expected_metric": "target_audience_fit",
                "range": expected_fit_rate,
                "score_hint": _bounded(fit * evidence_factor),
                "drivers": ["audience_context", "account_positioning", "platform_gene"],
            },
            "sound": {
                "label": "声音是否帮助停留、情绪进入和平台传播",
                "expected_metric": "sound_lift_hypothesis",
                "range": _range(sound, spread=0.45, cap=1.0),
                "score_hint": _bounded(sound),
                "drivers": ["platform_sound_id", "sound_momentum", "opening_cue", "mix_role", "rights_status"],
                "causal_warning": "单条作品只能形成相关性；因果增益需要同账号匹配内容或 A/B 变体校准。",
            },
            "risk": {
                "label": "是否存在标题党、硬广、版权、负反馈或伤账号风险",
                "expected_metric": "negative_feedback_rate",
                "range": expected_risk_rate,
                "score_hint": _bounded(risk_raw),
                "drivers": ["title_bait_risk", "controversy_overload_risk", "license_risk"],
                "lower_is_better": True,
            },
        },
        "confidence": confidence,
        "confidence_score": confidence_score,
        "basis": list(dict.fromkeys([*basis, f"platforms={platform_note}", "prediction_dimensions_v2"])),
        "missing_dimensions": (["trust", "account_fit"] if not evidence_ready else [])
        + (["sound"] if kind == "faceless_video" and sound <= 0 else []),
        "note": "v2 dimensions align pre-publish predictions with post-publish metric labels; legacy expected_* fields remain for retro compatibility.",
    }


def attach_prediction_dimensions(
    prediction: dict[str, Any],
    *,
    kind: str,
    scores: dict[str, Any],
    evidence_ready: bool,
) -> dict[str, Any]:
    """Return a copy of a legacy prediction enriched with v2 dimensions."""

    prediction = dict(prediction or {})
    basis = [str(item) for item in prediction.get("basis", [])]
    platforms = [str(item) for item in prediction.get("platforms", [])]
    dimensions = build_prediction_dimensions(
        kind=kind,
        confidence=str(prediction.get("confidence") or "low"),
        platforms=platforms,
        scores=scores,
        evidence_ready=evidence_ready,
        legacy_metrics=prediction,
        basis=basis,
    )
    prediction["prediction_version"] = PREDICTION_V2_VERSION
    prediction["prediction_dimensions"] = dimensions
    return prediction
