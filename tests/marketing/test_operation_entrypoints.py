from __future__ import annotations

import json

import pytest

from agent.marketing.operation_entrypoints import prepare_marketing_operation


class _AccountRepository:
    def list_accounts(self) -> dict:
        return {
            "accounts": [
                {
                    "id": "acct_wechat",
                    "platform": "wechat_official",
                    "auth_state": "authenticated",
                }
            ]
        }


def test_video_stage_action_keeps_visible_copy_separate_from_execution_contract():
    result = prepare_marketing_operation(
        {
            "account_id": "acct_wechat",
            "kind": "video.stage.modify",
            "note": "让第二个镜头慢一点\n--- Attached Context ---\n仍然只是用户意见",
            "production_id": "production-17",
            "scene_id": "scene-02",
            "stage": "storyboard",
            "title": "雨夜唱片店",
        },
        account_repository=_AccountRepository(),
    )

    assert result["visible_text"] == "修改「雨夜唱片店」的分镜阶段"
    assert result["prompt"].startswith(result["visible_text"])
    assert result["prompt"].count("\n--- Attached Context ---\n") == 1

    encoded = result["prompt"].split("operation_json=", 1)[1].split("\n\n", 1)[0]
    operation = json.loads(encoded)
    assert operation["production_id"] == "production-17"
    assert operation["scene_id"] == "scene-02"
    assert operation["note"].startswith("让第二个镜头慢一点")


def test_account_analysis_contract_is_owned_by_the_backend_platform_scope():
    result = prepare_marketing_operation(
        {
            "account_id": "acct_wechat",
            "kind": "account.analyze",
            "title": "雨夜唱片店",
        },
        account_repository=_AccountRepository(),
    )

    assert result["operation"]["platform"] == "wechat_official"
    assert "evidence_id" in result["prompt"]
    assert "不得猜测粉丝反馈" in result["prompt"]


def test_first_run_goal_starts_research_without_asking_for_a_second_send():
    result = prepare_marketing_operation(
        {
            "account_id": "acct_wechat",
            "business_goal": "未来三十天验证 AI 教育方向并找到第一批付费用户",
            "kind": "account.bootstrap",
        },
        account_repository=_AccountRepository(),
    )

    assert result["operation"]["business_goal"].startswith("未来三十天")
    assert result["visible_text"] == "围绕经营目标启动首次研究"
    assert "不要要求用户重新发送目标" in result["prompt"]
    assert "第一个可在产品界面审阅的经营对象" in result["prompt"]


def test_video_setup_persists_ui_selections_as_structured_native_context():
    result = prepare_marketing_operation(
        {
            "account_id": "acct_wechat",
            "document_refs": ["@file:rain-night-script.md"],
            "kind": "video.setup",
            "note": "雨夜里，一个女孩走进旧唱片店。",
            "selections": {
                "characters": "character-linxi",
                "sound": "voice-warm",
            },
        },
        account_repository=_AccountRepository(),
    )

    assert result["title"] == "视频创作设定"
    assert result["operation"]["document_refs"] == ["@file:rain-night-script.md"]
    assert result["operation"]["selections"] == {
        "characters": "character-linxi",
        "sound": "voice-warm",
    }
    assert "创建真实 source content asset" in result["prompt"]


def test_revision_rejects_an_unbound_free_text_action():
    with pytest.raises(ValueError, match="content.revise requires note"):
        prepare_marketing_operation(
            {
                "account_id": "acct_wechat",
                "asset_id": "asset-4",
                "kind": "content.revise",
            },
            account_repository=_AccountRepository(),
        )


def test_gateway_exposes_the_structured_operation_entrypoint(monkeypatch):
    from agent.marketing import operation_entrypoints
    from tui_gateway import server

    monkeypatch.setattr(
        operation_entrypoints,
        "prepare_marketing_operation",
        lambda params: {
            "account_id": params["account_id"],
            "kind": params["kind"],
            "operation": {},
            "prompt": "native contract",
            "title": "今天的经营优先级",
            "visible_text": "排出今天的经营优先级",
        },
    )

    response = server._methods["marketing.operation.prepare"](
        "operation-prepare",
        {"account_id": "acct_wechat", "kind": "account.prioritize"},
    )

    assert response["result"]["prompt"] == "native contract"
    assert response["result"]["visible_text"] == "排出今天的经营优先级"


