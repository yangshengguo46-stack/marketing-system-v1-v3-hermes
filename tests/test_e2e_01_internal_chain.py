"""E2E-01: End-to-end internal chain test.

Verifies the full pipeline:
1. plan_declare → creates structured plan with steps
2. draft_content_create → creates content asset (reversible write)
3. effect tool call → gateway blocks, creates approval (pending_approval)
4. decide_approval → user approves
5. create_effect_intent → pre-log before execution
6. bridge_call → external MCP server invoked (mocked)
7. record_effect_receipt → execution result persisted
8. plan step auto-completes on tool success
9. Idempotency: re-submit same effect → same result, no duplicate
10. Crash recovery: new store instance sees consistent state

This test does NOT require Hermes runtime — it simulates the gateway
behavior using real store + plan_protocol + external_mcp_bridge.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ENGINE_ROOT = Path(__file__).parent.parent / "engine"
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from agent_core.store import AgentCoreStore
from agent_core.models import TaskStatus, ApprovalStatus, CapabilityLevel
from agent_core.plan_protocol import (
    validate_steps,
    merge_declared_plan,
    declare_plan,
    bind_step_on_tool_start,
    complete_step_on_tool_success,
)
from agent_core.tool_gateway import set_task_context, get_task_context
from agent_core.tool_manifest import all_tools, tool_by_name
from agent_core.external_mcp_bridge import (
    bridge_call,
    get_mapping,
    TOOL_MAPPINGS,
    HUIMEI_SERVER,
)


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path):
    return AgentCoreStore(tmp_path / "e2e.db")


@pytest.fixture
def ctx(store):
    """Set up a task and inject gateway task context."""
    session = store.create_or_get_session(user_id="user_e2e")
    task = store.create_task(
        session_id=session["id"],
        user_id="user_e2e",
        objective="发布一条抖音短视频",
    )
    store.transition_task(task["id"], TaskStatus.RUNNING)

    context = {
        "store": store,
        "task_id": task["id"],
        "user_id": "user_e2e",
        "account_id": "acct_test01",
        "session_auths": None,
    }
    set_task_context(context)
    yield context
    set_task_context(None)


# ── Step 1: Plan Declaration ─────────────────────────────────────────

class TestStep1PlanDeclare:
    """Agent declares a structured plan before any tool calls."""

    def test_plan_declared_with_valid_steps(self, store, ctx):
        steps = [
            {"description": "读取营销上下文", "tool_name": "marketing_read_context"},
            {"description": "创建内容草稿", "tool_name": "marketing_draft_content_create"},
            {"description": "发布到抖音", "tool_name": "marketing_effect_publish"},
        ]
        result = declare_plan({"steps": steps})
        parsed = json.loads(result)
        assert parsed["status"] == "ok"
        assert parsed["plan_total"] == 3

    def test_plan_persisted_in_store(self, store, ctx):
        steps = [
            {"description": "读取上下文", "tool_name": "marketing_read_context"},
            {"description": "创建草稿", "tool_name": "marketing_draft_content_create"},
        ]
        declare_plan({"steps": steps})
        task = store.get_task(ctx["task_id"])
        plan = task.get("plan", [])
        assert len(plan) == 2
        assert plan[0]["status"] == "pending"
        assert plan[0]["tool_name"] == "marketing_read_context"

    def test_plan_event_emitted(self, store, ctx):
        declare_plan({"steps": [{"description": "测试步骤", "tool_name": "marketing_read_context"}]})
        events = store.list_events(ctx["task_id"])
        event_types = [e["event_type"] for e in events]
        assert "plan.ready" in event_types

    def test_plan_rejects_unknown_tool(self, store, ctx):
        result = declare_plan({"steps": [{"description": "bad", "tool_name": "nonexistent_tool"}]})
        parsed = json.loads(result)
        assert parsed["status"] == "invalid"

    def test_plan_completed_steps_preserved_on_update(self, store, ctx):
        # First declaration
        declare_plan({"steps": [
            {"description": "读取上下文", "tool_name": "marketing_read_context"},
            {"description": "创建草稿", "tool_name": "marketing_draft_content_create"},
        ]})
        # Simulate step 1 completion
        task = store.get_task(ctx["task_id"])
        plan = task["plan"]
        plan[0]["status"] = "completed"
        store.update_plan(ctx["task_id"], plan)
        # Second declaration (agent updates remaining steps)
        declare_plan({"steps": [
            {"description": "创建新草稿", "tool_name": "marketing_draft_content_create"},
            {"description": "发布", "tool_name": "marketing_effect_publish"},
        ]})
        task = store.get_task(ctx["task_id"])
        plan = task["plan"]
        # First step preserved as completed
        assert plan[0]["status"] == "completed"
        assert plan[0]["description"] == "读取上下文"
        # New steps appended
        assert len(plan) == 3


# ── Step 2: Draft Content Creation ───────────────────────────────────

class TestStep2DraftContent:
    """Agent creates a content draft (reversible write, no approval needed)."""

    def test_plan_step_binds_on_tool_start(self, store, ctx):
        declare_plan({"steps": [
            {"description": "读取上下文", "tool_name": "marketing_read_context"},
            {"description": "创建草稿", "tool_name": "marketing_draft_content_create"},
        ]})
        task = store.get_task(ctx["task_id"])
        plan = task["plan"]
        # Simulate tool start
        changed = bind_step_on_tool_start(plan, "marketing_read_context")
        assert changed is True
        assert plan[0]["status"] == "running"

    def test_plan_step_completes_on_success(self, store, ctx):
        declare_plan({"steps": [
            {"description": "读取上下文", "tool_name": "marketing_read_context"},
        ]})
        task = store.get_task(ctx["task_id"])
        plan = task["plan"]
        bind_step_on_tool_start(plan, "marketing_read_context")
        changed = complete_step_on_tool_success(plan, "marketing_read_context")
        assert changed is True
        assert plan[0]["status"] == "completed"

    def test_draft_tool_is_reversible_write(self):
        """Draft tools should be REVERSIBLE_WRITE level, no approval."""
        tool = tool_by_name("marketing_draft_content_create")
        assert tool is not None
        assert tool.level == CapabilityLevel.REVERSIBLE_WRITE
        assert tool.requires_approval is False


# ── Step 3: Effect Tool → Approval Required ──────────────────────────

class TestStep3EffectApproval:
    """Effect tools must trigger approval, not execute directly."""

    def test_effect_tool_requires_approval(self):
        tool = tool_by_name("marketing_effect_publish")
        assert tool is not None
        assert tool.level == CapabilityLevel.EXTERNAL_EFFECT
        assert tool.requires_approval is True

    def test_gateway_creates_approval_for_effect(self, store, ctx):
        # Simulate what the gateway does for an effect tool
        approval = store.create_approval(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            arguments={"asset_id": "asset_001", "platform": "douyin"},
            risk_summary="将内容资产发布到抖音平台，此操作不可撤销",
        )
        assert approval["status"] == ApprovalStatus.PENDING.value
        assert approval["capability"] == "marketing_effect_publish"

        # Task should transition to WAITING_USER
        task = store.get_task(ctx["task_id"])
        assert task["status"] == TaskStatus.WAITING_USER.value

    def test_approval_event_emitted(self, store, ctx):
        store.create_approval(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            arguments={"asset_id": "asset_001", "platform": "douyin"},
            risk_summary="发布到抖音",
        )
        events = store.list_events(ctx["task_id"])
        event_types = [e["event_type"] for e in events]
        assert "approval.requested" in event_types


# ── Step 4: User Approves ────────────────────────────────────────────

class TestStep4UserApproves:
    """User reviews and approves the effect."""

    def test_approval_granted_transitions_task_to_running(self, store, ctx):
        approval = store.create_approval(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            arguments={"asset_id": "asset_001", "platform": "douyin"},
            risk_summary="发布到抖音",
        )
        # User approves
        result = store.decide_approval(approval["id"], approved=True, reason="用户确认发布")
        assert result["status"] == ApprovalStatus.APPROVED.value

        # Task back to running
        task = store.get_task(ctx["task_id"])
        assert task["status"] == TaskStatus.RUNNING.value

    def test_approval_rejected_transitions_task_to_paused(self, store, ctx):
        approval = store.create_approval(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            arguments={"asset_id": "asset_001", "platform": "douyin"},
            risk_summary="发布到抖音",
        )
        result = store.decide_approval(approval["id"], approved=False, reason="用户拒绝")
        assert result["status"] == ApprovalStatus.REJECTED.value

        task = store.get_task(ctx["task_id"])
        assert task["status"] == TaskStatus.PAUSED.value

    def test_approval_decision_event_emitted(self, store, ctx):
        approval = store.create_approval(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            arguments={"asset_id": "asset_001"},
            risk_summary="发布",
        )
        store.decide_approval(approval["id"], approved=True)
        events = store.list_events(ctx["task_id"])
        decisions = [e for e in events if e["event_type"] == "approval.decided"]
        assert len(decisions) >= 1
        assert decisions[-1]["payload"]["decision"] == "approved"


# ── Step 5: Effect Intent (Pre-log) ──────────────────────────────────

class TestStep5EffectIntent:
    """Before executing the effect, create an intent (pre-log)."""

    def test_intent_created_with_approved_approval(self, store, ctx):
        approval = store.create_approval(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            arguments={"asset_id": "asset_001", "platform": "douyin"},
            risk_summary="发布",
        )
        store.decide_approval(approval["id"], approved=True)

        effect = store.create_effect_intent(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            idempotency_key="publish_douyin_001",
            preview={"asset_id": "asset_001", "platform": "douyin"},
            approval_id=approval["id"],
        )
        assert effect["status"] == "pending"
        assert effect["capability"] == "marketing_effect_publish"
        assert effect["idempotency_key"] == "publish_douyin_001"

    def test_intent_rejected_without_approval(self, store, ctx):
        with pytest.raises(PermissionError):
            store.create_effect_intent(
                task_id=ctx["task_id"],
                capability="marketing_effect_publish",
                idempotency_key="publish_002",
                preview={"asset_id": "asset_001"},
                approval_id="fake_approval_id",
            )

    def test_intent_event_emitted(self, store, ctx):
        approval = store.create_approval(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            arguments={"asset_id": "asset_001"},
            risk_summary="发布",
        )
        store.decide_approval(approval["id"], approved=True)
        store.create_effect_intent(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            idempotency_key="publish_003",
            preview={"asset_id": "asset_001"},
            approval_id=approval["id"],
        )
        events = store.list_events(ctx["task_id"])
        event_types = [e["event_type"] for e in events]
        assert "effect.intent_created" in event_types


# ── Step 6: Bridge Call (External MCP) ───────────────────────────────

class TestStep6BridgeCall:
    """After approval, the effect is dispatched to external MCP server."""

    def test_bridge_call_to_huimei_publish(self):
        """Simulate calling huimei publish through the bridge."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout.readline.return_value = (
            '{"jsonrpc":"2.0","id":1,"result":{"success":true,"task_id":"htask_001"}}'
        )
        with patch("shutil.which", return_value="/usr/local/bin/huimei-mcp-server"):
            with patch("subprocess.Popen", return_value=mock_process):
                result = bridge_call("marketing_external_publish", {
                    "platforms": ["douyin"],
                    "media_type": "video",
                    "file_path": "/tmp/video.mp4",
                    "title": "测试视频",
                    "description": "E2E测试",
                })
        assert result["status"] == "ok"
        assert result["server"] == "huimei"
        assert result["tool"] == "huimei_publish"

    def test_bridge_unavailable_returns_error_not_crash(self):
        with patch("shutil.which", return_value=None):
            result = bridge_call("marketing_external_publish", {})
        assert result["status"] == "unavailable"
        assert "huimei" in result["error"]

    def test_bridge_call_to_voice_clone(self):
        """Simulate calling TTS through the bridge."""
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout.readline.return_value = (
            '{"jsonrpc":"2.0","id":1,"result":{"audio_path":"/tmp/output.wav"}}'
        )
        with patch("shutil.which", return_value="/usr/local/bin/python"):
            with patch("subprocess.Popen", return_value=mock_process):
                result = bridge_call("marketing_external_tts", {
                    "text": "大家好，今天分享一个技巧",
                    "voice_id": "v_001",
                })
        assert result["status"] == "ok"
        assert result["server"] == "voice-clone"
        assert result["tool"] == "speak"


