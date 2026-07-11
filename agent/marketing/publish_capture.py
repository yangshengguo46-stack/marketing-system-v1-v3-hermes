"""Trusted post-tool seam for native publishing provider results."""

from __future__ import annotations

import json
from typing import Any

from agent.marketing.domains.publishing import PublishingRepository
from agent.marketing.session_scope import read_tool_session_scope


PUBLISH_TOOL_NAMES = {"marketing_effect_publish", "marketing_publish_query"}
PUBLISH_RESULT_KEY = "marketing_publish_result"


def enrich_tool_result_with_publish_receipt(
    *,
    tool_name: str,
    args: dict[str, Any],
    result: Any,
    task_id: str = "",
    session_id: str = "",
) -> Any:
    """Settle only the trusted native publish tool's provider envelope.

    The model cannot create a receipt by calling a separate record tool.  The
    envelope must be returned by the real ``marketing_effect_publish`` handler
    after its provider ran.  Scope is checked again against the bound Hermes
    session before the action is settled.
    """

    if tool_name not in PUBLISH_TOOL_NAMES or not isinstance(result, str):
        return result
    scope = read_tool_session_scope(task_id=task_id, session_id=session_id)
    if not scope:
        return result
    try:
        payload = json.loads(result)
    except (TypeError, ValueError):
        return result
    if not isinstance(payload, dict):
        return result
    provider_result = payload.get(PUBLISH_RESULT_KEY)
    if not isinstance(provider_result, dict):
        return result
    action_id = str(args.get("action_id") or provider_result.get("action_id") or "").strip()
    outcome = str(provider_result.get("outcome") or "").strip().lower()
    if not action_id or outcome not in {"published", "unknown", "failed", "cancelled"}:
        return result

    repository = PublishingRepository()
    action = repository.get_action(action_id)
    if (
        action["user_id"] != str(scope["user_id"])
        or action["account_id"] != str(scope["account_id"])
    ):
        raise PermissionError("publish action is outside the bound Hermes account scope")
    settled = repository.settle_action(
        action_id,
        outcome=outcome,
        provider_result=provider_result,
        verification_source=str(provider_result.get("verification_source") or ""),
        failure_code=str(provider_result.get("failure_code") or ""),
    )
    payload[PUBLISH_RESULT_KEY] = {
        **provider_result,
        "action_id": settled["id"],
        "outcome": settled["status"],
        "receipt_id": settled.get("receipt_id"),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
