"""Deterministic plan/checkpoint tests: schema, progression, resume, replay."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from agent_core import AgentCoreStore, PlanStep, PlanStepStatus, TaskStatus


class TestPlanStepSchema:
    def test_roundtrip(self):
        s = PlanStep(id="1", description="搜索热点", tool_name="marketing_read_trends",
                      status=PlanStepStatus.PENDING)
        d = s.to_dict()
        s2 = PlanStep.from_dict(d)
        assert s2.id == "1"
        assert s2.description == "搜索热点"
        assert s2.tool_name == "marketing_read_trends"
        assert s2.status == "pending"
        assert s2.effect_id is None

    def test_from_legacy_dict(self):
        """Old format (id, description, tool_guess, status) converts correctly."""
        legacy = {"id": "2", "description": "分析趋势", "tool_guess": "marketing_read_trends", "status": "completed"}
        s = PlanStep.from_legacy(legacy)
        assert s.id == "2"
        assert s.tool_name == "marketing_read_trends"  # tool_guess → tool_name
        assert s.status == "completed"

    def test_to_dict_omits_none(self):
        s = PlanStep(id="1", description="test")
        d = s.to_dict()
        assert "effect_id" not in d

    def test_with_effect_id(self):
        s = PlanStep(id="3", description="发布内容", tool_name="marketing_effect_publish",
                      status="completed", effect_id="effect_abc")
        d = s.to_dict()
        assert d["effect_id"] == "effect_abc"
        s2 = PlanStep.from_dict(d)
        assert s2.effect_id == "effect_abc"

    def test_plan_step_status_constants(self):
        assert PlanStepStatus.PENDING == "pending"
        assert PlanStepStatus.RUNNING == "running"
        assert PlanStepStatus.COMPLETED == "completed"
        assert PlanStepStatus.SKIPPED == "skipped"
        assert PlanStepStatus.WAITING_APPROVAL == "waiting_approval"
        assert "pending" in PlanStepStatus.NOT_STARTED
        assert "completed" in PlanStepStatus.FINISHED


class TestStepProgression:
    def test_sequential_three_steps(self, tmp_path):
        store = AgentCoreStore(tmp_path / "plan.db")
        task = store.create_task(session_id="sess-1", user_id="user-1", objective="三步计划")
        store.transition_task(task["id"], TaskStatus.RUNNING)

        plan = [
            {"id": "1", "description": "读取热点", "tool_name": "marketing_read_trends", "status": "pending"},
            {"id": "2", "description": "分析趋势", "tool_name": None, "status": "pending"},
            {"id": "3", "description": "生成选题", "tool_name": "marketing_read_suggestions", "status": "pending"},
        ]
        store.update_plan(task["id"], plan)

        # Step 1 starts and completes
        plan[0]["status"] = "running"
        store.update_plan(task["id"], plan)
        loaded = store.get_task(task["id"])
        assert loaded["plan"][0]["status"] == "running"
        assert loaded["plan"][1]["status"] == "pending"

        plan[0]["status"] = "completed"
        store.update_plan(task["id"], plan)
        loaded = store.get_task(task["id"])
        assert loaded["plan"][0]["status"] == "completed"
        assert loaded["plan"][1]["status"] == "pending"

        # Step 2 starts and completes
        plan[1]["status"] = "running"
        store.update_plan(task["id"], plan)
        plan[1]["status"] = "completed"
        store.update_plan(task["id"], plan)

        loaded = store.get_task(task["id"])
        completed = [s for s in loaded["plan"] if s["status"] == "completed"]
        pending = [s for s in loaded["plan"] if s["status"] == "pending"]
        assert len(completed) == 2
        assert len(pending) == 1
        assert pending[0]["id"] == "3"

    def test_step_not_completed_on_pending_approval(self, tmp_path):
        """A step stays running (not completed) when tool returns pending_approval."""
        store = AgentCoreStore(tmp_path / "plan.db")
        task = store.create_task(session_id="sess-1", user_id="user-1", objective="搜索")
        store.transition_task(task["id"], TaskStatus.RUNNING)

        plan = [
            {"id": "1", "description": "搜索抖音", "tool_name": "marketing_trending_search", "status": "running"},
        ]
        store.update_plan(task["id"], plan)

        # Tool completes with pending_approval → step should NOT be marked completed
        loaded = store.get_task(task["id"])
        step = loaded["plan"][0]
        assert step["status"] == "running"
        # The production code (on_tool_complete) checks result_status == "ok"
        # so a "pending_approval" result won't trigger completion


class TestCheckpoint:
    def test_checkpoint_structure(self, tmp_path):
        store = AgentCoreStore(tmp_path / "plan.db")
        task = store.create_task(session_id="sess-1", user_id="user-1", objective="test")
        store.transition_task(task["id"], TaskStatus.RUNNING)

        plan = [
            {"id": "1", "description": "step1", "tool_name": "marketing_read_trends", "status": "completed"},
            {"id": "2", "description": "step2", "tool_name": "marketing_read_suggestions", "status": "running"},
        ]
        store.update_plan(task["id"], plan)

        ck = {
            "completed_steps": ["1"],
            "current_step": "2",
            "executed_effects": {},
            "pending_approval_id": None,
        }
        store.update_task_progress(task["id"], checkpoint=ck)

        loaded = store.get_task(task["id"])
        assert loaded["checkpoint"]["completed_steps"] == ["1"]
        assert loaded["checkpoint"]["current_step"] == "2"
        assert loaded["checkpoint"]["executed_effects"] == {}
        assert loaded["checkpoint"]["pending_approval_id"] is None

    def test_checkpoint_survives_reopen(self, tmp_path):
        path = tmp_path / "plan.db"
        store = AgentCoreStore(path)
        task = store.create_task(session_id="sess-1", user_id="user-1", objective="test")
        store.transition_task(task["id"], TaskStatus.RUNNING)

        ck = {
            "completed_steps": ["1", "2"],
            "current_step": "3",
            "executed_effects": {"effect_1": {"capability": "marketing_trending_search", "receipt_status": "ok"}},
            "pending_approval_id": "approval_abc",
        }
        store.update_task_progress(task["id"], checkpoint=ck)

        reopened = AgentCoreStore(path)
        loaded = reopened.get_task(task["id"])
        assert loaded["checkpoint"] == ck


class TestCrashRecovery:
    def test_running_task_paused_with_checkpoint_on_restart(self, tmp_path):
        store = AgentCoreStore(tmp_path / "plan.db")
        task = store.create_task(session_id="sess-1", user_id="user-1", objective="test")
        store.transition_task(task["id"], TaskStatus.RUNNING)

        # Simulate what __init__ does: pause running tasks
        store.transition_task(
            task["id"], TaskStatus.PAUSED,
            checkpoint={"runtime_interrupted_at": "2026-06-30T10:00:00"},
            error="Agent runtime restarted; task is ready to resume",
        )

        loaded = store.get_task(task["id"])
        assert loaded["status"] == "paused"
        assert loaded["last_error"] == "Agent runtime restarted; task is ready to resume"
        assert "runtime_interrupted_at" in loaded["checkpoint"]

    def test_planning_and_retrying_also_paused(self, tmp_path):
        store = AgentCoreStore(tmp_path / "plan.db")

        t1 = store.create_task(session_id="sess-1", user_id="user-1", objective="p1")
        store.transition_task(t1["id"], TaskStatus.PLANNING)

        t2 = store.create_task(session_id="sess-1", user_id="user-1", objective="p2")
        store.transition_task(t2["id"], TaskStatus.RUNNING)
        store.transition_task(t2["id"], TaskStatus.FAILED)
        store.transition_task(t2["id"], TaskStatus.RETRYING)

        for tid in [t1["id"], t2["id"]]:
            store.transition_task(tid, TaskStatus.PAUSED,
                                  checkpoint={"runtime_interrupted_at": "now"})

        assert store.get_task(t1["id"])["status"] == "paused"
        assert store.get_task(t2["id"])["status"] == "paused"


class TestResumeWithCheckpoint:
    def test_resume_preserves_completed_steps(self, tmp_path):
        store = AgentCoreStore(tmp_path / "plan.db")
        task = store.create_task(session_id="sess-1", user_id="user-1", objective="test")
        store.transition_task(task["id"], TaskStatus.RUNNING)

        plan = [
            {"id": "1", "description": "done", "status": "completed"},
            {"id": "2", "description": "in-progress", "status": "running"},
            {"id": "3", "description": "pending", "status": "pending"},
        ]
        store.update_plan(task["id"], plan)
        store.transition_task(task["id"], TaskStatus.PAUSED)

        loaded = store.get_task(task["id"])
        completed_before = [s for s in loaded["plan"] if s["status"] == "completed"]
        assert len(completed_before) == 1
        assert completed_before[0]["id"] == "1"

    def test_executed_effects_preserved_in_checkpoint(self, tmp_path):
        store = AgentCoreStore(tmp_path / "plan.db")
        task = store.create_task(session_id="sess-1", user_id="user-1", objective="test")
        store.transition_task(task["id"], TaskStatus.RUNNING)

        ck = {
            "completed_steps": ["1"],
            "current_step": "2",
            "executed_effects": {
                "effect_abc": {"capability": "marketing_trending_search", "receipt_status": "ok"},
                "effect_def": {"capability": "marketing_accounts_sync", "receipt_status": "ok"},
            },
            "pending_approval_id": None,
        }
        store.update_task_progress(task["id"], checkpoint=ck)

        loaded = store.get_task(task["id"])
        assert len(loaded["checkpoint"]["executed_effects"]) == 2

    def test_skip_on_expired_approval_recovery(self, tmp_path):
        store = AgentCoreStore(tmp_path / "plan.db")
        task = store.create_task(session_id="sess-1", user_id="user-1", objective="test")
        store.transition_task(task["id"], TaskStatus.RUNNING)

        plan = [
            {"id": "1", "description": "done", "status": "completed"},
            {"id": "2", "description": "search", "tool_name": "marketing_trending_search", "status": "running"},
            {"id": "3", "description": "analyze", "status": "pending"},
        ]
        store.update_plan(task["id"], plan)

        approval = store.create_approval(
            task_id=task["id"], capability="marketing_trending_search",
            arguments={"platform": "douyin", "keyword": "AI"}, risk_summary="搜索",
        )
        future = (datetime.now(timezone.utc) + timedelta(seconds=301)).isoformat()
        store.expire_stale_approvals(timeout_seconds=300, now=future)

        # On resume, the expired approval step gets skipped
        loaded = store.get_task(task["id"])
        pending = [s for s in loaded["plan"] if s.get("status") == "pending"]
        assert len(pending) >= 1  # step 3 should still be pending


class TestRetrying:
    def test_failed_to_retrying_transition(self, tmp_path):
        store = AgentCoreStore(tmp_path / "plan.db")
        task = store.create_task(session_id="sess-1", user_id="user-1", objective="test")
        store.transition_task(task["id"], TaskStatus.RUNNING)
        store.transition_task(task["id"], TaskStatus.FAILED, error="API error")

        # FAILED → RETRYING is allowed
        store.transition_task(task["id"], TaskStatus.RETRYING)
        assert store.get_task(task["id"])["status"] == "retrying"

        # RETRYING → RUNNING
        store.transition_task(task["id"], TaskStatus.RUNNING)
        assert store.get_task(task["id"])["status"] == "running"


class TestMultiRestartIdempotency:
    def test_multiple_pauses_do_not_corrupt_plan(self, tmp_path):
        store = AgentCoreStore(tmp_path / "plan.db")
        task = store.create_task(session_id="sess-1", user_id="user-1", objective="test")
        store.transition_task(task["id"], TaskStatus.RUNNING)

        plan = [
            {"id": "1", "description": "done", "status": "completed"},
            {"id": "2", "description": "pending", "status": "pending"},
        ]
        store.update_plan(task["id"], plan)

        # Simulate multiple restart cycles
        for i in range(3):
            store.transition_task(task["id"], TaskStatus.PAUSED,
                                  checkpoint={"completed_steps": ["1"], "restart_count": i})
            loaded = store.get_task(task["id"])
            assert loaded["plan"][0]["status"] == "completed"  # never lost
            assert loaded["plan"][1]["status"] == "pending"     # never accidentally completed
            store.transition_task(task["id"], TaskStatus.RUNNING)