# ── Step 7: Record Effect Receipt ────────────────────────────────────

class TestStep7RecordReceipt:
    """After external tool returns, record the receipt."""

    def test_receipt_recorded(self, store, ctx):
        approval = store.create_approval(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            arguments={"asset_id": "asset_001"},
            risk_summary="发布",
        )
        store.decide_approval(approval["id"], approved=True)
        effect = store.create_effect_intent(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            idempotency_key="publish_receipt_001",
            preview={"asset_id": "asset_001"},
            approval_id=approval["id"],
        )
        receipt = store.record_effect_receipt(effect["id"], {
            "success": True,
            "platform_task_id": "htask_001",
            "published_at": "2026-07-02T22:00:00Z",
        })
        assert receipt["status"] == "executed"
        assert receipt["receipt"]["success"] is True

    def test_receipt_event_emitted(self, store, ctx):
        approval = store.create_approval(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            arguments={"asset_id": "asset_001"},
            risk_summary="发布",
        )
        store.decide_approval(approval["id"], approved=True)
        effect = store.create_effect_intent(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            idempotency_key="publish_receipt_002",
            preview={},
            approval_id=approval["id"],
        )
        store.record_effect_receipt(effect["id"], {"success": True})
        events = store.list_events(ctx["task_id"])
        event_types = [e["event_type"] for e in events]
        assert "effect.executed" in event_types


