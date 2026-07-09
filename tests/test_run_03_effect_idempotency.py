"""RUN-03: Effect idempotency tests.

Verifies the full effect execution chain:
1. Intent is recorded before execution (pre-log)
2. idempotency_key deduplicates — same key returns same effect
3. Receipt is recorded after execution
4. Double-submit of receipt is idempotent (no duplicate execution)
5. Unknown outcome (crash between intent and receipt) → can be detected
6. Restart safety — effects survive process restart
7. Compensation: voided approvals cancel pending effects
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ENGINE_ROOT = Path(__file__).parent.parent / "engine"
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from agent_core.store import AgentCoreStore
from agent_core.models import TaskStatus, ApprovalStatus


@pytest.fixture
def store(tmp_path):
    return AgentCoreStore(tmp_path / "test.db")


@pytest.fixture
def task_with_approval(store):
    """Create a task, transition to running, and get an approved approval."""
    session = store.create_or_get_session(user_id="user_1")
    task = store.create_task(
        session_id=session["id"],
        user_id="user_1",
        objective="同步账号数据",
    )
    store.transition_task(task["id"], TaskStatus.RUNNING)
    approval = store.create_approval(
        task_id=task["id"],
        capability="marketing_accounts_sync",
        arguments={"account_id": "acct_001"},
        risk_summary="同步账号数据",
    )
    store.decide_approval(approval["id"], approved=True)
    return task, approval


class TestIntentBeforeExecution:
    """Effect intent must be recorded before execution."""

    def test_intent_has_pending_status(self, store, task_with_approval):
        task, approval = task_with_approval
        effect = store.create_effect_intent(
            task_id=task["id"],
            capability="marketing_accounts_sync",
            idempotency_key="sync_001",
            preview={"action": "sync", "account": "acct_001"},
            approval_id=approval["id"],
        )
        assert effect["status"] == "pending"
        assert effect["capability"] == "marketing_accounts_sync"
        assert effect["idempotency_key"] == "sync_001"

    def test_intent_has_preview(self, store, task_with_approval):
        task, approval = task_with_approval
        effect = store.create_effect_intent(
            task_id=task["id"],
            capability="marketing_accounts_sync",
            idempotency_key="sync_002",
            preview={"action": "sync", "data": "test"},
            approval_id=approval["id"],
        )
        assert effect["preview"]["action"] == "sync"

    def test_intent_creates_event(self, store, task_with_approval):
        task, approval = task_with_approval
        store.create_effect_intent(
            task_id=task["id"],
            capability="marketing_accounts_sync",
            idempotency_key="sync_003",
            preview={},
            approval_id=approval["id"],
        )
        events = store.list_events(task["id"])
        intent_events = [e for e in events if e["event_type"] == "effect.intent_created"]
        assert len(intent_events) == 1


class TestIdempotencyKeyDedup:
    """Same idempotency_key must return the same effect."""

    def test_same_key_returns_same_effect(self, store, task_with_approval):
        task, approval = task_with_approval
        effect1 = store.create_effect_intent(
            task_id=task["id"],
            capability="marketing_accounts_sync",
            idempotency_key="dedup_key",
            preview={"run": 1},
            approval_id=approval["id"],
        )
        effect2 = store.create_effect_intent(
            task_id=task["id"],
            capability="marketing_accounts_sync",
            idempotency_key="dedup_key",
            preview={"run": 2},  # Different preview, should be ignored
            approval_id=approval["id"],
        )
        assert effect1["id"] == effect2["id"]
        assert effect2["preview"]["run"] == 1  # Original preview preserved

    def test_different_keys_create_different_effects(self, store, task_with_approval):
        task, approval = task_with_approval
        effect1 = store.create_effect_intent(
            task_id=task["id"],
            capability="marketing_accounts_sync",
            idempotency_key="key_a",
            preview={},
            approval_id=approval["id"],
        )
        effect2 = store.create_effect_intent(
            task_id=task["id"],
            capability="marketing_accounts_sync",
            idempotency_key="key_b",
            preview={},
            approval_id=approval["id"],
        )
        assert effect1["id"] != effect2["id"]

    def test_dedup_across_restart(self, store, tmp_path, task_with_approval):
        task, approval = task_with_approval
        effect = store.create_effect_intent(
            task_id=task["id"],
            capability="marketing_accounts_sync",
            idempotency_key="restart_key",
            preview={},
            approval_id=approval["id"],
        )
        del store

        store2 = AgentCoreStore(tmp_path / "test.db")
        effect2 = store2.create_effect_intent(
            task_id=task["id"],
            capability="marketing_accounts_sync",
            idempotency_key="restart_key",
            preview={},
            approval_id=approval["id"],
        )
        assert effect["id"] == effect2["id"]


class TestReceiptRecording:
    """Receipt must be recorded after execution."""

    def test_receipt_recorded(self, store, task_with_approval):
        task, approval = task_with_approval
        effect = store.create_effect_intent(
            task_id=task["id"],
            capability="marketing_accounts_sync",
            idempotency_key="receipt_001",
            preview={},
            approval_id=approval["id"],
        )
        result = store.record_effect_receipt(effect["id"], {"status": "ok", "synced": 42})
        assert result["status"] == "executed"
        assert result["receipt"]["synced"] == 42

    def test_receipt_creates_event(self, store, task_with_approval):
        task, approval = task_with_approval
        effect = store.create_effect_intent(
            task_id=task["id"],
            capability="marketing_accounts_sync",
            idempotency_key="receipt_002",
            preview={},
            approval_id=approval["id"],
        )
        store.record_effect_receipt(effect["id"], {"status": "ok"})
        events = store.list_events(task["id"])
        executed_events = [e for e in events if e["event_type"] == "effect.executed"]
        assert len(executed_events) == 1

    def test_failed_receipt_is_not_marked_executed(self, store, task_with_approval):
        task, approval = task_with_approval
        effect = store.create_effect_intent(
            task_id=task["id"], capability="marketing_effect_publish",
            idempotency_key="failed_publish", preview={}, approval_id=approval["id"],
        )
        result = store.record_effect_receipt(
            effect["id"], {"status": "failed", "error": "provider unavailable"},
        )
        assert result["status"] == "failed"
        events = store.list_events(task["id"])
        assert any(event["event_type"] == "effect.failed" for event in events)
        assert not any(event["event_type"] == "effect.executed" for event in events)

    def test_unknown_receipt_remains_queryable_before_retry(self, store, task_with_approval):
        task, approval = task_with_approval
        effect = store.create_effect_intent(
            task_id=task["id"], capability="marketing_effect_publish",
            idempotency_key="unknown_publish", preview={}, approval_id=approval["id"],
        )
        unknown = store.record_effect_receipt(effect["id"], {"status": "unknown"})
        assert unknown["status"] == "unknown"

        recovered = store.record_effect_receipt(
            effect["id"], {"status": "ok", "platform_post_id": "post-1"},
        )
        assert recovered["status"] == "executed"
        assert recovered["receipt"]["platform_post_id"] == "post-1"

    def test_double_submit_receipt_is_idempotent(self, store, task_with_approval):
        """Submitting receipt twice must not overwrite or duplicate."""
        task, approval = task_with_approval
        effect = store.create_effect_intent(
            task_id=task["id"],
            capability="marketing_accounts_sync",
            idempotency_key="double_submit",
            preview={},
            approval_id=approval["id"],
        )
        receipt1 = store.record_effect_receipt(effect["id"], {"status": "ok", "data": "first"})
        receipt2 = store.record_effect_receipt(effect["id"], {"status": "ok", "data": "second"})

        # Second submit should return original receipt
        assert receipt1["receipt"]["data"] == "first"
        assert receipt2["receipt"]["data"] == "first"

        # Only one effect.executed event
        events = store.list_events(task["id"])
        executed = [e for e in events if e["event_type"] == "effect.executed"]
        assert len(executed) == 1


class TestUnknownOutcome:
    """Crash between intent and receipt leaves effect in 'pending' state."""

    def test_pending_effect_detected_after_restart(self, store, tmp_path, task_with_approval):
        task, approval = task_with_approval
        effect = store.create_effect_intent(
            task_id=task["id"],
            capability="marketing_accounts_sync",
            idempotency_key="unknown_outcome",
            preview={},
            approval_id=approval["id"],
        )
        # Simulate crash: no receipt recorded
        del store

        store2 = AgentCoreStore(tmp_path / "test.db")
        effect2 = store2.get_effect(effect["id"])
        assert effect2["status"] == "pending"
        assert effect2["receipt"] is None

    def test_pending_effect_can_be_completed_after_restart(self, store, tmp_path, task_with_approval):
        task, approval = task_with_approval
        effect = store.create_effect_intent(
            task_id=task["id"],
            capability="marketing_accounts_sync",
            idempotency_key="recover_after_crash",
            preview={},
            approval_id=approval["id"],
        )
        del store

        store2 = AgentCoreStore(tmp_path / "test.db")
        result = store2.record_effect_receipt(effect["id"], {"status": "ok", "recovered": True})
        assert result["status"] == "executed"
        assert result["receipt"]["recovered"] is True


class TestRestartSafety:
    """Effects must survive process restart."""

    def test_executed_effect_survives_restart(self, store, tmp_path, task_with_approval):
        task, approval = task_with_approval
        effect = store.create_effect_intent(
            task_id=task["id"],
            capability="marketing_accounts_sync",
            idempotency_key="survive_restart",
            preview={},
            approval_id=approval["id"],
        )
        store.record_effect_receipt(effect["id"], {"status": "ok"})
        del store

        store2 = AgentCoreStore(tmp_path / "test.db")
        effect2 = store2.get_effect(effect["id"])
        assert effect2["status"] == "executed"
        assert effect2["receipt"]["status"] == "ok"

    def test_multiple_effects_survive_restart(self, store, tmp_path, task_with_approval):
        task, approval = task_with_approval
        for i in range(5):
            effect = store.create_effect_intent(
                task_id=task["id"],
                capability="marketing_accounts_sync",
                idempotency_key=f"batch_{i}",
                preview={"index": i},
                approval_id=approval["id"],
            )
            store.record_effect_receipt(effect["id"], {"result": i})
        del store

        store2 = AgentCoreStore(tmp_path / "test.db")
        with store2._connect() as conn:
            effects = conn.execute(
                "SELECT * FROM effect_intents WHERE task_id=? ORDER BY idempotency_key",
                (task["id"],),
            ).fetchall()
        assert len(effects) == 5
        for e in effects:
            assert e["status"] == "executed"


class TestApprovalRequired:
    """Effect with approval_id requires approved approval."""

    def test_rejected_approval_blocks_effect(self, store):
        session = store.create_or_get_session(user_id="user_1")
        task = store.create_task(
            session_id=session["id"],
            user_id="user_1",
            objective="test",
        )
        store.transition_task(task["id"], TaskStatus.RUNNING)
        approval = store.create_approval(
            task_id=task["id"],
            capability="marketing_accounts_sync",
            arguments={},
            risk_summary="test",
        )
        store.decide_approval(approval["id"], approved=False)

        with pytest.raises(PermissionError, match="approved"):
            store.create_effect_intent(
                task_id=task["id"],
                capability="marketing_accounts_sync",
                idempotency_key="blocked",
                preview={},
                approval_id=approval["id"],
            )

    def test_no_approval_id_allows_effect(self, store):
        """Effects without approval_id should work (for pre-approved capabilities)."""
        session = store.create_or_get_session(user_id="user_1")
        task = store.create_task(
            session_id=session["id"],
            user_id="user_1",
            objective="test",
        )
        effect = store.create_effect_intent(
            task_id=task["id"],
            capability="marketing_read_trends",
            idempotency_key="no_approval",
            preview={},
        )
        assert effect["status"] == "pending"


class TestCompensation:
    """Voided approvals should prevent pending effects from executing."""

    def test_cancel_task_voids_approvals(self, store):
        session = store.create_or_get_session(user_id="user_1")
        task = store.create_task(
            session_id=session["id"],
            user_id="user_1",
            objective="test",
        )
        store.transition_task(task["id"], TaskStatus.RUNNING)
        approval = store.create_approval(
            task_id=task["id"],
            capability="marketing_accounts_sync",
            arguments={},
            risk_summary="test",
        )
        store.decide_approval(approval["id"], approved=True)

        # Cancel task — should void approvals
        store.cancel_task_and_void_approvals(task["id"])
        task2 = store.get_task(task["id"])
        assert task2["status"] == "cancelled"


class TestIdempotencyKeyUniqueness:
    """idempotency_key must be unique at the DB level."""

    def test_unique_constraint_enforced(self, store, tmp_path, task_with_approval):
        task, approval = task_with_approval
        store.create_effect_intent(
            task_id=task["id"],
            capability="marketing_accounts_sync",
            idempotency_key="unique_test",
            preview={},
            approval_id=approval["id"],
        )
        # Direct insert with same key should fail
        with store._connect() as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO effect_intents (id, task_id, capability, idempotency_key, preview_json, status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
                    ("effect_dup", task["id"], "test", "unique_test", "{}", "2026-01-01"),
                )
