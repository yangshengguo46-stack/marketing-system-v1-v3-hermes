"""Memory scope isolation, auto-supersede, DNA, and evidence promotion tests."""

from __future__ import annotations

import json

from agent_core import ACCOUNT_DNA_FIELDS, AgentCoreStore, MemoryKind, TaskStatus


# ---------------------------------------------------------------------------
# Workspace isolation
# ---------------------------------------------------------------------------

def test_workspace_isolation(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="workspace-A偏好",
        evidence=[{"source": "conversation"}], confidence=0.9,
        workspace="project-a",
    )
    store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="workspace-B偏好",
        evidence=[{"source": "conversation"}], confidence=0.9,
        workspace="project-b",
    )

    a = store.list_memories(user_id="user-1", workspace="project-a", status=None)
    b = store.list_memories(user_id="user-1", workspace="project-b", status=None)
    assert len(a) == 1
    assert len(b) == 1
    assert a[0]["content"] == "workspace-A偏好"
    assert b[0]["content"] == "workspace-B偏好"


def test_workspace_null_and_specific_coexist(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="全局",
        evidence=[{"source": "conversation"}], confidence=0.9,
        workspace=None,
    )
    store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="项目内",
        evidence=[{"source": "conversation"}], confidence=0.9,
        workspace="proj",
    )
    all_ = store.list_memories(user_id="user-1", status=None)
    proj = store.list_memories(user_id="user-1", workspace="proj", status=None)
    assert len(all_) == 2
    assert len(proj) == 1
    assert proj[0]["content"] == "项目内"


# ---------------------------------------------------------------------------
# Auto-supersede
# ---------------------------------------------------------------------------

def test_auto_supersede_replaces_old(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    old = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="旧偏好",
        evidence=[{"source": "conversation"}], confidence=0.9,
    )
    assert old["status"] == "verified"

    new = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="新偏好",
        evidence=[{"source": "conversation"}], confidence=0.9,
        supersede_previous=True,
    )
    assert new["status"] == "verified"

    # Old memory should be superseded
    old_reloaded = store.get_memory_candidate(old["id"])
    assert old_reloaded["status"] == "superseded"


def test_superseded_not_injected(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")

    store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="v1",
        evidence=[{"source": "c"}], confidence=0.9,
    )
    store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="v2",
        evidence=[{"source": "c"}], confidence=0.9,
        supersede_previous=True,
    )

    verified = store.list_memories(user_id="user-1", status="verified")
    superseded = store.list_memories(user_id="user-1", status="superseded")
    assert len(verified) == 1
    assert verified[0]["content"] == "v2"
    assert len(superseded) == 1
    assert superseded[0]["content"] == "v1"


def test_supersede_respects_scope(tmp_path):
    """Supersede only affects same user_id + account_id + kind + workspace."""
    store = AgentCoreStore(tmp_path / "mem.db")
    store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="acc-A",
        evidence=[{"source": "c"}], confidence=0.9,
        account_id="acc-a",
    )
    store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="acc-B",
        evidence=[{"source": "c"}], confidence=0.9,
        account_id="acc-b",
    )

    # Supersede only acc-a memories
    store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="acc-A-v2",
        evidence=[{"source": "c"}], confidence=0.9,
        account_id="acc-a", supersede_previous=True,
    )

    # acc-b memory should still be verified
    acc_b = store.list_memories(user_id="user-1", account_id="acc-b", status="verified")
    assert len(acc_b) == 1
    assert acc_b[0]["content"] == "acc-B"


# ---------------------------------------------------------------------------
# Structured Account DNA
# ---------------------------------------------------------------------------