# ── Step 8: Plan Step Auto-Complete ──────────────────────────────────

class TestStep8PlanAutoComplete:
    """Plan step bound to the effect tool should complete after success."""

    def test_effect_step_completes_after_receipt(self, store, ctx):
        declare_plan({"steps": [
            {"description": "读取上下文", "tool_name": "marketing_read_context"},
            {"description": "创建草稿", "tool_name": "marketing_draft_content_create"},
            {"description": "发布到抖音", "tool_name": "marketing_effect_publish"},
        ]})
        task = store.get_task(ctx["task_id"])
        plan = task["plan"]

        # Simulate steps 1 and 2 completing
        bind_step_on_tool_start(plan, "marketing_read_context")
        complete_step_on_tool_success(plan, "marketing_read_context")
        bind_step_on_tool_start(plan, "marketing_draft_content_create")
        complete_step_on_tool_success(plan, "marketing_draft_content_create")

        # Step 3: effect tool starts
        bind_step_on_tool_start(plan, "marketing_effect_publish")
        assert plan[2]["status"] == "running"

        # Effect succeeds
        complete_step_on_tool_success(plan, "marketing_effect_publish")
        assert plan[2]["status"] == "completed"

        # All steps done
        assert all(s["status"] == "completed" for s in plan)


# ── Step 9: Idempotency ──────────────────────────────────────────────

