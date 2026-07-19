from __future__ import annotations

import json
import sqlite3

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.schema import LEGACY_MARKETING_TABLES
from hermes_state import SessionDB


def test_marketing_paths_default_to_the_hermes_state_owner(tmp_path):
    paths = MarketingDataPaths.from_env({"HERMES_HOME": str(tmp_path / "runtime")})

    assert paths.user_data == tmp_path / "runtime"
    assert paths.config_dir == tmp_path / "runtime" / "config"
    assert paths.agent_db == tmp_path / "runtime" / "state.db"


def test_session_db_owns_every_current_marketing_domain_table(tmp_path):
    db = SessionDB(db_path=tmp_path / "state.db")
    try:
        tables = {
            row[0]
            for row in db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        db.close()

    assert set(LEGACY_MARKETING_TABLES) <= tables


def test_legacy_agent_core_facts_import_once_without_deleting_source(tmp_path):
    legacy_path = tmp_path / "agent_core.db"
    legacy = sqlite3.connect(legacy_path)
    try:
        legacy.executescript(
            """
            CREATE TABLE account_strategy_projects (
                id TEXT PRIMARY KEY,user_id TEXT,account_id TEXT,business_goal TEXT,
                constraints_json TEXT,stage TEXT,status TEXT,created_at TEXT,updated_at TEXT
            );
            CREATE TABLE audience_hypotheses (
                id TEXT PRIMARY KEY,project_id TEXT,user_id TEXT,account_id TEXT,version INTEGER,
                segments_json TEXT,pains_json TEXT,scenarios_json TEXT,exclusions_json TEXT,
                data_gaps_json TEXT,status TEXT,created_at TEXT,confirmed_at TEXT
            );
            CREATE TABLE content_production_plans (
                id TEXT PRIMARY KEY,user_id TEXT,account_id TEXT,kind TEXT,objective TEXT,
                platforms_json TEXT,plan_json TEXT,status TEXT,created_at TEXT,updated_at TEXT
            );
            CREATE TABLE content_assets (
                id TEXT PRIMARY KEY,user_id TEXT,account_id TEXT,platform TEXT,title TEXT,type TEXT,
                status TEXT,parent_id TEXT,experiment_id TEXT,topic TEXT,hook TEXT,version INTEGER,
                content_json TEXT,metrics_json TEXT,created_at TEXT,updated_at TEXT
            );
            CREATE TABLE evidence_records (
                id TEXT PRIMARY KEY,user_id TEXT,account_id TEXT,source_type TEXT,provider TEXT,
                canonical_url TEXT,title TEXT,excerpt TEXT,content_sha256 TEXT,status TEXT,
                verification_level TEXT,captured_at TEXT,session_id TEXT,tool_call_id TEXT,
                metadata_json TEXT,created_at TEXT,updated_at TEXT
            );
            INSERT INTO account_strategy_projects VALUES
                ('strategy-1','default','acct-1','grow','{}','goal_defined','active','t0','t0');
            INSERT INTO audience_hypotheses VALUES
                ('audience-1','strategy-1','default','acct-1',1,'["founders"]','[]','[]','[]','[]','confirmed','t0','t1');
            INSERT INTO content_production_plans VALUES
                ('plan-1','default','acct-1','article_soft','first post','["zhihu"]','{}','planned','t0','t0');
            INSERT INTO content_assets VALUES
                ('asset-1','default','acct-1','zhihu','title','script','draft',NULL,NULL,'topic','hook',1,'{}','{}','t0','t0');
            INSERT INTO evidence_records VALUES
                ('evidence-1','default','acct-1','web','web_extract','https://example.com','source','excerpt','sha','verified','source_integrity','t0','session-1','','{}','t0','t0');
            """
        )
        legacy.commit()
    finally:
        legacy.close()

    for _ in range(2):
        db = SessionDB(db_path=tmp_path / "state.db")
        db.close()

    target = sqlite3.connect(tmp_path / "state.db")
    try:
        assert target.execute("SELECT count(*) FROM account_strategy_projects").fetchone()[0] == 1
        assert target.execute("SELECT count(*) FROM audience_hypotheses").fetchone()[0] == 1
        assert target.execute("SELECT count(*) FROM content_production_plans").fetchone()[0] == 1
        assert target.execute("SELECT count(*) FROM content_assets").fetchone()[0] == 1
        review = target.execute(
            "SELECT human_review_status,human_review_note,human_reviewed_at "
            "FROM content_assets WHERE id='asset-1'"
        ).fetchone()
        assert review == ("pending", "", None)
        assert target.execute("SELECT count(*) FROM evidence_records").fetchone()[0] == 1
        marker = target.execute(
            "SELECT value FROM state_meta WHERE key='marketing_agent_core_import_v1'"
        ).fetchone()[0]
        assert json.loads(marker)["imported"]["content_assets"] == 1
    finally:
        target.close()

    assert legacy_path.is_file()
