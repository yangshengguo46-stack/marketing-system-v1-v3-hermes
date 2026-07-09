"""DESK-09: Database migration tests.

Verifies:
1. Schema version tracking works
2. Backup is created before migration
3. Migrations apply in order
4. Failed migrations are rolled back
5. N-1 → N upgrade works
6. Idempotent (running twice doesn't re-apply)
7. Rollback restores from backup
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agent_core.migrations import (
    Migration,
    MIGRATIONS,
    get_schema_version,
    set_schema_version,
    backup_database,
    migrate_database,
    rollback_database,
    get_migration_status,
)
from agent_core.store import AgentCoreStore


@pytest.fixture
def test_db(tmp_path):
    """Create a minimal test database."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE agent_tasks (id TEXT PRIMARY KEY, status TEXT)")
    conn.execute("CREATE TABLE _schema_version (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO _schema_version VALUES ('version', '0')")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def test_migrations():
    """Create test migrations."""
    return [
        Migration(1, "baseline", ""),
        Migration(
            2, "add column",
            "ALTER TABLE agent_tasks ADD COLUMN objective TEXT",
        ),
        Migration(
            3, "add another column",
            "ALTER TABLE agent_tasks ADD COLUMN created_at TEXT",
        ),
    ]


class TestSchemaVersion:
    def test_get_version_from_fresh_db(self, tmp_path):
        db = tmp_path / "fresh.db"
        conn = sqlite3.connect(str(db))
        assert get_schema_version(conn) == 0
        conn.close()

    def test_set_and_get_version(self, tmp_path):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        set_schema_version(conn, 5)
        assert get_schema_version(conn) == 5
        conn.close()

    def test_set_version_is_idempotent(self, tmp_path):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        set_schema_version(conn, 3)
        set_schema_version(conn, 3)
        assert get_schema_version(conn) == 3
        conn.close()


