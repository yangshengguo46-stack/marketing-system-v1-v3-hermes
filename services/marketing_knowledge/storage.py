"""Durable central knowledge service state with replay and deletion control."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from marketing_knowledge_protocol import canonical_json
from services.marketing_knowledge.aggregation import (
    KnowledgeAggregator,
    validate_contribution,
)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS anonymous_contributions (
    contribution_ref TEXT PRIMARY KEY,
    content_sha256 TEXT NOT NULL,
    deletion_owner_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    received_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contribution_tombstones (
    contribution_ref TEXT PRIMARY KEY,
    deletion_ref TEXT NOT NULL UNIQUE,
    deletion_owner_sha256 TEXT NOT NULL,
    deleted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signed_knowledge_packs (
    id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    checksum TEXT NOT NULL,
    signature TEXT NOT NULL,
    generated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS service_clients (
    client_id TEXT PRIMARY KEY,
    token_sha256 TEXT NOT NULL,
    token_version INTEGER NOT NULL DEFAULT 1,
    requests_per_minute INTEGER NOT NULL DEFAULT 60,
    status TEXT NOT NULL DEFAULT 'active',
    created_at REAL NOT NULL,
    rotated_at REAL
);

CREATE TABLE IF NOT EXISTS service_request_nonces (
    client_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    received_at REAL NOT NULL,
    PRIMARY KEY(client_id,request_id),
    FOREIGN KEY(client_id) REFERENCES service_clients(client_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_service_request_nonces_window
ON service_request_nonces(client_id,received_at);
"""


