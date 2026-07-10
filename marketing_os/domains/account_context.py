"""Read the canonical account operating context without an outer API shell.

This is deliberately a read projection over the existing product truth. It lets
the native Hermes gateway consume account data before write ownership and schema
migrations move into the fork, without introducing a second JSON/SQLite store.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from marketing_os.data_paths import MarketingDataPaths


_ACCOUNT_FIELDS = ("id", "platform", "username", "label", "status", "stats")
_NEXT_ACTION_BY_STAGE = {
    "not_started": "draft_audience_hypothesis",
    "goal_defined": "draft_audience_hypothesis",
    "audience_hypothesis_ready": "complete_benchmark_evidence",
    "benchmark_evidence_ready": "draft_account_positioning",
    "positioning_approved": "propose_first_content_experiment",
    "experiment_running": "collect_and_review_evidence",
}


class AccountContextRepository:
    """Produce a bounded, secret-free account context from canonical storage."""

    def __init__(self, paths: MarketingDataPaths | None = None):
        self.paths = paths or MarketingDataPaths.from_env()

    def list_accounts(self) -> dict[str, Any]:
        raw = _read_json(self.paths.config_dir / "accounts.json", {"accounts": []})
        rows = raw.get("accounts") if isinstance(raw, dict) else []
        accounts = [_sanitize_account(item) for item in rows if isinstance(item, dict)]
        accounts = [item for item in accounts if item.get("id")]
        return {"accounts": accounts, "total": len(accounts), "source": "marketing_store"}

    def read(self, *, user_id: str, account_id: str) -> dict[str, Any]:
        user_id = str(user_id or "default").strip() or "default"
        account_id = str(account_id or "").strip()
        if not account_id:
            raise ValueError("account_id is required")

        account = next(
            (item for item in self.list_accounts()["accounts"] if item.get("id") == account_id),
            None,
        )
        context: dict[str, Any] = {
            "user_id": user_id,
            "account_id": account_id,
            "connected": account is not None,
            "account": account,
            "lifecycle": _empty_lifecycle(),
            "account_dna": {},
            "actual_audience": None,
            "source": "marketing_store",
        }
        if not self.paths.agent_db.is_file():
            context["data_state"] = "database_missing"
            return context

        with closing(_connect_readonly(self.paths.agent_db)) as db:
            tables = _table_names(db)
            project = _active_project(db, tables, user_id=user_id, account_id=account_id)
            context["account_dna"] = _memory_account_dna(
                db, tables, user_id=user_id, account_id=account_id
            )
            if project is None:
                context["data_state"] = "ready"
                return context

            project_id = str(project["id"])
            audience = _confirmed_audience(
                db, tables, user_id=user_id, account_id=account_id, project_id=project_id
            )
            positioning = _approved_positioning(
                db, tables, user_id=user_id, account_id=account_id, project_id=project_id
            )
            snapshot = _latest_audience_snapshot(
                db, tables, user_id=user_id, account_id=account_id, project_id=project_id
            )
            benchmark_count = _scoped_count(
                db,
                tables,
                "benchmark_accounts",
                "user_id=? AND target_account_id=? AND project_id=? AND selection_status='selected'",
                (user_id, account_id, project_id),
            )
            experiment_count = _scoped_count(
                db,
                tables,
                "account_experiments",
                "user_id=? AND account_id=? AND project_id=?",
                (user_id, account_id, project_id),
            )
            stage = str(project["stage"] or "goal_defined")
            context["lifecycle"] = {
                "project_id": project_id,
                "business_goal": str(project["business_goal"] or ""),
                "stage": stage,
                "next_action": _NEXT_ACTION_BY_STAGE.get(stage, "review_account_strategy"),
                "audience_hypothesis": audience,
                "positioning": positioning,
                "benchmark_count": benchmark_count,
                "experiment_count": experiment_count,
                "data_gaps": list(audience.get("data_gaps", [])) if audience else [],
            }
            if positioning:
                context["account_dna"] = {
                    **context["account_dna"],
                    "persona": positioning.get("persona"),
                    "tone": positioning.get("tone"),
                    "audience": positioning.get("audience_summary", "以已确认目标受众假设为准"),
                    "content_pillars": positioning.get("content_pillars", []),
                    "taboos": positioning.get("taboos", []),
                    "goals": [positioning.get("promise")] if positioning.get("promise") else [],
                }
            context["actual_audience"] = snapshot
            context["data_state"] = "ready"
        return context


def _empty_lifecycle() -> dict[str, Any]:
    return {
        "project_id": None,
        "business_goal": "",
        "stage": "not_started",
        "next_action": "draft_audience_hypothesis",
        "audience_hypothesis": None,
        "positioning": None,
        "benchmark_count": 0,
        "experiment_count": 0,
        "data_gaps": [],
    }


def _sanitize_account(value: dict[str, Any]) -> dict[str, Any]:
    return {key: value.get(key) for key in _ACCOUNT_FIELDS if key in value}


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default
    except (OSError, json.JSONDecodeError):
        return default


def _json_object(value: Any, default: Any) -> Any:
    if not isinstance(value, str):
        return default
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return default
    return parsed


def _connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _table_names(db: sqlite3.Connection) -> set[str]:
    return {str(row[0]) for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _active_project(
    db: sqlite3.Connection, tables: set[str], *, user_id: str, account_id: str
) -> sqlite3.Row | None:
    if "account_strategy_projects" not in tables:
        return None
    return db.execute(
        """SELECT id,business_goal,stage FROM account_strategy_projects
        WHERE user_id=? AND account_id=? AND status='active'
        ORDER BY updated_at DESC LIMIT 1""",
        (user_id, account_id),
    ).fetchone()


def _confirmed_audience(
    db: sqlite3.Connection,
    tables: set[str],
    *,
    user_id: str,
    account_id: str,
    project_id: str,
) -> dict[str, Any] | None:
    if "audience_hypotheses" not in tables:
        return None
    row = db.execute(
        """SELECT id,version,segments_json,pains_json,scenarios_json,exclusions_json,
        data_gaps_json,confirmed_at FROM audience_hypotheses WHERE project_id=?
        AND user_id=? AND account_id=? AND status='confirmed' ORDER BY version DESC LIMIT 1""",
        (project_id, user_id, account_id),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "version": row["version"],
        "segments": _json_object(row["segments_json"], []),
        "pains": _json_object(row["pains_json"], []),
        "scenarios": _json_object(row["scenarios_json"], []),
        "exclusions": _json_object(row["exclusions_json"], []),
        "data_gaps": _json_object(row["data_gaps_json"], []),
        "confirmed_at": row["confirmed_at"],
    }


def _approved_positioning(
    db: sqlite3.Connection,
    tables: set[str],
    *,
    user_id: str,
    account_id: str,
    project_id: str,
) -> dict[str, Any] | None:
    if "positioning_versions" not in tables:
        return None
    row = db.execute(
        """SELECT positioning_json FROM positioning_versions WHERE project_id=?
        AND user_id=? AND account_id=? AND status='approved' ORDER BY version DESC LIMIT 1""",
        (project_id, user_id, account_id),
    ).fetchone()
    return None if row is None else _json_object(row["positioning_json"], {})


def _latest_audience_snapshot(
    db: sqlite3.Connection,
    tables: set[str],
    *,
    user_id: str,
    account_id: str,
    project_id: str,
) -> dict[str, Any] | None:
    if "audience_snapshots" not in tables:
        return None
    row = db.execute(
        """SELECT platform,dimensions_json,provenance_json,window_start,window_end,captured_at
        FROM audience_snapshots WHERE project_id=? AND user_id=? AND account_id=?
        ORDER BY captured_at DESC LIMIT 1""",
        (project_id, user_id, account_id),
    ).fetchone()
    if row is None:
        return None
    return {
        "platform": row["platform"],
        "dimensions": _json_object(row["dimensions_json"], {}),
        "provenance": _json_object(row["provenance_json"], {}),
        "window_start": row["window_start"],
        "window_end": row["window_end"],
        "captured_at": row["captured_at"],
    }


def _memory_account_dna(
    db: sqlite3.Connection, tables: set[str], *, user_id: str, account_id: str
) -> dict[str, Any]:
    if "memory_candidates" not in tables:
        return {}
    rows = db.execute(
        """SELECT content FROM memory_candidates WHERE user_id=? AND account_id=?
        AND kind='account' AND status IN ('verified','locked') ORDER BY created_at""",
        (user_id, account_id),
    ).fetchall()
    dna: dict[str, Any] = {}
    for row in rows:
        value = _json_object(row["content"], {})
        if isinstance(value, dict) and value.get("field"):
            dna[str(value["field"])] = value.get("value")
    return dna


def _scoped_count(
    db: sqlite3.Connection,
    tables: set[str],
    table: str,
    where: str,
    params: tuple[Any, ...],
) -> int:
    if table not in tables:
        return 0
    return int(db.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", params).fetchone()[0])