class TestStep9Idempotency:
    """Re-submitting the same effect should not create duplicates."""

    def test_same_idempotency_key_returns_same_effect(self, store, ctx):
        approval = store.create_approval(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            arguments={"asset_id": "asset_001"},
            risk_summary="发布",
        )
        store.decide_approval(approval["id"], approved=True)

        effect1 = store.create_effect_intent(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            idempotency_key="idempotent_001",
            preview={"asset_id": "asset_001"},
            approval_id=approval["id"],
        )
        effect2 = store.create_effect_intent(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            idempotency_key="idempotent_001",
            preview={"asset_id": "asset_001"},
            approval_id=approval["id"],
        )
        assert effect1["id"] == effect2["id"]

    def test_double_receipt_is_idempotent(self, store, ctx):
        approval = store.create_approval(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            arguments={"asset_id": "asset_001"},
            risk_summary="发布",
        )
        store.decide_approval(approval["id"], approved=True)
        effect = store.create_effect_intent(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            idempotency_key="idempotent_002",
            preview={},
            approval_id=approval["id"],
        )
        receipt1 = store.record_effect_receipt(effect["id"], {"success": True, "ts": "t1"})
        receipt2 = store.record_effect_receipt(effect["id"], {"success": True, "ts": "t2"})
        # Second receipt should not overwrite
        assert receipt1["id"] == receipt2["id"]
        assert receipt2["receipt"]["ts"] == "t1"


