"""SQLite event store for durable tasks, approvals, effects, and memory candidates."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .models import ApprovalStatus, MemoryKind, TaskStatus


TERMINAL_TASK_STATUSES = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
ALLOWED_TRANSITIONS = {
    TaskStatus.QUEUED: {TaskStatus.PLANNING, TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.PLANNING: {TaskStatus.RUNNING, TaskStatus.WAITING_USER, TaskStatus.PAUSED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {
        TaskStatus.WAITING_USER, TaskStatus.RETRYING, TaskStatus.PAUSED,
        TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED,
    },
    TaskStatus.WAITING_USER: {TaskStatus.RUNNING, TaskStatus.PAUSED, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.RETRYING: {TaskStatus.RUNNING, TaskStatus.PAUSED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.PAUSED: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: {TaskStatus.RETRYING, TaskStatus.CANCELLED},
    TaskStatus.CANCELLED: set(),
}

SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_ -]?key|access[_ -]?token|refresh[_ -]?token|password|cookie)\b\s*[:=]"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b[A-Za-z0-9_-]{32,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b"),
)
SECRET_KEYS = {"api_key", "access_token", "refresh_token", "password", "cookie", "cookies", "token"}

REASONING_MARKERS = (
    re.compile(r"(?:我认为|我推测|我猜测|可能|也许|大概|似乎|好像|应该|估计|或许)"),
    re.compile(r"(?:I think|I guess|maybe|perhaps|probably|likely|possibly|seems like)"),
)
MIN_CONFIDENCE_WITHOUT_EVIDENCE = 0.5


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _json(value: Any) -> str:
    return json.dumps(_redact(value), ensure_ascii=False, separators=(",", ":"), default=str)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if str(key).lower() in SECRET_KEYS else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return [_redact(item) for item in value]
    if isinstance(value, str) and any(pattern.search(value) for pattern in SECRET_PATTERNS):
        return "[REDACTED]"
    return value


MEMORY_EVENT_CREATED = "memory.candidate.created"
MEMORY_EVENT_ADOPTED = "memory.candidate.adopted"
MEMORY_EVENT_REJECTED = "memory.candidate.rejected"
MEMORY_EVENT_MODIFIED = "memory.candidate.modified"
MEMORY_EVENT_SUPERSEDED = "memory.candidate.superseded"
MEMORY_EVENT_FORGOTTEN = "memory.candidate.forgotten"
MEMORY_EVENT_USER_STATED = "memory.user_stated"
MEMORY_EVENT_RESULT_OBSERVED = "memory.result_observed"
MEMORY_EVENT_RECOVERY_LEARNED = "memory.recovery_learned"

MEMORY_PROVENANCE_TYPES = frozenset({
    "agent_inference", "user_stated", "user_confirmed",
    "publish_result", "failure_recovery",
})


class AgentCoreStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_tasks (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    account_id TEXT,
                    objective TEXT NOT NULL,
                    status TEXT NOT NULL,
                    plan_json TEXT NOT NULL DEFAULT '[]',
                    plan_version INTEGER NOT NULL DEFAULT 1,
                    current_step TEXT,
                    checkpoint_json TEXT NOT NULL DEFAULT '{}',
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS agent_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    workspace TEXT,
                    active_task_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_sessions_scope
                    ON agent_sessions(user_id, COALESCE(workspace, ''));

                CREATE TABLE IF NOT EXISTS task_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    task_id TEXT NOT NULL REFERENCES agent_tasks(id),
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id, sequence);

                CREATE TABLE IF NOT EXISTS approval_requests (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES agent_tasks(id),
                    capability TEXT NOT NULL,
                    arguments_json TEXT NOT NULL,
                    risk_summary TEXT NOT NULL,
                    status TEXT NOT NULL,
                    decision_reason TEXT,
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                );

                CREATE TABLE IF NOT EXISTS effect_intents (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES agent_tasks(id),
                    approval_id TEXT REFERENCES approval_requests(id),
                    capability TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    preview_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    receipt_json TEXT,
                    created_at TEXT NOT NULL,
                    executed_at TEXT
                );

                CREATE TABLE IF NOT EXISTS user_authorizations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'permanent',
                    constraints_json TEXT NOT NULL DEFAULT '{}',
                    granted_at TEXT NOT NULL,
                    revoked_at TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_user_auths_active
                    ON user_authorizations(user_id, capability) WHERE revoked_at IS NULL;

                CREATE TABLE IF NOT EXISTS content_assets (
                    id TEXT PRIMARY KEY,
                    account_id TEXT,
                    platform TEXT,
                    title TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'script',
                    status TEXT NOT NULL DEFAULT 'draft',
                    parent_id TEXT REFERENCES content_assets(id),
                    topic TEXT,
                    hook TEXT,
                    version INTEGER NOT NULL DEFAULT 1,
                    content_json TEXT NOT NULL DEFAULT '{}',
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_content_assets_status ON content_assets(status);
                CREATE INDEX IF NOT EXISTS idx_content_assets_account ON content_assets(account_id);

                CREATE TABLE IF NOT EXISTS memory_candidates (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    account_id TEXT,
                    platform TEXT,
                    workspace TEXT,
                    content TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    rejection_reason TEXT,
                    observed_at TEXT NOT NULL,
                    valid_from TEXT,
                    valid_to TEXT,
                    supersedes_id TEXT REFERENCES memory_candidates(id),
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS publishing_tasks (
                    id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL REFERENCES content_assets(id),
                    platform TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    published_version INTEGER,
                    effect_id TEXT,
                    receipt_json TEXT,
                    published_at TEXT,
                    next_metrics_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_publishing_tasks_status ON publishing_tasks(status);
                CREATE INDEX IF NOT EXISTS idx_publishing_tasks_asset ON publishing_tasks(asset_id);
                """
            )
            columns = {row["name"] for row in db.execute("PRAGMA table_info(user_authorizations)")}
            if "constraints_json" not in columns:
                db.execute(
                    "ALTER TABLE user_authorizations ADD COLUMN constraints_json TEXT NOT NULL DEFAULT '{}'"
                )
                # Legacy grants had no account/platform boundary and some were
                # created by the Agent itself. Require the user to grant a new,
                # constrained permission after migration.
                db.execute(
                    "UPDATE user_authorizations SET revoked_at=? WHERE revoked_at IS NULL",
                    (_now(),),
                )

            mem_columns = {row["name"] for row in db.execute("PRAGMA table_info(memory_candidates)")}
            if "workspace" not in mem_columns:
                db.execute("ALTER TABLE memory_candidates ADD COLUMN workspace TEXT")

            ca_columns = {row["name"] for row in db.execute("PRAGMA table_info(content_assets)")}
            for col in ("parent_id", "topic", "hook"):
                if col not in ca_columns:
                    db.execute(f"ALTER TABLE content_assets ADD COLUMN {col} TEXT")

    def create_or_get_session(self, *, user_id: str, workspace: str | None = None) -> dict[str, Any]:
        normalized_workspace = workspace.strip() if isinstance(workspace, str) and workspace.strip() else None
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM agent_sessions WHERE user_id=? AND COALESCE(workspace, '')=COALESCE(?, '')",
                (user_id, normalized_workspace),
            ).fetchone()
            if row is None:
                timestamp = _now()
                session_id = _id("sess")
                db.execute(
                    """INSERT INTO agent_sessions
                    (id, user_id, workspace, active_task_id, created_at, updated_at)
                    VALUES (?, ?, ?, NULL, ?, ?)""",
                    (session_id, user_id, normalized_workspace, timestamp, timestamp),
                )
                row = db.execute("SELECT * FROM agent_sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM agent_sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row) if row is not None else None

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM agent_sessions ORDER BY updated_at DESC").fetchall()
        return [dict(row) for row in rows]

    def set_session_active_task(self, session_id: str, task_id: str | None) -> None:
        with self._connect() as db:
            updated = db.execute(
                "UPDATE agent_sessions SET active_task_id=?, updated_at=? WHERE id=?",
                (task_id, _now(), session_id),
            )
            if updated.rowcount == 0:
                raise KeyError(f"session not found: {session_id}")

    def create_task(
        self, *, session_id: str, user_id: str, objective: str,
        account_id: str | None = None, plan: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        task_id = _id("task")
        timestamp = _now()
        with self._connect() as db:
            db.execute(
                """INSERT INTO agent_tasks
                (id, session_id, user_id, account_id, objective, status, plan_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task_id, session_id, user_id, account_id, objective, TaskStatus.QUEUED.value,
                 _json(plan or []), timestamp, timestamp),
            )
            self._append_event(db, task_id, "task.created", {"objective": objective})
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(f"task not found: {task_id}")
        result = dict(row)
        result["plan"] = json.loads(result.pop("plan_json"))
        result["checkpoint"] = json.loads(result.pop("checkpoint_json"))
        return result

    def list_events(self, task_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM task_events WHERE task_id=? ORDER BY sequence", (task_id,)
            ).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

    def list_events_after(self, task_id: str, sequence: int = 0) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM task_events WHERE task_id=? AND sequence>? ORDER BY sequence",
                (task_id, sequence),
            ).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

    def append_event(self, task_id: str, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._connect() as db:
            self._append_event(db, task_id, event_type, payload or {})
            row = db.execute(
                "SELECT * FROM task_events WHERE task_id=? ORDER BY sequence DESC LIMIT 1",
                (task_id,),
            ).fetchone()
        result = dict(row)
        result["payload"] = json.loads(result["payload_json"])
        return result

    def list_tasks(self, statuses: set[TaskStatus] | None = None) -> list[dict[str, Any]]:
        query = "SELECT id FROM agent_tasks"
        params: list[Any] = []
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            query += f" WHERE status IN ({placeholders})"
            params.extend(status.value for status in statuses)
        query += " ORDER BY updated_at"
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [self.get_task(row["id"]) for row in rows]

    def update_task_progress(
        self,
        task_id: str,
        *,
        current_step: str | None = None,
        checkpoint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fields = ["updated_at=?"]
        values: list[Any] = [_now()]
        if current_step is not None:
            fields.append("current_step=?")
            values.append(current_step)
        if checkpoint is not None:
            fields.append("checkpoint_json=?")
            values.append(_json(checkpoint))
        values.append(task_id)
        with self._connect() as db:
            updated = db.execute(f"UPDATE agent_tasks SET {', '.join(fields)} WHERE id=?", values)
            if updated.rowcount == 0:
                raise KeyError(f"task not found: {task_id}")
        return self.get_task(task_id)

    def update_plan(self, task_id: str, plan: list[dict[str, Any]]) -> dict[str, Any]:
        with self._connect() as db:
            updated = db.execute(
                "UPDATE agent_tasks SET plan_json=?, plan_version=plan_version+1, updated_at=? WHERE id=?",
                (_json(plan), _now(), task_id),
            )
            if updated.rowcount == 0:
                raise KeyError(f"task not found: {task_id}")
        return self.get_task(task_id)

    def transition_task(
        self, task_id: str, status: TaskStatus, *, checkpoint: dict[str, Any] | None = None,
        current_step: str | None = None, error: str | None = None,
    ) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT status FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise KeyError(f"task not found: {task_id}")
            current = TaskStatus(row["status"])
            if status not in ALLOWED_TRANSITIONS[current]:
                raise ValueError(f"invalid task transition: {current.value} -> {status.value}")
            fields = ["status=?", "updated_at=?"]
            values: list[Any] = [status.value, _now()]
            if checkpoint is not None:
                fields.append("checkpoint_json=?")
                values.append(_json(checkpoint))
            if current_step is not None:
                fields.append("current_step=?")
                values.append(current_step)
            if error is not None:
                fields.append("last_error=?")
                values.append(error)
            values.append(task_id)
            db.execute(f"UPDATE agent_tasks SET {', '.join(fields)} WHERE id=?", values)
            self._append_event(db, task_id, "task.status_changed", {
                "from": current.value, "to": status.value, "current_step": current_step,
            })
        return self.get_task(task_id)

    def cancel_task_and_void_approvals(
        self, task_id: str, *, reason: str = "task cancelled",
    ) -> dict[str, Any]:
        """Atomically cancel a task and reject all of its pending approvals."""
        timestamp = _now()
        with self._connect() as db:
            task = db.execute(
                "SELECT status FROM agent_tasks WHERE id=?", (task_id,),
            ).fetchone()
            if task is None:
                raise KeyError(f"task not found: {task_id}")

            current = TaskStatus(task["status"])
            if current is TaskStatus.CANCELLED:
                return self.get_task(task_id)
            if TaskStatus.CANCELLED not in ALLOWED_TRANSITIONS[current]:
                raise ValueError(
                    f"invalid task transition: {current.value} -> {TaskStatus.CANCELLED.value}"
                )

            approvals = db.execute(
                "SELECT id FROM approval_requests WHERE task_id=? AND status=? ORDER BY created_at",
                (task_id, ApprovalStatus.PENDING.value),
            ).fetchall()
            for approval in approvals:
                db.execute(
                    "UPDATE approval_requests SET status=?, decision_reason=?, decided_at=? WHERE id=?",
                    (ApprovalStatus.REJECTED.value, reason, timestamp, approval["id"]),
                )
                self._append_event(db, task_id, "approval.decided", {
                    "approval_id": approval["id"],
                    "decision": ApprovalStatus.REJECTED.value,
                    "reason": reason,
                })

            db.execute(
                "UPDATE agent_tasks SET status=?, last_error=?, updated_at=? WHERE id=?",
                (TaskStatus.CANCELLED.value, reason, timestamp, task_id),
            )
            self._append_event(db, task_id, "task.status_changed", {
                "from": current.value,
                "to": TaskStatus.CANCELLED.value,
                "current_step": None,
            })
            self._append_event(db, task_id, "task.cancelled", {"reason": reason})
        return self.get_task(task_id)

    def create_approval(
        self, *, task_id: str, capability: str, arguments: dict[str, Any], risk_summary: str,
    ) -> dict[str, Any]:
        approval_id = _id("approval")
        timestamp = _now()
        with self._connect() as db:
            task = db.execute("SELECT status FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
            if task is None:
                raise KeyError(f"task not found: {task_id}")
            current = TaskStatus(task["status"])
            if current not in {TaskStatus.PLANNING, TaskStatus.RUNNING}:
                raise ValueError(f"task cannot request approval from {current.value}")
            db.execute(
                """INSERT INTO approval_requests
                (id, task_id, capability, arguments_json, risk_summary, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (approval_id, task_id, capability, _json(arguments), risk_summary,
                 ApprovalStatus.PENDING.value, timestamp),
            )
            db.execute(
                "UPDATE agent_tasks SET status=?, updated_at=? WHERE id=?",
                (TaskStatus.WAITING_USER.value, timestamp, task_id),
            )
            self._append_event(db, task_id, "approval.requested", {
                "approval_id": approval_id, "capability": capability,
                "arguments": arguments, "risk_summary": risk_summary,
            })
        return self.get_approval(approval_id)

    def get_approval(self, approval_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM approval_requests WHERE id=?", (approval_id,)).fetchone()
        if row is None:
            raise KeyError(f"approval not found: {approval_id}")
        result = dict(row)
        result["arguments"] = json.loads(result.pop("arguments_json"))
        return result

    def expire_stale_approvals(
        self, timeout_seconds: float = 300, *, now: str | None = None,
    ) -> list[dict[str, Any]]:
        """Mark pending approvals older than *timeout_seconds* as expired.

        Each expired approval's task is transitioned to PAUSED so the agent can
        inform the user rather than silently hanging.

        All mutations and event writes happen inside a single transaction.
        *now* is an injectable ISO timestamp for deterministic testing.
        """
        expired: list[dict[str, Any]] = []
        reference_time = datetime.fromisoformat(now) if now else datetime.now(timezone.utc)
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, task_id, capability, arguments_json, risk_summary, created_at "
                "FROM approval_requests WHERE status=? ORDER BY created_at",
                (ApprovalStatus.PENDING.value,),
            ).fetchall()
            for row in rows:
                created = row["created_at"]
                if not created:
                    continue
                try:
                    age = (reference_time - datetime.fromisoformat(created)).total_seconds()
                except (ValueError, TypeError):
                    continue
                if age < timeout_seconds:
                    continue
                timestamp = _now()
                db.execute(
                    "UPDATE approval_requests SET status=?, decision_reason=?, decided_at=? WHERE id=?",
                    (ApprovalStatus.EXPIRED.value, "approval timed out", timestamp, row["id"]),
                )
                db.execute(
                    "UPDATE agent_tasks SET status=?, updated_at=? WHERE id=? AND status=?",
                    (TaskStatus.PAUSED.value, timestamp, row["task_id"], TaskStatus.WAITING_USER.value),
                )
                self._append_event(db, row["task_id"], "approval.decided", {
                    "approval_id": row["id"],
                    "decision": "expired",
                    "reason": "approval timed out",
                })
                self._append_event(db, row["task_id"], "task.paused", {
                    "reason": "approval_expired",
                    "approval_id": row["id"],
                })
                expired.append({
                    "id": row["id"],
                    "task_id": row["task_id"],
                    "capability": row["capability"],
                    "arguments": json.loads(row["arguments_json"]),
                    "risk_summary": row["risk_summary"],
                    "status": "expired",
                    "decision_reason": "approval timed out",
                    "created_at": row["created_at"],
                    "decided_at": timestamp,
                })
        return expired

    def decide_approval(
        self, approval_id: str, approved: bool, reason: str | None = None,
        *, transition_task: bool = True,
    ) -> dict[str, Any]:
        target = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        with self._connect() as db:
            row = db.execute("SELECT * FROM approval_requests WHERE id=?", (approval_id,)).fetchone()
            if row is None:
                raise KeyError(f"approval not found: {approval_id}")
            if row["status"] != ApprovalStatus.PENDING.value:
                status_label = row["status"]
                raise ValueError(f"approval already {status_label}")
            timestamp = _now()
            db.execute(
                "UPDATE approval_requests SET status=?, decision_reason=?, decided_at=? WHERE id=?",
                (target.value, reason, timestamp, approval_id),
            )
            if transition_task:
                next_status = TaskStatus.RUNNING if approved else TaskStatus.PAUSED
                db.execute(
                    "UPDATE agent_tasks SET status=?, updated_at=? WHERE id=?",
                    (next_status.value, timestamp, row["task_id"]),
                )
            self._append_event(db, row["task_id"], "approval.decided", {
                "approval_id": approval_id, "decision": target.value, "reason": reason,
            })
        return self.get_approval(approval_id)

    def create_effect_intent(
        self, *, task_id: str, capability: str, idempotency_key: str,
        preview: dict[str, Any], approval_id: str | None = None,
    ) -> dict[str, Any]:
        effect_id = _id("effect")
        with self._connect() as db:
            existing = db.execute(
                "SELECT * FROM effect_intents WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if existing is not None:
                return self._effect_dict(existing)
            if approval_id:
                approval = db.execute(
                    "SELECT status FROM approval_requests WHERE id=?", (approval_id,)
                ).fetchone()
                if approval is None or approval["status"] != ApprovalStatus.APPROVED.value:
                    raise PermissionError("effect requires an approved approval request")
            db.execute(
                """INSERT INTO effect_intents
                (id, task_id, approval_id, capability, idempotency_key, preview_json, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (effect_id, task_id, approval_id, capability, idempotency_key, _json(preview), _now()),
            )
            self._append_event(db, task_id, "effect.intent_created", {
                "effect_id": effect_id, "capability": capability, "idempotency_key": idempotency_key,
            })
        return self.get_effect(effect_id)

    def get_effect(self, effect_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM effect_intents WHERE id=?", (effect_id,)).fetchone()
        if row is None:
            raise KeyError(f"effect not found: {effect_id}")
        return self._effect_dict(row)

    def record_effect_receipt(self, effect_id: str, receipt: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM effect_intents WHERE id=?", (effect_id,)).fetchone()
            if row is None:
                raise KeyError(f"effect not found: {effect_id}")
            if row["status"] == "executed":
                return self._effect_dict(row)
            timestamp = _now()
            db.execute(
                "UPDATE effect_intents SET status='executed', receipt_json=?, executed_at=? WHERE id=?",
                (_json(receipt), timestamp, effect_id),
            )
            self._append_event(db, row["task_id"], "effect.executed", {
                "effect_id": effect_id,
                "approval_id": row["approval_id"],
                "capability": row["capability"],
                "receipt": receipt,
            })
        return self.get_effect(effect_id)

    def add_memory_candidate(
        self, *, kind: MemoryKind, user_id: str, content: str,
        evidence: list[dict[str, Any]], confidence: float,
        account_id: str | None = None, platform: str | None = None,
        workspace: str | None = None,
        valid_from: str | None = None, valid_to: str | None = None,
        supersedes_id: str | None = None,
        supersede_previous: bool = False,
        task_id: str | None = None,
        provenance: str | None = None,
    ) -> dict[str, Any]:
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        rejected = any(pattern.search(content) for pattern in SECRET_PATTERNS)
        rejection_reason = "可能包含秘密，禁止进入记忆" if rejected else None
        if not rejected and not evidence:
            rejected = True
            rejection_reason = "缺少证据来源，拒绝无依据的记忆写入"
        if not rejected and confidence < MIN_CONFIDENCE_WITHOUT_EVIDENCE and not evidence:
            rejected = True
            rejection_reason = "低置信度且无证据，拒绝进入记忆"

        candidate_id = _id("memory")

        # Evidence-based auto-promotion: confidence + multi-evidence → skip pending
        # Thresholds per kind: user-stated facts need lower bar;
        # behavioral inferences need multiple independent evidence.
        if not rejected and evidence:
            kind_threshold = {
                MemoryKind.USER: 0.55,
                MemoryKind.ACCOUNT: 0.6,
                MemoryKind.EPISODIC: 0.6,
                MemoryKind.SEMANTIC: 0.7,
                MemoryKind.PROCEDURAL: 0.8,
            }.get(kind, 0.7)
            # Multiple independent sources → lower confidence bar by 0.1 per extra source
            evidence_sources = {e.get("source", "") for e in evidence if isinstance(e, dict)}
            multi_bonus = min(0.2, 0.05 * max(0, len(evidence_sources) - 1))
            effective_threshold = max(0.3, kind_threshold - multi_bonus)
            if confidence >= effective_threshold:
                status = "verified"
            else:
                status = "pending"
        elif rejected:
            status = "rejected"
        else:
            status = "pending"

        previous_ids: list[str] = []
        with self._connect() as db:
            # Auto-supersede: mark previous verified/locked memories as superseded
            if supersede_previous and not rejected:
                scope_conditions = ["kind=?", "user_id=?", "status IN ('verified', 'locked')"]
                scope_params: list[Any] = [kind.value, user_id]
                if account_id:
                    scope_conditions.append("account_id=?")
                    scope_params.append(account_id)
                else:
                    scope_conditions.append("account_id IS NULL")
                if workspace:
                    scope_conditions.append("workspace=?")
                    scope_params.append(workspace)
                else:
                    scope_conditions.append("workspace IS NULL")
                previous_rows = db.execute(
                    f"SELECT id FROM memory_candidates WHERE {' AND '.join(scope_conditions)}",
                    scope_params,
                ).fetchall()
                for prev in previous_rows:
                    db.execute(
                        "UPDATE memory_candidates SET status='superseded' WHERE id=?",
                        (prev["id"],),
                    )
                previous_ids = [r["id"] for r in previous_rows]
                supersedes_id = previous_rows[0]["id"] if previous_rows else None

            db.execute(
                """INSERT INTO memory_candidates
                (id, kind, user_id, account_id, platform, workspace, content, evidence_json, confidence,
                 status, rejection_reason, observed_at, valid_from, valid_to, supersedes_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (candidate_id, kind.value, user_id, account_id, platform, workspace, content, _json(evidence),
                 confidence, status, rejection_reason, _now(), valid_from, valid_to, supersedes_id, _now()),
            )
        candidate = self.get_memory_candidate(candidate_id)
        self._emit_memory_event(
            MEMORY_EVENT_CREATED if status != "superseded" else MEMORY_EVENT_SUPERSEDED,
            candidate, task_id=task_id, provenance=provenance or "agent_inference",
            supersedes_id=supersedes_id,
        )
        # Emit superseded events for the old memories
        for prev_id in previous_ids:
            try:
                prev = self.get_memory_candidate(prev_id)
                self._emit_memory_event(
                    MEMORY_EVENT_SUPERSEDED, prev, task_id=task_id,
                    provenance=provenance or "agent_inference",
                )
            except KeyError:
                pass
        return candidate

    def get_memory_candidate(self, candidate_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM memory_candidates WHERE id=?", (candidate_id,)).fetchone()
        if row is None:
            raise KeyError(f"memory candidate not found: {candidate_id}")
        result = dict(row)
        result["evidence"] = json.loads(result.pop("evidence_json"))
        return result

    def list_memories(
        self, *, user_id: str | None = None, kind: str | None = None,
        account_id: str | None = None, platform: str | None = None,
        workspace: str | None = None, status: str | None = "pending",
    ) -> list[dict[str, Any]]:
        query = "SELECT id FROM memory_candidates WHERE 1=1"
        params: list[Any] = []
        if user_id is not None:
            query += " AND user_id=?"
            params.append(user_id)
        if kind is not None:
            query += " AND kind=?"
            params.append(kind)
        if account_id is not None:
            query += " AND account_id=?"
            params.append(account_id)
        if platform is not None:
            query += " AND platform=?"
            params.append(platform)
        if workspace is not None:
            query += " AND workspace=?"
            params.append(workspace)
        if status is not None:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT 100"
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [self.get_memory_candidate(row["id"]) for row in rows]

    def delete_memory(self, candidate_id: str, *, task_id: str | None = None) -> None:
        try:
            current = self.get_memory_candidate(candidate_id)
        except KeyError:
            current = None
        with self._connect() as db:
            deleted = db.execute("DELETE FROM memory_candidates WHERE id=?", (candidate_id,))
            if deleted.rowcount == 0:
                raise KeyError(f"memory candidate not found: {candidate_id}")
        if current:
            self._emit_memory_event(
                MEMORY_EVENT_FORGOTTEN, current, task_id=task_id,
                provenance="user_confirmed",
            )

    # -- Structured Account DNA --

    def upsert_account_dna(
        self, *, user_id: str, account_id: str, field: str, value: str,
        workspace: str | None = None, evidence: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Write/update a single Account DNA field.

        Each field is stored as a memory_candidate with kind='account' and
        structured content.  Supersedes only the previous value for the same
        (user_id, account_id, workspace, field).
        """
        normalized_value = value.strip()[:2000]
        if any(pattern.search(normalized_value) for pattern in SECRET_PATTERNS):
            raise ValueError("account DNA value may contain a secret")

        # Supersede only the same field (not all account memories)
        existing = self.list_memories(
            user_id=user_id, kind=MemoryKind.ACCOUNT.value,
            account_id=account_id, workspace=workspace,
            status="verified",
        ) + self.list_memories(
            user_id=user_id, kind=MemoryKind.ACCOUNT.value,
            account_id=account_id, workspace=workspace,
            status="locked",
        )
        supersedes_id = None
        for item in existing:
            try:
                parsed = json.loads(item["content"])
                if isinstance(parsed, dict) and parsed.get("field") == field:
                    self.update_memory_candidate(item["id"], status="superseded")
                    supersedes_id = item["id"]
                    break
            except (json.JSONDecodeError, TypeError):
                pass

        return self.add_memory_candidate(
            kind=MemoryKind.ACCOUNT,
            user_id=user_id,
            content=json.dumps({"field": field, "value": normalized_value}, ensure_ascii=False),
            evidence=evidence or [],
            confidence=0.8,
            account_id=account_id,
            workspace=workspace,
            supersedes_id=supersedes_id,
        )

    def get_account_dna(
        self, *, user_id: str, account_id: str, workspace: str | None = None,
    ) -> dict[str, Any]:
        """Return the current Account DNA for an account as a flat dict."""
        items = self.list_memories(
            user_id=user_id, kind=MemoryKind.ACCOUNT.value,
            account_id=account_id, workspace=workspace,
            status="verified",
        )
        locked = self.list_memories(
            user_id=user_id, kind=MemoryKind.ACCOUNT.value,
            account_id=account_id, workspace=workspace,
            status="locked",
        )
        all_items = {m["id"]: m for m in items + locked}
        dna: dict[str, Any] = {}
        for m in all_items.values():
            try:
                parsed = json.loads(m["content"])
                if isinstance(parsed, dict) and "field" in parsed:
                    dna[parsed["field"]] = parsed["value"]
            except (json.JSONDecodeError, TypeError):
                pass
        return dna

    MEMORY_STATUS_TRANSITIONS = {
        "pending": {"verified", "rejected"},
        "verified": {"locked", "rejected", "superseded"},
        "locked": {"verified"},
        "rejected": {"verified"},
        "superseded": set(),
    }

    def update_memory_candidate(
        self, candidate_id: str, *, status: str | None = None,
        content: str | None = None,
        rejection_reason: str | None = None,
        task_id: str | None = None,
        provenance: str | None = None,
    ) -> dict[str, Any]:
        current = self.get_memory_candidate(candidate_id)
        old_status = current["status"]
        fields: list[str] = []
        values: list[Any] = []
        if content is not None:
            normalized = content.strip()
            if not normalized:
                raise ValueError("memory content cannot be empty")
            if any(pattern.search(normalized) for pattern in SECRET_PATTERNS):
                raise ValueError("memory content may contain a secret")
            fields.append("content=?")
            values.append(normalized[:2000])
        if status is not None and status != current["status"]:
            allowed = self.MEMORY_STATUS_TRANSITIONS.get(current["status"], set())
            if status not in allowed:
                raise ValueError(f"invalid memory transition: {current['status']} -> {status}")
            fields.append("status=?")
            values.append(status)
            if status == "rejected" and rejection_reason is not None:
                fields.append("rejection_reason=?")
                values.append((rejection_reason or "").strip()[:500])
            elif status != "rejected":
                fields.append("rejection_reason=NULL")
        if not fields:
            return current
        values.append(candidate_id)
        with self._connect() as db:
            db.execute(
                f"UPDATE memory_candidates SET {', '.join(fields)} WHERE id=?", values,
            )
        result = self.get_memory_candidate(candidate_id)

        event_type = None
        if status is not None and status != old_status:
            if status == "verified":
                event_type = MEMORY_EVENT_ADOPTED
            elif status == "rejected":
                event_type = MEMORY_EVENT_REJECTED
            elif status == "superseded":
                event_type = MEMORY_EVENT_SUPERSEDED
        if event_type is None and content is not None:
            event_type = MEMORY_EVENT_MODIFIED

        if event_type:
            self._emit_memory_event(
                event_type, result, task_id=task_id,
                provenance=provenance or "user_confirmed",
                previous_status=old_status,
                rejection_reason=result.get("rejection_reason") or rejection_reason,
            )
        return result

    def grant_authorization(
        self, user_id: str, capability: str, constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_constraints = constraints or {}
        with self._connect() as db:
            row = db.execute(
                "SELECT id, revoked_at FROM user_authorizations WHERE user_id=? AND capability=?",
                (user_id, capability),
            ).fetchone()
            if row:
                db.execute(
                    "UPDATE user_authorizations SET revoked_at=NULL, constraints_json=?, granted_at=? WHERE id=?",
                    (_json(normalized_constraints), _now(), row["id"]),
                )
            else:
                auth_id = _id("auth")
                db.execute(
                    "INSERT INTO user_authorizations (id, user_id, capability, constraints_json, granted_at) VALUES (?, ?, ?, ?, ?)",
                    (auth_id, user_id, capability, _json(normalized_constraints), _now()),
                )
            result = dict(db.execute("SELECT * FROM user_authorizations WHERE user_id=? AND capability=? AND revoked_at IS NULL", (user_id, capability)).fetchone())
            result["constraints"] = json.loads(result.pop("constraints_json"))
            return result

    def revoke_authorization(self, user_id: str, capability: str) -> None:
        with self._connect() as db:
            updated = db.execute(
                "UPDATE user_authorizations SET revoked_at=? WHERE user_id=? AND capability=? AND revoked_at IS NULL",
                (_now(), user_id, capability),
            )
            if updated.rowcount == 0:
                raise KeyError(f"authorization not found: {user_id}/{capability}")

    def list_authorizations(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM user_authorizations WHERE user_id=? AND revoked_at IS NULL ORDER BY granted_at DESC",
                (user_id,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["constraints"] = json.loads(item.pop("constraints_json"))
            result.append(item)
        return result

    CONTENT_STATUS_TRANSITIONS = {
        "draft": {"review", "archived"},
        "review": {"approved", "draft", "archived"},
        "approved": {"published", "archived"},
        "published": {"metrics_collected", "archived"},
        "metrics_collected": {"archived"},
        "archived": set(),
    }

    def create_content_asset(self, *, title: str, type: str = "script",
                             account_id: str | None = None, platform: str | None = None,
                             content: dict[str, Any] | None = None,
                             parent_id: str | None = None,
                             topic: str | None = None,
                             hook: str | None = None,
                             memory_ids: list[str] | None = None,
                             evidence_ids: list[str] | None = None,
                             prompt_model: str | None = None) -> dict[str, Any]:
        asset_id = _id("asset")
        timestamp = _now()
        content = dict(content or {})
        if memory_ids:
            content["_provenance_memory_ids"] = list(memory_ids)
        if evidence_ids:
            content["_provenance_evidence_ids"] = list(evidence_ids)
        if prompt_model:
            content["_provenance_prompt_model"] = prompt_model
        version = 1
        resolved_parent = None
        if parent_id:
            try:
                parent = self.get_content_asset(parent_id)
                version = parent["version"] + 1
                resolved_parent = parent_id
            except KeyError:
                pass
        with self._connect() as db:
            db.execute(
                """INSERT INTO content_assets
                (id, account_id, platform, title, type, status, parent_id, topic, hook,
                 version, content_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?)""",
                (asset_id, account_id, platform, title, type, resolved_parent,
                 (topic or "")[:200], (hook or "")[:200],
                 version, _json(content), timestamp, timestamp),
            )
        return self.get_content_asset(asset_id)

    def get_content_asset(self, asset_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM content_assets WHERE id=?", (asset_id,)).fetchone()
        if row is None:
            raise KeyError(f"content asset not found: {asset_id}")
        result = dict(row)
        result["content"] = json.loads(result.pop("content_json"))
        result["metrics"] = json.loads(result.pop("metrics_json"))
        return result

    def list_content_assets(self, *, account_id: str | None = None, platform: str | None = None,
                            status: str | None = None, type: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT id FROM content_assets WHERE 1=1"
        params: list[Any] = []
        if account_id is not None:
            query += " AND account_id=?"; params.append(account_id)
        if platform is not None:
            query += " AND platform=?"; params.append(platform)
        if status is not None:
            query += " AND status=?"; params.append(status)
        if type is not None:
            query += " AND type=?"; params.append(type)
        query += " ORDER BY updated_at DESC LIMIT 50"
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [self.get_content_asset(r["id"]) for r in rows]

    def transition_content_asset(self, asset_id: str, new_status: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT status FROM content_assets WHERE id=?", (asset_id,)).fetchone()
            if row is None:
                raise KeyError(f"content asset not found: {asset_id}")
            current = row["status"]
            allowed = self.CONTENT_STATUS_TRANSITIONS.get(current, set())
            if new_status not in allowed:
                raise ValueError(f"invalid status transition: {current} -> {new_status}")
            timestamp = _now()
            db.execute(
                "UPDATE content_assets SET status=?, updated_at=? WHERE id=?",
                (new_status, timestamp, asset_id),
            )
        return self.get_content_asset(asset_id)

    def update_content_metrics(self, asset_id: str, metrics: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as db:
            updated = db.execute(
                "UPDATE content_assets SET metrics_json=?, updated_at=? WHERE id=?",
                (_json(metrics), _now(), asset_id),
            )
            if updated.rowcount == 0:
                raise KeyError(f"content asset not found: {asset_id}")
        return self.get_content_asset(asset_id)

    def delete_content_asset(self, asset_id: str) -> None:
        with self._connect() as db:
            deleted = db.execute("DELETE FROM content_assets WHERE id=?", (asset_id,))
            if deleted.rowcount == 0:
                raise KeyError(f"content asset not found: {asset_id}")

    # -- Publishing tasks --

    PUBLISHING_STATUS_TRANSITIONS = {
        "queued": {"executing", "published", "cancelled"},
        "executing": {"published", "failed"},
        "published": {"metrics_collected", "archived"},
        "metrics_collected": {"archived"},
        "failed": {"queued", "archived"},
        "cancelled": {"queued", "archived"},
        "archived": set(),
    }

    def create_publishing_task(
        self, *, asset_id: str, platform: str,
    ) -> dict[str, Any]:
        """Create a publishing task for a content asset."""
        asset = self.get_content_asset(asset_id)
        if asset["status"] == "published":
            raise ValueError("asset already published")
        task_id = _id("pub")
        timestamp = _now()
        with self._connect() as db:
            db.execute(
                """INSERT INTO publishing_tasks
                (id, asset_id, platform, status, published_version, created_at, updated_at)
                VALUES (?, ?, ?, 'queued', ?, ?, ?)""",
                (task_id, asset_id, platform, asset["version"], timestamp, timestamp),
            )
        return self.get_publishing_task(task_id)

    def get_publishing_task(self, task_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM publishing_tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(f"publishing task not found: {task_id}")
        result = dict(row)
        result["receipt"] = json.loads(result.pop("receipt_json")) if result.get("receipt_json") else None
        return result

    def list_publishing_tasks(
        self, *, status: str | None = None, platform: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT id FROM publishing_tasks WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND status=?"
            params.append(status)
        if platform:
            query += " AND platform=?"
            params.append(platform)
        query += " ORDER BY created_at DESC LIMIT 100"
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [self.get_publishing_task(row["id"]) for row in rows]

    def transition_publishing_task(self, task_id: str, new_status: str) -> dict[str, Any]:
        current = self.get_publishing_task(task_id)
        allowed = self.PUBLISHING_STATUS_TRANSITIONS.get(current["status"], set())
        if new_status not in allowed:
            raise ValueError(f"invalid publishing transition: {current['status']} -> {new_status}")
        timestamp = _now()
        with self._connect() as db:
            db.execute(
                "UPDATE publishing_tasks SET status=?, updated_at=? WHERE id=?",
                (new_status, timestamp, task_id),
            )
        return self.get_publishing_task(task_id)

    def complete_publishing_task(
        self, task_id: str, *, effect_id: str, receipt: dict[str, Any],
    ) -> dict[str, Any]:
        """Complete a publishing task with an effect receipt."""
        self.transition_publishing_task(task_id, "published")
        timestamp = _now()
        with self._connect() as db:
            db.execute(
                "UPDATE publishing_tasks SET effect_id=?, receipt_json=?, published_at=?, updated_at=? WHERE id=?",
                (effect_id, _json(receipt), timestamp, timestamp, task_id),
            )
            task = self.get_publishing_task(task_id)
            # Transition the content asset to published
            asset = self.get_content_asset(task["asset_id"])
            if asset["status"] in ("approved", "review"):
                db.execute(
                    "UPDATE content_assets SET status='published', updated_at=? WHERE id=?",
                    (timestamp, task["asset_id"]),
                )
        return self.get_publishing_task(task_id)

    def schedule_metrics_collection(
        self, task_id: str, delay_hours: int = 24,
    ) -> dict[str, Any]:
        from datetime import timedelta
        next_at = (datetime.now(timezone.utc) + timedelta(hours=delay_hours)).isoformat()
        with self._connect() as db:
            db.execute(
                "UPDATE publishing_tasks SET next_metrics_at=?, updated_at=? WHERE id=?",
                (next_at, _now(), task_id),
            )
        return self.get_publishing_task(task_id)

    def collect_metrics(self, task_id: str, metrics: dict[str, Any]) -> dict[str, Any]:
        """Record post-publish metrics for a content asset."""
        task = self.get_publishing_task(task_id)
        self.update_content_metrics(task["asset_id"], metrics)
        if task["status"] == "published":
            self.transition_publishing_task(task_id, "metrics_collected")
        return self.get_publishing_task(task_id)

    def is_authorized(
        self, user_id: str, capability: str, arguments: dict[str, Any] | None = None,
    ) -> bool:
        with self._connect() as db:
            row = db.execute(
                "SELECT constraints_json FROM user_authorizations WHERE user_id=? AND capability=? AND revoked_at IS NULL",
                (user_id, capability),
            ).fetchone()
        if row is None:
            return False
        constraints = json.loads(row["constraints_json"] or "{}")
        supplied = arguments or {}
        return all(supplied.get(key) == value for key, value in constraints.items())

    def _emit_memory_event(
        self, event_type: str, candidate: dict[str, Any], *,
        task_id: str | None = None,
        provenance: str = "agent_inference",
        supersedes_id: str | None = None,
        previous_status: str | None = None,
        rejection_reason: str | None = None,
    ) -> None:
        """Write a typed memory event into ``task_events`` with provenance."""
        payload = {
            "memory_id": candidate["id"],
            "kind": candidate.get("kind"),
            "user_id": candidate.get("user_id"),
            "account_id": candidate.get("account_id"),
            "platform": candidate.get("platform"),
            "workspace": candidate.get("workspace"),
            "confidence": candidate.get("confidence"),
            "status": candidate.get("status"),
            "provenance": provenance,
            "evidence_count": len(candidate.get("evidence") or []),
        }
        if supersedes_id:
            payload["supersedes_id"] = supersedes_id
        if previous_status:
            payload["previous_status"] = previous_status
        if rejection_reason:
            payload["rejection_reason"] = rejection_reason

        tid = task_id or candidate.get("task_id") or ""
        if tid:
            with self._connect() as db:
                self._append_event(db, tid, event_type, payload)

    @staticmethod
    def _append_event(db: sqlite3.Connection, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        db.execute(
            "INSERT INTO task_events (id, task_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (_id("event"), task_id, event_type, _json(payload), _now()),
        )

    @staticmethod
    def _effect_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["preview"] = json.loads(result.pop("preview_json"))
        receipt = result.pop("receipt_json")
        result["receipt"] = json.loads(receipt) if receipt else None
        return result