class TestBackup:
    def test_backup_creates_file(self, test_db):
        backup = backup_database(test_db)
        assert backup.exists()
        assert backup.name == "test.db.bak"

    def test_backup_content_matches(self, test_db):
        conn = sqlite3.connect(str(test_db))
        conn.execute("INSERT INTO agent_tasks VALUES ('t1', 'running')")
        conn.commit()
        conn.close()

        backup = backup_database(test_db)

        backup_conn = sqlite3.connect(str(backup))
        rows = backup_conn.execute("SELECT * FROM agent_tasks").fetchall()
        assert len(rows) == 1
        backup_conn.close()

    def test_backup_fails_on_missing_db(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            backup_database(tmp_path / "nonexistent.db")


class TestMigrateDatabase:
    def test_applies_pending_migrations(self, test_db, test_migrations):
        result = migrate_database(test_db, test_migrations, create_backup=False)
        assert result["from_version"] == 0
        assert result["to_version"] == 3
        assert len(result["migrations_applied"]) == 3

    def test_idempotent(self, test_db, test_migrations):
        migrate_database(test_db, test_migrations, create_backup=False)
        result = migrate_database(test_db, test_migrations, create_backup=False)
        assert result["from_version"] == 3
        assert result["to_version"] == 3
        assert len(result["migrations_applied"]) == 0

    def test_creates_backup(self, test_db, test_migrations):
        result = migrate_database(test_db, test_migrations, create_backup=True)
        assert result["backup_path"] is not None
        assert Path(result["backup_path"]).exists()

    def test_no_backup_when_disabled(self, test_db, test_migrations):
        result = migrate_database(test_db, test_migrations, create_backup=False)
        assert result["backup_path"] is None

    def test_columns_added(self, test_db, test_migrations):
        migrate_database(test_db, test_migrations, create_backup=False)
        conn = sqlite3.connect(str(test_db))
        cols = {row[1] for row in conn.execute("PRAGMA table_info(agent_tasks)")}
        assert "objective" in cols
        assert "created_at" in cols
        conn.close()

    def test_failed_migration_rolls_back(self, test_db):
        bad_migrations = [
            Migration(1, "ok", ""),
            Migration(2, "bad", "ALTER TABLE nonexistent_table ADD COLUMN x TEXT"),
        ]
        with pytest.raises(RuntimeError, match="Migration v2 failed"):
            migrate_database(test_db, bad_migrations, create_backup=True)

        # Backup was created before any migration, so rollback restores to v0
        conn = sqlite3.connect(str(test_db))
        assert get_schema_version(conn) == 0
        conn.close()


class TestRollback:
    def test_rollback_restores_database(self, test_db):
        conn = sqlite3.connect(str(test_db))
        conn.execute("INSERT INTO agent_tasks VALUES ('t1', 'running')")
        conn.commit()
        conn.close()

        backup = backup_database(test_db)

        # Modify the database
        conn = sqlite3.connect(str(test_db))
        conn.execute("INSERT INTO agent_tasks VALUES ('t2', 'completed')")
        conn.commit()
        conn.close()

        # Rollback
        rollback_database(test_db, backup)

        conn = sqlite3.connect(str(test_db))
        rows = conn.execute("SELECT * FROM agent_tasks").fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "t1"
        conn.close()


class TestMigrationStatus:
    def test_status_for_fresh_db(self, tmp_path):
        status = get_migration_status(tmp_path / "nonexistent.db")
        assert status["exists"] is False
        assert status["version"] == 0

    def test_status_for_current_db(self, test_db, test_migrations):
        migrate_database(test_db, test_migrations, create_backup=False)
        status = get_migration_status(test_db)
        assert status["exists"] is True
        assert status["version"] == 3
        # Global MIGRATIONS may have more entries; just check version is correct
        assert status["version"] == test_migrations[-1].version

    def test_status_shows_pending(self, test_db, test_migrations):
        # Apply only first migration
        partial = [test_migrations[0]]
        migrate_database(test_db, partial, create_backup=False)
        status = get_migration_status(test_db)
        assert status["version"] == 1
        # Pending is based on global MIGRATIONS, just verify >0 pending
        assert status["pending"] > 0
        assert status["version"] < status["latest"]


class TestNM1Upgrade:
    """Simulate N-1 → N upgrade scenario."""

    def test_upgrade_from_v1_to_v3(self, test_db, test_migrations):
        # Start at v1
        migrate_database(test_db, [test_migrations[0]], create_backup=False)
        assert get_migration_status(test_db)["version"] == 1

        # Upgrade to v3
        result = migrate_database(test_db, test_migrations, create_backup=True)
        assert result["from_version"] == 1
        assert result["to_version"] == 3
        assert len(result["migrations_applied"]) == 2

    def test_upgrade_preserves_data(self, test_db, test_migrations):
        # Insert data at v0
        conn = sqlite3.connect(str(test_db))
        conn.execute("INSERT INTO agent_tasks VALUES ('task_001', 'running')")
        conn.commit()
        conn.close()

        # Migrate to v3
        migrate_database(test_db, test_migrations, create_backup=False)

        # Data should still be there
        conn = sqlite3.connect(str(test_db))
        rows = conn.execute("SELECT id, status FROM agent_tasks").fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "task_001"
        conn.close()


class TestRegisteredMigrations:
    def test_migrations_are_ordered(self):
        versions = [m.version for m in MIGRATIONS]
        assert versions == sorted(versions)
        assert len(versions) == len(set(versions))  # no duplicates

    def test_migrations_have_descriptions(self):
        for m in MIGRATIONS:
            assert m.description, f"Migration v{m.version} missing description"

    def test_latest_version_is_positive(self):
        assert MIGRATIONS[-1].version > 0


class TestStoreMigrationIntegration:
    def test_store_initialization_applies_registered_schema_version(self, tmp_path):
        db_path = tmp_path / "agent_core.db"

        AgentCoreStore(db_path)

        status = get_migration_status(db_path)
        assert status["version"] == MIGRATIONS[-1].version
        assert status["pending"] == 0

    def test_unversioned_legacy_database_is_reconciled_and_preserved(self, tmp_path):
        db_path = tmp_path / "legacy.db"
        store = AgentCoreStore(db_path)
        session = store.create_or_get_session(user_id="legacy-user")

        # Simulate a pre-versioning desktop database while preserving its data.
        conn = sqlite3.connect(db_path)
        conn.execute("DROP TABLE _schema_version")
        conn.commit()
        conn.close()

        reopened = AgentCoreStore(db_path)

        assert reopened.get_session(session["id"])["user_id"] == "legacy-user"
        assert get_migration_status(db_path)["pending"] == 0

        conn = sqlite3.connect(db_path)
        memory_columns = {row[1] for row in conn.execute("PRAGMA table_info(memory_candidates)")}
        score_columns = {row[1] for row in conn.execute("PRAGMA table_info(content_scores)")}
        conn.close()
        assert "classification_json" in memory_columns
        assert {"risk_adjusted_total", "risk_flags_json"} <= score_columns
