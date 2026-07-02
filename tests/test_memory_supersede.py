"""MEM-04: conflict, correction, and rollback for memory supersede chains."""

from __future__ import annotations

import pytest

from agent_core import AgentCoreStore, MemoryKind, TaskStatus
from agent_core.store import (
    MEMORY_EVENT_ADOPTED,
    MEMORY_EVENT_MODIFIED,
    MEMORY_EVENT_SUPERSEDED,
)


def _store(tmp_path):
    return AgentCoreStore(tmp_path / "mem.db")


def _add(store, content, *, user_id="user-1", supersede=False, **kwargs):
    return store.add_memory_candidate(
        kind=MemoryKind.USER, user_id=user_id, content=content,
        evidence=[{"source": "conversation"}], confidence=0.9,
        supersede_previous=supersede, **kwargs,
    )


# ---------------------------------------------------------------------------
# Conflict: new fact wins, history retained, chain traceable
# ---------------------------------------------------------------------------

def test_conflict_keeps_history_without_physical_overwrite(tmp_path):
    store = _store(tmp_path)
    old = _add(store, "发布时间偏好晚上8点")
    new = _add(store, "发布时间偏好中午12点", supersede=True)

    old_reloaded = store.get_memory_candidate(old["id"])
    assert old_reloaded["status"] == "superseded"
    assert old_reloaded["content"] == "发布时间偏好晚上8点"  # not overwritten
    assert new["supersedes_id"] == old["id"]  # chain is traceable
    assert new["status"] == "verified"


def test_conflict_chain_across_three_versions(tmp_path):
    store = _store(tmp_path)
    v1 = _add(store, "v1")
    v2 = _add(store, "v2", supersede=True)
    v3 = _add(store, "v3", supersede=True)

    assert store.get_memory_candidate(v1["id"])["status"] == "superseded"
    assert store.get_memory_candidate(v2["id"])["status"] == "superseded"
    assert store.get_memory_candidate(v3["id"])["status"] == "verified"
    # Only the latest version is injectable
    active = store.list_memories(user_id="user-1", status="verified")
    assert [m["content"] for m in active] == ["v3"]


def test_conflict_does_not_cross_account_scope(tmp_path):
    store = _store(tmp_path)
    a = _add(store, "账号A定位", account_id="acct-a")
    _add(store, "账号B定位", account_id="acct-b", supersede=True)

    assert store.get_memory_candidate(a["id"])["status"] == "verified"


# ---------------------------------------------------------------------------
# Correction: user edits content in place, modified event emitted
# ---------------------------------------------------------------------------

def test_user_correction_updates_content_and_emits_modified(tmp_path):
    store = _store(tmp_path)
    task = store.create_task(session_id="s1", user_id="user-1", objective="t")
    store.transition_task(task["id"], TaskStatus.RUNNING)
    memory = _add(store, "行业是美妆")

    corrected = store.update_memory_candidate(
        memory["id"], content="行业是母婴", provenance="user_confirmed",
        task_id=task["id"],
    )

    assert corrected["content"] == "行业是母婴"
    assert corrected["status"] == "verified"  # correction does not reset status
    events = store.list_events(task["id"])
    assert any(e["event_type"] == MEMORY_EVENT_MODIFIED for e in events)


def test_correction_with_secret_is_rejected(tmp_path):
    store = _store(tmp_path)
    memory = _add(store, "正常偏好")

    with pytest.raises(ValueError, match="secret"):
        store.update_memory_candidate(
            memory["id"], content="api key sk-abcdefghijklmnop1234",
        )
    assert store.get_memory_candidate(memory["id"])["content"] == "正常偏好"


def test_correction_to_empty_content_is_rejected(tmp_path):
    store = _store(tmp_path)
    memory = _add(store, "正常偏好")
    with pytest.raises(ValueError, match="empty"):
        store.update_memory_candidate(memory["id"], content="   ")


# ---------------------------------------------------------------------------
# Rollback: user restores a wrongly superseded memory
# ---------------------------------------------------------------------------

def test_rollback_restores_superseded_memory(tmp_path):
    store = _store(tmp_path)
    task = store.create_task(session_id="s1", user_id="user-1", objective="t")
    store.transition_task(task["id"], TaskStatus.RUNNING)
    old = _add(store, "正确的旧事实", task_id=task["id"])
    wrong = _add(store, "错误的新事实", supersede=True, task_id=task["id"])

    # User rejects the wrong new fact and restores the old one
    store.update_memory_candidate(wrong["id"], status="rejected",
                                  rejection_reason="事实错误", task_id=task["id"])
    restored = store.update_memory_candidate(old["id"], status="verified",
                                             task_id=task["id"])

    assert restored["status"] == "verified"
    active = store.list_memories(user_id="user-1", status="verified")
    assert [m["content"] for m in active] == ["正确的旧事实"]
    events = store.list_events(task["id"])
    old_events = [e["event_type"] for e in events
                  if e["payload"].get("memory_id") == old["id"]]
    assert MEMORY_EVENT_SUPERSEDED in old_events
    assert MEMORY_EVENT_ADOPTED in old_events  # rollback is auditable


def test_superseded_cannot_jump_to_locked_or_rejected(tmp_path):
    store = _store(tmp_path)
    old = _add(store, "旧事实")
    _add(store, "新事实", supersede=True)

    for target in ("locked", "rejected"):
        with pytest.raises(ValueError, match="invalid memory transition"):
            store.update_memory_candidate(old["id"], status=target)


def test_restored_memory_can_supersede_again(tmp_path):
    store = _store(tmp_path)
    old = _add(store, "v1")
    v2 = _add(store, "v2", supersede=True)

    store.update_memory_candidate(v2["id"], status="rejected",
                                  rejection_reason="错误")
    store.update_memory_candidate(old["id"], status="verified")
    v3 = _add(store, "v3", supersede=True)

    assert store.get_memory_candidate(old["id"])["status"] == "superseded"
    assert v3["supersedes_id"] == old["id"]
    active = store.list_memories(user_id="user-1", status="verified")
    assert [m["content"] for m in active] == ["v3"]
