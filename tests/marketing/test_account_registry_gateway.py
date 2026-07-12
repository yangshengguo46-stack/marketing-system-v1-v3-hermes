from __future__ import annotations

from agent.account_registry import AccountRegistry
from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import AccountLifecycleRepository
from hermes_state import SessionDB
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
