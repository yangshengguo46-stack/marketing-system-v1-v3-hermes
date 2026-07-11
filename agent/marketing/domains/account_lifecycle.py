"""Native, versioned account-onboarding writes for the Marketing OS fork."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.storage import MarketingDomainRepository


class AccountLifecycleRepository(MarketingDomainRepository):
    """Own the first account-strategy transitions inside the Hermes runtime."""

    def __init__(self, paths: MarketingDataPaths | None = None):
        super().__init__(paths)
        self._ensure_schema()

    def begin_project(
        self,
        *,
        user_id: str,
        account_id: str,
        business_goal: str,
        constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        goal = _bounded_text(business_goal, field="business_goal", limit=500)
        constraints_value = constraints or {}
        if not isinstance(constraints_value, dict):
            raise ValueError("constraints must be an object")
        constraints_json = _bounded_json(constraints_value, field="constraints", limit=8_000)
        with self._transaction() as db:
            existing = db.execute(
                """SELECT * FROM account_strategy_projects
                WHERE user_id=? AND account_id=? AND status='active'""",
                (user_id, account_id),
            ).fetchone()
            if existing is not None:
                return _project_record(existing, operation="existing")
            now = _now()
            project_id = f"strategy_{uuid.uuid4().hex}"
            db.execute(
                """INSERT INTO account_strategy_projects
                (id,user_id,account_id,business_goal,constraints_json,stage,status,created_at,updated_at)
                VALUES (?,?,?,?,?,'goal_defined','active',?,?)""",
                (project_id, user_id, account_id, goal, constraints_json, now, now),
            )
            row = db.execute(
                "SELECT * FROM account_strategy_projects WHERE id=?",
                (project_id,),
            ).fetchone()
        return _project_record(row, operation="created")

    def draft_audience_hypothesis(
        self,
        *,
        user_id: str,
        account_id: str,
        project_id: str,
        segments: list[Any],
        pains: list[Any] | None = None,
        scenarios: list[Any] | None = None,
        exclusions: list[Any] | None = None,
        data_gaps: list[Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "segments_json": _bounded_list(segments, field="segments", required=True),
            "pains_json": _bounded_list(pains or [], field="pains"),
            "scenarios_json": _bounded_list(scenarios or [], field="scenarios"),
            "exclusions_json": _bounded_list(exclusions or [], field="exclusions"),
            "data_gaps_json": _bounded_list(data_gaps or [], field="data_gaps"),
        }
        with self._transaction() as db:
            _require_active_project(
                db, user_id=user_id, account_id=account_id, project_id=project_id
            )
            version = int(
                db.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 FROM audience_hypotheses WHERE project_id=?",
                    (project_id,),
                ).fetchone()[0]
            )
            hypothesis_id = f"audience_{uuid.uuid4().hex}"
            db.execute(
                """INSERT INTO audience_hypotheses
                (id,project_id,user_id,account_id,version,segments_json,pains_json,
                 scenarios_json,exclusions_json,data_gaps_json,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,'draft',?)""",
                (
                    hypothesis_id,
                    project_id,
                    user_id,
                    account_id,
                    version,
                    payload["segments_json"],
                    payload["pains_json"],
                    payload["scenarios_json"],
                    payload["exclusions_json"],
                    payload["data_gaps_json"],
                    _now(),
                ),
            )
            row = db.execute(
                "SELECT * FROM audience_hypotheses WHERE id=?",
                (hypothesis_id,),
            ).fetchone()
        return _hypothesis_record(row, operation="drafted")

    def confirm_audience_hypothesis(
        self,
        *,
        user_id: str,
        account_id: str,
        project_id: str,
        hypothesis_id: str,
        confirmed_by_user: bool,
    ) -> dict[str, Any]:
        if confirmed_by_user is not True:
            raise ValueError("explicit user confirmation is required")
        with self._transaction() as db:
            _require_active_project(
                db, user_id=user_id, account_id=account_id, project_id=project_id
            )
            row = db.execute(
                """SELECT * FROM audience_hypotheses
                WHERE id=? AND project_id=? AND user_id=? AND account_id=?""",
                (hypothesis_id, project_id, user_id, account_id),
            ).fetchone()
            if row is None:
                raise KeyError("audience hypothesis not found in account scope")
            if row["status"] == "confirmed":
                return _hypothesis_record(row, operation="already_confirmed")
            if row["status"] != "draft":
                raise ValueError("only a draft audience hypothesis can be confirmed")
            now = _now()
            db.execute(
                """UPDATE audience_hypotheses SET status='superseded'
                WHERE project_id=? AND status='confirmed'""",
                (project_id,),
            )
            db.execute(
                """UPDATE audience_hypotheses
                SET status='confirmed', confirmed_at=? WHERE id=?""",
                (now, hypothesis_id),
            )
            db.execute(
                """UPDATE account_strategy_projects
                SET stage='audience_hypothesis_ready', updated_at=? WHERE id=?""",
                (now, project_id),
            )
            confirmed = db.execute(
                "SELECT * FROM audience_hypotheses WHERE id=?",
                (hypothesis_id,),
            ).fetchone()
        return _hypothesis_record(confirmed, operation="confirmed")

    def _ensure_schema(self) -> None:
        with self._connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS account_strategy_projects (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    business_goal TEXT NOT NULL,
                    constraints_json TEXT NOT NULL DEFAULT '{}',
                    stage TEXT NOT NULL DEFAULT 'goal_defined',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_strategy_projects_one_active
                    ON account_strategy_projects(user_id, account_id) WHERE status='active';
                CREATE INDEX IF NOT EXISTS idx_strategy_projects_scope
                    ON account_strategy_projects(user_id, account_id, status);

                CREATE TABLE IF NOT EXISTS audience_hypotheses (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES account_strategy_projects(id),
                    user_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    segments_json TEXT NOT NULL DEFAULT '[]',
                    pains_json TEXT NOT NULL DEFAULT '[]',
                    scenarios_json TEXT NOT NULL DEFAULT '[]',
                    exclusions_json TEXT NOT NULL DEFAULT '[]',
                    data_gaps_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL,
                    confirmed_at TEXT,
                    UNIQUE(project_id, version)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_audience_one_confirmed
                    ON audience_hypotheses(project_id) WHERE status='confirmed';
                CREATE INDEX IF NOT EXISTS idx_audience_scope
                    ON audience_hypotheses(user_id, account_id, project_id);
                """
            )

