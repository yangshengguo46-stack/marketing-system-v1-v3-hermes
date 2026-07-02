"""MEM-03: Multi-evidence memory promotion thresholds."""

import pytest
from agent_core import AgentCoreStore, MemoryKind


def test_user_kind_lower_threshold(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    # USER kind: threshold 0.55 by default
    c = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="u1", content="pref",
        evidence=[{"source": "conversation"}], confidence=0.6,
    )
    assert c["status"] == "verified"


def test_procedural_kind_higher_threshold(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    # PROCEDURAL: threshold 0.8
    c = store.add_memory_candidate(
        kind=MemoryKind.PROCEDURAL, user_id="u1", content="process",
        evidence=[{"source": "task"}], confidence=0.7,
    )
    assert c["status"] == "pending"


def test_multi_source_lowers_threshold(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    # SEMANTIC: threshold 0.7, two sources → effective 0.65
    c = store.add_memory_candidate(
        kind=MemoryKind.SEMANTIC, user_id="u1", content="knowledge",
        evidence=[{"source": "s1"}, {"source": "s2"}], confidence=0.65,
    )
    assert c["status"] == "verified"


def test_single_rejection_not_permanent(tmp_path):
    store = AgentCoreStore(tmp_path / "mem.db")
    c = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="u1", content="可疑",
        evidence=[], confidence=0.5,
    )
    assert c["status"] == "rejected"
    assert "证据" in c.get("rejection_reason", "")


def test_no_evidence_always_pending_or_rejected(tmp_path):
    """Without evidence, even high confidence stays pending/rejected."""
    store = AgentCoreStore(tmp_path / "mem.db")
    c = store.add_memory_candidate(
        kind=MemoryKind.USER, user_id="u1", content="no evidence",
        evidence=[], confidence=0.9,
    )
    assert c["status"] in ("pending", "rejected")
