"""Trusted post-tool transition from real browser login to AccountRegistry truth."""

from __future__ import annotations

import json
from typing import Any

from agent.account_registry import AccountRegistry
from agent.marketing.session_scope import read_tool_session_scope
from hermes_state import default_marketing_scope


AUTH_SCHEMA = "marketing_account_auth_verification.v1"
AUTH_TOOL = "browser_verify_account_login"
AUTH_TOOL_NAMES = {
    AUTH_TOOL,
    "mcp_marketing_browser_browser_verify_account_login",
}


def decode_account_auth_result(result: Any) -> dict[str, Any] | None:
    if isinstance(result, dict):
        return result if result.get("schema") == AUTH_SCHEMA else None
    if not isinstance(result, str) or AUTH_SCHEMA not in result:
        return None
    decoder = json.JSONDecoder()
    for index, character in enumerate(result):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(result[index:])
        except ValueError:
            continue
        if isinstance(value, dict) and value.get("schema") == AUTH_SCHEMA:
            return value
    return None


def enrich_tool_result_with_account_auth(
    *,
    tool_name: str,
    result: Any,
    task_id: str = "",
    session_id: str = "",
) -> Any:
    """Accept authentication only from the real account-scoped browser tool."""

    if tool_name not in AUTH_TOOL_NAMES:
        return result
    payload = decode_account_auth_result(result)
    scope = read_tool_session_scope(task_id=task_id, session_id=session_id)
    if not payload or not scope:
        return result
    if payload.get("verified") is not True:
        return result
    account_id = str(payload.get("account_id") or "")
    platform = str(payload.get("platform") or "")
    if account_id != str(scope["account_id"]) or platform != str(scope["platform"]):
        raise ValueError("browser login verification does not match the bound account scope")
    if account_id.startswith("prospect_"):
        raise ValueError("a prospect scope cannot be marked as a platform login")

    registry = AccountRegistry()
    try:
        account = registry.mark_authenticated(
            account_id,
            user_id=str(scope["user_id"]),
        )
        prospect_id = default_marketing_scope(str(scope["user_id"]))[1]
        try:
            adoption = registry.adopt_prospect(
                prospect_id,
                account_id,
                user_id=str(scope["user_id"]),
            )
        except ValueError as exc:
            adoption = {
                "status": "review_required",
                "reason": str(exc),
                "prospect_account_id": prospect_id,
                "target_account_id": account_id,
            }
    finally:
        registry.close()

    # The login browser was headed because the lease was unauthenticated.
    # Close it after the successful tool result; the next lease is authenticated
    # and therefore restarts the same persistent profile in background mode.
    from tools.mcp_tool import reconcile_marketing_account_browser

    reconcile_marketing_account_browser(
        user_id=str(account["user_id"]),
        account_id=str(account["id"]),
        platform=str(account["platform"]),
        profile_key=str(account["profile_key"]),
        purge_profile=False,
    )
    transition = {
        "schema": AUTH_SCHEMA,
        "account_id": account_id,
        "platform": platform,
        "auth_state": account["auth_state"],
        "account_status": account["status"],
        "prospect_adoption": adoption,
        "browser_transition": "headed_login_closed_next_lease_background",
    }
    return str(result) + "\n\nMarketing OS account transition:\n" + json.dumps(
        transition, ensure_ascii=False, indent=2
    )
