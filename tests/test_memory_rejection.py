"""MEM-08: Structured rejection reasons."""

import pytest
from agent_core import AgentCoreStore, MemoryKind, TaskStatus


def test_rejection_reason_saved(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    task = store.create_task(session_id="s1", user_id="u1", objective="test")
    store.transition_task(task["id"], TaskStatus.RUNNING)

    c = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="u1", content="not good",
        evidence=[{"source": "c"}], confidence=0.5,
        task_id=task["id"],
    )
    store.update_memory_candidate(
        c["id"], status="rejected",
        rejection_reason="用户偏好AI赛道而非娱乐",
        task_id=task["id"],
    )
    reloaded = store.get_memory_candidate(c["id"])
    assert reloaded["status"] == "rejected"
    assert reloaded["rejection_reason"] == "用户偏好AI赛道而非娱乐"


def test_rejection_reason_in_event(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    task = store.create_task(session_id="s1", user_id="u1", objective="test")
    store.transition_task(task["id"], TaskStatus.RUNNING)

    c = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="u1", content="test",
        evidence=[{"source": "c"}], confidence=0.5,
        task_id=task["id"],
    )
    store.update_memory_candidate(
        c["id"], status="rejected",
        rejection_reason="替代方案：关注教育赛道",
        task_id=task["id"],
    )
    events = store.list_events(task["id"])
    reject_ev = [e for e in events if e["event_type"] == "memory.candidate.rejected"]
    assert len(reject_ev) == 1
    assert "替代方案" in reject_ev[0]["payload"]["rejection_reason"]


def test_rejected_to_verified_clears_reason(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    c = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="u1", content="test",
        evidence=[{"source": "c"}], confidence=0.5,
    )
    store.update_memory_candidate(c["id"], status="rejected",
                                   rejection_reason="wrong")
    store.update_memory_candidate(c["id"], status="verified")
    reloaded = store.get_memory_candidate(c["id"])
    assert reloaded["rejection_reason"] is None


def test_no_reason_does_not_fail(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    c = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="u1", content="test",
        evidence=[{"source": "c"}], confidence=0.5,
    )
    # reject without explicit reason — should work
    store.update_memory_candidate(c["id"], status="rejected")
    assert store.get_memory_candidate(c["id"])["status"] == "rejected"
