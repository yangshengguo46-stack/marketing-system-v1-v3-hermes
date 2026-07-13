from __future__ import annotations

import json

from agent.account_registry import AccountRegistry
from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import AccountLifecycleRepository
from hermes_state import SessionDB
from tools import mcp_tool
from tui_gateway import server


def test_gateway_account_lifecycle_is_owned_by_hermes(tmp_path, monkeypatch):
    db = SessionDB(db_path=tmp_path / "state.db")
    monkeypatch.setattr(server, "_db", db)
    try:
        created = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "register",
                "method": "marketing.accounts.register",
                "params": {
                    "platform": "zhihu",
                    "label": "知乎主账号",
                    "permissions": {"read_metrics": True, "publish": "one_shot"},
                },
            }
        )["result"]["account"]
        assert created["status"] == "pending"
        assert created["profile_key"] == f"zhihu:{created['id']}"

        disconnected = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "disconnect",
                "method": "marketing.account.disconnect",
                "params": {"account_id": created["id"]},
            }
        )["result"]["account"]
        assert disconnected["status"] == "disconnected"

        deleted = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "delete",
                "method": "marketing.account.delete",
                "params": {"account_id": created["id"]},
            }
        )["result"]
        assert deleted == {"deleted": True}
        assert db.list_marketing_accounts() == []
    finally:
        db.close()


def test_gateway_exposes_native_prospect_adoption(tmp_path, monkeypatch):
    state_path = tmp_path / "state.db"
    db = SessionDB(db_path=state_path)
    monkeypatch.setattr(server, "_db", db)
    paths = MarketingDataPaths(tmp_path, tmp_path / "config", state_path)
    try:
        project = AccountLifecycleRepository(paths).begin_project(
            user_id="default",
            account_id="prospect_default",
            business_goal="建立长期内容方向",
        )
        registry = AccountRegistry(db)
        account = registry.register_pending(platform="zhihu")
        registry.mark_authenticated(account["id"])

        response = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "adopt-prospect",
                "method": "marketing.account.prospect.adopt",
                "params": {
                    "prospect_account_id": "prospect_default",
                    "target_account_id": account["id"],
                },
            }
        )

        assert response["result"]["operation"] == "adopted"
        assert response["result"]["successor_session_required"] is True
        adopted = AccountLifecycleRepository(paths).begin_project(
            user_id="default",
            account_id=account["id"],
            business_goal="不会覆盖原项目",
        )
        assert adopted["id"] == project["id"]
        assert adopted["operation"] == "existing"
    finally:
        db.close()


def test_gateway_starts_and_verifies_login_through_native_browser_owner(tmp_path, monkeypatch):
    db = SessionDB(db_path=tmp_path / "state.db")
    monkeypatch.setattr(server, "_db", db)
    calls = []

    def fake_browser(**kwargs):
        calls.append(kwargs)
        if kwargs["tool_name"] == "browser_start_account_login":
            return '{"schema":"marketing_account_login_started.v1"}'
        account = db.get_marketing_account(kwargs["account_id"])
        return (
            '{"schema":"marketing_account_auth_verification.v1",'
            f'"account_id":"{account["id"]}",'
            f'"platform":"{account["platform"]}",'
            '"verified":true}'
        )

    monkeypatch.setattr(mcp_tool, "execute_marketing_account_browser_tool", fake_browser)
    monkeypatch.setattr(
        mcp_tool,
        "reconcile_marketing_account_browser",
        lambda **kwargs: calls.append({"reconcile": kwargs}) or True,
    )
    try:
        account = AccountRegistry(db).register_pending(platform="douyin")
        started = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "start",
                "method": "marketing.account.login.start",
                "params": {"account_id": account["id"]},
            }
        )["result"]
        assert started["login_state"] == "waiting_for_user"
        assert started["browser_owner"] == "marketing-browser-mcp"

        verified = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "verify",
                "method": "marketing.account.login.verify",
                "params": {"account_id": account["id"]},
            }
        )["result"]
        assert verified["verified"] is True
        assert verified["account"]["auth_state"] == "authenticated"
        assert [call["tool_name"] for call in calls if "tool_name" in call] == [
            "browser_start_account_login",
            "browser_verify_account_login",
        ]
    finally:
        db.close()


def test_gateway_exposes_supported_platform_catalog_and_rejects_unknown(tmp_path, monkeypatch):
    db = SessionDB(db_path=tmp_path / "state.db")
    monkeypatch.setattr(server, "_db", db)
    try:
        catalog = server.handle_request(
            {"jsonrpc": "2.0", "id": "catalog", "method": "marketing.accounts.platforms", "params": {}}
        )["result"]
        platform_ids = {item["id"] for item in catalog["platforms"]}
        assert {"douyin", "wechat_official", "zhihu"}.issubset(platform_ids)
        assert "weibo" not in platform_ids

        response = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "invalid",
                "method": "marketing.accounts.register",
                "params": {"platform": "weibo"},
            }
        )
        assert response["error"]["code"] == -32602
    finally:
        db.close()


def test_gateway_syncs_douyin_metrics_through_native_browser_owner(tmp_path, monkeypatch):
    db = SessionDB(db_path=tmp_path / "state.db")
    monkeypatch.setattr(server, "_db", db)
    calls = []

    def fake_browser(**kwargs):
        calls.append(kwargs)
        return json.dumps(
            {
                "schema": "marketing_douyin_owned_portfolio.v1",
                "platform": "douyin",
                "observed_at": "2026-07-13T12:00:00Z",
                "account": {"name": "杨炎昭"},
                "stats": {
                    "followers": 4,
                    "total_likes": 56,
                    "all_work_count": 4,
                    "public_work_count": 3,
                    "private_work_count": 1,
                    "public_view_count": 5366,
                },
                "works": [],
                "collection": {"complete": True},
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(mcp_tool, "execute_marketing_account_browser_tool", fake_browser)
    try:
        registry = AccountRegistry(db)
        account = registry.register_pending(platform="douyin")
        registry.mark_authenticated(account["id"])

        result = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": "sync",
                "method": "marketing.account.sync",
                "params": {"account_id": account["id"]},
            }
        )["result"]

        assert result["account"]["stats"]["videos_count"] == 3
        assert result["account"]["stats"]["all_videos_count"] == 4
        assert result["account"]["stats"]["total_views"] == 5366
        assert calls[0]["tool_name"] == "browser_collect_douyin_portfolio"
        assert calls[0]["arguments"] == {"max_works": 50}
    finally:
        db.close()
