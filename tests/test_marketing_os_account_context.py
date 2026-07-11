import json
import sqlite3

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import AccountContextRepository
from agent.marketing.session_scope import build_account_scope_prompt, resolve_account_scope
from hermes_state import SessionDB
from model_tools import get_tool_definitions, handle_function_call
from toolsets import resolve_toolset
from tui_gateway import server


def _seed_product_store(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "accounts.json").write_text(
        json.dumps({
            "accounts": [{
                "id": "acct-1",
                "platform": "douyin",
                "username": "creator",
                "label": "主账号",
                "status": "active",
                "stats": {"followers": 42},
                "cookie": "must-not-cross-the-domain-port",
            }]
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    db_path = tmp_path / "agent-runtime" / "agent_core.db"
    db_path.parent.mkdir()
    with sqlite3.connect(db_path) as db:
        db.executescript(
            """
            CREATE TABLE account_strategy_projects (
                id TEXT PRIMARY KEY,user_id TEXT,account_id TEXT,business_goal TEXT,
                stage TEXT,status TEXT,updated_at TEXT
            );
            CREATE TABLE audience_hypotheses (
                id TEXT PRIMARY KEY,project_id TEXT,user_id TEXT,account_id TEXT,version INTEGER,
                segments_json TEXT,pains_json TEXT,scenarios_json TEXT,exclusions_json TEXT,
                data_gaps_json TEXT,status TEXT,confirmed_at TEXT
            );
            CREATE TABLE positioning_versions (
                id TEXT PRIMARY KEY,project_id TEXT,user_id TEXT,account_id TEXT,version INTEGER,
                positioning_json TEXT,status TEXT
            );
            CREATE TABLE audience_snapshots (
                id TEXT PRIMARY KEY,project_id TEXT,user_id TEXT,account_id TEXT,platform TEXT,
                dimensions_json TEXT,provenance_json TEXT,window_start TEXT,window_end TEXT,captured_at TEXT
            );
            CREATE TABLE benchmark_accounts (
                id TEXT PRIMARY KEY,user_id TEXT,target_account_id TEXT,project_id TEXT,selection_status TEXT
            );
            CREATE TABLE account_experiments (
                id TEXT PRIMARY KEY,user_id TEXT,account_id TEXT,project_id TEXT
            );
            CREATE TABLE memory_candidates (
                id TEXT PRIMARY KEY,user_id TEXT,account_id TEXT,kind TEXT,status TEXT,content TEXT,created_at TEXT
            );
            """
        )
        db.execute(
            "INSERT INTO account_strategy_projects VALUES (?,?,?,?,?,?,?)",
            ("project-1", "default", "acct-1", "经营 AI 教育账号", "positioning_approved", "active", "2026-07-10"),
        )
        db.execute(
            "INSERT INTO audience_hypotheses VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "audience-1", "project-1", "default", "acct-1", 1,
                '[{"label":"想转型的职场人"}]', '["缺少路径"]', '["下班学习"]', '[]',
                '["真实年龄分布"]', "confirmed", "2026-07-10",
            ),
        )
        positioning = {
            "persona": "懂业务的 AI 实践者",
            "tone": "直接、可信",
            "audience_summary": "想用 AI 转型的职场人",
            "content_pillars": ["案例", "方法"],
            "taboos": ["虚构收益"],
            "promise": "提供可复现路径",
        }
        db.execute(
            "INSERT INTO positioning_versions VALUES (?,?,?,?,?,?,?)",
            ("position-1", "project-1", "default", "acct-1", 1, json.dumps(positioning, ensure_ascii=False), "approved"),
        )
        db.execute(
            "INSERT INTO audience_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "snapshot-1", "project-1", "default", "acct-1", "douyin",
                '{"age":{"25-34":0.6}}',
                '{"source_kind":"creator_center_mcp","source_ref":"creator-center","captured_at":"2026-07-10"}',
                None, None, "2026-07-10",
            ),
        )
        db.execute(
            "INSERT INTO benchmark_accounts VALUES (?,?,?,?,?)",
            ("bench-1", "default", "acct-1", "project-1", "selected"),
        )
        db.execute(
            "INSERT INTO memory_candidates VALUES (?,?,?,?,?,?,?)",
            ("memory-1", "default", "acct-1", "account", "verified", '{"field":"goals","value":"稳定获客"}', "2026-07-09"),
        )
    return MarketingDataPaths(user_data=tmp_path, config_dir=config_dir, agent_db=db_path)


def test_account_context_projects_existing_product_truth_without_secrets(tmp_path):
    repository = AccountContextRepository(_seed_product_store(tmp_path))

    accounts = repository.list_accounts()
    context = repository.read(user_id="default", account_id="acct-1")

    assert accounts["total"] == 1
    assert "cookie" not in accounts["accounts"][0]
    assert context["connected"] is True
    assert context["lifecycle"]["stage"] == "positioning_approved"
    assert context["lifecycle"]["audience_hypothesis"]["segments"][0]["label"] == "想转型的职场人"
    assert context["account_dna"]["persona"] == "懂业务的 AI 实践者"
    assert context["account_dna"]["goals"] == ["提供可复现路径"]
    assert context["actual_audience"]["dimensions"]["age"]["25-34"] == 0.6


def test_account_context_is_explicit_when_database_is_not_initialized(tmp_path):
    paths = MarketingDataPaths(
        user_data=tmp_path,
        config_dir=tmp_path / "config",
        agent_db=tmp_path / "agent-runtime" / "agent_core.db",
    )
    repository = AccountContextRepository(paths)

    result = repository.read(user_id="default", account_id="prospect_default")

    assert result["connected"] is False
    assert result["data_state"] == "database_missing"
    assert result["lifecycle"]["next_action"] == "draft_audience_hypothesis"


def test_native_gateway_reads_same_marketing_store(tmp_path, monkeypatch):
    paths = _seed_product_store(tmp_path)
    monkeypatch.setenv("MARKETING_OS_USER_DATA", str(paths.user_data))
    monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(paths.config_dir))
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(paths.agent_db))

    response = server.handle_request({
        "jsonrpc": "2.0",
        "id": "account-context",
        "method": "marketing.account.context",
        "params": {"user_id": "default", "account_id": "acct-1"},
    })

    assert response["result"]["account"]["platform"] == "douyin"
    assert response["result"]["lifecycle"]["business_goal"] == "经营 AI 教育账号"


