"""High-end video previsualization preflight.

This module belongs to ``video_core`` on purpose.  It evaluates whether a film
project canvas is ready to become an animatic or paid production work.  It does
not know anything about Marketing OS accounts, platform trends, publishing, or
memory.  The desktop agent may *call* this module, but must not absorb its
responsibilities into the general content preflight engine.
"""

from __future__ import annotations

from typing import Any

from .schema import Project


FILM_PREFLIGHT_VERSION = "high-end-video-previsualization-v0.1"


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, round(value, 3)))


def _as_project(project: Project | dict[str, Any]) -> Project:
    if isinstance(project, Project):
        return project
    if isinstance(project, dict):
        return Project.model_validate(project)
    raise TypeError("project must be a video_core.schema.Project or dict")


def _timeline_slots(project: Project) -> list[dict[str, Any]]:
    raw_slots = (project.timeline or {}).get("slots") or []
    return [item for item in raw_slots if isinstance(item, dict)]


def _shot_count(project: Project) -> int:
    return sum(len(scene.shots) for scene in project.scenes)


def preflight_high_end_video_project(project: Project | dict[str, Any]) -> dict[str, Any]:
    """Evaluate the film-production canvas, not the account/business strategy.

    Output is intentionally shaped like an agent report.  It can be shown in the
    premium video product UI or summarized by Marketing OS, but it should remain
    a separate previsualization artifact.
    """
    project = _as_project(project)
    slots = _timeline_slots(project)
    shots = [shot for scene in project.scenes for shot in scene.shots]
    total_duration = sum(float(item.get("duration_sec") or 0) for item in slots)
    storyboard_refs = sum(1 for shot in shots if shot.storyboard_asset_id)
    dependency_refs = sum(1 for shot in shots if shot.asset_refs)
    accepted_or_draft = sum(1 for shot in shots if str(shot.status) in {"draft", "accepted", "generated"})

    narrative_clarity = _clamp(
        (0.35 if project.brief.strip() else 0.0)
        + (0.35 if project.script.strip() else 0.0)
        + min(0.3, 0.08 * len(project.scenes))
    )
    shot_feasibility = _clamp(
        (0.25 if shots else 0.0)
        + (0.25 if slots else 0.0)
        + min(0.3, 0.08 * storyboard_refs)
        + min(0.2, 0.05 * accepted_or_draft)
    )
    continuity_basis = _clamp(
        (0.35 if project.style_lock.locked else 0.0)
        + min(0.35, 0.08 * dependency_refs)
        + (0.15 if project.style_lock.reference_asset_ids else 0.0)
        + (0.15 if storyboard_refs else 0.0)
    )
    pacing_basis = _clamp(
        (0.25 if total_duration > 0 else 0.0)
        + min(0.45, 0.08 * len(slots))
        + (0.3 if 15 <= total_duration <= 180 else 0.1 if total_duration else 0.0)
    )
    sound_basis = _clamp(
        min(0.45, 0.1 * len(project.tracks.voice))
        + min(0.25, 0.08 * len(project.tracks.sfx))
        + min(0.2, 0.08 * len(project.tracks.bgm))
        + (0.1 if project.timeline else 0.0)
    )
    budget_safety = _clamp(
        (0.55 if project.budget.total > 0 else 0.0)
        + (0.25 if project.budget.approved else 0.0)
        + (0.2 if project.budget.remaining >= 0 else 0.0)
    )

    scores = {
        "narrative_clarity": narrative_clarity,
        "shot_feasibility": shot_feasibility,
        "visual_continuity_basis": continuity_basis,
        "pacing_basis": pacing_basis,
        "sound_basis": sound_basis,
        "budget_safety": budget_safety,
    }
    overall = _clamp(
        narrative_clarity * 0.22
        + shot_feasibility * 0.22
        + continuity_basis * 0.18
        + pacing_basis * 0.16
        + sound_basis * 0.10
        + budget_safety * 0.12
    )

    blockers: list[str] = []
    if not project.script.strip():
        blockers.append("script_missing")
    if not slots:
        blockers.append("timeline_slots_missing")
    if not shots:
        blockers.append("shot_plan_missing")
    if shots and storyboard_refs < max(1, min(len(shots), 3)):
        blockers.append("storyboard_basis_insufficient")
    if project.budget.total <= 0:
        blockers.append("budget_not_estimated")
    elif not project.budget.approved:
        blockers.append("budget_not_approved")

    if not project.script.strip() or not shots:
        status = "needs_story_canvas"
        next_action = "先让编剧/导演补齐剧本、场景和镜头清单。"
    elif not slots:
        status = "needs_animatic_timeline"
        next_action = "先让剪辑师生成 EDL 骨架和 v0 动态样片。"
    elif project.budget.total <= 0 or not project.budget.approved:
        status = "needs_budget_gate"
        next_action = "先由制片人估算预算，用户看样片和预算后再批准正片。"
    elif overall >= 0.72 and not blockers:
        status = "ready_for_paid_generation"
        next_action = "可以进入付费镜头生成，但仍需逐镜头成本和权利回执。"
    else:
        status = "needs_animatic_iteration"
        next_action = "先迭代 v0 样片，补节奏、连续性或声音依据。"

    return {
        "agent": "high_end_video_previsualization_agent",
        "scope": "film_previsualization",
        "version": FILM_PREFLIGHT_VERSION,
        "project_id": project.id,
        "status": status,
        "overall": overall,
        "scores": scores,
        "blockers": blockers,
        "next_action": next_action,
        "observations": {
            "scene_count": len(project.scenes),
            "shot_count": _shot_count(project),
            "timeline_slot_count": len(slots),
            "timeline_duration_sec": round(total_duration, 3),
            "style_locked": project.style_lock.locked,
            "budget_total": project.budget.total,
            "budget_approved": project.budget.approved,
        },
        "owns": [
            "script_to_screen_coherence",
            "shot_feasibility",
            "visual_continuity",
            "pacing_and_animatic",
            "sound_timing",
            "budget_gate_readiness",
        ],
        "not_responsible_for": [
            "account_positioning",
            "platform_attention_score",
            "publish_go_no_go",
            "long_term_memory_promotion",
        ],
    }
