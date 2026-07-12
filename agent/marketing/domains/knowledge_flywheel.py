"""Privacy-governed bridge between private learning and aggregate knowledge."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.storage import MarketingDomainRepository
from marketing_knowledge_protocol import (
    CONTRIBUTION_PROTOCOL,
    verify_knowledge_pack,
)


_FORBIDDEN_KEY = re.compile(
    r"(?:account.?id|user.?id|username|cookie|token|password|secret|(?:^|_)url$|raw.?content|raw.?text|message|email|phone)",
    re.IGNORECASE,
)
_STATUSES = {
    "pending",
    "uploading",
    "submitted",
    "accepted",
    "rejected",
    "withheld",
    "delete_pending",
    "deleted",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _aggregate_value(value: Any, *, path: str = "root") -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if len(text) > 64:
            raise ValueError(f"aggregate value at {path} is too specific")
        return text
    if isinstance(value, list):
        if len(value) > 32:
            raise ValueError(f"aggregate list at {path} is too large")
        return [_aggregate_value(item, path=f"{path}[]") for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            name = str(key).strip()
            if not name or _FORBIDDEN_KEY.search(name):
                raise ValueError(f"forbidden aggregate field: {name or '<empty>'}")
            result[name] = _aggregate_value(item, path=f"{path}.{name}")
        return result
    raise ValueError(f"unsupported aggregate value at {path}")


class KnowledgeFlywheelRepository(MarketingDomainRepository):
    """Own consented contribution outbox and verified aggregate priors."""

    def __init__(self, paths: MarketingDataPaths | None = None):
        super().__init__(paths)

    def create_contribution(
        self,
        *,
        user_id: str,
        account_id: str,
        source_candidate_id: str,
        consent_ref: str,
        schema_version: str,
        cohort: dict[str, Any],
        features: dict[str, Any],
        outcomes: dict[str, Any],
    ) -> dict[str, Any]:
        consent = str(consent_ref or "").strip()
        if not consent:
            raise ValueError("explicit contribution consent_ref is required")
        payloads = tuple(
            _aggregate_value(value, path=name)
            for name, value in (("cohort", cohort), ("features", features), ("outcomes", outcomes))
        )
        canonical = _json(
            {
                "candidate": source_candidate_id,
                "consent": consent,
                "schema": schema_version,
                "cohort": payloads[0],
                "features": payloads[1],
                "outcomes": payloads[2],
            }
        )
        idempotency_key = hashlib.sha256(canonical.encode()).hexdigest()
        with self._transaction() as db:
            candidate = db.execute(
                """SELECT status FROM marketing_learning_candidates
                WHERE id=? AND user_id=? AND account_id=?""",
                (source_candidate_id, user_id, account_id),
            ).fetchone()
            if candidate is None:
                raise KeyError("learning candidate not found in account scope")
            if candidate["status"] != "accepted":
                raise ValueError("only an accepted learning candidate may contribute")
            existing = db.execute(
                "SELECT id FROM marketing_knowledge_contributions WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                contribution_id = existing["id"]
            else:
                contribution_id = f"contrib_{uuid.uuid4().hex}"
                db.execute(
                    """INSERT INTO marketing_knowledge_contributions
                    (id,idempotency_key,user_id,account_id,source_candidate_id,consent_ref,
                     schema_version,cohort_json,features_json,outcomes_json,status,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,'pending',?)""",
                    (
                        contribution_id,
                        idempotency_key,
                        user_id,
                        account_id,
                        source_candidate_id,
                        consent,
                        str(schema_version),
                        _json(payloads[0]),
                        _json(payloads[1]),
                        _json(payloads[2]),
                        _now(),
                    ),
                )
        return self.get_contribution(contribution_id)

    def get_contribution(self, contribution_id: str) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM marketing_knowledge_contributions WHERE id=?",
                (contribution_id,),
            ).fetchone()
        if row is None:
            raise KeyError("knowledge contribution not found")
        value = dict(row)
        for key in ("cohort_json", "features_json", "outcomes_json"):
            value[key.removesuffix("_json")] = json.loads(value.pop(key))
        return value

    def list_contributions(
        self,
        *,
        statuses: tuple[str, ...] = ("pending",),
        limit: int = 100,
        user_id: str | None = None,
        account_id: str | None = None,
    ) -> list[dict[str, Any]]:
        selected = tuple(dict.fromkeys(str(value or "").strip() for value in statuses))
        if not selected or any(value not in _STATUSES for value in selected):
            raise ValueError("invalid contribution status filter")
        bounded_limit = max(1, min(int(limit), 500))
        placeholders = ",".join("?" for _ in selected)
        filters = [f"status IN ({placeholders})"]
        parameters: list[Any] = list(selected)
        if user_id is not None:
            filters.append("user_id=?")
            parameters.append(str(user_id))
        if account_id is not None:
            filters.append("account_id=?")
            parameters.append(str(account_id))
        with self._connection() as db:
            rows = db.execute(
                f"""SELECT id FROM marketing_knowledge_contributions
                WHERE {' AND '.join(filters)} ORDER BY created_at,id LIMIT ?""",
                (*parameters, bounded_limit),
            ).fetchall()
        return [self.get_contribution(str(row["id"])) for row in rows]

    def update_contribution_status(self, contribution_id: str, status: str) -> dict[str, Any]:
        if status not in _STATUSES - {"pending"}:
            raise ValueError("invalid contribution status")
        with self._transaction() as db:
            updated = db.execute(
                """UPDATE marketing_knowledge_contributions
                SET status=?,submitted_at=CASE WHEN ?='submitted' THEN ? ELSE submitted_at END
                WHERE id=? AND status='pending'""",
                (status, status, _now(), contribution_id),
            ).rowcount
            if updated != 1:
                raise ValueError("only a pending contribution can transition")
        return self.get_contribution(contribution_id)

    def claim_pending_contributions(
        self,
        *,
        limit: int = 100,
        stale_before: str | None = None,
    ) -> list[dict[str, Any]]:
        """Claim upload work so withdrawal can safely race an in-flight request."""

        bounded_limit = max(1, min(int(limit), 500))
        with self._transaction() as db:
            if stale_before:
                db.execute(
                    """UPDATE marketing_knowledge_contributions
                    SET status='pending',upload_claimed_at=NULL,
                        last_sync_error='stale_upload_claim_recovered'
                    WHERE status='uploading' AND upload_claimed_at<?""",
                    (str(stale_before),),
                )
            rows = db.execute(
                """SELECT id FROM marketing_knowledge_contributions
                WHERE status='pending' ORDER BY created_at,id LIMIT ?""",
                (bounded_limit,),
            ).fetchall()
            claimed_at = _now()
            ids = [str(row["id"]) for row in rows]
            for contribution_id in ids:
                db.execute(
                    """UPDATE marketing_knowledge_contributions
                    SET status='uploading',upload_claimed_at=?,last_sync_error=NULL
                    WHERE id=? AND status='pending'""",
                    (claimed_at, contribution_id),
                )
        return [self.get_contribution(contribution_id) for contribution_id in ids]

    def settle_contribution_upload(self, contribution_id: str) -> dict[str, Any]:
        """Settle a server acknowledgement without overriding a concurrent withdrawal."""

        with self._transaction() as db:
            row = db.execute(
                "SELECT status FROM marketing_knowledge_contributions WHERE id=?",
                (contribution_id,),
            ).fetchone()
            if row is None:
                raise KeyError("knowledge contribution not found")
            if row["status"] == "uploading":
                db.execute(
                    """UPDATE marketing_knowledge_contributions
                    SET status='submitted',submitted_at=?,upload_claimed_at=NULL,
                        last_sync_error=NULL WHERE id=?""",
                    (_now(), contribution_id),
                )
            elif row["status"] != "delete_pending":
                raise ValueError("only uploading or concurrently withdrawn contribution can settle")
        return self.get_contribution(contribution_id)

    def release_contribution_upload(
        self, contribution_id: str, *, error_type: str
    ) -> dict[str, Any]:
        with self._transaction() as db:
            db.execute(
                """UPDATE marketing_knowledge_contributions
                SET status='pending',upload_claimed_at=NULL,last_sync_error=?
                WHERE id=? AND status='uploading'""",
                (str(error_type or "upload_failed")[:120], contribution_id),
            )
        return self.get_contribution(contribution_id)

    def request_contribution_withdrawal(
        self,
        contribution_id: str,
        *,
        user_id: str,
        account_id: str,
    ) -> dict[str, Any]:
        """Revoke local consent and enqueue central deletion when data may have left."""

        now = _now()
        with self._transaction() as db:
            row = db.execute(
                """SELECT status,deletion_ref FROM marketing_knowledge_contributions
                WHERE id=? AND user_id=? AND account_id=?""",
                (contribution_id, user_id, account_id),
            ).fetchone()
            if row is None:
                raise KeyError("knowledge contribution not found in account scope")
            status = str(row["status"])
            if status in {"withheld", "delete_pending", "deleted"}:
                pass
            elif status in {"pending", "rejected"}:
                db.execute(
                    """UPDATE marketing_knowledge_contributions
                    SET status='withheld',withdrawal_requested_at=?,upload_claimed_at=NULL,
                        cohort_json='{}',features_json='{}',outcomes_json='{}'
                    WHERE id=?""",
                    (now, contribution_id),
                )
            elif status in {"uploading", "submitted", "accepted"}:
                deletion_ref = str(row["deletion_ref"] or f"delete_{uuid.uuid4().hex}")
                db.execute(
                    """UPDATE marketing_knowledge_contributions
                    SET status='delete_pending',deletion_ref=?,withdrawal_requested_at=?,
                        upload_claimed_at=NULL,cohort_json='{}',features_json='{}',
                        outcomes_json='{}' WHERE id=?""",
                    (deletion_ref, now, contribution_id),
                )
            else:
                raise ValueError(f"contribution cannot be withdrawn from status: {status}")
        return self.get_contribution(contribution_id)

    def settle_contribution_deletion(self, contribution_id: str) -> dict[str, Any]:
        with self._transaction() as db:
            updated = db.execute(
                """UPDATE marketing_knowledge_contributions
                SET status='deleted',deleted_at=?,last_sync_error=NULL
                WHERE id=? AND status='delete_pending'""",
                (_now(), contribution_id),
            ).rowcount
            if updated != 1:
                raise ValueError("only a pending contribution deletion can settle")
        return self.get_contribution(contribution_id)

    def record_contribution_deletion_error(
        self, contribution_id: str, *, error_type: str
    ) -> dict[str, Any]:
        with self._transaction() as db:
            db.execute(
                """UPDATE marketing_knowledge_contributions SET last_sync_error=?
                WHERE id=? AND status='delete_pending'""",
                (str(error_type or "delete_failed")[:120], contribution_id),
            )
        return self.get_contribution(contribution_id)

    def export_contribution(self, contribution_id: str) -> dict[str, Any]:
        """Return the exact anonymous wire envelope; never export local scope or consent data."""

        contribution = self.get_contribution(contribution_id)
        if contribution["status"] not in {"pending", "uploading", "submitted"}:
            raise ValueError("only pending, claimed or submitted contributions may be exported")
        return {
            "protocol": CONTRIBUTION_PROTOCOL,
            "contribution_ref": contribution["id"],
            "schema_version": contribution["schema_version"],
            "cohort": contribution["cohort"],
            "features": contribution["features"],
            "outcomes": contribution["outcomes"],
            "observed_at": contribution["created_at"],
        }

    def export_contribution_deletion(self, contribution_id: str) -> dict[str, str]:
        contribution = self.get_contribution(contribution_id)
        if contribution["status"] != "delete_pending" or not contribution.get(
            "deletion_ref"
        ):
            raise ValueError("contribution deletion is not pending")
        return {
            "contribution_ref": contribution["id"],
            "deletion_ref": contribution["deletion_ref"],
        }

    def install_knowledge_pack(
        self,
        pack: dict[str, Any],
        *,
        public_keys: dict[str, bytes | Any],
    ) -> dict[str, Any]:
        """Verify a central prior before it can enter the local product state."""

        verified = verify_knowledge_pack(pack, public_keys=public_keys)
        now = _now()
        with self._transaction() as db:
            db.execute(
                """INSERT INTO marketing_knowledge_packs
                (id,version,knowledge_type,platform,region,window_start,window_end,
                 sample_size,min_cohort_size,payload_json,checksum,signature,status,verified_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'verified',?)
                ON CONFLICT(id) DO UPDATE SET
                    payload_json=excluded.payload_json,checksum=excluded.checksum,
                    signature=excluded.signature,status='verified',verified_at=excluded.verified_at""",
                (
                    verified["id"],
                    verified["version"],
                    verified["knowledge_type"],
                    verified["platform"],
                    verified.get("region") or "",
                    verified["window_start"],
                    verified["window_end"],
                    int(verified["sample_size"]),
                    int(verified["min_cohort_size"]),
                    _json(verified["payload"]),
                    verified["checksum"],
                    verified["signature"],
                    now,
                ),
            )
        installed = self.get_knowledge_pack(verified["id"])
        from agent.marketing.domains.knowledge_bases import KnowledgeBaseRepository

        installed["knowledge_entry"] = KnowledgeBaseRepository(self.paths).install_signed_pack(
            verified
        )
        return installed

    def get_knowledge_pack(self, pack_id: str) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM marketing_knowledge_packs WHERE id=?", (pack_id,)
            ).fetchone()
        if row is None:
            raise KeyError("knowledge pack not found")
        value = dict(row)
        value["payload"] = json.loads(value.pop("payload_json"))
        value["authority"] = "global_prior_below_local_receipt"
        return value
