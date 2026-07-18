"""Durable product-operation projections owned by Hermes ``state.db``."""

from __future__ import annotations

import json
import time
from typing import Any

from agent.marketing.domains.storage import MarketingDomainRepository


OPERATION_STATES = frozenset({"working", "waiting", "complete", "error"})


class MarketingOperationRepository(MarketingDomainRepository):
    """Persist the product-facing projection of a hidden native Agent turn."""

    def create(self, run: dict[str, Any], *, live_session_id: str) -> dict[str, Any]:
        operation_id = _required(run.get("operation_id"), "operation_id", 200)
        if not operation_id.startswith("marketing_operation_"):
            raise ValueError("operation_id must use the Marketing OS namespace")
        now = float(run.get("created_at") or time.time())
        values = {
            "account_id": _required(run.get("account_id"), "account_id", 160),
            "baseline_json": _encoded(run.get("baseline") or {}, "baseline", 100_000),
            "kind": _required(run.get("kind"), "kind", 120),
            "live_session_id": _required(live_session_id, "live_session_id", 240),
            "operation_json": _encoded(run.get("operation") or {}, "operation", 100_000),
            "project_id": str(run.get("project_id") or "")[:200],
            "stored_session_id": _required(
                run.get("stored_session_id"), "stored_session_id", 240
            ),
            "title": _required(run.get("title"), "title", 500),
            "user_id": _required(run.get("user_id") or "default", "user_id", 160),
            "visible_text": _required(run.get("visible_text"), "visible_text", 2_000),
        }
        with self._connection() as db:
            owner = db.execute(
                """SELECT entity_id FROM marketing_operating_entity_accounts
                WHERE user_id=? AND account_id=? AND status='active' LIMIT 1""",
                (values["user_id"], values["account_id"]),
            ).fetchone()
        entity_id = str(owner["entity_id"] or "") if owner is not None else ""

        from agent.harness import HarnessRepository

        harness = HarnessRepository(self.paths.agent_db)
        workflow = harness.create_workflow(
            namespace="marketing",
            owner_user_id=values["user_id"],
            owner_entity_id=entity_id,
            source_kind="marketing.operation",
            source_ref=operation_id,
            kind=values["kind"],
            title=values["title"],
            input=(
                run.get("harness_input")
                if isinstance(run.get("harness_input"), dict)
                else {
                    "baseline": run.get("baseline") or {},
                    "operation": run.get("operation") or {},
                }
            ),
            policy={"compatibility": "marketing.operation.v1"},
            steps=[
                {
                    "key": "agent_turn",
                    "kind": "agent_turn",
                    "worker_role": "marketing_coordinator",
                    "resource_scope": (
                        f"marketing:{values['user_id']}:"
                        f"{entity_id or values['account_id']}:{values['kind']}"
                    ),
                    "max_attempts": 3,
                }
            ],
            actor="marketing.operation",
            now=now,
        )
        claimed = harness.claim_ready_step(
            worker_id=f"gateway:{live_session_id}",
            workflow_id=str(workflow["id"]),
            lease_seconds=900,
            runner={
                "kind": "hermes.agent_turn",
                "live_session_id": live_session_id,
                "stored_session_id": values["stored_session_id"],
            },
            now=now,
        )
        if claimed is None:
            raise RuntimeError("Harness did not claim the operation Step")
        harness.start_step(
            step_id=str(claimed["id"]),
            lease_token=str(claimed["lease_token"]),
            now=now,
        )
        with self._transaction() as db:
            db.execute(
                """INSERT INTO marketing_operations
                (id,user_id,account_id,kind,state,live_session_id,stored_session_id,
                 project_id,title,visible_text,operation_json,baseline_json,results_json,
                 workflow_id,workflow_step_id,error,created_at,updated_at)
                VALUES (?,?,?,?,'working',?,?,?,?,?,?,?,'[]',?,?,'',?,?)""",
                (
                    operation_id,
                    values["user_id"],
                    values["account_id"],
                    values["kind"],
                    values["live_session_id"],
                    values["stored_session_id"],
                    values["project_id"],
                    values["title"],
                    values["visible_text"],
                    values["operation_json"],
                    values["baseline_json"],
                    workflow["id"],
                    claimed["id"],
                    now,
                    now,
                ),
            )
        result = self.get(operation_id)
        result["workflow_lease_token"] = str(claimed["lease_token"])
        return result

    def get(self, operation_id: str) -> dict[str, Any]:
        value = _required(operation_id, "operation_id", 200)
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM marketing_operations WHERE id=?", (value,)
            ).fetchone()
        if row is None:
            raise KeyError("Marketing OS operation not found")
        return _record(row)

    def update_state(
        self,
        operation_id: str,
        *,
        state: str,
        error: str = "",
        results: list[dict[str, Any]] | None = None,
        workflow_lease_token: str = "",
    ) -> dict[str, Any]:
        value = _required(operation_id, "operation_id", 200)
        state_value = str(state or "").strip()
        if state_value not in OPERATION_STATES:
            raise ValueError("operation state is invalid")
        results_json = _encoded(results or [], "results", 100_000)
        error_value = str(error or "").strip()[:4_000]
        now = time.time()
        completed_at = now if state_value in {"complete", "error"} else None
        current = self.get(value)
        workflow_id = str(current.get("workflow_id") or "")
        workflow_step_id = str(current.get("workflow_step_id") or "")
        lease_token = str(workflow_lease_token or "").strip()
        if workflow_id and workflow_step_id and lease_token:
            from agent.harness import HarnessRepository

            harness = HarnessRepository(self.paths.agent_db)
            if state_value in {"working", "waiting"}:
                harness.heartbeat(
                    step_id=workflow_step_id,
                    lease_token=lease_token,
                    extend_seconds=900,
                    now=now,
                )
            elif state_value == "complete":
                harness.complete_step(
                    step_id=workflow_step_id,
                    lease_token=lease_token,
                    output={"results": results or []},
                    artifacts=[
                        {
                            "kind": "domain_ref",
                            "object_type": str(item.get("object_type") or ""),
                            "object_id": str(item.get("object_id") or ""),
                            "metadata": {"title": str(item.get("title") or "")},
                        }
                        for item in (results or [])
                        if isinstance(item, dict) and item.get("object_id")
                    ],
                    now=now,
                )
            elif state_value == "error":
                harness.fail_step(
                    step_id=workflow_step_id,
                    lease_token=lease_token,
                    error={"code": "agent_turn_failed", "message": error_value},
                    retryable=True,
                    now=now,
                )
        with self._transaction() as db:
            updated = db.execute(
                """UPDATE marketing_operations
                SET state=?,results_json=?,error=?,updated_at=?,completed_at=?
                WHERE id=?""",
                (state_value, results_json, error_value, now, completed_at, value),
            ).rowcount
        if not updated:
            raise KeyError("Marketing OS operation not found")
        return self.get(value)

    def recover_execution(self, operation_id: str) -> dict[str, Any]:
        """Reclaim a process-owned Agent turn without converting it to error."""

        value = _required(operation_id, "operation_id", 200)
        current = self.get(value)
        workflow_id = str(current.get("workflow_id") or "")
        if workflow_id:
            from agent.harness import HarnessRepository

            HarnessRepository(self.paths.agent_db).recover_source(
                namespace="marketing",
                source_kind="marketing.operation",
                source_ref=value,
                actor="gateway.recovery",
            )
        now = time.time()
        with self._transaction() as db:
            db.execute(
                """UPDATE marketing_operations SET state='waiting',error='',
                updated_at=?,completed_at=NULL WHERE id=?""",
                (now, value),
            )
        return self.get(value)


