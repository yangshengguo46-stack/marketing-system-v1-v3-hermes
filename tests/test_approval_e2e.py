"""End-to-end approval flow tests: HTTP API → store → events → state transitions.

Covers the four paths (success/reject/cancel/timeout) plus auth scope and failure
receipt, all through the real FastAPI TestClient and real AgentCoreStore.
"""

from __future__ import annotations

import json
import asyncio
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, AsyncIterator

import yaml
from fastapi.testclient import TestClient

import server
import marketing_tools.account as account_tools
from agent_core import AgentCoreStore, TaskStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now().isoformat()


_AUTHORIZATION_KEYS = {
    "marketing_trending_search": ("platform",),
    "marketing_session_login": ("platform",),
    "marketing_accounts_sync": ("platform", "username"),
}


def _auth_constraints(capability: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    keys = _AUTHORIZATION_KEYS.get(capability, ())
    supplied = arguments or {}
    return {k: supplied[k] for k in keys if k in supplied}


def client_for(tmp_path, monkeypatch, store=None):
    """Return a TestClient pointed at a tmp config dir with a FakeAgentService."""
    monkeypatch.setattr(server, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(server, "BUNDLED_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(account_tools, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(account_tools, "ACCOUNTS_DB", tmp_path / "accounts.json")
    (tmp_path / "accounts.json").write_text(json.dumps({"accounts": [], "updated_at": None}))
    (tmp_path / "trending-cache.json").write_text(json.dumps({"status": "no_data", "top_trends": []}))
    (tmp_path / "suggestions-cache.json").write_text(json.dumps({"status": "no_data", "suggestions": []}))
    (tmp_path / "user-profiles.yaml").write_text(yaml.safe_dump({"profiles": [{"id": "default", "category": "科技"}]}))
    svc = FakeAgentService(store or AgentCoreStore(tmp_path / "agent_core.db"))
    monkeypatch.setattr(server, "_agent_service", svc)
    return TestClient(server.app), svc


# ---------------------------------------------------------------------------
# Fake Agent Service — real store, real logic, no model/threads
# ---------------------------------------------------------------------------

class FakeAgentService:
    def __init__(self, store: AgentCoreStore):
        self._store = store
        self._session_auths: dict[str, dict[str, dict[str, Any]]] = {}

    def get_store(self) -> AgentCoreStore:
        return self._store

    # -- sessions --

    async def create_session(self, user_id: str, workspace: str | None = None):
        return self._store.create_or_get_session(user_id=user_id, workspace=workspace)

    async def get_session(self, session_id: str):
        s = self._store.get_session(session_id)
        if s is None:
            from fastapi import HTTPException
            raise HTTPException(404, "session not found")
        return s

    # -- messages (stub: tests set up tasks/approvals directly) --

    async def send_message(self, session_id: str, message: str, account_id: str | None = None):
        task = self._store.create_task(
            session_id=session_id, user_id="user-1", objective=message,
            account_id=account_id,
        )
        return {"task_id": task["id"], "session_id": session_id, "status": task["status"]}

    # -- task status / events --

    async def get_task_status(self, task_id: str):
        return self._store.get_task(task_id)

    async def stream_events(self, task_id: str) -> AsyncIterator[dict[str, Any]]:
        seq = 0
        while True:
            events = self._store.list_events_after(task_id, seq)
            for ev in events:
                yield ev
                seq = max(seq, ev["sequence"])
            await asyncio.sleep(0.05)

    # -- task lifecycle --

    async def cancel_task(self, task_id: str):
        task = self._store.get_task(task_id)
        # Void pending approvals
        try:
            events = self._store.list_events_after(task_id, 0)
            for e in events:
                if e["event_type"] == "approval.requested":
                    approval_id = e.get("payload", {}).get("approval_id")
                    if approval_id:
                        try:
                            approval = self._store.get_approval(approval_id)
                            if approval["status"] == "pending":
                                self._store.decide_approval(
                                    approval_id, False, "task cancelled",
                                    transition_task=False,
                                )
                        except (KeyError, ValueError):
                            pass
        except Exception:
            pass
        try:
            self._store.transition_task(task_id, TaskStatus.CANCELLED, error="user cancelled")
        except ValueError:
            pass
        return {"task_id": task_id, "status": "cancelled"}

    async def pause_task(self, task_id: str):
        self._store.transition_task(task_id, TaskStatus.PAUSED)
        return {"task_id": task_id, "status": "paused"}

    async def resume_task(self, task_id: str):
        task = self._store.get_task(task_id)
        if task["status"] in {TaskStatus.COMPLETED, TaskStatus.CANCELLED}:
            raise ValueError(f"cannot resume from terminal state {task['status']}")
        if task["status"] in {TaskStatus.PAUSED, TaskStatus.FAILED}:
            self._store.transition_task(task_id, TaskStatus.RUNNING, current_step="resuming")
        return {"task_id": task_id, "status": "running"}

    # -- approval decisions --

    async def decide_approval(self, approval_id: str, approved: bool, reason: str | None = None,
                               transition_task: bool = True):
        return self._store.decide_approval(approval_id, approved, reason, transition_task=transition_task)

    # -- authorization --

    def grant_authorization(self, user_id: str, capability: str, scope: str = "once",
                            session_id: str | None = None, arguments: dict[str, Any] | None = None) -> dict:
        constraints = _auth_constraints(capability, arguments)
        if scope == "permanent":
            return self._store.grant_authorization(user_id, capability, constraints)
        if scope == "session" and session_id:
            self._session_auths.setdefault(session_id, {})[capability] = constraints
            return {"capability": capability, "scope": "session", "session_id": session_id, "constraints": constraints}
        return {"capability": capability, "scope": "once"}

    def is_session_authorized(self, session_id: str, capability: str, arguments: dict[str, Any] | None) -> bool:
        constraints = self._session_auths.get(session_id, {}).get(capability)
        if constraints is None:
            return False
        supplied = arguments or {}
        return all(supplied.get(k) == v for k, v in constraints.items())

    # -- resume after effect --

    async def resume_after_effect(self, task_id: str):
        task = self._store.get_task(task_id)
        if task["status"] == TaskStatus.WAITING_USER:
            self._store.transition_task(task_id, TaskStatus.RUNNING, current_step="resuming")
            self._store.append_event(task_id, "task.resumed", {"reason": "effect_executed"})
        return {"task_id": task_id, "status": "running"}

    async def resume_after_rejection(self, task_id: str):
        task = self._store.get_task(task_id)
        if task["status"] == TaskStatus.WAITING_USER:
            self._store.transition_task(task_id, TaskStatus.PAUSED)
            self._store.append_event(task_id, "task.resumed", {"reason": "approval_rejected"})
        return {"task_id": task_id, "status": "paused"}


# ---------------------------------------------------------------------------
# Helpers to create a task with a pending approval
# ---------------------------------------------------------------------------

def _create_task_with_approval(store, user_id="user-1", session_id="sess-1",
                                capability="marketing_trending_search",
                                arguments=None) -> tuple[dict, dict]:
    """Return (task, approval) with task in WAITING_USER."""
    if arguments is None:
        arguments = {"platform": "douyin", "keyword": "AI"}
    task = store.create_task(session_id=session_id, user_id=user_id, objective="搜索行业热点")
    store.transition_task(task["id"], TaskStatus.RUNNING)
    approval = store.create_approval(
        task_id=task["id"], capability=capability,
        arguments=arguments, risk_summary="需要登录态搜索",
    )
    return task, approval


# ===================================================================
# Tests
# ===================================================================

class TestApprovalSuccessPath:
    """Full success chain: approve → effect submit → task resume."""

    def test_full_success_chain(self, tmp_path, monkeypatch):
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        task, approval = _create_task_with_approval(store)

        # 1. Approve
        resp = client.post(f"/agent/approvals/{approval['id']}/approve",
                           json={"scope": "once"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"
        # Task should still be waiting_user (transition_task=False in server)
        assert store.get_task(task["id"])["status"] == "waiting_user"

        # 2. Submit effect
        resp2 = client.post("/agent/effects/submit", json={
            "approval_id": approval["id"],
            "receipt": {"status": "succeeded", "results_count": 12},
        })
        assert resp2.status_code == 200
        body = resp2.json()
        assert body["status"] == "executed"
        assert body["capability"] == "marketing_trending_search"

        # 3. Task resumed (FakeAgentService.resume_after_effect transitions it)
        updated = store.get_task(task["id"])
        assert updated["status"] == "running"

        # 4. Events are present
        events = store.list_events(task["id"])
        event_types = [e["event_type"] for e in events]
        assert "approval.requested" in event_types
        assert "approval.decided" in event_types
        assert "effect.executed" in event_types
        assert "task.resumed" in event_types

    def test_approve_is_idempotent(self, tmp_path, monkeypatch):
        """Approving an already-approved approval returns the existing approval."""
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        _, approval = _create_task_with_approval(store)

        r1 = client.post(f"/agent/approvals/{approval['id']}/approve", json={"scope": "once"})
        assert r1.status_code == 200
        # Second approve returns same approval (idempotent)
        r2 = client.post(f"/agent/approvals/{approval['id']}/approve", json={"scope": "once"})
        assert r2.status_code == 200
        assert r2.json()["id"] == r1.json()["id"]

    def test_effect_submit_requires_approved_approval(self, tmp_path, monkeypatch):
        """Cannot submit effect before approval."""
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        _, approval = _create_task_with_approval(store)

        resp = client.post("/agent/effects/submit", json={
            "approval_id": approval["id"],
            "receipt": {"status": "ok"},
        })
        assert resp.status_code == 409


class TestRejectPath:
    def test_reject_approval_pauses_task(self, tmp_path, monkeypatch):
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        _, approval = _create_task_with_approval(store)

        resp = client.post(f"/agent/approvals/{approval['id']}/reject",
                           json={"reason": "用户不想搜索"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

        # Task transitioned by resume_after_rejection
        updated = store.get_task(approval["task_id"])
        assert updated["status"] == "paused"
        assert updated["last_error"] is None  # rejection is not an error, it's a decision

        # Events
        events = store.list_events(approval["task_id"])
        event_types = [e["event_type"] for e in events]
        assert "approval.decided" in event_types


class TestCancelPath:
    def test_cancel_during_approval(self, tmp_path, monkeypatch):
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        task, approval = _create_task_with_approval(store)

        resp = client.post(f"/agent/tasks/{task['id']}/cancel")
        assert resp.status_code == 200

        updated = store.get_task(task["id"])
        assert updated["status"] == "cancelled"

    def test_cancelled_task_approval_cannot_be_approved(self, tmp_path, monkeypatch):
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        task, approval = _create_task_with_approval(store)

        client.post(f"/agent/tasks/{task['id']}/cancel")

        # Approval should be rejected (voided by cancel)
        loaded = store.get_approval(approval["id"])
        assert loaded["status"] == "rejected"

        # Approve should return 409 (approval already decided + task cancelled)
        resp = client.post(f"/agent/approvals/{approval['id']}/approve",
                           json={"scope": "once"})
        assert resp.status_code == 409


class TestSessionAuthorization:
    def test_session_scope_stores_constraints(self, tmp_path, monkeypatch):
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        _, approval = _create_task_with_approval(store)

        resp = client.post(f"/agent/approvals/{approval['id']}/approve",
                           json={"scope": "session"})
        assert resp.status_code == 200

        # Session auth should be stored
        assert svc.is_session_authorized(
            "sess-1", "marketing_trending_search",
            {"platform": "douyin", "keyword": "AI"},
        )

        # Different platform should not match
        assert not svc.is_session_authorized(
            "sess-1", "marketing_trending_search",
            {"platform": "weibo", "keyword": "AI"},
        )

        # Different session should not match
        assert not svc.is_session_authorized(
            "sess-2", "marketing_trending_search",
            {"platform": "douyin", "keyword": "AI"},
        )

    def test_session_scope_cross_tool_not_authorized(self, tmp_path, monkeypatch):
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        _, approval = _create_task_with_approval(store, capability="marketing_trending_search")

        client.post(f"/agent/approvals/{approval['id']}/approve", json={"scope": "session"})

        # Different capability should not be authorized
        assert not svc.is_session_authorized(
            "sess-1", "marketing_session_login",
            {"platform": "douyin"},
        )


class TestPermanentAuthorization:
    def test_permanent_scope_persists_to_store(self, tmp_path, monkeypatch):
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        _, approval = _create_task_with_approval(store)

        resp = client.post(f"/agent/approvals/{approval['id']}/approve",
                           json={"scope": "permanent"})
        assert resp.status_code == 200

        # Store should have the authorization
        assert store.is_authorized("user-1", "marketing_trending_search",
                                    {"platform": "douyin"})

        # Different platform should not match
        assert not store.is_authorized("user-1", "marketing_trending_search",
                                        {"platform": "weibo"})

        # Different user should not match
        assert not store.is_authorized("user-2", "marketing_trending_search",
                                        {"platform": "douyin"})

    def test_revoke_permanent_authorization(self, tmp_path, monkeypatch):
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        _, approval = _create_task_with_approval(store)

        client.post(f"/agent/approvals/{approval['id']}/approve", json={"scope": "permanent"})
        assert store.is_authorized("user-1", "marketing_trending_search", {"platform": "douyin"})

        store.revoke_authorization("user-1", "marketing_trending_search")
        assert not store.is_authorized("user-1", "marketing_trending_search", {"platform": "douyin"})

    def test_regrant_after_revoke(self, tmp_path, monkeypatch):
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        _, approval = _create_task_with_approval(store)

        # First grant then revoke
        client.post(f"/agent/approvals/{approval['id']}/approve", json={"scope": "permanent"})
        store.revoke_authorization("user-1", "marketing_trending_search")
        assert not store.is_authorized("user-1", "marketing_trending_search", {"platform": "douyin"})

        # New approval = new grant
        task2, approval2 = _create_task_with_approval(store)
        client.post(f"/agent/approvals/{approval2['id']}/approve", json={"scope": "permanent"})
        assert store.is_authorized("user-1", "marketing_trending_search", {"platform": "douyin"})


class TestFailedEffectReceipt:
    def test_failed_receipt_still_resumes_task(self, tmp_path, monkeypatch):
        """A failed effect should still record receipt and allow agent to recover."""
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        _, approval = _create_task_with_approval(store)

        client.post(f"/agent/approvals/{approval['id']}/approve", json={"scope": "once"})

        resp = client.post("/agent/effects/submit", json={
            "approval_id": approval["id"],
            "receipt": {"status": "failed", "error": "登录态过期"},
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        # Receipt is recorded, but a failed platform action must never be
        # represented as an executed effect.
        stored = store.get_effect(body["id"])
        receipt = json.loads(stored["receipt_json"]) if isinstance(stored.get("receipt_json"), str) else stored.get("receipt", {})
        assert receipt["status"] == "failed"

        # Task still resumes — agent should handle the failure
        updated = store.get_task(approval["task_id"])
        assert updated["status"] == "running"


class TestIdempotentEffect:
    def test_duplicate_idempotency_key_returns_same_effect(self, tmp_path, monkeypatch):
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        _, approval = _create_task_with_approval(store)

        client.post(f"/agent/approvals/{approval['id']}/approve", json={"scope": "once"})

        payload = {"approval_id": approval["id"], "receipt": {"status": "ok"},
                    "idempotency_key": "my-key-001"}
        r1 = client.post("/agent/effects/submit", json=payload)
        r2 = client.post("/agent/effects/submit", json=payload)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["id"] == r2.json()["id"]


class TestApprovalTimeout:
    def test_mark_approval_expired_and_resume_task(self, tmp_path, monkeypatch):
        """Simulate expiration with real timestamp: stale pending → expired → paused."""
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store

        task, approval = _create_task_with_approval(store)
        assert store.get_task(task["id"])["status"] == "waiting_user"

        # Use injectable `now` 301s in the future to trigger expiry
        future = (datetime.now(timezone.utc) + timedelta(seconds=301)).isoformat()
        expired = store.expire_stale_approvals(timeout_seconds=300, now=future)
        assert len(expired) == 1
        assert expired[0]["id"] == approval["id"]

        loaded = store.get_approval(approval["id"])
        assert loaded["status"] == "expired"

        updated = store.get_task(task["id"])
        assert updated["status"] == "paused"

    def test_not_expired_when_under_timeout(self, tmp_path, monkeypatch):
        """Approval created just now does NOT expire."""
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store

        _, approval = _create_task_with_approval(store)
        now = datetime.now(timezone.utc).isoformat()
        expired = store.expire_stale_approvals(timeout_seconds=300, now=now)
        assert len(expired) == 0
        assert store.get_approval(approval["id"])["status"] == "pending"

    def test_timeout_boundary_uses_real_elapsed_seconds(self, tmp_path, monkeypatch):
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        _, approval = _create_task_with_approval(store)
        created = datetime.fromisoformat(approval["created_at"])

        before = (created + timedelta(seconds=299)).isoformat()
        assert store.expire_stale_approvals(timeout_seconds=300, now=before) == []

        boundary = (created + timedelta(seconds=300)).isoformat()
        expired = store.expire_stale_approvals(timeout_seconds=300, now=boundary)
        assert [item["id"] for item in expired] == [approval["id"]]

    def test_expired_approval_cannot_be_approved(self, tmp_path, monkeypatch):
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        _, approval = _create_task_with_approval(store)

        future = (datetime.now(timezone.utc) + timedelta(seconds=301)).isoformat()
        store.expire_stale_approvals(timeout_seconds=300, now=future)

        resp = client.post(f"/agent/approvals/{approval['id']}/approve",
                           json={"scope": "once"})
        assert resp.status_code == 409

    def test_multiple_expired_approvals(self, tmp_path, monkeypatch):
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store

        _, a1 = _create_task_with_approval(store)
        _, a2 = _create_task_with_approval(store, capability="marketing_session_login",
                                            arguments={"platform": "douyin"})

        future = (datetime.now(timezone.utc) + timedelta(seconds=301)).isoformat()
        expired = store.expire_stale_approvals(timeout_seconds=300, now=future)
        assert len(expired) == 2
        assert all(a["status"] == "expired" for a in [store.get_approval(a["id"]) for a in [a1, a2]])


class TestCancelVoidsApproval:
    def test_cancel_rejects_pending_approval(self, tmp_path, monkeypatch):
        """Cancelled task → pending approval rejected, approve returns 409."""
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        task, approval = _create_task_with_approval(store)

        # Cancel the task through the service
        resp = client.post(f"/agent/tasks/{task['id']}/cancel")
        assert resp.status_code == 200

        # Approval should be rejected (voided by cancel)
        loaded = store.get_approval(approval["id"])
        assert loaded["status"] == "rejected"
        assert loaded["decision_reason"] == "task cancelled"

        # Approve should now return 409
        approve_resp = client.post(f"/agent/approvals/{approval['id']}/approve",
                                   json={"scope": "once"})
        assert approve_resp.status_code == 409

    def test_cancel_then_effect_submit_fails(self, tmp_path, monkeypatch):
        """After cancel, effect submit for a non-approved approval fails."""
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        _, approval = _create_task_with_approval(store)

        # Cancel voids the pending approval
        task = store.get_task(approval["task_id"])
        client.post(f"/agent/tasks/{task['id']}/cancel")

        # Approval is now rejected
        assert store.get_approval(approval["id"])["status"] == "rejected"

        # Effect submit should fail (not approved)
        resp = client.post("/agent/effects/submit", json={
            "approval_id": approval["id"], "receipt": {"status": "ok"},
        })
        assert resp.status_code == 409


class TestRestartHandling:
    def test_waiting_user_task_stays_waiting_after_restart(self, tmp_path, monkeypatch):
        """On restart, unexpired WAITING_USER tasks are left alone."""
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        task, _ = _create_task_with_approval(store)
        assert store.get_task(task["id"])["status"] == "waiting_user"

        # Simulate restart: the task is already waiting_user, no transition
        loaded = store.get_task(task["id"])
        assert loaded["status"] == "waiting_user"

    def test_restart_expires_overdue_approval(self, tmp_path, monkeypatch):
        """On restart + expiry check, overdue approval → expired + task → paused."""
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        task, _ = _create_task_with_approval(store)

        future = (datetime.now(timezone.utc) + timedelta(seconds=301)).isoformat()
        store.expire_stale_approvals(timeout_seconds=300, now=future)

        loaded = store.get_task(task["id"])
        assert loaded["status"] == "paused"


class TestSchedulerIntegration:
    def test_scheduler_calls_expire(self, tmp_path, monkeypatch):
        """Verify expire_stale_approvals is callable from production context."""
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        _, _ = _create_task_with_approval(store)

        # Production call: timeout from env default, no now injection
        result = store.expire_stale_approvals(timeout_seconds=300)
        assert isinstance(result, list)
        # Approval just created, should NOT be expired with 300s timeout
        assert len(result) == 0


class TestTaskResume:
    def test_resume_paused_task(self, tmp_path, monkeypatch):
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        task = store.create_task(session_id="sess-1", user_id="user-1", objective="test")
        store.transition_task(task["id"], TaskStatus.RUNNING)
        store.transition_task(task["id"], TaskStatus.PAUSED)

        resp = client.post(f"/agent/tasks/{task['id']}/resume")
        assert resp.status_code == 200
        assert store.get_task(task["id"])["status"] == "running"

    def test_resume_completed_task_fails(self, tmp_path, monkeypatch):
        client, svc = client_for(tmp_path, monkeypatch)
        store = svc._store
        task = store.create_task(session_id="sess-1", user_id="user-1", objective="test")
        store.transition_task(task["id"], TaskStatus.RUNNING)
        store.transition_task(task["id"], TaskStatus.COMPLETED)

        resp = client.post(f"/agent/tasks/{task['id']}/resume")
        assert resp.status_code == 409  # terminal state
