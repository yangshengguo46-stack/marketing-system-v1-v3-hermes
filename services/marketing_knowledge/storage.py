"""Durable central knowledge service state with replay and deletion control."""

from __future__ import annotations

import hashlib
import json
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
    payload_json TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    received_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contribution_tombstones (
    contribution_ref TEXT PRIMARY KEY,
    deletion_ref TEXT NOT NULL UNIQUE,
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
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CentralKnowledgeStore:
    """Own service-side anonymous facts; never store local account identity."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as db:
            db.executescript(_SCHEMA)

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

    def ingest_contribution(self, contribution: dict[str, Any]) -> dict[str, Any]:
        """Persist one validated envelope; identical retries are idempotent."""

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
                "SELECT content_sha256,received_at FROM anonymous_contributions WHERE contribution_ref=?",
                (contribution_ref,),
            ).fetchone()
            if existing is not None:
                if existing["content_sha256"] != checksum:
                    raise ValueError("contribution reference replayed with different content")
                return {
                    "contribution_ref": contribution_ref,
                    "content_sha256": checksum,
                    "received_at": existing["received_at"],
                    "operation": "already_ingested",
                }
            db.execute(
                """INSERT INTO anonymous_contributions
                (contribution_ref,content_sha256,payload_json,observed_at,received_at)
                VALUES (?,?,?,?,?)""",
                (
                    contribution_ref,
                    checksum,
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
    ) -> dict[str, Any]:
        """Delete payload and retain the minimum tombstone needed to stop replay."""

        reference = str(contribution_ref or "").strip()
        deletion = str(deletion_ref or "").strip()
        if not reference.startswith("contrib_") or not deletion.startswith("delete_"):
            raise ValueError("invalid contribution deletion reference")
        deleted_at = _now()
        with self._transaction() as db:
            existing = db.execute(
                "SELECT deletion_ref,deleted_at FROM contribution_tombstones WHERE contribution_ref=?",
                (reference,),
            ).fetchone()
            if existing is not None:
                if existing["deletion_ref"] != deletion:
                    raise ValueError("contribution already deleted by another request")
                return {
                    "contribution_ref": reference,
                    "deletion_ref": deletion,
                    "deleted_at": existing["deleted_at"],
                    "operation": "already_deleted",
                }
            db.execute(
                "DELETE FROM anonymous_contributions WHERE contribution_ref=?",
                (reference,),
            )
            db.execute(
                """INSERT INTO contribution_tombstones
                (contribution_ref,deletion_ref,deleted_at) VALUES (?,?,?)""",
                (reference, deletion, deleted_at),
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
