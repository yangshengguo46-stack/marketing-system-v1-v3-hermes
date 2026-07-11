from __future__ import annotations

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
