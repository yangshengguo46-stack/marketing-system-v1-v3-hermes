"""SQLite event store for durable tasks, approvals, effects, and memory candidates."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from .models import ApprovalStatus, MemoryKind, TaskStatus
from .migrations import (
    MIGRATIONS, backup_database, get_migration_status, migrate_database, rollback_database,
)


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
    METRIC_CHECKPOINTS: tuple[tuple[str, int], ...] = (
        ("1h", 1),
        ("6h", 6),
        ("24h", 24),
        ("3d", 72),
        ("7d", 168),
    )
    METRIC_SNAPSHOT_SOURCES = frozenset({
        "official_api", "creator_center_mcp", "mcp_browser",
        "manual_entry", "public_web", "imported_report",
    })
    PREFLIGHT_STATUSES = frozenset({
        "created", "used_for_action", "revised", "blocked", "archived",
    })
    LEARNING_CANDIDATE_TYPES = frozenset({"memory", "strategy", "weight"})
    LEARNING_CANDIDATE_STATUSES = frozenset({
        "pending", "accepted", "rejected", "superseded",
    })

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        backup_path: Path | None = None
        if self.path.exists() and self.path.stat().st_size > 0:
            migration_status = get_migration_status(self.path)
            if migration_status["pending"]:
                backup_path = backup_database(self.path)
        try:
            # Reconcile the physical schema first.  This is intentionally
            # idempotent so unversioned databases from older desktop builds
            # can be adopted safely before their version marker is advanced.
            self._initialize()
            migrate_database(self.path, MIGRATIONS, create_backup=False)
        except Exception:
            if backup_path is not None and backup_path.exists():
                rollback_database(self.path, backup_path)
            raise

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
            media_table = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='media_attachments'"
            ).fetchone()
            if media_table:
                columns = {row["name"] for row in db.execute("PRAGMA table_info(media_attachments)")}
                if "position" not in columns:
                    db.execute(
                        "ALTER TABLE media_attachments ADD COLUMN position INTEGER NOT NULL DEFAULT 0"
                    )
                if "provenance_json" not in columns:
                    db.execute(
                        "ALTER TABLE media_attachments ADD COLUMN provenance_json TEXT NOT NULL DEFAULT '{}'"
                    )
                db.execute("DROP INDEX IF EXISTS idx_media_attachments_one_active")
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
                    user_id TEXT NOT NULL DEFAULT 'default',
                    account_id TEXT,
                    platform TEXT,
                    title TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'script',
                    status TEXT NOT NULL DEFAULT 'draft',
                    parent_id TEXT REFERENCES content_assets(id),
                    experiment_id TEXT REFERENCES account_experiments(id),
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
                    classification_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS publishing_tasks (
                    id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL REFERENCES content_assets(id) ON DELETE CASCADE,
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

                CREATE TABLE IF NOT EXISTS publishing_metric_checkpoints (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES publishing_tasks(id) ON DELETE CASCADE,
                    checkpoint_label TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'scheduled',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    collected_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(task_id, checkpoint_label)
                );
                CREATE INDEX IF NOT EXISTS idx_metric_checkpoints_due
                    ON publishing_metric_checkpoints(status, due_at);
                CREATE INDEX IF NOT EXISTS idx_metric_checkpoints_task
                    ON publishing_metric_checkpoints(task_id);

                CREATE TABLE IF NOT EXISTS publishing_metric_snapshots (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES publishing_tasks(id) ON DELETE CASCADE,
                    checkpoint_id TEXT REFERENCES publishing_metric_checkpoints(id),
                    asset_id TEXT NOT NULL REFERENCES content_assets(id),
                    platform TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    provenance_json TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_metric_snapshots_task
                    ON publishing_metric_snapshots(task_id, captured_at);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_metric_snapshots_checkpoint
                    ON publishing_metric_snapshots(checkpoint_id) WHERE checkpoint_id IS NOT NULL;

                CREATE TABLE IF NOT EXISTS content_scores (
                    id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL REFERENCES content_assets(id),
                    task_id TEXT REFERENCES agent_tasks(id),
                    rubric_type TEXT NOT NULL DEFAULT 'opinion_video',
                    scores_json TEXT NOT NULL,
                    weighted_total REAL NOT NULL,
                    risk_adjusted_total REAL,
                    risk_flags_json TEXT NOT NULL DEFAULT '[]',
                    notes TEXT NOT NULL DEFAULT '',
                    scored_by TEXT NOT NULL DEFAULT 'agent',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_content_scores_asset ON content_scores(asset_id);
                CREATE INDEX IF NOT EXISTS idx_content_scores_rubric ON content_scores(rubric_type);

                CREATE TABLE IF NOT EXISTS content_predictions (
                    id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL REFERENCES content_assets(id),
                    task_id TEXT REFERENCES agent_tasks(id),
                    prediction_json TEXT NOT NULL,
                    retro_json TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    retro_at TEXT,
                    UNIQUE(asset_id, task_id)
                );
                CREATE INDEX IF NOT EXISTS idx_content_predictions_asset ON content_predictions(asset_id);
                CREATE INDEX IF NOT EXISTS idx_content_predictions_status ON content_predictions(status);

                CREATE TABLE IF NOT EXISTS receipt_refs (
                    id TEXT PRIMARY KEY,
                    source_kind TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    source_table TEXT NOT NULL DEFAULT '',
                    receipt_type TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    account_id TEXT,
                    platform TEXT,
                    asset_id TEXT REFERENCES content_assets(id),
                    task_id TEXT,
                    summary_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    UNIQUE(source_kind, source_id, receipt_type)
                );
                CREATE INDEX IF NOT EXISTS idx_receipt_refs_asset ON receipt_refs(asset_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_receipt_refs_account ON receipt_refs(account_id, platform, created_at);

                CREATE TABLE IF NOT EXISTS preflight_records (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    account_id TEXT,
                    platform TEXT,
                    asset_id TEXT REFERENCES content_assets(id),
                    task_id TEXT REFERENCES agent_tasks(id),
                    prediction_id TEXT REFERENCES content_predictions(id),
                    formula_version TEXT NOT NULL DEFAULT 'influenceos-v0',
                    input_json TEXT NOT NULL DEFAULT '{}',
                    scores_json TEXT NOT NULL DEFAULT '{}',
                    decision_json TEXT NOT NULL DEFAULT '{}',
                    receipt_refs_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'created',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_preflight_records_asset ON preflight_records(asset_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_preflight_records_account ON preflight_records(account_id, platform, created_at);
                CREATE INDEX IF NOT EXISTS idx_preflight_records_prediction ON preflight_records(prediction_id);

                CREATE TABLE IF NOT EXISTS learning_candidates (
                    id TEXT PRIMARY KEY,
                    candidate_type TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    account_id TEXT,
                    platform TEXT,
                    asset_id TEXT REFERENCES content_assets(id),
                    preflight_id TEXT REFERENCES preflight_records(id),
                    prediction_id TEXT REFERENCES content_predictions(id),
                    receipt_refs_json TEXT NOT NULL DEFAULT '[]',
                    proposal_json TEXT NOT NULL DEFAULT '{}',
                    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
                    confidence REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    decision_reason TEXT,
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_learning_candidates_status ON learning_candidates(status, created_at);
                CREATE INDEX IF NOT EXISTS idx_learning_candidates_scope ON learning_candidates(user_id, account_id, platform, created_at);

                CREATE TABLE IF NOT EXISTS benchmark_accounts (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    account_handle TEXT NOT NULL,
                    account_name TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_benchmark_accounts_user ON benchmark_accounts(user_id);

                CREATE TABLE IF NOT EXISTS benchmark_samples (
                    id TEXT PRIMARY KEY,
                    benchmark_account_id TEXT NOT NULL REFERENCES benchmark_accounts(id),
                    video_id TEXT,
                    title TEXT,
                    transcript TEXT,
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    scores_json TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_benchmark_samples_account ON benchmark_samples(benchmark_account_id);

                CREATE TABLE IF NOT EXISTS cadence_state (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    account_id TEXT NOT NULL DEFAULT '',
                    platform TEXT,
                    buffer INTEGER NOT NULL DEFAULT 0,
                    last_published_at TEXT,
                    target_frequency TEXT NOT NULL DEFAULT 'daily',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, account_id)
                );

                CREATE TABLE IF NOT EXISTS video_metrics (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    url TEXT,
                    play_count INTEGER NOT NULL DEFAULT 0,
                    like_count INTEGER NOT NULL DEFAULT 0,
                    comment_count INTEGER NOT NULL DEFAULT 0,
                    share_count INTEGER NOT NULL DEFAULT 0,
                    collect_count INTEGER NOT NULL DEFAULT 0,
                    collected_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_video_metrics_account ON video_metrics(account_id);
                CREATE INDEX IF NOT EXISTS idx_video_metrics_collected ON video_metrics(collected_at);

                CREATE TABLE IF NOT EXISTS media_attachments (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL REFERENCES content_assets(id),
                    original_name TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    byte_size INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    storage_key TEXT NOT NULL UNIQUE,
                    position INTEGER NOT NULL DEFAULT 0,
                    provenance_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    deleted_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_media_attachments_scope
                    ON media_attachments(user_id, account_id, asset_id, status);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_media_attachments_active_position
                    ON media_attachments(asset_id, position) WHERE status='active';

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

                CREATE TABLE IF NOT EXISTS audience_snapshots (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES account_strategy_projects(id),
                    user_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    dimensions_json TEXT NOT NULL DEFAULT '{}',
                    provenance_json TEXT NOT NULL,
                    window_start TEXT,
                    window_end TEXT,
                    captured_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audience_snapshots_scope
                    ON audience_snapshots(user_id, account_id, project_id, captured_at);

                CREATE TABLE IF NOT EXISTS positioning_versions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES account_strategy_projects(id),
                    user_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    positioning_json TEXT NOT NULL,
                    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL,
                    approved_at TEXT,
                    UNIQUE(project_id, version)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_positioning_one_active
                    ON positioning_versions(project_id) WHERE status='approved';
                CREATE INDEX IF NOT EXISTS idx_positioning_scope
                    ON positioning_versions(user_id, account_id, project_id);

                CREATE TABLE IF NOT EXISTS account_experiments (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES account_strategy_projects(id),
                    user_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    hypothesis TEXT NOT NULL,
                    variable_json TEXT NOT NULL DEFAULT '{}',
                    asset_ids_json TEXT NOT NULL DEFAULT '[]',
                    prediction_json TEXT NOT NULL DEFAULT '{}',
                    success_criteria_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_account_experiments_scope
                    ON account_experiments(user_id, account_id, project_id, status);

                CREATE TABLE IF NOT EXISTS strategy_candidates (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES account_strategy_projects(id),
                    user_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    proposal_json TEXT NOT NULL,
                    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_strategy_candidates_scope
                    ON strategy_candidates(user_id, account_id, project_id, status);

                CREATE TABLE IF NOT EXISTS benchmark_observations (
                    id TEXT PRIMARY KEY,
                    benchmark_account_id TEXT NOT NULL REFERENCES benchmark_accounts(id),
                    project_id TEXT NOT NULL REFERENCES account_strategy_projects(id),
                    user_id TEXT NOT NULL,
                    target_account_id TEXT NOT NULL,
                    dimension TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    provenance_json TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_benchmark_observations_scope
                    ON benchmark_observations(user_id, target_account_id, project_id, benchmark_account_id);
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
            if "classification_json" not in mem_columns:
                db.execute(
                    "ALTER TABLE memory_candidates ADD COLUMN classification_json TEXT NOT NULL DEFAULT '{}'"
                )

            ca_columns = {row["name"] for row in db.execute("PRAGMA table_info(content_assets)")}
            if "user_id" not in ca_columns:
                db.execute(
                    "ALTER TABLE content_assets ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'"
                )
            for col in ("parent_id", "topic", "hook"):
                if col not in ca_columns:
                    db.execute(f"ALTER TABLE content_assets ADD COLUMN {col} TEXT")
            if "experiment_id" not in ca_columns:
                db.execute("ALTER TABLE content_assets ADD COLUMN experiment_id TEXT")
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_content_assets_experiment ON content_assets(experiment_id)"
            )

            score_columns = {row["name"] for row in db.execute("PRAGMA table_info(content_scores)")}
            if "risk_adjusted_total" not in score_columns:
                db.execute("ALTER TABLE content_scores ADD COLUMN risk_adjusted_total REAL")
            if "risk_flags_json" not in score_columns:
                db.execute(
                    "ALTER TABLE content_scores ADD COLUMN risk_flags_json TEXT NOT NULL DEFAULT '[]'"
                )

            benchmark_columns = {row["name"] for row in db.execute("PRAGMA table_info(benchmark_accounts)")}
            for column in ("project_id", "target_account_id", "relation", "selection_reason", "source_ref"):
                if column not in benchmark_columns:
                    db.execute(f"ALTER TABLE benchmark_accounts ADD COLUMN {column} TEXT")
            if "selection_status" not in benchmark_columns:
                db.execute(
                    "ALTER TABLE benchmark_accounts ADD COLUMN selection_status "
                    "TEXT NOT NULL DEFAULT 'selected'"
                )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_benchmark_accounts_scope "
                "ON benchmark_accounts(user_id, target_account_id, project_id)"
            )
            sample_columns = {row["name"] for row in db.execute("PRAGMA table_info(benchmark_samples)")}
            if "provenance_json" not in sample_columns:
                db.execute(
                    "ALTER TABLE benchmark_samples ADD COLUMN provenance_json "
                    "TEXT NOT NULL DEFAULT '{}'"
                )
            strategy_columns = {row["name"] for row in db.execute("PRAGMA table_info(strategy_candidates)")}
            if "decision_reason" not in strategy_columns:
                db.execute("ALTER TABLE strategy_candidates ADD COLUMN decision_reason TEXT")

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

    def task_has_pending_approval(self, task_id: str) -> bool:
        with self._connect() as db:
            row = db.execute(
                """SELECT 1 FROM approval_requests WHERE task_id=? AND status='pending' LIMIT 1""",
                (task_id,),
            ).fetchone()
        return row is not None

    def task_has_unresolved_effect(self, task_id: str) -> bool:
        with self._connect() as db:
            row = db.execute(
                """SELECT 1 FROM effect_intents WHERE task_id=?
                AND status IN ('pending','unknown') LIMIT 1""", (task_id,)
            ).fetchone()
        return row is not None

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

    def update_task_objective(self, task_id: str, objective: str) -> dict[str, Any]:
        with self._connect() as db:
            updated = db.execute(
                "UPDATE agent_tasks SET objective=?, updated_at=? WHERE id=?",
                (objective, _now(), task_id),
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
            elif status is TaskStatus.COMPLETED:
                fields.append("last_error=NULL")
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
            reported_status = str(receipt.get("status", "")).strip().lower()
            if reported_status in {"failed", "error", "cancelled"}:
                effect_status = "failed"
                event_type = "effect.failed"
            elif reported_status in {"unknown", "timeout", "indeterminate"}:
                effect_status = "unknown"
                event_type = "effect.outcome_unknown"
            else:
                effect_status = "executed"
                event_type = "effect.executed"
            db.execute(
                "UPDATE effect_intents SET status=?, receipt_json=?, executed_at=? WHERE id=?",
                (effect_status, _json(receipt), timestamp, effect_id),
            )
            self._append_event(db, row["task_id"], event_type, {
                "effect_id": effect_id,
                "approval_id": row["approval_id"],
                "capability": row["capability"],
                "receipt": receipt,
            })
        effect = self.get_effect(effect_id)
        task = self.get_task(effect["task_id"])
        self.create_receipt_ref(
            source_kind="effect",
            source_id=effect_id,
            source_table="effect_intents",
            receipt_type=effect["capability"],
            user_id=task.get("user_id") or "default",
            account_id=task.get("account_id"),
            task_id=task["id"],
            summary={
                "status": effect["status"],
                "capability": effect["capability"],
                "executed_at": effect.get("executed_at"),
                "receipt": effect.get("receipt") or {},
            },
        )
        return effect

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
        classification: dict[str, Any] | None = None,
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
                 status, rejection_reason, observed_at, valid_from, valid_to, supersedes_id, classification_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (candidate_id, kind.value, user_id, account_id, platform, workspace, content, _json(evidence),
                 confidence, status, rejection_reason, _now(), valid_from, valid_to, supersedes_id,
                 _json(classification or {}), _now()),
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
        if "classification_json" in result:
            result["classification"] = json.loads(result.pop("classification_json"))
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
        # MEM-04: supersede keeps history and must be user-reversible.
        "superseded": {"verified"},
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
                             user_id: str = "default",
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
                (id, user_id, account_id, platform, title, type, status, parent_id, topic, hook,
                 version, content_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?)""",
                (asset_id, user_id, account_id, platform, title, type, resolved_parent,
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
        should_increment_buffer = False
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
            should_increment_buffer = new_status == "approved" and current != "approved"
        asset = self.get_content_asset(asset_id)
        if should_increment_buffer:
            self.get_or_create_cadence(
                user_id=asset.get("user_id") or "default",
                account_id=asset.get("account_id"), platform=asset.get("platform"),
            )
            self.increment_buffer(asset.get("user_id") or "default", asset.get("account_id"))
        return asset

    def update_content_metrics(self, asset_id: str, metrics: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as db:
            updated = db.execute(
                "UPDATE content_assets SET metrics_json=?, updated_at=? WHERE id=?",
                (_json(metrics), _now(), asset_id),
            )
            if updated.rowcount == 0:
                raise KeyError(f"content asset not found: {asset_id}")
        return self.get_content_asset(asset_id)

    def update_content_asset_content(self, asset_id: str, content: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as db:
            updated = db.execute(
                "UPDATE content_assets SET content_json=?, updated_at=? WHERE id=?",
                (_json(dict(content or {})), _now(), asset_id),
            )
            if updated.rowcount == 0:
                raise KeyError(f"content asset not found: {asset_id}")
        return self.get_content_asset(asset_id)

    def delete_content_asset(self, asset_id: str) -> None:
        with self._connect() as db:
            deleted = db.execute("DELETE FROM content_assets WHERE id=?", (asset_id,))
            if deleted.rowcount == 0:
                raise KeyError(f"content asset not found: {asset_id}")

    def register_media_attachment(
        self, *, user_id: str, account_id: str, asset_id: str,
        original_name: str, mime_type: str, byte_size: int,
        sha256: str, storage_key: str, position: int | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Register a user-selected file copied into the App-managed media root."""
        asset = self.get_content_asset(asset_id)
        if asset.get("user_id") != user_id or asset.get("account_id") != account_id:
            raise ValueError("media attachment is outside content asset scope")
        if asset.get("type") not in {"video", "image"}:
            raise ValueError("media attachments require a video or image asset")
        if not original_name.strip() or len(original_name) > 255:
            raise ValueError("invalid original_name")
        allowed_mimes = {
            "video/mp4", "video/quicktime", "video/webm",
            "image/jpeg", "image/png", "image/webp",
        }
        if mime_type not in allowed_mimes:
            raise ValueError(f"unsupported media type: {mime_type}")
        if not isinstance(byte_size, int) or isinstance(byte_size, bool) or not 0 < byte_size <= 5 * 1024**3:
            raise ValueError("media byte_size must be between 1 byte and 5 GiB")
        if not re.fullmatch(r"[a-f0-9]{64}", sha256):
            raise ValueError("invalid media sha256")
        if not re.fullmatch(r"[a-f0-9]{32}/[A-Za-z0-9._-]{1,180}", storage_key):
            raise ValueError("invalid media storage_key")
        provenance = dict(provenance or {})
        if provenance:
            if provenance.get("provider") != "pexels":
                raise ValueError("unsupported media provenance provider")
            if not str(provenance.get("source_url") or "").startswith("https://www.pexels.com/"):
                raise ValueError("invalid media provenance source_url")
            if str(provenance.get("license") or "") != "Pexels License":
                raise ValueError("invalid media provenance license")
        attachment_id = _id("media")
        timestamp = _now()
        with self._connect() as db:
            if asset.get("type") == "video":
                if not mime_type.startswith("video/"):
                    raise ValueError("video assets require a video attachment")
                position = 0
                db.execute(
                    """UPDATE media_attachments SET status='superseded',deleted_at=?
                    WHERE asset_id=? AND user_id=? AND account_id=? AND status='active'""",
                    (timestamp, asset_id, user_id, account_id),
                )
            else:
                if not mime_type.startswith("image/"):
                    raise ValueError("image assets require image attachments")
                active = db.execute(
                    """SELECT position FROM media_attachments WHERE asset_id=? AND user_id=?
                    AND account_id=? AND status='active' ORDER BY position""",
                    (asset_id, user_id, account_id),
                ).fetchall()
                if position is None:
                    position = (max((row["position"] for row in active), default=-1) + 1)
                if not isinstance(position, int) or isinstance(position, bool) or not 0 <= position <= 8:
                    raise ValueError("image attachment position must be between 0 and 8")
                if len(active) >= 9 and all(row["position"] != position for row in active):
                    raise ValueError("image assets support at most 9 active attachments")
                db.execute(
                    """UPDATE media_attachments SET status='superseded',deleted_at=?
                    WHERE asset_id=? AND user_id=? AND account_id=? AND position=? AND status='active'""",
                    (timestamp, asset_id, user_id, account_id, position),
                )
            db.execute(
                """INSERT INTO media_attachments
                (id,user_id,account_id,asset_id,original_name,mime_type,byte_size,sha256,
                 storage_key,position,provenance_json,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,'active',?)""",
                (attachment_id, user_id, account_id, asset_id, original_name.strip(),
                 mime_type, byte_size, sha256, storage_key, position,
                 json.dumps(provenance, ensure_ascii=False), timestamp),
            )
        return self.get_media_attachment(
            attachment_id, user_id=user_id, account_id=account_id, include_storage_key=True,
        )

    def get_media_attachment(
        self, attachment_id: str, *, user_id: str, account_id: str,
        include_storage_key: bool = False,
    ) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute(
                """SELECT * FROM media_attachments
                WHERE id=? AND user_id=? AND account_id=?""",
                (attachment_id, user_id, account_id),
            ).fetchone()
        if row is None:
            raise KeyError("media attachment not found in account scope")
        result = dict(row)
        result["provenance"] = json.loads(result.pop("provenance_json", "{}") or "{}")
        if not include_storage_key:
            result.pop("storage_key", None)
        return result

    def get_active_media_attachment(
        self, *, asset_id: str, user_id: str, account_id: str,
        include_storage_key: bool = False,
    ) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                """SELECT id FROM media_attachments WHERE asset_id=? AND user_id=?
                AND account_id=? AND status='active'""",
                (asset_id, user_id, account_id),
            ).fetchone()
        return None if row is None else self.get_media_attachment(
            row["id"], user_id=user_id, account_id=account_id,
            include_storage_key=include_storage_key,
        )

    def list_active_media_attachments(
        self, *, asset_id: str, user_id: str, account_id: str,
        include_storage_key: bool = False,
    ) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT id FROM media_attachments WHERE asset_id=? AND user_id=?
                AND account_id=? AND status='active' ORDER BY position,created_at""",
                (asset_id, user_id, account_id),
            ).fetchall()
        return [
            self.get_media_attachment(
                row["id"], user_id=user_id, account_id=account_id,
                include_storage_key=include_storage_key,
            )
            for row in rows
        ]

    def delete_media_attachment(
        self, attachment_id: str, *, user_id: str, account_id: str,
    ) -> dict[str, Any]:
        with self._connect() as db:
            changed = db.execute(
                """UPDATE media_attachments SET status='deleted',deleted_at=?
                WHERE id=? AND user_id=? AND account_id=? AND status='active'""",
                (_now(), attachment_id, user_id, account_id),
            )
            if changed.rowcount != 1:
                raise KeyError("active media attachment not found in account scope")
        return self.get_media_attachment(
            attachment_id, user_id=user_id, account_id=account_id,
        )

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
        asset = self.get_content_asset(task["asset_id"])
        self.get_or_create_cadence(
            user_id=asset.get("user_id") or "default",
            account_id=asset.get("account_id"), platform=asset.get("platform"),
        )
        self.decrement_buffer(asset.get("user_id") or "default", asset.get("account_id"))
        self.schedule_metric_checkpoints(task_id)
        published = self.get_publishing_task(task_id)
        self.create_receipt_ref(
            source_kind="publishing",
            source_id=task_id,
            source_table="publishing_tasks",
            receipt_type="publish_receipt",
            user_id=asset.get("user_id") or "default",
            account_id=asset.get("account_id"),
            platform=published.get("platform") or asset.get("platform"),
            asset_id=asset["id"],
            task_id=task_id,
            summary={
                "status": published["status"],
                "platform": published.get("platform"),
                "published_at": published.get("published_at"),
                "receipt": published.get("receipt") or {},
            },
        )
        return published

    def schedule_metrics_collection(
        self, task_id: str, delay_hours: int = 24,
    ) -> dict[str, Any]:
        next_at = (datetime.now(timezone.utc) + timedelta(hours=delay_hours)).isoformat()
        with self._connect() as db:
            db.execute(
                "UPDATE publishing_tasks SET next_metrics_at=?, updated_at=? WHERE id=?",
                (next_at, _now(), task_id),
            )
        return self.get_publishing_task(task_id)

    def schedule_metric_checkpoints(self, task_id: str) -> list[dict[str, Any]]:
        """Create the product metric recovery cadence for a published task.

        Checkpoints are idempotent.  Keeping this as store-owned state makes
        future MCP, official API, or manual collection adapters share the same
        recovery plan instead of inventing separate timers.
        """
        task = self.get_publishing_task(task_id)
        if task["status"] not in {"published", "metrics_collected"}:
            raise ValueError("metric checkpoints require a published task")
        published_at = task.get("published_at") or _now()
        try:
            base = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
        except ValueError:
            base = datetime.now(timezone.utc)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        timestamp = _now()
        with self._connect() as db:
            for label, hours in self.METRIC_CHECKPOINTS:
                db.execute(
                    """INSERT OR IGNORE INTO publishing_metric_checkpoints
                    (id, task_id, checkpoint_label, due_at, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'scheduled', ?, ?)""",
                    (_id("metric_ckpt"), task_id, label,
                     (base + timedelta(hours=hours)).isoformat(), timestamp, timestamp),
                )
            first_due = db.execute(
                """SELECT due_at FROM publishing_metric_checkpoints
                WHERE task_id=? AND status='scheduled' ORDER BY due_at ASC LIMIT 1""",
                (task_id,),
            ).fetchone()
            if first_due is not None:
                db.execute(
                    "UPDATE publishing_tasks SET next_metrics_at=?, updated_at=? WHERE id=?",
                    (first_due["due_at"], timestamp, task_id),
                )
        return self.list_metric_checkpoints(task_id)

    def _metric_checkpoint_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        return dict(row)

    def list_metric_checkpoints(self, task_id: str) -> list[dict[str, Any]]:
        self.get_publishing_task(task_id)
        with self._connect() as db:
            rows = db.execute(
                """SELECT * FROM publishing_metric_checkpoints
                WHERE task_id=? ORDER BY due_at ASC""",
                (task_id,),
            ).fetchall()
        return [self._metric_checkpoint_from_row(row) for row in rows]

    def list_due_metric_checkpoints(self, *, now: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        cutoff = now or _now()
        with self._connect() as db:
            rows = db.execute(
                """SELECT * FROM publishing_metric_checkpoints
                WHERE status='scheduled' AND due_at<=?
                ORDER BY due_at ASC LIMIT ?""",
                (cutoff, max(1, min(int(limit), 100))),
            ).fetchall()
        return [self._metric_checkpoint_from_row(row) for row in rows]

    def defer_metric_checkpoint(
        self, checkpoint_id: str, *, reason: str, retry_after_minutes: int = 60,
    ) -> dict[str, Any]:
        """Record a failed/deferred metric attempt without fabricating metrics."""
        delay = max(5, min(int(retry_after_minutes), 24 * 60))
        next_due = (datetime.now(timezone.utc) + timedelta(minutes=delay)).isoformat()
        timestamp = _now()
        with self._connect() as db:
            row = db.execute(
                "SELECT task_id FROM publishing_metric_checkpoints WHERE id=?",
                (checkpoint_id,),
            ).fetchone()
            if row is None:
                raise KeyError("metric checkpoint not found")
            task_id = row["task_id"]
            db.execute(
                """UPDATE publishing_metric_checkpoints
                SET due_at=?, attempts=attempts+1, last_error=?, updated_at=?
                WHERE id=?""",
                (next_due, str(reason)[:500], timestamp, checkpoint_id),
            )
            first_due = db.execute(
                """SELECT due_at FROM publishing_metric_checkpoints
                WHERE task_id=? AND status='scheduled'
                ORDER BY due_at ASC LIMIT 1""",
                (task_id,),
            ).fetchone()
            db.execute(
                "UPDATE publishing_tasks SET next_metrics_at=?, updated_at=? WHERE id=?",
                (first_due["due_at"] if first_due is not None else None, timestamp, task_id),
            )
            updated = db.execute(
                "SELECT * FROM publishing_metric_checkpoints WHERE id=?",
                (checkpoint_id,),
            ).fetchone()
        return self._metric_checkpoint_from_row(updated)

    def _normalize_metric_snapshot(
        self, metrics: dict[str, Any], provenance: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any], str]:
        if not isinstance(metrics, dict) or not metrics:
            raise ValueError("metrics must be a non-empty object")
        normalized: dict[str, Any] = {}
        for key, value in metrics.items():
            metric_key = str(key).strip()
            if not metric_key:
                raise ValueError("metric keys must be non-empty")
            if value is None:
                raise ValueError(f"metric {metric_key!r} is unknown; omit it instead of writing null")
            if isinstance(value, str) and value.strip().lower() in {"", "unknown", "未知", "n/a", "na"}:
                raise ValueError(f"metric {metric_key!r} is unknown; omit it instead of writing a placeholder")
            normalized[metric_key] = value
        prov = dict(provenance or {})
        source_kind = str(prov.get("source_kind") or prov.get("source") or "manual_entry").strip()
        if source_kind not in self.METRIC_SNAPSHOT_SOURCES:
            raise ValueError(f"unsupported metric source: {source_kind}")
        captured_at = str(prov.get("captured_at") or _now()).strip()
        prov["source_kind"] = source_kind
        prov["captured_at"] = captured_at
        return normalized, prov, captured_at

    def record_metric_snapshot(
        self, task_id: str, metrics: dict[str, Any], *,
        checkpoint_id: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        task = self.get_publishing_task(task_id)
        asset = self.get_content_asset(task["asset_id"])
        normalized, prov, captured_at = self._normalize_metric_snapshot(metrics, provenance)
        timestamp = _now()
        snapshot_id = _id("metric")
        with self._connect() as db:
            if checkpoint_id is None:
                row = db.execute(
                    """SELECT id FROM publishing_metric_checkpoints
                    WHERE task_id=? AND status='scheduled'
                    ORDER BY due_at ASC LIMIT 1""",
                    (task_id,),
                ).fetchone()
                checkpoint_id = row["id"] if row is not None else None
            elif db.execute(
                "SELECT id FROM publishing_metric_checkpoints WHERE id=? AND task_id=?",
                (checkpoint_id, task_id),
            ).fetchone() is None:
                raise KeyError("metric checkpoint not found for task")
            db.execute(
                """INSERT INTO publishing_metric_snapshots
                (id, task_id, checkpoint_id, asset_id, platform, metrics_json,
                 provenance_json, captured_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (snapshot_id, task_id, checkpoint_id, asset["id"], task["platform"],
                 _json(normalized), _json(prov), captured_at, timestamp),
            )
            if checkpoint_id is not None:
                db.execute(
                    """UPDATE publishing_metric_checkpoints
                    SET status='collected', attempts=attempts+1, collected_at=?,
                        last_error=NULL, updated_at=?
                    WHERE id=?""",
                    (captured_at, timestamp, checkpoint_id),
                )
                next_due = db.execute(
                    """SELECT due_at FROM publishing_metric_checkpoints
                    WHERE task_id=? AND status='scheduled'
                    ORDER BY due_at ASC LIMIT 1""",
                    (task_id,),
                ).fetchone()
                db.execute(
                    "UPDATE publishing_tasks SET next_metrics_at=?, updated_at=? WHERE id=?",
                    (next_due["due_at"] if next_due is not None else None, timestamp, task_id),
                )
        snapshot = self.get_metric_snapshot(snapshot_id)
        self.create_receipt_ref(
            source_kind="metric_snapshot",
            source_id=snapshot_id,
            source_table="publishing_metric_snapshots",
            receipt_type="metric_snapshot",
            user_id=asset.get("user_id") or "default",
            account_id=asset.get("account_id"),
            platform=snapshot["platform"],
            asset_id=asset["id"],
            task_id=task_id,
            summary={
                "checkpoint_id": snapshot.get("checkpoint_id"),
                "captured_at": snapshot.get("captured_at"),
                "metrics": snapshot.get("metrics") or {},
                "provenance": snapshot.get("provenance") or {},
            },
        )
        return snapshot

    def get_metric_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM publishing_metric_snapshots WHERE id=?",
                (snapshot_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"metric snapshot not found: {snapshot_id}")
        result = dict(row)
        result["metrics"] = json.loads(result.pop("metrics_json"))
        result["provenance"] = json.loads(result.pop("provenance_json"))
        return result

    def list_metric_snapshots(self, task_id: str) -> list[dict[str, Any]]:
        self.get_publishing_task(task_id)
        with self._connect() as db:
            rows = db.execute(
                """SELECT id FROM publishing_metric_snapshots
                WHERE task_id=? ORDER BY captured_at ASC""",
                (task_id,),
            ).fetchall()
        return [self.get_metric_snapshot(row["id"]) for row in rows]

    def collect_metrics(
        self, task_id: str, metrics: dict[str, Any],
        *, checkpoint_id: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record metrics and trigger the product-owned learning pipeline."""
        task = self.get_publishing_task(task_id)
        snapshot = self.record_metric_snapshot(
            task_id, metrics, checkpoint_id=checkpoint_id, provenance=provenance,
        )
        self.update_content_metrics(task["asset_id"], metrics)
        if task["status"] == "published":
            self.transition_publishing_task(task_id, "metrics_collected")
        from .learning_pipeline import reconcile_published_metrics
        learning = reconcile_published_metrics(self, task_id, snapshot=snapshot)
        return {
            **self.get_publishing_task(task_id),
            "metric_snapshot": snapshot,
            "metric_checkpoints": self.list_metric_checkpoints(task_id),
            "learning": learning,
        }

    # ── Core loop: Memory × Receipt × Preflight ───────────────────────

    def create_receipt_ref(
        self,
        *,
        source_kind: str,
        source_id: str,
        receipt_type: str,
        source_table: str = "",
        user_id: str = "default",
        account_id: str | None = None,
        platform: str | None = None,
        asset_id: str | None = None,
        task_id: str | None = None,
        summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create an idempotent reference to a concrete observed fact.

        A receipt ref is deliberately tiny: it points at the durable source of
        truth and carries only a redacted summary for LLM/context use.  This is
        the bridge that lets preflight predictions and learning candidates cite
        real outcomes without copying raw cookies, reports, or bulky payloads.
        """
        source_kind = str(source_kind).strip()
        source_id = str(source_id).strip()
        receipt_type = str(receipt_type).strip()
        if not source_kind or not source_id or not receipt_type:
            raise ValueError("source_kind, source_id and receipt_type are required")
        if asset_id:
            self.get_content_asset(asset_id)
        if task_id:
            try:
                self.get_task(task_id)
            except KeyError:
                # Publishing tasks also use task_id in this table; keep this
                # generic so the receipt layer can reference both agent tasks
                # and publish tasks without forcing one artificial hierarchy.
                self.get_publishing_task(task_id)
        timestamp = _now()
        with self._connect() as db:
            existing = db.execute(
                """SELECT * FROM receipt_refs
                WHERE source_kind=? AND source_id=? AND receipt_type=?""",
                (source_kind, source_id, receipt_type),
            ).fetchone()
            if existing is not None:
                return self._receipt_ref_dict(existing)
            receipt_id = _id("receipt")
            db.execute(
                """INSERT INTO receipt_refs
                (id, source_kind, source_id, source_table, receipt_type, user_id,
                 account_id, platform, asset_id, task_id, summary_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    receipt_id, source_kind, source_id, source_table, receipt_type,
                    user_id, account_id, platform, asset_id, task_id,
                    _json(summary or {}), timestamp,
                ),
            )
            row = db.execute("SELECT * FROM receipt_refs WHERE id=?", (receipt_id,)).fetchone()
        return self._receipt_ref_dict(row)

    def get_receipt_ref(self, receipt_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM receipt_refs WHERE id=?", (receipt_id,)).fetchone()
        if row is None:
            raise KeyError(f"receipt ref not found: {receipt_id}")
        return self._receipt_ref_dict(row)

    def list_receipt_refs(
        self,
        *,
        asset_id: str | None = None,
        account_id: str | None = None,
        platform: str | None = None,
        receipt_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = "SELECT id FROM receipt_refs WHERE 1=1"
        params: list[Any] = []
        if asset_id:
            query += " AND asset_id=?"; params.append(asset_id)
        if account_id:
            query += " AND account_id=?"; params.append(account_id)
        if platform:
            query += " AND platform=?"; params.append(platform)
        if receipt_type:
            query += " AND receipt_type=?"; params.append(receipt_type)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [self.get_receipt_ref(row["id"]) for row in rows]

    def create_preflight_record(
        self,
        *,
        input: dict[str, Any],
        scores: dict[str, Any],
        decision: dict[str, Any],
        user_id: str = "default",
        account_id: str | None = None,
        platform: str | None = None,
        asset_id: str | None = None,
        task_id: str | None = None,
        prediction_id: str | None = None,
        formula_version: str = "influenceos-v0",
        receipt_refs: list[str] | None = None,
        status: str = "created",
    ) -> dict[str, Any]:
        """Persist an immutable pre-action forecast for later settlement."""
        if status not in self.PREFLIGHT_STATUSES:
            raise ValueError(f"unsupported preflight status: {status}")
        if asset_id:
            self.get_content_asset(asset_id)
        if task_id:
            self.get_task(task_id)
        if prediction_id:
            self.get_prediction(prediction_id)
        refs = list(receipt_refs or [])
        for ref_id in refs:
            self.get_receipt_ref(ref_id)
        preflight_id = _id("preflight")
        timestamp = _now()
        with self._connect() as db:
            db.execute(
                """INSERT INTO preflight_records
                (id, user_id, account_id, platform, asset_id, task_id, prediction_id,
                 formula_version, input_json, scores_json, decision_json,
                 receipt_refs_json, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    preflight_id, user_id, account_id, platform, asset_id, task_id,
                    prediction_id, formula_version, _json(input), _json(scores),
                    _json(decision), _json(refs), status, timestamp,
                ),
            )
            if task_id:
                self._append_event(db, task_id, "core.preflight_created", {
                    "preflight_id": preflight_id,
                    "asset_id": asset_id,
                    "prediction_id": prediction_id,
                    "formula_version": formula_version,
                    "status": status,
                })
        return self.get_preflight_record(preflight_id)

    def get_preflight_record(self, preflight_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM preflight_records WHERE id=?", (preflight_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"preflight record not found: {preflight_id}")
        return self._preflight_record_dict(row)

    def list_preflight_records(
        self,
        *,
        asset_id: str | None = None,
        account_id: str | None = None,
        platform: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        query = "SELECT id FROM preflight_records WHERE 1=1"
        params: list[Any] = []
        if asset_id:
            query += " AND asset_id=?"; params.append(asset_id)
        if account_id:
            query += " AND account_id=?"; params.append(account_id)
        if platform:
            query += " AND platform=?"; params.append(platform)
        if status:
            query += " AND status=?"; params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [self.get_preflight_record(row["id"]) for row in rows]

    def mark_preflight_used(self, preflight_id: str) -> dict[str, Any]:
        with self._connect() as db:
            updated = db.execute(
                "UPDATE preflight_records SET status='used_for_action' WHERE id=?",
                (preflight_id,),
            )
            if updated.rowcount != 1:
                raise KeyError(f"preflight record not found: {preflight_id}")
        return self.get_preflight_record(preflight_id)

    def create_learning_candidate(
        self,
        *,
        candidate_type: str,
        proposal: dict[str, Any],
        evidence_refs: list[str] | None = None,
        receipt_refs: list[str] | None = None,
        confidence: float = 0.0,
        user_id: str = "default",
        account_id: str | None = None,
        platform: str | None = None,
        asset_id: str | None = None,
        preflight_id: str | None = None,
        prediction_id: str | None = None,
        status: str = "pending",
    ) -> dict[str, Any]:
        """Create a governed learning candidate without mutating memory.

        This is the safety valve between "the system noticed something" and
        "the agent has learned it".  Promotion into durable memory or strategy
        weights should happen only after review/guardrails decide the candidate.
        """
        candidate_type = str(candidate_type).strip()
        if candidate_type not in self.LEARNING_CANDIDATE_TYPES:
            raise ValueError(f"unsupported learning candidate type: {candidate_type}")
        if status not in self.LEARNING_CANDIDATE_STATUSES:
            raise ValueError(f"unsupported learning candidate status: {status}")
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if asset_id:
            self.get_content_asset(asset_id)
        if preflight_id:
            self.get_preflight_record(preflight_id)
        if prediction_id:
            self.get_prediction(prediction_id)
        refs = list(receipt_refs or [])
        for ref_id in refs:
            self.get_receipt_ref(ref_id)
        evidence = list(evidence_refs or [])
        candidate_id = _id("learn")
        timestamp = _now()
        decided_at = timestamp if status != "pending" else None
        with self._connect() as db:
            db.execute(
                """INSERT INTO learning_candidates
                (id, candidate_type, user_id, account_id, platform, asset_id,
                 preflight_id, prediction_id, receipt_refs_json, proposal_json,
                 evidence_refs_json, confidence, status, created_at, decided_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    candidate_id, candidate_type, user_id, account_id, platform,
                    asset_id, preflight_id, prediction_id, _json(refs),
                    _json(proposal), _json(evidence), confidence, status,
                    timestamp, decided_at,
                ),
            )
        return self.get_learning_candidate(candidate_id)

    def get_learning_candidate(self, candidate_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM learning_candidates WHERE id=?", (candidate_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"learning candidate not found: {candidate_id}")
        return self._learning_candidate_dict(row)

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
        query = "SELECT id FROM learning_candidates WHERE 1=1"
        params: list[Any] = []
        if candidate_type:
            query += " AND candidate_type=?"; params.append(candidate_type)
        if status:
            query += " AND status=?"; params.append(status)
        if user_id:
            query += " AND user_id=?"; params.append(user_id)
        if account_id:
            query += " AND account_id=?"; params.append(account_id)
        if platform:
            query += " AND platform=?"; params.append(platform)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [self.get_learning_candidate(row["id"]) for row in rows]

    def decide_learning_candidate(
        self, candidate_id: str, *, status: str, reason: str | None = None,
    ) -> dict[str, Any]:
        if status not in {"accepted", "rejected", "superseded"}:
            raise ValueError("learning candidate decision must be accepted, rejected or superseded")
        timestamp = _now()
        with self._connect() as db:
            row = db.execute(
                "SELECT status FROM learning_candidates WHERE id=?", (candidate_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"learning candidate not found: {candidate_id}")
            if row["status"] != "pending":
                return self.get_learning_candidate(candidate_id)
            db.execute(
                """UPDATE learning_candidates
                SET status=?, decision_reason=?, decided_at=?
                WHERE id=?""",
                (status, (reason or "")[:500], timestamp, candidate_id),
            )
        return self.get_learning_candidate(candidate_id)

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

    # ── Content scores (RUN-17) ────────────────────────────────────────

    def record_content_score(
        self,
        *,
        asset_id: str,
        scores: dict[str, int],
        rubric_type: str = "opinion_video",
        task_id: str | None = None,
        notes: str = "",
        scored_by: str = "agent",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a content score for an asset.

        Validates scores via content_rubric and persists.
        """
        from .content_rubric import validate_scores, compute_weighted_total, score_content

        validate_scores(scores, rubric_type)
        cs = score_content(scores, rubric_type=rubric_type, notes=notes, scored_by=scored_by, metadata=metadata)
        weighted = cs.weighted_total
        risk_adjusted = cs.risk_adjusted_total
        risk_flags = cs.risk_flags
        score_id = _id("score")
        timestamp = _now()
        with self._connect() as db:
            db.execute(
                """INSERT INTO content_scores
                (id, asset_id, task_id, rubric_type, scores_json, weighted_total,
                 risk_adjusted_total, risk_flags_json,
                 notes, scored_by, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    score_id, asset_id, task_id, rubric_type,
                    _json(scores), weighted, risk_adjusted, _json(risk_flags),
                    notes, scored_by,
                    _json(metadata or {}), timestamp,
                ),
            )
            if task_id:
                self._append_event(db, task_id, "content.scored", {
                    "score_id": score_id,
                    "asset_id": asset_id,
                    "rubric_type": rubric_type,
                    "weighted_total": weighted,
                    "risk_adjusted_total": risk_adjusted,
                    "risk_flags": risk_flags,
                    "scored_by": scored_by,
                })
        return self.get_content_score(score_id)

    def get_content_score(self, score_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM content_scores WHERE id=?", (score_id,)).fetchone()
        if row is None:
            raise KeyError(f"content score not found: {score_id}")
        return self._content_score_dict(row)

    def list_content_scores(
        self,
        *,
        asset_id: str | None = None,
        rubric_type: str | None = None,
        scored_by: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT id FROM content_scores WHERE 1=1"
        params: list[Any] = []
        if asset_id:
            query += " AND asset_id=?"; params.append(asset_id)
        if rubric_type:
            query += " AND rubric_type=?"; params.append(rubric_type)
        if scored_by:
            query += " AND scored_by=?"; params.append(scored_by)
        query += " ORDER BY created_at DESC LIMIT 100"
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [self.get_content_score(r["id"]) for r in rows]

    @staticmethod
    def _content_score_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["scores"] = json.loads(result.pop("scores_json"))
        result["metadata"] = json.loads(result.pop("metadata_json"))
        if "risk_flags_json" in result:
            result["risk_flags"] = json.loads(result.pop("risk_flags_json"))
        return result

    # ── Content predictions (RUN-18) ───────────────────────────────────

    def create_prediction(
        self,
        *,
        asset_id: str,
        prediction: dict[str, Any],
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a blind prediction for an asset.

        Predictions are immutable once written. If a prediction already
        exists for the same (asset_id, task_id) pair, the existing one is
        returned unchanged — this enforces the blind-prediction principle.
        """
        prediction_id = _id("pred")
        timestamp = _now()
        with self._connect() as db:
            # Check existing for same asset+task.
            if task_id:
                existing = db.execute(
                    "SELECT * FROM content_predictions WHERE asset_id=? AND task_id=?",
                    (asset_id, task_id),
                ).fetchone()
                if existing is not None:
                    return self._prediction_dict(existing)
            db.execute(
                """INSERT INTO content_predictions
                (id, asset_id, task_id, prediction_json, status, created_at)
                VALUES (?, ?, ?, ?, 'pending', ?)""",
                (prediction_id, asset_id, task_id, _json(prediction), timestamp),
            )
            if task_id:
                self._append_event(db, task_id, "content.prediction_created", {
                    "prediction_id": prediction_id,
                    "asset_id": asset_id,
                })
        return self.get_prediction(prediction_id)

    def get_prediction(self, prediction_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM content_predictions WHERE id=?", (prediction_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"prediction not found: {prediction_id}")
        return self._prediction_dict(row)

    def get_prediction_by_asset(
        self, asset_id: str, task_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Get the prediction for an asset, optionally filtered by task."""
        with self._connect() as db:
            if task_id:
                row = db.execute(
                    "SELECT * FROM content_predictions WHERE asset_id=? AND task_id=?",
                    (asset_id, task_id),
                ).fetchone()
            else:
                row = db.execute(
                    "SELECT * FROM content_predictions WHERE asset_id=? ORDER BY created_at DESC LIMIT 1",
                    (asset_id,),
                ).fetchone()
        return self._prediction_dict(row) if row else None

    def list_predictions(
        self,
        *,
        asset_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT id FROM content_predictions WHERE 1=1"
        params: list[Any] = []
        if asset_id:
            query += " AND asset_id=?"; params.append(asset_id)
        if status:
            query += " AND status=?"; params.append(status)
        query += " ORDER BY created_at DESC LIMIT 100"
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [self.get_prediction(r["id"]) for r in rows]

    def record_retro(
        self,
        prediction_id: str,
        retro: dict[str, Any],
    ) -> dict[str, Any]:
        """Record retrospective results for a prediction.

        The prediction itself remains immutable; only the retro_json and
        status are updated. This enforces the blind-prediction principle:
        predictions cannot be rewritten after seeing data.
        """
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM content_predictions WHERE id=?", (prediction_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"prediction not found: {prediction_id}")
            if row["status"] == "retro_completed":
                # Idempotent: return existing if already completed
                return self._prediction_dict(row)
            timestamp = _now()
            db.execute(
                "UPDATE content_predictions SET retro_json=?, status='retro_completed', retro_at=? WHERE id=?",
                (_json(retro), timestamp, prediction_id),
            )
            if row["task_id"]:
                self._append_event(db, row["task_id"], "content.retrospective", {
                    "prediction_id": prediction_id,
                    "asset_id": row["asset_id"],
                })
        return self.get_prediction(prediction_id)

    @staticmethod
    def _prediction_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["prediction"] = json.loads(result.pop("prediction_json"))
        retro = result.pop("retro_json")
        result["retro"] = json.loads(retro) if retro else None
        return result

    # ── Benchmark accounts & samples (RUN-21) ──────────────────────────

    def add_benchmark_account(
        self,
        *,
        user_id: str,
        platform: str,
        account_handle: str,
        account_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Register a benchmark (对标) account for cold-start anchoring."""
        account_id = _id("bench")
        timestamp = _now()
        with self._connect() as db:
            db.execute(
                """INSERT INTO benchmark_accounts
                (id, user_id, platform, account_handle, account_name, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (account_id, user_id, platform, account_handle, account_name,
                 _json(metadata or {}), timestamp),
            )
        return self.get_benchmark_account(account_id)

    def get_benchmark_account(self, account_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM benchmark_accounts WHERE id=?", (account_id,)).fetchone()
        if row is None:
            raise KeyError(f"benchmark account not found: {account_id}")
        result = dict(row)
        result["metadata"] = json.loads(result.pop("metadata_json"))
        return result

    def list_benchmark_accounts(self, user_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id FROM benchmark_accounts WHERE user_id=? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [self.get_benchmark_account(r["id"]) for r in rows]

    def add_benchmark_sample(
        self,
        *,
        benchmark_account_id: str,
        video_id: str | None = None,
        title: str | None = None,
        transcript: str | None = None,
        metrics: dict[str, Any] | None = None,
        scores: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """Add a sample video from a benchmark account."""
        sample_id = _id("sample")
        timestamp = _now()
        with self._connect() as db:
            db.execute(
                """INSERT INTO benchmark_samples
                (id, benchmark_account_id, video_id, title, transcript,
                 metrics_json, scores_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (sample_id, benchmark_account_id, video_id, title, transcript,
                 _json(metrics or {}), _json(scores) if scores else None, timestamp),
            )
        return self.get_benchmark_sample(sample_id)

    def get_benchmark_sample(self, sample_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM benchmark_samples WHERE id=?", (sample_id,)).fetchone()
        if row is None:
            raise KeyError(f"benchmark sample not found: {sample_id}")
        result = dict(row)
        result["metrics"] = json.loads(result.pop("metrics_json"))
        scores = result.pop("scores_json")
        result["scores"] = json.loads(scores) if scores else None
        return result

    def list_benchmark_samples(self, benchmark_account_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id FROM benchmark_samples WHERE benchmark_account_id=? ORDER BY created_at DESC",
                (benchmark_account_id,),
            ).fetchall()
        return [self.get_benchmark_sample(r["id"]) for r in rows]

    def derive_rubric_anchor(
        self,
        benchmark_account_id: str,
        rubric_type: str = "opinion_video",
    ) -> dict[str, Any]:
        """Derive initial rubric anchor from benchmark samples.

        Averages the dimension scores across all samples to produce
        a baseline scoring pattern for the user's content type.
        """
        from .content_rubric import get_rubric

        samples = self.list_benchmark_samples(benchmark_account_id)
        rubric = get_rubric(rubric_type)
        dim_keys = [d.key for d in rubric]

        # Collect scores per dimension
        dim_scores: dict[str, list[int]] = {k: [] for k in dim_keys}
        for sample in samples:
            if sample.get("scores"):
                for key in dim_keys:
                    val = sample["scores"].get(key)
                    if val is not None:
                        dim_scores[key].append(val)

        # Compute averages
        anchor: dict[str, float] = {}
        for key in dim_keys:
            vals = dim_scores[key]
            anchor[key] = round(sum(vals) / len(vals), 1) if vals else 5.0

        return {
            "benchmark_account_id": benchmark_account_id,
            "rubric_type": rubric_type,
            "sample_count": len(samples),
            "anchor_scores": anchor,
            "dimension_averages": anchor,
        }

    # ── Cadence state (RUN-22) ─────────────────────────────────────────

    # Buffer thresholds per frequency
    CADENCE_THRESHOLDS = {
        "daily": {"green": 3, "yellow": 1, "red": 0},
        "weekly": {"green": 2, "yellow": 1, "red": 0},
        "biweekly": {"green": 1, "yellow": 0, "red": -1},
    }

    def get_or_create_cadence(
        self,
        *,
        user_id: str,
        account_id: str | None = None,
        platform: str | None = None,
        target_frequency: str = "daily",
    ) -> dict[str, Any]:
        """Get or create cadence state for a user/account."""
        acct = account_id or ""
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM cadence_state WHERE user_id=? AND account_id=?",
                (user_id, acct),
            ).fetchone()
            if row:
                result = dict(row)
                result["metadata"] = json.loads(result.pop("metadata_json"))
                return result
            cadence_id = _id("cadence")
            timestamp = _now()
            db.execute(
                """INSERT INTO cadence_state
                (id, user_id, account_id, platform, buffer, target_frequency, metadata_json, updated_at)
                VALUES (?, ?, ?, ?, 0, ?, '{}', ?)""",
                (cadence_id, user_id, acct, platform, target_frequency, timestamp),
            )
        return self.get_or_create_cadence(
            user_id=user_id, account_id=account_id, platform=platform,
            target_frequency=target_frequency,
        )

    def increment_buffer(self, user_id: str, account_id: str | None = None) -> dict[str, Any]:
        """Increment buffer when content is shot but not published."""
        acct = account_id or ""
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM cadence_state WHERE user_id=? AND account_id=?",
                (user_id, acct),
            ).fetchone()
            if row is None:
                raise KeyError(f"cadence state not found for user {user_id}")
            new_buffer = row["buffer"] + 1
            timestamp = _now()
            db.execute(
                "UPDATE cadence_state SET buffer=?, updated_at=? WHERE id=?",
                (new_buffer, timestamp, row["id"]),
            )
        return self.get_or_create_cadence(user_id=user_id, account_id=account_id)

    def decrement_buffer(self, user_id: str, account_id: str | None = None) -> dict[str, Any]:
        """Decrement buffer when content is published."""
        acct = account_id or ""
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM cadence_state WHERE user_id=? AND account_id=?",
                (user_id, acct),
            ).fetchone()
            if row is None:
                raise KeyError(f"cadence state not found for user {user_id}")
            new_buffer = max(0, row["buffer"] - 1)
            timestamp = _now()
            db.execute(
                "UPDATE cadence_state SET buffer=?, last_published_at=?, updated_at=? WHERE id=?",
                (new_buffer, timestamp, timestamp, row["id"]),
            )
        return self.get_or_create_cadence(user_id=user_id, account_id=account_id)

    def get_cadence_status(self, user_id: str, account_id: str | None = None) -> dict[str, Any]:
        """Get cadence status with buffer alert level."""
        cadence = self.get_or_create_cadence(user_id=user_id, account_id=account_id)
        freq = cadence["target_frequency"]
        thresholds = self.CADENCE_THRESHOLDS.get(freq, self.CADENCE_THRESHOLDS["daily"])
        buffer = cadence["buffer"]

        if buffer >= thresholds["green"]:
            alert = "green"
        elif buffer >= thresholds["yellow"]:
            alert = "yellow"
        else:
            alert = "red"

        return {
            **cadence,
            "alert": alert,
            "thresholds": thresholds,
        }

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
    def _receipt_ref_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["summary"] = json.loads(result.pop("summary_json") or "{}")
        return result

    @staticmethod
    def _preflight_record_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["input"] = json.loads(result.pop("input_json") or "{}")
        result["scores"] = json.loads(result.pop("scores_json") or "{}")
        result["decision"] = json.loads(result.pop("decision_json") or "{}")
        result["receipt_refs"] = json.loads(result.pop("receipt_refs_json") or "[]")
        return result

    @staticmethod
    def _learning_candidate_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["receipt_refs"] = json.loads(result.pop("receipt_refs_json") or "[]")
        result["proposal"] = json.loads(result.pop("proposal_json") or "{}")
        result["evidence_refs"] = json.loads(result.pop("evidence_refs_json") or "[]")
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

    def add_video_metric(
        self,
        *,
        account_id: str,
        title: str,
        url: str | None = None,
        play_count: int = 0,
        like_count: int = 0,
        comment_count: int = 0,
        share_count: int = 0,
        collect_count: int = 0,
    ) -> dict[str, Any]:
        ts = _now()
        vid = _id("vm")
        with self._connect() as db:
            db.execute(
                """INSERT INTO video_metrics
                (id, account_id, title, url, play_count, like_count,
                 comment_count, share_count, collect_count, collected_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (vid, account_id, title, url, play_count, like_count,
                 comment_count, share_count, collect_count, ts, ts),
            )
            row = db.execute("SELECT * FROM video_metrics WHERE id=?", (vid,)).fetchone()
        return dict(row)

    def list_video_metrics(
        self,
        *,
        account_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM video_metrics WHERE account_id=? ORDER BY collected_at DESC LIMIT ?",
                (account_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]
