from __future__ import annotations

import json

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import AccountContextRepository
from hermes_state import SessionDB
import pytest


def test_session_db_owns_secret_free_marketing_accounts(tmp_path):
    db = SessionDB(db_path=tmp_path / "state.db")
    try:
        account = db.upsert_marketing_account(
            account_id="acct_ab3145",
            platform="douyin",
            platform_user_id="66867825385",
            username="杨炎昭",
            label="主账号",
            status="active",
            auth_state="authenticated",
            permissions={"read_metrics": True, "publish": "one_shot"},
            stats={"followers": 4},
        )

        assert account["profile_key"] == "douyin:acct_ab3145"
        assert account["stats"] == {"followers": 4}
        assert account["permissions"]["publish"] == "one_shot"
        assert "cookie" not in account
        assert db.list_marketing_accounts()[0]["id"] == "acct_ab3145"

        assert db.delete_marketing_account("acct_ab3145") is True
        assert db.list_marketing_accounts() == []
        assert db.get_marketing_account("acct_ab3145", include_deleted=True)["status"] == "deleted"
    finally:
        db.close()


def test_account_owner_rejects_profile_path_segments(tmp_path):
    db = SessionDB(db_path=tmp_path / "state.db")
    try:
        with pytest.raises(ValueError, match="invalid account_id"):
            db.upsert_marketing_account(account_id="..", platform="zhihu")
    finally:
        db.close()


def test_account_context_imports_legacy_json_once_into_hermes(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "accounts.json").write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "id": "acct_legacy",
                        "platform": "zhihu",
                        "username": "creator",
                        "status": "active",
                        "stats": {"followers": 12},
                        "cookie": "must-never-migrate",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    paths = MarketingDataPaths(
        user_data=tmp_path,
        config_dir=config_dir,
        agent_db=tmp_path / "agent-runtime" / "agent_core.db",
    )
    db = SessionDB(db_path=tmp_path / "state.db")
    try:
        repository = AccountContextRepository(paths, session_db=db)
        first = repository.list_accounts()
        (config_dir / "accounts.json").write_text('{"accounts": []}', encoding="utf-8")
        second = repository.list_accounts()

        assert first["source"] == "hermes_state"
        assert first["accounts"][0]["id"] == "acct_legacy"
        assert first["accounts"][0]["auth_state"] == "authenticated"
        assert "cookie" not in first["accounts"][0]
        assert second["accounts"][0]["id"] == "acct_legacy"
    finally:
        db.close()
