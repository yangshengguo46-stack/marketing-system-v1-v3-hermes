from __future__ import annotations

from agent.account_registry import AccountRegistry
from hermes_state import SessionDB
from tools import mcp_tool


def test_native_registry_owns_lifecycle_binding_and_browser_lease(tmp_path):
    db = SessionDB(db_path=tmp_path / "state.db")
    registry = AccountRegistry(db)
    try:
        pending = registry.register_pending(platform="zhihu", label="知乎主账号")
        assert pending["auth_state"] == "unauthenticated"

        connected = registry.mark_authenticated(
            pending["id"], platform_user_id="people-123", username="创作者"
        )
        assert connected["status"] == "active"
        assert connected["auth_state"] == "authenticated"

        db.create_session("session-1", "desktop")
        assert registry.bind_session("session-1", pending["id"]) is True
        lease = registry.lease_for_session("session-1")
        assert lease.account_id == pending["id"]
        assert lease.platform == "zhihu"
        assert lease.profile_key == f"zhihu:{pending['id']}"

        registry.mark_verification_required(pending["id"])
        try:
            registry.lease_for_session("session-1")
        except ValueError as exc:
            assert "requires login or verification" in str(exc)
        else:
            raise AssertionError("stale authentication must not produce an execution lease")

        disconnected = registry.disconnect(pending["id"])
        assert disconnected["status"] == "disconnected"
        disconnected_lifecycle = registry.browser_context_lifecycle(pending["id"])
        assert disconnected_lifecycle["may_run"] is False
        assert disconnected_lifecycle["purge_profile"] is False
        try:
            registry.lease_for_session("session-1", require_authenticated=False)
        except ValueError as exc:
            assert "disconnected" in str(exc)
        else:
            raise AssertionError("disconnected account must not retain browser authority")
        assert registry.delete(pending["id"]) is True
        deleted_lifecycle = registry.browser_context_lifecycle(pending["id"])
        assert deleted_lifecycle["may_run"] is False
        assert deleted_lifecycle["purge_profile"] is True
        assert registry.list() == []
    finally:
        db.close()


def test_product_account_lifecycle_notifies_native_browser_owner(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("MARKETING_OS_USER_DATA", str(tmp_path))
    monkeypatch.setattr(
        mcp_tool,
        "reconcile_marketing_account_browser",
        lambda **kwargs: calls.append(kwargs) or True,
    )
    db = SessionDB(db_path=tmp_path / "state.db")
    registry = AccountRegistry(db)
    try:
        account = registry.register_pending(platform="zhihu")
        registry.disconnect(account["id"])
        registry.delete(account["id"])
    finally:
        db.close()

    assert [call["purge_profile"] for call in calls] == [False, True]
    assert all(call["account_id"] == account["id"] for call in calls)
