"""Tests for the standalone API actually spawned by Electron."""

import asyncio
import json
from datetime import datetime
from unittest.mock import patch

import yaml
from fastapi.testclient import TestClient

import server
import marketing_tools.account as account_tools
from agent_core import AgentCoreStore, MemoryKind, TaskStatus


def client_for(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(server, "BUNDLED_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(account_tools, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(account_tools, "ACCOUNTS_DB", tmp_path / "accounts.json")
    monkeypatch.setattr(server, "_agent_service", None)
    (tmp_path / "accounts.json").write_text(json.dumps({"accounts": [], "updated_at": None}))
    (tmp_path / "trending-cache.json").write_text(json.dumps({"status": "no_data", "top_trends": []}))
    (tmp_path / "suggestions-cache.json").write_text(json.dumps({"status": "no_data", "suggestions": []}))
    (tmp_path / "user-profiles.yaml").write_text(yaml.safe_dump({"profiles": [{"id": "default", "category": "科技"}]}))
    return TestClient(server.app)


def test_scheduler_expires_approvals_in_electron_mode(tmp_path, monkeypatch):
    store = AgentCoreStore(tmp_path / "scheduler.db")

    class Service:
        def get_store(self):
            return store

    calls = []
    original = store.expire_stale_approvals

    def recording_expire(timeout_seconds, **kwargs):
        calls.append(timeout_seconds)
        return original(timeout_seconds, **kwargs)

    monkeypatch.setattr(store, "expire_stale_approvals", recording_expire)
    monkeypatch.setattr(server, "_agent_service", Service())
    monkeypatch.setenv("MARKETING_OS_SESSION_ORCHESTRATOR", "electron")
    monkeypatch.setenv("MARKETING_OS_APPROVAL_TIMEOUT_SECONDS", "300")

    result = asyncio.run(server._run_scheduler_cycle())

    assert calls == [300.0]
    assert result == {"expired_approvals": 0, "workflow_started": False}


def test_approval_timeout_configuration_is_bounded(monkeypatch):
    monkeypatch.setenv("MARKETING_OS_APPROVAL_TIMEOUT_SECONDS", "-1")
    assert server._approval_timeout_seconds() == 30.0
    monkeypatch.setenv("MARKETING_OS_APPROVAL_TIMEOUT_SECONDS", "999999")
    assert server._approval_timeout_seconds() == 3600.0
    monkeypatch.setenv("MARKETING_OS_APPROVAL_TIMEOUT_SECONDS", "invalid")
    assert server._approval_timeout_seconds() == 300.0


def test_account_crud_persists(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    created = client.post("/api/plugins/marketing-os/accounts", json={
        "platform": "douyin", "username": "tester", "label": "主号",
    })
    assert created.status_code == 200
    account_id = created.json()["account"]["id"]
    assert client.get("/api/plugins/marketing-os/accounts").json()["total"] == 1
    assert client.delete(f"/api/plugins/marketing-os/accounts/{account_id}").status_code == 200
    assert client.get("/api/plugins/marketing-os/accounts").json()["total"] == 0


def test_mcp_status_is_fail_closed_until_reviewed_servers_are_installed(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    monkeypatch.setattr(server, "_mcp_broker", None)
    status = client.get("/api/plugins/marketing-os/mcp/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload["ready"] is False
    assert {item["name"] for item in payload["servers"]} >= {
        "playwright_browser", "web_fetch", "local_filesystem",
        "sqlite_analytics", "local_transcription",
    }
    assert not any(item["enabled"] for item in payload["servers"])


def test_account_api_keeps_electron_id_and_updates_connection_status(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    account_id = "acct_frontend123"
    created = client.post("/api/plugins/marketing-os/accounts", json={
        "account_id": account_id,
        "platform": "douyin",
        "username": "creator-1",
        "label": "主账号",
    })
    assert created.status_code == 200
    assert created.json()["account"]["id"] == account_id

    disconnected = client.put(
        f"/api/plugins/marketing-os/accounts/{account_id}/status",
        json={"status": "disconnected"},
    )
    assert disconnected.status_code == 200
    assert disconnected.json()["account"]["status"] == "disconnected"

    identity = client.put(
        f"/api/plugins/marketing-os/accounts/{account_id}/identity",
        json={"username": "public-user-1", "label": "真实昵称"},
    )
    assert identity.status_code == 200
    assert identity.json()["account"]["username"] == "public-user-1"
    assert identity.json()["account"]["label"] == "真实昵称"


def test_douyin_login_snapshot_requires_multiple_backend_markers_without_login_ui():
    result = server._classify_douyin_login_snapshot(
        "创作者服务中心\n发布作品\n内容管理\n数据中心"
    )
    assert result["authenticated"] is True
    assert len(result["auth_markers"]) >= 2

    login_shell = server._classify_douyin_login_snapshot(
        "创作者服务中心\n发布作品\n扫码登录\n获取验证码"
    )
    assert login_shell["authenticated"] is False
    assert login_shell["login_markers"]

    weak = server._classify_douyin_login_snapshot("创作者服务中心")
    assert weak["authenticated"] is False


def test_mcp_authenticated_account_is_idempotent_and_account_scoped(tmp_path, monkeypatch):
    client_for(tmp_path, monkeypatch)
    first = server._persist_mcp_authenticated_account("acct_abcdef123456", "douyin")
    second = server._persist_mcp_authenticated_account("acct_abcdef123456", "douyin")
    assert first["id"] == "acct_abcdef123456"
    assert second["id"] == first["id"]
    assert second["status"] == "connected"
    accounts = json.loads((tmp_path / "accounts.json").read_text())["accounts"]
    assert len(accounts) == 1


def test_creator_snapshot_parsers_extract_public_identity_metrics_and_trends():
    account_text = '''
- generic [ref=e147]:
- generic [ref=e149]: 杨炎昭
  - generic [ref=e150]: 抖音号：66867825385
- generic [ref=e155] [cursor=pointer]:
  - text: 粉丝
  - generic [ref=e156]: "4"
- generic [ref=e157]:
  - text: 获赞
  - generic [ref=e158]: "56"
- generic [ref=e1033]: 播放量
  - generic [ref=e1034]: "193"
'''
    parsed = server._parse_creator_account_snapshot(account_text)
    assert parsed["identity"] == {"username": "66867825385", "label": "杨炎昭"}
    assert parsed["stats"] == {"followers": 4, "total_likes": 56, "total_views": 193}

    trend_text = '''
- generic [ref=e993] [cursor=pointer]:
  - generic [ref=e995]: "1"
  - generic [ref=e996]:
    - generic [ref=e997]: "#搞笑"
    - generic [ref=e998]:
      - text: 播放量
      - generic [ref=e999]: 8.82亿
- generic [ref=e1033] [cursor=pointer]:
  - generic [ref=e1035]: "1"
  - generic [ref=e1036]:
    - generic [ref=e1037]: 永远怀念我们亲爱的妹爷
    - generic [ref=e1038]:
      - text: 热度
      - generic [ref=e1039]: 201.91万
'''
    items = server._parse_creator_trend_snapshot(trend_text)
    assert [item["title"] for item in items] == ["#搞笑", "永远怀念我们亲爱的妹爷"]
    assert items[0]["heat_value"] == 882_000_000
    assert items[1]["heat_value"] == 2_019_100


def test_refresh_writes_trend_and_suggestion_caches(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    raw = {"results": {"weibo": {"success": True, "backend_used": "mock", "data": []}}, "backends_used": ["mock"]}
    analysis = {"top_trends": [{"title": "AI 新趋势", "rank": 1, "source_platform": "weibo"}]}
    suggestions = {"suggestions": [{"id": "s1", "trend": "AI 新趋势", "angles": ["角度"]}]}
    with patch("marketing_tools.scraping.aggregate_all_trending", return_value=json.dumps(raw)), \
         patch("marketing_tools.content.analyze_trends", return_value=json.dumps(analysis)), \
         patch("marketing_tools.content.generate_content_suggestions", return_value=json.dumps(suggestions)):
        response = client.post("/api/plugins/marketing-os/trending/refresh", json={"platforms": ["weibo"]})
    assert response.status_code == 200
    assert response.json()["trends_count"] == 1
    assert json.loads((tmp_path / "trending-cache.json").read_text())["status"] == "ok"
    assert len(json.loads((tmp_path / "suggestions-cache.json").read_text())["suggestions"]) == 1


def test_failed_refresh_preserves_last_good_cache(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    previous = {
        "status": "ok", "cached_at": "2026-06-30T08:00:00",
        "top_trends": [{"title": "上一轮有效热点", "source_platform": "weibo"}],
    }
    (tmp_path / "trending-cache.json").write_text(json.dumps(previous))
    failed = {"results": {"weibo": {"success": False, "error": "upstream 503"}}}
    with patch("marketing_tools.scraping.aggregate_all_trending", return_value=json.dumps(failed)):
        response = client.post("/api/plugins/marketing-os/trending/refresh", json={"platforms": ["weibo"]})
    assert response.status_code == 200
    assert response.json()["status"] == "stale"
    cache = json.loads((tmp_path / "trending-cache.json").read_text())
    assert cache["top_trends"] == previous["top_trends"]
    assert cache["refresh_status"] == "failed"


def test_import_electron_session_trends(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    response = client.post("/api/plugins/marketing-os/trending/import", json={
        "platform": "douyin",
        "keyword": "美妆",
        "items": [
            {"rank": 1, "title": "国货美妆新品趋势", "url": "https://www.douyin.com/video/1"},
            {"rank": 2, "title": "夏季护肤成分解析", "url": "https://www.douyin.com/video/2"},
        ],
    })
    assert response.status_code == 200
    assert response.json()["imported_count"] == 2
    cache = json.loads((tmp_path / "trending-cache.json").read_text())
    assert cache["source"] == "playwright_mcp_session"
    assert cache["query"] == "美妆"
    assert len(cache["top_trends"]) == 2
    assert cache["session_overlays"]["douyin"]["items"][0]["title"] == "国货美妆新品趋势"


def test_public_refresh_preserves_mcp_session_overlay_and_other_platforms(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    imported = client.post("/api/plugins/marketing-os/trending/import", json={
        "platform": "douyin", "keyword": "AI",
        "items": [{"rank": 1, "title": "抖音账号个性化热点", "heat_value": 99}],
    })
    assert imported.status_code == 200
    public = {
        "platforms_scraped": ["weibo", "bilibili"],
        "results": {
            "weibo": {"success": True, "backend_used": "public", "data": [{"title": "微博热点"}]},
            "bilibili": {"success": True, "backend_used": "public", "data": [{"title": "B站热点"}]},
        },
    }
    with patch("marketing_tools.scraping.aggregate_all_trending", return_value=json.dumps(public)):
        refreshed = client.post("/api/plugins/marketing-os/trending/refresh", json={"platforms": ["weibo", "bilibili"]})
    assert refreshed.status_code == 200
    cache = json.loads((tmp_path / "trending-cache.json").read_text())
    platforms = {item["source_platform"] for item in cache["top_trends"]}
    assert platforms == {"douyin", "weibo", "bilibili"}
    douyin = next(item for item in cache["top_trends"] if item["source_platform"] == "douyin")
    assert douyin["source_backend"] == "playwright_mcp_creator_center"


def test_batch_import_merges_and_deduplicates_industries(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    response = client.post("/api/plugins/marketing-os/trending/import-batch", json={"collections": [
        {"platform": "douyin", "keyword": "美妆", "items": [{"title": "国货新品", "url": "https://d/1"}]},
        {"platform": "douyin", "keyword": "护肤", "items": [
            {"title": "国货新品", "url": "https://d/1"},
            {"title": "成分趋势", "url": "https://d/2"},
        ]},
    ]})
    assert response.status_code == 200
    assert response.json()["imported_count"] == 2
    assert response.json()["queries"] == ["美妆", "护肤"]


def test_overview_uses_persisted_counts(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    (tmp_path / "accounts.json").write_text(json.dumps({"accounts": [{"stats": {"followers": 20, "follower_growth_today": 3}}]}))
    (tmp_path / "trending-cache.json").write_text(json.dumps({"top_trends": [{}, {}]}))
    (tmp_path / "suggestions-cache.json").write_text(json.dumps({"suggestions": [{}]}))
    data = client.get("/api/plugins/marketing-os/dashboard/overview").json()
    assert data["accounts_connected"] == 1
    assert data["trending_topics_today"] == 2
    assert data["suggestions_generated"] == 1
    assert data["total_followers"] == 20


def test_profile_update_persists(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    response = client.put("/api/plugins/marketing-os/profiles/default", json={"style": "观点型"})
    assert response.status_code == 200
    profiles = yaml.safe_load((tmp_path / "user-profiles.yaml").read_text())["profiles"]
    assert profiles[0]["style"] == "观点型"


def test_publishing_and_analytics_use_real_data(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    created = client.post("/api/plugins/marketing-os/publishing/tasks", json={"title": "真实任务", "platform": "weibo"})
    assert created.status_code == 200
    task_id = created.json()["task"]["id"]
    assert client.get("/api/plugins/marketing-os/publishing/tasks").json()["total"] == 1
    summary = client.get("/api/plugins/marketing-os/analytics/summary").json()
    assert summary["published_count"] == 0
    assert client.delete(f"/api/plugins/marketing-os/publishing/tasks/{task_id}").status_code == 200


def test_workflow_state_persists(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    response = client.put("/api/plugins/marketing-os/workflow/status", json={"enabled": True})
    assert response.status_code == 200
    assert client.get("/api/plugins/marketing-os/workflow/status").json()["enabled"] is True


def test_intelligence_config_report_and_completion(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    config = client.put("/api/plugins/marketing-os/intelligence/config", json={
        "industries": ["美妆", "美妆", "餐饮"], "sync_accounts": False,
    }).json()
    assert config["industries"] == ["美妆", "餐饮"]
    assert config["sync_accounts"] is False
    report = {"status": "partial", "steps": [{"id": "a"}], "errors": [{"scope": "x"}], "summary": {"trends_count": 3}}
    assert client.post("/api/plugins/marketing-os/intelligence/report", json=report).json()["status"] == "partial"
    completed = client.post("/api/plugins/marketing-os/workflow/complete", json={"summary": {"trends_count": 3}}).json()
    assert completed["last_result"]["trends_count"] == 3


def test_workflow_schedule_and_due_calculation(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    response = client.put("/api/plugins/marketing-os/workflow/status", json={"enabled": True, "schedule_time": "09:30"})
    assert response.status_code == 200
    assert response.json()["schedule_time"] == "09:30"
    now = datetime(2026, 6, 28, 10, 0)
    assert server._workflow_due({"enabled": True, "schedule_time": "09:30", "last_run": None}, now)
    assert not server._workflow_due({"enabled": True, "schedule_time": "09:30", "last_run": now.isoformat()}, now)


def test_manual_account_stats_feed_overview(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    created = client.post("/api/plugins/marketing-os/accounts", json={"platform": "bilibili", "username": "123"}).json()
    account_id = created["account"]["id"]
    response = client.put(f"/api/plugins/marketing-os/accounts/{account_id}/stats", json={"followers": 120, "total_views": 5000})
    assert response.status_code == 200
    assert response.json()["account"]["stats"]["followers"] == 120
    assert client.get("/api/plugins/marketing-os/dashboard/overview").json()["total_followers"] == 120
    history = (tmp_path / "monitor_data" / f"{account_id}.jsonl").read_text().splitlines()
    assert len(history) == 1
    assert json.loads(history[0])["source"] == "electron_session"


def test_agent_endpoints_use_async_task_contract(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)

    class FakeService:
        async def create_session(self, user_id, workspace=None):
            return {"session_id": "sess_1", "user_id": user_id, "workspace": workspace}
        async def get_session(self, session_id):
            return {"session_id": session_id, "user_id": "default", "active_task_id": None}
        async def send_message(self, session_id, message, account_id=None):
            return {"task_id": "task_1", "session_id": session_id, "status": "planning"}
        async def get_task_status(self, task_id):
            return {"task_id": task_id, "status": "running", "objective": "目标"}

    monkeypatch.setattr(server, "_agent_service", FakeService())
    session_response = client.post("/agent/sessions", json={"user_id": "user-1", "workspace": "main"})
    assert session_response.status_code == 200
    sent = client.post("/agent/messages", json={"session_id": "sess_1", "message": "你好"})
    assert sent.status_code == 200
    assert sent.json()["task_id"] == "task_1"
    assert client.get("/agent/runs/task_1").json()["status"] == "running"


def test_account_specific_message_auto_binds_the_only_connected_account(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    (tmp_path / "accounts.json").write_text(json.dumps({"accounts": [{
        "id": "acct-only", "platform": "douyin", "status": "connected",
    }]}))
    captured = []

    class FakeService:
        async def send_message(self, session_id, message, account_id=None):
            captured.append(account_id)
            return {"task_id": "task_1", "session_id": session_id, "status": "planning"}

    monkeypatch.setattr(server, "_agent_service", FakeService())
    response = client.post("/agent/messages", json={
        "session_id": "sess_1", "message": "为当前账号整理三个热点选题",
    })
    assert response.status_code == 200
    assert captured == ["acct-only"]


def test_account_specific_message_requires_selection_when_multiple_connected(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    (tmp_path / "accounts.json").write_text(json.dumps({"accounts": [
        {"id": "acct-a", "platform": "douyin", "status": "connected"},
        {"id": "acct-b", "platform": "douyin", "status": "connected"},
    ]}))
    response = client.post("/agent/messages", json={
        "session_id": "sess_1", "message": "分析当前账号的粉丝数据",
    })
    assert response.status_code == 409
    assert "选择" in response.json()["detail"]


def test_tool_account_read_is_filtered_to_task_scope(tmp_path, monkeypatch):
    client_for(tmp_path, monkeypatch)
    (tmp_path / "accounts.json").write_text(json.dumps({"accounts": [
        {"id": "acct-a", "platform": "douyin", "status": "connected"},
        {"id": "acct-b", "platform": "douyin", "status": "connected"},
    ]}))
    scoped = server.get_accounts_for_tool({"account_id": "acct-b"})
    assert scoped["total"] == 1
    assert scoped["accounts"][0]["id"] == "acct-b"


def test_approval_scope_is_bound_to_owning_user_and_session(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    store = AgentCoreStore(tmp_path / "approval.db")
    task = store.create_task(
        session_id="sess-owner", user_id="user-owner", objective="搜索行业热点",
    )
    store.transition_task(task["id"], TaskStatus.RUNNING)
    approval = store.create_approval(
        task_id=task["id"], capability="marketing_trending_search",
        arguments={"platform": "douyin", "keyword": "AI 教育"}, risk_summary="需要登录态搜索",
    )
    grants = []

    class FakeService:
        def get_store(self):
            return store
        async def decide_approval(self, approval_id, approved, reason=None, transition_task=True):
            return store.decide_approval(approval_id, approved, reason, transition_task=transition_task)
        def grant_authorization(self, user_id, capability, scope, session_id=None, arguments=None):
            grants.append((user_id, capability, scope, session_id, arguments))
            return {"scope": scope}

    monkeypatch.setattr(server, "_agent_service", FakeService())
    response = client.post(
        f"/agent/approvals/{approval['id']}/approve",
        json={"scope": "session", "reason": "用户确认"},
    )
    assert response.status_code == 200
    assert response.json()["arguments"] == {"platform": "douyin", "keyword": "AI 教育"}
    assert grants == [(
        "user-owner", "marketing_trending_search", "session", "sess-owner",
        {"platform": "douyin", "keyword": "AI 教育"},
    )]


def test_effect_receipt_resumes_waiting_task(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    store = AgentCoreStore(tmp_path / "effect.db")
    task = store.create_task(session_id="sess-1", user_id="user-1", objective="同步账号")
    store.transition_task(task["id"], TaskStatus.RUNNING)
    approval = store.create_approval(
        task_id=task["id"], capability="marketing_accounts_sync",
        arguments={"platform": "douyin", "username": "user-1"}, risk_summary="同步指标",
    )
    store.decide_approval(approval["id"], True, transition_task=False)
    resumed = []

    class FakeService:
        def get_store(self):
            return store
        async def resume_after_effect(self, task_id):
            resumed.append(task_id)
            return {"task_id": task_id, "status": "running"}

    monkeypatch.setattr(server, "_agent_service", FakeService())
    response = client.post("/agent/effects/submit", json={
        "approval_id": approval["id"],
        "receipt": {"status": "succeeded", "followers": 42},
        "idempotency_key": f"effect_{approval['id']}",
    })
    assert response.status_code == 200
    assert resumed == [task["id"]]
    effect_event = [
        event for event in store.list_events(task["id"])
        if event["event_type"] == "effect.executed"
    ][0]
    assert effect_event["payload"]["approval_id"] == approval["id"]
    assert effect_event["payload"]["capability"] == "marketing_accounts_sync"


def test_rejected_approval_resumes_agent_for_an_alternative(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    store = AgentCoreStore(tmp_path / "reject.db")
    task = store.create_task(session_id="sess-1", user_id="user-1", objective="搜索热点")
    store.transition_task(task["id"], TaskStatus.RUNNING)
    approval = store.create_approval(
        task_id=task["id"], capability="marketing_trending_search",
        arguments={"platform": "douyin", "keyword": "AI"}, risk_summary="登录态搜索",
    )
    resumed = []

    class FakeService:
        async def decide_approval(self, approval_id, approved, reason=None, transition_task=True):
            return store.decide_approval(approval_id, approved, reason, transition_task=transition_task)
        async def resume_after_rejection(self, task_id):
            resumed.append(task_id)
            return {"task_id": task_id, "status": "running"}

    monkeypatch.setattr(server, "_agent_service", FakeService())
    response = client.post(
        f"/agent/approvals/{approval['id']}/reject", json={"reason": "用户拒绝"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert store.get_task(task["id"])["status"] == "waiting_user"
    assert resumed == [task["id"]]


def test_memory_tool_read_is_user_and_account_scoped(tmp_path, monkeypatch):
    client_for(tmp_path, monkeypatch)
    store = AgentCoreStore(tmp_path / "memory-scope.db")
    evidence = [{"source": "conversation"}]
    user_one = store.add_memory_candidate(
        kind=MemoryKind.ACCOUNT, user_id="user-1", account_id="account-a",
        content="属于用户一", evidence=evidence, confidence=0.9,
    )
    user_two = store.add_memory_candidate(
        kind=MemoryKind.ACCOUNT, user_id="user-2", account_id="account-a",
        content="属于用户二", evidence=evidence, confidence=0.9,
    )
    store.update_memory_candidate(user_one["id"], status="verified")
    store.update_memory_candidate(user_two["id"], status="verified")

    class FakeService:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", FakeService())
    memories = server.get_memories({"__user_id": "user-1", "account_id": "account-a"})
    assert [item["content"] for item in memories] == ["属于用户一"]


def test_local_api_token_blocks_untrusted_clients(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    monkeypatch.setattr(server, "API_TOKEN", "desktop-secret")
    assert client.get("/health").status_code == 200
    assert client.get("/api/plugins/marketing-os/accounts").status_code == 401
    assert client.post("/agent/sessions", json={"user_id": "u"}).status_code == 401
    response = client.get(
        "/api/plugins/marketing-os/accounts",
        headers={"X-Marketing-OS-Token": "desktop-secret"},
    )
    assert response.status_code == 200


# ---- query_trending_cache tests ----

def test_query_trending_cache_filters_by_platform(tmp_path, monkeypatch):
    client_for(tmp_path, monkeypatch)
    cache = {
        "status": "ok", "cached_at": "2026-06-30T10:00:00",
        "top_trends": [
            {"title": "AI突破", "source_platform": "douyin", "category": "科技/AI"},
            {"title": "AI新模型", "source_platform": "weibo", "category": "科技/AI"},
            {"title": "娱乐新闻", "source_platform": "weibo", "category": "娱乐/影视"},
        ],
    }
    (tmp_path / "trending-cache.json").write_text(json.dumps(cache))
    result = server.query_trending_cache({"platform": "weibo"})
    assert result["matched"] == 2
    assert all(t["source_platform"] == "weibo" for t in result["top_trends"])


def test_query_trending_cache_matches_title_and_category(tmp_path, monkeypatch):
    client_for(tmp_path, monkeypatch)
    cache = {
        "status": "ok", "cached_at": "2026-06-30T10:00:00",
        "top_trends": [
            {"title": "AI大模型", "source_platform": "douyin", "category": "科技/AI"},
            {"title": "高考分数线", "source_platform": "weibo", "category": "教育"},
            {"title": "股市大涨", "source_platform": "weibo", "category": "财经/商业"},
        ],
    }
    (tmp_path / "trending-cache.json").write_text(json.dumps(cache))
    result = server.query_trending_cache({"query": "AI"})
    assert result["matched"] == 1
    assert result["top_trends"][0]["title"] == "AI大模型"


def test_query_trending_cache_no_match_returns_empty(tmp_path, monkeypatch):
    client_for(tmp_path, monkeypatch)
    cache = {
        "status": "ok", "cached_at": "2026-06-30T10:00:00",
        "top_trends": [
            {"title": "某明星动态", "source_platform": "douyin", "category": "娱乐/影视"},
        ],
    }
    (tmp_path / "trending-cache.json").write_text(json.dumps(cache))
    result = server.query_trending_cache({"query": "AI教育"})
    assert result["matched"] == 0
    assert result["top_trends"] == []


def test_query_trending_cache_limit_is_clamped(tmp_path, monkeypatch):
    client_for(tmp_path, monkeypatch)
    cache = {
        "status": "ok", "cached_at": "2026-06-30T10:00:00",
        "top_trends": [{"title": f"热点{i}", "source_platform": "douyin", "category": "其他"} for i in range(20)],
    }
    (tmp_path / "trending-cache.json").write_text(json.dumps(cache))
    assert len(server.query_trending_cache({"limit": 5})["top_trends"]) == 5
    assert len(server.query_trending_cache({"limit": 50})["top_trends"]) == 20
    assert len(server.query_trending_cache({"limit": 0})["top_trends"]) == 1
    assert len(server.query_trending_cache({"limit": -1})["top_trends"]) == 1


def test_query_trending_cache_stale(tmp_path, monkeypatch):
    client_for(tmp_path, monkeypatch)
    cache = {
        "status": "stale", "cached_at": "2026-06-29T10:00:00",
        "stale": True, "refresh_status": "failed",
        "last_refresh_attempt": "2026-06-30T10:00:00",
        "top_trends": [{"title": "旧数据", "source_platform": "douyin", "category": "科技/AI"}],
    }
    (tmp_path / "trending-cache.json").write_text(json.dumps(cache))
    result = server.query_trending_cache({"query": "旧数据"})
    assert result["status"] == "stale"
    assert result["matched"] == 1


def test_query_trending_cache_no_data(tmp_path, monkeypatch):
    client_for(tmp_path, monkeypatch)
    (tmp_path / "trending-cache.json").write_text(json.dumps({"status": "no_data", "cached_at": None, "top_trends": []}))
    result = server.query_trending_cache({"query": "AI"})
    assert result["status"] == "no_data"
    assert result["top_trends"] == []
    assert result["matched"] == 0


def test_query_trending_cache_preserves_evidence_fields(tmp_path, monkeypatch):
    client_for(tmp_path, monkeypatch)
    cache = {
        "status": "ok", "cached_at": "2026-06-30T10:00:00",
        "top_trends": [{
            "title": "AI突破", "source_platform": "weibo", "source_backend": "hot_topics_api",
            "url": "https://weibo.com/123", "rank": 1, "collected_at": "2026-06-30T09:00:00",
            "category": "科技/AI", "heat_value": 2840000,
        }],
        "source_errors": {"bilibili": "timeout"},
    }
    (tmp_path / "trending-cache.json").write_text(json.dumps(cache))
    result = server.query_trending_cache({"query": "AI"})
    item = result["top_trends"][0]
    assert item["title"] == "AI突破"
    assert item["source_platform"] == "weibo"
    assert item["source_backend"] == "hot_topics_api"
    assert item["url"] == "https://weibo.com/123"
    assert item["rank"] == 1
    assert item["collected_at"] == "2026-06-30T09:00:00"
    assert "source_errors" in result
    assert result["cache_age_seconds"] >= 0
