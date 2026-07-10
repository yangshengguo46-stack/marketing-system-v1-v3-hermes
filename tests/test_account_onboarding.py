from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
for sub in ("engine", "engine/marketing-os"):
    p = str(ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import server
from agent_core import AccountLifecycleService, AgentCoreStore
from agent_core.account_onboarding import (
    ACCOUNT_ONBOARDING_VERSION,
    build_account_onboarding_plan,
)
from agent_core.tool_manifest import tool_by_name


def test_onboarding_guides_explorer_without_login_or_fake_profile():
    plan = build_account_onboarding_plan({
        "user_id": "ordinary-user",
        "message": "我只是个普通人，还没账号，也不知道怎么变现",
        "constraints": ["不露脸"],
    })

    assert plan["version"] == ACCOUNT_ONBOARDING_VERSION
    assert plan["mode"] == "prospect"
    assert plan["inferred_stage"] == "explorer"
    assert "不用急着登录账号" in plan["opening_message"]
    assert len(plan["next_questions"]) <= 2
    assert plan["account_dna_v0"]["status"] == "provisional"
    assert plan["account_dna_v0"]["confidence"] < 0.7
    assert plan["recommended_next_action"] == "ask_next_question"
    assert [item["window"] for item in plan["first_72_hours"]] == ["Day 0", "Day 1", "Day 2", "Day 3"]
    assert any("不要要求用户先登录" in item for item in plan["guardrails"])


def test_onboarding_returns_audience_draft_payload_when_enough_signal():
    plan = build_account_onboarding_plan({
        "account_id": "acct-ai-teacher",
        "business_goal": "用 AI 教育账号获客卖企业内训课",
        "industry": "AI 教育",
        "resources": ["企业培训案例", "一线交付经验"],
        "audience": ["想用 AI 提效的中小企业老板"],
        "platforms": ["zhihu", "wechat_mp"],
    })

    assert plan["mode"] == "connected_account"
    assert plan["recommended_next_action"] == "draft_audience_hypothesis_for_user_confirmation"
    payload = plan["suggested_audience_draft_payload"]
    assert payload["account_id"] == "acct-ai-teacher"
    assert payload["business_goal"] == "用 AI 教育账号获客卖企业内训课"
    assert payload["segments"][0]["label"] == "想用 AI 提效的中小企业老板"
    assert "marketing_draft_audience_hypothesis" in {step["tool"] for step in plan["tool_sequence"]}


def test_onboarding_reads_lifecycle_but_does_not_create_project(tmp_path):
    store = AgentCoreStore(tmp_path / "onboarding.db")

    plan = build_account_onboarding_plan({
        "user_id": "ordinary-user",
        "message": "我还没账号，想找起号方向",
    }, store=store)

    assert plan["lifecycle"]["stage"] == "not_started"
    assert plan["lifecycle"]["project_id"] is None
    assert AccountLifecycleService(store).get_active_project(
        user_id="ordinary-user", account_id="prospect_ordinary-user"
    ) is None


def test_onboarding_tool_and_server_endpoint_share_contract(tmp_path, monkeypatch):
    store = AgentCoreStore(tmp_path / "server-onboarding.db")

    class Service:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", Service())

    tool = tool_by_name("marketing_read_account_onboarding")
    assert tool is not None
    raw = tool.handler({"user_id": "ordinary-user", "message": "普通人想做账号"})
    assert "Account DNA" in raw

    client = TestClient(server.app)
    response = client.post(
        "/api/plugins/marketing-os/account-onboarding",
        json={"user_id": "ordinary-user", "message": "普通人想做账号"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["account_id"] == "prospect_ordinary-user"
    assert payload["version"] == ACCOUNT_ONBOARDING_VERSION
