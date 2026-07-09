"""InfluenceOS Score v0.

The score is a deterministic, explainable first pass at the "preflight"
formula documented in the ledger:

    reach * attention * retention * persuasion * propagation * fit * value
    - risk

It is intentionally not a hidden model.  Every component records the signal it
used, missing dimensions are explicit, and later real publishing metrics can
calibrate the weights through governed learning candidates.
"""

from __future__ import annotations

import math
from typing import Any


INFLUENCE_SCORE_VERSION = "influenceos-score-v0.1"

POSITIVE_COMPONENTS: tuple[str, ...] = (
    "PlatformReachPotential",
    "HumanAttentionKernel",
    "RetentionDesign",
    "PersuasionScore",
    "SocialPropagation",
    "AccountFit",
    "BusinessValue",
)

DEFAULT_WEIGHTS: dict[str, float] = {
    "PlatformReachPotential": 0.14,
    "HumanAttentionKernel": 0.18,
    "RetentionDesign": 0.16,
    "PersuasionScore": 0.14,
    "SocialPropagation": 0.12,
    "AccountFit": 0.14,
    "BusinessValue": 0.12,
    "RiskPenalty": 0.18,
}

BUCKET_VALUES: dict[str, float] = {
    "zero": 0.05,
    "low": 0.28,
    "mid": 0.56,
    "high": 0.78,
    "spike": 0.94,
}

RISK_BUCKET_VALUES: dict[str, float] = {
    "zero": 0.0,
    "low": 0.25,
    "mid": 0.5,
    "high": 0.78,
    "spike": 0.95,
}


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


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


