"""DESK-09: Database migration framework.

Provides:
1. Schema version tracking via `_schema_version` meta table
2. Pre-migration backup (copy DB file)
3. Atomic migrations with rollback on failure
4. N-1 → N migration support

Migrations are registered in MIGRATIONS list and applied in order.
Each migration has: version, description, up(sql), down(sql).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Callable


class Migration:
    """A single database migration."""

    def __init__(
        self,
        version: int,
        description: str,
        up_sql: str,
        down_sql: str = "",
    ):
        self.version = version
        self.description = description
        self.up_sql = up_sql
        self.down_sql = down_sql


# Registry of all migrations, ordered by version
MIGRATIONS: list[Migration] = [
    Migration(
        version=1,
        description="Initial schema (all CREATE TABLE IF NOT EXISTS)",
        up_sql="",  # Already handled by _initialize, this is the baseline
        down_sql="",
    ),
    Migration(
        version=2,
        description="Add constraints_json to user_authorizations + revoke legacy grants",
        up_sql="""
            -- Column addition is idempotent via PRAGMA check in _initialize
            -- This migration records that the schema change was applied
        """,
        down_sql="",
    ),
    Migration(
        version=3,
        description="Add workspace to memory_candidates",
        # AgentCoreStore performs the idempotent column reconciliation.
        up_sql="",
        down_sql="",
    ),
    Migration(
        version=4,
        description="Add parent_id, topic, hook to content_assets",
        # AgentCoreStore performs the idempotent column reconciliation.
        up_sql="",
        down_sql="",
    ),
    Migration(
        version=5,
        description="Add content_scores table for RUN-17 content scoring protocol",
        up_sql="""
            CREATE TABLE IF NOT EXISTS content_scores (
                id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL REFERENCES content_assets(id),
                task_id TEXT REFERENCES agent_tasks(id),
                rubric_type TEXT NOT NULL DEFAULT 'opinion_video',
                scores_json TEXT NOT NULL,
                weighted_total REAL NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                scored_by TEXT NOT NULL DEFAULT 'agent',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_content_scores_asset ON content_scores(asset_id);
            CREATE INDEX IF NOT EXISTS idx_content_scores_rubric ON content_scores(rubric_type);
        """,
        down_sql="DROP TABLE IF EXISTS content_scores;",
    ),
    Migration(
        version=6,
        description="Add content_predictions table for RUN-18 blind prediction mechanism",
        up_sql="""
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
        """,
        down_sql="DROP TABLE IF EXISTS content_predictions;",
    ),
    Migration(
        version=7,
        description="Add benchmark_accounts, benchmark_samples, cadence_state for RUN-21/22",
        up_sql="""
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
        """,
        down_sql="""
            DROP TABLE IF EXISTS cadence_state;
            DROP TABLE IF EXISTS benchmark_samples;
            DROP TABLE IF EXISTS benchmark_accounts;
        """,
    ),
    Migration(
        version=8,
        description="UPGRADE-01: Add risk_adjusted_total and risk_flags_json to content_scores",
        # Column reconciliation is performed idempotently by AgentCoreStore.
        # Keeping this migration as a version marker avoids duplicate-column
        # failures for databases created by builds that already had the fields.
        up_sql="",
        down_sql="""
            -- SQLite doesn't support DROP COLUMN easily; recreate without the columns
            -- For rollback, restore from backup
        """,
    ),
    Migration(
        version=9,
        description="UPGRADE-03: Add classification_json to memory_candidates for three-layer knowledge classification",
        # See v8: AgentCoreStore owns idempotent column reconciliation.
        up_sql="",
        down_sql="",
    ),
    Migration(
        version=10,
        description="Add user ownership to content assets for learning scope isolation",
        # AgentCoreStore performs the idempotent column reconciliation.
        up_sql="",
        down_sql="",
    ),
    Migration(
        version=11,
        description="Add video_metrics table for per-video performance data",
        # AgentCoreStore creates the table idempotently via CREATE TABLE IF NOT EXISTS.
        up_sql="",
        down_sql="",
    ),
    Migration(
        version=12,
        description="LIFE-01: Add account lifecycle domain truth tables",
        # AgentCoreStore reconciles this schema before advancing the marker so
        # old unversioned desktop databases and current databases share one path.
        up_sql="",
        down_sql="",
    ),
    Migration(
        version=13,
        description="LIFE-03: Add scoped benchmark observations",
        up_sql="",
        down_sql="",
    ),
    Migration(
        version=14,
        description="LIFE-03: Separate benchmark candidates from selected evidence",
        up_sql="",
        down_sql="",
    ),
    Migration(
        version=15,
        description="LIFE-03: Add provenance to benchmark content samples",
        up_sql="",
        down_sql="",
    ),
    Migration(
        version=16,
        description="LIFE-07: Link content assets to account experiments",
        up_sql="",
        down_sql="",
    ),
    Migration(
        version=17,
        description="LIFE-09: Add strategy candidate decision reason",
        up_sql="",
        down_sql="",
    ),
    Migration(
        version=18,
        description="PUB-06A: Add user-imported media attachments",
        up_sql="",
        down_sql="DROP TABLE IF EXISTS media_attachments;",
    ),
    Migration(
        version=19,
        description="PUB-06C: Support ordered multi-image attachments",
        # Physical reconciliation is performed idempotently by AgentCoreStore._initialize
        # so fresh, legacy, and unversioned databases follow the same path.
        up_sql="",
        down_sql="""
            DROP INDEX IF EXISTS idx_media_attachments_active_position;
            CREATE UNIQUE INDEX IF NOT EXISTS idx_media_attachments_one_active
                ON media_attachments(asset_id) WHERE status='active';
        """,
    ),
    Migration(
        version=20,
        description="PUB-06D: Preserve stock-image provenance on media attachments",
        up_sql="",
        down_sql="",
    ),
    Migration(
        version=21,
        description="DELIV-05: Add publishing metric checkpoints and provenance snapshots",
        # AgentCoreStore creates and reconciles the physical tables idempotently.
        up_sql="",
        down_sql="""
            DROP TABLE IF EXISTS publishing_metric_snapshots;
            DROP TABLE IF EXISTS publishing_metric_checkpoints;
        """,
    ),
    Migration(
        version=22,
        description="CORE-LOOP-01/02/03: Add preflight records, receipt refs, and learning candidates",
        # AgentCoreStore creates and reconciles these tables idempotently.
        # Keeping this as a version marker lets existing desktop databases move
        # forward without duplicating CREATE TABLE logic in two places.
        up_sql="",
        down_sql="""
            DROP TABLE IF EXISTS learning_candidates;
            DROP TABLE IF EXISTS preflight_records;
            DROP TABLE IF EXISTS receipt_refs;
        """,
    ),
]


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Get current schema version from _schema_version meta table."""
    try:
        row = conn.execute(
            "SELECT value FROM _schema_version WHERE key='version'"
        ).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.OperationalError:
        return 0


def set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Set schema version in meta table."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _schema_version (key TEXT PRIMARY KEY, value TEXT)"
    )
    conn.execute(
        "INSERT OR REPLACE INTO _schema_version (key, value) VALUES ('version', ?)",
        (str(version),),
    )


