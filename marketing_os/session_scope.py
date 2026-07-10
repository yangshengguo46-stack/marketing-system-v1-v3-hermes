"""Stable per-conversation Marketing OS account routing.

Account scope belongs to the native session, not to a UI card or an adapter.
Only immutable routing identifiers enter the cached prompt. Mutable account
facts remain in :class:`AccountContextRepository` and must be read through the
native account tool when the agent needs a current answer.
"""

from __future__ import annotations

import re
from typing import Any

from marketing_os.domains import AccountContextRepository


_SCOPE_ID = re.compile(r"^[A-Za-z0-9_.:@-]{1,160}$")


def resolve_account_scope(
    *,
    user_id: str = "default",
    account_id: str,
    repository: AccountContextRepository | None = None,
) -> dict[str, Any]:
    """Validate and resolve a connected account or onboarding prospect."""

    normalized_user = _normalize_id(user_id or "default", field="user_id")
    normalized_account = _normalize_id(account_id, field="account_id")
    repo = repository or AccountContextRepository()
    account = next(
        (
            item
            for item in repo.list_accounts().get("accounts", [])
            if item.get("id") == normalized_account
        ),
        None,
    )
    if account is None and not normalized_account.startswith("prospect_"):
        raise ValueError(f"unknown Marketing OS account: {normalized_account}")

    platform = str((account or {}).get("platform") or "unassigned").strip().lower()
    if not re.fullmatch(r"[a-z0-9_-]{1,48}", platform):
        platform = "unknown"
    return {
        "user_id": normalized_user,
        "account_id": normalized_account,
        "platform": platform,
        "connected": account is not None,
    }


def scope_from_session_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the stored identifiers without reinterpreting other session data."""

    if not row:
        return None
    account_id = str(row.get("marketing_account_id") or "").strip()
    if not account_id:
        return None
    try:
        user_id = _normalize_id(
            str(row.get("marketing_user_id") or "default"), field="user_id"
        )
        account_id = _normalize_id(account_id, field="account_id")
    except ValueError:
        return None
    try:
        return resolve_account_scope(
            user_id=user_id,
            account_id=account_id,
        )
    except ValueError:
        # A platform account may have been disconnected after the conversation
        # was created. Preserve routing identity for historical continuity,
        # while making its disconnected state explicit.
        return {
            "user_id": user_id,
            "account_id": account_id,
            "platform": "unavailable",
            "connected": False,
        }


def read_session_scope(session_db: Any, session_id: str) -> dict[str, Any] | None:
    if session_db is None or not session_id:
        return None
    return scope_from_session_row(session_db.get_session(session_id))


def read_tool_session_scope(
    *, task_id: str | None = None, session_id: str | None = None
) -> dict[str, Any] | None:
    """Resolve the durable account scope for a native model-tool invocation."""

    durable_id = str(session_id or task_id or "").strip()
    if not durable_id:
        return None
    try:
        from hermes_state import SessionDB

        db = SessionDB()
        try:
            return read_session_scope(db, durable_id)
        finally:
            db.close()
    except Exception:
        return None


def enforce_tool_account_scope(
    args: dict[str, Any],
    *,
    task_id: str | None = None,
    session_id: str | None = None,
    require_bound: bool = False,
) -> tuple[str, str]:
    """Return ``(user_id, account_id)`` while preventing cross-account calls."""

    scope = read_tool_session_scope(task_id=task_id, session_id=session_id)
    requested_user = str(args.get("user_id") or "default").strip() or "default"
    requested_account = str(args.get("account_id") or "").strip()
    if scope:
        if requested_user not in {"", "default", scope["user_id"]}:
            raise ValueError("tool user_id does not match the bound conversation")
        if requested_account and requested_account != scope["account_id"]:
            raise ValueError("tool account_id does not match the bound conversation")
        return str(scope["user_id"]), str(scope["account_id"])
    if require_bound:
        raise ValueError("this operation requires a conversation bound to a Marketing OS account")
    return (
        _normalize_id(requested_user, field="user_id"),
        _normalize_id(requested_account, field="account_id"),
    )


def build_account_scope_prompt(scope: dict[str, Any] | None) -> str:
    """Build the compact, byte-stable account routing prompt for one session."""

    if not scope:
        return ""
    user_id = _normalize_id(str(scope.get("user_id") or "default"), field="user_id")
    account_id = _normalize_id(str(scope.get("account_id") or ""), field="account_id")
    platform = str(scope.get("platform") or "unassigned")
    if not re.fullmatch(r"[a-z0-9_-]{1,48}", platform):
        platform = "unknown"
    return (
        "MARKETING OS SESSION SCOPE (stable routing identity)\n"
        f"user_id={user_id}\naccount_id={account_id}\nplatform={platform}\n"
        "Never silently switch to another account. Before account-specific "
        "positioning, content, publishing, metrics, or growth advice, call "
        "marketing_read_account_context with exactly these user_id/account_id "
        "values. The tool result is the current source of truth; missing fields "
        "are evidence gaps, never permission to invent data."
    )


def _normalize_id(value: str, *, field: str) -> str:
    normalized = str(value or "").strip()
    if not _SCOPE_ID.fullmatch(normalized):
        raise ValueError(f"{field} must be 1-160 safe identifier characters")
    return normalized
