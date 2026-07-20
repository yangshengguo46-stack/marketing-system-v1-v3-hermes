"""Content-production level preflight for Marketing OS.

This is the *general* preflight layer.  It answers:

- Is this content worth starting for this user/account/platform?
- What is missing before we create a draft asset?
- Which lane should run next?

It owns only Marketing OS article and faceless-video lanes. Professional
human/digital-human/AI film production belongs to the standalone
``video-studio`` product and never enters this preflight runtime.
"""

from __future__ import annotations

from typing import Any

from agent.marketing.domains.content_policy import ContentProductionPolicy
from agent.marketing.platform_catalog import (
    platform_content_blueprints,
    platform_profile,
    platform_profile_confidence,
)

from .influence_score import build_influence_score
from .preflight_decision import build_preflight_decision


CONTENT_PREFLIGHT_VERSION = "content-production-preflight-v0.9"
VIDEO_TREATMENT_PREFLIGHT_VERSION = "content-production-preflight-v0.9.video-treatment-v1"
VIDEO_CUT_PREFLIGHT_VERSION = "content-production-preflight-v0.9.video-cut-v1"
ARTICLE_DRAFT_PREFLIGHT_VERSION = "content-production-preflight-v0.9.article-draft-v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, round(value, 3)))


def _evidence_items(params: dict[str, Any]) -> list[Any]:
    evidence = (
        params.get("evidence_refs")
        or params.get("evidence")
        or params.get("evidence_pack")
        or []
    )
    if isinstance(evidence, dict):
        evidence = evidence.get("items") or evidence.get("sources") or []
    if not isinstance(evidence, list):
        return []
    return [item for item in evidence if isinstance(item, (dict, str)) and item]


def _url_evidence_count(evidence: list[Any]) -> int:
    return sum(
        1
        for item in evidence
        if (isinstance(item, str) and item.startswith("evidence_"))
        or (
            isinstance(item, dict)
            and _text(item.get("url") or item.get("source_url"))
        )
    )


def _has_audience_context(params: dict[str, Any]) -> bool:
    plan = params.get("plan") if isinstance(params.get("plan"), dict) else {}
    gates = plan.get("gates") if isinstance(plan.get("gates"), list) else []
    for gate in gates:
        if isinstance(gate, dict) and gate.get("id") == "audience":
            return gate.get("status") == "ready"
    ctx = params.get("audience_context") or params.get("account_context") or {}
    if not isinstance(ctx, dict):
        return False
    useful_keys = {"target_reader", "target_audience", "pain_points", "promise", "business_goal"}
    return any(_text(ctx.get(key)) or bool(ctx.get(key)) for key in useful_keys)


def _has_current_strategy(plan: dict[str, Any]) -> bool:
    gates = plan.get("gates") if isinstance(plan.get("gates"), list) else []
    return any(
        isinstance(gate, dict)
        and gate.get("id") == "strategy"
        and gate.get("status") == "ready"
        for gate in gates
    )


def _memory_signal(params: dict[str, Any]) -> float:
    memories = params.get("memories") or params.get("memory_refs") or []
    if isinstance(memories, dict):
        memories = memories.get("items") or memories.get("ids") or []
    if not isinstance(memories, list):
        return 0.0
    return _clamp(min(0.75, 0.18 * len(memories)))


def _human_observer_context(params: dict[str, Any]) -> dict[str, Any] | None:
    """Accept an explicit core projection as read-only research context.

    Marketing-owned audience fields are deliberately not searched.  Human
    Observation is an upstream research system, not a hidden scoring feature.
    """

    value = params.get("human_observer_projection")
    if not isinstance(value, dict):
        return None
    if value.get("contract") != "human-observer-read-projection-v1":
        return None
    return {
        "contract": value["contract"],
        "namespace": _text(value.get("namespace")),
        "interpretation_count": len(value.get("interpretations") or []),
        "model_revision_count": len(value.get("model_revisions") or []),
        "authority": "read_only_no_score_or_writeback",
    }


def _platform_fit(plan: dict[str, Any]) -> float:
    platforms = plan.get("target_platforms") or []
    if not platforms:
        return 0.45
    return _clamp(
        sum(platform_profile_confidence(item) for item in platforms) / len(platforms)
    )


def _production_feasibility(kind: str, url_evidence: int, has_audience: bool) -> float:
    if kind == "article_soft":
        return _clamp(0.58 + (0.18 if url_evidence else 0.0) + (0.12 if has_audience else 0.0))
    if kind == "faceless_video":
        return _clamp(0.42 + (0.18 if url_evidence else 0.0) + (0.12 if has_audience else 0.0))
    if kind == "cross_platform_campaign":
        return _clamp(0.36 + (0.18 if url_evidence else 0.0) + (0.12 if has_audience else 0.0))
    return 0.45


