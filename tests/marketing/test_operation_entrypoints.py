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
