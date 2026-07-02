import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from agent_core import AgentCoreStore, CapabilityLevel, CapabilityPolicy, HermesAgentService, MemoryKind, TaskStatus
from agent_core.policy import set_authorization_checker


def running_task(store: AgentCoreStore):
    task = store.create_task(session_id="session-1", user_id="user-1", objective="整理行业热点")
    store.transition_task(task["id"], TaskStatus.RUNNING, current_step="research")
    return store.get_task(task["id"])


def test_task_events_and_checkpoint_survive_reopen(tmp_path):
    path = tmp_path / "agent-core.db"
    store = AgentCoreStore(path)
    task = running_task(store)
    store.transition_task(task["id"], TaskStatus.PAUSED, checkpoint={"cursor": 3})

    reopened = AgentCoreStore(path)
    loaded = reopened.get_task(task["id"])
    assert loaded["status"] == "paused"
    assert loaded["checkpoint"] == {"cursor": 3}
    assert [event["event_type"] for event in reopened.list_events(task["id"])] == [
        "task.created", "task.status_changed", "task.status_changed",
    ]


def test_invalid_terminal_transition_is_rejected(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    task = running_task(store)
    store.transition_task(task["id"], TaskStatus.COMPLETED)
    with pytest.raises(ValueError):
        store.transition_task(task["id"], TaskStatus.RUNNING)


def test_approval_is_durable_and_controls_effect(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    task = running_task(store)
    approval = store.create_approval(
        task_id=task["id"], capability="marketing_effect_publish",
        arguments={"platform": "douyin"}, risk_summary="将向抖音正式发布内容",
    )
    assert store.get_task(task["id"])["status"] == "waiting_user"

    with pytest.raises(PermissionError):
        store.create_effect_intent(
            task_id=task["id"], capability="marketing_effect_publish",
            idempotency_key="publish:1", preview={"title": "草稿"}, approval_id=approval["id"],
        )

    store.decide_approval(approval["id"], True, "用户确认预览")
    effect = store.create_effect_intent(
        task_id=task["id"], capability="marketing_effect_publish",
        idempotency_key="publish:1", preview={"title": "草稿"}, approval_id=approval["id"],
    )
    duplicate = store.create_effect_intent(
        task_id=task["id"], capability="marketing_effect_publish",
        idempotency_key="publish:1", preview={"title": "不会重复"}, approval_id=approval["id"],
    )
    assert duplicate["id"] == effect["id"]
    assert store.record_effect_receipt(effect["id"], {"platform_id": "video-1"})["status"] == "executed"


def test_secret_is_rejected_before_memory_promotion(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    candidate = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1",
        content="请记住 api_key=sk-this-must-never-be-stored",
        evidence=[{"source": "conversation"}], confidence=1.0,
    )
    assert candidate["status"] == "rejected"
    assert "秘密" in candidate["rejection_reason"]


def test_capability_policy_fails_closed():
    policy = CapabilityPolicy()
    assert policy.evaluate("marketing_read_trends").allowed
    assert policy.evaluate("marketing_effect_publish").approval_required
    shell = policy.evaluate("system_shell")
    assert not shell.allowed and shell.level is CapabilityLevel.SYSTEM_FORBIDDEN
    assert not policy.evaluate("unknown_tool").allowed


def test_tool_manifest_all_have_valid_levels():
    from agent_core.tool_manifest import all_tools
    tools = all_tools()
    assert len(tools) == 19
    for tool in tools:
        assert tool.level in CapabilityLevel
        assert tool.name.startswith("marketing_")
        assert tool.schema.get("type") == "object"


def test_only_implemented_tools_are_registered():
    from agent_core.tool_manifest import all_tools
    tools = all_tools()
    read_count = sum(1 for t in tools if t.level is CapabilityLevel.READ_ONLY)
    controlled_count = sum(1 for t in tools if t.level is CapabilityLevel.CONTROLLED_RESOURCE)
    effect_count = sum(1 for t in tools if t.level is CapabilityLevel.EXTERNAL_EFFECT)
    assert read_count == 13
    assert controlled_count == 3
    assert effect_count == 1
    assert sum(1 for t in tools if t.level is CapabilityLevel.REVERSIBLE_WRITE) == 2
    assert any(t.level is CapabilityLevel.EXTERNAL_EFFECT for t in tools)
    assert not any(t.level is CapabilityLevel.SYSTEM_FORBIDDEN for t in tools)


def test_hermes_and_marketing_tool_packages_do_not_shadow_each_other():
    """Hermes' top-level tools package must coexist with marketing_tools."""
    hermes_root = ROOT / "runtime" / "hermes-agent"
    marketing_root = ROOT / "engine" / "marketing-os"
    for path in (str(hermes_root), str(marketing_root)):
        if path not in sys.path:
            sys.path.insert(0, path)
    from tools.registry import registry
    from marketing_tools.account import list_accounts
    assert registry is not None
    assert callable(list_accounts)


def test_tool_manifest_l2_l3_require_approval():
    from agent_core.tool_manifest import all_tools
    for tool in all_tools():
        if tool.level in (CapabilityLevel.CONTROLLED_RESOURCE, CapabilityLevel.EXTERNAL_EFFECT):
            assert tool.requires_approval, f"{tool.name} should require approval"


def test_tool_manifest_no_l4_registered():
    from agent_core.tool_manifest import all_tools
    for tool in all_tools():
        assert tool.level is not CapabilityLevel.SYSTEM_FORBIDDEN, \
            f"{tool.name} is SYSTEM_FORBIDDEN and should not be registered"


def test_policy_enforcement_on_all_tools():
    """Every tool in the manifest passes policy evaluation."""
    from agent_core.tool_manifest import all_tools
    policy = CapabilityPolicy()
    for tool in all_tools():
        decision = policy.evaluate(tool.name)
        assert decision.allowed, f"{tool.name} should be allowed by policy"
        assert not decision.approval_required or tool.requires_approval, \
            f"{tool.name}: approval mismatch"


def test_gateway_injects_durable_account_context_into_tool_arguments():
    from agent_core.tool_gateway import _wrap_handler, set_task_context

    captured = {}

    def handler(params):
        captured.update(params)
        return {"ok": True}

    wrapped = _wrap_handler("marketing_read_accounts", handler)
    set_task_context({"task_id": "task-1", "user_id": "user-1", "account_id": "acct-one"})
    try:
        wrapped(None)
    finally:
        set_task_context(None)

    assert captured["account_id"] == "acct-one"
    assert captured["__task_id"] == "task-1"


def test_system_tools_blocked_by_policy():
    """System-level capabilities must be blocked."""
    policy = CapabilityPolicy()
    blocked = ["system_shell", "system_cookies_raw", "system_permissions_modify"]
    for name in blocked:
        decision = policy.evaluate(name)
        assert not decision.allowed, f"{name} should be blocked"
        assert decision.level is CapabilityLevel.SYSTEM_FORBIDDEN


def test_tool_namespacing():
    """All tools must use the marketing_ namespace with valid API-safe names."""
    from agent_core.tool_manifest import all_tools
    import re
    api_safe = re.compile(r'^[a-zA-Z0-9_-]+$')
    for tool in all_tools():
        assert tool.name.startswith("marketing_"), f"{tool.name}: bad namespace"
        parts = tool.name.split("_")
        assert len(parts) >= 3, f"{tool.name}: too few namespace segments"
        assert api_safe.match(tool.name), f"{tool.name}: not API-safe (no dots)"


# ── HermesAgentService tests ──────────────────────────────────────────


def _fake_agent_service(tmp_path):
    """Use the checked-in Hermes source without making a model call."""
    store = AgentCoreStore(tmp_path / "agent-core.db")
    svc = HermesAgentService(
        store=store,
        hermes_home=tmp_path / "hermes-home",
        agent_root=ROOT / "runtime" / "hermes-agent",
        enabled_toolsets=["__none__"],
    )
    return svc, store


def test_agent_service_creates_session(tmp_path):
    svc, store = _fake_agent_service(tmp_path)
    import asyncio
    runtime = svc.runtime_status()
    assert runtime["source_available"] is True
    assert runtime["provider_configured"] is False
    result = asyncio.run(svc.create_session("user-1"))
    assert result["user_id"] == "user-1"
    assert len(result["session_id"]) > 0

    same = asyncio.run(svc.create_session("user-1"))
    assert same["session_id"] == result["session_id"]


def test_agent_session_survives_service_reopen(tmp_path):
    import asyncio
    svc, store = _fake_agent_service(tmp_path)
    created = asyncio.run(svc.create_session("user-1", "workspace-a"))
    reopened = HermesAgentService(
        store=AgentCoreStore(tmp_path / "agent-core.db"),
        hermes_home=tmp_path / "hermes-home",
        agent_root=ROOT / "runtime" / "hermes-agent",
        enabled_toolsets=["__none__"],
    )
    loaded = asyncio.run(reopened.get_session(created["session_id"]))
    assert loaded and loaded["workspace"] == "workspace-a"


def test_agent_service_send_message_creates_task(tmp_path, monkeypatch):
    svc, store = _fake_agent_service(tmp_path)
    monkeypatch.setattr(svc, "_start_task", lambda *_args, **_kwargs: None)
    import asyncio

    async def run():
        session = await svc.create_session("user-1")
        sid = session["session_id"]
        result = await svc.send_message(sid, "帮我整理AI教育热点")
        assert result["task_id"].startswith("task_")
        assert result["status"] == "planning"

        status = await svc.get_task_status(result["task_id"])
        assert status["task_id"] == result["task_id"]
        assert status["objective"] == "帮我整理AI教育热点"
        assert status["plan"]
        assert status["plan"][-1]["kind"] == "synthesis"
        assert any(step.get("tool_name") == "marketing_read_trends" for step in status["plan"])
        plan_events = [event for event in store.list_events(result["task_id"]) if event["event_type"] == "plan.ready"]
        assert len(plan_events) == 1
        assert plan_events[0]["payload"]["source"] == "product_executor"
        return result

    asyncio.run(run())


def test_initial_plan_is_not_created_for_casual_conversation():
    assert HermesAgentService._build_initial_plan("你好，今天心情怎么样", None) == []


def test_evidence_discipline_is_reinjected_on_existing_sessions(tmp_path):
    svc, _ = _fake_agent_service(tmp_path)
    import asyncio
    session_data = asyncio.run(svc.create_session("user-1"))
    session = svc._sessions[session_data["session_id"]]
    context = svc._build_turn_context(session, "acct-one")
    assert "industries 是全局监控范围，不是账号标签" in context
    assert "策略推断必须标注为推断" in context


def test_product_executor_prefetches_account_and_degradation_evidence(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    import agent_core.hermes_adapter as adapter_module

    svc, store = _fake_agent_service(tmp_path)
    plan = svc._build_initial_plan("为当前抖音账号整理 AI 热点选题", "acct-one")
    task = store.create_task(
        session_id="sess-1", user_id="user-1", account_id="acct-one",
        objective="整理热点", plan=plan,
    )
    store.transition_task(task["id"], TaskStatus.RUNNING)

    payloads = {
        "marketing_read_context": {
            "scope": {"account_id": "acct-one"},
            "industries": ["AI"],
            "accounts": [{"id": "acct-one", "platform": "douyin", "stats": {"followers": 4}}],
        },
        "marketing_read_trends": {
            "total_deduped": 1,
            "platforms_succeeded": ["bilibili"],
            "categories": {
                "科技/AI": [{
                    "title": "真实 AI 热点", "source_platform": "bilibili",
                    "url": "https://www.bilibili.com/video/real", "rank": 1,
                }],
            },
        },
        "marketing_read_intelligence_report": {"status": "partial", "errors": [{"scope": "fallback"}]},
    }
    monkeypatch.setattr(
        adapter_module, "tool_by_name",
        lambda name: SimpleNamespace(handler=lambda _params, n=name: json.dumps(payloads[n], ensure_ascii=False)),
    )

    evidence = svc._prefetch_required_evidence(task["id"])

    assert set(evidence) == set(payloads)
    updated = store.get_task(task["id"])
    statuses = {step.get("tool_name"): step["status"] for step in updated["plan"]}
    assert statuses["marketing_read_context"] == "completed"
    assert statuses["marketing_read_trends"] == "completed"
    assert statuses["marketing_read_intelligence_report"] == "completed"
    assert updated["checkpoint"]["completed_steps"] == ["1", "2", "3"]
    event_types = [event["event_type"] for event in store.list_events(task["id"])]
    assert event_types.count("tool.completed") == 3

    lines = svc._format_authoritative_evidence(evidence)
    rendered = "\n".join(lines)
    assert '"followers": 4' in rendered
    assert "全局监控行业（不是账号定位或标签）：AI" in rendered
    assert "定位、标签、受众、内容数量、产品用户画像" in rendered


def test_evidence_guard_requests_repair_for_unsupported_account_claims():
    evidence = {
        "marketing_read_context": {
            "accounts": [{"id": "acct-one", "platform": "douyin", "stats": {"followers": 4}}],
        },
    }
    reply = (
        "账号定位 AI / 科技，和 AI/教育/创业 标签完美匹配。"
        "这是今天全网热议的话题，正值世界杯淘汰赛日，适合新号阶段冷启动。"
    )

    violations = HermesAgentService._detect_evidence_violations(reply, evidence, "acct-one")

    assert len(violations) == 4
    assert any("定位或标签字段" in item for item in violations)
    assert any("扩大性判断" in item for item in violations)
    assert any("赛事事实" in item for item in violations)
    assert any("冷启动" in item for item in violations)


def test_evidence_guard_allows_scoped_fact_and_labeled_inference():
    evidence = {
        "marketing_read_context": {
            "accounts": [{"id": "acct-one", "platform": "douyin", "stats": {"followers": 4}}],
        },
    }
    reply = "已证实事实：粉丝数为4。策略推断：账号可能仍在早期阶段。创作建议：测试该选题。"
    assert HermesAgentService._detect_evidence_violations(reply, evidence, "acct-one") == []


def test_evidence_guard_rejects_fabricated_trend_titles_platforms_and_metrics():
    evidence = {
        "marketing_read_context": {
            "accounts": [{"id": "acct-one", "platform": "douyin", "stats": {"followers": 4}}],
        },
        "marketing_read_trends": {
            "total_deduped": 1,
            "platforms_succeeded": ["bilibili"],
            "categories": {
                "科技/AI": [{
                    "title": "真实 AI 热点", "source_platform": "bilibili",
                    "url": "https://www.bilibili.com/video/real", "rank": 1,
                }],
            },
        },
    }
    reply = (
        "| **来源平台** | 抖音 / 微信 |\n"
        "| **原始标题** | 《不存在的热点》 |\n"
        "| **链接** | 微信趋势周环比约 320%，可见百万播放 |\n"
        "| **热点榜** | `AI_EDUCATION_20260629`，采集时间推测 |"
    )

    violations = HermesAgentService._detect_evidence_violations(reply, evidence, "acct-one")

    assert any("不在本轮热点证据白名单" in item for item in violations)
    assert any("来源平台没有" in item for item in violations)
    assert any("百分比或播放量级" in item for item in violations)
    assert any("不得推测或自造" in item for item in violations)


def test_grounding_failure_reply_returns_empty_result_instead_of_inventing():
    reply = HermesAgentService._build_grounding_failure_reply({
        "marketing_read_context": {
            "accounts": [{
                "id": "acct-one", "platform": "douyin",
                "stats": {"followers": 4, "total_likes": 56, "total_views": 193},
            }],
        },
        "marketing_read_trends": {
            "total_deduped": 30,
            "platforms_succeeded": ["bilibili"],
            "source_errors": {"douyin": "ssl failed"},
        },
    })
    assert "本轮未交付选题" in reply
    assert "返回空结果" in reply
    assert "粉丝 4" in reply
    assert "ssl failed" in reply


def test_plan_finalization_marks_synthesis_complete_and_unused_tools_skipped(tmp_path):
    svc, store = _fake_agent_service(tmp_path)
    plan = svc._build_initial_plan("为当前抖音账号整理 AI 热点选题", "acct-one")
    task = store.create_task(
        session_id="sess-1", user_id="user-1", account_id="acct-one",
        objective="整理热点", plan=plan,
    )
    store.transition_task(task["id"], TaskStatus.RUNNING)
    current = store.get_task(task["id"])["plan"]
    current[0]["status"] = "completed"
    store.update_plan(task["id"], current)

    svc._finalize_plan(task["id"])

    finalized = store.get_task(task["id"])
    assert finalized["plan"][0]["status"] == "completed"
    assert finalized["plan"][-1]["status"] == "completed"
    assert all(step["status"] in {"completed", "skipped"} for step in finalized["plan"])
    assert finalized["checkpoint"]["completed_steps"]
    assert finalized["checkpoint"]["current_step"] is None


def test_agent_service_cancel_task(tmp_path, monkeypatch):
    svc, store = _fake_agent_service(tmp_path)
    monkeypatch.setattr(svc, "_start_task", lambda *_args, **_kwargs: None)
    import asyncio

    async def run():
        session = await svc.create_session("user-1")
        sid = session["session_id"]
        result = await svc.send_message(sid, "任务待取消")
        cancel_result = await svc.cancel_task(result["task_id"])
        assert cancel_result["status"] == "cancelled"

    asyncio.run(run())


def test_real_agent_service_cancels_waiting_approval_atomically(tmp_path):
    svc, store = _fake_agent_service(tmp_path)
    task = store.create_task(session_id="sess-1", user_id="user-1", objective="待审批任务")
    store.transition_task(task["id"], TaskStatus.RUNNING)
    approval = store.create_approval(
        task_id=task["id"], capability="marketing_session_login",
        arguments={"platform": "douyin"}, risk_summary="需要登录",
    )

    import asyncio
    result = asyncio.run(svc.cancel_task(task["id"]))

    assert result["status"] == "cancelled"
    assert store.get_task(task["id"])["status"] == "cancelled"
    decided = store.get_approval(approval["id"])
    assert decided["status"] == "rejected"
    assert decided["decision_reason"] == "task cancelled"
    event_types = [event["event_type"] for event in store.list_events(task["id"])]
    assert event_types[-3:] == ["approval.decided", "task.status_changed", "task.cancelled"]


def test_agent_service_send_to_unknown_session_fails(tmp_path):
    svc, store = _fake_agent_service(tmp_path)
    import asyncio
    with pytest.raises(KeyError):
        asyncio.run(svc.send_message("nonexistent", "hello"))


def test_agent_service_approval_decisions_persist(tmp_path):
    store = AgentCoreStore(tmp_path / "agent-core.db")
    task = store.create_task(session_id="sess-1", user_id="user-1", objective="测试发布审批")
    store.transition_task(task["id"], TaskStatus.RUNNING)
    approval = store.create_approval(
        task_id=task["id"], capability="marketing_effect_publish",
        arguments={"platform": "douyin"}, risk_summary="将向抖音发布内容",
    )

    # approve: task goes back to running
    decided = store.decide_approval(approval["id"], True, "确认发布")
    assert decided["status"] == "approved"
    assert store.get_task(task["id"])["status"] == "running"

    # double-decide is rejected
    with pytest.raises(ValueError, match="already approved"):
        store.decide_approval(approval["id"], False, "重复操作")


def test_agent_service_approval_rejected_pauses_task(tmp_path):
    store = AgentCoreStore(tmp_path / "agent-core.db")
    task = store.create_task(session_id="sess-2", user_id="user-1", objective="测试拒绝审批")
    store.transition_task(task["id"], TaskStatus.RUNNING)
    approval = store.create_approval(
        task_id=task["id"], capability="marketing_effect_send",
        arguments={"platform": "weixin"}, risk_summary="向微信发送消息",
    )

    decided = store.decide_approval(approval["id"], False, "暂不发送")
    assert decided["status"] == "rejected"
    assert store.get_task(task["id"])["status"] == "paused"


def test_agent_service_stream_events_on_completed_task(tmp_path, monkeypatch):
    svc, store = _fake_agent_service(tmp_path)
    import asyncio

    monkeypatch.setattr(svc, "_start_task", lambda *_args, **_kwargs: None)

    async def run():
        session = await svc.create_session("user-1")
        sid = session["session_id"]
        result = await svc.send_message(sid, "快速任务")
        task_id = result["task_id"]

        # Manually simulate agent completing
        store.transition_task(task_id, TaskStatus.RUNNING)
        store.transition_task(task_id, TaskStatus.COMPLETED)

        events = []
        async for event in svc.stream_events(task_id):
            events.append(event)
            if len(events) > 20:
                break

        stored_events = [e for e in events if e.get("type") == "task.created"]
        assert len(stored_events) >= 1
        return len(events)

    count = asyncio.run(run())
    assert count > 0


def test_approval_without_transition_task_keeps_waiting(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    task = store.create_task(session_id="sess-1", user_id="user-1", objective="测试bridge模式")
    store.transition_task(task["id"], TaskStatus.RUNNING)
    approval = store.create_approval(
        task_id=task["id"], capability="marketing_trending_search",
        arguments={"platform": "douyin"}, risk_summary="搜索行业内容",
    )
    decided = store.decide_approval(approval["id"], True, transition_task=False)
    assert decided["status"] == "approved"
    assert store.get_task(task["id"])["status"] == "waiting_user"


def test_effect_idempotency_key_unique(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    task = store.create_task(session_id="sess-1", user_id="user-1", objective="测试幂等")
    store.transition_task(task["id"], TaskStatus.RUNNING)
    approval = store.create_approval(
        task_id=task["id"], capability="marketing_accounts_sync",
        arguments={"platform": "douyin"}, risk_summary="同步账号",
    )
    store.decide_approval(approval["id"], True, transition_task=False)
    effect1 = store.create_effect_intent(
        task_id=task["id"], capability="marketing_accounts_sync",
        idempotency_key="sync:douyin:user1", preview={}, approval_id=approval["id"],
    )
    effect2 = store.create_effect_intent(
        task_id=task["id"], capability="marketing_accounts_sync",
        idempotency_key="sync:douyin:user1", preview={"different": True}, approval_id=approval["id"],
    )
    assert effect1["id"] == effect2["id"]


def test_effect_receipt_idempotent(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    task = store.create_task(session_id="sess-1", user_id="user-1", objective="测试幂等receipt")
    store.transition_task(task["id"], TaskStatus.RUNNING)
    approval = store.create_approval(
        task_id=task["id"], capability="marketing_trending_search",
        arguments={"keyword": "AI"}, risk_summary="搜索",
    )
    store.decide_approval(approval["id"], True, transition_task=False)
    effect = store.create_effect_intent(
        task_id=task["id"], capability="marketing_trending_search",
        idempotency_key="search:ai:1", preview={}, approval_id=approval["id"],
    )
    first = store.record_effect_receipt(effect["id"], {"data": "first"})
    second = store.record_effect_receipt(effect["id"], {"data": "second"})
    assert first["receipt"]["data"] == "first"
    assert second["receipt"]["data"] == "first"
    assert first["status"] == "executed"


def test_controlled_tools_count(tmp_path):
    from agent_core.tool_manifest import all_tools
    tools = all_tools()
    assert len(tools) == 19
    controlled = [t for t in tools if t.level is CapabilityLevel.CONTROLLED_RESOURCE]
    assert len(controlled) == 3
    effect = [t for t in tools if t.level is CapabilityLevel.EXTERNAL_EFFECT]
    assert len(effect) == 1
    assert all(t.requires_approval for t in controlled)


def test_agent_cannot_grant_or_revoke_its_own_authorization():
    from agent_core.tool_manifest import all_tools
    names = {tool.name for tool in all_tools()}
    assert "marketing_draft_auth_grant" not in names
    assert "marketing_draft_auth_revoke" not in names


def test_approval_event_contains_canonical_arguments(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    task = running_task(store)
    approval = store.create_approval(
        task_id=task["id"], capability="marketing_trending_search",
        arguments={"platform": "douyin", "keyword": "AI 教育"}, risk_summary="搜索行业内容",
    )
    event = store.list_events(task["id"])[-1]
    assert event["event_type"] == "approval.requested"
    assert event["payload"]["approval_id"] == approval["id"]
    assert event["payload"]["arguments"] == {"platform": "douyin", "keyword": "AI 教育"}


def test_tool_gateway_creates_approval_for_l2_tool(tmp_path, monkeypatch):
    from agent_core.tool_gateway import _wrap_handler, set_task_context, get_task_context
    from agent_core.tool_manifest import all_tools
    import json as _json

    store = AgentCoreStore(tmp_path / "core.db")
    task = store.create_task(session_id="sess-1", user_id="user-1", objective="搜索测试")
    store.transition_task(task["id"], TaskStatus.RUNNING)
    set_task_context({"task_id": task["id"], "store": store})

    try:
        tool = next(t for t in all_tools() if t.name == "marketing_trending_search")
        handler = _wrap_handler(tool.name, tool.handler)
        result = _json.loads(handler(platform="douyin", keyword="AI教育"))
        assert result["status"] == "pending_approval"
        assert result["approval_id"].startswith("approval_")
        assert store.get_task(task["id"])["status"] == "waiting_user"
    finally:
        set_task_context(None)


def test_tool_gateway_no_context_returns_blocked(tmp_path):
    from agent_core.tool_gateway import _wrap_handler
    from agent_core.tool_manifest import all_tools
    import json as _json

    tool = next(t for t in all_tools() if t.name == "marketing_trending_search")
    handler = _wrap_handler(tool.name, tool.handler)
    result = _json.loads(handler(platform="douyin", keyword="test"))
    assert result["status"] == "blocked"
    assert "上下文" in result["error"]


def test_plan_parsing_from_numbered_list():
    from agent_core.hermes_adapter import HermesAgentService
    text = "计划：\n1. 读取账号状态\n2. 搜索抖音AI教育内容\n3. 基于结果分析趋势"
    plan = HermesAgentService._parse_plan_from_text(text)
    assert len(plan) == 3
    assert plan[0]["id"] == "1"
    assert plan[0]["description"] == "读取账号状态"
    assert plan[0]["tool_guess"] == "marketing_read_accounts"
    assert plan[0]["status"] == "pending"


def test_plan_parsing_alternative_markers():
    from agent_core.hermes_adapter import HermesAgentService
    text = "1、搜索热点\n2）分析数据\n3.生成报告"
    plan = HermesAgentService._parse_plan_from_text(text)
    assert len(plan) == 3
    assert plan[0]["id"] == "1"
    assert plan[1]["id"] == "2"
    assert plan[2]["id"] == "3"


def test_plan_parsing_ignores_non_numbered():
    from agent_core.hermes_adapter import HermesAgentService
    plan = HermesAgentService._parse_plan_from_text("你好，我能帮你什么？")
    assert plan == []


def test_tool_guess_matches_keywords():
    from agent_core.hermes_adapter import HermesAgentService

    # Trend/hotspot keywords map to L0 read tool
    assert HermesAgentService._guess_tool_for_step("分析热点趋势") == "marketing_read_trends"
    assert HermesAgentService._guess_tool_for_step("行业热点分析") == "marketing_read_trends"
    assert HermesAgentService._guess_tool_for_step("今日热榜") == "marketing_read_trends"
    assert HermesAgentService._guess_tool_for_step("查看热搜") == "marketing_read_trends"

    # Explicit platform search keywords map to L2
    assert HermesAgentService._guess_tool_for_step("搜索抖音AI教育内容") == "marketing_trending_search"
    assert HermesAgentService._guess_tool_for_step("采集抖音美妆内容") == "marketing_trending_search"

    # Other keywords still work
    assert HermesAgentService._guess_tool_for_step("读取账号状态") == "marketing_read_accounts"
    assert HermesAgentService._guess_tool_for_step("生成选题") == "marketing_read_suggestions"
    assert HermesAgentService._guess_tool_for_step("推理和判断") is None


def test_marketing_read_trends_schema():
    from agent_core.tool_manifest import tool_by_name
    tool = tool_by_name("marketing_read_trends")
    assert tool is not None
    props = tool.schema.get("properties", {})
    assert "query" in props
    assert "platform" in props
    assert "limit" in props
    assert props["limit"].get("default") == 30
    assert props["limit"].get("minimum") == 1
    assert props["limit"].get("maximum") == 30


def test_update_plan_persists_and_versions(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    task = store.create_task(session_id="session-1", user_id="user-1", objective="test")
    store.transition_task(task["id"], TaskStatus.RUNNING)

    plan = [{"id": "1", "description": "Step 1", "tool_guess": None, "status": "pending"}]
    updated = store.update_plan(task["id"], plan)
    assert updated["plan"] == plan
    assert updated["plan_version"] == 2

    plan[0]["status"] = "completed"
    updated2 = store.update_plan(task["id"], plan)
    assert updated2["plan_version"] == 3

    reopened = AgentCoreStore(path=tmp_path / "core.db")
    loaded = reopened.get_task(task["id"])
    assert loaded["plan"] == plan
    assert loaded["plan_version"] == 3


def test_memory_candidate_add_and_list(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="偏好AI教育赛道",
        evidence=[{"source": "conversation"}], confidence=0.9,
    )
    store.add_memory_candidate(
        kind=MemoryKind.ACCOUNT, user_id="user-1",
        content="抖音账号定位：职场知识", account_id="acc-1", platform="douyin",
        evidence=[{"source": "user_stated"}], confidence=0.95,
    )
    all_memories = store.list_memories(user_id="user-1", status=None)
    assert len(all_memories) == 2
    user_only = store.list_memories(user_id="user-1", kind="user", status=None)
    assert len(user_only) == 1
    assert user_only[0]["content"] == "偏好AI教育赛道"


def test_memory_delete(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    candidate = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="test",
        evidence=[{"source": "user_stated"}], confidence=0.9,
    )
    assert candidate["status"] == "verified"
    store.delete_memory(candidate["id"])
    result = store.list_memories(user_id="user-1", status=None)
    assert len(result) == 0


def test_memory_secret_rejection(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    candidate = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1",
        content="password = mysecret123", evidence=[], confidence=1.0,
    )
    assert candidate["status"] == "rejected"
    assert "秘密" in candidate.get("rejection_reason", "")


def test_authorization_grant_and_check(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    assert not store.is_authorized("user-1", "marketing_trending_search")
    store.grant_authorization("user-1", "marketing_trending_search")
    assert store.is_authorized("user-1", "marketing_trending_search")
    assert not store.is_authorized("user-1", "marketing_accounts_sync")


def test_authorization_revoke(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    store.grant_authorization("user-1", "marketing_session_login")
    assert store.is_authorized("user-1", "marketing_session_login")
    store.revoke_authorization("user-1", "marketing_session_login")
    assert not store.is_authorized("user-1", "marketing_session_login")


def test_authorization_list(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    store.grant_authorization("user-1", "marketing_trending_search")
    store.grant_authorization("user-1", "marketing_accounts_sync")
    auths = store.list_authorizations("user-1")
    assert len(auths) == 2
    capabilities = {a["capability"] for a in auths}
    assert "marketing_trending_search" in capabilities
    assert "marketing_accounts_sync" in capabilities


def test_authorization_constraints_do_not_expand_to_other_accounts(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    store.grant_authorization(
        "user-1", "marketing_accounts_sync",
        {"platform": "douyin", "username": "account-a"},
    )
    assert store.is_authorized(
        "user-1", "marketing_accounts_sync",
        {"platform": "douyin", "username": "account-a"},
    )
    assert not store.is_authorized(
        "user-1", "marketing_accounts_sync",
        {"platform": "douyin", "username": "account-b"},
    )


def test_legacy_unscoped_authorization_is_revoked_on_migration(tmp_path):
    import sqlite3
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as db:
        db.execute(
            """CREATE TABLE user_authorizations (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL, capability TEXT NOT NULL,
            scope TEXT NOT NULL DEFAULT 'permanent', granted_at TEXT NOT NULL, revoked_at TEXT
            )"""
        )
        db.execute(
            "INSERT INTO user_authorizations (id, user_id, capability, granted_at) VALUES ('auth-old', 'user-1', 'marketing_accounts_sync', '2026-06-29')"
        )
    store = AgentCoreStore(path)
    assert not store.is_authorized(
        "user-1", "marketing_accounts_sync",
        {"platform": "douyin", "username": "account-a"},
    )


def test_exact_capability_respects_scoped_authorization(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    store.grant_authorization("user-1", "marketing_session_login", {"platform": "douyin"})
    set_authorization_checker(store.is_authorized)
    policy = CapabilityPolicy()
    assert not policy.evaluate(
        "marketing_session_login", user_id="user-1", arguments={"platform": "douyin"},
    ).approval_required
    assert policy.evaluate(
        "marketing_session_login", user_id="user-1", arguments={"platform": "weibo"},
    ).approval_required


def test_turn_context_is_scoped_to_current_user_and_account(tmp_path):
    import asyncio
    svc, store = _fake_agent_service(tmp_path)
    created = asyncio.run(svc.create_session("user-1"))
    evidence = [{"source": "conversation", "message_id": "m-1"}]
    global_memory = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="用户偏好简洁表达",
        evidence=evidence, confidence=0.9,
    )
    account_a = store.add_memory_candidate(
        kind=MemoryKind.ACCOUNT, user_id="user-1", account_id="account-a",
        content="账号 A 面向新手", evidence=evidence, confidence=0.9,
    )
    account_b = store.add_memory_candidate(
        kind=MemoryKind.ACCOUNT, user_id="user-1", account_id="account-b",
        content="账号 B 面向专家", evidence=evidence, confidence=0.9,
    )
    other_user = store.add_memory_candidate(
        kind=MemoryKind.ACCOUNT, user_id="user-2", account_id="account-a",
        content="其他用户的账号信息", evidence=evidence, confidence=0.9,
    )
    for memory in (global_memory, account_a, account_b, other_user):
        store.update_memory_candidate(memory["id"], status="verified")
    context = svc._build_turn_context(svc._sessions[created["session_id"]], "account-a")
    assert "用户偏好简洁表达" in context
    assert "账号 A 面向新手" in context
    assert "账号 B 面向专家" not in context
    assert "其他用户的账号信息" not in context


def test_pending_memory_is_not_injected_until_user_verifies_it(tmp_path):
    import asyncio
    svc, store = _fake_agent_service(tmp_path)
    created = asyncio.run(svc.create_session("user-1"))
    candidate = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="候选偏好",
        evidence=[{"source": "agent_task", "task_id": "task-1"}], confidence=0.5,
    )
    session = svc._sessions[created["session_id"]]
    assert "候选偏好" not in svc._build_turn_context(session, None)
    store.update_memory_candidate(candidate["id"], status="verified")
    assert "候选偏好" in svc._build_turn_context(session, None)
def test_memory_rejects_no_evidence(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    candidate = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="AI教育赛道有潜力",
        evidence=[], confidence=0.9,
    )
    assert candidate["status"] == "rejected"
    assert "证据" in candidate.get("rejection_reason", "")


def test_memory_rejects_low_confidence_no_evidence(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    candidate = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="AI教育赛道有潜力",
        evidence=[], confidence=0.3,
    )
    assert candidate["status"] == "rejected"


def test_content_asset_state_machine(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    asset = store.create_content_asset(title="测试选题", type="script", platform="douyin")
    assert asset["status"] == "draft"

    store.transition_content_asset(asset["id"], "review")
    assert store.get_content_asset(asset["id"])["status"] == "review"

    store.transition_content_asset(asset["id"], "approved")
    assert store.get_content_asset(asset["id"])["status"] == "approved"

    with pytest.raises(ValueError):
        store.transition_content_asset(asset["id"], "draft")


def test_content_asset_list_and_filter(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    store.create_content_asset(title="选题A", type="script", account_id="acc-1")
    store.create_content_asset(title="选题B", type="video", account_id="acc-1")
    store.create_content_asset(title="选题C", type="script")

    assert len(store.list_content_assets()) == 3
    assert len(store.list_content_assets(account_id="acc-1")) == 2
    assert len(store.list_content_assets(type="script")) == 2

    asset = store.list_content_assets()[0]
    store.transition_content_asset(asset["id"], "review")
    assert len(store.list_content_assets(status="review")) == 1


def test_content_asset_metrics_update(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    asset = store.create_content_asset(title="测试", type="video")
    updated = store.update_content_metrics(asset["id"], {"views": 1200, "likes": 89})
    assert updated["metrics"]["views"] == 1200
    assert updated["metrics"]["likes"] == 89


def test_content_asset_delete(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    asset = store.create_content_asset(title="待删除")
    store.delete_content_asset(asset["id"])
    assert len(store.list_content_assets()) == 0


def test_policy_respects_authorization(tmp_path):
    store = AgentCoreStore(tmp_path / "core.db")
    store.grant_authorization("user-1", "marketing_trending_search")
    set_authorization_checker(store.is_authorized)
    policy = CapabilityPolicy()
    decision = policy.evaluate("marketing_trending_search", user_id="user-1")
    assert decision.allowed
    assert not decision.approval_required
    decision_unauth = policy.evaluate("marketing_trending_search", user_id="user-2")
    assert decision_unauth.approval_required
