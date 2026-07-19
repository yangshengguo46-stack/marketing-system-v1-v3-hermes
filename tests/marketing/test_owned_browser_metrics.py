from __future__ import annotations

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.intelligence.store import OperatingLoopRepository
from agent.marketing.providers.owned_browser_metrics import collect_owned_browser_metrics
from hermes_state import SessionDB


def _paths(tmp_path):
    state_path = tmp_path / "state.db"
    SessionDB(db_path=state_path).close()
    return MarketingDataPaths(tmp_path, tmp_path / "config", state_path)


def test_owned_douyin_collector_matches_publish_receipt_and_normalizes_metrics(
    tmp_path, monkeypatch
):
    paths = _paths(tmp_path)
    receipt = OperatingLoopRepository(paths).create_receipt(
        source_kind="publish:douyin:test",
        source_id="work-88",
        receipt_type="publish_published",
        user_id="default",
        account_id="acct-1",
        platform="douyin",
        summary={
            "platform_post_id": "work-88",
            "published_url": "https://www.douyin.com/video/work-88",
        },
    )
    monkeypatch.setattr(
        "tools.mcp_tool.execute_marketing_account_browser_tool",
        lambda **kwargs: {
            "schema": "marketing_douyin_owned_portfolio.v1",
            "platform": "douyin",
            "observed_at": "2026-07-19T08:00:00+00:00",
            "account": {"name": "owned"},
            "stats": {},
            "collection": {"complete": True},
            "works": [
                {
                    "source_item_id": "work-88",
                    "source_url": "https://www.douyin.com/video/work-88?from=creator",
                    "metrics": {
                        "view_count": 1200,
                        "like_count": 30,
                        "completion_rate": 0.18,
                        "followers_gained": 4,
                    },
                    "metrics_provenance": {
                        "source": "douyin_creator_center_work_list"
                    },
                }
            ],
        },
    )
    monkeypatch.setattr(
        "agent.marketing.providers.owned_browser_metrics.apply_account_metrics",
        lambda *args, **kwargs: {},
    )

    result = collect_owned_browser_metrics(
        paths,
        {
            "user_id": "default",
            "account_id": "acct-1",
            "platform": "douyin",
            "receipt_id": receipt["id"],
        },
        {"id": "checkpoint-1", "label": "24h", "due_at": "2026-07-19T08:00:00+00:00"},
    )

    assert result["state"] == "observed"
    assert result["metrics"]["views"] == 1200
    assert result["metrics"]["likes"] == 30
    assert result["metrics"]["new_followers"] == 4
    assert result["verification_source"] == "douyin_creator_center_work_list"


def test_owned_metric_collector_waits_then_eliminates_missing_work(tmp_path, monkeypatch):
    paths = _paths(tmp_path)
    receipt = OperatingLoopRepository(paths).create_receipt(
        source_kind="publish:douyin:test",
        source_id="work-missing",
        receipt_type="publish_published",
        user_id="default",
        account_id="acct-1",
        platform="douyin",
        summary={"platform_post_id": "work-missing"},
    )
    monkeypatch.setattr(
        "tools.mcp_tool.execute_marketing_account_browser_tool",
        lambda **kwargs: {
            "schema": "marketing_douyin_owned_portfolio.v1",
            "platform": "douyin",
            "observed_at": "2026-07-19T08:00:00+00:00",
            "account": {},
            "stats": {},
            "collection": {"complete": True},
            "works": [],
        },
    )
    monkeypatch.setattr(
        "agent.marketing.providers.owned_browser_metrics.apply_account_metrics",
        lambda *args, **kwargs: {},
    )
    action = {
        "user_id": "default",
        "account_id": "acct-1",
        "platform": "douyin",
        "receipt_id": receipt["id"],
    }

    waiting = collect_owned_browser_metrics(
        paths, action, {"id": "c1", "label": "24h", "due_at": ""}
    )
    eliminated = collect_owned_browser_metrics(
        paths, action, {"id": "c2", "label": "7d", "due_at": ""}
    )

    assert waiting["state"] == "not_ready"
    assert eliminated["state"] == "unavailable"
