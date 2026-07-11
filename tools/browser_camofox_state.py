"""Hermes-managed Camofox state helpers.

Provides profile-scoped identity and state directory paths for Camofox
persistent browser profiles.  When managed persistence is enabled, Hermes
sends a deterministic userId derived from the active profile so that
Camofox can map it to the same persistent browser profile directory
across restarts.
"""

from __future__ import annotations

import uuid
import contextvars
from pathlib import Path
from typing import Dict, Optional

from hermes_constants import get_hermes_home

CAMOFOX_STATE_DIR_NAME = "browser_auth"
CAMOFOX_STATE_SUBDIR = "camofox"
_CURRENT_MARKETING_ACCOUNT: contextvars.ContextVar[str] = contextvars.ContextVar(
    "camofox_marketing_account", default=""
)


def bind_camofox_marketing_account(account_id: Optional[str]):
    """Bind account scope for one native tool dispatch and return its token."""

    return _CURRENT_MARKETING_ACCOUNT.set(str(account_id or "").strip())


def reset_camofox_marketing_account(token) -> None:
    _CURRENT_MARKETING_ACCOUNT.reset(token)


def current_camofox_marketing_account() -> str:
    return _CURRENT_MARKETING_ACCOUNT.get()


def get_camofox_state_dir() -> Path:
    """Return the profile-scoped root directory for Camofox persistence."""
    return get_hermes_home() / CAMOFOX_STATE_DIR_NAME / CAMOFOX_STATE_SUBDIR


def get_camofox_identity(
    task_id: Optional[str] = None,
    account_id: Optional[str] = None,
) -> Dict[str, str]:
    """Return the stable Hermes-managed Camofox identity for this profile.

    The identity is profile-scoped for general Hermes use and becomes
    account-scoped when Marketing OS binds a social account. Two accounts must
    never share cookies merely because they use the same local installation.
    """
    scope_root = str(get_camofox_state_dir())
    logical_scope = task_id or "default"
    account_scope = str(account_id or "").strip()
    user_seed = f"camofox-user:{scope_root}"
    session_seed = f"camofox-session:{scope_root}:{logical_scope}"
    if account_scope:
        user_seed += f":account:{account_scope}"
        session_seed += f":account:{account_scope}"
    user_digest = uuid.uuid5(
        uuid.NAMESPACE_URL,
        user_seed,
    ).hex[:10]
    session_digest = uuid.uuid5(
        uuid.NAMESPACE_URL,
        session_seed,
    ).hex[:16]
    return {
        "user_id": f"hermes_{user_digest}",
        "session_key": f"task_{session_digest}",
    }
