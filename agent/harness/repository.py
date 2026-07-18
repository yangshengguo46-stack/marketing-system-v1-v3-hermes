"""Durable Workflow/Step execution primitives backed by Hermes ``state.db``."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from hermes_constants import get_hermes_home


WORKFLOW_STATES = frozenset(
    {
        "queued",
        "planning",
        "running",
        "waiting_approval",
        "retrying",
        "paused",
        "failed",
        "cancelled",
        "completed",
    }
)
STEP_STATES = frozenset(
    {
        "blocked",
        "ready",
        "leased",
        "running",
        "waiting_approval",
        "retry_wait",
        "failed",
        "cancelled",
        "succeeded",
    }
)
ACTIVE_STEP_STATES = frozenset({"leased", "running"})
TERMINAL_STEP_STATES = frozenset({"failed", "cancelled", "succeeded"})


class HarnessRepository:
    """Own durable execution facts without owning product facts.

    The repository deliberately accepts canonical object references as
    artifacts. It never writes Marketing content, media, publishing or metric
    facts itself.
    """

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path is not None else get_hermes_home() / "state.db"
        from hermes_state import SessionDB

        owner = SessionDB(db_path=self.db_path)
        owner.close()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        db = self._connect()
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def create_workflow(
        self,
        *,
        namespace: str,
        owner_user_id: str,
        kind: str,
        title: str,
        steps: Sequence[dict[str, Any]],
        owner_entity_id: str = "",
        source_kind: str = "",
        source_ref: str = "",
        input: dict[str, Any] | None = None,
        policy: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
        priority: int = 0,
        workflow_id: str = "",
        actor: str = "system",
        now: float | None = None,
    ) -> dict[str, Any]:
        """Create an immutable Step DAG and append its initial events."""

        namespace_value = _required(namespace, "namespace", 120)
        user_value = _required(owner_user_id, "owner_user_id", 160)
        kind_value = _required(kind, "kind", 160)
        title_value = _required(title, "title", 500)
        entity_value = _bounded(owner_entity_id, "owner_entity_id", 200)
        source_kind_value = _bounded(source_kind, "source_kind", 120)
        source_ref_value = _bounded(source_ref, "source_ref", 240)
        if bool(source_kind_value) != bool(source_ref_value):
            raise ValueError("source_kind and source_ref must be provided together")
        actor_value = _required(actor, "actor", 160)
        definitions = _validate_steps(steps)
        created_at = float(now if now is not None else time.time())
        workflow_value = workflow_id or f"workflow_{uuid.uuid4().hex}"
        if not workflow_value.startswith("workflow_"):
            raise ValueError("workflow_id must use the workflow_ namespace")

        step_ids = {
            definition["key"]: f"step_{uuid.uuid4().hex}"
            for definition in definitions
        }
        with self._transaction() as db:
            db.execute(
                """INSERT INTO harness_workflows
                (id,namespace,owner_user_id,owner_entity_id,source_kind,source_ref,
                 kind,title,state,priority,input_json,policy_json,budget_json,
                 result_json,error_json,version,created_at,updated_at,completed_at)
                VALUES (?,?,?,?,?,?,?,?,'queued',?,?,?,?, '{}','{}',1,?,?,NULL)""",
                (
                    workflow_value,
                    namespace_value,
                    user_value,
                    entity_value,
                    source_kind_value,
                    source_ref_value,
                    kind_value,
                    title_value,
                    int(priority),
                    _encoded(input or {}, "input"),
                    _encoded(policy or {}, "policy"),
                    _encoded(budget or {}, "budget"),
                    created_at,
                    created_at,
                ),
            )
            _append_event(
                db,
                workflow_id=workflow_value,
                event_kind="workflow.created",
                actor=actor_value,
                payload={"kind": kind_value, "source_ref": source_ref_value},
                created_at=created_at,
            )
            for sequence, definition in enumerate(definitions):
                step_id = step_ids[definition["key"]]
                state = "ready" if not definition["depends_on"] else "blocked"
                db.execute(
                    """INSERT INTO harness_steps
                    (id,workflow_id,step_key,kind,state,sequence,worker_role,
                     toolset_json,resource_scope,input_json,output_json,error_json,
                     retry_policy_json,attempt_count,max_attempts,available_at,
                     lease_owner,lease_token_hash,lease_expires_at,heartbeat_at,
                     version,created_at,updated_at,started_at,completed_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?, '{}','{}',?,0,?,?, '', '',NULL,NULL,
                            1,?,?,NULL,NULL)""",
                    (
                        step_id,
                        workflow_value,
                        definition["key"],
                        definition["kind"],
                        state,
                        sequence,
                        definition["worker_role"],
                        _encoded(definition["toolsets"], "toolsets"),
                        definition["resource_scope"],
                        _encoded(definition["input"], "step input"),
                        _encoded(definition["retry_policy"], "retry policy"),
                        definition["max_attempts"],
                        created_at,
                        created_at,
                        created_at,
                    ),
                )
                _append_event(
                    db,
                    workflow_id=workflow_value,
                    step_id=step_id,
                    event_kind="step.created",
                    actor=actor_value,
                    payload={"state": state, "step_key": definition["key"]},
                    created_at=created_at,
                )
            for definition in definitions:
                for dependency_key in definition["depends_on"]:
                    db.execute(
                        """INSERT INTO harness_step_dependencies
                        (workflow_id,step_id,depends_on_step_id,created_at)
                        VALUES (?,?,?,?)""",
                        (
                            workflow_value,
                            step_ids[definition["key"]],
                            step_ids[dependency_key],
                            created_at,
                        ),
                    )
        return self.get_workflow(workflow_value)

    def get_workflow(
        self,
        workflow_id: str,
        *,
        include_events: bool = False,
    ) -> dict[str, Any]:
        value = _required(workflow_id, "workflow_id", 200)
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM harness_workflows WHERE id=?", (value,)
            ).fetchone()
            if row is None:
                raise KeyError("workflow not found")
            steps = db.execute(
                "SELECT * FROM harness_steps WHERE workflow_id=? ORDER BY sequence,id",
                (value,),
            ).fetchall()
            dependencies = db.execute(
                """SELECT child.step_key AS child_key,parent.step_key AS parent_key
                FROM harness_step_dependencies d
                JOIN harness_steps child ON child.id=d.step_id
                JOIN harness_steps parent ON parent.id=d.depends_on_step_id
                WHERE d.workflow_id=? ORDER BY child.sequence,parent.sequence""",
                (value,),
            ).fetchall()
            events = (
                db.execute(
                    "SELECT * FROM harness_events WHERE workflow_id=? ORDER BY id",
                    (value,),
                ).fetchall()
                if include_events
                else []
            )
        parents: dict[str, list[str]] = {}
        for dependency in dependencies:
            parents.setdefault(str(dependency["child_key"]), []).append(
                str(dependency["parent_key"])
            )
        result = _workflow_record(row)
        result["steps"] = [
            {**_step_record(step), "depends_on": parents.get(str(step["step_key"]), [])}
            for step in steps
        ]
        if include_events:
            result["events"] = [_event_record(event) for event in events]
        return result

    def find_by_source(
        self, *, namespace: str, source_kind: str, source_ref: str
    ) -> dict[str, Any] | None:
        values = (
            _required(namespace, "namespace", 120),
            _required(source_kind, "source_kind", 120),
            _required(source_ref, "source_ref", 240),
        )
        with self._connection() as db:
            row = db.execute(
                """SELECT id FROM harness_workflows
                WHERE namespace=? AND source_kind=? AND source_ref=?""",
                values,
            ).fetchone()
        return self.get_workflow(str(row["id"])) if row is not None else None

    def list_workflows(
        self,
        *,
        namespace: str,
        owner_user_id: str,
        owner_entity_id: str = "",
        states: Sequence[str] = (),
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        namespace_value = _required(namespace, "namespace", 120)
        user_value = _required(owner_user_id, "owner_user_id", 160)
        entity_value = _bounded(owner_entity_id, "owner_entity_id", 200)
        state_values = [str(state) for state in states]
        if any(state not in WORKFLOW_STATES for state in state_values):
            raise ValueError("workflow state filter is invalid")
        clauses = ["namespace=?", "owner_user_id=?"]
        params: list[Any] = [namespace_value, user_value]
        if entity_value:
            clauses.append("owner_entity_id=?")
            params.append(entity_value)
        if state_values:
            clauses.append("state IN (" + ",".join("?" for _ in state_values) + ")")
            params.extend(state_values)
        params.append(max(1, min(int(limit), 200)))
        with self._connection() as db:
            rows = db.execute(
                "SELECT * FROM harness_workflows WHERE "
                + " AND ".join(clauses)
                + " ORDER BY updated_at DESC,id DESC LIMIT ?",
                params,
            ).fetchall()
        return [_workflow_record(row) for row in rows]

    def claim_ready_step(
        self,
        *,
        worker_id: str,
        workflow_id: str = "",
        lease_seconds: int = 900,
        runner: dict[str, Any] | None = None,
        step_kinds: Sequence[str] = (),
        now: float | None = None,
    ) -> dict[str, Any] | None:
        """Atomically claim one ready Step and create a durable Attempt."""

        worker_value = _required(worker_id, "worker_id", 200)
        workflow_value = _bounded(workflow_id, "workflow_id", 200)
        kind_values = [_required(value, "step kind", 160) for value in step_kinds]
        lease_value = max(5, min(int(lease_seconds), 86_400))
        claimed_at = float(now if now is not None else time.time())
        lease_token = secrets.token_urlsafe(32)
        token_hash = _token_hash(lease_token)
        with self._transaction() as db:
            self._promote_due_retries_locked(db, now=claimed_at)
            self._reclaim_locked(db, now=claimed_at, workflow_id=workflow_value)
            where_workflow = "AND s.workflow_id=?" if workflow_value else ""
            where_kinds = (
                "AND s.kind IN (" + ",".join("?" for _ in kind_values) + ")"
                if kind_values
                else ""
            )
            params: list[Any] = [claimed_at]
            if workflow_value:
                params.append(workflow_value)
            params.extend(kind_values)
            row = db.execute(
                f"""SELECT s.* FROM harness_steps s
                JOIN harness_workflows w ON w.id=s.workflow_id
                WHERE s.state='ready' AND s.available_at<=?
                  AND w.state IN ('queued','planning','running','retrying')
                  {where_workflow}
                  {where_kinds}
                  AND (
                    s.resource_scope='' OR NOT EXISTS (
                      SELECT 1 FROM harness_steps active
                      WHERE active.resource_scope=s.resource_scope
                        AND active.id<>s.id
                        AND active.state IN ('leased','running')
                        AND active.lease_expires_at>?
                    )
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM harness_step_dependencies d
                    JOIN harness_steps parent ON parent.id=d.depends_on_step_id
                    WHERE d.step_id=s.id AND parent.state<>'succeeded'
                  )
                ORDER BY w.priority DESC,s.sequence,s.created_at,s.id LIMIT 1""",
                [*params, claimed_at],
            ).fetchone()
            if row is None:
                return None
            step_id = str(row["id"])
            attempt_number = int(row["attempt_count"]) + 1
            attempt_id = f"attempt_{uuid.uuid4().hex}"
            expires_at = claimed_at + lease_value
            updated = db.execute(
                """UPDATE harness_steps
                SET state='leased',attempt_count=?,lease_owner=?,lease_token_hash=?,
                    lease_expires_at=?,heartbeat_at=?,started_at=COALESCE(started_at,?),
                    updated_at=?,version=version+1
                WHERE id=? AND state='ready' AND version=?""",
                (
                    attempt_number,
                    worker_value,
                    token_hash,
                    expires_at,
                    claimed_at,
                    claimed_at,
                    claimed_at,
                    step_id,
                    int(row["version"]),
                ),
            ).rowcount
            if updated != 1:
                return None
            db.execute(
                """INSERT INTO harness_attempts
                (id,workflow_id,step_id,attempt_number,state,worker_id,
                 lease_token_hash,input_hash,runner_json,output_json,error_json,
                 started_at,heartbeat_at,ended_at)
                VALUES (?,?,?,?, 'leased',?,?,?,?, '{}','{}',?,?,NULL)""",
                (
                    attempt_id,
                    str(row["workflow_id"]),
                    step_id,
                    attempt_number,
                    worker_value,
                    token_hash,
                    _content_hash(str(row["input_json"])),
                    _encoded(runner or {}, "runner"),
                    claimed_at,
                    claimed_at,
                ),
            )
            db.execute(
                """UPDATE harness_workflows
                SET state='running',updated_at=?,version=version+1
                WHERE id=? AND state IN ('queued','planning','retrying')""",
                (claimed_at, str(row["workflow_id"])),
            )
            _append_event(
                db,
                workflow_id=str(row["workflow_id"]),
                step_id=step_id,
                attempt_id=attempt_id,
                event_kind="step.leased",
                actor=worker_value,
                payload={"attempt_number": attempt_number, "lease_expires_at": expires_at},
                created_at=claimed_at,
            )
            claimed = db.execute(
                "SELECT * FROM harness_steps WHERE id=?", (step_id,)
            ).fetchone()
        return {
            **_step_record(claimed),
            "attempt_id": attempt_id,
            "lease_token": lease_token,
        }

    def start_step(
        self, *, step_id: str, lease_token: str, now: float | None = None
    ) -> dict[str, Any]:
        started_at = float(now if now is not None else time.time())
        with self._transaction() as db:
            row, attempt = self._authorized_active_locked(db, step_id, lease_token)
            if str(row["state"]) == "leased":
                db.execute(
                    """UPDATE harness_steps SET state='running',heartbeat_at=?,
                    updated_at=?,version=version+1 WHERE id=?""",
                    (started_at, started_at, str(row["id"])),
                )
                db.execute(
                    """UPDATE harness_attempts SET state='running',heartbeat_at=?
                    WHERE id=?""",
                    (started_at, str(attempt["id"])),
                )
                _append_event(
                    db,
                    workflow_id=str(row["workflow_id"]),
                    step_id=str(row["id"]),
                    attempt_id=str(attempt["id"]),
                    event_kind="step.started",
                    actor=str(row["lease_owner"]),
                    payload={},
                    created_at=started_at,
                )
            updated = db.execute(
                "SELECT * FROM harness_steps WHERE id=?", (str(row["id"]),)
            ).fetchone()
        return _step_record(updated)

    def heartbeat(
        self,
        *,
        step_id: str,
        lease_token: str,
        extend_seconds: int = 900,
        now: float | None = None,
    ) -> dict[str, Any]:
        heartbeat_at = float(now if now is not None else time.time())
        extension = max(5, min(int(extend_seconds), 86_400))
        with self._transaction() as db:
            row, attempt = self._authorized_active_locked(db, step_id, lease_token)
            expires_at = heartbeat_at + extension
            db.execute(
                """UPDATE harness_steps SET heartbeat_at=?,lease_expires_at=?,
                updated_at=?,version=version+1 WHERE id=?""",
                (heartbeat_at, expires_at, heartbeat_at, str(row["id"])),
            )
            db.execute(
                "UPDATE harness_attempts SET heartbeat_at=? WHERE id=?",
                (heartbeat_at, str(attempt["id"])),
            )
            updated = db.execute(
                "SELECT * FROM harness_steps WHERE id=?", (str(row["id"]),)
            ).fetchone()
        return _step_record(updated)

    def complete_step(
        self,
        *,
        step_id: str,
        lease_token: str,
        output: dict[str, Any] | None = None,
        artifacts: Sequence[dict[str, Any]] = (),
        now: float | None = None,
    ) -> dict[str, Any]:
        completed_at = float(now if now is not None else time.time())
        output_json = _encoded(output or {}, "output")
        with self._transaction() as db:
            row, attempt = self._authorized_or_completed_locked(
                db, step_id, lease_token, output_json
            )
            if str(row["state"]) == "succeeded":
                return self.get_workflow(str(row["workflow_id"]))
            workflow_id = str(row["workflow_id"])
            db.execute(
                """UPDATE harness_steps
                SET state='succeeded',output_json=?,error_json='{}',lease_owner='',
                    lease_token_hash='',lease_expires_at=NULL,heartbeat_at=?,
                    completed_at=?,updated_at=?,version=version+1 WHERE id=?""",
                (output_json, completed_at, completed_at, completed_at, str(row["id"])),
            )
            db.execute(
                """UPDATE harness_attempts SET state='succeeded',output_json=?,
                error_json='{}',heartbeat_at=?,ended_at=? WHERE id=?""",
                (output_json, completed_at, completed_at, str(attempt["id"])),
            )
            for artifact in artifacts:
                self._insert_artifact_locked(
                    db,
                    workflow_id=workflow_id,
                    step_id=str(row["id"]),
                    attempt_id=str(attempt["id"]),
                    artifact=artifact,
                    created_at=completed_at,
                )
            _append_event(
                db,
                workflow_id=workflow_id,
                step_id=str(row["id"]),
                attempt_id=str(attempt["id"]),
                event_kind="step.succeeded",
                actor=str(row["lease_owner"]),
                payload={"output_hash": _content_hash(output_json)},
                created_at=completed_at,
            )
            self._promote_dependents_locked(
                db, workflow_id=workflow_id, actor="harness", now=completed_at
            )
            remaining = int(
                db.execute(
                    """SELECT COUNT(*) FROM harness_steps
                    WHERE workflow_id=? AND state<>'succeeded'""",
                    (workflow_id,),
                ).fetchone()[0]
            )
            if remaining == 0:
                db.execute(
                    """UPDATE harness_workflows SET state='completed',result_json=?,
                    error_json='{}',completed_at=?,updated_at=?,version=version+1
                    WHERE id=?""",
                    (output_json, completed_at, completed_at, workflow_id),
                )
                _append_event(
                    db,
                    workflow_id=workflow_id,
                    event_kind="workflow.completed",
                    actor="harness",
                    payload={},
                    created_at=completed_at,
                )
            else:
                failed = int(
                    db.execute(
                        """SELECT COUNT(*) FROM harness_steps
                        WHERE workflow_id=? AND state='failed'""",
                        (workflow_id,),
                    ).fetchone()[0]
                )
                if not failed:
                    db.execute(
                        """UPDATE harness_workflows SET state='running',updated_at=?,
                        completed_at=NULL,version=version+1 WHERE id=?""",
                        (completed_at, workflow_id),
                    )
        return self.get_workflow(workflow_id)

    def fail_step(
        self,
        *,
        step_id: str,
        lease_token: str,
        error: dict[str, Any] | str,
        retryable: bool,
        retry_delay_seconds: float = 0,
        now: float | None = None,
    ) -> dict[str, Any]:
        failed_at = float(now if now is not None else time.time())
        error_value = error if isinstance(error, dict) else {"message": str(error)}
        error_json = _encoded(error_value, "error")
        with self._transaction() as db:
            row, attempt = self._authorized_active_locked(db, step_id, lease_token)
            workflow_id = str(row["workflow_id"])
            will_retry = bool(retryable) and int(row["attempt_count"]) < int(
                row["max_attempts"]
            )
            next_state = "retry_wait" if will_retry else "failed"
            available_at = failed_at + max(0.0, float(retry_delay_seconds))
            db.execute(
                """UPDATE harness_steps SET state=?,error_json=?,available_at=?,
                lease_owner='',lease_token_hash='',lease_expires_at=NULL,
                heartbeat_at=?,completed_at=?,updated_at=?,version=version+1
                WHERE id=?""",
                (
                    next_state,
                    error_json,
                    available_at,
                    failed_at,
                    None if will_retry else failed_at,
                    failed_at,
                    str(row["id"]),
                ),
            )
            db.execute(
                """UPDATE harness_attempts SET state=?,error_json=?,heartbeat_at=?,
                ended_at=? WHERE id=?""",
                (
                    "retryable_failed" if will_retry else "failed",
                    error_json,
                    failed_at,
                    failed_at,
                    str(attempt["id"]),
                ),
            )
            _append_event(
                db,
                workflow_id=workflow_id,
                step_id=str(row["id"]),
                attempt_id=str(attempt["id"]),
                event_kind="step.retry_scheduled" if will_retry else "step.failed",
                actor=str(row["lease_owner"]),
                payload={"available_at": available_at, "error": error_value},
                created_at=failed_at,
            )
            db.execute(
                """UPDATE harness_workflows SET state=?,error_json=?,updated_at=?,
                completed_at=?,version=version+1 WHERE id=?""",
                (
                    "retrying" if will_retry else "failed",
                    error_json,
                    failed_at,
                    None if will_retry else failed_at,
                    workflow_id,
                ),
            )
            if not will_retry:
                _append_event(
                    db,
                    workflow_id=workflow_id,
                    event_kind="workflow.failed",
                    actor="harness",
                    payload={"step_id": str(row["id"]), "error": error_value},
                    created_at=failed_at,
                )
        return self.get_workflow(workflow_id)

    def request_approval(
        self,
        *,
        step_id: str,
        lease_token: str,
        approval_key: str,
        request: dict[str, Any],
        requested_by: str,
        contract_version: str = "",
        expires_at: float | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        requested_at = float(now if now is not None else time.time())
        key_value = _required(approval_key, "approval_key", 240)
        actor = _required(requested_by, "requested_by", 160)
        with self._transaction() as db:
            row, attempt = self._authorized_active_locked(db, step_id, lease_token)
            approval_id = f"approval_{uuid.uuid4().hex}"
            db.execute(
                """INSERT INTO harness_approvals
                (id,workflow_id,step_id,approval_key,state,request_json,decision_json,
                 requested_by,decided_by,contract_version,requested_at,expires_at,decided_at)
                VALUES (?,?,?,?, 'pending',?,'{}',?,'',?,?,?,NULL)""",
                (
                    approval_id,
                    str(row["workflow_id"]),
                    str(row["id"]),
                    key_value,
                    _encoded(request, "approval request"),
                    actor,
                    _bounded(contract_version, "contract_version", 160),
                    requested_at,
                    expires_at,
                ),
            )
            db.execute(
                """UPDATE harness_steps SET state='waiting_approval',lease_owner='',
                lease_token_hash='',lease_expires_at=NULL,heartbeat_at=?,updated_at=?,
                version=version+1 WHERE id=?""",
                (requested_at, requested_at, str(row["id"])),
            )
            db.execute(
                """UPDATE harness_attempts SET state='waiting_approval',heartbeat_at=?,
                ended_at=? WHERE id=?""",
                (requested_at, requested_at, str(attempt["id"])),
            )
            db.execute(
                """UPDATE harness_workflows SET state='waiting_approval',updated_at=?,
                version=version+1 WHERE id=?""",
                (requested_at, str(row["workflow_id"])),
            )
            _append_event(
                db,
                workflow_id=str(row["workflow_id"]),
                step_id=str(row["id"]),
                attempt_id=str(attempt["id"]),
                event_kind="approval.requested",
                actor=actor,
                payload={"approval_id": approval_id, "approval_key": key_value},
                created_at=requested_at,
            )
            approval = db.execute(
                "SELECT * FROM harness_approvals WHERE id=?", (approval_id,)
            ).fetchone()
        return _approval_record(approval)

    def decide_approval(
        self,
        *,
        approval_id: str,
        approved: bool,
        decided_by: str,
        decision: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        value = _required(approval_id, "approval_id", 200)
        actor = _required(decided_by, "decided_by", 160)
        decided_at = float(now if now is not None else time.time())
        with self._transaction() as db:
            approval = db.execute(
                "SELECT * FROM harness_approvals WHERE id=?", (value,)
            ).fetchone()
            if approval is None:
                raise KeyError("approval not found")
            if str(approval["state"]) != "pending":
                raise ValueError("approval is no longer pending")
            if approval["expires_at"] is not None and float(approval["expires_at"]) <= decided_at:
                raise ValueError("approval has expired")
            state = "approved" if approved else "rejected"
            step_state = "ready" if approved else "cancelled"
            db.execute(
                """UPDATE harness_approvals SET state=?,decision_json=?,decided_by=?,
                decided_at=? WHERE id=? AND state='pending'""",
                (state, _encoded(decision or {}, "decision"), actor, decided_at, value),
            )
            db.execute(
                """UPDATE harness_steps SET state=?,available_at=?,completed_at=?,
                updated_at=?,version=version+1 WHERE id=? AND state='waiting_approval'""",
                (
                    step_state,
                    decided_at,
                    None if approved else decided_at,
                    decided_at,
                    str(approval["step_id"]),
                ),
            )
            workflow_state = "running" if approved else "cancelled"
            db.execute(
                """UPDATE harness_workflows SET state=?,updated_at=?,completed_at=?,
                version=version+1 WHERE id=?""",
                (
                    workflow_state,
                    decided_at,
                    None if approved else decided_at,
                    str(approval["workflow_id"]),
                ),
            )
            _append_event(
                db,
                workflow_id=str(approval["workflow_id"]),
                step_id=str(approval["step_id"]),
                event_kind=f"approval.{state}",
                actor=actor,
                payload={"approval_id": value},
                created_at=decided_at,
            )
            updated = db.execute(
                "SELECT * FROM harness_approvals WHERE id=?", (value,)
            ).fetchone()
        return _approval_record(updated)

    def list_pending_approvals(
        self, *, workflow_id: str = "", owner_user_id: str = ""
    ) -> list[dict[str, Any]]:
        workflow_value = _bounded(workflow_id, "workflow_id", 200)
        user_value = _bounded(owner_user_id, "owner_user_id", 160)
        if not workflow_value and not user_value:
            raise ValueError("workflow_id or owner_user_id is required")
        clauses = ["a.state='pending'"]
        params: list[Any] = []
        if workflow_value:
            clauses.append("a.workflow_id=?")
            params.append(workflow_value)
        if user_value:
            clauses.append("w.owner_user_id=?")
            params.append(user_value)
        with self._connection() as db:
            rows = db.execute(
                """SELECT a.* FROM harness_approvals a
                JOIN harness_workflows w ON w.id=a.workflow_id WHERE """
                + " AND ".join(clauses)
                + " ORDER BY a.requested_at,a.id",
                params,
            ).fetchall()
        return [_approval_record(row) for row in rows]

    def retry_step(
        self,
        *,
        step_id: str,
        actor: str,
        allow_additional_attempt: bool = False,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Explicitly requeue a failed/retry-wait Step after human review."""

        value = _required(step_id, "step_id", 200)
        actor_value = _required(actor, "actor", 160)
        retried_at = float(now if now is not None else time.time())
        with self._transaction() as db:
            row = db.execute("SELECT * FROM harness_steps WHERE id=?", (value,)).fetchone()
            if row is None:
                raise KeyError("step not found")
            if str(row["state"]) not in {"failed", "retry_wait"}:
                raise ValueError("only failed or retry-wait Steps can be retried")
            max_attempts = int(row["max_attempts"])
            if int(row["attempt_count"]) >= max_attempts:
                if not allow_additional_attempt:
                    raise ValueError("step retry budget is exhausted")
                max_attempts = int(row["attempt_count"]) + 1
            db.execute(
                """UPDATE harness_steps SET state='ready',error_json='{}',
                available_at=?,max_attempts=?,completed_at=NULL,updated_at=?,
                version=version+1 WHERE id=?""",
                (retried_at, max_attempts, retried_at, value),
            )
            db.execute(
                """UPDATE harness_workflows SET state='retrying',error_json='{}',
                completed_at=NULL,updated_at=?,version=version+1 WHERE id=?""",
                (retried_at, str(row["workflow_id"])),
            )
            _append_event(
                db,
                workflow_id=str(row["workflow_id"]),
                step_id=value,
                event_kind="step.retry_requested",
                actor=actor_value,
                payload={"additional_attempt": bool(allow_additional_attempt)},
                created_at=retried_at,
            )
        return self.get_workflow(str(row["workflow_id"]))

    def cancel_workflow(
        self,
        *,
        workflow_id: str,
        actor: str,
        reason: str = "",
        now: float | None = None,
    ) -> dict[str, Any]:
        value = _required(workflow_id, "workflow_id", 200)
        actor_value = _required(actor, "actor", 160)
        cancelled_at = float(now if now is not None else time.time())
        reason_value = _bounded(reason, "reason", 2_000)
        with self._transaction() as db:
            workflow = db.execute(
                "SELECT * FROM harness_workflows WHERE id=?", (value,)
            ).fetchone()
            if workflow is None:
                raise KeyError("workflow not found")
            if str(workflow["state"]) in {"completed", "cancelled"}:
                return self.get_workflow(value)
            active_attempts = db.execute(
                """SELECT a.id FROM harness_attempts a
                JOIN harness_steps s ON s.id=a.step_id
                WHERE s.workflow_id=? AND a.ended_at IS NULL""",
                (value,),
            ).fetchall()
            db.execute(
                """UPDATE harness_attempts SET state='cancelled',error_json=?,
                heartbeat_at=?,ended_at=? WHERE id IN (
                  SELECT a.id FROM harness_attempts a JOIN harness_steps s ON s.id=a.step_id
                  WHERE s.workflow_id=? AND a.ended_at IS NULL
                )""",
                (_encoded({"reason": reason_value}, "cancel reason"), cancelled_at, cancelled_at, value),
            )
            db.execute(
                """UPDATE harness_steps SET state='cancelled',error_json=?,
                lease_owner='',lease_token_hash='',lease_expires_at=NULL,
                heartbeat_at=?,completed_at=?,updated_at=?,version=version+1
                WHERE workflow_id=? AND state NOT IN ('succeeded','failed','cancelled')""",
                (
                    _encoded({"reason": reason_value}, "cancel reason"),
                    cancelled_at,
                    cancelled_at,
                    cancelled_at,
                    value,
                ),
            )
            db.execute(
                """UPDATE harness_approvals SET state='superseded',decision_json=?,
                decided_by=?,decided_at=? WHERE workflow_id=? AND state='pending'""",
                (
                    _encoded({"reason": reason_value}, "cancel decision"),
                    actor_value,
                    cancelled_at,
                    value,
                ),
            )
            db.execute(
                """UPDATE harness_workflows SET state='cancelled',error_json=?,
                completed_at=?,updated_at=?,version=version+1 WHERE id=?""",
                (
                    _encoded({"reason": reason_value}, "cancel reason"),
                    cancelled_at,
                    cancelled_at,
                    value,
                ),
            )
            _append_event(
                db,
                workflow_id=value,
                event_kind="workflow.cancelled",
                actor=actor_value,
                payload={"reason": reason_value, "active_attempts": len(active_attempts)},
                created_at=cancelled_at,
            )
        return self.get_workflow(value)

    def restart_cancelled_workflow(
        self,
        *,
        workflow_id: str,
        actor: str,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Restart unfinished Steps while preserving completed work and audit history."""

        value = _required(workflow_id, "workflow_id", 200)
        actor_value = _required(actor, "actor", 160)
        restarted_at = float(now if now is not None else time.time())
        with self._transaction() as db:
            workflow = db.execute(
                "SELECT * FROM harness_workflows WHERE id=?", (value,)
            ).fetchone()
            if workflow is None:
                raise KeyError("workflow not found")
            if str(workflow["state"]) != "cancelled":
                raise ValueError("only cancelled workflows can be restarted")

            steps = db.execute(
                "SELECT * FROM harness_steps WHERE workflow_id=? ORDER BY sequence,id",
                (value,),
            ).fetchall()
            succeeded_ids = {
                str(step["id"])
                for step in steps
                if str(step["state"]) == "succeeded"
            }
            dependencies = db.execute(
                """SELECT step_id,depends_on_step_id
                FROM harness_step_dependencies WHERE workflow_id=?""",
                (value,),
            ).fetchall()
            parents: dict[str, set[str]] = {}
            for dependency in dependencies:
                parents.setdefault(str(dependency["step_id"]), set()).add(
                    str(dependency["depends_on_step_id"])
                )

            restarted_steps: list[str] = []
            for step in steps:
                step_id = str(step["id"])
                if step_id in succeeded_ids:
                    continue
                state = "ready" if parents.get(step_id, set()) <= succeeded_ids else "blocked"
                max_attempts = max(
                    int(step["max_attempts"]), int(step["attempt_count"]) + 1
                )
                db.execute(
                    """UPDATE harness_steps SET state=?,output_json='{}',error_json='{}',
                    max_attempts=?,available_at=?,lease_owner='',lease_token_hash='',
                    lease_expires_at=NULL,heartbeat_at=NULL,completed_at=NULL,updated_at=?,
                    version=version+1 WHERE id=?""",
                    (state, max_attempts, restarted_at, restarted_at, step_id),
                )
                restarted_steps.append(str(step["step_key"]))

            db.execute(
                """UPDATE harness_workflows SET state='retrying',error_json='{}',
                completed_at=NULL,updated_at=?,version=version+1 WHERE id=?""",
                (restarted_at, value),
            )
            _append_event(
                db,
                workflow_id=value,
                event_kind="workflow.restart_requested",
                actor=actor_value,
                payload={"restarted_steps": restarted_steps},
                created_at=restarted_at,
            )
        return self.get_workflow(value)

    def record_receipt(
        self,
        *,
        workflow_id: str,
        receipt_kind: str,
        input: dict[str, Any],
        status: str,
        output: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
        idempotency_key: str = "",
        step_id: str = "",
        attempt_id: str = "",
        started_at: float | None = None,
        completed_at: float | None = None,
    ) -> dict[str, Any]:
        workflow_value = _required(workflow_id, "workflow_id", 200)
        kind_value = _required(receipt_kind, "receipt_kind", 160)
        status_value = _required(status, "receipt status", 80)
        key_value = _bounded(idempotency_key, "idempotency_key", 300)
        input_json = _encoded(input, "receipt input")
        input_hash = _content_hash(input_json)
        start_value = float(started_at if started_at is not None else time.time())
        with self._transaction() as db:
            workflow = db.execute(
                "SELECT id FROM harness_workflows WHERE id=?", (workflow_value,)
            ).fetchone()
            if workflow is None:
                raise KeyError("workflow not found")
            if key_value:
                existing = db.execute(
                    """SELECT * FROM harness_receipts
                    WHERE receipt_kind=? AND idempotency_key=?""",
                    (kind_value, key_value),
                ).fetchone()
                if existing is not None:
                    if str(existing["input_hash"]) != input_hash:
                        raise ValueError("idempotency key was already used with different input")
                    return _receipt_record(existing)
            receipt_id = f"receipt_{uuid.uuid4().hex}"
            db.execute(
                """INSERT INTO harness_receipts
                (id,workflow_id,step_id,attempt_id,receipt_kind,idempotency_key,
                 input_hash,status,output_json,error_json,started_at,completed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    receipt_id,
                    workflow_value,
                    _bounded(step_id, "step_id", 200) or None,
                    _bounded(attempt_id, "attempt_id", 200) or None,
                    kind_value,
                    key_value,
                    input_hash,
                    status_value,
                    _encoded(output or {}, "receipt output"),
                    _encoded(error or {}, "receipt error"),
                    start_value,
                    completed_at,
                ),
            )
            _append_event(
                db,
                workflow_id=workflow_value,
                step_id=step_id,
                attempt_id=attempt_id,
                event_kind="receipt.recorded",
                actor="harness",
                payload={"receipt_id": receipt_id, "status": status_value},
                created_at=float(completed_at if completed_at is not None else start_value),
            )
            receipt = db.execute(
                "SELECT * FROM harness_receipts WHERE id=?", (receipt_id,)
            ).fetchone()
        return _receipt_record(receipt)

    def reclaim_expired(
        self,
        *,
        workflow_id: str = "",
        now: float | None = None,
    ) -> int:
        value = _bounded(workflow_id, "workflow_id", 200)
        reclaimed_at = float(now if now is not None else time.time())
        with self._transaction() as db:
            self._promote_due_retries_locked(db, now=reclaimed_at)
            return self._reclaim_locked(db, now=reclaimed_at, workflow_id=value)

    def recover_source(
        self,
        *,
        namespace: str,
        source_kind: str,
        source_ref: str,
        actor: str,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Force-reclaim active Attempts after their owning process restarted."""

        workflow = self.find_by_source(
            namespace=namespace, source_kind=source_kind, source_ref=source_ref
        )
        if workflow is None:
            raise KeyError("workflow not found")
        recovered_at = float(now if now is not None else time.time())
        actor_value = _required(actor, "actor", 160)
        workflow_id = str(workflow["id"])
        with self._transaction() as db:
            rows = db.execute(
                """SELECT * FROM harness_steps WHERE workflow_id=?
                AND state IN ('leased','running')""",
                (workflow_id,),
            ).fetchall()
            for row in rows:
                self._reclaim_step_locked(
                    db, row=row, now=recovered_at, actor=actor_value, forced=True
                )
        return self.get_workflow(workflow_id, include_events=True)

    def list_events(self, workflow_id: str, *, after_id: int = 0) -> list[dict[str, Any]]:
        value = _required(workflow_id, "workflow_id", 200)
        with self._connection() as db:
            rows = db.execute(
                """SELECT * FROM harness_events WHERE workflow_id=? AND id>?
                ORDER BY id""",
                (value, max(0, int(after_id))),
            ).fetchall()
        return [_event_record(row) for row in rows]

    def _authorized_active_locked(
        self, db: sqlite3.Connection, step_id: str, lease_token: str
    ) -> tuple[sqlite3.Row, sqlite3.Row]:
        value = _required(step_id, "step_id", 200)
        token_hash = _token_hash(_required(lease_token, "lease_token", 300))
        row = db.execute("SELECT * FROM harness_steps WHERE id=?", (value,)).fetchone()
        if row is None:
            raise KeyError("step not found")
        if str(row["state"]) not in ACTIVE_STEP_STATES:
            raise ValueError("step has no active lease")
        if not secrets.compare_digest(str(row["lease_token_hash"]), token_hash):
            raise PermissionError("lease token does not own this step")
        attempt = db.execute(
            """SELECT * FROM harness_attempts WHERE step_id=?
            AND lease_token_hash=? ORDER BY attempt_number DESC LIMIT 1""",
            (value, token_hash),
        ).fetchone()
        if attempt is None:
            raise RuntimeError("active step has no matching attempt")
        return row, attempt

    def _authorized_or_completed_locked(
        self,
        db: sqlite3.Connection,
        step_id: str,
        lease_token: str,
        output_json: str,
    ) -> tuple[sqlite3.Row, sqlite3.Row]:
        value = _required(step_id, "step_id", 200)
        token_hash = _token_hash(_required(lease_token, "lease_token", 300))
        row = db.execute("SELECT * FROM harness_steps WHERE id=?", (value,)).fetchone()
        if row is None:
            raise KeyError("step not found")
        if str(row["state"]) in ACTIVE_STEP_STATES:
            return self._authorized_active_locked(db, value, lease_token)
        attempt = db.execute(
            """SELECT * FROM harness_attempts WHERE step_id=? AND lease_token_hash=?
            ORDER BY attempt_number DESC LIMIT 1""",
            (value, token_hash),
        ).fetchone()
        if (
            str(row["state"]) == "succeeded"
            and attempt is not None
            and str(row["output_json"]) == output_json
        ):
            return row, attempt
        raise ValueError("step has no active lease")

    def _promote_due_retries_locked(self, db: sqlite3.Connection, *, now: float) -> None:
        rows = db.execute(
            "SELECT id,workflow_id FROM harness_steps WHERE state='retry_wait' AND available_at<=?",
            (now,),
        ).fetchall()
        for row in rows:
            db.execute(
                """UPDATE harness_steps SET state='ready',updated_at=?,version=version+1
                WHERE id=? AND state='retry_wait'""",
                (now, str(row["id"])),
            )
            _append_event(
                db,
                workflow_id=str(row["workflow_id"]),
                step_id=str(row["id"]),
                event_kind="step.retry_ready",
                actor="harness",
                payload={},
                created_at=now,
            )

    def _reclaim_locked(
        self, db: sqlite3.Connection, *, now: float, workflow_id: str = ""
    ) -> int:
        where_workflow = "AND workflow_id=?" if workflow_id else ""
        params: list[Any] = [now]
        if workflow_id:
            params.append(workflow_id)
        rows = db.execute(
            f"""SELECT * FROM harness_steps
            WHERE state IN ('leased','running') AND lease_expires_at<=? {where_workflow}""",
            params,
        ).fetchall()
        for row in rows:
            self._reclaim_step_locked(db, row=row, now=now, actor="harness", forced=False)
        return len(rows)

    def _reclaim_step_locked(
        self,
        db: sqlite3.Connection,
        *,
        row: sqlite3.Row,
        now: float,
        actor: str,
        forced: bool,
    ) -> None:
        can_retry = int(row["attempt_count"]) < int(row["max_attempts"])
        next_state = "ready" if can_retry else "failed"
        error = {
            "code": "executor_restarted" if forced else "lease_expired",
            "retryable": can_retry,
        }
        db.execute(
            """UPDATE harness_steps SET state=?,error_json=?,available_at=?,
            lease_owner='',lease_token_hash='',lease_expires_at=NULL,
            heartbeat_at=?,completed_at=?,updated_at=?,version=version+1 WHERE id=?""",
            (
                next_state,
                _encoded(error, "reclaim error"),
                now,
                now,
                None if can_retry else now,
                now,
                str(row["id"]),
            ),
        )
        attempt = db.execute(
            """SELECT id FROM harness_attempts WHERE step_id=? AND ended_at IS NULL
            ORDER BY attempt_number DESC LIMIT 1""",
            (str(row["id"]),),
        ).fetchone()
        attempt_id = str(attempt["id"]) if attempt is not None else ""
        if attempt_id:
            db.execute(
                """UPDATE harness_attempts SET state='reclaimed',error_json=?,
                heartbeat_at=?,ended_at=? WHERE id=?""",
                (_encoded(error, "reclaim error"), now, now, attempt_id),
            )
        workflow_state = "retrying" if can_retry else "failed"
        db.execute(
            """UPDATE harness_workflows SET state=?,error_json=?,updated_at=?,
            completed_at=?,version=version+1 WHERE id=?""",
            (
                workflow_state,
                _encoded(error, "reclaim error"),
                now,
                None if can_retry else now,
                str(row["workflow_id"]),
            ),
        )
        _append_event(
            db,
            workflow_id=str(row["workflow_id"]),
            step_id=str(row["id"]),
            attempt_id=attempt_id,
            event_kind="step.reclaimed" if can_retry else "step.reclaim_failed",
            actor=actor,
            payload=error,
            created_at=now,
        )

    def _promote_dependents_locked(
        self, db: sqlite3.Connection, *, workflow_id: str, actor: str, now: float
    ) -> None:
        rows = db.execute(
            """SELECT child.id FROM harness_steps child
            WHERE child.workflow_id=? AND child.state='blocked'
              AND NOT EXISTS (
                SELECT 1 FROM harness_step_dependencies d
                JOIN harness_steps parent ON parent.id=d.depends_on_step_id
                WHERE d.step_id=child.id AND parent.state<>'succeeded'
              )""",
            (workflow_id,),
        ).fetchall()
        for row in rows:
            db.execute(
                """UPDATE harness_steps SET state='ready',available_at=?,updated_at=?,
                version=version+1 WHERE id=? AND state='blocked'""",
                (now, now, str(row["id"])),
            )
            _append_event(
                db,
                workflow_id=workflow_id,
                step_id=str(row["id"]),
                event_kind="step.ready",
                actor=actor,
                payload={},
                created_at=now,
            )

    def _insert_artifact_locked(
        self,
        db: sqlite3.Connection,
        *,
        workflow_id: str,
        step_id: str,
        attempt_id: str,
        artifact: dict[str, Any],
        created_at: float,
    ) -> None:
        if not isinstance(artifact, dict):
            raise ValueError("artifact must be an object")
        object_type = _bounded(artifact.get("object_type"), "object_type", 160)
        object_id = _bounded(artifact.get("object_id"), "object_id", 240)
        uri = _bounded(artifact.get("uri"), "artifact uri", 2_000)
        content_hash = _bounded(artifact.get("content_hash"), "content_hash", 160)
        if not content_hash:
            content_hash = _content_hash(f"{object_type}:{object_id}:{uri}")
        db.execute(
            """INSERT INTO harness_artifacts
            (id,workflow_id,step_id,attempt_id,kind,object_type,object_id,uri,
             content_hash,media_type,metadata_json,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f"artifact_{uuid.uuid4().hex}",
                workflow_id,
                step_id,
                attempt_id,
                _required(artifact.get("kind"), "artifact kind", 160),
                object_type,
                object_id,
                uri,
                content_hash,
                _bounded(artifact.get("media_type") or "application/json", "media_type", 160),
                _encoded(artifact.get("metadata") or {}, "artifact metadata"),
                created_at,
            ),
        )