def _prior_mode(
    *, has_audience: bool, knowledge_counts: dict[str, int], platforms: list[str]
) -> str:
    has_account_knowledge = knowledge_counts.get("account", 0) > 0
    has_public_prior = bool(platforms) or any(
        knowledge_counts.get(key, 0) > 0 for key in ("platform", "market", "content")
    )
    if has_audience and has_account_knowledge:
        return "account_calibrated"
    if has_audience or has_account_knowledge:
        return "hybrid_personal_and_public_prior"
    if has_public_prior:
        return "public_prior_cold_start"
    return "minimal_generic_prior"


def build_content_production_preflight(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a deterministic business/content preflight without writing state."""
    params = dict(params or {})
    plan = params.get("plan") if isinstance(params.get("plan"), dict) else None
    if not plan:
        plan = ContentProductionPolicy().plan(
            objective=_text(params.get("objective")),
            kind=_text(params.get("kind")) or "auto",
            platforms=params.get("platforms"),
            audience=_text(params.get("audience")),
            evidence_refs=[str(item) for item in (params.get("evidence_refs") or [])],
            constraints=params.get("constraints") or {},
            account_context=params.get("account_context") or {},
        )
    kind = str(plan["kind"])
    evidence = _evidence_items(params)
    url_evidence = _url_evidence_count(evidence)
    has_audience = _has_audience_context(params)
    has_current_strategy = _has_current_strategy(plan)
    memory_score = _memory_signal(params)
    sound_context = params.get("sound_context") if isinstance(params.get("sound_context"), dict) else {}
    sound_candidates = sound_context.get("candidates") if isinstance(sound_context.get("candidates"), list) else []
    knowledge_context = params.get("knowledge_context") if isinstance(params.get("knowledge_context"), dict) else {}
    knowledge_counts = {
        key: len(knowledge_context.get(key) or [])
        for key in ("platform", "market", "account", "content")
        if isinstance(knowledge_context.get(key) or [], list)
    }
    knowledge_support = _clamp(
        min(0.45, knowledge_counts.get("account", 0) * 0.12)
        + min(0.25, knowledge_counts.get("platform", 0) * 0.08)
        + min(0.2, knowledge_counts.get("market", 0) * 0.05)
        + min(0.15, knowledge_counts.get("content", 0) * 0.03)
    )
    human_observer_context = _human_observer_context(params)

    prior_mode = _prior_mode(
        has_audience=has_audience,
        knowledge_counts=knowledge_counts,
        platforms=list(plan.get("target_platforms") or []),
    )
    # Missing private history lowers confidence and publish eligibility, but it
    # must not turn a useful public platform/content prior into a hard stop.
    audience_fit = 0.78 if has_audience else (0.52 if prior_mode == "public_prior_cold_start" else 0.42)
    evidence_strength = _clamp(0.28 + min(0.45, 0.15 * url_evidence))
    platform_fit = _platform_fit(plan)
    platform_blueprints = platform_content_blueprints(plan.get("target_platforms") or [])
    platform_assessments = {
        platform: {
            "fit": platform_profile_confidence(platform),
            "guidance_status": blueprint["guidance_status"],
            "recommended_formats": blueprint["recommended_formats"],
            "discovery_mode": blueprint["discovery_mode"],
            "audience_intent": blueprint["audience_intent"],
        }
        for platform, blueprint in platform_blueprints.items()
    }
    production_feasibility = _production_feasibility(kind, url_evidence, has_audience)
    cost_safety = 0.82
    if kind in {"faceless_video", "cross_platform_campaign"}:
        cost_safety = 0.68

    scores = {
        "audience_fit": _clamp(audience_fit),
        "evidence_strength": evidence_strength,
        "platform_fit": _clamp(platform_fit),
        "production_feasibility": production_feasibility,
        "cost_safety": _clamp(cost_safety),
        "memory_support": memory_score,
        "knowledge_support": knowledge_support,
        "strategy_fit": 0.82 if has_current_strategy else 0.24,
    }
    if kind == "faceless_video":
        top_sound_score = max(
            [float(item.get("selection_score") or 0) for item in sound_candidates if isinstance(item, dict)],
            default=0.0,
        )
        scores["sound_fit"] = _clamp(top_sound_score)
        base_overall = (
            scores["audience_fit"] * 0.18
            + scores["evidence_strength"] * 0.17
            + scores["platform_fit"] * 0.13
            + scores["production_feasibility"] * 0.14
            + scores["cost_safety"] * 0.08
            + scores["memory_support"] * 0.06
            + scores["sound_fit"] * 0.11
            + scores["strategy_fit"] * 0.13
        )
    else:
        base_overall = (
            scores["audience_fit"] * 0.19
            + scores["evidence_strength"] * 0.19
            + scores["platform_fit"] * 0.15
            + scores["production_feasibility"] * 0.16
            + scores["cost_safety"] * 0.09
            + scores["memory_support"] * 0.07
            + scores["strategy_fit"] * 0.15
        )
    # Knowledge is confidence coverage, not proof that a draft is good.  It
    # may reduce confidence when absent, but generic principles cannot inflate
    # a weak content score merely by existing in the database.
    scores["knowledge_confidence_factor"] = _clamp(
        0.9 + scores["knowledge_support"] * 0.1
    )
    overall = _clamp(base_overall * scores["knowledge_confidence_factor"])
    scores["overall"] = overall

    blockers: list[str] = []
    warnings: list[str] = []
    if not has_audience:
        warnings.append("personal_audience_context_missing_using_public_prior")
    if not has_current_strategy:
        warnings.append("account_strategy_missing_or_stale_exploratory_draft_only")
    if kind in {"article_soft", "faceless_video", "cross_platform_campaign"} and url_evidence == 0:
        blockers.append("url_evidence_missing")
    if kind in {"faceless_video", "cross_platform_campaign"} and "stock_material" in (plan.get("capabilities") or {}):
        warnings.append("material_license_check_required")
    if kind == "faceless_video" and not sound_candidates:
        warnings.append("bgm_trend_evidence_missing")
    for platform, assessment in platform_assessments.items():
        if str(assessment.get("guidance_status") or "").startswith("generic_"):
            warnings.append(f"platform_guidance_unverified:{platform}")
    influence_score = build_influence_score({
        "preflight_scores": scores,
        "content_score": params.get("content_score") if isinstance(params.get("content_score"), dict) else {},
        "metric_labels": params.get("metric_labels") if isinstance(params.get("metric_labels"), dict) else {},
        "weights": params.get("influence_weights"),
    })
    preflight_decision = build_preflight_decision(
        influence_score,
        stage="production_draft",
        context={
            "selected_lane": kind,
            "blockers": blockers,
            "warnings": warnings,
            "exploratory_public_prior": prior_mode
            in {"public_prior_cold_start", "minimal_generic_prior"},
        },
    )

    status = preflight_decision["status"]
    decision = {
        **preflight_decision,
        "blockers": blockers,
        "warnings": preflight_decision["warnings"],
        "selected_lane": kind,
        "publish_eligible": bool(
            has_current_strategy and (plan.get("account_scope") or {}).get("connected") is True
        ),
    }

    return {
        "status": status,
        "scope": "content_business_preflight",
        "formula_version": CONTENT_PREFLIGHT_VERSION,
        "objective": plan["objective"],
        "kind": kind,
        "target_platforms": plan.get("target_platforms") or [],
        "account_id": params.get("account_id") or (plan.get("account_scope") or {}).get("account_id"),
        "plan_status": plan.get("status"),
        "scores": scores,
        "influence_score": influence_score,
        "preflight_decision": preflight_decision,
        "decision": decision,
        "platform_assessments": platform_assessments,
        "human_observer_context": human_observer_context,
        "input": {
            "objective": plan["objective"],
            "kind": kind,
            "target_platforms": plan.get("target_platforms") or [],
            "account_id": params.get("account_id") or (plan.get("account_scope") or {}).get("account_id"),
            "evidence_count": len(evidence),
            "url_evidence_count": url_evidence,
            "has_audience_context": has_audience,
            "has_current_strategy": has_current_strategy,
            "memory_support": memory_score,
            "sound_candidate_count": len(sound_candidates),
            "sound_candidate_ids": [
                str(item.get("sound_id"))
                for item in sound_candidates[:10]
                if isinstance(item, dict) and item.get("sound_id")
            ],
            "knowledge_entry_ids": [
                str(item.get("id"))
                for base in ("account", "platform", "market", "content")
                for item in (knowledge_context.get(base) or [])[:20]
                if isinstance(item, dict) and item.get("id")
            ],
            "knowledge_counts": knowledge_counts,
            "prior_mode": prior_mode,
            "platform_assessments": platform_assessments,
            "influence_calibration_id": _text(params.get("influence_calibration_id")),
        },
        "separation": {
            "general_preflight_owns": [
                "audience_fit",
                "evidence_strength",
                "platform_fit",
                "production_feasibility",
                "cost_safety",
                "sound_fit_for_short_video",
                "governed_knowledge_support",
                "read_only_human_observer_context_without_score_effect",
                "content_lane_go_no_go",
            ],
            "cold_start_rule": (
                "Public platform, market, benchmark and content priors may authorize a reversible "
                "draft. Missing private account history lowers confidence and never authorizes publishing."
            ),
            "external_product": "video-studio",
            "rule": (
                "Professional human, digital-human, and AI film production is "
                "not scored, planned, or persisted by Marketing OS."
            ),
        },
        "plan_summary": {
            "kind_label": plan.get("kind_label"),
            "tool_sequence": plan.get("execution_order") or [],
            "recommended_next_action": plan.get("recommended_next_action"),
        },
    }


def build_video_treatment_preflight(
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one platform-native shooting/editing treatment in the general engine.

    This is a second *stage* of the same Marketing Preflight owner, not a second
    prediction system.  Public platform/content/market knowledge is a valid
    cold-start prior; account receipts only increase personalization confidence.
    """

    params = dict(params or {})
    treatment = params.get("treatment")
    if not isinstance(treatment, dict):
        raise ValueError("video treatment preflight requires treatment")
    platform = _text(params.get("platform") or treatment.get("platform"))
    if not platform:
        raise ValueError("video treatment preflight requires platform")
    profile = platform_profile(platform)
    knowledge = (
        params.get("knowledge_context")
        if isinstance(params.get("knowledge_context"), dict)
        else {}
    )
    counts = {
        key: len(knowledge.get(key) or [])
        for key in ("platform", "market", "account", "content")
        if isinstance(knowledge.get(key) or [], list)
    }
    account_context = (
        params.get("account_context")
        if isinstance(params.get("account_context"), dict)
        else {}
    )
    has_audience = _has_audience_context({"account_context": account_context})
    prior_mode = _prior_mode(
        has_audience=has_audience,
        knowledge_counts=counts,
        platforms=[platform],
    )

    shots = treatment.get("shot_list") if isinstance(treatment.get("shot_list"), list) else []
    beats = treatment.get("beat_sheet") if isinstance(treatment.get("beat_sheet"), list) else []
    claim_map = (
        treatment.get("claim_evidence_map")
        if isinstance(treatment.get("claim_evidence_map"), list)
        else []
    )
    evidence_refs = {
        str(item).strip() for item in (params.get("evidence_refs") or []) if str(item).strip()
    }
    target_duration = _positive_number(treatment.get("target_duration"))
    shot_duration = sum(
        _positive_number(item.get("duration"))
        for item in shots
        if isinstance(item, dict)
    )
    duration_alignment = (
        max(0.0, 1.0 - abs(shot_duration - target_duration) / max(target_duration, 1.0))
        if target_duration and shots
        else 0.0
    )
    hook = treatment.get("hook")
    hook_contract = (
        treatment.get("hook_hypothesis")
        if isinstance(treatment.get("hook_hypothesis"), dict)
        else {}
    )
    first_three_seconds = _text(
        hook_contract.get("first_three_seconds")
        or hook_contract.get("first_3_seconds")
        or hook
    )
    complete_shots = [
        item
        for item in shots
        if isinstance(item, dict)
        and _text(item.get("purpose"))
        and _text(item.get("visual_query"))
        and _text(item.get("on_screen_text"))
    ]
    mapped_claims = [
        item
        for item in claim_map
        if isinstance(item, dict)
        and _text(item.get("claim"))
        and _claim_refs(item) & evidence_refs
    ]
    unmapped_claims = [
        item
        for item in claim_map
        if isinstance(item, dict)
        and _text(item.get("claim"))
        and not (_claim_refs(item) & evidence_refs)
    ]
    platform_contract = all(
        _text(treatment.get(field))
        for field in ("aspect_ratio", "pacing", "caption_style", "cta")
    )
    sound_strategy = (
        treatment.get("sound_strategy")
        if isinstance(treatment.get("sound_strategy"), dict)
        else {}
    )
    grounding_review = (
        params.get("grounding_review")
        if isinstance(params.get("grounding_review"), dict)
        else {}
    )
    grounding_reviewed = isinstance(grounding_review.get("go"), bool)
    grounding_ok = grounding_review.get("go") is True
    public_prior_support = _clamp(
        0.46
        + min(0.18, counts.get("platform", 0) * 0.06)
        + min(0.16, counts.get("market", 0) * 0.04)
        + min(0.16, counts.get("content", 0) * 0.025)
    )
    personal_support = _clamp(
        (0.55 if has_audience else 0.0) + min(0.45, counts.get("account", 0) * 0.12)
    )
    evidence_strength = _clamp(
        0.3 + min(0.4, len(evidence_refs) * 0.12) + min(0.25, len(mapped_claims) * 0.08)
    )
    treatment_feasibility = _clamp(
        duration_alignment * 0.3
        + (len(complete_shots) / max(len(shots), 1)) * 0.35
        + (0.2 if beats else 0.0)
        + (0.15 if _text(treatment.get("voiceover_script")) else 0.0)
    )
    platform_fit = _clamp(
        platform_profile_confidence(platform) * 0.55
        + (0.25 if platform_contract else 0.0)
        + public_prior_support * 0.2
    )
    audience_fit = _clamp(
        0.72 if has_audience else 0.5 + public_prior_support * 0.12
    )
    sound_fit = _clamp(
        0.25
        + (0.25 if _text(sound_strategy.get("voice_style")) else 0.0)
        + (0.2 if _text(sound_strategy.get("music_role")) else 0.0)
        + (0.15 if sound_strategy.get("sfx_cues") else 0.0)
    )
    preflight_scores = {
        "audience_fit": audience_fit,
        "evidence_strength": evidence_strength,
        "platform_fit": platform_fit,
        "production_feasibility": treatment_feasibility,
        "cost_safety": 0.82,
        "memory_support": personal_support,
        "knowledge_support": public_prior_support,
        "strategy_fit": 0.76 if has_audience else 0.56,
        "sound_fit": sound_fit,
    }
    content_scores = {
        "topic": platform_fit * 10,
        "hook": (0.82 if len(first_three_seconds) >= 8 else 0.45) * 10,
        "emotion": (0.7 if _text(hook_contract.get("tension")) else 0.5) * 10,
        "pacing": duration_alignment * 10,
        "density": evidence_strength * 10,
        "viewpoint": (0.8 if _text(treatment.get("thesis")) else 0.4) * 10,
        "cta": (0.75 if _text(treatment.get("cta")) else 0.3) * 10,
        "sound_fit": sound_fit * 10,
    }
    influence = build_influence_score(
        {
            "preflight_scores": preflight_scores,
            "content_score": {"scores": content_scores},
            "weights": params.get("influence_weights"),
        }
    )
    blockers: list[str] = []
    warnings: list[str] = []
    if len(first_three_seconds) < 8:
        blockers.append("hook_first_three_seconds_missing")
    if len(shots) < 2 or len(complete_shots) != len(shots):
        blockers.append("treatment_shot_contract_incomplete")
    if not beats:
        blockers.append("treatment_beat_sheet_missing")
    if target_duration <= 0 or duration_alignment < 0.72:
        blockers.append("duration_plan_mismatch")
    if not platform_contract:
        blockers.append("platform_contract_incomplete")
    if evidence_refs and not mapped_claims:
        blockers.append("treatment_claim_evidence_missing")
    elif unmapped_claims:
        blockers.append("treatment_contains_unverified_claims")
    if grounding_reviewed and not grounding_ok:
        blockers.append("treatment_evidence_grounding_failed")
    if not has_audience:
        warnings.append("personal_model_missing_public_prior_cold_start")
    if profile.get("guidance_status", "").startswith("generic_"):
        warnings.append("platform_guidance_requires_current_research")
    decision = build_preflight_decision(
        influence,
        stage="treatment_review",
        context={
            "selected_lane": "faceless_video",
            "blockers": blockers,
            "warnings": warnings,
        },
    )
    return {
        "status": decision["status"],
        "scope": "video_treatment_preflight",
        "formula_version": VIDEO_TREATMENT_PREFLIGHT_VERSION,
        "platform": platform,
        "account_id": _text(params.get("account_id")) or None,
        "prior_mode": prior_mode,
        "public_prior": {
            "support": public_prior_support,
            "platform_profile_version": profile.get("version"),
            "platform_guidance_status": profile.get("guidance_status"),
            "knowledge_counts": counts,
            "knowledge_entry_ids": [
                str(item.get("id"))
                for base in ("platform", "market", "content")
                for item in (knowledge.get(base) or [])
                if isinstance(item, dict) and item.get("id")
            ][:60],
        },
        "personal_prior": {
            "available": bool(has_audience or counts.get("account", 0)),
            "support": personal_support,
            "knowledge_entry_ids": [
                str(item.get("id"))
                for item in (knowledge.get("account") or [])
                if isinstance(item, dict) and item.get("id")
            ][:30],
        },
        "scores": preflight_scores,
        "treatment_features": {
            "hook_first_three_seconds": first_three_seconds,
            "shot_count": len(shots),
            "complete_shot_count": len(complete_shots),
            "beat_count": len(beats),
            "mapped_claim_count": len(mapped_claims),
            "unmapped_claim_count": len(unmapped_claims),
            "target_duration": target_duration,
            "shot_duration": round(shot_duration, 3),
            "duration_alignment": round(duration_alignment, 3),
            "platform_contract_complete": platform_contract,
            "evidence_grounding_reviewed": grounding_reviewed,
            "evidence_grounding_passed": grounding_ok if grounding_reviewed else None,
            "evidence_grounding_findings": sum(
                len(grounding_review.get(field) or [])
                for field in (
                    "unsupported_claims",
                    "stance_conflicts",
                    "invented_personal_proof",
                    "invented_offers",
                )
            ),
        },
        "influence_score": influence,
        "preflight_decision": decision,
        "decision": decision,
        "prediction_contract": {
            "output": "range_with_confidence_not_point_promise",
            "cold_start": prior_mode in {"public_prior_cold_start", "minimal_generic_prior"},
            "exact_views_allowed": False,
            "calibration_required_for_account_ranges": True,
        },
    }


def create_video_treatment_preflight(
    store: Any, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Persist an immutable platform-treatment evaluation in the canonical store."""

    params = dict(params or {})
    result = build_video_treatment_preflight(params)
    record = store.create_preflight(
        user_id=_text(params.get("user_id") or params.get("__user_id")) or "default",
        account_id=_text(result.get("account_id")),
        platform=result["platform"],
        plan_id=_text(params.get("plan_id")),
        session_id=_text(params.get("session_id") or params.get("__task_id")),
        formula_version=result["formula_version"],
        input={
            "scope": result["scope"],
            "platform": result["platform"],
            "prior_mode": result["prior_mode"],
            "public_prior": result["public_prior"],
            "personal_prior": result["personal_prior"],
            "treatment_features": result["treatment_features"],
        },
        scores=result["scores"],
        decision={
            **result["decision"],
            "influence_score": result["influence_score"],
            "preflight_decision": result["preflight_decision"],
            "prediction_contract": result["prediction_contract"],
        },
    )
    return {**result, "preflight_id": record["id"], "preflight_record": record}


def build_video_cut_preflight(
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate a rendered cut against its approved platform treatment.

    A multimodal reviewer supplies observations; this function owns the
    deterministic decision and never treats model prose as a render receipt.
    This is the cut-review stage of the canonical Marketing Preflight engine,
    not a separate prediction system.
    """

    params = dict(params or {})
    treatment = params.get("treatment")
    review = params.get("visual_review")
    technical = params.get("technical_qa")
    if not isinstance(treatment, dict):
        raise ValueError("video cut preflight requires approved treatment")
    if not isinstance(review, dict):
        raise ValueError("video cut preflight requires visual review")
    if not isinstance(technical, dict):
        raise ValueError("video cut preflight requires technical QA")
    platform = _text(params.get("platform") or treatment.get("platform"))
    if not platform:
        raise ValueError("video cut preflight requires platform")

    technical_ready = _text(technical.get("disposition")) == "ready"
    hook_visible = _review_pass(review, "hook_first_three_seconds_visible")
    treatment_parity = _review_pass(review, "treatment_parity")
    captions_readable = _review_pass(review, "caption_readability")
    material_relevance = _review_pass(review, "material_relevance")
    evidence_alignment = _review_pass(review, "evidence_alignment")
    audio_required = params.get("audio_expected") is True
    audio_present = _review_pass(review, "audio_present")
    audio_sync = _review_pass(review, "audio_sync")
    cta_present = _review_pass(review, "ending_cta_present")
    playable = _review_pass(review, "playable")
    issues = [
        item
        for item in (review.get("issues") or [])
        if isinstance(item, dict) and _text(item.get("code"))
    ]
    severe_issues = [
        item
        for item in issues
        if _text(item.get("severity")).lower() in {"critical", "high"}
    ]
    visual_score = _clamp(
        sum(
            1.0 if value else 0.0
            for value in (
                playable,
                hook_visible,
                treatment_parity,
                captions_readable,
                material_relevance,
                evidence_alignment,
                cta_present,
            )
        )
        / 7
    )
    audio_score = 1.0 if not audio_required else _clamp(
        (0.55 if audio_present else 0.0) + (0.45 if audio_sync else 0.0)
    )
    preflight_scores = {
        "audience_fit": _review_score(review, "audience_fit", 0.62),
        "evidence_strength": _clamp(
            0.25 + (0.55 if evidence_alignment else 0.0) + (0.2 if material_relevance else 0.0)
        ),
        "platform_fit": _review_score(
            review, "platform_fit", 0.7 if treatment_parity else 0.35
        ),
        "production_feasibility": _clamp(
            (0.35 if technical_ready else 0.0)
            + (0.25 if playable else 0.0)
            + visual_score * 0.25
            + audio_score * 0.15
        ),
        "cost_safety": 0.82,
        "memory_support": _review_score(review, "account_fit", 0.45),
        "knowledge_support": _review_score(
            review, "evidence_alignment", 0.7 if evidence_alignment else 0.3
        ),
        "strategy_fit": _clamp(
            0.25 + (0.45 if treatment_parity else 0.0) + (0.2 if cta_present else 0.0)
        ),
        "sound_fit": audio_score,
    }
    content_scores = {
        "topic": preflight_scores["platform_fit"] * 10,
        "hook": (0.86 if hook_visible else 0.25) * 10,
        "emotion": _review_score(review, "emotional_pull", 0.55) * 10,
        "pacing": _review_score(review, "pacing", 0.55) * 10,
        "density": _review_score(review, "information_density", 0.58) * 10,
        "viewpoint": (0.78 if treatment_parity else 0.38) * 10,
        "cta": (0.78 if cta_present else 0.25) * 10,
        "sound_fit": audio_score * 10,
    }
    influence = build_influence_score(
        {
            "preflight_scores": preflight_scores,
            "content_score": {"scores": content_scores},
            "weights": params.get("influence_weights"),
        }
    )
    blockers: list[str] = []
    if not technical_ready:
        blockers.append("cut_technical_qa_failed")
    if not playable:
        blockers.append("cut_not_playable")
    if not hook_visible:
        blockers.append("cut_hook_contract_failed")
    if not treatment_parity:
        blockers.append("cut_treatment_parity_failed")
    if not captions_readable:
        blockers.append("cut_caption_readability_failed")
    if not material_relevance:
        blockers.append("cut_material_relevance_failed")
    if not evidence_alignment:
        blockers.append("cut_evidence_alignment_failed")
    if audio_required and (not audio_present or not audio_sync):
        blockers.append("cut_audio_contract_failed")
    if not cta_present:
        blockers.append("cut_cta_contract_failed")
    if severe_issues:
        blockers.append("cut_has_high_severity_review_issues")
    warnings = [
        f"cut_review_issue:{_text(item.get('code'))}"
        for item in issues
        if item not in severe_issues
    ]
    decision = build_preflight_decision(
        influence,
        stage="cut_review",
        context={
            "selected_lane": "faceless_video",
            "blockers": blockers,
            "warnings": warnings,
        },
    )
    return {
        "status": decision["status"],
        "scope": "video_cut_preflight",
        "formula_version": VIDEO_CUT_PREFLIGHT_VERSION,
        "platform": platform,
        "account_id": _text(params.get("account_id")) or None,
        "scores": preflight_scores,
        "cut_features": {
            "technical_disposition": technical.get("disposition"),
            "playable": playable,
            "hook_first_three_seconds_visible": hook_visible,
            "treatment_parity": treatment_parity,
            "caption_readability": captions_readable,
            "material_relevance": material_relevance,
            "evidence_alignment": evidence_alignment,
            "audio_expected": audio_required,
            "audio_present": audio_present,
            "audio_sync": audio_sync,
            "ending_cta_present": cta_present,
            "issue_count": len(issues),
            "high_severity_issue_count": len(severe_issues),
        },
        "issues": issues,
        "influence_score": influence,
        "preflight_decision": decision,
        "decision": decision,
        "prediction_contract": {
            "output": "range_with_confidence_not_point_promise",
            "exact_views_allowed": False,
            "observed_cut_required": True,
            "publication_still_requires_human_effect_approval": True,
        },
    }


def create_video_cut_preflight(
    store: Any, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Persist an immutable cut review in the canonical preflight store."""

    params = dict(params or {})
    result = build_video_cut_preflight(params)
    record = store.create_preflight(
        user_id=_text(params.get("user_id") or params.get("__user_id")) or "default",
        account_id=_text(result.get("account_id")),
        platform=result["platform"],
        plan_id=_text(params.get("plan_id")),
        session_id=_text(params.get("session_id") or params.get("__task_id")),
        formula_version=result["formula_version"],
        input={
            "scope": result["scope"],
            "platform": result["platform"],
            "final_video_asset_id": _text(params.get("final_video_asset_id")),
            "cut_features": result["cut_features"],
            "issues": result["issues"],
        },
        scores=result["scores"],
        decision={
            **result["decision"],
            "influence_score": result["influence_score"],
            "preflight_decision": result["preflight_decision"],
            "prediction_contract": result["prediction_contract"],
        },
    )
    return {**result, "preflight_id": record["id"], "preflight_record": record}


def build_article_draft_preflight(
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate one platform-native article draft in the same preflight owner."""

    params = dict(params or {})
    article = params.get("article")
    review = params.get("draft_review")
    if not isinstance(article, dict):
        raise ValueError("article draft preflight requires article")
    if not isinstance(review, dict):
        raise ValueError("article draft preflight requires draft review")
    platform = _text(params.get("platform") or article.get("platform"))
    if not platform:
        raise ValueError("article draft preflight requires platform")
    passes = {
        key: _review_pass(review, key)
        for key in (
            "platform_native",
            "factual_claims_traceable",
            "hook_effective",
            "structure_complete",
            "cta_present",
            "deliverable_complete",
        )
    }
    issues = [
        item
        for item in (review.get("issues") or [])
        if isinstance(item, dict) and _text(item.get("code"))
    ]
    severe = [
        item
        for item in issues
        if _text(item.get("severity")).lower() in {"critical", "high"}
    ]
    evidence_refs = {
        _text(ref)
        for item in (article.get("claim_evidence_map") or [])
        if isinstance(item, dict)
        for ref in (item.get("evidence_refs") or [])
        if _text(ref)
    }
    preflight_scores = {
        "audience_fit": _review_score(review, "audience_fit", 0.58),
        "evidence_strength": _review_score(
            review,
            "evidence_strength",
            0.78 if passes["factual_claims_traceable"] and evidence_refs else 0.35,
        ),
        "platform_fit": _review_score(
            review, "platform_fit", 0.78 if passes["platform_native"] else 0.35
        ),
        "production_feasibility": _clamp(
            sum(1 for value in passes.values() if value) / len(passes)
        ),
        "cost_safety": 0.92,
        "memory_support": _review_score(review, "account_fit", 0.45),
        "knowledge_support": _review_score(review, "knowledge_fit", 0.55),
        "strategy_fit": _review_score(review, "strategy_fit", 0.62),
    }
    content_scores = {
        "topic": preflight_scores["platform_fit"] * 10,
        "hook": _review_score(review, "hook", 0.78 if passes["hook_effective"] else 0.3) * 10,
        "emotion": _review_score(review, "emotion", 0.55) * 10,
        "pacing": _review_score(review, "structure", 0.72 if passes["structure_complete"] else 0.35) * 10,
        "density": preflight_scores["evidence_strength"] * 10,
        "viewpoint": _review_score(review, "viewpoint", 0.68) * 10,
        "cta": (0.78 if passes["cta_present"] else 0.25) * 10,
    }
    influence = build_influence_score(
        {
            "preflight_scores": preflight_scores,
            "content_score": {"scores": content_scores},
            "weights": params.get("influence_weights"),
        }
    )
    blockers = [
        f"article_{key}_failed" for key, passed in passes.items() if not passed
    ]
    if severe:
        blockers.append("article_has_high_severity_review_issues")
    warnings = [
        f"article_review_issue:{_text(item.get('code'))}"
        for item in issues
        if item not in severe
    ]
    decision = build_preflight_decision(
        influence,
        stage="production_draft",
        context={
            "selected_lane": "article_soft",
            "blockers": blockers,
            "warnings": warnings,
        },
    )
    return {
        "status": decision["status"],
        "scope": "article_draft_preflight",
        "formula_version": ARTICLE_DRAFT_PREFLIGHT_VERSION,
        "platform": platform,
        "account_id": _text(params.get("account_id")) or None,
        "scores": preflight_scores,
        "draft_features": {
            **passes,
            "mapped_evidence_count": len(evidence_refs),
            "issue_count": len(issues),
            "high_severity_issue_count": len(severe),
        },
        "issues": issues,
        "influence_score": influence,
        "preflight_decision": decision,
        "decision": decision,
        "prediction_contract": {
            "output": "range_with_confidence_not_point_promise",
            "exact_impressions_allowed": False,
            "publication_still_requires_human_effect_approval": True,
        },
    }


def create_article_draft_preflight(
    store: Any, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Persist an immutable platform article review in the canonical store."""

    params = dict(params or {})
    result = build_article_draft_preflight(params)
    record = store.create_preflight(
        user_id=_text(params.get("user_id") or params.get("__user_id")) or "default",
        account_id=_text(result.get("account_id")),
        platform=result["platform"],
        plan_id=_text(params.get("plan_id")),
        session_id=_text(params.get("session_id") or params.get("__task_id")),
        formula_version=result["formula_version"],
        input={
            "scope": result["scope"],
            "platform": result["platform"],
            "draft_features": result["draft_features"],
            "issues": result["issues"],
        },
        scores=result["scores"],
        decision={
            **result["decision"],
            "influence_score": result["influence_score"],
            "preflight_decision": result["preflight_decision"],
            "prediction_contract": result["prediction_contract"],
        },
    )
    return {**result, "preflight_id": record["id"], "preflight_record": record}


def _positive_number(value: Any) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, number)


def _review_pass(value: dict[str, Any], key: str) -> bool:
    raw = value.get(key)
    if isinstance(raw, bool):
        return raw
    return _text(raw).lower() in {"pass", "passed", "ready", "true", "yes"}


def _review_score(value: dict[str, Any], key: str, default: float) -> float:
    scores = value.get("scores") if isinstance(value.get("scores"), dict) else {}
    raw = scores.get(key)
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return _clamp(default)
    return _clamp(number / 10 if number > 1 else number)


def _claim_refs(value: dict[str, Any]) -> set[str]:
    raw = value.get("evidence_refs")
    if raw is None:
        raw = [value.get("evidence_ref")] if value.get("evidence_ref") else []
    if not isinstance(raw, list):
        return set()
    return {str(item).strip() for item in raw if str(item).strip()}


def create_content_production_preflight(store: Any, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build and persist a content-production preflight record."""
    params = dict(params or {})
    result = build_content_production_preflight(params)
    target_platforms = result.get("target_platforms") or []
    preflight = store.create_preflight(
        user_id=_text(params.get("__user_id") or params.get("user_id")) or "default",
        account_id=_text(result.get("account_id")),
        platform=target_platforms[0] if target_platforms else None,
        plan_id=_text(params.get("plan_id") or (params.get("plan") or {}).get("plan_id")),
        session_id=_text(params.get("session_id") or params.get("__task_id")),
        formula_version=CONTENT_PREFLIGHT_VERSION,
        input=result["input"],
        scores=result["scores"],
        decision={
            **result["decision"],
            "influence_score": result["influence_score"],
            "preflight_decision": result["preflight_decision"],
            "separation_rule": result["separation"]["rule"],
        },
    )
    return {
        **result,
        "preflight_id": preflight["id"],
        "preflight_record": preflight,
    }