# ── Step 10: Crash Recovery ──────────────────────────────────────────

class TestStep10CrashRecovery:
    """After process restart, state should be consistent."""

    def test_state_survives_store_recreation(self, store, ctx, tmp_path):
        approval = store.create_approval(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            arguments={"asset_id": "asset_001"},
            risk_summary="发布",
        )
        store.decide_approval(approval["id"], approved=True)
        effect = store.create_effect_intent(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            idempotency_key="crash_001",
            preview={"asset_id": "asset_001"},
            approval_id=approval["id"],
        )
        store.record_effect_receipt(effect["id"], {"success": True})

        # Simulate crash: create new store instance pointing to same DB
        new_store = AgentCoreStore(tmp_path / "e2e.db")
        task = new_store.get_task(ctx["task_id"])
        assert task is not None
        assert task["status"] == TaskStatus.RUNNING.value

        # Effect should still show as executed
        recovered_effect = new_store.get_effect(effect["id"])
        assert recovered_effect["status"] == "executed"
        assert recovered_effect["receipt"]["success"] is True

        # Events should be intact
        events = new_store.list_events(ctx["task_id"])
        event_types = [e["event_type"] for e in events]
        assert "effect.intent_created" in event_types
        assert "effect.executed" in event_types
        assert "approval.requested" in event_types
        assert "approval.decided" in event_types

    def test_pending_effect_detected_after_crash(self, store, ctx, tmp_path):
        """If crash happened between intent and receipt, effect is still pending."""
        approval = store.create_approval(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            arguments={"asset_id": "asset_001"},
            risk_summary="发布",
        )
        store.decide_approval(approval["id"], approved=True)
        effect = store.create_effect_intent(
            task_id=ctx["task_id"],
            capability="marketing_effect_publish",
            idempotency_key="crash_pending_001",
            preview={"asset_id": "asset_001"},
            approval_id=approval["id"],
        )
        # No receipt recorded — crash happened

        new_store = AgentCoreStore(tmp_path / "e2e.db")
        recovered = new_store.get_effect(effect["id"])
        assert recovered["status"] == "pending"  # Can be retried safely


# ── Full Chain Integration ───────────────────────────────────────────