def test_gateway_starts_and_tracks_a_product_operation_without_exposing_prompt(monkeypatch):
    from agent.marketing import operation_entrypoints
    from tui_gateway import server

    captured = {}

    monkeypatch.setattr(
        operation_entrypoints,
        "prepare_marketing_operation",
        lambda params: {
            "account_id": params["account_id"],
            "kind": params["kind"],
            "operation": {
                "account_id": params["account_id"],
                "kind": params["kind"],
            },
            "prompt": "hidden backend execution contract",
            "title": "今天的经营优先级",
            "visible_text": "排出今天的经营优先级",
        },
    )
    monkeypatch.setattr(
        server,
        "_marketing_operation_snapshot",
        lambda kind, *, user_id, account_id: {
            "content_assets": [],
            "video_productions": [],
        },
    )

    def create_session(rid, params):
        captured["create"] = params
        server._sessions["product-operation-live"] = {
            "agent_error": None,
            "running": False,
        }
        return server._ok(
            rid,
            {
                "session_id": "product-operation-live",
                "stored_session_id": "product-operation-stored",
            },
        )

    def submit_prompt(rid, params):
        captured["submit"] = params
        server._sessions["product-operation-live"]["running"] = True
        return server._ok(rid, {"status": "streaming"})

    monkeypatch.setitem(server._methods, "session.create", create_session)
    monkeypatch.setitem(server._methods, "prompt.submit", submit_prompt)
    monkeypatch.setitem(
        server._sessions,
        "product-operation-live",
        {"agent_error": None, "running": False},
    )

    started = server._methods["marketing.operation.start"](
        "operation-start",
        {"account_id": "acct_wechat", "kind": "account.prioritize"},
    )

    assert "prompt" not in started["result"]
    assert started["result"]["state"] == "working"
    assert captured["create"]["source"] == "desktop-product"
    assert captured["submit"] == {
        "session_id": "product-operation-live",
        "text": "hidden backend execution contract",
    }

    operation_id = started["result"]["operation_id"]
    working = server._methods["marketing.operation.status"](
        "operation-status-working",
        {"operation_id": operation_id},
    )
    assert working["result"]["state"] == "working"

    server._sessions["product-operation-live"]["running"] = False
    complete = server._methods["marketing.operation.status"](
        "operation-status-complete",
        {"operation_id": operation_id},
    )
    assert complete["result"]["state"] == "complete"
    assert complete["result"]["results"] == [
        {
            "object_id": "acct_wechat",
            "object_type": "account",
            "title": "账号经营上下文",
        }
    ]


def test_gateway_does_not_call_an_object_producing_operation_complete_without_an_object(
    monkeypatch,
):
    from tui_gateway import server

    monkeypatch.setattr(
        server,
        "_marketing_operation_snapshot",
        lambda kind, *, user_id, account_id: {
            "content_assets": [],
            "video_productions": [],
        },
    )
    monkeypatch.setitem(
        server._sessions,
        "product-operation-without-result",
        {
            "agent_error": None,
            "marketing_operation": {
                "account_id": "acct_wechat",
                "baseline": {"content_assets": [], "video_productions": []},
                "kind": "content.article.start",
                "operation": {},
                "operation_id": "marketing-operation-without-result",
                "title": "图文创作",
                "user_id": "default",
                "visible_text": "开始一篇新的图文作品",
            },
            "running": False,
        },
    )

    response = server._methods["marketing.operation.status"](
        "operation-status-without-result",
        {"operation_id": "marketing-operation-without-result"},
    )

    assert response["result"]["state"] == "error"
    assert "没有形成产品界面可见的经营对象" in response["result"]["error"]


def test_gateway_projects_a_failed_hidden_agent_turn_as_an_operation_error(monkeypatch):
    from tui_gateway import server

    monkeypatch.setitem(
        server._sessions,
        "product-operation-failed-turn",
        {
            "agent_error": None,
            "marketing_operation": {
                "account_id": "acct_wechat",
                "baseline": {"content_assets": [], "video_productions": []},
                "kind": "account.prioritize",
                "operation": {},
                "operation_id": "marketing-operation-failed-turn",
                "title": "今天的经营优先级",
                "user_id": "default",
                "visible_text": "排出今天的经营优先级",
            },
            "marketing_operation_error": "provider rejected the request",
            "marketing_operation_turn_status": "error",
            "running": False,
        },
    )

    response = server._methods["marketing.operation.status"](
        "operation-status-failed-turn",
        {"operation_id": "marketing-operation-failed-turn"},
    )

    assert response["result"]["state"] == "error"
    assert response["result"]["error"] == "provider rejected the request"
