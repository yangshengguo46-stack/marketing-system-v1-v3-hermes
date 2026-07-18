import json

import pytest

import hermes_state
from hermes_state import SessionDB
from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import (
    AccountContextRepository,
    AccountLifecycleRepository,
    AccountStrategyRepository,
)
from model_tools import handle_function_call


def _paths(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "accounts.json").write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "id": "acct-1",
                        "platform": "douyin",
                        "label": "主账号",
                        "status": "active",
                    },
                    {
                        "id": "acct-2",
                        "platform": "xiaohongshu",
                        "label": "副账号",
                        "status": "active",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return MarketingDataPaths(
        user_data=tmp_path,
        config_dir=config_dir,
        agent_db=tmp_path / "agent-runtime" / "agent_core.db",
    )


def _bind_env(monkeypatch, paths):
    monkeypatch.setenv("MARKETING_OS_USER_DATA", str(paths.user_data))
    monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(paths.config_dir))
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(paths.agent_db))


def _creator_profile():
    return {
        "identity": {"role": "职场 AI 实践者"},
        "experiences": ["为团队落地 AI 工作流"],
        "skills": ["AI 工具教学"],
        "proof_assets": ["真实项目复盘"],
        "strong_views": ["先解决任务再讲概念"],
        "expression_capabilities": {"camera": "willing"},
        "production_resources": {"hours_per_week": 5},
        "constraints": ["不编造数据"],
        "taboos": ["夸大收益"],
        "motivations": ["建立长期专业信任"],
        "unknowns": ["镜头表现稳定性"],
        "sustainability": {"weekly_topics": 3},
    }


def _market_route():
    return {
        "label": "职场 AI 落地",
        "category": "AI 教育",
        "subcategory": "职场效率",
        "target_audience": "需要完成真实工作的职场人",
        "urgent_problem": "知道 AI 但不会落到工作任务",
        "content_promise": "每条内容解决一个具体工作任务",
        "creator_advantage": "有真实项目经验",
        "platform_candidates": ["douyin", "zhihu"],
        "monetization_paths": ["课程", "咨询"],
        "sustainability": {"source": "日常项目"},
        "competition_hypothesis": "概念讲解多，真实复盘少",
        "risks": ["工具更新快"],
        "data_gaps": ["平台需求规模"],
    }


def _select_route(paths, project):
    strategy = AccountStrategyRepository(paths)
    profile = strategy.draft_creator_profile(
        user_id="default", account_id="acct-1", project_id=project["id"],
        profile=_creator_profile(),
    )
    strategy.confirm_creator_profile(
        user_id="default", account_id="acct-1", project_id=project["id"],
        profile_id=profile["id"], confirmed_by_user=True,
    )
    route = strategy.draft_market_route(
        user_id="default", account_id="acct-1", project_id=project["id"],
        route=_market_route(), confidence=0.8,
    )
    strategy.select_market_route(
        user_id="default", account_id="acct-1", project_id=project["id"],
        route_id=route["id"], confirmed_by_user=True,
    )


def test_native_lifecycle_creates_versioned_audience_truth(tmp_path):
    paths = _paths(tmp_path)
    lifecycle = AccountLifecycleRepository(paths)

    project = lifecycle.begin_project(
        user_id="default",
        account_id="acct-1",
        business_goal="帮助职场人用 AI 提升工作效率",
        constraints={"hours_per_week": 5},
    )
    _select_route(paths, project)
    draft = lifecycle.draft_audience_hypothesis(
        user_id="default",
        account_id="acct-1",
        project_id=project["id"],
        segments=[{"label": "想学 AI 的职场人"}],
        pains=["不知道如何落地"],
        scenarios=["下班后学习"],
        jobs=["完成一份能交付的工作成果"],
        current_alternatives=["收藏教程但不实践"],
        trust_barriers=["担心案例是编的"],
        desired_outcomes=["当天能复用"],
        behavior_signals=["搜索具体工作任务"],
        exclusions=["只看娱乐内容的人"],
        data_gaps=["真实年龄分布"],
    )

    with pytest.raises(ValueError, match="explicit user confirmation"):
        lifecycle.confirm_audience_hypothesis(
            user_id="default",
            account_id="acct-1",
            project_id=project["id"],
            hypothesis_id=draft["id"],
            confirmed_by_user=False,
        )

    confirmed = lifecycle.confirm_audience_hypothesis(
        user_id="default",
        account_id="acct-1",
        project_id=project["id"],
        hypothesis_id=draft["id"],
        confirmed_by_user=True,
    )
    context = AccountContextRepository(paths).read(
        user_id="default", account_id="acct-1"
    )

    assert confirmed["status"] == "confirmed"
    assert context["lifecycle"]["stage"] == "audience_hypothesis_ready"
    assert context["lifecycle"]["next_action"] == "build_benchmark_operating_graph"
    assert context["lifecycle"]["data_gaps"] == ["真实年龄分布"]
    assert context["lifecycle"]["audience_hypothesis"]["jobs"] == [
        "完成一份能交付的工作成果"
    ]


