from __future__ import annotations

from agent.account_registry import AccountRegistry
from hermes_state import SessionDB


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
        assert registry.delete(pending["id"]) is True
        assert registry.list() == []
    finally:
        db.close()