def _record(row: Any) -> dict[str, Any]:
    return {
        "account_id": str(row["account_id"]),
        "baseline": _decoded(row["baseline_json"], {}),
        "completed_at": row["completed_at"],
        "created_at": float(row["created_at"]),
        "error": str(row["error"] or ""),
        "kind": str(row["kind"]),
        "live_session_id": str(row["live_session_id"] or ""),
        "operation": _decoded(row["operation_json"], {}),
        "operation_id": str(row["id"]),
        "project_id": str(row["project_id"] or ""),
        "results": _decoded(row["results_json"], []),
        "state": str(row["state"]),
        "stored_session_id": str(row["stored_session_id"] or ""),
        "title": str(row["title"]),
        "updated_at": float(row["updated_at"]),
        "user_id": str(row["user_id"]),
        "visible_text": str(row["visible_text"]),
        "workflow_id": str(row["workflow_id"] or ""),
        "workflow_step_id": str(row["workflow_step_id"] or ""),
    }


def _required(value: Any, field: str, limit: int) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    if len(normalized) > limit:
        raise ValueError(f"{field} is too long")
    return normalized


def _encoded(value: Any, field: str, limit: int) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be JSON serializable") from exc
    if len(encoded.encode("utf-8")) > limit:
        raise ValueError(f"{field} is too large")
    return encoded


def _decoded(value: Any, fallback: Any) -> Any:
    try:
        decoded = json.loads(str(value or ""))
    except (TypeError, ValueError):
        return fallback
    return decoded if isinstance(decoded, type(fallback)) else fallback
