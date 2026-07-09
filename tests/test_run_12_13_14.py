"""RUN-12/13/14: scope isolation, manifest snapshot, observable timeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for sub in ("engine",):
    p = str(ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)

from agent_core.store import AgentCoreStore
from agent_core.models import TaskStatus, CapabilityLevel
from agent_core.tool_manifest import all_tools, tool_by_name
from agent_core.tool_gateway import get_tool_names_by_level
from agent_core.policy import CapabilityPolicy


# ── RUN-13: Manifest snapshot ─────────────────────────────────────────


# Frozen snapshot of the canonical tool manifest.
# If this snapshot changes, the test must be updated deliberately —
# accidental tool additions or removals are regressions.
EXPECTED_TOOL_NAMES = frozenset({
    # L0 read-only (28)
    "marketing_read_context",
    "marketing_research_web_search",
    "marketing_read_trends",
    "marketing_read_accounts",
    "marketing_read_suggestions",
    "marketing_read_dashboard",
    "marketing_read_profiles",
    "marketing_read_intelligence_report",
    "marketing_read_analytics",
    "marketing_read_publishing_tasks",
    "marketing_read_workflow_status",
    "marketing_read_intelligence_config",
    "marketing_read_memory_list",
    "marketing_read_content_list",
    "marketing_plan_content_production",
    "marketing_prepare_faceless_render",
    "marketing_read_learning_status",
    "marketing_read_learning_candidates",
    "marketing_read_weight_candidate_replay",
    "marketing_read_influence_score",
    "marketing_read_preflight_decision",
    "marketing_read_account_lifecycle",
    "marketing_read_benchmark_research",
    "marketing_read_account_positioning",
    "marketing_read_audience_snapshots",
    "marketing_read_account_experiments",
    "marketing_read_audience_gap",
    "marketing_read_strategy_candidates",
    # L1 reversible write (25)
    "marketing_plan_declare",
    "marketing_draft_memory_add",
    "marketing_draft_content_create",
    "marketing_draft_content_preflight",
    "marketing_draft_soft_article_create",
    "marketing_draft_faceless_video_create",
    "marketing_draft_content_from_experiment",
    "marketing_draft_content_decompose",
    "marketing_draft_content_review",
    "marketing_draft_weight_candidate_decide",
    "marketing_draft_audience_hypothesis",
    "marketing_draft_bind_prospect_strategy",
    "marketing_draft_audience_confirm",
    "marketing_draft_benchmark_add",
    "marketing_draft_benchmark_discover",
    "marketing_draft_benchmark_decide",
    "marketing_draft_benchmark_observation",
    "marketing_draft_benchmark_sample",
    "marketing_draft_account_positioning",
    "marketing_draft_account_positioning_approve",
    "marketing_draft_account_positioning_rollback",
    "marketing_draft_account_experiment",
    "marketing_draft_account_experiment_attach",
    "marketing_draft_strategy_candidate",
    "marketing_draft_strategy_decide",
    # L2 controlled resource (5)
    "marketing_trending_search",
    "marketing_session_login",
    "marketing_accounts_sync",
    "marketing_publish_prepare",
    "marketing_publish_query",
    # L3 external effect (1)
    "marketing_effect_publish",
})


def test_manifest_snapshot_tool_names():
    """RUN-13: the exact set of registered tool names must match the snapshot."""
    actual = {t.name for t in all_tools()}
    assert actual == EXPECTED_TOOL_NAMES, (
        f"Manifest drift: added={actual - EXPECTED_TOOL_NAMES}, "
        f"removed={EXPECTED_TOOL_NAMES - actual}"
    )


def test_manifest_snapshot_tool_count():
    """RUN-13: total tool count must match snapshot."""
    assert len(all_tools()) == 59


def test_manifest_snapshot_level_distribution():
    """RUN-13: capability level distribution must match snapshot."""
    tools = all_tools()
    by_level = {}
    for t in tools:
        by_level.setdefault(t.level, []).append(t.name)
    assert len(by_level[CapabilityLevel.READ_ONLY]) == 28
    assert len(by_level[CapabilityLevel.REVERSIBLE_WRITE]) == 25
    assert len(by_level[CapabilityLevel.CONTROLLED_RESOURCE]) == 5
    assert len(by_level[CapabilityLevel.EXTERNAL_EFFECT]) == 1
    assert CapabilityLevel.SYSTEM_FORBIDDEN not in by_level


def test_manifest_snapshot_gateway_names_by_level():
    """RUN-13: gateway level grouping matches manifest."""
    groups = get_tool_names_by_level()
    assert len(groups["L0_read_only"]) == 28
    assert len(groups["L1_reversible_write"]) == 25
    assert len(groups["L2_controlled_resource"]) == 5
    assert len(groups["L3_external_effect"]) == 1


def test_policy_rejects_unregistered_tool():
    """RUN-13: a tool name not in the manifest must be denied by policy."""
    policy = CapabilityPolicy()
    decision = policy.evaluate("marketing_evil_exfiltrate")
    assert not decision.allowed
    assert decision.level is CapabilityLevel.SYSTEM_FORBIDDEN


def test_policy_rejects_raw_system_tool():
    """RUN-13: system_ prefixed tools are permanently forbidden."""
    policy = CapabilityPolicy()
    decision = policy.evaluate("system_shell")
    assert not decision.allowed
    assert decision.level is CapabilityLevel.SYSTEM_FORBIDDEN


def test_policy_rejects_non_marketing_tool():
    """RUN-13: tools without a marketing_ prefix are denied by default."""
    policy = CapabilityPolicy()
    for name in ["read_file", "write_file", "terminal", "bash", "exec"]:
        decision = policy.evaluate(name)
        assert not decision.allowed, f"{name} should be denied"


def test_all_tools_have_marketing_prefix():
    """RUN-13: every registered tool must start with marketing_."""
    for tool in all_tools():
        assert tool.name.startswith("marketing_"), f"{tool.name} lacks marketing_ prefix"


def test_all_tools_have_object_schema():
    """RUN-13: every tool schema must be type=object with additionalProperties=False."""
    for tool in all_tools():
        assert tool.schema.get("type") == "object"
        assert tool.schema.get("additionalProperties") is False


def test_tool_by_name_roundtrip():
    """RUN-13: tool_by_name resolves every tool in the manifest."""
    for tool in all_tools():
        resolved = tool_by_name(tool.name)
        assert resolved is not None
        assert resolved.name == tool.name


# ── RUN-12: Project scope isolation ───────────────────────────────────


def test_dual_project_no_plan_pollution(tmp_path):
    """RUN-12: two tasks in different projects must not share plan state."""
    store = AgentCoreStore(tmp_path / "scope.db")

    t1 = store.create_task(session_id="sess-a", user_id="user-1", objective="项目A")
    t2 = store.create_task(session_id="sess-b", user_id="user-1", objective="项目B")
    store.transition_task(t1["id"], TaskStatus.RUNNING)
    store.transition_task(t2["id"], TaskStatus.RUNNING)

    plan_a = [
        {"id": "1", "description": "项目A步骤", "tool_name": "marketing_read_trends",
         "status": "completed", "kind": "tool"},
    ]
    plan_b = [
        {"id": "1", "description": "项目B步骤", "tool_name": "marketing_read_accounts",
         "status": "pending", "kind": "tool"},
    ]
    store.update_plan(t1["id"], plan_a)
    store.update_plan(t2["id"], plan_b)

    loaded_a = store.get_task(t1["id"])
    loaded_b = store.get_task(t2["id"])
    assert loaded_a["plan"][0]["description"] == "项目A步骤"
    assert loaded_b["plan"][0]["description"] == "项目B步骤"
    assert loaded_a["plan"][0]["status"] == "completed"
    assert loaded_b["plan"][0]["status"] == "pending"


def test_dual_project_no_event_pollution(tmp_path):
    """RUN-12: events from one task must not appear in another task's event list."""
    store = AgentCoreStore(tmp_path / "scope.db")

    t1 = store.create_task(session_id="sess-a", user_id="user-1", objective="项目A")
    t2 = store.create_task(session_id="sess-b", user_id="user-1", objective="项目B")
    store.transition_task(t1["id"], TaskStatus.RUNNING)
    store.transition_task(t2["id"], TaskStatus.RUNNING)

    store.append_event(t1["id"], "tool.started", {"tool": "marketing_read_trends"})
    store.append_event(t2["id"], "tool.started", {"tool": "marketing_read_accounts"})

    events_a = store.list_events(t1["id"])
    events_b = store.list_events(t2["id"])
    tool_events_a = [e for e in events_a if e["event_type"] == "tool.started"]
    tool_events_b = [e for e in events_b if e["event_type"] == "tool.started"]
    assert all(e["payload"].get("tool") == "marketing_read_trends" for e in tool_events_a)
    assert all(e["payload"].get("tool") == "marketing_read_accounts" for e in tool_events_b)
    assert len(tool_events_a) == 1
    assert len(tool_events_b) == 1


