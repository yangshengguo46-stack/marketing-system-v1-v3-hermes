from __future__ import annotations

import json
import sqlite3

from hermes_state import SessionDB
from tui_gateway import server


def test_gateway_lists_bounded_content_summaries_and_loads_body_on_demand(tmp_path, monkeypatch):
    state_path = tmp_path / "state.db"
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(state_path))
    SessionDB(db_path=state_path).close()
    content = {
        "schema": "marketing.article_bundle.v1",
        "_production_kind": "article_soft",
        "review_status": "ready_for_human_review",
        "parent_draft": {"body_markdown": "很长的正文"},
        "platform_variants": {"zhihu": {"body_markdown": "知乎版本"}},
        "validation": {
            "version": "marketing.article_validation.v2",
            "ready": True,
            "issues": [],
        },
    }
    with sqlite3.connect(state_path) as db:
        db.execute(
            """INSERT INTO content_assets
            (id,user_id,account_id,platform,title,type,status,parent_id,experiment_id,
             topic,hook,version,content_json,metrics_json,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "asset-1",
                "default",
                "acct-1",
                "multi_article",
                "一篇待审核文章",
                "script",
                "review_ready",
                None,
                "experiment-1",
                "AI 教育",
                "先讲一个反常识",
                2,
                json.dumps(content, ensure_ascii=False),
                "{}",
                "2026-07-12T00:00:00+00:00",
                "2026-07-12T00:00:00+00:00",
            ),
        )

    listed = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": "list",
            "method": "marketing.content.assets.list",
            "params": {"account_id": "acct-1"},
        }
    )["result"]
    assert listed["total"] == 1
    summary = listed["assets"][0]
    assert summary["production_kind"] == "article_soft"
    assert summary["review_status"] == "ready_for_human_review"
    assert summary["validation_ready"] is True
    assert summary["target_platforms"] == ["zhihu"]
    assert summary["human_review_status"] == "pending"
    assert "content" not in summary

    opened = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": "get",
            "method": "marketing.content.asset.get",
            "params": {"account_id": "acct-1", "asset_id": "asset-1"},
        }
    )["result"]["asset"]
    assert opened["content"]["parent_draft"]["body_markdown"] == "很长的正文"

    reviewed = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": "review",
            "method": "marketing.content.asset.review",
            "params": {
                "account_id": "acct-1",
                "asset_id": "asset-1",
                "decision": "accepted",
                "confirmed": True,
            },
        }
    )["result"]["asset"]
    assert reviewed["human_review_status"] == "accepted"
    assert reviewed["human_reviewed_at"]


def test_content_gateway_requires_account_scope():
    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": "missing-account",
            "method": "marketing.content.assets.list",
            "params": {},
        }
    )
    assert response["error"]["code"] == -32602


def test_content_gateway_requires_explicit_review_confirmation(tmp_path, monkeypatch):
    state_path = tmp_path / "state.db"
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(state_path))
    SessionDB(db_path=state_path).close()

    response = server.handle_request(
        {
            "jsonrpc": "2.0",
            "id": "review",
            "method": "marketing.content.asset.review",
            "params": {
                "account_id": "acct-1",
                "asset_id": "asset-1",
                "decision": "accepted",
            },
        }
    )
    assert response["error"]["code"] == 4095
