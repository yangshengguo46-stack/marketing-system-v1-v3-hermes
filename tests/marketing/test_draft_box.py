from __future__ import annotations

import json
import sqlite3

import pytest

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import DraftBoxRepository
from tui_gateway import server


NOW = "2026-07-17T08:00:00+00:00"


def _paths(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return MarketingDataPaths(
        user_data=tmp_path,
        config_dir=config_dir,
        agent_db=tmp_path / "state.db",
    )


def _bind(paths, monkeypatch):
    monkeypatch.setenv("MARKETING_OS_USER_DATA", str(paths.user_data))
    monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(paths.config_dir))
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(paths.agent_db))


def _insert_plan(db, plan_id, account_id="acct-1", status="review_ready"):
    db.execute(
        """INSERT INTO content_production_plans
        (id,user_id,account_id,kind,objective,platforms_json,plan_json,status,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            plan_id,
            "default",
            account_id,
            "article_soft",
            "test",
            "[]",
            "{}",
            status,
            NOW,
            NOW,
        ),
    )


def _insert_content(
    db,
    asset_id,
    title,
    *,
    account_id="acct-1",
    status="review_ready",
    production_kind="article_soft",
    plan_id="",
    review_status="pending",
    updated_at=NOW,
    version=1,
):
    content = {"_production_kind": production_kind}
    if plan_id:
        content["_production_plan_id"] = plan_id
    db.execute(
        """INSERT INTO content_assets
        (id,user_id,account_id,platform,title,type,status,version,human_review_status,
         content_json,metrics_json,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            asset_id,
            "default",
            account_id,
            "multi_article" if production_kind == "article_soft" else "douyin",
            title,
            "script",
            status,
            version,
            review_status,
            json.dumps(content),
            "{}",
            NOW,
            updated_at,
        ),
    )