def test_dual_account_isolation(tmp_path):
    """RUN-12: tasks with different account_ids must not share memory scope."""
    store = AgentCoreStore(tmp_path / "scope.db")

    t1 = store.create_task(session_id="sess-a", user_id="user-1", objective="账号A", account_id="acc-a")
    t2 = store.create_task(session_id="sess-b", user_id="user-1", objective="账号B", account_id="acc-b")
    store.transition_task(t1["id"], TaskStatus.RUNNING)
    store.transition_task(t2["id"], TaskStatus.RUNNING)

    loaded_a = store.get_task(t1["id"])
    loaded_b = store.get_task(t2["id"])
    assert loaded_a["account_id"] == "acc-a"
    assert loaded_b["account_id"] == "acc-b"
    assert loaded_a["account_id"] != loaded_b["account_id"]


def test_dual_user_isolation(tmp_path):
    """RUN-12: tasks from different users must not share sessions."""
    store = AgentCoreStore(tmp_path / "scope.db")

    t1 = store.create_task(session_id="sess-a", user_id="user-1", objective="用户1")
    t2 = store.create_task(session_id="sess-b", user_id="user-2", objective="用户2")
    store.transition_task(t1["id"], TaskStatus.RUNNING)
    store.transition_task(t2["id"], TaskStatus.RUNNING)

    loaded_1 = store.get_task(t1["id"])
    loaded_2 = store.get_task(t2["id"])
    assert loaded_1["user_id"] == "user-1"
    assert loaded_2["user_id"] == "user-2"


