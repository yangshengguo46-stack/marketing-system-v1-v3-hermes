"""MEM-01: Typed memory events with provenance."""

import pytest
from agent_core import AgentCoreStore, MemoryKind, TaskStatus
from agent_core.store import (
    MEMORY_EVENT_CREATED, MEMORY_EVENT_ADOPTED, MEMORY_EVENT_REJECTED,
    MEMORY_EVENT_MODIFIED, MEMORY_EVENT_SUPERSEDED, MEMORY_EVENT_FORGOTTEN,
    MEMORY_PROVENANCE_TYPES,
)


def test_created_event_generated(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    task = store.create_task(session_id="s1", user_id="u1", objective="test")
    store.transition_task(task["id"], TaskStatus.RUNNING)

    c = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="u1", content="偏好AI教育",
        evidence=[{"source": "conversation"}], confidence=0.9,
        task_id=task["id"], provenance="agent_inference",
    )
    events = store.list_events(task["id"])
    mem_events = [e for e in events if e["event_type"].startswith("memory.")]
    assert len(mem_events) == 1
    assert mem_events[0]["event_type"] == MEMORY_EVENT_CREATED
    assert mem_events[0]["payload"]["memory_id"] == c["id"]
    assert mem_events[0]["payload"]["provenance"] == "agent_inference"


def test_adopted_event_generated(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    task = store.create_task(session_id="s1", user_id="u1", objective="test")
    store.transition_task(task["id"], TaskStatus.RUNNING)

    c = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="u1", content="偏好AI",
        evidence=[{"source": "c"}], confidence=0.5,
        task_id=task["id"],
    )
    store.update_memory_candidate(c["id"], status="verified", task_id=task["id"])
    events = store.list_events(task["id"])
    adopt = [e for e in events if e["event_type"] == MEMORY_EVENT_ADOPTED]
    assert len(adopt) == 1
    assert adopt[0]["payload"]["previous_status"] == "pending"


def test_rejected_event_generated(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    task = store.create_task(session_id="s1", user_id="u1", objective="test")
    store.transition_task(task["id"], TaskStatus.RUNNING)

    c = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="u1", content="不推荐",
        evidence=[{"source": "c"}], confidence=0.5,
        task_id=task["id"],
    )
    store.update_memory_candidate(c["id"], status="rejected", task_id=task["id"])
    events = store.list_events(task["id"])
    reject = [e for e in events if e["event_type"] == MEMORY_EVENT_REJECTED]
    assert len(reject) == 1


def test_modified_event_generated(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    task = store.create_task(session_id="s1", user_id="u1", objective="test")
    store.transition_task(task["id"], TaskStatus.RUNNING)

    c = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="u1", content="old",
        evidence=[{"source": "c"}], confidence=0.6,
        task_id=task["id"],
    )
    store.update_memory_candidate(c["id"], content="new", task_id=task["id"])
    events = store.list_events(task["id"])
    modify = [e for e in events if e["event_type"] == MEMORY_EVENT_MODIFIED]
    assert len(modify) == 1


def test_superseded_event_generated(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    task = store.create_task(session_id="s1", user_id="u1", objective="test")
    store.transition_task(task["id"], TaskStatus.RUNNING)

    store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="u1", content="v1",
        evidence=[{"source": "c"}], confidence=0.7,
        task_id=task["id"],
    )
    # Second write with supersede_previous generates superseded event
    store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="u1", content="v2",
        evidence=[{"source": "c"}], confidence=0.8,
        task_id=task["id"], supersede_previous=True,
    )
    events = store.list_events(task["id"])
    superseded = [e for e in events if e["event_type"] == MEMORY_EVENT_SUPERSEDED]
    assert len(superseded) >= 1


def test_forgotten_event_generated(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    task = store.create_task(session_id="s1", user_id="u1", objective="test")
    store.transition_task(task["id"], TaskStatus.RUNNING)

    c = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="u1", content="forget me",
        evidence=[{"source": "c"}], confidence=0.6,
        task_id=task["id"],
    )
    store.delete_memory(c["id"], task_id=task["id"])
    events = store.list_events(task["id"])
    forgot = [e for e in events if e["event_type"] == MEMORY_EVENT_FORGOTTEN]
    assert len(forgot) == 1


def test_no_event_without_task_id(tmp_path):
    """Memory writes without task_id still work but generate no events."""
    store = AgentCoreStore(tmp_path / "mem.db")
    c = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="u1", content="no task",
        evidence=[{"source": "c"}], confidence=0.6,
    )
    assert c["id"]


def test_provenance_values_valid():
    for v in ["agent_inference", "user_stated", "user_confirmed",
              "publish_result", "failure_recovery"]:
        assert v in MEMORY_PROVENANCE_TYPES


def test_payload_includes_provenance_and_evidence_count(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    task = store.create_task(session_id="s1", user_id="u1", objective="test")
    store.transition_task(task["id"], TaskStatus.RUNNING)

    c = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="u1", content="test",
        evidence=[{"source": "s1"}, {"source": "s2"}], confidence=0.7,
        task_id=task["id"], provenance="user_stated",
    )
    events = store.list_events(task["id"])
    mem_ev = [e for e in events if e["event_type"].startswith("memory.")]
    p = mem_ev[0]["payload"]
    assert p["provenance"] == "user_stated"
    assert p["evidence_count"] == 2
    assert p["kind"] == "user"