def _require_active_project(
    db: sqlite3.Connection, *, user_id: str, account_id: str, project_id: str
) -> sqlite3.Row:
    row = db.execute(
        """SELECT * FROM account_strategy_projects
        WHERE id=? AND user_id=? AND account_id=? AND status='active'""",
        (project_id, user_id, account_id),
    ).fetchone()
    if row is None:
        raise KeyError("active strategy project not found in account scope")
    return row


def _project_record(row: sqlite3.Row, *, operation: str) -> dict[str, Any]:
    value = dict(row)
    value["constraints"] = json.loads(value.pop("constraints_json"))
    value["operation"] = operation
    return value


def _hypothesis_record(row: sqlite3.Row, *, operation: str) -> dict[str, Any]:
    value = dict(row)
    for key in (
        "segments_json",
        "pains_json",
        "scenarios_json",
        "exclusions_json",
        "data_gaps_json",
    ):
        value[key.removesuffix("_json")] = json.loads(value.pop(key))
    value["operation"] = operation
    return value


def _bounded_text(value: Any, *, field: str, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    if len(text) > limit:
        raise ValueError(f"{field} exceeds {limit} characters")
    return text


def _bounded_json(value: Any, *, field: str, limit: int) -> str:
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be JSON serializable") from exc
    if len(encoded.encode("utf-8")) > limit:
        raise ValueError(f"{field} exceeds {limit} bytes")
    return encoded


def _bounded_list(value: Any, *, field: str, required: bool = False) -> str:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    if required and not value:
        raise ValueError(f"{field} must contain at least one item")
    if len(value) > 30:
        raise ValueError(f"{field} exceeds 30 items")
    return _bounded_json(value, field=field, limit=16_000)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