def test_native_agent_toolset_reads_account_context_without_outer_adapter(tmp_path, monkeypatch):
    paths = _seed_product_store(tmp_path)
    monkeypatch.setenv("MARKETING_OS_USER_DATA", str(paths.user_data))
    monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(paths.config_dir))
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(paths.agent_db))

    definitions = get_tool_definitions(enabled_toolsets=["marketing"], quiet_mode=True)
    names = {item["function"]["name"] for item in definitions}
    result = json.loads(handle_function_call(
        "marketing_read_account_context",
        {"account_id": "acct-1"},
        enabled_toolsets=["marketing"],
    ))

    assert names == {
        "marketing_read_accounts",
        "marketing_read_account_context",
        "marketing_update_account_lifecycle",
        "marketing_plan_content_production",
        "marketing_read_evidence_pack",
        "marketing_read_content_assets",
        "marketing_draft_article_create",
        "marketing_draft_content_create",
        "marketing_prepare_publish",
        "marketing_read_publish_state",
    }
    assert "marketing_read_account_context" in resolve_toolset("hermes-cli")
    assert result["lifecycle"]["stage"] == "positioning_approved"
    assert result["account_dna"]["taboos"] == ["虚构收益"]


def test_session_scope_keeps_only_stable_routing_identity_in_prompt(tmp_path):
    repository = AccountContextRepository(_seed_product_store(tmp_path))

    scope = resolve_account_scope(
        user_id="default",
        account_id="acct-1",
        repository=repository,
    )
    prompt = build_account_scope_prompt(scope)

    assert scope == {
        "user_id": "default",
        "account_id": "acct-1",
        "platform": "douyin",
        "connected": True,
    }
    assert "account_id=acct-1" in prompt
    assert "marketing_read_account_context" in prompt
    assert "经营 AI 教育账号" not in prompt


def test_native_gateway_binds_pristine_session_to_account(tmp_path, monkeypatch):
    paths = _seed_product_store(tmp_path)
    monkeypatch.setenv("MARKETING_OS_USER_DATA", str(paths.user_data))
    monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(paths.config_dir))
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(paths.agent_db))
    state_db = SessionDB(db_path=tmp_path / "state.db")
    monkeypatch.setattr(server, "_db", state_db)
    monkeypatch.setattr(server, "_schedule_agent_build", lambda _sid: None)

    response = server.handle_request({
        "jsonrpc": "2.0",
        "id": "create-scoped-session",
        "method": "session.create",
        "params": {"marketing_account_id": "acct-1"},
    })
    sid = response["result"]["session_id"]
    session = server._sessions[sid]
    try:
        assert response["result"]["info"]["marketing_scope"]["account_id"] == "acct-1"
        server._ensure_session_db_row(session)
        row = state_db.get_session(session["session_key"])
        assert row["marketing_account_id"] == "acct-1"

        bound = server.handle_request({
            "jsonrpc": "2.0",
            "id": "read-scope",
            "method": "marketing.session.account.get",
            "params": {"session_id": sid},
        })
        assert bound["result"]["scope"]["platform"] == "douyin"

        session["history"].append({"role": "user", "content": "hello"})
        rejected = server.handle_request({
            "jsonrpc": "2.0",
            "id": "change-scope",
            "method": "marketing.session.account.set",
            "params": {"session_id": sid, "account_id": "prospect_new"},
        })
        assert rejected["error"]["code"] == 4095
    finally:
        server._close_session_by_id(sid, end_reason="test_cleanup")
        state_db.close()
