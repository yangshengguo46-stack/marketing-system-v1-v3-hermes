"""Pre-publish social reaction scenarios for Marketing OS content.

The Agent may propose likely commenter cohorts and synthetic comment examples,
but Hermes owns the contract.  The output is an explicitly uncertain,
account-scoped hypothesis for later comparison with real comment observations.
It never predicts an identifiable person or stores generated text as a receipt.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


REACTION_SIMULATION_VERSION = "social-reaction-simulation-v0.3"

VALID_STANCES = {
    "supportive",
    "experience_sharing",
    "questioning",
    "skeptical",
    "oppositional",
    "action_seeking",
    "off_target",
}
VALID_EXISTENCE_STRATEGIES = {"preserve", "confirm", "expand", "continue", "unknown"}
VALID_NEED_PROJECTIONS = {
    "physiological",
    "safety",
    "belonging",
    "esteem",
    "self_actualization",
    "transcendence",
    "unknown",
}
VALID_COGNITIVE_PROJECTIONS = {"Se", "Si", "Ne", "Ni", "Te", "Ti", "Fe", "Fi", "unknown"}
VALID_COLLECTIVE_MECHANISMS = {
    "identity_convergence",
    "emotional_contagion",
    "normative_pressure",
    "suggestibility",
    "deindividuation",
    "polarization",
    "imitation",
    "authority_transfer",
    "rumor_cascade",
    "collective_effervescence",
    "unknown",
}
VALID_LIKELIHOOD_BANDS = {"low", "medium", "high", "unknown"}
VALID_COHORT_RELATIONS = {"target", "adjacent", "opposed", "off_target", "unknown"}

_PII_PATTERNS = (
    re.compile(r"https?://|www\.", re.IGNORECASE),
    re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
    re.compile(r"@[A-Za-z0-9_\-\u4e00-\u9fff]{2,}"),
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"(?:微信|vx|v信|wechat)\s*[:：]?\s*[A-Za-z][-_A-Za-z0-9]{5,}", re.IGNORECASE),
)


def build_social_reaction_simulation(
    *,
    scenarios: Any,
    audience_context: Any,
    content_context: dict[str, Any],
    platforms: list[str],
    evidence_refs: list[str],
) -> dict[str, Any]:
    """Validate and freeze anonymous commenter-cohort hypotheses."""

    audience = _audience_summary(audience_context)
    raw_scenarios = scenarios if isinstance(scenarios, list) else []
    if not raw_scenarios:
        return {
            "version": REACTION_SIMULATION_VERSION,
            "status": "missing",
            "scope": "anonymous_cohort_scenarios_not_individual_prediction",
            "scenarios": [],
            "audience_basis": audience,
            "platforms": _strings(platforms, field="platforms", limit=8, item_limit=80),
            "data_gaps": ["reaction_scenarios_missing"],
            "simulation_notice": (
                "发布前假设，不是真实评论、具体用户预测或心理诊断；"
                "只有发布后的平台观察才能形成事实回执。"
            ),
            "retro_contract": _retro_contract(),
        }
    if len(raw_scenarios) < 3:
        raise ValueError("reaction_scenarios requires at least 3 items")
    if len(raw_scenarios) > 8:
        raise ValueError("reaction_scenarios exceeds 8 items")

    normalized = [
        _normalize_scenario(
            item,
            index=index,
            content_context=content_context,
            evidence_refs=evidence_refs,
        )
        for index, item in enumerate(raw_scenarios)
    ]
    scenario_ids = [item["id"] for item in normalized]
    status = "audience_hypothesis_backed" if audience["has_structured_audience"] else "uncalibrated"
    data_gaps = list(audience["data_gaps"])
    represented = {item["stance"] for item in normalized}
    if not represented & {"skeptical", "oppositional"}:
        data_gaps.append("skeptical_or_oppositional_scenario_missing")
    if not represented & {"questioning", "action_seeking"}:
        data_gaps.append("question_or_action_scenario_missing")

    body = {
        "version": REACTION_SIMULATION_VERSION,
        "status": status,
        "scope": "anonymous_cohort_scenarios_not_individual_prediction",
        "platforms": _strings(platforms, field="platforms", limit=8, item_limit=80),
        "content_context": {
            key: _text(content_context.get(key), field=key, limit=300, required=False)
            for key in ("title", "topic", "hook", "objective")
        },
        "audience_basis": audience,
        "scenarios": normalized,
        "scenario_ids": scenario_ids,
        "data_gaps": list(dict.fromkeys(data_gaps)),
        "simulation_notice": (
            "所有评论样例均为合成情景，只表示可能的主题和立场；"
            "不得展示为真人原话、精确概率、具体用户画像或发布后事实。"
        ),
        "retro_contract": _retro_contract(),
    }
    body["simulation_id"] = "srs_" + hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return body


def normalize_social_reaction_observation(
    value: Any, *, simulation: dict[str, Any]
) -> dict[str, Any] | None:
    """Accept only anonymous aggregate reaction clusters from a trusted Provider."""

    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("social_reaction_observation must be an object")
    forbidden_keys = {
        "comments", "raw_comments", "comment_texts", "users", "handles", "profiles",
        "user_ids", "avatars", "profile_urls", "contact_details",
    }
    leaked_keys = sorted(forbidden_keys & set(value))
    if leaked_keys:
        raise ValueError(
            "social reaction observation must be anonymous aggregates: "
            + ", ".join(leaked_keys)
        )
    sample_size = value.get("sample_size")
    if isinstance(sample_size, bool) or not isinstance(sample_size, int) or sample_size < 0:
        raise ValueError("social_reaction_observation.sample_size must be a non-negative integer")
    known_ids = {
        str(item.get("id"))
        for item in simulation.get("scenarios") or []
        if isinstance(item, dict) and item.get("id")
    }
    matches: list[dict[str, Any]] = []
    matched_ids: set[str] = set()
    for item in value.get("scenario_matches") or []:
        if not isinstance(item, dict):
            raise ValueError("scenario_matches entries must be objects")
        scenario_id = _text(item.get("scenario_id"), field="scenario_id", limit=120, required=True)
        if scenario_id not in known_ids:
            raise ValueError(f"unknown reaction scenario id: {scenario_id}")
        if scenario_id in matched_ids:
            raise ValueError(f"duplicate reaction scenario id: {scenario_id}")
        matched_ids.add(scenario_id)
        count = item.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("scenario match count must be a non-negative integer")
        observed_themes = _strings(
            item.get("observed_themes"),
            field="observed_themes",
            limit=8,
            item_limit=160,
        )
        _reject_identity_text(observed_themes, field="observed_themes")
        matches.append(
            {
                "scenario_id": scenario_id,
                "count": count,
                "observed_themes": observed_themes,
            }
        )
    if len(matches) > 8:
        raise ValueError("scenario_matches exceeds 8 items")

    unexpected: list[dict[str, Any]] = []
    for item in value.get("unexpected_clusters") or []:
        if not isinstance(item, dict):
            raise ValueError("unexpected_clusters entries must be objects")
        count = item.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("unexpected cluster count must be a non-negative integer")
        theme = _text(item.get("theme"), field="theme", limit=200, required=True)
        _reject_identity_text([theme], field="unexpected cluster theme")
        unexpected.append(
            {
                "stance": _enum(item.get("stance"), VALID_STANCES, field="stance"),
                "need_projection": _enum(
                    item.get("need_projection") or "unknown",
                    VALID_NEED_PROJECTIONS,
                    field="need_projection",
                ),
                "cognitive_projection": _enum(
                    item.get("cognitive_projection") or "unknown",
                    VALID_COGNITIVE_PROJECTIONS,
                    field="cognitive_projection",
                ),
                "collective_mechanism": _enum(
                    item.get("collective_mechanism") or "unknown",
                    VALID_COLLECTIVE_MECHANISMS,
                    field="collective_mechanism",
                ),
                "existence_strategy": _enum(
                    item.get("existence_strategy")
                    or item.get("existence_direction")
                    or "unknown",
                    VALID_EXISTENCE_STRATEGIES,
                    field="existence_strategy",
                ),
                "theme": theme,
                "count": count,
            }
        )
    if len(unexpected) > 12:
        raise ValueError("unexpected_clusters exceeds 12 items")

    question_patterns = _strings(
        value.get("question_patterns"), field="question_patterns", limit=12, item_limit=240
    )
    objection_patterns = _strings(
        value.get("objection_patterns"), field="objection_patterns", limit=12, item_limit=240
    )
    _reject_identity_text(question_patterns, field="question_patterns")
    _reject_identity_text(objection_patterns, field="objection_patterns")
    return {
        "version": "social-reaction-observation-v0.3",
        "aggregation": "anonymous_clusters_only",
        "sample_size": sample_size,
        "scenario_matches": matches,
        "unexpected_clusters": unexpected,
        "question_patterns": question_patterns,
        "objection_patterns": objection_patterns,
        "data_gaps": _strings(value.get("data_gaps"), field="data_gaps", limit=20, item_limit=240),
        "privacy_notice": "不保存昵称、头像、主页、联系方式或可还原的逐条评论。",
    }


def compare_social_reaction_simulation(
    simulation: Any, observation: Any
) -> dict[str, Any]:
    """Compare frozen scenarios with anonymous post-publish clusters."""

    if not isinstance(simulation, dict) or not simulation.get("scenarios"):
        return {
            "status": "prediction_unavailable",
            "matched_scenario_ids": [],
            "missed_scenario_ids": [],
            "unexpected_clusters": [],
        }
    if not isinstance(observation, dict):
        return {
            "status": "observation_unavailable",
            "matched_scenario_ids": [],
            "missed_scenario_ids": [],
            "unexpected_clusters": [],
        }
    scenario_by_id = {
        str(item.get("id")): item
        for item in simulation.get("scenarios") or []
        if isinstance(item, dict) and item.get("id")
    }
    predicted = list(scenario_by_id)
    matched = [
        str(item.get("scenario_id"))
        for item in observation.get("scenario_matches") or []
        if isinstance(item, dict) and int(item.get("count") or 0) > 0
    ]
    matched = list(dict.fromkeys(matched))
    projection_retro = _projection_chain_retro(
        scenario_by_id=scenario_by_id,
        matches=observation.get("scenario_matches") or [],
        unexpected=observation.get("unexpected_clusters") or [],
    )
    return {
        "status": "compared",
        "prediction_version": simulation.get("version"),
        "observation_version": observation.get("version"),
        "sample_size": observation.get("sample_size"),
        "matched_scenario_ids": matched,
        "missed_scenario_ids": [item for item in predicted if item not in matched],
        "unexpected_clusters": list(observation.get("unexpected_clusters") or []),
        "coverage": round(len(matched) / len(predicted), 4) if predicted else None,
        "question_patterns": list(observation.get("question_patterns") or []),
        "objection_patterns": list(observation.get("objection_patterns") or []),
        "data_gaps": list(observation.get("data_gaps") or []),
        "projection_chain_retro": projection_retro,
        "causal_warning": "评论聚类只能校准反应场，不证明内容触发了某种心理或社会因果。",
    }


def _projection_chain_retro(
    *,
    scenario_by_id: dict[str, dict[str, Any]],
    matches: list[Any],
    unexpected: list[Any],
) -> dict[str, Any]:
    dimensions = (
        ("need_projection", None),
        ("cognitive_projection", None),
        ("existence_strategy", "existence_direction"),
        ("collective_mechanism", None),
    )
    compared: dict[str, Any] = {}
    for field, legacy_field in dimensions:
        predicted_counts: dict[str, int] = {}
        matched_counts: dict[str, int] = {}
        unexpected_counts: dict[str, int] = {}
        observed_counts: dict[str, int] = {}
        for scenario in scenario_by_id.values():
            projection = str(
                scenario.get(field)
                or (scenario.get(legacy_field) if legacy_field else None)
                or "unknown"
            )
            predicted_counts[projection] = predicted_counts.get(projection, 0) + 1
        for item in matches:
            if not isinstance(item, dict) or int(item.get("count") or 0) <= 0:
                continue
            scenario = scenario_by_id.get(str(item.get("scenario_id"))) or {}
            projection = str(
                scenario.get(field)
                or (scenario.get(legacy_field) if legacy_field else None)
                or "unknown"
            )
            matched_counts[projection] = matched_counts.get(projection, 0) + 1
            observed_counts[projection] = (
                observed_counts.get(projection, 0) + int(item.get("count") or 0)
            )
        for item in unexpected:
            if not isinstance(item, dict):
                continue
            projection = str(
                item.get(field)
                or (item.get(legacy_field) if legacy_field else None)
                or "unknown"
            )
            count = int(item.get("count") or 0)
            unexpected_counts[projection] = unexpected_counts.get(projection, 0) + count
            observed_counts[projection] = observed_counts.get(projection, 0) + count
        compared[field] = {
            "predicted_scenario_counts": predicted_counts,
            "matched_scenario_counts": matched_counts,
            "unexpected_cluster_counts": unexpected_counts,
            "observed_comment_counts": observed_counts,
            "scenario_coverage": {
                projection: round(matched_counts.get(projection, 0) / count, 4)
                for projection, count in predicted_counts.items()
                if count > 0
            },
        }
    return {
        "status": "compared_as_anonymous_projection_clusters",
        "mechanism_chain": [
            "need_projection",
            "cognitive_projection",
            "existence_strategy",
            "collective_mechanism",
            "observable_reaction",
        ],
        "dimensions": compared,
        "interpretation_limit": (
            "A match calibrates a bundled projection hypothesis. It neither observes existence "
            "itself nor reveals a person's inner need or cognitive process."
        ),
    }


def _normalize_scenario(
    value: Any,
    *,
    index: int,
    content_context: dict[str, Any],
    evidence_refs: list[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("each reaction scenario must be an object")
    forbidden_keys = {
        "user_id", "account_id", "platform_user_id", "handle", "profile_url",
        "phone", "email", "wechat_id", "real_name",
    }
    leaked_keys = sorted(forbidden_keys & set(value))
    if leaked_keys:
        raise ValueError("reaction scenario cannot identify a person: " + ", ".join(leaked_keys))

    cohort = _text(value.get("cohort"), field="cohort", limit=160, required=True)
    stance = _enum(value.get("stance"), VALID_STANCES, field="stance")
    need_projection = _enum(
        value.get("need_projection") or "unknown",
        VALID_NEED_PROJECTIONS,
        field="need_projection",
    )
    cognitive_projection = _enum(
        value.get("cognitive_projection") or "unknown",
        VALID_COGNITIVE_PROJECTIONS,
        field="cognitive_projection",
    )
    existence_strategy = _enum(
        value.get("existence_strategy") or value.get("existence_direction") or "unknown",
        VALID_EXISTENCE_STRATEGIES,
        field="existence_strategy",
    )
    collective_mechanism = _enum(
        value.get("collective_mechanism") or "unknown",
        VALID_COLLECTIVE_MECHANISMS,
        field="collective_mechanism",
    )
    likelihood_band = _enum(
        value.get("likelihood_band") or "unknown",
        VALID_LIKELIHOOD_BANDS,
        field="likelihood_band",
    )
    cohort_relation = _enum(
        value.get("cohort_relation") or "unknown",
        VALID_COHORT_RELATIONS,
        field="cohort_relation",
    )
    trigger = _text(value.get("trigger"), field="trigger", limit=300, required=True)
    rationale = _text(value.get("rationale"), field="rationale", limit=500, required=True)
    themes = _strings(
        value.get("likely_comment_themes"),
        field="likely_comment_themes",
        limit=6,
        item_limit=160,
        required=True,
    )
    examples = _strings(
        value.get("synthetic_comment_examples"),
        field="synthetic_comment_examples",
        limit=4,
        item_limit=300,
        required=True,
    )
    _reject_identity_text(
        [cohort, trigger, rationale, *themes, *examples],
        field="reaction scenario",
    )

    supplied_refs = _strings(
        value.get("evidence_basis"), field="evidence_basis", limit=20, item_limit=500
    )
    known_refs = set(str(item) for item in evidence_refs)
    unknown_refs = sorted(set(supplied_refs) - known_refs)
    if unknown_refs:
        raise ValueError("reaction scenario contains unknown evidence refs: " + ", ".join(unknown_refs))

    response_opportunity = _text(
        value.get("response_opportunity"),
        field="response_opportunity",
        limit=500,
        required=False,
    )
    risk = _text(value.get("risk"), field="risk", limit=500, required=False)
    disconfirming_signals = _strings(
        value.get("disconfirming_signals"),
        field="disconfirming_signals",
        limit=6,
        item_limit=240,
        required=True,
    )
    _reject_identity_text(
        [response_opportunity, risk, *disconfirming_signals],
        field="reaction scenario",
    )

    normalized = {
        "cohort": cohort,
        "cohort_relation": cohort_relation,
        "stance": stance,
        "need_projection": need_projection,
        "cognitive_projection": cognitive_projection,
        "existence_strategy": existence_strategy,
        "collective_mechanism": collective_mechanism,
        "likelihood_band": likelihood_band,
        "trigger": trigger,
        "rationale": rationale,
        "likely_comment_themes": themes,
        "synthetic_comment_examples": examples,
        "response_opportunity": response_opportunity,
        "risk": risk,
        "evidence_basis": supplied_refs,
        "disconfirming_signals": disconfirming_signals,
        "synthetic": True,
    }
    identity = {
        "index": index,
        "content": {key: content_context.get(key) for key in ("title", "topic", "hook")},
        "scenario": normalized,
    }
    normalized["id"] = "reaction_" + hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:14]
    return normalized


def _audience_summary(value: Any) -> dict[str, Any]:
    audience = value if isinstance(value, dict) else {}
    segments = _strings(audience.get("segments"), field="audience.segments", limit=12, item_limit=200)
    pains = _strings(audience.get("pains"), field="audience.pains", limit=12, item_limit=240)
    scenarios = _strings(audience.get("scenarios"), field="audience.scenarios", limit=12, item_limit=240)
    jobs = _strings(audience.get("jobs"), field="audience.jobs", limit=12, item_limit=240)
    trust_barriers = _strings(
        audience.get("trust_barriers"), field="audience.trust_barriers", limit=12, item_limit=240
    )
    desired_outcomes = _strings(
        audience.get("desired_outcomes"), field="audience.desired_outcomes", limit=12, item_limit=240
    )
    data_gaps = _strings(audience.get("data_gaps"), field="audience.data_gaps", limit=20, item_limit=240)
    has_structured = bool(segments or pains or scenarios or jobs or trust_barriers or desired_outcomes)
    if not has_structured:
        data_gaps.append("structured_audience_hypothesis_missing")
    return {
        "hypothesis_id": _text(audience.get("id"), field="audience.id", limit=160, required=False) or None,
        "version": audience.get("version") if isinstance(audience.get("version"), int) else None,
        "status": _text(audience.get("status"), field="audience.status", limit=80, required=False) or None,
        "segments": segments,
        "pains": pains,
        "scenarios": scenarios,
        "jobs": jobs,
        "trust_barriers": trust_barriers,
        "desired_outcomes": desired_outcomes,
        "has_structured_audience": has_structured,
        "data_gaps": list(dict.fromkeys(data_gaps)),
    }


def _retro_contract() -> dict[str, Any]:
    return {
        "mutable": False,
        "compare_after_publish": [
            "observed_comment_stance_clusters",
            "observed_comment_theme_clusters",
            "question_and_objection_patterns",
            "target_vs_off_target_audience_signals",
            "anonymous_collective_mechanism_clusters",
        ],
        "calibration_rule": (
            "只比较聚合主题、立场和匿名群体信号；"
            "不得把平台昵称、头像或个人主页写入学习候选。"
        ),
    }


def _enum(value: Any, allowed: set[str], *, field: str) -> str:
    text = str(value or "").strip()
    if text not in allowed:
        raise ValueError(f"unsupported {field}: {text}")
    return text


def _strings(
    value: Any,
    *,
    field: str,
    limit: int,
    item_limit: int,
    required: bool = False,
) -> list[str]:
    if value is None:
        items: list[Any] = []
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        raise ValueError(f"{field} must be a list")
    if len(items) > limit:
        raise ValueError(f"{field} exceeds {limit} items")
    result = [_text(item, field=field, limit=item_limit, required=True) for item in items]
    result = list(dict.fromkeys(result))
    if required and not result:
        raise ValueError(f"{field} is required")
    return result


def _text(value: Any, *, field: str, limit: int, required: bool) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if required and not text:
        raise ValueError(f"{field} is required")
    if len(text) > limit:
        raise ValueError(f"{field} exceeds {limit} characters")
    return text


def _reject_identity_text(values: list[str], *, field: str) -> None:
    if any(pattern.search(text) for text in values for pattern in _PII_PATTERNS):
        raise ValueError(f"{field} cannot contain handles, contact details, or URLs")