def test_checkpoint_isolation(tmp_path):
    """RUN-12: checkpoints from one task must not leak into another."""
    store = AgentCoreStore(tmp_path / "scope.db")

    t1 = store.create_task(session_id="sess-a", user_id="user-1", objective="项目A")
    t2 = store.create_task(session_id="sess-b", user_id="user-1", objective="项目B")
    store.transition_task(t1["id"], TaskStatus.RUNNING)
    store.transition_task(t2["id"], TaskStatus.RUNNING)

    store.update_task_progress(t1["id"], checkpoint={
        "completed_steps": ["1", "2"],
        "failed_steps": [],
        "current_step": "3",
        "executed_effects": {"effect_a": {"capability": "x", "receipt_status": "ok"}},
        "pending_approval_id": None,
    })
    # t2 has no checkpoint
    loaded_a = store.get_task(t1["id"])
    loaded_b = store.get_task(t2["id"])
    assert loaded_a["checkpoint"]["completed_steps"] == ["1", "2"]
    assert loaded_b.get("checkpoint") is None or loaded_b.get("checkpoint") == {}


# ── RUN-14: Observable timeline ───────────────────────────────────────


def test_full_timeline_correlation(tmp_path):
    """RUN-14: a single task's event timeline has correlated IDs and correct ordering."""
    store = AgentCoreStore(tmp_path / "timeline.db")
    task = store.create_task(session_id="sess-1", user_id="user-1", objective="完整任务")
    store.transition_task(task["id"], TaskStatus.PLANNING)
    store.transition_task(task["id"], TaskStatus.RUNNING)

    # Simulate a full task lifecycle
    store.update_plan(task["id"], [
        {"id": "1", "description": "读取热点", "tool_name": "marketing_read_trends",
         "status": "running", "kind": "tool"},
    ])
    store.append_event(task["id"], "plan.ready", {
        "plan": store.get_task(task["id"])["plan"],
        "plan_version": 1, "plan_total": 1, "source": "declared",
    })
    store.append_event(task["id"], "step.update", {
        "label": "1/1", "status": "running",
        "plan_step_id": "1", "plan_total": 1, "plan_version": 1,
    })
    store.append_event(task["id"], "tool.started", {
        "tool_call_id": "tc_1", "tool": "marketing_read_trends",
        "arguments": {"query": "AI"},
    })
    store.append_event(task["id"], "tool.completed", {
        "tool_call_id": "tc_1", "tool": "marketing_read_trends",
        "arguments": {"query": "AI"}, "result": {"status": "ok", "data": []},
    })
    store.append_event(task["id"], "plan.updated", {
        "plan": [{"id": "1", "status": "completed"}],
        "plan_version": 1, "plan_total": 1,
    })
    store.append_event(task["id"], "effect.executed", {
        "effect_id": "effect_1", "capability": "marketing_read_trends",
        "receipt": {"status": "ok"},
    })
    store.append_event(task["id"], "approval.requested", {
        "approval_id": "approval_1", "capability": "marketing_trending_search",
        "arguments": {"platform": "douyin", "keyword": "AI"},
        "risk_summary": "搜索行业内容",
    })
    store.append_event(task["id"], "approval.decided", {
        "approval_id": "approval_1", "decision": "approved",
    })
    store.append_event(task["id"], "task.completed", {"reply": "分析完成"})

    events = store.list_events(task["id"])

    # All events must reference the same task_id
    for e in events:
        assert e["task_id"] == task["id"]

    # Events must be ordered by sequence
    sequences = [e["sequence"] for e in events]
    assert sequences == sorted(sequences)

    # Verify event type coverage
    event_types = [e["event_type"] for e in events]
    assert "task.created" in event_types or "status" in event_types  # transition creates events
    assert "plan.ready" in event_types
    assert "step.update" in event_types
    assert "tool.started" in event_types
    assert "tool.completed" in event_types
    assert "plan.updated" in event_types
    assert "effect.executed" in event_types
    assert "approval.requested" in event_types
    assert "approval.decided" in event_types
    assert "task.completed" in event_types

    # Tool call ID correlation: tool.started and tool.completed share tc_1
    started = next(e for e in events if e["event_type"] == "tool.started")
    completed = next(e for e in events if e["event_type"] == "tool.completed")
    assert started["payload"]["tool_call_id"] == completed["payload"]["tool_call_id"] == "tc_1"

    # Approval ID correlation: requested and decided share approval_1
    requested = next(e for e in events if e["event_type"] == "approval.requested")
    decided = next(e for e in events if e["event_type"] == "approval.decided")
    assert requested["payload"]["approval_id"] == decided["payload"]["approval_id"] == "approval_1"

    # Effect ID present in effect.executed
    effect_ev = next(e for e in events if e["event_type"] == "effect.executed")
    assert effect_ev["payload"]["effect_id"] == "effect_1"


