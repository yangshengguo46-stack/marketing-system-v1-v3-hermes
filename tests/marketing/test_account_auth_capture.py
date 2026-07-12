from __future__ import annotations

import json

import hermes_state
from agent.account_registry import AccountRegistry
from agent.marketing.account_auth_capture import enrich_tool_result_with_account_auth
from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import AccountLifecycleRepository
from hermes_state import SessionDB
from tools import mcp_tool


def test_real_browser_verification_marks_account_adopts_prospect_and_closes_login(tmp_path, monkeypatch):
    state_path = tmp_path / "state.db"
    monkeypatch.setattr(hermes_state, "DEFAULT_DB_PATH", state_path)
    paths = MarketingDataPaths(tmp_path, tmp_path / "config", state_path)
    db = SessionDB(db_path=state_path)
    registry = AccountRegistry(db)
    calls = []
    monkeypatch.setattr(
        mcp_tool,
        "reconcile_marketing_account_browser",
        lambda **kwargs: calls.append(kwargs) or True,
    )
    try:
        project = AccountLifecycleRepository(paths).begin_project(
            user_id="default",
            account_id="prospect_default",
            business_goal="先通过自然对话找到方向",
        )
        account = registry.register_pending(platform="douyin")
        db.create_session(
            "login-session",
            "tui",
            marketing_user_id="default",
            marketing_account_id=account["id"],
        )
        browser_result = json.dumps(
            {
                "schema": "marketing_account_auth_verification.v1",
                "account_id": account["id"],
                "platform": "douyin",
                "verified": True,
                "verification_basis": ["first_party_session_cookie_set"],
                "signal_count": 1,
            }
        )

        enriched = enrich_tool_result_with_account_auth(
            tool_name="mcp_marketing_browser_browser_verify_account_login",
            result=browser_result,
            task_id="login-session",
            session_id="login-session",
        )

        connected = db.get_marketing_account(account["id"])
        assert connected["status"] == "active"
        assert connected["auth_state"] == "authenticated"
        assert calls == [
            {
                "user_id": "default",
                "account_id": account["id"],
                "platform": "douyin",
                "profile_key": f"douyin:{account['id']}",
                "purge_profile": False,
            }
        ]
        assert "headed_login_closed_next_lease_background" in enriched
        adopted = AccountLifecycleRepository(paths).begin_project(
            user_id="default",
            account_id=account["id"],
            business_goal="不覆盖",
        )
        assert adopted["id"] == project["id"]
        assert adopted["operation"] == "existing"
    finally:
        db.close()


def test_unverified_or_scope_mismatched_result_cannot_authenticate(tmp_path, monkeypatch):
    state_path = tmp_path / "state.db"
    monkeypatch.setattr(hermes_state, "DEFAULT_DB_PATH", state_path)
    db = SessionDB(db_path=state_path)
    registry = AccountRegistry(db)
    try:
        account = registry.register_pending(platform="douyin")
        db.create_session(
            "login-session",
            "tui",
            marketing_user_id="default",
            marketing_account_id=account["id"],
        )
        unverified = json.dumps(
            {
                "schema": "marketing_account_auth_verification.v1",
                "account_id": account["id"],
                "platform": "douyin",
                "verified": False,
            }
        )
        unchanged = enrich_tool_result_with_account_auth(
            tool_name="browser_verify_account_login",
            result=unverified,
            session_id="login-session",
        )
        assert unchanged == unverified
        assert db.get_marketing_account(account["id"])["auth_state"] == "unauthenticated"

        mismatched = json.dumps(
            {
                "schema": "marketing_account_auth_verification.v1",
                "account_id": "acct_other",
                "platform": "douyin",
                "verified": True,
            }
        )
        try:
            enrich_tool_result_with_account_auth(
                tool_name="browser_verify_account_login",
                result=mismatched,
                session_id="login-session",
            )
        except ValueError as exc:
            assert "does not match" in str(exc)
        else:
            raise AssertionError("cross-account browser verification must be rejected")
        assert db.get_marketing_account(account["id"])["auth_state"] == "unauthenticated"
    finally:
        db.close()
