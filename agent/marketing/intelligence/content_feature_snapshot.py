"""Pre-publish content feature snapshots.

The prediction engine needs a stable "black box" for every draft it scores.
If a post later wins or fails, the retro loop must be able to replay what the
agent knew *before* publishing: title, structure, evidence, platform choices,
account context, material state and risk hints.

This module deliberately stays deterministic and storage-agnostic.  Production
lanes embed the returned snapshot into ``content_assets.content_json`` so the
snapshot travels with the asset and can later be compared with receipts,
predictions and learning candidates.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


FEATURE_SNAPSHOT_VERSION = "content-feature-snapshot-v0.1"


def _text(value: Any, *, limit: int | None = None) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit] if limit is not None else text


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value, key=lambda item: str(item))
    return [value]


def _platforms(value: Any) -> list[str]:
    result: list[str] = []
    for item in _list(value):
        platform = _text(item, limit=80)
        if platform and platform not in result:
            result.append(platform)
    return result


def _evidence_summary(evidence: Any) -> dict[str, Any]:
    items = [item for item in _list(evidence) if isinstance(item, dict)]
    with_url = [
        item
        for item in items
        if item.get("has_url")
        or item.get("url")
        or item.get("source_url")
        or item.get("canonical_url")
    ]
    titles: list[str] = []
    sources: list[str] = []
    for item in items[:8]:
        title = _text(item.get("title") or item.get("name") or item.get("headline"), limit=120)
        source = _text(
            item.get("url")
            or item.get("source_url")
            or item.get("canonical_url")
            or item.get("link"),
            limit=200,
        )
        if title:
            titles.append(title)
        if source:
            sources.append(source)
    return {
        "total": len(items),
        "with_url": len(with_url),
        "ready": bool(with_url),
        "sample_titles": titles,
        "sample_sources": sources[:5],
    }


def _score_summary(scores: Any) -> dict[str, Any]:
    if not isinstance(scores, dict):
        return {}
    wanted = (
        "hook", "topic", "emotion", "density", "pacing", "viewpoint", "cta",
        "title_bait_risk", "controversy_overload_risk",
    )
    return {key: scores[key] for key in wanted if key in scores}


def _prediction_summary(prediction: Any) -> dict[str, Any]:
    if not isinstance(prediction, dict):
        return {}
    dimensions = prediction.get("prediction_dimensions") or {}
    dimension_payload = dimensions.get("dimensions") if isinstance(dimensions, dict) else {}
    dimension_names = list(dimension_payload) if isinstance(dimension_payload, dict) else []
    reaction = prediction.get("social_reaction_simulation")
    if not isinstance(reaction, dict):
        reaction = {}
    system_simulation = prediction.get("social_system_simulation")
    if not isinstance(system_simulation, dict):
        system_simulation = {}
    return {
        "prediction_version": prediction.get("prediction_version"),
        "confidence": prediction.get("confidence"),
        "expected_outcome": prediction.get("expected_outcome"),
        "dimension_names": dimension_names,
        "basis": list(prediction.get("basis") or [])[:8],
        "social_reaction": {
            "version": reaction.get("version"),
            "status": reaction.get("status"),
            "simulation_id": reaction.get("simulation_id"),
            "scenario_ids": list(reaction.get("scenario_ids") or [])[:8],
            "scenario_count": len(reaction.get("scenarios") or []),
        },
        "social_system": {
            "version": system_simulation.get("version"),
            "simulation_id": system_simulation.get("simulation_id"),
            "scope": system_simulation.get("scope"),
            "stage_ids": sorted((system_simulation.get("stages") or {}).keys()),
            "mutable": system_simulation.get("mutable"),
        },
    }


def _stable_snapshot_id(body: dict[str, Any]) -> str:
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, default=str)
    return "cfs_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_content_feature_snapshot(
    *,
    kind: str,
    objective: str,
    title: str,
    topic: str,
    hook: str,
    account_id: str | None = None,
    platforms: Any = None,
    audience_context: Any = None,
    evidence: Any = None,
    structure: dict[str, Any] | None = None,
    material_context: dict[str, Any] | None = None,
    sound_context: dict[str, Any] | None = None,
    platform_context: dict[str, Any] | None = None,
    scores: dict[str, Any] | None = None,
    prediction: dict[str, Any] | None = None,
    risks: list[str] | None = None,
) -> dict[str, Any]:
    """Return a compact, replayable feature snapshot for a draft asset."""

    body: dict[str, Any] = {
        "version": FEATURE_SNAPSHOT_VERSION,
        "protocol": "content_feature_snapshots",
        "kind": _text(kind, limit=80),
        "identity": {
            "account_id": _text(account_id, limit=120) if account_id else None,
            "platforms": _platforms(platforms),
        },
        "content_intent": {
            "objective": _text(objective, limit=300),
            "topic": _text(topic, limit=120),
            "title": _text(title, limit=160),
            "hook": _text(hook, limit=240),
        },
        "audience_context": audience_context if isinstance(audience_context, dict) else {},
        "evidence": _evidence_summary(evidence),
        "structure": structure or {},
        "material_context": material_context or {},
        "sound_context": sound_context or {"status": "not_planned"},
        "platform_context": platform_context or {},
        "score_inputs": _score_summary(scores or {}),
        "prediction_ref": _prediction_summary(prediction or {}),
        "risk_hints": list(risks or []),
        "retro_contract": {
            "label_dimensions": [
                "attention", "retention", "trust", "action", "fit", "sound", "risk",
                "social_reaction",
            ],
            "mutable": False,
            "purpose": "pre_publish_replay_and_retro_attribution",
            "social_reaction_observations": [
                "comment_stance_clusters",
                "comment_theme_clusters",
                "question_and_objection_patterns",
                "target_vs_off_target_audience_signals",
            ],
        },
    }
    return {"id": _stable_snapshot_id(body), **body}
