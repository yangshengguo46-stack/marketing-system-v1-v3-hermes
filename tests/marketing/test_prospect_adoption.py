from __future__ import annotations

import sqlite3

import pytest

from agent.account_registry import AccountRegistry
from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import (
    AccountLifecycleRepository,
    ContentAssetRepository,
    ContentProductionPolicy,
    EvidenceRepository,
)
from hermes_state import SessionDB


def _runtime(tmp_path):
    state_path = tmp_path / "state.db"
    db = SessionDB(db_path=state_path)
    paths = MarketingDataPaths(tmp_path, tmp_path / "config", state_path)
    return db, paths, AccountRegistry(db)


def _seed_prospect(paths, prospect_id="prospect_default"):
    project = AccountLifecycleRepository(paths).begin_project(
        user_id="default",
        account_id=prospect_id,
        business_goal="找到适合自己的长期内容方向",
    )
    evidence = EvidenceRepository(paths).capture_web_extract_result(
        user_id="default",
        account_id=prospect_id,
        session_id="prospect-session",
        result={
            "results": [
                {
                    "url": "https://example.com/category-research",
                    "title": "Category research",
                    "content": "A bounded public category observation.",
                }
            ]
        },
    )[0]
    plan = ContentProductionPolicy().plan(
        objective="做一条探索方向的 AI 短视频",
        kind="faceless_video",
        platforms=["douyin"],
        audience="希望把 AI 用到工作中的普通人",
        evidence_refs=[evidence["id"]],
        account_context={"account_id": prospect_id, "connected": False},
    )
    assets = ContentAssetRepository(paths)
    saved_plan = assets.save_production_plan(
        user_id="default", account_id=prospect_id, plan=plan
    )
    asset = assets.create_draft(
        user_id="default",
        account_id=prospect_id,
        title="第一次方向探索",
        plan_id=saved_plan["plan_id"],
        asset_type="video",
        platform="douyin",
        production_kind="faceless_video",
        content={"script": "先展示工作结果，再解释方法"},
        evidence_refs=[evidence["id"]],
    )
    return project, evidence, saved_plan, asset


def test_authenticated_account_atomically_adopts_prospect_facts(tmp_path):
    db, paths, registry = _runtime(tmp_path)
    try:
        db.create_session("prospect-session", "tui")
        project, evidence, plan, asset = _seed_prospect(paths)
        pending = registry.register_pending(platform="douyin", label="主账号")
        connected = registry.mark_authenticated(
            pending["id"], platform_user_id="douyin-user-1", username="创作者"
        )

        adopted = registry.adopt_prospect("prospect_default", connected["id"])
        repeated = registry.adopt_prospect("prospect_default", connected["id"])

        assert adopted["operation"] == "adopted"
        assert adopted["moved_counts"]["account_strategy_projects"] == 1
        assert adopted["moved_counts"]["evidence_records"] == 1
        assert adopted["moved_counts"]["content_production_plans"] == 1
        assert adopted["moved_counts"]["content_assets"] == 1
        assert repeated["operation"] == "already_complete"
        assert repeated["successor_session_required"] is True
        assert db.get_session("prospect-session")["marketing_account_id"] == (
            "prospect_default"
        )

        db.create_session(
            "successor-session",
            "tui",
            parent_session_id="prospect-session",
            marketing_user_id="default",
            marketing_account_id=connected["id"],
        )
        assert db.get_session("successor-session")["marketing_account_id"] == connected["id"]

        sql = sqlite3.connect(paths.agent_db)
        try:
            checks = {
                "account_strategy_projects": project["id"],
                "evidence_records": evidence["id"],
                "content_production_plans": plan["plan_id"],
                "content_assets": asset["id"],
            }
            for table, identifier in checks.items():
                row = sql.execute(
                    f'SELECT account_id FROM "{table}" WHERE id=?', (identifier,)
                ).fetchone()
                assert row == (connected["id"],)
        finally:
            sql.close()
    finally:
        db.close()


def test_adoption_requires_authenticated_empty_target(tmp_path):
    db, paths, registry = _runtime(tmp_path)
    try:
        _seed_prospect(paths)
        pending = registry.register_pending(platform="douyin")
        with pytest.raises(ValueError, match="authenticated"):
            registry.adopt_prospect("prospect_default", pending["id"])

        connected = registry.mark_authenticated(pending["id"])
        AccountLifecycleRepository(paths).begin_project(
            user_id="default",
            account_id=connected["id"],
            business_goal="账号已有独立经营模型",
        )
        with pytest.raises(ValueError, match="explicit merge review"):
            registry.adopt_prospect("prospect_default", connected["id"])
    finally:
        db.close()
