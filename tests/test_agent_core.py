import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from agent_core import AgentCoreStore, CapabilityLevel, CapabilityPolicy, MemoryKind, TaskStatus


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
        task_id=task["id"], capability="marketing.effect.publish",
        arguments={"platform": "douyin"}, risk_summary="将向抖音正式发布内容",
    )
    assert store.get_task(task["id"])["status"] == "waiting_user"

    with pytest.raises(PermissionError):
        store.create_effect_intent(
            task_id=task["id"], capability="marketing.effect.publish",
            idempotency_key="publish:1", preview={"title": "草稿"}, approval_id=approval["id"],
        )

    store.decide_approval(approval["id"], True, "用户确认预览")
    effect = store.create_effect_intent(
        task_id=task["id"], capability="marketing.effect.publish",
        idempotency_key="publish:1", preview={"title": "草稿"}, approval_id=approval["id"],
    )
    duplicate = store.create_effect_intent(
        task_id=task["id"], capability="marketing.effect.publish",
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
    assert policy.evaluate("marketing.read.trends").allowed
    assert policy.evaluate("marketing.effect.publish").approval_required
    shell = policy.evaluate("system.shell")
    assert not shell.allowed and shell.level is CapabilityLevel.SYSTEM_FORBIDDEN
    assert not policy.evaluate("unknown.tool").allowed

