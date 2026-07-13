from __future__ import annotations

import json

import hermes_state
from agent.account_registry import AccountRegistry
from agent.marketing.account_metrics_capture import (
    apply_account_metrics,
    enrich_tool_result_with_account_metrics,
)
from hermes_state import SessionDB


def test_douyin_portfolio_projects_public_and_all_work_counts(tmp_path, monkeypatch):
    state_path = tmp_path / "state.db"
    monkeypatch.setattr(hermes_state, "DEFAULT_DB_PATH", state_path)
    db = SessionDB(db_path=state_path)
    registry = AccountRegistry(db)
    try:
        account = registry.register_pending(platform="douyin")
        db.create_session(
            "session-1",
            "tui",
            marketing_user_id="default",
            marketing_account_id=account["id"],
        )
        payload = {
            "schema": "marketing_douyin_owned_portfolio.v1",
            "platform": "douyin",
            "observed_at": "2026-07-13T12:00:00Z",
            "account": {"name": "杨炎昭"},
            "stats": {
                "followers": 4,
                "following": 2,
                "total_likes": 56,
                "all_work_count": 4,
                "public_work_count": 3,
                "private_work_count": 1,
                "public_view_count": 5366,
                "public_like_count": 55,
            },
            "collection": {"complete": True},
            "works": [],
        }

        enriched = enrich_tool_result_with_account_metrics(
            tool_name="mcp_marketing_browser_browser_collect_douyin_portfolio",
            result=json.dumps(payload, ensure_ascii=False),
            session_id="session-1",
        )

        updated = db.get_marketing_account(account["id"])
        assert updated["auth_state"] == "authenticated"
        assert updated["username"] == "杨炎昭"
        assert updated["stats"]["videos_count"] == 3
        assert updated["stats"]["all_videos_count"] == 4
        assert updated["stats"]["private_videos_count"] == 1
        assert updated["stats"]["total_views"] == 5366
        assert "marketing_account_metrics_projection.v1" in enriched
    finally:
        db.close()


def test_wechat_projection_uses_content_analysis_unique_users(tmp_path, monkeypatch):
    state_path = tmp_path / "state.db"
    monkeypatch.setattr(hermes_state, "DEFAULT_DB_PATH", state_path)
    db = SessionDB(db_path=state_path)
    registry = AccountRegistry(db)
    try:
        account = registry.register_pending(platform="wechat_official")
        projection = apply_account_metrics(
            {
                "schema": "marketing_wechat_official_portfolio.v1",
                "platform": "wechat_official",
                "observed_at": "2026-07-13T12:00:00Z",
                "account": {"name": "示例公众号"},
                "articles": [
                    {
                        "metrics": {"read_users": 14, "share_users": 3, "like_count": 1},
                        "publish_preview": {"read_num": 12, "share_num": 2, "like_num": 0},
                    },
                    {"metrics": {"read_users": 32, "share_users": 2, "like_count": 1}},
                ],
            },
            user_id="default",
            account_id=account["id"],
            session_db=db,
        )

        assert projection["stats"]["read_users"] == 46
        assert projection["stats"]["share_users"] == 5
        assert projection["stats"]["like_count"] == 2
        assert projection["stats"]["articles_count"] == 2
        assert projection["stats"]["metrics_provenance"]["read_unit"] == "unique_users"
    finally:
        db.close()


def test_incomplete_douyin_page_does_not_project_partial_public_totals(tmp_path):
    db = SessionDB(db_path=tmp_path / "state.db")
    registry = AccountRegistry(db)
    try:
        account = registry.register_pending(platform="douyin")
        result = apply_account_metrics(
            {
                "schema": "marketing_douyin_owned_portfolio.v1",
                "platform": "douyin",
                "stats": {
                    "all_work_count": 80,
                    "public_work_count": None,
                    "public_view_count": 1234,
                    "public_like_count": 20,
                },
                "collection": {"complete": False},
                "works": [],
            },
            user_id="default",
            account_id=account["id"],
            session_db=db,
        )

        assert result["stats"]["all_videos_count"] == 80
        assert "videos_count" not in result["stats"]
        assert "total_views" not in result["stats"]
        assert "public_video_likes" not in result["stats"]
    finally:
        db.close()