class TestFullChain:
    """Complete chain: plan → draft → approval → effect → bridge → receipt."""

    def test_complete_publishing_workflow(self, store, ctx, tmp_path):
        task_id = ctx["task_id"]

        # 1. Declare plan
        result = declare_plan({"steps": [
            {"description": "读取营销上下文", "tool_name": "marketing_read_context"},
            {"description": "创建内容草稿", "tool_name": "marketing_draft_content_create"},
            {"description": "发布到抖音", "tool_name": "marketing_effect_publish"},
        ]})
        assert json.loads(result)["status"] == "ok"

        # 2. Simulate step 1 (read — no approval)
        task = store.get_task(task_id)
        plan = task["plan"]
        bind_step_on_tool_start(plan, "marketing_read_context")
        complete_step_on_tool_success(plan, "marketing_read_context")
        store.update_plan(task_id, plan)

        # 3. Simulate step 2 (draft — no approval, reversible)
        task = store.get_task(task_id)
        plan = task["plan"]
        bind_step_on_tool_start(plan, "marketing_draft_content_create")
        complete_step_on_tool_success(plan, "marketing_draft_content_create")
        store.update_plan(task_id, plan)

        # 4. Step 3: effect — requires approval
        task = store.get_task(task_id)
        plan = task["plan"]
        bind_step_on_tool_start(plan, "marketing_effect_publish")
        store.update_plan(task_id, plan)

        approval = store.create_approval(
            task_id=task_id,
            capability="marketing_effect_publish",
            arguments={"asset_id": "asset_001", "platform": "douyin"},
            risk_summary="将内容资产 asset_001 发布到抖音平台",
        )
        # Task → WAITING_USER
        task = store.get_task(task_id)
        assert task["status"] == TaskStatus.WAITING_USER.value

        # 5. User approves
        store.decide_approval(approval["id"], approved=True, reason="用户确认")
        task = store.get_task(task_id)
        assert task["status"] == TaskStatus.RUNNING.value

        # 6. Create effect intent (pre-log)
        effect = store.create_effect_intent(
            task_id=task_id,
            capability="marketing_effect_publish",
            idempotency_key="e2e_full_chain_001",
            preview={"asset_id": "asset_001", "platform": "douyin"},
            approval_id=approval["id"],
        )
        assert effect["status"] == "pending"

        # 7. Bridge call to external MCP (mocked)
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout.readline.return_value = (
            '{"jsonrpc":"2.0","id":1,"result":{"success":true,"platform_task_id":"dt_001"}}'
        )
        with patch("shutil.which", return_value="/usr/local/bin/huimei-mcp-server"):
            with patch("subprocess.Popen", return_value=mock_process):
                bridge_result = bridge_call("marketing_external_publish", {
                    "platforms": ["douyin"],
                    "media_type": "video",
                    "file_path": "/tmp/video.mp4",
                    "title": "E2E测试视频",
                    "description": "端到端链路测试",
                })
        assert bridge_result["status"] == "ok"

        # 8. Record receipt
        receipt = store.record_effect_receipt(effect["id"], {
            "success": True,
            "platform_task_id": "dt_001",
            "bridge_status": bridge_result["status"],
            "server": bridge_result["server"],
        })
        assert receipt["status"] == "executed"

        # 9. Complete plan step
        task = store.get_task(task_id)
        plan = task["plan"]
        complete_step_on_tool_success(plan, "marketing_effect_publish")
        store.update_plan(task_id, plan)
        task = store.get_task(task_id)
        assert all(s["status"] == "completed" for s in task["plan"])

        # 10. Verify full event chain
        events = store.list_events(task_id)
        event_types = [e["event_type"] for e in events]
        assert "plan.ready" in event_types
        assert "approval.requested" in event_types
        assert "approval.decided" in event_types
        assert "effect.intent_created" in event_types
        assert "effect.executed" in event_types

        # 11. Crash recovery: new store sees consistent state
        new_store = AgentCoreStore(tmp_path / "e2e.db")
        recovered_task = new_store.get_task(task_id)
        assert all(s["status"] == "completed" for s in recovered_task["plan"])
        recovered_effect = new_store.get_effect(effect["id"])
        assert recovered_effect["status"] == "executed"
        assert recovered_effect["receipt"]["success"] is True
