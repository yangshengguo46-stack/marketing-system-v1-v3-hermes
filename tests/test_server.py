"""Tests for the standalone API actually spawned by Electron."""

import json
from datetime import datetime
from unittest.mock import patch

import yaml
from fastapi.testclient import TestClient

import server
import tools.account as account_tools


def client_for(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(server, "BUNDLED_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(account_tools, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(account_tools, "ACCOUNTS_DB", tmp_path / "accounts.json")
    (tmp_path / "accounts.json").write_text(json.dumps({"accounts": [], "updated_at": None}))
    (tmp_path / "trending-cache.json").write_text(json.dumps({"status": "no_data", "top_trends": []}))
    (tmp_path / "suggestions-cache.json").write_text(json.dumps({"status": "no_data", "suggestions": []}))
    (tmp_path / "user-profiles.yaml").write_text(yaml.safe_dump({"profiles": [{"id": "default", "category": "科技"}]}))
    return TestClient(server.app)


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


def test_refresh_writes_trend_and_suggestion_caches(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    raw = {"results": {"weibo": {"success": True, "backend_used": "mock", "data": []}}, "backends_used": ["mock"]}
    analysis = {"top_trends": [{"title": "AI 新趋势", "rank": 1, "source_platform": "weibo"}]}
    suggestions = {"suggestions": [{"id": "s1", "trend": "AI 新趋势", "angles": ["角度"]}]}
    with patch("tools.scraping.aggregate_all_trending", return_value=json.dumps(raw)), \
         patch("tools.content.analyze_trends", return_value=json.dumps(analysis)), \
         patch("tools.content.generate_content_suggestions", return_value=json.dumps(suggestions)):
        response = client.post("/api/plugins/marketing-os/trending/refresh", json={"platforms": ["weibo"]})
    assert response.status_code == 200
    assert response.json()["trends_count"] == 1
    assert json.loads((tmp_path / "trending-cache.json").read_text())["status"] == "ok"
    assert len(json.loads((tmp_path / "suggestions-cache.json").read_text())["suggestions"]) == 1


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
    assert cache["source"] == "electron_session"
    assert cache["query"] == "美妆"
    assert len(cache["top_trends"]) == 2


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


def test_assistant_message_uses_read_only_hermes(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    completed = type("Completed", (), {"returncode": 0, "stdout": "Warning: no tools\nsession_id: abc\n这是建议", "stderr": ""})()
    monkeypatch.setattr(server, "_hermes_command", lambda: "/tmp/hermes")
    with patch("subprocess.run", return_value=completed) as run:
        response = client.post("/api/plugins/marketing-os/assistant/message", json={"message": "今天做什么？"})
    assert response.status_code == 200
    assert response.json()["reply"] == "这是建议"
    command = run.call_args.args[0]
    assert "--safe-mode" in command
    assert "__none__" in command
    assert "营销参考数据" in command[3]


def test_assistant_greeting_does_not_trigger_marketing_analysis(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    completed = type("Completed", (), {"returncode": 0, "stdout": "你好！今天想一起做点什么？", "stderr": ""})()
    monkeypatch.setattr(server, "_hermes_command", lambda: "/tmp/hermes")
    with patch("subprocess.run", return_value=completed) as run:
        response = client.post("/api/plugins/marketing-os/assistant/message", json={
            "message": "你好",
            "history": [{"role": "assistant", "content": "之前的回复"}],
        })
    assert response.status_code == 200
    prompt = run.call_args.args[0][3]
    assert "不提供营销数据" in prompt
    assert "当前营销数据" not in prompt
    assert "助手：之前的回复" in prompt


def test_local_api_token_blocks_untrusted_clients(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    monkeypatch.setattr(server, "API_TOKEN", "desktop-secret")
    assert client.get("/health").status_code == 200
    assert client.get("/api/plugins/marketing-os/accounts").status_code == 401
    response = client.get(
        "/api/plugins/marketing-os/accounts",
        headers={"X-Marketing-OS-Token": "desktop-secret"},
    )
    assert response.status_code == 200