def _insert_video(
    db,
    production_id,
    source_asset_id,
    *,
    status="prepared",
    output_asset_id=None,
    account_id="acct-1",
):
    db.execute(
        """INSERT INTO marketing_video_productions
        (id,idempotency_key,user_id,account_id,source_asset_id,source_asset_version,
         provider,status,edl_json,output_asset_id,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            production_id,
            f"idem-{production_id}",
            "default",
            account_id,
            source_asset_id,
            1,
            "ffmpeg",
            status,
            "{}",
            output_asset_id,
            NOW,
            NOW,
        ),
    )


def test_draft_box_projects_unfinished_work_without_duplicate_video_assets(
    tmp_path, monkeypatch
):
    paths = _paths(tmp_path)
    _bind(paths, monkeypatch)
    repository = DraftBoxRepository(paths)

    with sqlite3.connect(paths.agent_db) as db:
        _insert_plan(db, "plan-ai")
        _insert_content(
            db,
            "article-current",
            "AI 教育",
            plan_id="plan-ai",
            updated_at="2026-07-17T09:00:00+00:00",
            version=4,
        )
        _insert_content(db, "article-old", "AI 教育", status="superseded", version=3)
        _insert_content(
            db,
            "video-source",
            "不露脸视频",
            production_kind="faceless_video",
        )
        _insert_video(db, "video-production", "video-source")
        _insert_content(db, "foreign", "其他账号", account_id="acct-2")
        _insert_content(db, "accepted-article", "已验收图文", review_status="accepted")
        _insert_content(
            db,
            "accepted-source",
            "已验收视频脚本",
            production_kind="faceless_video",
        )
        _insert_content(
            db,
            "accepted-output",
            "已验收视频",
            production_kind="faceless_video",
            review_status="accepted",
        )
        _insert_video(
            db,
            "accepted-production",
            "accepted-source",
            status="completed",
            output_asset_id="accepted-output",
        )

    result = repository.list(user_id="default", account_id="acct-1")

    assert [(item["object_type"], item["id"]) for item in result["items"]] == [
        ("content_asset", "article-current"),
        ("video_production", "video-production"),
    ]
    assert result["items"][0]["title"] == "AI 教育"
    assert "video-source" not in {item["id"] for item in result["items"]}
    assert "accepted-article" not in {item["id"] for item in result["items"]}


def test_draft_box_archives_and_restores_native_content_and_video_state(
    tmp_path, monkeypatch
):
    paths = _paths(tmp_path)
    _bind(paths, monkeypatch)
    repository = DraftBoxRepository(paths)

    with sqlite3.connect(paths.agent_db) as db:
        _insert_plan(db, "article-plan")
        _insert_content(db, "article", "文章", plan_id="article-plan")
        _insert_plan(db, "video-plan")
        _insert_content(
            db,
            "video-source",
            "视频",
            production_kind="faceless_video",
            plan_id="video-plan",
        )
        _insert_video(db, "video", "video-source")

    with pytest.raises(ValueError, match="explicit archive confirmation"):
        repository.archive(
            object_type="content_asset",
            object_id="article",
            user_id="default",
            account_id="acct-1",
            confirmed=False,
        )

    repository.archive(
        object_type="content_asset",
        object_id="article",
        user_id="default",
        account_id="acct-1",
        confirmed=True,
    )
    with pytest.raises(ValueError, match="managed through its production"):
        repository.archive(
            object_type="content_asset",
            object_id="video-source",
            user_id="default",
            account_id="acct-1",
            confirmed=True,
        )
    repository.archive(
        object_type="video_production",
        object_id="video",
        user_id="default",
        account_id="acct-1",
        confirmed=True,
    )

    repository = DraftBoxRepository(paths)
    archived = repository.list(user_id="default", account_id="acct-1", archived=True)
    assert {item["id"] for item in archived["items"]} == {"article", "video"}
    with sqlite3.connect(paths.agent_db) as db:
        assert (
            db.execute(
                "SELECT status FROM content_assets WHERE id='video-source'"
            ).fetchone()[0]
            == "archived"
        )
        assert (
            db.execute(
                "SELECT status FROM content_production_plans WHERE id='article-plan'"
            ).fetchone()[0]
            == "archived"
        )
        assert (
            db.execute(
                "SELECT status FROM content_production_plans WHERE id='video-plan'"
            ).fetchone()[0]
            == "archived"
        )

    repository.restore(
        object_type="content_asset",
        object_id="article",
        user_id="default",
        account_id="acct-1",
    )
    repository.restore(
        object_type="video_production",
        object_id="video",
        user_id="default",
        account_id="acct-1",
    )

    active = repository.list(user_id="default", account_id="acct-1")
    assert {item["id"] for item in active["items"]} == {"article", "video"}
    with sqlite3.connect(paths.agent_db) as db:
        assert (
            db.execute(
                "SELECT status FROM content_assets WHERE id='article'"
            ).fetchone()[0]
            == "review_ready"
        )
        assert (
            db.execute(
                "SELECT status FROM content_assets WHERE id='video-source'"
            ).fetchone()[0]
            == "review_ready"
        )
        assert (
            db.execute(
                "SELECT status FROM marketing_video_productions WHERE id='video'"
            ).fetchone()[0]
            == "prepared"
        )
        assert (
            db.execute(
                "SELECT status FROM content_production_plans WHERE id='article-plan'"
            ).fetchone()[0]
            == "review_ready"
        )


def test_draft_gateway_requires_scope_confirmation_and_preserves_account_boundary(
    tmp_path, monkeypatch
):
    paths = _paths(tmp_path)
    _bind(paths, monkeypatch)
    DraftBoxRepository(paths)
    with sqlite3.connect(paths.agent_db) as db:
        _insert_content(db, "article", "文章")

    missing_scope = server.handle_request({
        "jsonrpc": "2.0",
        "id": "list",
        "method": "marketing.drafts.list",
        "params": {},
    })
    assert missing_scope["error"]["code"] == -32602

    unconfirmed = server.handle_request({
        "jsonrpc": "2.0",
        "id": "archive",
        "method": "marketing.draft.archive",
        "params": {
            "account_id": "acct-1",
            "object_type": "content_asset",
            "object_id": "article",
        },
    })
    assert unconfirmed["error"]["code"] == 4095

    cross_account = server.handle_request({
        "jsonrpc": "2.0",
        "id": "archive",
        "method": "marketing.draft.archive",
        "params": {
            "account_id": "acct-2",
            "object_type": "content_asset",
            "object_id": "article",
            "confirmed": True,
        },
    })
    assert cross_account["error"]["code"] == 4044