def test_native_tool_writes_only_the_conversation_bound_account(
    tmp_path, monkeypatch
):
    paths = _paths(tmp_path)
    _bind_env(monkeypatch, paths)
    state_path = tmp_path / "state.db"
    monkeypatch.setattr(hermes_state, "DEFAULT_DB_PATH", state_path)
    db = SessionDB(db_path=state_path)
    db.create_session(
        "session-1",
        "tui",
        marketing_user_id="default",
        marketing_account_id="acct-1",
    )
    db.close()

    begun = json.loads(
        handle_function_call(
            "marketing_update_account_lifecycle",
            {
                "action": "begin_project",
                "business_goal": "建立可信的 AI 教育账号",
                "constraints": {"no_fake_metrics": True},
            },
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )
    project_id = begun["result"]["id"]

    drafted_profile = json.loads(
        handle_function_call(
            "marketing_update_account_lifecycle",
            {"action": "draft_creator_profile", "project_id": project_id,
             "profile": _creator_profile()},
            task_id="session-1", session_id="session-1", enabled_toolsets=["marketing"],
        )
    )
    handle_function_call(
        "marketing_update_account_lifecycle",
        {"action": "confirm_creator_profile", "project_id": project_id,
         "profile_id": drafted_profile["result"]["id"], "confirmed_by_user": True},
        task_id="session-1", session_id="session-1", enabled_toolsets=["marketing"],
    )
    drafted_route = json.loads(
        handle_function_call(
            "marketing_update_account_lifecycle",
            {"action": "draft_market_route", "project_id": project_id,
             "route": _market_route(), "confidence": 0.8},
            task_id="session-1", session_id="session-1", enabled_toolsets=["marketing"],
        )
    )
    handle_function_call(
        "marketing_update_account_lifecycle",
        {"action": "select_market_route", "project_id": project_id,
         "route_id": drafted_route["result"]["id"], "confirmed_by_user": True},
        task_id="session-1", session_id="session-1", enabled_toolsets=["marketing"],
    )

    drafted = json.loads(
        handle_function_call(
            "marketing_update_account_lifecycle",
            {
                "action": "draft_audience_hypothesis",
                "project_id": project_id,
                "segments": [{"label": "AI 入门职场人"}],
                "data_gaps": ["真实兴趣分布"],
            },
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )
    hypothesis_id = drafted["result"]["id"]
    confirmed = json.loads(
        handle_function_call(
            "marketing_update_account_lifecycle",
            {
                "action": "confirm_audience_hypothesis",
                "project_id": project_id,
                "hypothesis_id": hypothesis_id,
                "confirmed_by_user": True,
            },
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )
    cross_account = json.loads(
        handle_function_call(
            "marketing_read_account_context",
            {"account_id": "acct-2"},
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )
    unlinked_account = json.loads(
        handle_function_call(
            "marketing_read_account_context",
            {"account_id": "acct-not-in-entity"},
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )

    assert begun["account_context"]["account_id"] == "acct-1"
    assert confirmed["account_context"]["lifecycle"]["stage"] == "audience_hypothesis_ready"
    assert cross_account["entity_id"].startswith("entity_")
    assert cross_account["focus_account_id"] == "acct-2"
    assert set(cross_account["operating_entity"]["account_ids"]) == {
        "acct-1",
        "acct-2",
    }
    assert cross_account["shared_operating_context"]["account_id"] == "acct-1"
    assert "not linked to the bound operating entity" in unlinked_account["error"]
    assert AccountContextRepository(paths).read(
        user_id="default", account_id="acct-2"
    )["lifecycle"]["stage"] == "not_started"