def test_account_dna_field_upsert(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    store.upsert_account_dna(
        user_id="user-1", account_id="acc-1",
        field="persona", value="AI教育博主",
        evidence=[{"source": "user_stated"}],
    )
    dna = store.get_account_dna(user_id="user-1", account_id="acc-1")
    assert dna["persona"] == "AI教育博主"


def test_account_dna_multiple_fields(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    store.upsert_account_dna(
        user_id="user-1", account_id="acc-1",
        field="persona", value="AI教育",
        evidence=[{"source": "c"}],
    )
    store.upsert_account_dna(
        user_id="user-1", account_id="acc-1",
        field="tone", value="专业+亲和",
        evidence=[{"source": "c"}],
    )
    store.upsert_account_dna(
        user_id="user-1", account_id="acc-1",
        field="audience", value="25-35岁科技从业者",
        evidence=[{"source": "c"}],
    )
    dna = store.get_account_dna(user_id="user-1", account_id="acc-1")
    assert dna["persona"] == "AI教育"
    assert dna["tone"] == "专业+亲和"
    assert dna["audience"] == "25-35岁科技从业者"


def test_account_dna_isolated_by_account(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    store.upsert_account_dna(
        user_id="user-1", account_id="acc-a",
        field="persona", value="博主A",
        evidence=[{"source": "c"}],
    )
    store.upsert_account_dna(
        user_id="user-1", account_id="acc-b",
        field="persona", value="博主B",
        evidence=[{"source": "c"}],
    )
    dna_a = store.get_account_dna(user_id="user-1", account_id="acc-a")
    dna_b = store.get_account_dna(user_id="user-1", account_id="acc-b")
    assert dna_a["persona"] == "博主A"
    assert dna_b["persona"] == "博主B"


def test_account_dna_workspace_isolated(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    store.upsert_account_dna(
        user_id="user-1", account_id="acc-1", workspace="ws-1",
        field="persona", value="项目1人设",
        evidence=[{"source": "c"}],
    )
    store.upsert_account_dna(
        user_id="user-1", account_id="acc-1", workspace="ws-2",
        field="persona", value="项目2人设",
        evidence=[{"source": "c"}],
    )
    dna1 = store.get_account_dna(user_id="user-1", account_id="acc-1", workspace="ws-1")
    dna2 = store.get_account_dna(user_id="user-1", account_id="acc-1", workspace="ws-2")
    assert dna1["persona"] == "项目1人设"
    assert dna2["persona"] == "项目2人设"


def test_account_dna_fields_match_schema():
    for f in ACCOUNT_DNA_FIELDS:
        assert f in {"persona", "tone", "audience", "content_pillars", "taboos", "goals"}


# ---------------------------------------------------------------------------
# Evidence-based auto-promotion
# ---------------------------------------------------------------------------

def test_auto_verify_high_confidence_evidence(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    m = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="auto-verified",
        evidence=[{"source": "agent_task", "task_id": "task-1"}], confidence=0.9,
    )
    assert m["status"] == "verified"


def test_pending_low_confidence(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    m = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="待确认",
        evidence=[{"source": "agent_task", "task_id": "t-1"}], confidence=0.5,
    )
    assert m["status"] == "pending"


def test_pending_no_evidence_high_confidence(tmp_path):
    """High confidence without evidence stays pending (or rejected by no-evidence rule)."""
    store = AgentCoreStore(tmp_path / "mem.db")
    m = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="无依据",
        evidence=[], confidence=0.9,
    )
    # No evidence → rejected, regardless of confidence
    assert m["status"] == "rejected"


# ---------------------------------------------------------------------------
# Adopt/reject recording
# ---------------------------------------------------------------------------

def test_adopt_reject_recorded(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    task = store.create_task(session_id="sess-1", user_id="user-1", objective="test")
    store.transition_task(task["id"], TaskStatus.RUNNING)

    # Agent writes a memory with confidence below auto-verify threshold
    m = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="推荐AI赛道",
        evidence=[{"source": "agent_task", "task_id": task["id"]}], confidence=0.5,
    )
    assert m["status"] == "pending"

    # User confirms → verified
    store.update_memory_candidate(m["id"], status="verified")
    assert store.get_memory_candidate(m["id"])["status"] == "verified"

    # User rejects
    m2 = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="user-1", content="不推荐娱乐赛道",
        evidence=[{"source": "agent_task", "task_id": task["id"]}], confidence=0.5,
    )
    store.update_memory_candidate(m2["id"], status="rejected")
    assert store.get_memory_candidate(m2["id"])["status"] == "rejected"
