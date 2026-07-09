"""Tests for the standalone API actually spawned by Electron."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import yaml
from fastapi.testclient import TestClient

import server
import marketing_tools.account as account_tools
from agent_core import AccountLifecycleService, AgentCoreStore, MemoryKind, TaskStatus


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
    assert result["expired_approvals"] == 0
    assert result["workflow_started"] is False
    assert result["tasks_auto_resumed"] == 0
    assert result["metric_checkpoints"]["due"] == 0


def test_agent_memory_tool_creates_candidate_with_task_evidence(tmp_path, monkeypatch):
    store = AgentCoreStore(tmp_path / "memory.db")
    task = store.create_task(
        session_id="sess-memory", user_id="memory-user",
        objective="remember user preference",
    )

    class Service:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", Service())

    result = server.add_memory({
        "__user_id": "memory-user",
        "__task_id": task["id"],
        "kind": "user",
        "content": "用户不喜欢割韭菜式变现。",
        "confidence": 0.8,
    })

    assert result["status"] in {"verified", "pending"}
    saved = store.list_memories(user_id="memory-user", status=None)
    assert len(saved) == 1
    assert saved[0]["kind"] == MemoryKind.USER.value
    assert saved[0]["content"] == "用户不喜欢割韭菜式变现。"


def test_agent_memory_tool_accepts_key_value_preference_alias(tmp_path, monkeypatch):
    store = AgentCoreStore(tmp_path / "memory-alias.db")
    task = store.create_task(
        session_id="sess-memory", user_id="memory-user",
        objective="remember user preference",
    )

    class Service:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", Service())

    result = server.add_memory({
        "__user_id": "memory-user",
        "__task_id": task["id"],
        "memory_type": "user_preference",
        "key": "变现价值观",
        "value": "讨厌割韭菜式副业课；偏好诚实、可验证、低夸张的变现路径。",
    })

    assert result["status"] in {"verified", "pending"}
    saved = store.list_memories(user_id="memory-user", status=None)
    assert len(saved) == 1
    assert saved[0]["kind"] == MemoryKind.USER.value
    assert "变现价值观" in saved[0]["content"]
    assert "割韭菜" in saved[0]["content"]


def test_agent_content_tool_accepts_string_script_body(tmp_path, monkeypatch):
    store = AgentCoreStore(tmp_path / "content-tool.db")

    class Service:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", Service())

    result = server.create_content_asset({
        "__user_id": "creator-user",
        "account_id": "acct-1",
        "platform": "douyin",
        "type": "short_video_script",
        "title": "测试脚本",
        "content": "开场：今天聊一个真实问题。",
    })

    assert result["status"] == "ok"
    assert result["type"] == "script"
    asset = store.get_content_asset(result["id"])
    assert asset["user_id"] == "creator-user"
    assert asset["type"] == "script"
    assert asset["content"]["body"] == "开场：今天聊一个真实问题。"

    result_from_body = server.create_content_asset({
        "__user_id": "creator-user",
        "type": "script",
        "title": "body 字段脚本",
        "body": "正文从 body 字段进入。",
    })
    asset_from_body = store.get_content_asset(result_from_body["id"])
    assert asset_from_body["content"]["body"] == "正文从 body 字段进入。"


def test_content_asset_endpoint_accepts_body_field(tmp_path, monkeypatch):
    store = AgentCoreStore(tmp_path / "content-endpoint.db")

    class Service:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", Service())

    result = server.create_content_asset_endpoint({
        "user_id": "ui-user",
        "title": "UI body 字段脚本",
        "type": "short_video_script",
        "body": "UI 路径正文。",
    })

    assert result["user_id"] == "ui-user"
    assert result["type"] == "script"
    assert result["content"]["body"] == "UI 路径正文。"


def _published_task_with_due_checkpoint(store: AgentCoreStore, *, receipt: dict | None = None):
    asset = store.create_content_asset(
        user_id="u", account_id="acct", platform="douyin",
        title="测试内容", type="script", content={"body": "x"},
    )
    store.transition_content_asset(asset["id"], "review")
    store.transition_content_asset(asset["id"], "approved")
    task = store.create_publishing_task(asset_id=asset["id"], platform="douyin")
    store.complete_publishing_task(task["id"], effect_id="effect", receipt=receipt or {"status": "ok"})
    checkpoint = store.list_metric_checkpoints(task["id"])[0]
    due = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with store._connect() as db:
        db.execute(
            "UPDATE publishing_metric_checkpoints SET due_at=? WHERE id=?",
            (due, checkpoint["id"]),
        )
    return task, store.list_metric_checkpoints(task["id"])[0]


def test_scheduler_defers_due_metric_checkpoint_without_adapter(tmp_path, monkeypatch):
    store = AgentCoreStore(tmp_path / "scheduler.db")
    task, checkpoint = _published_task_with_due_checkpoint(store)

    class Service:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", Service())
    monkeypatch.setenv("MARKETING_OS_SESSION_ORCHESTRATOR", "electron")

    result = asyncio.run(server._run_scheduler_cycle())

    assert result["metric_checkpoints"]["due"] == 1
    assert result["metric_checkpoints"]["deferred"] == 1
    updated = {item["id"]: item for item in store.list_metric_checkpoints(task["id"])}[checkpoint["id"]]
    assert updated["attempts"] == 1
    assert "adapter_missing" in updated["last_error"]
    assert store.list_metric_snapshots(task["id"]) == []


def test_scheduler_collects_due_metric_checkpoint_from_imported_receipt(tmp_path, monkeypatch):
    store = AgentCoreStore(tmp_path / "scheduler.db")
    task, checkpoint = _published_task_with_due_checkpoint(
        store,
        receipt={
            "status": "ok",
            "metrics": {"views": 123, "likes": 4},
            "metrics_captured_at": "2026-07-07T12:00:00",
        },
    )

    class Service:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", Service())
    monkeypatch.setenv("MARKETING_OS_SESSION_ORCHESTRATOR", "electron")

    result = asyncio.run(server._run_scheduler_cycle())

    assert result["metric_checkpoints"]["due"] == 1
    assert result["metric_checkpoints"]["collected"] == 1
    updated = {item["id"]: item for item in store.list_metric_checkpoints(task["id"])}[checkpoint["id"]]
    assert updated["status"] == "collected"
    snapshots = store.list_metric_snapshots(task["id"])
    assert snapshots[0]["metrics"]["views"] == 123
    assert snapshots[0]["provenance"]["source_kind"] == "imported_report"


def test_scheduler_collects_due_metric_checkpoint_from_creator_center_cache(tmp_path, monkeypatch):
    store = AgentCoreStore(tmp_path / "scheduler.db")
    task, checkpoint = _published_task_with_due_checkpoint(store)
    store.add_video_metric(
        account_id="acct",
        title="测试内容",
        play_count=1000,
        like_count=50,
        comment_count=8,
        share_count=2,
        collect_count=10,
    )

    class Service:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", Service())
    monkeypatch.setenv("MARKETING_OS_SESSION_ORCHESTRATOR", "electron")

    result = asyncio.run(server._run_scheduler_cycle())

    assert result["metric_checkpoints"]["due"] == 1
    assert result["metric_checkpoints"]["collected"] == 1
    updated = {item["id"]: item for item in store.list_metric_checkpoints(task["id"])}[checkpoint["id"]]
    assert updated["status"] == "collected"
    snapshots = store.list_metric_snapshots(task["id"])
    assert snapshots[0]["metrics"]["views"] == 1000
    assert snapshots[0]["metrics"]["engagement_rate"] == 0.07
    assert snapshots[0]["provenance"]["source_kind"] == "creator_center_mcp"


def test_scheduler_refreshes_creator_center_before_metric_match(tmp_path, monkeypatch):
    store = AgentCoreStore(tmp_path / "scheduler.db")
    task, _checkpoint = _published_task_with_due_checkpoint(store)

    async def fake_sync(account_id: str):
        store.add_video_metric(
            account_id=account_id,
            title="测试内容",
            play_count=200,
            like_count=20,
            comment_count=0,
            share_count=0,
            collect_count=0,
        )
        return {"source": "playwright_mcp_creator_center", "videos_count_parsed": 1}

    class Service:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", Service())
    monkeypatch.setattr(server, "_mcp_login_enabled", lambda: True)
    monkeypatch.setattr(server, "mcp_sync_account", fake_sync)
    monkeypatch.setenv("MARKETING_OS_SESSION_ORCHESTRATOR", "electron")

    result = asyncio.run(server._run_scheduler_cycle())

    assert result["metric_checkpoints"]["collected"] == 1
    assert result["metric_checkpoints"]["items"][0]["refreshed"] is True
    snapshots = store.list_metric_snapshots(task["id"])
    assert snapshots[0]["metrics"]["views"] == 200
    assert snapshots[0]["provenance"]["source_kind"] == "creator_center_mcp"


def test_sql_publishing_metrics_endpoint_collects_checkpoint_and_learning(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    store = AgentCoreStore(tmp_path / "publishing-metrics.db")

    class Service:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", Service())

    from agent_core.learning_pipeline import review_content_asset

    asset = store.create_content_asset(
        user_id="default", account_id="acct", platform="douyin",
        title="指标端点测试内容", type="script", content={"body": "x"},
    )
    review_content_asset(
        store,
        asset_id=asset["id"],
        scores={
            "hook": 8, "topic": 8, "emotion": 6, "density": 7,
            "pacing": 7, "viewpoint": 8, "cta": 6,
            "title_bait_risk": 1, "controversy_overload_risk": 1,
        },
        prediction={
            "expected_views": {"low": 100, "mid": 500, "high": 1000},
            "expected_engagement_rate": {"low": 0.02, "mid": 0.05, "high": 0.1},
        },
    )
    store.transition_content_asset(asset["id"], "review")
    store.transition_content_asset(asset["id"], "approved")
    task = store.create_publishing_task(asset_id=asset["id"], platform="douyin")
    store.complete_publishing_task(task["id"], effect_id="effect", receipt={"status": "ok", "platform_post_id": "post-1"})
    checkpoint = store.list_metric_checkpoints(task["id"])[0]

    response = client.post(
        f"/api/plugins/marketing-os/publishing/sql-tasks/{task['id']}/metrics",
        json={
            "checkpoint_id": checkpoint["id"],
            "metrics": {"views": 1200, "likes": 80, "engagement_rate": 0.07},
            "provenance": {"source_kind": "manual_entry", "source_ref": "test"},
        },
    )

    assert response.status_code == 200
    payload = response.json()["task"]
    assert payload["metric_snapshot"]["metrics"]["views"] == 1200
    assert payload["metric_checkpoints"][0]["status"] == "collected"
    assert payload["learning"]["status"] == "reconciled"
    assert payload["learning"]["memory_candidate_id"]
    assert payload["learning"]["learning_candidate_id"]
    assert payload["learning"]["metric_labels"]["labels"]["attention"]["source_metric"] == "views"
    assert payload["learning"]["influence_score"]["version"] == "influenceos-score-v0.1"


def test_influence_score_endpoint_reads_asset_features(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    store = AgentCoreStore(tmp_path / "influence-score.db")

    class Service:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", Service())
    asset = store.create_content_asset(
        user_id="default", account_id="acct", platform="douyin",
        title="预演分数测试内容", type="script", topic="AI 教育",
        content={"body": "开头给冲突，中段给证据，结尾给行动"},
    )
    store.record_content_score(
        asset_id=asset["id"],
        scores={
            "hook": 8, "topic": 7, "emotion": 7, "density": 6,
            "pacing": 6, "viewpoint": 8, "cta": 5,
            "title_bait_risk": 1, "controversy_overload_risk": 1,
        },
    )
    store.create_preflight_record(
        user_id="default", account_id="acct", platform="douyin",
        asset_id=asset["id"], input={"topic": "AI 教育"},
        scores={"platform_fit": 0.7, "audience_fit": 0.65, "evidence_strength": 0.55},
        decision={"go": True},
    )

    response = client.get(
        "/api/plugins/marketing-os/influence/score",
        params={"asset_id": asset["id"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "influenceos-score-v0.1"
    assert payload["feature_refs"]["asset_id"] == asset["id"]
    assert payload["components"]["HumanAttentionKernel"]["source"] == "content_score.hook_emotion_topic"
    assert payload["decision"] in {
        "strong_go",
        "go_with_watchpoints",
        "revise_before_action",
        "do_not_open_or_publish_yet",
    }


def test_preflight_decision_endpoints_share_unified_contract(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    store = AgentCoreStore(tmp_path / "preflight-decision.db")

    class Service:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", Service())
    asset = store.create_content_asset(
        user_id="default", account_id="acct", platform="douyin",
        title="发布决策测试内容", type="script", topic="AI 教育",
        content={"body": "开头冲突，中段证据，结尾行动"},
    )
    store.record_content_score(
        asset_id=asset["id"],
        scores={
            "hook": 8, "topic": 8, "emotion": 7, "density": 7,
            "pacing": 7, "viewpoint": 8, "cta": 6,
            "title_bait_risk": 1, "controversy_overload_risk": 1,
        },
    )
    store.create_preflight_record(
        user_id="default", account_id="acct", platform="douyin",
        asset_id=asset["id"], input={"topic": "AI 教育"},
        scores={"platform_fit": 0.78, "audience_fit": 0.72, "evidence_strength": 0.7, "production_feasibility": 0.76},
        decision={"go": True},
    )

    get_response = client.get(
        "/api/plugins/marketing-os/preflight/decision",
        params={"asset_id": asset["id"], "stage": "publish_review"},
    )
    assert get_response.status_code == 200
    get_payload = get_response.json()
    assert get_payload["preflight_decision"]["version"] == "preflight-decision-v0.1"
    assert get_payload["preflight_decision"]["stage"] == "publish_review"
    assert get_payload["influence_score"]["version"] == "influenceos-score-v0.1"

    post_response = client.post(
        "/api/plugins/marketing-os/preflight/decision",
        json={
            "stage": "production_draft",
            "preflight_scores": {
                "platform_fit": 0.8,
                "production_feasibility": 0.7,
                "evidence_strength": 0.0,
                "audience_fit": 0.0,
            },
            "context": {"selected_lane": "article_soft", "blockers": ["audience_context_missing"]},
        },
    )
    assert post_response.status_code == 200
    post_payload = post_response.json()
    assert post_payload["preflight_decision"]["status"] == "needs_audience_context"
    assert post_payload["preflight_decision"]["go"] is False


def test_weight_candidate_replay_and_decision_endpoints_guard_learning(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    store = AgentCoreStore(tmp_path / "weight-replay.db")

    class Service:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", Service())
    lifecycle = AccountLifecycleService(store)
    project = lifecycle.create_project(
        user_id="default", account_id="acct", business_goal="经营 AI 教育账号",
    )
    for _ in range(3):
        store.create_learning_candidate(
            candidate_type="memory",
            user_id="default",
            account_id="acct",
            platform="douyin",
            proposal={
                "kind": "published_metric_retro",
                "metric_labels": {
                    "labels": {
                        "attention": {"bucket": "high"},
                        "retention": {"bucket": "low"},
                        "action": {"bucket": "zero"},
                    },
                },
                "retro": {"bias_direction": ""},
                "influence_score": {
                    "score": 42.0,
                    "components": {
                        "RetentionDesign": {"value": 0.28},
                        "BusinessValue": {"value": 0.05},
                    },
                },
            },
            confidence=0.7,
        )
    weight = store.create_learning_candidate(
        candidate_type="weight",
        user_id="default",
        account_id="acct",
        platform="douyin",
        proposal={
            "kind": "influence_weight_adjustment",
            "rule_key": "retention_gap_after_attention",
            "support_count": 3,
            "proposed_adjustment": {
                "component": "RetentionDesign",
                "direction": "increase_weight",
                "amount": 0.04,
            },
        },
        confidence=0.8,
    )

    replay = client.get(
        "/api/plugins/marketing-os/learning/weight-replay",
        params={"candidate_id": weight["id"]},
    )
    assert replay.status_code == 200
    assert replay.json()["status"] == "passed"
    assert replay.json()["can_accept"] is True

    accepted = client.post(
        "/api/plugins/marketing-os/learning/weight-decision",
        json={"candidate_id": weight["id"], "decision": "accepted", "reason": "回放通过"},
    )
    assert accepted.status_code == 200
    payload = accepted.json()
    assert payload["status"] == "accepted"
    assert payload["candidate"]["status"] == "accepted"
    assert "no durable weights changed" in payload["guardrail"]
    assert payload["strategy_candidate_id"]
    strategy = lifecycle.get_strategy_candidate(
        user_id="default",
        account_id="acct",
        project_id=project["id"],
        candidate_id=payload["strategy_candidate_id"],
    )
    assert strategy["proposal"]["type"] == "calibrate_influence_weight"


def test_publish_query_verifies_task_from_creator_center_url(tmp_path):
    store = AgentCoreStore(tmp_path / "scheduler.db")
    task, _checkpoint = _published_task_with_due_checkpoint(store)
    # Put the task back into a pre-published state to simulate unknown outcome query.
    with store._connect() as db:
        db.execute(
            "UPDATE publishing_tasks SET status='queued', receipt_json=NULL, published_at=NULL WHERE id=?",
            (task["id"],),
        )
    store.add_video_metric(
        account_id="acct",
        title="测试内容",
        url="https://www.douyin.com/video/7345678901234567890",
        play_count=321,
        like_count=12,
    )

    result = asyncio.run(server._query_publishing_task_receipt(store, task["id"], refresh=False))

    assert result["status"] == "verified"
    assert result["receipt"]["provider"] == "creator_center_mcp"
    assert result["receipt"]["platform_post_id"] == "7345678901234567890"
    assert result["task"]["status"] == "published"
    verified = store.get_publishing_task(task["id"])
    assert verified["receipt"]["published_url"].endswith("/7345678901234567890")


def test_publish_query_does_not_verify_title_only_match(tmp_path):
    store = AgentCoreStore(tmp_path / "scheduler.db")
    task, _checkpoint = _published_task_with_due_checkpoint(store)
    with store._connect() as db:
        db.execute(
            "UPDATE publishing_tasks SET status='queued', receipt_json=NULL, published_at=NULL WHERE id=?",
            (task["id"],),
        )
    store.add_video_metric(
        account_id="acct", title="测试内容", play_count=321, like_count=12,
    )

    result = asyncio.run(server._query_publishing_task_receipt(store, task["id"], refresh=False))

    assert result["status"] == "found_unverified"
    assert "no stable platform URL or post id" in result["reason"]
    assert store.get_publishing_task(task["id"])["status"] == "queued"


def test_publish_query_refreshes_creator_center_before_verification(tmp_path, monkeypatch):
    store = AgentCoreStore(tmp_path / "scheduler.db")
    task, _checkpoint = _published_task_with_due_checkpoint(store)
    with store._connect() as db:
        db.execute(
            "UPDATE publishing_tasks SET status='queued', receipt_json=NULL, published_at=NULL WHERE id=?",
            (task["id"],),
        )

    async def fake_sync(account_id: str):
        store.add_video_metric(
            account_id=account_id,
            title="测试内容",
            url="https://www.douyin.com/video/7456789012345678901",
            play_count=99,
        )
        return {"source": "playwright_mcp_creator_center", "videos_count_parsed": 1}

    monkeypatch.setattr(server, "_mcp_login_enabled", lambda: True)
    monkeypatch.setattr(server, "mcp_sync_account", fake_sync)

    result = asyncio.run(server._query_publishing_task_receipt(store, task["id"], refresh=True))

    assert result["status"] == "verified"
    assert result["receipt"]["platform_post_id"] == "7456789012345678901"
    assert store.get_publishing_task(task["id"])["status"] == "published"


def test_agent_publishing_tasks_recommends_publish_query_for_unverified_task(tmp_path, monkeypatch):
    store = AgentCoreStore(tmp_path / "scheduler.db")
    task, _checkpoint = _published_task_with_due_checkpoint(store)
    with store._connect() as db:
        db.execute(
            "UPDATE publishing_tasks SET receipt_json=? WHERE id=?",
            (json.dumps({"status": "ok"}, ensure_ascii=False), task["id"]),
        )

    class Service:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", Service())

    payload = server.agent_publishing_tasks({})

    row = next(item for item in payload["tasks"] if item["id"] == task["id"])
    assert row["recommended_next_action"] == "marketing_publish_query"


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
- generic [ref=e149]: 测试账号
  - generic [ref=e150]: 抖音号：12345678901
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
    assert parsed["identity"] == {"username": "12345678901", "label": "测试账号"}
    assert {
        key: parsed["stats"][key] for key in ("followers", "total_likes", "total_views")
    } == {"followers": 4, "total_likes": 56, "total_views": 193}

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
    assert [item["title"] for item in items] == ["永远怀念我们亲爱的妹爷"]
    assert items[0]["heat_value"] == 2_019_100


def test_publish_snapshot_summary_exposes_only_readiness_markers():
    text = "账号昵称\n点击上传\n作品描述\n封面\nCookie: secret-value"
    summary = server._summarize_douyin_publish_snapshot(text)
    assert summary == {
        "ready": True,
        "visible_markers": ["点击上传", "作品描述", "封面"],
        "snapshot_chars": len(text),
    }
    assert "账号昵称" not in str(summary)
    assert "secret-value" not in str(summary)


def test_publish_snapshot_summary_is_blocked_without_upload_control():
    summary = server._summarize_douyin_publish_snapshot("发布视频\n标题\n发布设置")
    assert summary["ready"] is False
    assert summary["visible_markers"] == ["发布视频", "标题", "发布设置"]

    image = server._summarize_douyin_publish_snapshot("发布图文\n添加图片\n作品描述", "image")
    assert image["ready"] is True
    assert image["visible_markers"] == ["添加图片", "发布图文", "作品描述"]


def test_refresh_writes_trend_and_suggestion_caches(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    raw = {"results": {"bilibili": {"success": True, "backend_used": "mock", "data": []}}, "backends_used": ["mock"]}
    analysis = {"top_trends": [{"title": "AI 新趋势", "rank": 1, "source_platform": "bilibili"}]}
    suggestions = {"suggestions": [{"id": "s1", "trend": "AI 新趋势", "angles": ["角度"]}]}
    with patch("marketing_tools.scraping.aggregate_all_trending", return_value=json.dumps(raw)), \
         patch("marketing_tools.content.analyze_trends", return_value=json.dumps(analysis)), \
         patch("marketing_tools.content.generate_content_suggestions", return_value=json.dumps(suggestions)):
        response = client.post("/api/plugins/marketing-os/trending/refresh", json={"platforms": ["bilibili"]})
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
    # Product target platforms no longer include weibo; old public weibo
    # inputs are filtered while account-scoped Douyin overlays are preserved.
    assert platforms == {"douyin", "bilibili"}
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
    store = AgentCoreStore(tmp_path / "overview-agent.db")

    class Service:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", Service())
    store.create_content_asset(
        user_id="u", account_id="acct-overview", platform="douyin",
        title="待生产草稿", type="script", content={"body": "草稿"},
    )
    asset = store.create_content_asset(
        user_id="u", account_id="acct-overview", platform="douyin",
        title="已发布内容", type="script", content={"body": "成稿"},
    )
    store.transition_content_asset(asset["id"], "review")
    store.transition_content_asset(asset["id"], "approved")
    task = store.create_publishing_task(asset_id=asset["id"], platform="douyin")
    store.complete_publishing_task(
        task["id"], effect_id="effect-overview",
        receipt={"status": "ok", "platform_post_id": "post-overview"},
    )
    checkpoint = store.list_metric_checkpoints(task["id"])[0]
    store.record_metric_snapshot(
        task["id"], {"views": 1200},
        checkpoint_id=checkpoint["id"],
        provenance={"source_kind": "manual_entry", "source_ref": "overview-test"},
    )
    (tmp_path / "accounts.json").write_text(json.dumps({"accounts": [{"stats": {"followers": 20, "follower_growth_today": 3}}]}))
    (tmp_path / "trending-cache.json").write_text(json.dumps({"top_trends": [
        {"title": "B站热点", "source_platform": "bilibili"},
        {"title": "抖音热点", "source_platform": "douyin"},
    ]}))
    (tmp_path / "suggestions-cache.json").write_text(json.dumps({"suggestions": [
        {"id": "s1", "trend": "B站热点", "trend_source": "bilibili", "angles": ["角度"]},
    ]}))
    data = client.get("/api/plugins/marketing-os/dashboard/overview").json()
    assert data["accounts_connected"] == 1
    assert data["trending_topics_today"] == 2
    assert data["suggestions_generated"] == 1
    assert data["total_followers"] == 20
    assert data["videos_published"] == 1
    assert data["content_pipeline"]["drafts"] == 1
    assert data["content_pipeline"]["published"] == 1
    assert data["content_pipeline"]["latest_draft"]["title"] == "待生产草稿"
    assert data["publishing_receipts"]["total"] == 1
    assert data["publishing_receipts"]["verified"] == 1
    assert data["publishing_receipts"]["metric_checkpoints"]["total"] == 5
    assert data["publishing_receipts"]["metric_checkpoints"]["collected"] == 1


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


def test_native_api_prefix_routes_to_marketing_os_backend(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    response = client.get("/api/marketing-os/dashboard/overview")
    assert response.status_code == 200
    assert "accounts_connected" in response.json()


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


def test_workflow_due_compares_electron_utc_completion_in_local_day():
    local_tz = timezone(timedelta(hours=8))
    now = datetime(2026, 7, 8, 3, 39, tzinfo=local_tz)
    completed_from_electron = "2026-07-07T19:39:15.832Z"

    assert not server._workflow_due({
        "enabled": True,
        "schedule_time": "00:01",
        "last_run": completed_from_electron,
    }, now)


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


def test_pre_account_positioning_conversation_does_not_require_login(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    captured = []

    class FakeService:
        async def send_message(self, session_id, message, account_id=None):
            captured.append(account_id)
            return {"task_id": "task_pre", "session_id": session_id, "status": "planning"}

    monkeypatch.setattr(server, "_agent_service", FakeService())
    response = client.post("/agent/messages", json={
        "session_id": "sess_1",
        "message": "我只是个普通人，还没账号也不知道怎么变现，想通过聊天找到起号方向",
    })
    assert response.status_code == 200
    assert captured == [None]


def test_agent_session_history_lists_and_reconstructs_messages(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    store = AgentCoreStore(tmp_path / "sessions.db")
    session = store.create_or_get_session(user_id="default", workspace="chat:test")
    task = store.create_task(
        session_id=session["id"], user_id="default",
        objective="帮我从普通人开始规划起号方向",
    )
    store.transition_task(task["id"], TaskStatus.RUNNING)
    store.transition_task(task["id"], TaskStatus.COMPLETED)
    store.append_event(task["id"], "task.completed", {"reply": "先问你两个问题：你长期愿意讲什么？"})
    store.set_session_active_task(session["id"], None)

    class FakeService:
        def get_store(self):
            return store

        async def get_session(self, session_id):
            return store.get_session(session_id)

    monkeypatch.setattr(server, "_agent_service", FakeService())

    listed = client.get("/agent/sessions")
    assert listed.status_code == 200
    items = listed.json()["sessions"]
    assert items[0]["session_id"] == session["id"]
    assert items[0]["title"].startswith("帮我从普通人开始")
    assert items[0]["task_count"] == 1

    messages = client.get(f"/agent/sessions/{session['id']}/messages")
    assert messages.status_code == 200
    assert messages.json()["messages"] == [
        {
            "role": "user",
            "content": "帮我从普通人开始规划起号方向",
            "task_id": task["id"],
            "created_at": task["created_at"],
        },
        {
            "role": "assistant",
            "content": "先问你两个问题：你长期愿意讲什么？",
            "task_id": task["id"],
            "created_at": messages.json()["messages"][1]["created_at"],
        },
    ]


def test_unbound_lifecycle_uses_stable_prospect_scope(tmp_path, monkeypatch):
    client_for(tmp_path, monkeypatch)
    store = AgentCoreStore(tmp_path / "prospect.db")

    class FakeService:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", FakeService())
    empty = server.account_lifecycle_status({"user_id": "ordinary-user"})
    assert empty["stage"] == "not_started"
    drafted = server.draft_audience_hypothesis({
        "user_id": "ordinary-user", "business_goal": "探索适合长期经营的个人账号方向",
        "segments": [{"label": "待通过对话验证的人群"}],
        "data_gaps": ["industry_unknown", "monetization_unknown"],
    })
    assert drafted["project"]["account_id"] == "prospect_ordinary-user"
    current = server.account_lifecycle_status({"user_id": "ordinary-user"})
    assert current["project_id"] == drafted["project"]["id"]


def test_prospect_strategy_can_bind_to_connected_account_via_api(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    store = AgentCoreStore(tmp_path / "prospect-bind-api.db")

    class FakeService:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", FakeService())
    drafted = server.draft_audience_hypothesis({
        "user_id": "default", "business_goal": "找到长期内容方向",
        "segments": [{"label": "初次创业者"}],
    })
    project_id = drafted["project"]["id"]
    response = client.post(
        "/api/plugins/marketing-os/accounts/acct-connected/lifecycle/bind-prospect",
        json={"project_id": project_id},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "bound"
    assert response.json()["account_id"] == "acct-connected"
    current = client.get("/api/plugins/marketing-os/accounts/acct-connected/lifecycle")
    assert current.status_code == 200
    assert current.json()["project_id"] == project_id


def test_prospect_strategy_api_refuses_overwriting_existing_account_project(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    store = AgentCoreStore(tmp_path / "prospect-bind-conflict.db")
    lifecycle = AccountLifecycleService(store)
    prospect = lifecycle.create_project(
        user_id="default", account_id="prospect_default", business_goal="探索方向",
    )
    lifecycle.create_project(
        user_id="default", account_id="acct-connected", business_goal="已有项目",
    )

    class FakeService:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", FakeService())
    response = client.post(
        "/api/plugins/marketing-os/accounts/acct-connected/lifecycle/bind-prospect",
        json={"project_id": prospect["id"]},
    )
    assert response.status_code == 409
    assert lifecycle.get_active_project(
        user_id="default", account_id="prospect_default",
    )["id"] == prospect["id"]


def test_benchmark_discovery_persists_candidate_and_source_samples(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    store = AgentCoreStore(tmp_path / "benchmark-discovery.db")
    lifecycle = AccountLifecycleService(store)
    project = lifecycle.create_project(
        user_id="default", account_id="acct-target", business_goal="AI 教育获客",
    )
    draft = lifecycle.draft_audience_hypothesis(
        user_id="default", account_id="acct-target", project_id=project["id"],
        segments=[{"label": "想学习 AI 的普通人"}],
    )
    lifecycle.confirm_audience_hypothesis(
        user_id="default", account_id="acct-target", project_id=project["id"],
        hypothesis_id=draft["id"],
    )
    (tmp_path / "trending-cache.json").write_text(json.dumps({
        "status": "ok", "cached_at": "2026-07-04T10:00:00",
        "top_trends": [{
            "source_platform": "bilibili", "source_backend": "bilibili_public",
            "title": "普通人如何学习 AI 教育", "url": "https://www.bilibili.com/video/BV1",
            "video_id": "BV1", "collected_at": "2026-07-04T10:00:00+00:00",
            "author": {"id": "42", "name": "AI 学习者", "profile_url": "https://space.bilibili.com/42"},
            "metrics": {"views": 1000},
        }],
    }))

    class FakeService:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", FakeService())
    response = client.post(
        "/api/plugins/marketing-os/accounts/acct-target/benchmarks/discover",
        json={"project_id": project["id"], "query": "AI 教育", "platform": "bilibili"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate_count"] == 1
    assert payload["candidates"][0]["selection_status"] == "candidate"
    assert payload["candidates"][0]["samples_imported"] == 1
    research = lifecycle.list_benchmark_accounts(
        user_id="default", account_id="acct-target", project_id=project["id"],
    )
    assert research[0]["account_handle"] == "42"
    assert research[0]["selection_status"] == "candidate"
    retry = client.post(
        "/api/plugins/marketing-os/accounts/acct-target/benchmarks/discover",
        json={"project_id": project["id"], "query": "AI 教育", "platform": "bilibili"},
    )
    assert retry.status_code == 200
    assert retry.json()["candidates"][0]["samples_imported"] == 0
    assert len(lifecycle.list_benchmark_accounts(
        user_id="default", account_id="acct-target", project_id=project["id"],
    )) == 1


def test_benchmark_discovery_does_not_resurrect_rejected_candidate(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    store = AgentCoreStore(tmp_path / "benchmark-rejected.db")
    lifecycle = AccountLifecycleService(store)
    project = lifecycle.create_project(
        user_id="default", account_id="acct-target", business_goal="AI 教育获客",
    )
    rejected = lifecycle.add_benchmark_account(
        user_id="default", account_id="acct-target", project_id=project["id"],
        platform="bilibili", account_handle="42", account_name="不合适的账号",
        relation="adjacent", selection_reason="待判断",
        source_ref="https://space.bilibili.com/42", selection_status="candidate",
    )
    lifecycle.decide_benchmark_account(
        user_id="default", account_id="acct-target", project_id=project["id"],
        benchmark_account_id=rejected["id"], decision="rejected",
    )
    (tmp_path / "trending-cache.json").write_text(json.dumps({
        "status": "ok", "cached_at": "2026-07-04T10:00:00",
        "top_trends": [{
            "source_platform": "bilibili", "source_backend": "bilibili_public",
            "title": "AI 教育", "url": "https://www.bilibili.com/video/BV1",
            "collected_at": "2026-07-04T10:00:00+00:00",
            "author": {"id": "42", "name": "不合适的账号"},
        }],
    }))

    class FakeService:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", FakeService())
    response = client.post(
        "/api/plugins/marketing-os/accounts/acct-target/benchmarks/discover",
        json={"project_id": project["id"], "query": "AI 教育", "platform": "bilibili"},
    )
    assert response.status_code == 200
    assert response.json()["candidate_count"] == 0
    assert response.json()["suppressed_rejected"] == 1


def test_lifecycle_e2e_from_prospect_to_first_experiment_survives_restart(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    store = AgentCoreStore(tmp_path / "lifecycle-e2e.db")

    class Service:
        def __init__(self, current_store):
            self.current_store = current_store

        def get_store(self):
            return self.current_store

    monkeypatch.setattr(server, "_agent_service", Service(store))

    drafted = client.post(
        "/api/plugins/marketing-os/accounts/prospect_default/audience-hypotheses",
        json={
            "business_goal": "帮助普通人学会 AI 并形成咨询线索",
            "segments": [{"label": "想学习 AI 的普通人"}],
            "pains": ["信息太杂，不知道从哪里开始"],
            "scenarios": ["下班后学习并尝试副业"],
            "exclusions": ["只追逐工具新闻的人"],
        },
    ).json()
    project_id = drafted["project"]["id"]
    hypothesis_id = drafted["draft"]["id"]
    confirmed = client.post(
        f"/api/plugins/marketing-os/accounts/prospect_default/audience-hypotheses/{hypothesis_id}/confirm",
        json={"project_id": project_id},
    )
    assert confirmed.status_code == 200

    bound = client.post(
        "/api/plugins/marketing-os/accounts/acct-real/lifecycle/bind-prospect",
        json={"project_id": project_id},
    )
    assert bound.status_code == 200
    retry = client.post(
        "/api/plugins/marketing-os/accounts/acct-real/lifecycle/bind-prospect",
        json={"project_id": project_id},
    )
    assert retry.json()["status"] == "already_bound"

    evidence = []
    for author_id, author_name in (("101", "AI 实战派"), ("202", "反面案例号")):
        for index in range(5):
            evidence.append({
                "source_platform": "bilibili", "source_backend": "bilibili_public",
                "title": f"AI 教育普通人案例 {author_id}-{index}",
                "url": f"https://www.bilibili.com/video/BV{author_id}{index}",
                "video_id": f"BV{author_id}{index}",
                "collected_at": "2026-07-04T10:00:00+00:00",
                "author": {
                    "id": author_id, "name": author_name,
                    "profile_url": f"https://space.bilibili.com/{author_id}",
                },
                "metrics": {"views": 1000 + index},
            })
    (tmp_path / "trending-cache.json").write_text(json.dumps({
        "status": "ok", "cached_at": "2026-07-04T10:00:00", "top_trends": evidence,
    }))
    discovered = client.post(
        "/api/plugins/marketing-os/accounts/acct-real/benchmarks/discover",
        json={"project_id": project_id, "query": "AI 教育", "platform": "bilibili"},
    ).json()
    assert discovered["candidate_count"] == 2
    by_handle = {item["account_handle"]: item for item in discovered["candidates"]}
    for handle, relation in (("101", "direct"), ("202", "negative")):
        decision = client.post(
            f"/api/plugins/marketing-os/accounts/acct-real/benchmarks/{by_handle[handle]['benchmark_account_id']}/decision",
            json={"project_id": project_id, "decision": "selected", "relation": relation},
        )
        assert decision.status_code == 200
        assert decision.json()["relation"] == relation

    evidence_refs = []
    direct_id = by_handle["101"]["benchmark_account_id"]
    for dimension in ("audience", "positioning", "content_pillar", "format", "engagement"):
        observation = client.post(
            f"/api/plugins/marketing-os/accounts/acct-real/benchmarks/{direct_id}/observations",
            json={
                "project_id": project_id, "dimension": dimension,
                "value": {"finding": f"{dimension} 的可验证观察"},
                "provenance": {
                    "source_kind": "public_web",
                    "source_ref": f"https://www.bilibili.com/video/evidence-{dimension}",
                    "captured_at": "2026-07-04T10:00:00+00:00",
                },
                "confidence": 0.8,
            },
        )
        assert observation.status_code == 200
        evidence_refs.append(observation.json()["id"])

    ready = client.get(
        f"/api/plugins/marketing-os/accounts/acct-real/lifecycle"
    ).json()
    assert ready["benchmark_readiness"]["ready"] is True
    positioning = client.post(
        "/api/plugins/marketing-os/accounts/acct-real/positioning",
        json={
            "project_id": project_id,
            "positioning": {
                "promise": "让普通人能执行地学习 AI",
                "differentiation": "只讲经过实际验证的工作流",
                "persona": "一起动手的 AI 实践者",
                "content_pillars": ["基础认知", "实战案例", "失败复盘"],
                "tone": ["真诚", "具体"], "taboos": ["虚假收益承诺"],
            },
            "evidence_refs": evidence_refs,
        },
    )
    assert positioning.status_code == 200
    positioning_id = positioning.json()["id"]
    approved = client.post(
        f"/api/plugins/marketing-os/accounts/acct-real/positioning/{positioning_id}/approve",
        json={"project_id": project_id},
    )
    assert approved.status_code == 200

    experiment = client.post(
        "/api/plugins/marketing-os/accounts/acct-real/experiments",
        json={
            "project_id": project_id,
            "hypothesis": "案例型开头比工具新闻更能吸引目标用户",
            "variable": {"hook_type": "case_first"},
            "prediction": {"completion_rate": {"low": 0.2, "mid": 0.3, "high": 0.4}},
            "success_criteria": {"completion_rate_gte": 0.3},
        },
    )
    assert experiment.status_code == 200
    experiment_id = experiment.json()["id"]
    asset = client.post(
        "/api/plugins/marketing-os/content/assets",
        json={
            "title": "普通人第一次用 AI 的真实失败案例", "type": "script",
            "platform": "douyin", "account_id": "acct-real", "content": {"script": "draft"},
        },
    )
    assert asset.status_code == 200
    attached = client.post(
        f"/api/plugins/marketing-os/accounts/acct-real/experiments/{experiment_id}/assets",
        json={"project_id": project_id, "asset_id": asset.json()["id"]},
    )
    assert attached.status_code == 200
    assert attached.json()["status"] == "running"

    reopened = AgentCoreStore(tmp_path / "lifecycle-e2e.db")
    monkeypatch.setattr(server, "_agent_service", Service(reopened))
    after_restart = client.get("/api/plugins/marketing-os/accounts/acct-real/lifecycle").json()
    assert after_restart["project_id"] == project_id
    assert after_restart["stage"] == "experiment_running"
    assert client.get("/api/plugins/marketing-os/accounts/acct-other/lifecycle").json()["stage"] == "not_started"


def test_benchmark_discovery_offline_returns_explicit_degradation(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    store = AgentCoreStore(tmp_path / "benchmark-offline.db")
    project = AccountLifecycleService(store).create_project(
        user_id="default", account_id="acct-target", business_goal="探索 AI 教育",
    )

    class Service:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", Service())
    monkeypatch.setattr(
        "marketing_tools.scraping_backends.bilibili_public.BilibiliPublicBackend.search_content",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("network unavailable")),
    )
    response = client.post(
        "/api/plugins/marketing-os/accounts/acct-target/benchmarks/discover",
        json={"project_id": project["id"], "query": "AI 教育", "platform": "bilibili"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate_count"] == 0
    assert payload["next_action"] == "refresh_or_add_benchmark_source"
    assert "network unavailable" in payload["source_errors"]["bilibili_public_search"]


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
            {"title": "AI新模型", "source_platform": "bilibili", "category": "科技/AI"},
            {"title": "娱乐新闻", "source_platform": "bilibili", "category": "娱乐/影视"},
        ],
    }
    (tmp_path / "trending-cache.json").write_text(json.dumps(cache))
    result = server.query_trending_cache({"platform": "bilibili"})
    assert result["matched"] == 2
    assert all(t["source_platform"] == "bilibili" for t in result["top_trends"])


def test_trending_cache_sanitizes_generic_distribution_tags(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    (tmp_path / "trending-cache.json").write_text(json.dumps({
        "status": "ok",
        "cached_at": "2026-07-08T10:00:00",
        "top_trends": [
            {"title": "#fyp", "source_platform": "tiktok", "heat_value": 999},
            {"title": "#搞笑", "source_platform": "douyin", "heat_value": 888},
            {"title": "#因为一个片段看了整部剧", "source_platform": "douyin", "heat_value": 811000000},
            {"title": "广西暴雨致多人失联", "source_platform": "douyin", "heat_value": 777},
        ],
        "categories": {"其他": [
            {"title": "#fyp", "source_platform": "tiktok"},
            {"title": "广西暴雨致多人失联", "source_platform": "douyin"},
        ]},
    }))
    payload = client.get("/api/plugins/marketing-os/trending").json()
    titles = [item["title"] for item in payload["top_trends"]]
    assert titles == ["广西暴雨致多人失联"]
    queried = server.query_trending_cache({"platform": "douyin"})
    assert [item["title"] for item in queried["top_trends"]] == ["广西暴雨致多人失联"]


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
    assert result["categories"] == {}
    assert result["query"] == "AI教育"


def test_query_trending_cache_does_not_leak_unfiltered_categories(tmp_path, monkeypatch):
    client_for(tmp_path, monkeypatch)
    cache = {
        "status": "ok", "cached_at": "2026-06-30T10:00:00",
        "categories": {
            "娱乐": [{"title": "明星新闻", "source_platform": "weibo", "category": "娱乐"}],
            "汽车": [{"title": "新能源汽车销量", "source_platform": "douyin", "category": "汽车"}],
        },
        "top_trends": [],
    }
    (tmp_path / "trending-cache.json").write_text(json.dumps(cache))

    result = server.query_trending_cache({"query": "新能源汽车"})

    assert result["matched"] == 1
    assert [item["title"] for item in result["top_trends"]] == ["新能源汽车销量"]
    assert list(result["categories"]) == ["汽车"]


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
            "title": "AI突破", "source_platform": "douyin", "source_backend": "douyin_creator_center",
            "url": "https://www.douyin.com/hot/123", "rank": 1, "collected_at": "2026-06-30T09:00:00",
            "category": "科技/AI", "heat_value": 2840000,
        }],
        "source_errors": {"bilibili": "timeout"},
    }
    (tmp_path / "trending-cache.json").write_text(json.dumps(cache))
    result = server.query_trending_cache({"query": "AI"})
    item = result["top_trends"][0]
    assert item["title"] == "AI突破"
    assert item["source_platform"] == "douyin"
    assert item["source_backend"] == "douyin_creator_center"
    assert item["url"] == "https://www.douyin.com/hot/123"
    assert item["rank"] == 1
    assert item["collected_at"] == "2026-06-30T09:00:00"
    assert "source_errors" in result
    assert result["cache_age_seconds"] >= 0


def test_account_lifecycle_api_draft_confirm_and_read(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    store = AgentCoreStore(tmp_path / "lifecycle-api.db")

    class FakeService:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", FakeService())
    account_id = "acct_lifecycle"

    empty = client.get(f"/api/plugins/marketing-os/accounts/{account_id}/lifecycle")
    assert empty.status_code == 200
    assert empty.json()["stage"] == "not_started"

    drafted = client.post(
        f"/api/plugins/marketing-os/accounts/{account_id}/audience-hypotheses",
        json={
            "user_id": "default",
            "business_goal": "为本地门店获取咨询客户",
            "segments": [{"label": "本地门店经营者", "needs": ["稳定获客"]}],
            "pains": ["不会持续生产内容"],
            "scenarios": ["晚上复盘门店经营时"],
            "exclusions": ["只追求泛娱乐流量的人"],
            "data_gaps": ["occupation_unverified"],
        },
    )
    assert drafted.status_code == 200
    payload = drafted.json()
    assert payload["draft"]["status"] == "draft"
    assert payload["next_action"] == "ask_user_to_confirm_audience"

    confirmed = client.post(
        f"/api/plugins/marketing-os/accounts/{account_id}/audience-hypotheses/"
        f"{payload['draft']['id']}/confirm",
        json={"user_id": "default", "project_id": payload["project"]["id"]},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["lifecycle"]["stage"] == "audience_hypothesis_ready"

    current = client.get(f"/api/plugins/marketing-os/accounts/{account_id}/lifecycle")
    assert current.json()["audience_hypothesis"]["segments"][0]["label"] == "本地门店经营者"

    project_id = payload["project"]["id"]
    benchmark = client.post(
        f"/api/plugins/marketing-os/accounts/{account_id}/benchmarks",
        json={
            "user_id": "default", "project_id": project_id, "platform": "douyin",
            "account_handle": "peer-shop", "account_name": "同行门店号",
            "relation": "direct", "selection_reason": "同区域同目标客户",
            "source_ref": "https://example.com/peer-shop",
        },
    )
    assert benchmark.status_code == 200
    benchmark_id = benchmark.json()["id"]
    assert benchmark.json()["selection_status"] == "candidate"
    decision = client.post(
        f"/api/plugins/marketing-os/accounts/{account_id}/benchmarks/{benchmark_id}/decision",
        json={"user_id": "default", "project_id": project_id, "decision": "selected"},
    )
    assert decision.status_code == 200
    assert decision.json()["selection_status"] == "selected"
    sample = client.post(
        f"/api/plugins/marketing-os/accounts/{account_id}/benchmarks/{benchmark_id}/samples",
        json={
            "user_id": "default", "project_id": project_id, "video_id": "video-1",
            "title": "门店获客真实案例", "metrics": {"likes": 1200},
            "provenance": {
                "source_kind": "public_web", "source_ref": "https://example.com/video-1",
                "captured_at": "2026-07-03T11:50:00Z",
            },
        },
    )
    assert sample.status_code == 200
    assert sample.json()["metrics"]["likes"] == 1200
    observation = client.post(
        f"/api/plugins/marketing-os/accounts/{account_id}/benchmarks/{benchmark_id}/observations",
        json={
            "user_id": "default", "project_id": project_id,
            "dimension": "content_pillar", "value": {"label": "真实改造案例"},
            "provenance": {
                "source_kind": "public_web", "source_ref": "https://example.com/peer-shop/videos",
                "captured_at": "2026-07-03T12:00:00Z",
            }, "confidence": 0.75,
        },
    )
    assert observation.status_code == 200
    research = client.get(
        f"/api/plugins/marketing-os/accounts/{account_id}/benchmarks?project_id={project_id}"
    ).json()
    assert len(research["accounts"]) == 1
    assert research["samples"][0]["title"] == "门店获客真实案例"
    assert research["observations"][0]["provenance"]["source_kind"] == "public_web"
    lifecycle_status = client.get(
        f"/api/plugins/marketing-os/accounts/{account_id}/lifecycle"
    ).json()
    assert lifecycle_status["stage"] == "audience_hypothesis_ready"
    assert lifecycle_status["next_action"] == "complete_benchmark_evidence"
    assert research["readiness"]["ready"] is False


def test_audience_snapshot_api_only_accepts_first_party_sources(tmp_path, monkeypatch):
    client = client_for(tmp_path, monkeypatch)
    store = AgentCoreStore(tmp_path / "audience-api.db")

    class FakeService:
        def get_store(self):
            return store

    monkeypatch.setattr(server, "_agent_service", FakeService())
    lifecycle = AccountLifecycleService(store)
    project = lifecycle.create_project(user_id="default", account_id="acct", business_goal="了解受众")
    rejected = client.post(
        "/api/plugins/marketing-os/accounts/acct/audience-snapshots",
        json={
            "project_id": project["id"], "platform": "douyin",
            "dimensions": {"age": {"24-30": 0.5}},
            "provenance": {
                "source_kind": "model_inference", "source_ref": "model://guess",
                "captured_at": "2026-07-03T12:00:00Z",
            },
        },
    )
    assert rejected.status_code == 400
    accepted = client.post(
        "/api/plugins/marketing-os/accounts/acct/audience-snapshots",
        json={
            "project_id": project["id"], "platform": "douyin",
            "dimensions": {"age": {"24-30": 0.5}, "region": {"广东": 0.3}},
            "provenance": {
                "source_kind": "official_api", "source_ref": "douyin:fans.data",
                "captured_at": "2026-07-03T12:00:00Z", "data_gaps": ["occupation_unavailable"],
            },
        },
    )
    assert accepted.status_code == 200
    listed = client.get(
        f"/api/plugins/marketing-os/accounts/acct/audience-snapshots?project_id={project['id']}"
    ).json()
    assert listed["latest"]["provenance"]["source_kind"] == "official_api"
