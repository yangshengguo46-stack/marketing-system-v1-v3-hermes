import json

import hermes_state
import pytest
from hermes_state import SessionDB
from marketing_os.data_paths import MarketingDataPaths
from marketing_os.domains import ContentAssetRepository, ContentProductionPlanner
from model_tools import get_tool_definitions, handle_function_call


def _paths(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "accounts.json").write_text(
        json.dumps(
            {
                "accounts": [
                    {"id": "acct-1", "platform": "douyin", "label": "主账号", "status": "active"},
                    {"id": "acct-2", "platform": "xiaohongshu", "label": "副账号", "status": "active"},
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


def _bind_session(tmp_path, monkeypatch, account_id="acct-1"):
    paths = _paths(tmp_path)
    monkeypatch.setenv("MARKETING_OS_USER_DATA", str(paths.user_data))
    monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(paths.config_dir))
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(paths.agent_db))
    state_path = tmp_path / "state.db"
    monkeypatch.setattr(hermes_state, "DEFAULT_DB_PATH", state_path)
    db = SessionDB(db_path=state_path)
    db.create_session(
        "session-1",
        "tui",
        marketing_user_id="default",
        marketing_account_id=account_id,
    )
    db.close()
    return paths


@pytest.mark.parametrize(
    ("objective", "kind"),
    [
        ("写一篇公众号软文", "article_soft"),
        ("做一条授权素材拼接的不露脸视频", "faceless_video"),
        ("做一条真人数字人高质量视频", "premium_human_video"),
    ],
)
def test_native_planner_selects_three_connected_lanes(objective, kind):
    result = ContentProductionPlanner().plan(objective=objective)

    assert result["kind"] == kind
    assert result["architecture"] == "hermes-native-shared-capability-pool"
    assert "account_context" in result["capabilities"]
    assert "evidence_research" in result["capabilities"]
    assert "copywriting" in result["capabilities"]
    if kind != "article_soft":
        assert "editing_render" in result["capabilities"]


def test_native_content_tools_plan_save_and_resume_in_bound_account(tmp_path, monkeypatch):
    paths = _bind_session(tmp_path, monkeypatch)
    plan_args = {
        "objective": "写一篇面向 AI 入门职场人的公众号软文",
        "platforms": ["wechat_official"],
        "audience": "想提高效率的职场人",
        "evidence_refs": ["source:https://example.com/report"],
    }
    planned = json.loads(
        handle_function_call(
            "marketing_plan_content_production",
            plan_args,
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )
    created = json.loads(
        handle_function_call(
            "marketing_draft_content_create",
            {
                "title": "普通人如何把 AI 变成工作搭档",
                "plan_id": planned["plan_id"],
                "type": "script",
                "platform": "wechat_official",
                "production_kind": "article_soft",
                "topic": "AI 工作流",
                "hook": "不是多学一个工具，而是重做工作方式",
                "content": {
                    "markdown": "# 普通人如何把 AI 变成工作搭档\n\n这是一份可审阅草稿。"
                },
                "evidence_refs": ["source:https://example.com/report"],
            },
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )
    listed = json.loads(
        handle_function_call(
            "marketing_read_content_assets",
            {"status": "draft"},
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )
    replanned = json.loads(
        handle_function_call(
            "marketing_plan_content_production",
            plan_args,
            task_id="session-1",
            session_id="session-1",
            enabled_toolsets=["marketing"],
        )
    )

    assert planned["account_scope"]["account_id"] == "acct-1"
    assert planned["checkpoint_status"] == "planned"
    assert planned["recommended_next_action"].startswith("核对证据引用")
    assert created["account_id"] == "acct-1"
    assert created["content"]["_created_by"] == "hermes-native-marketing"
    assert created["content"]["_production_plan_id"] == planned["plan_id"]
    assert listed["total"] == 1
    assert listed["assets"][0]["id"] == created["id"]
    assert replanned["plan_id"] == planned["plan_id"]
    assert replanned["checkpoint_status"] == "draft_created"
    assert ContentAssetRepository(paths).list(user_id="default", account_id="acct-2")["total"] == 0


def test_content_write_schema_cannot_override_account_scope():
    definitions = get_tool_definitions(enabled_toolsets=["marketing"], quiet_mode=True)
    by_name = {item["function"]["name"]: item["function"] for item in definitions}

    create_properties = by_name["marketing_draft_content_create"]["parameters"]["properties"]
    plan_properties = by_name["marketing_plan_content_production"]["parameters"]["properties"]

    assert "account_id" not in create_properties
    assert "account_id" not in plan_properties
    assert "marketing_read_content_assets" in by_name


def test_content_repository_rejects_reserved_provenance_keys(tmp_path):
    paths = _paths(tmp_path)
    repository = ContentAssetRepository(paths)

    with pytest.raises(ValueError, match="reserved"):
        repository.create_draft(
            user_id="default",
            account_id="acct-1",
            title="bad",
            plan_id="production_plan_missing",
            asset_type="script",
            platform="zhihu",
            production_kind="article_soft",
            content={"_created_by": "model-forged"},
        )


def test_draft_requires_real_plan_in_same_account_scope(tmp_path):
    paths = _paths(tmp_path)
    repository = ContentAssetRepository(paths)

    with pytest.raises(KeyError, match="plan not found"):
        repository.create_draft(
            user_id="default",
            account_id="acct-1",
            title="不能绕过工单",
            plan_id="production_plan_invented",
            asset_type="script",
            platform="zhihu",
            production_kind="article_soft",
            content={"markdown": "正文"},
        )
