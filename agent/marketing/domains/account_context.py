"""Read the canonical account operating context without an outer API shell.

This is deliberately a read projection over the existing product truth. It lets
the native Hermes gateway consume account data before write ownership and schema
migrations move into the fork, without introducing a second JSON/SQLite store.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from agent.marketing.data_paths import MarketingDataPaths


_ACCOUNT_FIELDS = (
    "id", "platform", "platform_user_id", "username", "label", "status",
    "auth_state", "permissions", "stats", "connected_at", "last_verified_at", "updated_at",
)
class AccountContextRepository:
    """Produce a bounded, secret-free account context from canonical storage."""

    def __init__(self, paths: MarketingDataPaths | None = None, session_db: Any = None):
        self._session_db = session_db
        resolved = paths or MarketingDataPaths.from_env()
        if paths is None and session_db is None and not os.environ.get(
            "MARKETING_OS_AGENT_DB"
        ):
            # SessionDB owns the canonical account database location.  Honor
            # its live default as well as tests/embedders which deliberately
            # replace that default, instead of reconstructing a parallel path.
            from hermes_state import DEFAULT_DB_PATH

            resolved = MarketingDataPaths(
                user_data=resolved.user_data,
                config_dir=resolved.config_dir,
                agent_db=Path(DEFAULT_DB_PATH),
            )
        if session_db is not None:
            resolved = MarketingDataPaths(
                user_data=resolved.user_data,
                config_dir=resolved.config_dir,
                agent_db=Path(session_db.db_path),
            )
        self.paths = resolved

    def list_accounts(self) -> dict[str, Any]:
        accounts = self._list_native_accounts()
        return {"accounts": accounts, "total": len(accounts), "source": "hermes_state"}

    def _list_native_accounts(self) -> list[dict[str, Any]]:
        from agent.account_registry import AccountRegistry
        from hermes_state import SessionDB

        legacy_accounts = self.paths.config_dir / "accounts.json"
        if (
            self._session_db is None
            and not self.paths.agent_db.is_file()
            and not legacy_accounts.is_file()
        ):
            return []
        db = self._session_db or SessionDB(db_path=self.paths.agent_db)
        owns_db = self._session_db is None
        registry = AccountRegistry(db)
        try:
            registry.import_legacy_accounts(legacy_accounts)
            registry.reconcile_unverified_legacy_accounts()
            rows = registry.list()
            return [_sanitize_account(item) for item in rows]
        finally:
            if owns_db:
                db.close()

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
            "source": "hermes_state",
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
            from agent.marketing.domains.account_strategy import AccountStrategyRepository

            operating_model = AccountStrategyRepository(self.paths).read_operating_model(
                user_id=user_id, account_id=account_id, project_id=project_id
            )
            audience = operating_model["audience_hypothesis"]
            positioning_record = operating_model["positioning"]
            positioning = (
                positioning_record.get("positioning") if positioning_record else None
            )
            snapshot = _latest_audience_snapshot(
                db, tables, user_id=user_id, account_id=account_id, project_id=project_id
            )
            stage = str(project["stage"] or "goal_defined")
            context["lifecycle"] = {
                "project_id": project_id,
                "business_goal": str(project["business_goal"] or ""),
                "stage": stage,
                "next_action": _next_action(operating_model),
                "creator_profile": operating_model["creator_profile"],
                "market_route": operating_model["market_route"],
                "audience_hypothesis": audience,
                "positioning_id": positioning_record.get("id") if positioning_record else None,
                "positioning": positioning,
                "content_system_id": (
                    operating_model["content_system"].get("id")
                    if operating_model["content_system"] else None
                ),
                "content_system": operating_model["content_system"],
                "strategy_alignment": operating_model["strategy_alignment"],
                "benchmark_readiness": operating_model["benchmark_readiness"],
                "benchmark_count": operating_model["benchmark_readiness"]["selected_count"],
                "experiment_count": operating_model["experiment_count"],
                "data_gaps": list(audience.get("data_gaps", [])) if audience else [],
            }
            if positioning and operating_model["strategy_alignment"]["positioning_current"]:
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

    def read_operating_entity(
        self,
        *,
        user_id: str,
        entity_id: str,
        focus_account_id: str = "",
    ) -> dict[str, Any]:
        """Aggregate strategy and first-party channel facts without merging them."""

        from agent.marketing.domains.operating_entities import OperatingEntityRepository

        # Operating-entity membership is Hermes session state. It may live in
        # the native SessionDB while legacy content evidence still points at a
        # separately configured MarketingDataPaths database.
        entity = OperatingEntityRepository(self.paths).get(
            entity_id=entity_id, user_id=user_id
        )
        contexts = [
            self.read(user_id=user_id, account_id=account_id)
            for account_id in entity.get("account_ids", [])
        ]
        strategy_contexts = [
            item
            for item in contexts
            if str((item.get("lifecycle") or {}).get("business_goal") or "").strip()
        ]
        shared = strategy_contexts[0] if strategy_contexts else None
        strategy_project_ids = list(
            dict.fromkeys(
                str((item.get("lifecycle") or {}).get("project_id") or "")
                for item in strategy_contexts
                if (item.get("lifecycle") or {}).get("project_id")
            )
        )
        focus = next(
            (item for item in contexts if item.get("account_id") == focus_account_id),
            None,
        )
        return {
            "user_id": user_id,
            "entity_id": entity_id,
            "operating_entity": {
                "id": entity["id"],
                "label": entity["label"],
                "platforms": entity.get("platforms", []),
                "account_ids": entity.get("account_ids", []),
            },
            "focus_account_id": focus_account_id or None,
            "focus_account_context": focus,
            "linked_account_contexts": contexts,
            "shared_operating_context": shared,
            "strategy_scope_status": (
                "ready"
                if len(strategy_project_ids) <= 1
                else "conflict_requires_explicit_merge_review"
            ),
            "strategy_project_ids": strategy_project_ids,
            "data_gaps": [
                *(
                    ["no_shared_operating_strategy"]
                    if not strategy_contexts
                    else []
                ),
                *(
                    ["multiple_platform_scoped_strategies_require_merge"]
                    if len(strategy_project_ids) > 1
                    else []
                ),
            ],
            "source": "hermes_state",
        }


def _empty_lifecycle() -> dict[str, Any]:
    return {
        "project_id": None,
        "business_goal": "",
        "stage": "not_started",
        "next_action": "begin_project",
        "creator_profile": None,
        "market_route": None,
        "audience_hypothesis": None,
        "positioning_id": None,
        "positioning": None,
        "content_system_id": None,
        "content_system": None,
        "strategy_alignment": None,
        "benchmark_readiness": None,
        "benchmark_count": 0,
        "experiment_count": 0,
        "data_gaps": [],
    }


def _next_action(model: dict[str, Any]) -> str:
    stage = str((model.get("project") or {}).get("stage") or "goal_defined")
    if not model.get("creator_profile"):
        return "draft_creator_profile"
    if not model.get("market_route"):
        return "select_market_route" if stage == "market_routes_ready" else "draft_market_routes"
    if not model.get("audience_hypothesis"):
        return "draft_audience_hypothesis"
    if not (model.get("benchmark_readiness") or {}).get("ready"):
        return "build_benchmark_operating_graph"
    if not model.get("positioning"):
        return "draft_account_positioning"
    if not (model.get("strategy_alignment") or {}).get("positioning_current"):
        return "revise_account_positioning"
    if not model.get("content_system"):
        return "draft_content_system"
    if not (model.get("strategy_alignment") or {}).get("content_system_current"):
        return "revise_content_system"
    if int(model.get("experiment_count") or 0) == 0:
        return "propose_first_content_experiment"
    if stage == "experiment_running":
        return "collect_and_review_experiment_receipts"
    return "review_account_operating_model"


def _sanitize_account(value: dict[str, Any]) -> dict[str, Any]:
    return {key: value.get(key) for key in _ACCOUNT_FIELDS if key in value}


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