def backup_database(db_path: Path) -> Path:
    """Create a backup of the database file before migration.

    Returns path to backup file.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    backup_path = db_path.with_suffix(f".db.bak")
    # Use SQLite's online backup API so committed WAL pages are included.
    # Copying only the main .db file can silently produce a stale backup.
    source = sqlite3.connect(str(db_path))
    destination = sqlite3.connect(str(backup_path))
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return backup_path


def migrate_database(
    db_path: Path,
    migrations: list[Migration] | None = None,
    *,
    create_backup: bool = True,
) -> dict[str, Any]:
    """Run pending migrations on a database.

    Returns dict with: from_version, to_version, migrations_applied, backup_path.
    Raises on migration failure (database is rolled back to pre-migration state).
    """
    if migrations is None:
        migrations = MIGRATIONS

    backup_path: Path | None = None
    if create_backup and db_path.exists():
        backup_path = backup_database(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")

    current_version = get_schema_version(conn)
    pending = [m for m in migrations if m.version > current_version]

    if not pending:
        conn.close()
        return {
            "from_version": current_version,
            "to_version": current_version,
            "migrations_applied": [],
            "backup_path": str(backup_path) if backup_path else None,
        }

    applied: list[dict[str, Any]] = []

    try:
        for migration in pending:
            try:
                # sqlite3.executescript commits an already-open transaction.
                # Put BEGIN/COMMIT inside the script so a multi-statement
                # migration and its version marker are one atomic unit.
                escaped_version = str(int(migration.version))
                migration_sql = migration.up_sql.strip()
                if migration_sql and not migration_sql.endswith(";"):
                    migration_sql += ";"
                conn.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + migration_sql
                    + "\nCREATE TABLE IF NOT EXISTS _schema_version "
                      "(key TEXT PRIMARY KEY, value TEXT);\n"
                    + "INSERT OR REPLACE INTO _schema_version (key, value) "
                      f"VALUES ('version', '{escaped_version}');\n"
                    + "COMMIT;"
                )
                applied.append({
                    "version": migration.version,
                    "description": migration.description,
                })
            except Exception as e:
                conn.rollback()
                raise RuntimeError(
                    f"Migration v{migration.version} failed: {e}"
                ) from e

        new_version = get_schema_version(conn)
        conn.close()

        return {
            "from_version": current_version,
            "to_version": new_version,
            "migrations_applied": applied,
            "backup_path": str(backup_path) if backup_path else None,
        }

    except Exception as e:
        conn.close()
        # Restore backup if migration failed
        if backup_path and backup_path.exists():
            rollback_database(db_path, backup_path)
        raise


def rollback_database(db_path: Path, backup_path: Path) -> None:
    """Restore database from a backup file."""
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_path}")
    source = sqlite3.connect(str(backup_path))
    destination = sqlite3.connect(str(db_path))
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def get_migration_status(db_path: Path) -> dict[str, Any]:
    """Get current migration status without running migrations."""
    if not db_path.exists():
        return {"exists": False, "version": 0, "pending": len(MIGRATIONS)}

    conn = sqlite3.connect(str(db_path))
    version = get_schema_version(conn)
    conn.close()

    pending = [m for m in MIGRATIONS if m.version > version]

    return {
        "exists": True,
        "version": version,
        "latest": MIGRATIONS[-1].version if MIGRATIONS else 0,
        "pending": len(pending),
        "pending_versions": [m.version for m in pending],
    }
