from __future__ import annotations

import sqlite3
import time

import pytest

from agent.account_registry import AccountRegistry
from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import (
    AccountLifecycleRepository,
    ContentAssetRepository,
    EvidenceRepository,
)
from agent.marketing.domains.operating_entities import OperatingEntityRepository
from agent.marketing.schema import ENTITY_OWNED_SCOPE_COLUMNS
from hermes_state import SessionDB


def _paths(tmp_path) -> MarketingDataPaths:
    return MarketingDataPaths(
        user_data=tmp_path,
        config_dir=tmp_path / "config",
        agent_db=tmp_path / "state.db",
    )


def _insert_entity(
    db: sqlite3.Connection,
    *,
    entity_id: str,
    user_id: str = "default",
    label: str,
) -> None:
    now = time.time()
    db.execute(
        """INSERT INTO marketing_operating_entities
        (id,user_id,label,status,metadata_json,created_at,updated_at)
        VALUES (?,?,?,'active','{}',?,?)""",
        (entity_id, user_id, label, now, now),
    )


def test_every_historical_business_table_has_a_required_entity_owner(tmp_path):
    paths = _paths(tmp_path)
    SessionDB(db_path=paths.agent_db).close()

    with sqlite3.connect(paths.agent_db) as db:
        existing = {
            str(row[0])
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        core_tables = [
            table for table in ENTITY_OWNED_SCOPE_COLUMNS if table in existing
        ]
        assert len(core_tables) >= 33
        for table in core_tables:
            columns = {
                str(row[1]): row
                for row in db.execute(f'PRAGMA table_info("{table}")').fetchall()
            }
            assert "entity_id" in columns, table
            assert columns["entity_id"][3] == 1, table

        trigger_count = int(
            db.execute(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='trigger' AND name LIKE 'trg_%_entity_owner_a_'"
            ).fetchone()[0]
        )
        assert trigger_count == len(core_tables) * 2


def test_new_account_provenance_write_gets_a_canonical_entity_owner(tmp_path):
    paths = _paths(tmp_path)
    SessionDB(db_path=paths.agent_db).close()

    now = time.time()
    with sqlite3.connect(paths.agent_db) as db:
        db.execute(
            """INSERT INTO marketing_operations
            (id,user_id,account_id,kind,title,visible_text,created_at,updated_at)
            VALUES ('operation-1','default','prospect_default','analysis',
                    '选题分析','分析中',?,?)""",
            (now, now),
        )
        row = db.execute(
            "SELECT entity_id,account_id FROM marketing_operations "
            "WHERE id='operation-1'"
        ).fetchone()
        assert row is not None
        assert str(row[0]).startswith("entity_")
        assert row[1] == "prospect_default"
        assert db.execute(
            """SELECT 1 FROM marketing_operating_entities
            WHERE id=? AND user_id='default' AND status='active'""",
            (row[0],),
        ).fetchone() is not None


def test_optional_legacy_table_is_added_and_backfilled_idempotently(tmp_path):
    paths = _paths(tmp_path)
    SessionDB(db_path=paths.agent_db).close()
    with sqlite3.connect(paths.agent_db) as db:
        db.execute(
            """CREATE TABLE audience_snapshots (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                account_id TEXT NOT NULL
            )"""
        )
        db.execute(
            "INSERT INTO audience_snapshots(id,user_id,account_id) "
            "VALUES ('legacy-audience','default','prospect_default')"
        )

    SessionDB(db_path=paths.agent_db).close()
    SessionDB(db_path=paths.agent_db).close()

    with sqlite3.connect(paths.agent_db) as db:
        columns = {
            str(row[1]): row
            for row in db.execute(
                'PRAGMA table_info("audience_snapshots")'
            ).fetchall()
        }
        assert columns["entity_id"][3] == 1
        row = db.execute(
            "SELECT entity_id,account_id FROM audience_snapshots "
            "WHERE id='legacy-audience'"
        ).fetchone()
        assert row is not None
        assert str(row[0]).startswith("entity_")
        assert row[1] == "prospect_default"


def test_multi_entity_legacy_ambiguity_fails_closed(tmp_path):
    paths = _paths(tmp_path)
    SessionDB(db_path=paths.agent_db).close()
    with sqlite3.connect(paths.agent_db) as db:
        _insert_entity(db, entity_id="entity-alpha", label="品牌 A")
        _insert_entity(db, entity_id="entity-beta", label="品牌 B")
        db.execute(
            """CREATE TABLE audience_snapshots (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                account_id TEXT NOT NULL
            )"""
        )
        db.execute(
            "INSERT INTO audience_snapshots(id,user_id,account_id) "
            "VALUES ('ambiguous','default','prospect_default')"
        )

    with pytest.raises(ValueError, match="cannot safely resolve audience_snapshots"):
        SessionDB(db_path=paths.agent_db)


def test_unassigned_real_account_cannot_write_across_multiple_entities(tmp_path):
    paths = _paths(tmp_path)
    owner = SessionDB(db_path=paths.agent_db)
    registry = AccountRegistry(owner)
    account = registry.register_pending(platform="douyin")
    owner.close()
    with sqlite3.connect(paths.agent_db) as db:
        _insert_entity(db, entity_id="entity-alpha", label="品牌 A")
        _insert_entity(db, entity_id="entity-beta", label="品牌 B")
        now = time.time()
        with pytest.raises(sqlite3.IntegrityError, match="missing or ambiguous"):
            db.execute(
                """INSERT INTO marketing_operations
                (id,user_id,account_id,kind,title,visible_text,created_at,updated_at)
                VALUES ('ambiguous-write','default',?,'analysis','分析','分析中',?,?)""",
                (account["id"], now, now),
            )


def test_two_platform_accounts_share_one_entity_strategy(tmp_path):
    paths = _paths(tmp_path)
    owner = SessionDB(db_path=paths.agent_db)
    registry = AccountRegistry(owner)
    douyin = registry.register_pending(platform="douyin")
    wechat = registry.register_pending(platform="wechat_official")
    owner.close()

    entities = OperatingEntityRepository(paths)
    first_entity = entities.ensure_for_account(
        user_id="default", account_id=douyin["id"]
    )
    entities.link_account(
        entity_id=first_entity["id"],
        user_id="default",
        account_id=wechat["id"],
    )

    lifecycle = AccountLifecycleRepository(paths)
    first = lifecycle.begin_project(
        user_id="default",
        account_id=douyin["id"],
        business_goal="建立统一的 AI 教育内容品牌",
    )
    second = lifecycle.begin_project(
        user_id="default",
        account_id=wechat["id"],
        business_goal="不应生成第二套账号策略",
    )

    assert second["id"] == first["id"]
    assert second["operation"] == "existing"
    assert second["entity_id"] == first_entity["id"]
    assert second["account_id"] == douyin["id"]


def test_linked_platform_plan_can_cite_verified_entity_evidence(tmp_path):
    paths = _paths(tmp_path)
    owner = SessionDB(db_path=paths.agent_db)
    registry = AccountRegistry(owner)
    douyin = registry.register_pending(platform="douyin")
    wechat = registry.register_pending(platform="wechat_official")
    owner.close()

    entities = OperatingEntityRepository(paths)
    entity = entities.ensure_for_account(
        user_id="default", account_id=douyin["id"]
    )
    entities.link_account(
        entity_id=entity["id"],
        user_id="default",
        account_id=wechat["id"],
    )
    evidence = EvidenceRepository(paths).capture_web_extract_result(
        user_id="default",
        account_id=wechat["id"],
        session_id="entity-evidence",
        result={
            "results": [
                {
                    "url": "https://example.com/entity-evidence",
                    "title": "跨平台证据",
                    "content": "同一经营主体的公众号证据可被抖音制作任务引用。",
                }
            ]
        },
    )[0]
    repository = ContentAssetRepository(paths)
    plan = repository.save_production_plan(
        user_id="default",
        account_id=douyin["id"],
        plan={
            "status": "planned",
            "kind": "faceless_video",
            "objective": "制作一条跨平台证据短视频",
            "target_platforms": ["douyin"],
            "constraints": {},
            "audience_model": {"target_audience": "AI 创业者"},
        },
    )

    asset = repository.create_draft(
        user_id="default",
        account_id=douyin["id"],
        title="跨平台证据短视频",
        plan_id=plan["plan_id"],
        asset_type="script",
        platform="douyin",
        production_kind="faceless_video",
        content={"script": "先看公众号历史证据，再设计短视频表达。"},
        evidence_refs=[evidence["id"]],
    )

    assert asset["entity_id"] == entity["id"]
    assert asset["content"]["_provenance_evidence_refs"] == [evidence["id"]]
