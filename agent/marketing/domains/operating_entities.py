"""Native creator/brand operating entities and their platform channels."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.storage import MarketingDomainRepository


_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:@-]{1,160}$")


class OperatingEntityRepository(MarketingDomainRepository):
    """Own the many-platform identity above isolated login accounts.

    Existing single-owner installations are migrated to one deterministic
    default entity.  Once multiple entities exist, an unassigned account is
    never guessed into one; callers must link it explicitly.
    """

    def __init__(self, paths: MarketingDataPaths | None = None):
        if paths is None:
            defaults = MarketingDataPaths.from_env()
            if os.environ.get("MARKETING_OS_AGENT_DB"):
                paths = defaults
            else:
                from hermes_state import SessionDB

                owner = SessionDB()
                db_path = owner.db_path
                owner.close()
                paths = MarketingDataPaths(
                    user_data=defaults.user_data,
                    config_dir=defaults.config_dir,
                    agent_db=db_path,
                )
        super().__init__(paths)

    def ensure_for_account(
        self,
        *,
        user_id: str,
        account_id: str,
        label: str = "我的经营主体",
    ) -> dict[str, Any]:
        user = _identifier(user_id or "default", "user_id")
        account = _identifier(account_id, "account_id")
        now = time.time()
        with self._transaction() as db:
            existing = db.execute(
                """SELECT e.* FROM marketing_operating_entities e
                JOIN marketing_operating_entity_accounts m ON m.entity_id=e.id
                WHERE m.user_id=? AND m.account_id=? AND m.status='active'
                  AND e.status='active'""",
                (user, account),
            ).fetchone()
            if existing is not None:
                entity_id = str(existing["id"])
            else:
                entities = db.execute(
                    """SELECT * FROM marketing_operating_entities
                    WHERE user_id=? AND status='active' ORDER BY created_at,id""",
                    (user,),
                ).fetchall()
                if not entities:
                    entity_id = _default_entity_id(user)
                    db.execute(
                        """INSERT INTO marketing_operating_entities
                        (id,user_id,label,status,metadata_json,created_at,updated_at)
                        VALUES (?,?,?,'active',?, ?,?)""",
                        (
                            entity_id,
                            user,
                            str(label or "我的经营主体").strip()[:256],
                            json.dumps(
                                {"migration": "single-owner-default-v1"},
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                            now,
                            now,
                        ),
                    )
                    # This is the one safe automatic grouping: a legacy install
                    # had no concept of multiple brands, so all existing channel
                    # accounts belonged to its single operating scope.
                    rows = db.execute(
                        """SELECT id FROM marketing_accounts
                        WHERE user_id=? AND deleted_at IS NULL
                          AND status IN ('pending','active','stale','disconnected')""",
                        (user,),
                    ).fetchall()
                    for row in rows:
                        _insert_membership(
                            db,
                            entity_id=entity_id,
                            user_id=user,
                            account_id=str(row["id"]),
                            now=now,
                        )
                elif len(entities) == 1:
                    entity_id = str(entities[0]["id"])
                    account_exists = db.execute(
                        """SELECT 1 FROM marketing_accounts
                        WHERE id=? AND user_id=? AND deleted_at IS NULL""",
                        (account, user),
                    ).fetchone()
                    if account_exists is not None:
                        _insert_membership(
                            db,
                            entity_id=entity_id,
                            user_id=user,
                            account_id=account,
                            now=now,
                        )
                else:
                    raise ValueError(
                        "account is not linked to an operating entity; explicit entity selection is required"
                    )
        return self.get(entity_id=entity_id, user_id=user)

    def link_account(
        self,
        *,
        entity_id: str,
        user_id: str,
        account_id: str,
        role: str = "channel",
    ) -> dict[str, Any]:
        entity = _identifier(entity_id, "entity_id")
        user = _identifier(user_id or "default", "user_id")
        account = _identifier(account_id, "account_id")
        role_value = str(role or "channel").strip()[:80] or "channel"
        now = time.time()
        with self._transaction() as db:
            if db.execute(
                "SELECT 1 FROM marketing_operating_entities WHERE id=? AND user_id=? AND status='active'",
                (entity, user),
            ).fetchone() is None:
                raise KeyError("operating entity not found")
            if db.execute(
                "SELECT 1 FROM marketing_accounts WHERE id=? AND user_id=? AND deleted_at IS NULL",
                (account, user),
            ).fetchone() is None:
                raise KeyError("marketing account not found")
            conflict = db.execute(
                """SELECT entity_id FROM marketing_operating_entity_accounts
                WHERE user_id=? AND account_id=? AND status='active'""",
                (user, account),
            ).fetchone()
            if conflict is not None and conflict["entity_id"] != entity:
                raise ValueError("account already belongs to another operating entity")
            _insert_membership(
                db,
                entity_id=entity,
                user_id=user,
                account_id=account,
                now=now,
                role=role_value,
            )
        return self.get(entity_id=entity, user_id=user)

    def get(self, *, entity_id: str, user_id: str = "default") -> dict[str, Any]:
        entity = _identifier(entity_id, "entity_id")
        user = _identifier(user_id or "default", "user_id")
        with self._connection() as db:
            row = db.execute(
                """SELECT * FROM marketing_operating_entities
                WHERE id=? AND user_id=? AND status='active'""",
                (entity, user),
            ).fetchone()
            if row is None:
                raise KeyError("operating entity not found")
            accounts = db.execute(
                """SELECT a.id,a.platform,a.label,a.username,a.status,a.auth_state,m.role
                FROM marketing_operating_entity_accounts m
                JOIN marketing_accounts a ON a.id=m.account_id AND a.user_id=m.user_id
                WHERE m.entity_id=? AND m.user_id=? AND m.status='active'
                  AND a.deleted_at IS NULL
                ORDER BY a.connected_at,a.created_at,a.id""",
                (entity, user),
            ).fetchall()
        value = dict(row)
        value["metadata"] = json.loads(value.pop("metadata_json") or "{}")
        value["accounts"] = [dict(item) for item in accounts]
        value["account_ids"] = [str(item["id"]) for item in accounts]
        value["platforms"] = list(dict.fromkeys(str(item["platform"]) for item in accounts))
        return value

    def account_is_linked(
        self, *, entity_id: str, user_id: str, account_id: str
    ) -> bool:
        entity = _identifier(entity_id, "entity_id")
        user = _identifier(user_id or "default", "user_id")
        account = _identifier(account_id, "account_id")
        with self._connection() as db:
            return db.execute(
                """SELECT 1 FROM marketing_operating_entity_accounts
                WHERE entity_id=? AND user_id=? AND account_id=? AND status='active'""",
                (entity, user, account),
            ).fetchone() is not None


def _default_entity_id(user_id: str) -> str:
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:20]
    return f"entity_{digest}"


def _identifier(value: Any, field: str) -> str:
    normalized = str(value or "").strip()
    if not _SAFE_ID.fullmatch(normalized):
        raise ValueError(f"{field} must be 1-160 safe identifier characters")
    return normalized


def _insert_membership(
    db,
    *,
    entity_id: str,
    user_id: str,
    account_id: str,
    now: float,
    role: str = "channel",
) -> None:
    db.execute(
        """INSERT INTO marketing_operating_entity_accounts
        (entity_id,user_id,account_id,role,status,created_at,updated_at)
        VALUES (?,?,?,?,'active',?,?)
        ON CONFLICT(entity_id,account_id) DO UPDATE SET
            role=excluded.role,status='active',updated_at=excluded.updated_at""",
        (entity_id, user_id, account_id, role, now, now),
    )
