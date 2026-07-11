import json

import pytest

import hermes_state
from hermes_state import SessionDB
from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import AccountContextRepository, AccountLifecycleRepository
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


def test_native_lifecycle_creates_versioned_audience_truth(tmp_path):
    paths = _paths(tmp_path)
    lifecycle = AccountLifecycleRepository(paths)

    project = lifecycle.begin_project(
        user_id="default",
        account_id="acct-1",
        business_goal="帮助职场人用 AI 提升工作效率",
        constraints={"hours_per_week": 5},
    )
    draft = lifecycle.draft_audience_hypothesis(
        user_id="default",
        account_id="acct-1",
        project_id=project["id"],
        segments=[{"label": "想学 AI 的职场人"}],
        pains=["不知道如何落地"],
        scenarios=["下班后学习"],
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
    assert context["lifecycle"]["next_action"] == "complete_benchmark_evidence"
    assert context["lifecycle"]["data_gaps"] == ["真实年龄分布"]


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

    assert begun["account_context"]["account_id"] == "acct-1"
    assert confirmed["account_context"]["lifecycle"]["stage"] == "audience_hypothesis_ready"
    assert "does not match the bound conversation" in cross_account["error"]
    assert AccountContextRepository(paths).read(
        user_id="default", account_id="acct-2"
    )["lifecycle"]["stage"] == "not_started"
