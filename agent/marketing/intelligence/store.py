"""Durable state for the native Memory -> Preflight -> Receipt loop.

This repository stores marketing facts beside the other account/content
domain records.  It does not own an Agent loop, a task runner, or a memory
engine; Hermes remains the owner of those capabilities.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from agent.epistemic_contract import (
    EpistemicClass,
    SystemAuthority,
    require_system_authority,
)
from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.storage import MarketingDomainRepository


PREFLIGHT_STATUSES = {"created", "used_for_action", "settled", "superseded"}
LEARNING_TYPES = {"memory", "strategy", "weight", "skill"}
LEARNING_STATUSES = {"pending", "accepted", "rejected", "superseded"}
_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|cookie|password|secret|token)", re.IGNORECASE
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class OperatingLoopRepository(MarketingDomainRepository):
    """Append-oriented truth for forecasts, observed receipts and candidates."""

    def __init__(self, paths: MarketingDataPaths | None = None):
        super().__init__(paths)
        self._ensure_schema()

    def create_preflight(
        self,
        *,
        user_id: str,
        account_id: str,
        plan_id: str,
        platform: str | None,
        formula_version: str,
        input: dict[str, Any],
        scores: dict[str, Any],
        decision: dict[str, Any],
        session_id: str = "",
    ) -> dict[str, Any]:
        """Persist the prediction before action; records are never overwritten."""

        preflight_id = _id("preflight")
        with self._transaction() as db:
            plan = db.execute(
                """SELECT id FROM content_production_plans
                WHERE id=? AND user_id=? AND account_id=?""",
                (plan_id, user_id, account_id),
            ).fetchone()
            if plan is None:
                raise KeyError("production plan not found in account scope")
            db.execute(
                """INSERT INTO marketing_preflight_records
                (id,user_id,account_id,platform,plan_id,session_id,formula_version,
                 input_json,scores_json,decision_json,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,'created',?)""",
                (
                    preflight_id,
                    user_id,
                    account_id,
                    platform,
                    plan_id,
                    session_id,
                    formula_version,
                    _json(input),
                    _json(scores),
                    _json(decision),
                    _now(),
                ),
            )
        return self.get_preflight(preflight_id)

    def get_preflight(self, preflight_id: str) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM marketing_preflight_records WHERE id=?", (preflight_id,)
            ).fetchone()
        if row is None:
            raise KeyError("preflight record not found")
        return _preflight(row)

    def latest_preflight_for_plan(
        self, *, plan_id: str, user_id: str, account_id: str
    ) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                """SELECT * FROM marketing_preflight_records
                WHERE plan_id=? AND user_id=? AND account_id=?
                ORDER BY created_at DESC,id DESC LIMIT 1""",
                (plan_id, user_id, account_id),
            ).fetchone()
        if row is None:
            raise ValueError("content production requires a persisted preflight")
        return _preflight(row)

    def mark_preflight_used(self, preflight_id: str) -> dict[str, Any]:
        with self._transaction() as db:
            row = db.execute(
                "SELECT status FROM marketing_preflight_records WHERE id=?", (preflight_id,)
            ).fetchone()
            if row is None:
                raise KeyError("preflight record not found")
            if row["status"] == "created":
                db.execute(
                    "UPDATE marketing_preflight_records SET status='used_for_action' WHERE id=?",
                    (preflight_id,),
                )
        return self.get_preflight(preflight_id)

    def create_receipt(
        self,
        *,
        source_kind: str,
        source_id: str,
        receipt_type: str,
        user_id: str,
        account_id: str,
        summary: dict[str, Any],
        platform: str | None = None,
        plan_id: str | None = None,
        experiment_id: str | None = None,
        preflight_id: str | None = None,
        session_id: str = "",
    ) -> dict[str, Any]:
        """Create an idempotent, redacted pointer to an observed external fact."""

        source_kind = str(source_kind or "").strip()
        source_id = str(source_id or "").strip()
        receipt_type = str(receipt_type or "").strip()
        if not source_kind or not source_id or not receipt_type:
            raise ValueError("source_kind, source_id and receipt_type are required")
        with self._transaction() as db:
            resolved_experiment_id = str(experiment_id or "").strip() or None
            if not resolved_experiment_id and plan_id:
                plan = db.execute(
                    """SELECT experiment_id FROM content_production_plans
                    WHERE id=? AND user_id=? AND account_id=?""",
                    (plan_id, user_id, account_id),
                ).fetchone()
                resolved_experiment_id = (
                    str(plan["experiment_id"] or "").strip() or None if plan else None
                )
            existing = db.execute(
                """SELECT id FROM marketing_receipt_refs
                WHERE source_kind=? AND source_id=? AND receipt_type=?""",
                (source_kind, source_id, receipt_type),
            ).fetchone()
            if existing is not None:
                receipt_id = existing["id"]
            else:
                if preflight_id and db.execute(
                    "SELECT id FROM marketing_preflight_records WHERE id=?",
                    (preflight_id,),
                ).fetchone() is None:
                    raise KeyError("preflight record not found")
                receipt_id = _id("receipt")
                db.execute(
                    """INSERT INTO marketing_receipt_refs
                    (id,source_kind,source_id,receipt_type,user_id,account_id,platform,
                     plan_id,experiment_id,preflight_id,session_id,summary_json,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        receipt_id,
                        source_kind,
                        source_id,
                        receipt_type,
                        user_id,
                        account_id,
                        platform,
                        plan_id,
                        resolved_experiment_id,
                        preflight_id,
                        session_id,
                        _json(_redact(summary)),
                        _now(),
                    ),
                )
        return self.get_receipt(receipt_id)

    def get_receipt(self, receipt_id: str) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM marketing_receipt_refs WHERE id=?", (receipt_id,)
            ).fetchone()
        if row is None:
            raise KeyError("receipt ref not found")
        value = dict(row)
        value["summary"] = json.loads(value.pop("summary_json"))
        return value

    def create_learning_candidate(
        self,
        *,
        candidate_type: str,
        user_id: str,
        account_id: str,
        proposal: dict[str, Any],
        confidence: float,
        platform: str | None = None,
        preflight_id: str | None = None,
        receipt_ids: list[str] | None = None,
        receipt_refs: list[str] | None = None,
        evidence_refs: list[str] | None = None,
        prediction_id: str | None = None,
        source_key: str | None = None,
    ) -> dict[str, Any]:
        """Record an interpretation candidate without mutating Hermes memory."""

        if candidate_type not in LEARNING_TYPES:
            raise ValueError("unsupported learning candidate type")
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        refs = list(dict.fromkeys([*(receipt_ids or []), *(receipt_refs or [])]))
        evidence = list(dict.fromkeys(evidence_refs or []))
        source_value = str(source_key or "").strip() or None
        with self._transaction() as db:
            if source_value:
                existing = db.execute(
                    "SELECT id FROM marketing_learning_candidates WHERE source_key=?",
                    (source_value,),
                ).fetchone()
                if existing is not None:
                    return self.get_learning_candidate(existing["id"])
            if preflight_id and db.execute(
                "SELECT id FROM marketing_preflight_records WHERE id=?",
                (preflight_id,),
            ).fetchone() is None:
                raise KeyError("preflight record not found")
            for receipt_id in refs:
                if db.execute(
                    "SELECT id FROM marketing_receipt_refs WHERE id=?", (receipt_id,)
                ).fetchone() is None:
                    raise KeyError("receipt ref not found")
            candidate_id = _id("learn")
            db.execute(
                """INSERT INTO marketing_learning_candidates
                (id,source_key,candidate_type,user_id,account_id,platform,preflight_id,
                 prediction_id,receipt_refs_json,evidence_refs_json,proposal_json,
                 confidence,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'pending',?)""",
                (
                    candidate_id,
                    source_value,
                    candidate_type,
                    user_id,
                    account_id,
                    platform,
                    preflight_id,
                    prediction_id,
                    _json(refs),
                    _json(evidence),
                    _json(proposal),
                    confidence,
                    _now(),
                ),
            )
        return self.get_learning_candidate(candidate_id)

    def get_learning_candidate(self, candidate_id: str) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM marketing_learning_candidates WHERE id=?", (candidate_id,)
            ).fetchone()
        if row is None:
            raise KeyError("learning candidate not found")
        value = dict(row)
        value["receipt_refs"] = json.loads(value.pop("receipt_refs_json"))
        value["evidence_refs"] = json.loads(value.pop("evidence_refs_json"))
        value["proposal"] = json.loads(value.pop("proposal_json"))
        return value

    def list_learning_candidates(
        self,
        *,
        candidate_type: str | None = None,
        status: str | None = None,
        user_id: str | None = None,
        account_id: str | None = None,
        platform: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = "SELECT id FROM marketing_learning_candidates WHERE 1=1"
        params: list[Any] = []
        for column, value in (
            ("candidate_type", candidate_type),
            ("status", status),
            ("user_id", user_id),
            ("account_id", account_id),
            ("platform", platform),
        ):
            if value is not None:
                query += f" AND {column}=?"
                params.append(value)
        query += " ORDER BY created_at DESC,id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._connection() as db:
            rows = db.execute(query, params).fetchall()
        return [self.get_learning_candidate(row["id"]) for row in rows]

    def decide_learning_candidate(
        self,
        candidate_id: str,
        *,
        status: str,
        reason: str = "",
        authority: SystemAuthority | None = None,
    ) -> dict[str, Any]:
        require_system_authority(authority, EpistemicClass.DERIVED_KNOWLEDGE)
        if status not in {"accepted", "rejected", "superseded"}:
            raise ValueError("invalid learning candidate decision")
        with self._transaction() as db:
            row = db.execute(
                "SELECT status FROM marketing_learning_candidates WHERE id=?",
                (candidate_id,),
            ).fetchone()
            if row is None:
                raise KeyError("learning candidate not found")
            if row["status"] == "pending":
                db.execute(
                    """UPDATE marketing_learning_candidates
                    SET status=?,decision_reason=?,decided_at=? WHERE id=?""",
                    (status, str(reason)[:500], _now(), candidate_id),
                )
        return self.get_learning_candidate(candidate_id)

    def _ensure_schema(self) -> None:
        with self._connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS marketing_preflight_records (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    platform TEXT,
                    plan_id TEXT NOT NULL REFERENCES content_production_plans(id),
                    session_id TEXT NOT NULL DEFAULT '',
                    formula_version TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    scores_json TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'created',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_marketing_preflight_scope
                    ON marketing_preflight_records(account_id,platform,created_at);

                CREATE TABLE IF NOT EXISTS marketing_receipt_refs (
                    id TEXT PRIMARY KEY,
                    source_kind TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    receipt_type TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    platform TEXT,
                    plan_id TEXT,
                    experiment_id TEXT REFERENCES account_experiments(id),
                    preflight_id TEXT REFERENCES marketing_preflight_records(id),
                    session_id TEXT NOT NULL DEFAULT '',
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    UNIQUE(source_kind,source_id,receipt_type)
                );
                CREATE INDEX IF NOT EXISTS idx_marketing_receipt_scope
                    ON marketing_receipt_refs(account_id,platform,created_at);

                CREATE TABLE IF NOT EXISTS marketing_learning_candidates (
                    id TEXT PRIMARY KEY,
                    source_key TEXT,
                    candidate_type TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    platform TEXT,
                    preflight_id TEXT REFERENCES marketing_preflight_records(id),
                    prediction_id TEXT,
                    receipt_refs_json TEXT NOT NULL DEFAULT '[]',
                    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
                    proposal_json TEXT NOT NULL DEFAULT '{}',
                    confidence REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    decision_reason TEXT,
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_marketing_learning_scope
                    ON marketing_learning_candidates(account_id,platform,status,created_at);
                """
            )
            columns = {
                row["name"]
                for row in db.execute("PRAGMA table_info(marketing_learning_candidates)")
            }
            if "source_key" not in columns:
                db.execute("ALTER TABLE marketing_learning_candidates ADD COLUMN source_key TEXT")
            db.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS idx_marketing_learning_source
                ON marketing_learning_candidates(source_key) WHERE source_key IS NOT NULL"""
            )


def _preflight(row: Any) -> dict[str, Any]:
    value = dict(row)
    value["input"] = json.loads(value.pop("input_json"))
    value["scores"] = json.loads(value.pop("scores_json"))
    value["decision"] = json.loads(value.pop("decision_json"))
    return value
