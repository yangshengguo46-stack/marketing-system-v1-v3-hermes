"""Hermes-native social account lifecycle and BrowserContext leases."""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from hermes_state import SessionDB

logger = logging.getLogger(__name__)

MARKETING_ACCOUNT_PLATFORMS: dict[str, dict[str, Any]] = {
    "douyin": {"label": "抖音", "region": "china", "content": ["video"]},
    "xiaohongshu": {"label": "小红书", "region": "china", "content": ["image", "video"]},
    "bilibili": {"label": "B站", "region": "china", "content": ["video"]},
    "kuaishou": {"label": "快手", "region": "china", "content": ["video"]},
    "wechat_channels": {"label": "视频号", "region": "china", "content": ["video"]},
    "wechat_official": {"label": "微信公众号", "region": "china", "content": ["article"]},
    "zhihu": {"label": "知乎", "region": "china", "content": ["article", "video"]},
    "tiktok": {"label": "TikTok", "region": "global", "content": ["video"]},
    "youtube": {"label": "YouTube", "region": "global", "content": ["video"]},
}


def marketing_account_platforms() -> list[dict[str, Any]]:
    return [
        {"id": platform, **details}
        for platform, details in MARKETING_ACCOUNT_PLATFORMS.items()
    ]


@dataclass(frozen=True)
class BrowserContextLease:
    """Secret-free authority for one session to use one account context."""

    session_id: str
    user_id: str
    account_id: str
    platform: str
    profile_key: str
    auth_state: str
    issued_at: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AccountRegistry:
    """The sole Hermes owner of connected social account identity and lifecycle."""

    LEGACY_IMPORT_MARKER = "marketing_accounts_json_import_v1"
    LEGACY_TRUST_RECONCILE_MARKER = "marketing_accounts_legacy_trust_reconcile_v1"

    def __init__(self, session_db: SessionDB | None = None):
        self.db = session_db or SessionDB()
        self._owns_db = session_db is None

    def close(self) -> None:
        if self._owns_db:
            self.db.close()

    def register_pending(
        self,
        *,
        platform: str,
        user_id: str = "default",
        label: str | None = None,
        permissions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        platform = str(platform or "").strip().lower()
        if platform not in MARKETING_ACCOUNT_PLATFORMS:
            raise ValueError("unsupported Marketing OS account platform")
        user_id = str(user_id or "default").strip() or "default"
        if len(user_id) > 160:
            raise ValueError("user_id must be at most 160 characters")
        label = str(label or "").strip() or None
        if label is not None and len(label) > 256:
            raise ValueError("label must be at most 256 characters")
        account_id = f"acct_{uuid.uuid4().hex[:16]}"
        return self.db.upsert_marketing_account(
            account_id=account_id,
            user_id=user_id,
            platform=platform,
            label=label,
            status="pending",
            auth_state="unauthenticated",
            permissions=permissions or {},
        )

    def mark_authenticated(
        self,
        account_id: str,
        *,
        user_id: str = "default",
        platform_user_id: str | None = None,
        username: str | None = None,
        stats: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = self._require(account_id, user_id=user_id)
        now = time.time()
        return self.db.upsert_marketing_account(
            account_id=account_id,
            user_id=user_id,
            platform=current["platform"],
            platform_user_id=platform_user_id,
            username=username,
            label=current.get("label"),
            status="active",
            auth_state="authenticated",
            permissions=current.get("permissions"),
            stats=stats,
            metadata=current.get("metadata"),
            connected_at=current.get("connected_at") or now,
            last_verified_at=now,
        )

    def mark_verification_required(
        self, account_id: str, *, user_id: str = "default"
    ) -> dict[str, Any]:
        current = self._require(account_id, user_id=user_id)
        return self.db.upsert_marketing_account(
            account_id=account_id,
            user_id=user_id,
            platform=current["platform"],
            status="stale",
            auth_state="verification_required",
        )

    def disconnect(self, account_id: str, *, user_id: str = "default") -> dict[str, Any]:
        current = self._require(account_id, user_id=user_id)
        account = self.db.upsert_marketing_account(
            account_id=account_id,
            user_id=user_id,
            platform=current["platform"],
            status="disconnected",
            auth_state="unauthenticated",
        )
        self._reconcile_browser_owner(account, purge_profile=False)
        return account

    def delete(self, account_id: str, *, user_id: str = "default") -> bool:
        current = self._require(account_id, user_id=user_id)
        deleted = self.db.delete_marketing_account(account_id, user_id=user_id)
        if deleted:
            self._reconcile_browser_owner(current, purge_profile=True)
        return deleted

    def list(self, *, user_id: str = "default") -> list[dict[str, Any]]:
        return self.db.list_marketing_accounts(user_id=user_id)

    def get(self, account_id: str, *, user_id: str = "default") -> dict[str, Any]:
        return dict(self._require(account_id, user_id=user_id))

    def browser_context_lifecycle(
        self, account_id: str, *, user_id: str = "default"
    ) -> dict[str, Any]:
        """Return the account-owner decision consumed by the browser owner."""

        account = self.db.get_marketing_account(
            account_id,
            user_id=user_id,
            include_deleted=True,
        )
        if account is None:
            return {
                "account_id": account_id,
                "user_id": user_id,
                "status": "missing",
                "may_run": False,
                "purge_profile": True,
            }
        status = str(account.get("status") or "unknown")
        return {
            "account_id": str(account["id"]),
            "user_id": str(account["user_id"]),
            "platform": str(account["platform"]),
            "profile_key": str(account["profile_key"]),
            "status": status,
            "may_run": status in {"pending", "active", "stale"},
            "purge_profile": status == "deleted",
        }

    def bind_session(
        self,
        session_id: str,
        account_id: str,
        *,
        user_id: str = "default",
        require_pristine: bool = True,
    ) -> bool:
        self._require(account_id, user_id=user_id)
        return self.db.update_session_marketing_scope(
            session_id,
            marketing_user_id=user_id,
            marketing_account_id=account_id,
            require_pristine=require_pristine,
        )

    def adopt_prospect(
        self,
        prospect_account_id: str,
        target_account_id: str,
        *,
        user_id: str = "default",
    ) -> dict[str, Any]:
        """Move pre-login operating facts after the real account authenticated."""

        target = self._require(target_account_id, user_id=user_id)
        if target.get("status") != "active" or target.get("auth_state") != "authenticated":
            raise ValueError("target account must be authenticated before prospect adoption")
        result = self.db.adopt_marketing_prospect_scope(
            user_id=user_id,
            prospect_account_id=prospect_account_id,
            target_account_id=target_account_id,
        )
        return {
            **result,
            "successor_session_required": True,
            "successor_account_id": target_account_id,
            "rule": "existing conversations keep immutable scope; start the successor on target",
        }

    def unbind_session(self, session_id: str, *, require_pristine: bool = True) -> bool:
        return self.db.update_session_marketing_scope(
            session_id,
            marketing_user_id=None,
            marketing_account_id=None,
            require_pristine=require_pristine,
        )

    def lease_for_session(
        self, session_id: str, *, require_authenticated: bool = True
    ) -> BrowserContextLease:
        session = self.db.get_session(session_id)
        if not session or not session.get("marketing_account_id"):
            raise ValueError("conversation is not bound to a Marketing OS account")
        user_id = str(session.get("marketing_user_id") or "default")
        account = self._require(str(session["marketing_account_id"]), user_id=user_id)
        if account.get("status") not in {"pending", "active", "stale"}:
            raise ValueError("bound account is disconnected and cannot be used")
        if require_authenticated and account.get("auth_state") != "authenticated":
            raise ValueError("bound account requires login or verification")
        return BrowserContextLease(
            session_id=session_id,
            user_id=user_id,
            account_id=str(account["id"]),
            platform=str(account["platform"]),
            profile_key=str(account["profile_key"]),
            auth_state=str(account["auth_state"]),
            issued_at=time.time(),
        )

    def lease_for_login(
        self, account_id: str, *, user_id: str = "default"
    ) -> BrowserContextLease:
        """Issue a bounded lease for an explicit product-surface login flow."""

        account = self._require(account_id, user_id=user_id)
        if account.get("status") not in {"pending", "stale"}:
            raise ValueError("account is not waiting for login or verification")
        return BrowserContextLease(
            session_id=f"login-{account_id}",
            user_id=user_id,
            account_id=str(account["id"]),
            platform=str(account["platform"]),
            profile_key=str(account["profile_key"]),
            auth_state=str(account["auth_state"]),
            issued_at=time.time(),
        )

    def lease_for_sync(
        self, account_id: str, *, user_id: str = "default"
    ) -> BrowserContextLease:
        """Issue a bounded lease for a first-party read collector.

        A stale migrated account may use this lease once so the isolated
        browser profile itself can prove whether its login is still valid.
        """

        account = self._require(account_id, user_id=user_id)
        authenticated = (
            account.get("status") == "active"
            and account.get("auth_state") == "authenticated"
        )
        legacy_verification = (
            account.get("status") == "stale"
            and account.get("auth_state") == "verification_required"
        )
        if not (authenticated or legacy_verification):
            raise ValueError("account requires login before metrics can be synchronized")
        return BrowserContextLease(
            session_id=f"sync-{account_id}",
            user_id=user_id,
            account_id=str(account["id"]),
            platform=str(account["platform"]),
            profile_key=str(account["profile_key"]),
            auth_state=str(account["auth_state"]),
            issued_at=time.time(),
        )

    def import_legacy_accounts(self, accounts_path: Path) -> int:
        """One-time secret-free import from the deleted shell's accounts.json."""

        if self.db.get_meta(self.LEGACY_IMPORT_MARKER) == "complete":
            return 0
        imported = 0
        try:
            payload = json.loads(accounts_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {"accounts": []}
        rows = payload.get("accounts") if isinstance(payload, dict) else []
        for item in rows or []:
            if not isinstance(item, dict) or not item.get("id") or not item.get("platform"):
                continue
            legacy_status = str(item.get("status") or "active").lower()
            terminal = legacy_status if legacy_status in {"disconnected", "deleted"} else None
            status = terminal or "stale"
            legacy_stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
            self.db.upsert_marketing_account(
                account_id=str(item["id"]),
                platform=str(item["platform"]),
                platform_user_id=str(item.get("platform_user_id") or "") or None,
                username=str(item.get("username") or "") or None,
                label=str(item.get("label") or "") or None,
                status=status,
                auth_state=(
                    "verification_required"
                    if status == "stale"
                    else "unauthenticated"
                ),
                stats={},
                metadata={
                    "migrated_from": "accounts.json",
                    "legacy_stats_snapshot": legacy_stats,
                    "trust_state": "unverified_legacy_import",
                },
            )
            imported += 1
        self.db.set_meta(self.LEGACY_IMPORT_MARKER, "complete")
        return imported

    def reconcile_unverified_legacy_accounts(self) -> int:
        """Remove live authority from legacy rows never verified by this owner."""

        if self.db.get_meta(self.LEGACY_TRUST_RECONCILE_MARKER) == "complete":
            return 0
        reconciled = 0
        for account in self.db.list_marketing_accounts(include_deleted=True):
            metadata = account.get("metadata") or {}
            if (
                metadata.get("migrated_from") != "accounts.json"
                or account.get("last_verified_at") is not None
                or account.get("status") == "deleted"
            ):
                continue
            legacy_stats = account.get("stats") or metadata.get("legacy_stats_snapshot") or {}
            self.db.upsert_marketing_account(
                account_id=str(account["id"]),
                user_id=str(account.get("user_id") or "default"),
                platform=str(account["platform"]),
                platform_user_id=account.get("platform_user_id"),
                username=account.get("username"),
                label=account.get("label"),
                status="stale",
                auth_state="verification_required",
                permissions=account.get("permissions") or {},
                stats={},
                metadata={
                    **metadata,
                    "legacy_stats_snapshot": legacy_stats,
                    "trust_state": "unverified_legacy_import",
                },
            )
            reconciled += 1
        self.db.set_meta(self.LEGACY_TRUST_RECONCILE_MARKER, "complete")
        return reconciled

    def _require(self, account_id: str, *, user_id: str) -> dict[str, Any]:
        account = self.db.get_marketing_account(account_id, user_id=user_id)
        if account is None:
            raise ValueError(f"unknown Marketing OS account: {account_id}")
        return account

    @staticmethod
    def _reconcile_browser_owner(
        account: dict[str, Any], *, purge_profile: bool
    ) -> None:
        """Tell the native MCP owner to release this account's browser context."""

        try:
            from agent.product import is_product_runtime

            if not is_product_runtime():
                return
            from tools.mcp_tool import reconcile_marketing_account_browser

            reconcile_marketing_account_browser(
                user_id=str(account["user_id"]),
                account_id=str(account["id"]),
                platform=str(account["platform"]),
                profile_key=str(account["profile_key"]),
                purge_profile=purge_profile,
            )
        except Exception:
            # Account truth is authoritative and must remain disconnected/deleted
            # even when best-effort process or filesystem cleanup needs retrying.
            logger.exception(
                "BrowserContext reconciliation failed for account '%s'",
                account.get("id"),
            )