def _ratio(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    if number <= 1:
        return _clip01(number)
    if number <= 10:
        return _clip01(number / 10)
    return _clip01(number / 100)


def _avg_score(scores: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    values = [_ratio(scores.get(key)) for key in keys if key in scores]
    numeric = [value for value in values if value is not None]
    if not numeric:
        return None
    return round(sum(numeric) / len(numeric), 3)


def _metric_value(metric_labels: dict[str, Any] | None, dimension: str, *, risk: bool = False) -> float | None:
    labels = (metric_labels or {}).get("labels") or {}
    label = labels.get(dimension)
    if not isinstance(label, dict):
        return None
    bucket = str(label.get("bucket") or "").strip()
    table = RISK_BUCKET_VALUES if risk else BUCKET_VALUES
    if bucket in table:
        return table[bucket]
    value = _ratio(label.get("value"))
    return value


def _component(value: float, *, source: str, why: str) -> dict[str, Any]:
    return {
        "value": round(_clip01(value), 3),
        "source": source,
        "why": why,
    }


def build_influence_score(features: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compute an explainable InfluenceOS Score.

    Expected feature groups are optional:

    - ``metric_labels``: output of ``build_metric_labels`` after real metrics.
    - ``content_score``: latest rubric score dict, usually from content review.
    - ``preflight_scores``: pre-action production/account-fit scores.

    Missing signals are not faked.  The returned ``confidence`` reflects how
    much of the formula was actually supported by observable data.
    """

    features = dict(features or {})
    metric_labels = features.get("metric_labels") if isinstance(features.get("metric_labels"), dict) else {}
    content_score = features.get("content_score") if isinstance(features.get("content_score"), dict) else {}
    preflight_scores = features.get("preflight_scores") if isinstance(features.get("preflight_scores"), dict) else {}
    dimensions = content_score.get("scores") or content_score.get("dimensions") or {}
    if not isinstance(dimensions, dict):
        dimensions = {}

    components: dict[str, dict[str, Any]] = {}

    platform = _ratio(preflight_scores.get("platform_fit"))
    if platform is None:
        platform = _avg_score(dimensions, ("topic",))
        source = "content_score.topic" if platform is not None else ""
    else:
        source = "preflight.platform_fit"
    if platform is not None:
        components["PlatformReachPotential"] = _component(
            platform, source=source, why="平台题材/分发适配度",
        )

    attention = _metric_value(metric_labels, "attention")
    if attention is not None:
        components["HumanAttentionKernel"] = _component(
            attention, source="metric_labels.attention", why="真实曝光/播放体现用户是否停下",
        )
    else:
        attention = _avg_score(dimensions, ("hook", "emotion", "topic"))
        if attention is not None:
            components["HumanAttentionKernel"] = _component(
                attention, source="content_score.hook_emotion_topic", why="开头钩子、情绪和话题热度",
            )

    retention = _metric_value(metric_labels, "retention")
    if retention is not None:
        components["RetentionDesign"] = _component(
            retention, source="metric_labels.retention", why="真实完播/留存信号",
        )
    else:
        retention = _avg_score(dimensions, ("pacing", "density"))
        if retention is None:
            retention = _ratio(preflight_scores.get("production_feasibility"))
            source = "preflight.production_feasibility" if retention is not None else ""
        else:
            source = "content_score.pacing_density"
        if retention is not None:
            components["RetentionDesign"] = _component(
                retention, source=source, why="节奏、信息密度或生产可行性",
            )

    trust = _metric_value(metric_labels, "trust")
    if trust is not None:
        components["PersuasionScore"] = _component(
            trust, source="metric_labels.trust", why="真实互动/收藏/分享近似信任",
        )
    else:
        trust = _avg_score(dimensions, ("viewpoint", "density"))
        if trust is None:
            trust = _ratio(preflight_scores.get("evidence_strength"))
            source = "preflight.evidence_strength" if trust is not None else ""
        else:
            source = "content_score.viewpoint_density"
        if trust is not None:
            components["PersuasionScore"] = _component(
                trust, source=source, why="观点清晰度、证据密度或事实支撑",
            )

    propagation = _metric_value(metric_labels, "trust")
    if propagation is not None:
        components["SocialPropagation"] = _component(
            propagation, source="metric_labels.trust", why="互动传播势能",
        )
    else:
        propagation = _avg_score(dimensions, ("cta", "emotion"))
        if propagation is not None:
            components["SocialPropagation"] = _component(
                propagation, source="content_score.cta_emotion", why="互动引导与情绪扩散",
            )

    fit = _metric_value(metric_labels, "fit")
    if fit is not None:
        components["AccountFit"] = _component(
            fit, source="metric_labels.fit", why="真实目标受众匹配/粉丝转化",
        )
    else:
        fit = _ratio(preflight_scores.get("audience_fit") or preflight_scores.get("account_fit"))
        if fit is not None:
            components["AccountFit"] = _component(
                fit, source="preflight.audience_fit", why="账号受众与内容方向匹配",
            )

    value = _metric_value(metric_labels, "action")
    if value is not None:
        components["BusinessValue"] = _component(
            value, source="metric_labels.action", why="真实关注/点击/转化等行动信号",
        )
    else:
        value = _ratio(
            preflight_scores.get("business_value")
            or preflight_scores.get("memory_support")
            or preflight_scores.get("evidence_strength")
        )
        if value is not None:
            components["BusinessValue"] = _component(
                value, source="preflight.business_or_memory_support", why="商业目标/证据/记忆支持度",
            )

    risk_sources: list[dict[str, Any]] = []
    metric_risk = _metric_value(metric_labels, "risk", risk=True)
    if metric_risk is not None:
        risk_sources.append({"value": metric_risk, "source": "metric_labels.risk", "why": "真实负反馈/举报/取关"})
    risk_flags = content_score.get("risk_flags") or []
    if risk_flags:
        risk_sources.append({
            "value": min(1.0, 0.35 + 0.18 * len(risk_flags)),
            "source": "content_score.risk_flags",
            "why": f"内容评分风险项：{', '.join(str(item) for item in risk_flags[:5])}",
        })
    cost_safety = _ratio(preflight_scores.get("cost_safety"))
    if cost_safety is not None and cost_safety < 0.5:
        risk_sources.append({
            "value": 1.0 - cost_safety,
            "source": "preflight.cost_safety",
            "why": "成本/版权/合规安全不足",
        })
    risk_value = max((item["value"] for item in risk_sources), default=0.0)
    components["RiskPenalty"] = {
        "value": round(_clip01(risk_value), 3),
        "source": ", ".join(item["source"] for item in risk_sources) if risk_sources else "none",
        "why": "；".join(item["why"] for item in risk_sources) if risk_sources else "未观察到明确风险信号",
    }

    positive_values = [
        max(0.05, components[key]["value"])
        for key in POSITIVE_COMPONENTS
        if key in components
    ]
    positive_weight = sum(DEFAULT_WEIGHTS[key] for key in POSITIVE_COMPONENTS if key in components)
    if positive_values and positive_weight > 0:
        weighted_log = sum(
            DEFAULT_WEIGHTS[key] * math.log(max(0.05, components[key]["value"]))
            for key in POSITIVE_COMPONENTS
            if key in components
        ) / positive_weight
        multiplicative_core = math.exp(weighted_log)
    else:
        multiplicative_core = 0.0

    risk_penalty_points = components["RiskPenalty"]["value"] * DEFAULT_WEIGHTS["RiskPenalty"] * 100
    score = round(max(0.0, min(100.0, multiplicative_core * 100 - risk_penalty_points)), 1)
    missing = [key for key in POSITIVE_COMPONENTS if key not in components]
    source_groups: set[str] = set()
    for key, value in components.items():
        if key == "RiskPenalty" or not value.get("source"):
            continue
        source_groups.add(str(value["source"]).split(".", 1)[0])
    confidence = round(min(1.0, 0.12 * len(components) + 0.08 * len(source_groups)), 3)

    if score >= 72 and components["RiskPenalty"]["value"] < 0.35:
        decision = "strong_go"
    elif score >= 58 and components["RiskPenalty"]["value"] < 0.55:
        decision = "go_with_watchpoints"
    elif score >= 42:
        decision = "revise_before_action"
    else:
        decision = "do_not_open_or_publish_yet"

    return {
        "version": INFLUENCE_SCORE_VERSION,
        "score": score,
        "decision": decision,
        "components": components,
        "weights": DEFAULT_WEIGHTS,
        "missing_dimensions": missing,
        "confidence": confidence,
        "formula_note": "weighted multiplicative kernel over positive components minus explicit risk penalty",
    }


def build_asset_influence_score(store: Any, asset_id: str, *, metric_labels: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read the latest asset-side features and compute the score.

    This helper performs reads only; the core scoring function remains pure.
    """

    asset = store.get_content_asset(asset_id)
    content_scores = store.list_content_scores(asset_id=asset_id)
    preflights = store.list_preflight_records(asset_id=asset_id, limit=1)
    latest_score = content_scores[0] if content_scores else {}
    latest_preflight = preflights[0] if preflights else {}
    features = {
        "asset": {
            "id": asset.get("id"),
            "type": asset.get("type"),
            "platform": asset.get("platform"),
            "account_id": asset.get("account_id"),
            "topic": asset.get("topic"),
            "hook": asset.get("hook"),
        },
        "content_score": latest_score,
        "preflight_scores": latest_preflight.get("scores") or {},
        "metric_labels": metric_labels or {},
    }
    result = build_influence_score(features)
    result["feature_refs"] = {
        "asset_id": asset_id,
        "content_score_id": latest_score.get("id"),
        "preflight_id": latest_preflight.get("id"),
        "metric_label_version": (metric_labels or {}).get("version"),
    }
    return result