def test_timeline_timestamps_present(tmp_path):
    """RUN-14: every event must have a created_at timestamp."""
    store = AgentCoreStore(tmp_path / "timeline.db")
    task = store.create_task(session_id="sess-1", user_id="user-1", objective="test")
    store.transition_task(task["id"], TaskStatus.RUNNING)
    store.append_event(task["id"], "tool.started", {"tool": "marketing_read_trends"})

    events = store.list_events(task["id"])
    for e in events:
        assert e["created_at"] is not None
        assert len(e["created_at"]) > 0


def test_timeline_sequential_ordering(tmp_path):
    """RUN-14: events retrieved via list_events_after must respect sequence."""
    store = AgentCoreStore(tmp_path / "timeline.db")
    task = store.create_task(session_id="sess-1", user_id="user-1", objective="test")
    store.transition_task(task["id"], TaskStatus.RUNNING)

    for i in range(5):
        store.append_event(task["id"], "step.update", {"index": i})

    events = store.list_events_after(task["id"], 0)
    indices = [e["payload"]["index"] for e in events if e["event_type"] == "step.update"]
    assert indices == [0, 1, 2, 3, 4]


def test_timeline_secret_redaction(tmp_path):
    """RUN-14: secrets in event payloads must be redacted."""
    store = AgentCoreStore(tmp_path / "timeline.db")
    task = store.create_task(session_id="sess-1", user_id="user-1", objective="test")
    store.transition_task(task["id"], TaskStatus.RUNNING)

    store.append_event(task["id"], "tool.completed", {
        "tool_call_id": "tc_1",
        "tool": "marketing_read_trends",
        "arguments": {"query": "AI"},
        "result": {"status": "ok", "data": "cookie: sessionid=secret123; token=abc"},
    })

    events = store.list_events(task["id"])
    tool_ev = next(e for e in events if e["event_type"] == "tool.completed")
    payload_str = str(tool_ev["payload"])
    assert "REDACTED" in payload_str
    assert "secret123" not in payload_str
    assert "cookie" not in payload_str