_SAFE_CLIENT_ID = re.compile(r"^[A-Za-z0-9_.-]{3,96}$")
_SAFE_REQUEST_ID = re.compile(r"^req_[A-Za-z0-9_-]{12,128}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class ServiceAuthenticationError(ValueError):
    pass


class ServiceReplayError(ValueError):
    pass


class ServiceRateLimitError(ValueError):
    def __init__(self, retry_after: int):
        super().__init__("service client rate limit exceeded")
        self.retry_after = max(1, int(retry_after))


class ContributionAuthorizationError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CentralKnowledgeStore:
    """Own service-side anonymous facts; never store local account identity."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as db:
            db.executescript(_SCHEMA)
            columns = {
                str(row["name"])
                for row in db.execute("PRAGMA table_info(anonymous_contributions)")
            }
            if "deletion_owner_sha256" not in columns:
                db.execute(
                    """ALTER TABLE anonymous_contributions
                    ADD COLUMN deletion_owner_sha256 TEXT NOT NULL DEFAULT ''"""
                )
            tombstone_columns = {
                str(row["name"])
                for row in db.execute("PRAGMA table_info(contribution_tombstones)")
            }
            if "deletion_owner_sha256" not in tombstone_columns:
                db.execute(
                    """ALTER TABLE contribution_tombstones
                    ADD COLUMN deletion_owner_sha256 TEXT NOT NULL DEFAULT ''"""
                )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
            except Exception:
                db.rollback()
                raise
            else:
                db.commit()

    def ingest_contribution(
        self,
        contribution: dict[str, Any],
        *,
        deletion_owner_sha256: str,
        accepted_deletion_owner_sha256: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        """Persist one validated envelope; identical retries are idempotent."""

        owner = str(deletion_owner_sha256 or "").lower()
        if not _SHA256.fullmatch(owner):
            raise ValueError("valid deletion owner proof is required")
        accepted_owners = {owner}
        for candidate in accepted_deletion_owner_sha256:
            normalized = str(candidate or "").lower()
            if not _SHA256.fullmatch(normalized):
                raise ValueError("invalid accepted deletion owner proof")
            accepted_owners.add(normalized)
        value = validate_contribution(contribution)
        contribution_ref = str(value["contribution_ref"])
        payload = canonical_json(value)
        checksum = hashlib.sha256(payload).hexdigest()
        received_at = _now()
        with self._transaction() as db:
            if db.execute(
                "SELECT 1 FROM contribution_tombstones WHERE contribution_ref=?",
                (contribution_ref,),
            ).fetchone():
                raise ValueError("deleted contribution cannot be replayed")
            existing = db.execute(
                """SELECT content_sha256,deletion_owner_sha256,received_at
                FROM anonymous_contributions WHERE contribution_ref=?""",
                (contribution_ref,),
            ).fetchone()
            if existing is not None:
                if existing["content_sha256"] != checksum:
                    raise ValueError("contribution reference replayed with different content")
                if not any(
                    hmac.compare_digest(existing["deletion_owner_sha256"], candidate)
                    for candidate in accepted_owners
                ):
                    raise ContributionAuthorizationError(
                        "contribution reference belongs to another authenticated client"
                    )
                if not hmac.compare_digest(existing["deletion_owner_sha256"], owner):
                    db.execute(
                        """UPDATE anonymous_contributions SET deletion_owner_sha256=?
                        WHERE contribution_ref=?""",
                        (owner, contribution_ref),
                    )
                return {
                    "contribution_ref": contribution_ref,
                    "content_sha256": checksum,
                    "received_at": existing["received_at"],
                    "operation": "already_ingested",
                }
            db.execute(
                """INSERT INTO anonymous_contributions
                (contribution_ref,content_sha256,deletion_owner_sha256,payload_json,
                 observed_at,received_at)
                VALUES (?,?,?,?,?,?)""",
                (
                    contribution_ref,
                    checksum,
                    owner,
                    payload.decode("utf-8"),
                    str(value["observed_at"]),
                    received_at,
                ),
            )
            # Packs are derived snapshots. Any corpus change invalidates all
            # currently served packs until aggregation runs again.
            db.execute("DELETE FROM signed_knowledge_packs")
        return {
            "contribution_ref": contribution_ref,
            "content_sha256": checksum,
            "received_at": received_at,
            "operation": "ingested",
        }

    def delete_contribution(
        self,
        contribution_ref: str,
        *,
        deletion_ref: str,
        deletion_owner_sha256: str,
        accepted_deletion_owner_sha256: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        """Delete payload and retain the minimum tombstone needed to stop replay."""

        reference = str(contribution_ref or "").strip()
        deletion = str(deletion_ref or "").strip()
        owner = str(deletion_owner_sha256 or "").lower()
        if not reference.startswith("contrib_") or not deletion.startswith("delete_"):
            raise ValueError("invalid contribution deletion reference")
        if not _SHA256.fullmatch(owner):
            raise ValueError("valid deletion owner proof is required")
        accepted_owners = {owner}
        for candidate in accepted_deletion_owner_sha256:
            normalized = str(candidate or "").lower()
            if not _SHA256.fullmatch(normalized):
                raise ValueError("invalid accepted deletion owner proof")
            accepted_owners.add(normalized)
        deleted_at = _now()
        with self._transaction() as db:
            existing = db.execute(
                """SELECT deletion_ref,deletion_owner_sha256,deleted_at
                FROM contribution_tombstones WHERE contribution_ref=?""",
                (reference,),
            ).fetchone()
            if existing is not None:
                if not any(
                    hmac.compare_digest(existing["deletion_owner_sha256"], candidate)
                    for candidate in accepted_owners
                ):
                    raise ContributionAuthorizationError(
                        "authenticated client cannot repeat this deletion"
                    )
                if not hmac.compare_digest(existing["deletion_owner_sha256"], owner):
                    db.execute(
                        """UPDATE contribution_tombstones SET deletion_owner_sha256=?
                        WHERE contribution_ref=?""",
                        (owner, reference),
                    )
                if existing["deletion_ref"] != deletion:
                    raise ValueError("contribution already deleted by another request")
                return {
                    "contribution_ref": reference,
                    "deletion_ref": deletion,
                    "deleted_at": existing["deleted_at"],
                    "operation": "already_deleted",
                }
            contribution = db.execute(
                "SELECT deletion_owner_sha256 FROM anonymous_contributions WHERE contribution_ref=?",
                (reference,),
            ).fetchone()
            if contribution is None:
                raise KeyError("knowledge contribution not found")
            if not any(
                hmac.compare_digest(contribution["deletion_owner_sha256"], candidate)
                for candidate in accepted_owners
            ):
                raise ContributionAuthorizationError(
                    "authenticated client cannot delete this contribution"
                )
            db.execute(
                "DELETE FROM anonymous_contributions WHERE contribution_ref=?",
                (reference,),
            )
            db.execute(
                """INSERT INTO contribution_tombstones
                (contribution_ref,deletion_ref,deletion_owner_sha256,deleted_at)
                VALUES (?,?,?,?)""",
                (reference, deletion, owner, deleted_at),
            )
            db.execute("DELETE FROM signed_knowledge_packs")
        return {
            "contribution_ref": reference,
            "deletion_ref": deletion,
            "deleted_at": deleted_at,
            "operation": "deleted",
        }

    def list_contributions(self) -> list[dict[str, Any]]:
        with self._connection() as db:
            rows = db.execute(
                "SELECT payload_json FROM anonymous_contributions ORDER BY contribution_ref"
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def build_and_store_packs(
        self,
        aggregator: KnowledgeAggregator,
        *,
        version: str,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        with self._transaction() as db:
            rows = db.execute(
                "SELECT payload_json FROM anonymous_contributions ORDER BY contribution_ref"
            ).fetchall()
            packs = aggregator.build_packs(
                [json.loads(row["payload_json"]) for row in rows],
                version=version,
                now=now,
            )
            # Build and replace happen under the same write transaction so an
            # ingest/delete cannot race a stale pack back into service.
            db.execute("DELETE FROM signed_knowledge_packs")
            for pack in packs:
                db.execute(
                    """INSERT INTO signed_knowledge_packs
                    (id,version,payload_json,checksum,signature,generated_at)
                    VALUES (?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET
                        payload_json=excluded.payload_json,
                        checksum=excluded.checksum,
                        signature=excluded.signature,
                        generated_at=excluded.generated_at""",
                    (
                        pack["id"],
                        pack["version"],
                        canonical_json(pack).decode("utf-8"),
                        pack["checksum"],
                        pack["signature"],
                        pack["generated_at"],
                    ),
                )
        return packs

    def get_pack(self, pack_id: str) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                "SELECT payload_json FROM signed_knowledge_packs WHERE id=?",
                (str(pack_id or ""),),
            ).fetchone()
        if row is None:
            raise KeyError("knowledge pack not found")
        return json.loads(row["payload_json"])

    def list_packs(self) -> list[dict[str, Any]]:
        with self._connection() as db:
            rows = db.execute(
                "SELECT payload_json FROM signed_knowledge_packs ORDER BY id"
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def provision_client(
        self,
        client_id: str,
        token: str,
        *,
        requests_per_minute: int = 60,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Offline administration seam; never expose this as a public endpoint."""

        client = str(client_id or "").strip()
        secret = str(token or "")
        limit = int(requests_per_minute)
        if not _SAFE_CLIENT_ID.fullmatch(client):
            raise ValueError("invalid service client_id")
        if len(secret) < 32:
            raise ValueError("service client token must contain at least 32 characters")
        if limit < 1 or limit > 10_000:
            raise ValueError("requests_per_minute is outside the allowed range")
        created_at = float(now if now is not None else datetime.now(timezone.utc).timestamp())
        digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        with self._transaction() as db:
            try:
                db.execute(
                    """INSERT INTO service_clients
                    (client_id,token_sha256,token_version,requests_per_minute,status,created_at)
                    VALUES (?,?,1,?,'active',?)""",
                    (client, digest, limit, created_at),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("service client already exists; rotate its token") from exc
        return {"client_id": client, "token_version": 1, "status": "active"}

    def rotate_client_token(
        self,
        client_id: str,
        new_token: str,
        *,
        now: float | None = None,
    ) -> dict[str, Any]:
        client = str(client_id or "").strip()
        secret = str(new_token or "")
        if len(secret) < 32:
            raise ValueError("service client token must contain at least 32 characters")
        rotated_at = float(now if now is not None else datetime.now(timezone.utc).timestamp())
        digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        with self._transaction() as db:
            updated = db.execute(
                """UPDATE service_clients SET token_sha256=?,token_version=token_version+1,
                status='active',rotated_at=? WHERE client_id=?""",
                (digest, rotated_at, client),
            ).rowcount
            if updated != 1:
                raise KeyError("service client not found")
            row = db.execute(
                "SELECT token_version,status FROM service_clients WHERE client_id=?",
                (client,),
            ).fetchone()
        return {
            "client_id": client,
            "token_version": int(row["token_version"]),
            "status": row["status"],
        }

    def revoke_client(self, client_id: str) -> dict[str, Any]:
        client = str(client_id or "").strip()
        with self._transaction() as db:
            updated = db.execute(
                "UPDATE service_clients SET status='revoked' WHERE client_id=?",
                (client,),
            ).rowcount
            if updated != 1:
                raise KeyError("service client not found")
        return {"client_id": client, "status": "revoked"}

    def authorize_request(
        self,
        *,
        client_id: str,
        token: str,
        request_id: str,
        request_sha256: str,
        timestamp: float,
        now: float | None = None,
        max_clock_skew_seconds: int = 300,
    ) -> dict[str, Any]:
        """Authenticate and consume one nonce in the same durable transaction."""

        client = str(client_id or "").strip()
        request = str(request_id or "").strip()
        digest = str(request_sha256 or "").lower()
        current = float(now if now is not None else datetime.now(timezone.utc).timestamp())
        if not _SAFE_CLIENT_ID.fullmatch(client) or not _SAFE_REQUEST_ID.fullmatch(request):
            raise ServiceAuthenticationError("invalid service request identity")
        if not _SHA256.fullmatch(digest):
            raise ServiceAuthenticationError("invalid service request digest")
        if abs(current - float(timestamp)) > max(1, int(max_clock_skew_seconds)):
            raise ServiceAuthenticationError("service request timestamp is outside the allowed window")

        token_digest = hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()
        with self._transaction() as db:
            account = db.execute(
                """SELECT token_sha256,token_version,requests_per_minute,status
                FROM service_clients WHERE client_id=?""",
                (client,),
            ).fetchone()
            if (
                account is None
                or account["status"] != "active"
                or not hmac.compare_digest(account["token_sha256"], token_digest)
            ):
                raise ServiceAuthenticationError("invalid or revoked service client credential")
            if db.execute(
                "SELECT 1 FROM service_request_nonces WHERE client_id=? AND request_id=?",
                (client, request),
            ).fetchone():
                raise ServiceReplayError("service request nonce has already been used")
            window_start = current - 60.0
            request_count = int(
                db.execute(
                    """SELECT COUNT(*) FROM service_request_nonces
                    WHERE client_id=? AND received_at>?""",
                    (client, window_start),
                ).fetchone()[0]
            )
            if request_count >= int(account["requests_per_minute"]):
                oldest = db.execute(
                    """SELECT MIN(received_at) FROM service_request_nonces
                    WHERE client_id=? AND received_at>?""",
                    (client, window_start),
                ).fetchone()[0]
                raise ServiceRateLimitError(int(max(1.0, 60.0 - (current - float(oldest)))))
            db.execute(
                """INSERT INTO service_request_nonces
                (client_id,request_id,request_sha256,received_at) VALUES (?,?,?,?)""",
                (client, request, digest, current),
            )
            db.execute(
                "DELETE FROM service_request_nonces WHERE received_at<?",
                (current - 86_400.0,),
            )
        return {
            "client_id": client,
            "token_version": int(account["token_version"]),
            "request_id": request,
        }
