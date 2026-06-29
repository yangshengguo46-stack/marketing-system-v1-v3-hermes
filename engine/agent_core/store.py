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
    TaskStatus.PLANNING: {TaskStatus.RUNNING, TaskStatus.WAITING_USER, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {
        TaskStatus.WAITING_USER, TaskStatus.RETRYING, TaskStatus.PAUSED,
        TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED,
    },
    TaskStatus.WAITING_USER: {TaskStatus.RUNNING, TaskStatus.PAUSED, TaskStatus.CANCELLED, TaskStatus.FAILED},
    TaskStatus.RETRYING: {TaskStatus.RUNNING, TaskStatus.FAILED, TaskStatus.CANCELLED},
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


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

                CREATE TABLE IF NOT EXISTS memory_candidates (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    account_id TEXT,
                    platform TEXT,
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
                """
            )

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
                "approval_id": approval_id, "capability": capability, "risk_summary": risk_summary,
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

    def decide_approval(self, approval_id: str, approved: bool, reason: str | None = None) -> dict[str, Any]:
        target = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        with self._connect() as db:
            row = db.execute("SELECT * FROM approval_requests WHERE id=?", (approval_id,)).fetchone()
            if row is None:
                raise KeyError(f"approval not found: {approval_id}")
            if row["status"] != ApprovalStatus.PENDING.value:
                raise ValueError("approval already decided")
            timestamp = _now()
            db.execute(
                "UPDATE approval_requests SET status=?, decision_reason=?, decided_at=? WHERE id=?",
                (target.value, reason, timestamp, approval_id),
            )
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
                "effect_id": effect_id, "receipt": receipt,
            })
        return self.get_effect(effect_id)

    def add_memory_candidate(
        self, *, kind: MemoryKind, user_id: str, content: str,
        evidence: list[dict[str, Any]], confidence: float,
        account_id: str | None = None, platform: str | None = None,
        valid_from: str | None = None, valid_to: str | None = None,
        supersedes_id: str | None = None,
    ) -> dict[str, Any]:
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        rejected = any(pattern.search(content) for pattern in SECRET_PATTERNS)
        candidate_id = _id("memory")
        status = "rejected" if rejected else "pending"
        rejection_reason = "可能包含秘密，禁止进入记忆" if rejected else None
        with self._connect() as db:
            db.execute(
                """INSERT INTO memory_candidates
                (id, kind, user_id, account_id, platform, content, evidence_json, confidence,
                 status, rejection_reason, observed_at, valid_from, valid_to, supersedes_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (candidate_id, kind.value, user_id, account_id, platform, content, _json(evidence),
                 confidence, status, rejection_reason, _now(), valid_from, valid_to, supersedes_id, _now()),
            )
        return self.get_memory_candidate(candidate_id)

    def get_memory_candidate(self, candidate_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM memory_candidates WHERE id=?", (candidate_id,)).fetchone()
        if row is None:
            raise KeyError(f"memory candidate not found: {candidate_id}")
        result = dict(row)
        result["evidence"] = json.loads(result.pop("evidence_json"))
        return result

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

