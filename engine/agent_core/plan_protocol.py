"""RUN-01: structured plan protocol.

The model declares its execution plan by calling ``marketing_plan_declare``
with structured steps.  This module owns validation, plan persistence, and
the deterministic step<->tool binding rules used by the adapter callbacks.
No plan is ever parsed from model prose.
"""

from __future__ import annotations

import json
from typing import Any

MAX_STEPS = 12
MAX_DESCRIPTION_CHARS = 200


def _manifest_tool_names() -> set[str]:
    from .tool_manifest import all_tools

    return {tool.name for tool in all_tools()}


def validate_steps(raw_steps: Any) -> list[dict[str, Any]]:
    """Validate model-declared steps. Raises ValueError with a reason."""
    if not isinstance(raw_steps, list) or not raw_steps:
        raise ValueError("steps must be a non-empty list")
    if len(raw_steps) > MAX_STEPS:
        raise ValueError(f"plan cannot exceed {MAX_STEPS} steps")
    known_tools = _manifest_tool_names()
    validated: list[dict[str, Any]] = []
    for index, item in enumerate(raw_steps, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"step {index} must be an object")
        description = str(item.get("description") or "").strip()
        if not description:
            raise ValueError(f"step {index} requires a non-empty description")
        tool_name = item.get("tool_name")
        if tool_name is not None:
            tool_name = str(tool_name).strip() or None
        if tool_name is not None and tool_name not in known_tools:
            raise ValueError(f"step {index} references unknown tool: {tool_name}")
        if tool_name == "marketing_plan_declare":
            raise ValueError(f"step {index} must not plan the plan tool itself")
        validated.append({
            "id": str(index),
            "description": description[:MAX_DESCRIPTION_CHARS],
            "tool_name": tool_name,
            "kind": "tool" if tool_name else "synthesis",
            "status": "pending",
        })
    return validated


def merge_declared_plan(
    existing_plan: list[dict[str, Any]], declared: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Completed/skipped steps of the existing plan are immutable history;
    the declared steps replace only the not-yet-finished remainder."""
    kept = [s for s in existing_plan if s.get("status") in {"completed", "skipped"}]
    merged = list(kept)
    next_id = len(kept) + 1
    for step in declared:
        merged.append({**step, "id": str(next_id)})
        next_id += 1
    return merged


def declare_plan(params: dict) -> str:
    """Handler body for ``marketing_plan_declare`` (gateway-wrapped)."""
    from .tool_gateway import get_task_context

    ctx = get_task_context()
    if not ctx or not ctx.get("store") or not ctx.get("task_id"):
        return json.dumps({
            "status": "blocked",
            "error": "任务上下文不可用，无法声明计划",
        }, ensure_ascii=False)
    store = ctx["store"]
    task_id = ctx["task_id"]

    try:
        declared = validate_steps(params.get("steps"))
    except ValueError as exc:
        return json.dumps({
            "status": "invalid",
            "error": str(exc),
        }, ensure_ascii=False)

    task = store.get_task(task_id)
    existing = task.get("plan") or []
    first_declaration = not existing
    plan = merge_declared_plan(existing, declared)
    updated = store.update_plan(task_id, plan)
    store.append_event(
        task_id,
        "plan.ready" if first_declaration else "plan.updated",
        {
            "plan": plan,
            "plan_version": updated.get("plan_version", 1),
            "plan_total": len(plan),
            "source": "declared",
        },
    )
    return json.dumps({
        "status": "ok",
        "plan_version": updated.get("plan_version", 1),
        "plan_total": len(plan),
        "steps": [{"id": s["id"], "description": s["description"],
                   "tool_name": s["tool_name"]} for s in plan],
    }, ensure_ascii=False)


def bind_step_on_tool_start(plan: list[dict[str, Any]], tool_name: str) -> bool:
    """Mark the first pending step explicitly bound to ``tool_name`` as
    running.  Steps without a tool_name never bind — no guessing."""
    for step in plan:
        if step.get("status") == "pending" and step.get("tool_name") == tool_name:
            step["status"] = "running"
            return True
    return False


def complete_step_on_tool_success(plan: list[dict[str, Any]], tool_name: str) -> bool:
    """Complete the running step explicitly bound to ``tool_name``."""
    for step in plan:
        if step.get("status") == "running" and step.get("tool_name") == tool_name:
            step["status"] = "completed"
            return True
    return False


def fail_step_on_tool_error(plan: list[dict[str, Any]], tool_name: str) -> bool:
    """Mark the running step bound to ``tool_name`` as failed."""
    for step in plan:
        if step.get("status") == "running" and step.get("tool_name") == tool_name:
            step["status"] = "failed"
            return True
    return False
