"""Content-production level preflight for Marketing OS.

This is the *general* preflight layer.  It answers:

- Is this content worth starting for this user/account/platform?
- What is missing before we create a draft asset?
- Which lane should run next?

It deliberately does not judge high-end video cinematography or film quality.
Premium video projects delegate that to ``video_core.high_end_preflight``.
"""

from __future__ import annotations

from typing import Any

from .content_production import build_content_production_plan
from .influence_score import build_influence_score
from .preflight_decision import build_preflight_decision


CONTENT_PREFLIGHT_VERSION = "content-production-preflight-v0.1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, round(value, 3)))


def _evidence_items(params: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = params.get("evidence") or params.get("evidence_pack") or []
    if isinstance(evidence, dict):
        evidence = evidence.get("items") or evidence.get("sources") or []
    if not isinstance(evidence, list):
        return []
    return [item for item in evidence if isinstance(item, dict)]


def _url_evidence_count(evidence: list[dict[str, Any]]) -> int:
    return sum(1 for item in evidence if _text(item.get("url") or item.get("source_url")))


def _has_audience_context(params: dict[str, Any]) -> bool:
    if _text(params.get("account_id")):
        return True
    ctx = params.get("audience_context") or params.get("account_context") or {}
    if not isinstance(ctx, dict):
        return False
    useful_keys = {"target_reader", "target_audience", "pain_points", "promise", "business_goal"}
    return any(_text(ctx.get(key)) or bool(ctx.get(key)) for key in useful_keys)


def _memory_signal(params: dict[str, Any]) -> float:
    memories = params.get("memories") or params.get("memory_refs") or []
    if isinstance(memories, dict):
        memories = memories.get("items") or memories.get("ids") or []
    if not isinstance(memories, list):
        return 0.0
    return _clamp(min(0.75, 0.18 * len(memories)))


def _platform_fit(plan: dict[str, Any]) -> float:
    platforms = plan.get("target_platforms") or []
    kind = plan.get("kind")
    if not platforms:
        return 0.45
    if kind == "article_soft" and set(platforms).issubset({"zhihu", "wechat_official"}):
        return 0.82
    if kind in {"faceless_video", "premium_human_video"} and any(
        item in {"douyin", "wechat_channels", "bilibili", "xiaohongshu", "kuaishou"}
        for item in platforms
    ):
        return 0.78
    return 0.62


def _production_feasibility(kind: str, plan_status: str, url_evidence: int, has_audience: bool) -> float:
    if kind == "article_soft":
        return _clamp(0.58 + (0.18 if url_evidence else 0.0) + (0.12 if has_audience else 0.0))
    if kind == "faceless_video":
        return _clamp(0.42 + (0.18 if url_evidence else 0.0) + (0.12 if has_audience else 0.0))
    if plan_status == "blocked_on_provider_calibration":
        return 0.32
    return 0.45


def build_content_production_preflight(params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a deterministic business/content preflight without writing state."""
    params = dict(params or {})
    plan = build_content_production_plan(params)
    kind = str(plan["kind"])
    evidence = _evidence_items(params)
    url_evidence = _url_evidence_count(evidence)
    has_audience = _has_audience_context(params)
    memory_score = _memory_signal(params)

    audience_fit = 0.78 if has_audience else 0.34
    evidence_strength = _clamp(0.28 + min(0.45, 0.15 * url_evidence))
    platform_fit = _platform_fit(plan)
    production_feasibility = _production_feasibility(kind, str(plan.get("status")), url_evidence, has_audience)
    cost_safety = 0.82
    if kind == "faceless_video":
        cost_safety = 0.68
    if kind == "premium_human_video":
        cost_safety = 0.28

    scores = {
        "audience_fit": _clamp(audience_fit),
        "evidence_strength": evidence_strength,
        "platform_fit": _clamp(platform_fit),
        "production_feasibility": production_feasibility,
        "cost_safety": _clamp(cost_safety),
        "memory_support": memory_score,
    }
    overall = _clamp(
        scores["audience_fit"] * 0.24
        + scores["evidence_strength"] * 0.22
        + scores["platform_fit"] * 0.18
        + scores["production_feasibility"] * 0.18
        + scores["cost_safety"] * 0.10
        + scores["memory_support"] * 0.08
    )
    scores["overall"] = overall

    blockers: list[str] = []
    warnings: list[str] = []
    if not has_audience:
        blockers.append("audience_context_missing")
    if kind in {"article_soft", "faceless_video"} and url_evidence == 0:
        blockers.append("url_evidence_missing")
    if kind == "faceless_video" and "stock_material" in (plan.get("capability_pool") or {}).get("required", []):
        warnings.append("material_license_check_required")
    if kind == "premium_human_video":
        blockers.append("video_previsualization_agent_required")
        if plan.get("status") == "blocked_on_provider_calibration":
            blockers.append("provider_calibration_required")

    video_project = params.get("video_project") or params.get("project")
    video_previsualization: dict[str, Any]
    if kind == "premium_human_video" and video_project:
        from engine.video_core.high_end_preflight import preflight_high_end_video_project

        video_previsualization = preflight_high_end_video_project(video_project)
    elif kind == "premium_human_video":
        video_previsualization = {
            "agent": "high_end_video_previsualization_agent",
            "scope": "film_previsualization",
            "status": "not_run",
            "required": True,
            "reason": "premium_human_video needs film-level animatic/project preflight",
        }
    else:
        video_previsualization = {
            "agent": "high_end_video_previsualization_agent",
            "scope": "film_previsualization",
            "status": "not_required_for_lane",
            "required": False,
        }

    influence_score = build_influence_score({
        "preflight_scores": scores,
        "content_score": params.get("content_score") if isinstance(params.get("content_score"), dict) else {},
        "metric_labels": params.get("metric_labels") if isinstance(params.get("metric_labels"), dict) else {},
    })
    preflight_decision = build_preflight_decision(
        influence_score,
        stage="production_draft",
        context={
            "selected_lane": kind,
            "blockers": blockers,
            "warnings": warnings,
            "force_video_previsualization": True,
            "video_previsualization_status": video_previsualization["status"],
        },
    )

    status = preflight_decision["status"]
    decision = {
        **preflight_decision,
        "blockers": blockers,
        "warnings": preflight_decision["warnings"],
        "selected_lane": kind,
        "video_previsualization_status": video_previsualization["status"],
    }

    return {
        "status": status,
        "scope": "content_business_preflight",
        "formula_version": CONTENT_PREFLIGHT_VERSION,
        "objective": plan["objective"],
        "kind": kind,
        "target_platforms": plan.get("target_platforms") or [],
        "account_id": plan.get("account_id"),
        "plan_status": plan.get("status"),
        "scores": scores,
        "influence_score": influence_score,
        "preflight_decision": preflight_decision,
        "decision": decision,
        "input": {
            "objective": plan["objective"],
            "kind": kind,
            "target_platforms": plan.get("target_platforms") or [],
            "account_id": plan.get("account_id"),
            "evidence_count": len(evidence),
            "url_evidence_count": url_evidence,
            "has_audience_context": has_audience,
            "memory_support": memory_score,
        },
        "separation": {
            "general_preflight_owns": [
                "audience_fit",
                "evidence_strength",
                "platform_fit",
                "production_feasibility",
                "cost_safety",
                "content_lane_go_no_go",
            ],
            "high_end_video_previsualization_agent_owns": [
                "script_to_screen_coherence",
                "shot_feasibility",
                "visual_continuity",
                "pacing_and_animatic",
                "sound_timing",
                "budget_gate_readiness",
            ],
            "rule": "premium_human_video must not collapse film previsualization into the general Marketing OS score.",
        },
        "video_previsualization": video_previsualization,
        "plan_summary": {
            "kind_label": plan.get("kind_label"),
            "tool_sequence": plan.get("tool_sequence") or [],
            "recommended_next_action": plan.get("recommended_next_action"),
        },
    }


def create_content_production_preflight(store: Any, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build and persist a content-production preflight record."""
    params = dict(params or {})
    result = build_content_production_preflight(params)
    target_platforms = result.get("target_platforms") or []
    receipt_refs = params.get("receipt_refs") or []
    if not isinstance(receipt_refs, list):
        receipt_refs = []

    task_id = _text(params.get("__task_id") or params.get("task_id")) or None
    if task_id:
        try:
            store.get_task(task_id)
        except KeyError:
            task_id = None

    preflight = store.create_preflight_record(
        user_id=_text(params.get("__user_id") or params.get("user_id")) or "default",
        account_id=result.get("account_id"),
        platform=target_platforms[0] if target_platforms else None,
        asset_id=_text(params.get("asset_id")) or None,
        task_id=task_id,
        formula_version=CONTENT_PREFLIGHT_VERSION,
        input=result["input"],
        scores=result["scores"],
        decision={
            **result["decision"],
            "influence_score": result["influence_score"],
            "preflight_decision": result["preflight_decision"],
            "separation_rule": result["separation"]["rule"],
            "video_previsualization_status": result["video_previsualization"]["status"],
        },
        receipt_refs=[str(item) for item in receipt_refs],
        status="created",
    )
    return {
        **result,
        "preflight_id": preflight["id"],
        "preflight_record": preflight,
    }
