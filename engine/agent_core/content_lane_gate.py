"""Shared PreflightDecision gate for content-production asset creators.

The content factory has multiple lanes, but they must share one business
preflight contract before a draft becomes reviewable:

- soft articles for Zhihu / WeChat Official Account;
- faceless material-composite videos;
- premium human/digital-human videos, which delegate film quality to the
  high-end video previsualization agent.

This module deliberately keeps the gate small and JSON-shaped so it can be
embedded into ``content_assets.content_json`` and consumed by Hermes, FastAPI,
Electron and the future UI without adapter-specific branching.
"""

from __future__ import annotations

from typing import Any

from .production_preflight import create_content_production_preflight


CONTENT_LANE_GATE_VERSION = "content-lane-gate-v0.1"


def run_content_lane_gate(
    store: Any,
    params: dict[str, Any] | None = None,
    *,
    kind: str,
) -> dict[str, Any]:
    """Run and persist the unified production preflight for a concrete lane."""

    gate_params = dict(params or {})
    gate_params["kind"] = kind
    preflight = create_content_production_preflight(store, gate_params)
    preflight_decision = dict(preflight.get("preflight_decision") or {})
    decision = dict(preflight.get("decision") or {})
    influence_score = dict(preflight.get("influence_score") or {})

    status = str(preflight_decision.get("status") or decision.get("status") or preflight.get("status") or "unknown")
    return {
        "version": CONTENT_LANE_GATE_VERSION,
        "preflight_id": preflight["preflight_id"],
        "formula_version": preflight.get("formula_version"),
        "kind": preflight.get("kind") or kind,
        "stage": preflight_decision.get("stage") or "production_draft",
        "status": status,
        "go": bool(preflight_decision.get("go")),
        "action": preflight_decision.get("action"),
        "selected_lane": preflight_decision.get("selected_lane") or preflight.get("kind") or kind,
        "primary_reason": preflight_decision.get("primary_reason") or decision.get("primary_reason"),
        "required_next_steps": list(preflight_decision.get("required_next_steps") or []),
        "watch_metrics": list(preflight_decision.get("watch_metrics") or []),
        "blockers": list(decision.get("blockers") or []),
        "warnings": list(decision.get("warnings") or preflight_decision.get("warnings") or []),
        "influence_score": influence_score,
        "score": influence_score.get("score"),
        "score_decision": influence_score.get("decision"),
        "target_platforms": list(preflight.get("target_platforms") or []),
        "account_id": preflight.get("account_id"),
        "plan_status": preflight.get("plan_status"),
        "video_previsualization_status": decision.get("video_previsualization_status")
        or preflight.get("video_previsualization", {}).get("status"),
    }


def attach_content_lane_gate(content: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any]:
    """Return content with a durable gate summary and quality-gate row."""

    updated = dict(content or {})
    quality_gates = [dict(item) for item in (updated.get("quality_gates") or []) if isinstance(item, dict)]
    quality_gates.append({
        "name": "总预演门",
        "status": "pass" if gate.get("go") else "blocked",
        "decision_status": gate.get("status"),
        "preflight_id": gate.get("preflight_id"),
        "reason": gate.get("primary_reason"),
    })
    updated["quality_gates"] = quality_gates
    updated["preflight_gate"] = gate
    return updated


def requested_experiment_context(store: Any, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Validate and return an account-experiment binding requested by a content creator."""

    params = dict(params or {})
    experiment_id = str(params.get("experiment_id") or "").strip()
    if not experiment_id:
        return None
    project_id = str(params.get("project_id") or "").strip()
    account_id = str(params.get("account_id") or "").strip()
    user_id = str(params.get("__user_id") or params.get("user_id") or "default").strip() or "default"
    if not project_id:
        raise ValueError("project_id is required when experiment_id is provided")
    if not account_id:
        raise ValueError("account_id is required when experiment_id is provided")

    from .account_lifecycle import AccountLifecycleService

    lifecycle = AccountLifecycleService(store)
    experiment = lifecycle.get_experiment(
        user_id=user_id,
        account_id=account_id,
        project_id=project_id,
        experiment_id=experiment_id,
    )
    return {
        "user_id": user_id,
        "account_id": account_id,
        "project_id": project_id,
        "experiment_id": experiment_id,
        "experiment": experiment,
    }


def attach_experiment_context(content: dict[str, Any], context: dict[str, Any] | None) -> dict[str, Any]:
    """Embed a compact experiment binding into a draft asset payload."""

    if context is None:
        return content
    experiment = context["experiment"]
    updated = dict(content or {})
    updated["experiment_binding"] = {
        "project_id": context["project_id"],
        "experiment_id": context["experiment_id"],
        "hypothesis": experiment.get("hypothesis"),
        "primary_metric": (experiment.get("success_criteria") or {}).get("primary_metric"),
        "source_strategy_candidate_id": (experiment.get("variable") or {}).get("source_strategy_candidate_id"),
        "guardrail": "content asset is bound to an account experiment before publish/receipt learning",
    }
    return updated


def attach_asset_to_requested_experiment(
    store: Any,
    context: dict[str, Any] | None,
    *,
    asset_id: str,
) -> dict[str, Any] | None:
    """Attach a created draft asset back to the validated experiment scope."""

    if context is None:
        return None
    from .account_lifecycle import AccountLifecycleService

    lifecycle = AccountLifecycleService(store)
    experiment = lifecycle.attach_experiment_asset(
        user_id=context["user_id"],
        account_id=context["account_id"],
        project_id=context["project_id"],
        experiment_id=context["experiment_id"],
        asset_id=asset_id,
    )
    return {
        "project_id": context["project_id"],
        "experiment_id": context["experiment_id"],
        "status": experiment["status"],
        "asset_ids": experiment["asset_ids"],
    }


def gate_result_status(gate: dict[str, Any]) -> str:
    """Return a top-level tool status that separates creation from readiness."""

    return "ok" if gate.get("go") else "blocked"