def _validate_steps(steps: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(steps, Sequence) or isinstance(steps, (str, bytes)) or not steps:
        raise ValueError("steps must be a non-empty list")
    if len(steps) > 200:
        raise ValueError("workflow has too many steps")
    definitions: list[dict[str, Any]] = []
    keys: set[str] = set()
    for raw in steps:
        if not isinstance(raw, dict):
            raise ValueError("each step must be an object")
        key = _required(raw.get("key"), "step key", 120)
        if key in keys:
            raise ValueError(f"duplicate step key: {key}")
        keys.add(key)
        toolsets = raw.get("toolsets") or []
        depends_on = raw.get("depends_on") or []
        if not isinstance(toolsets, list) or not all(isinstance(item, str) for item in toolsets):
            raise ValueError(f"step {key} toolsets must be a string list")
        if not isinstance(depends_on, list) or not all(isinstance(item, str) for item in depends_on):
            raise ValueError(f"step {key} depends_on must be a string list")
        definitions.append(
            {
                "key": key,
                "kind": _required(raw.get("kind") or key, "step kind", 160),
                "worker_role": _bounded(raw.get("worker_role"), "worker_role", 160),
                "toolsets": list(dict.fromkeys(toolsets)),
                "resource_scope": _bounded(raw.get("resource_scope"), "resource_scope", 300),
                "input": raw.get("input") if isinstance(raw.get("input"), dict) else {},
                "retry_policy": raw.get("retry_policy") if isinstance(raw.get("retry_policy"), dict) else {},
                "max_attempts": max(1, min(int(raw.get("max_attempts") or 3), 20)),
                "depends_on": list(dict.fromkeys(depends_on)),
            }
        )
    for definition in definitions:
        unknown = set(definition["depends_on"]) - keys
        if unknown:
            raise ValueError(
                f"step {definition['key']} depends on unknown steps: {sorted(unknown)}"
            )
        if definition["key"] in definition["depends_on"]:
            raise ValueError(f"step {definition['key']} cannot depend on itself")
    graph = {item["key"]: item["depends_on"] for item in definitions}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(key: str) -> None:
        if key in visiting:
            raise ValueError("workflow step dependencies contain a cycle")
        if key in visited:
            return
        visiting.add(key)
        for parent in graph[key]:
            visit(parent)
        visiting.remove(key)
        visited.add(key)

    for key in graph:
        visit(key)
    return definitions


def _append_event(
    db: sqlite3.Connection,
    *,
    workflow_id: str,
    event_kind: str,
    actor: str,
    payload: dict[str, Any],
    created_at: float,
    step_id: str = "",
    attempt_id: str = "",
) -> None:
    db.execute(
        """INSERT INTO harness_events
        (workflow_id,step_id,attempt_id,event_kind,actor,payload_json,created_at)
        VALUES (?,?,?,?,?,?,?)""",
        (
            workflow_id,
            step_id or None,
            attempt_id or None,
            event_kind,
            actor,
            _encoded(payload, "event payload"),
            created_at,
        ),
    )


def _workflow_record(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "namespace": str(row["namespace"]),
        "owner_user_id": str(row["owner_user_id"]),
        "owner_entity_id": str(row["owner_entity_id"] or ""),
        "source_kind": str(row["source_kind"] or ""),
        "source_ref": str(row["source_ref"] or ""),
        "kind": str(row["kind"]),
        "title": str(row["title"]),
        "state": str(row["state"]),
        "priority": int(row["priority"]),
        "input": _decoded(row["input_json"], {}),
        "policy": _decoded(row["policy_json"], {}),
        "budget": _decoded(row["budget_json"], {}),
        "result": _decoded(row["result_json"], {}),
        "error": _decoded(row["error_json"], {}),
        "version": int(row["version"]),
        "created_at": float(row["created_at"]),
        "updated_at": float(row["updated_at"]),
        "completed_at": row["completed_at"],
    }


def _step_record(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "workflow_id": str(row["workflow_id"]),
        "key": str(row["step_key"]),
        "kind": str(row["kind"]),
        "state": str(row["state"]),
        "sequence": int(row["sequence"]),
        "worker_role": str(row["worker_role"] or ""),
        "toolsets": _decoded(row["toolset_json"], []),
        "resource_scope": str(row["resource_scope"] or ""),
        "input": _decoded(row["input_json"], {}),
        "output": _decoded(row["output_json"], {}),
        "error": _decoded(row["error_json"], {}),
        "retry_policy": _decoded(row["retry_policy_json"], {}),
        "attempt_count": int(row["attempt_count"]),
        "max_attempts": int(row["max_attempts"]),
        "available_at": float(row["available_at"]),
        "lease_owner": str(row["lease_owner"] or ""),
        "lease_expires_at": row["lease_expires_at"],
        "heartbeat_at": row["heartbeat_at"],
        "version": int(row["version"]),
        "created_at": float(row["created_at"]),
        "updated_at": float(row["updated_at"]),
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
    }


def _approval_record(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "workflow_id": str(row["workflow_id"]),
        "step_id": str(row["step_id"]),
        "approval_key": str(row["approval_key"]),
        "state": str(row["state"]),
        "request": _decoded(row["request_json"], {}),
        "decision": _decoded(row["decision_json"], {}),
        "requested_by": str(row["requested_by"]),
        "decided_by": str(row["decided_by"] or ""),
        "contract_version": str(row["contract_version"] or ""),
        "requested_at": float(row["requested_at"]),
        "expires_at": row["expires_at"],
        "decided_at": row["decided_at"],
    }


def _receipt_record(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "workflow_id": str(row["workflow_id"]),
        "step_id": str(row["step_id"] or ""),
        "attempt_id": str(row["attempt_id"] or ""),
        "kind": str(row["receipt_kind"]),
        "idempotency_key": str(row["idempotency_key"] or ""),
        "input_hash": str(row["input_hash"]),
        "status": str(row["status"]),
        "output": _decoded(row["output_json"], {}),
        "error": _decoded(row["error_json"], {}),
        "started_at": float(row["started_at"]),
        "completed_at": row["completed_at"],
    }


def _event_record(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "workflow_id": str(row["workflow_id"]),
        "step_id": str(row["step_id"] or ""),
        "attempt_id": str(row["attempt_id"] or ""),
        "kind": str(row["event_kind"]),
        "actor": str(row["actor"]),
        "payload": _decoded(row["payload_json"], {}),
        "created_at": float(row["created_at"]),
    }


def _required(value: Any, field: str, limit: int) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field} is required")
    if len(normalized) > limit:
        raise ValueError(f"{field} is too long")
    return normalized


def _bounded(value: Any, field: str, limit: int) -> str:
    normalized = str(value or "").strip()
    if len(normalized) > limit:
        raise ValueError(f"{field} is too long")
    return normalized


def _encoded(value: Any, field: str) -> str:
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be JSON serializable") from exc
    if len(encoded.encode("utf-8")) > 1_000_000:
        raise ValueError(f"{field} is too large")
    return encoded


def _decoded(value: Any, fallback: Any) -> Any:
    try:
        result = json.loads(str(value or ""))
    except (TypeError, ValueError):
        return fallback
    return result if isinstance(result, type(fallback)) else fallback


def _content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _token_hash(value: str) -> str:
    return _content_hash(value)
