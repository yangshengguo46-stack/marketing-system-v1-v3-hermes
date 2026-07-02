"""Account metadata boundary tests."""

import json
from unittest.mock import patch

from marketing_tools.account import (
    add_account, get_account_stats, list_accounts, monitor_all_accounts,
    remove_account, update_account_status,
    update_account_identity,
)


@patch("marketing_tools.account._write_accounts_db")
@patch("marketing_tools.account._read_accounts_db")
def test_add_account_stores_metadata_only(mock_read, mock_write):
    mock_read.return_value = {"accounts": [], "updated_at": None}
    result = json.loads(add_account({"platform": "douyin", "username": "tester", "label": "主号"}))
    assert result["success"] is True
    assert result["account"]["status"] == "connected"
    assert "password" not in result["account"]
    assert "bitwarden_id" not in result["account"]
    mock_write.assert_called_once()


@patch("marketing_tools.account._write_accounts_db")
@patch("marketing_tools.account._read_accounts_db")
def test_add_account_preserves_electron_account_id(mock_read, mock_write):
    mock_read.return_value = {"accounts": [], "updated_at": None}
    result = json.loads(add_account({
        "account_id": "acct_electron123",
        "platform": "douyin",
        "username": "creator-1",
    }))
    assert result["account"]["id"] == "acct_electron123"
    assert mock_write.call_args.args[0]["accounts"][0]["id"] == "acct_electron123"


@patch("marketing_tools.account._write_accounts_db")
@patch("marketing_tools.account._read_accounts_db")
def test_reconnect_reuses_existing_partition_identity(mock_read, mock_write):
    mock_read.return_value = {"accounts": [{
        "id": "acct_electron123", "platform": "douyin", "username": "old",
        "label": "主账号", "status": "disconnected",
    }]}
    result = json.loads(add_account({
        "account_id": "acct_electron123", "platform": "douyin",
        "username": "creator-1", "label": "主账号",
    }))
    assert result["created"] is False
    assert result["account"]["status"] == "connected"
    assert result["account"]["username"] == "creator-1"


@patch("marketing_tools.account._read_accounts_db")
def test_same_identity_cannot_move_to_another_partition(mock_read):
    mock_read.return_value = {"accounts": [{
        "id": "acct_original1", "platform": "douyin", "username": "creator-1",
    }]}
    result = json.loads(add_account({
        "account_id": "acct_different2", "platform": "douyin", "username": "creator-1",
    }))
    assert result["success"] is False
    assert result["code"] == "account_identity_conflict"
    assert result["existing_account_id"] == "acct_original1"


@patch("marketing_tools.account._write_accounts_db")
@patch("marketing_tools.account._read_accounts_db")
def test_placeholder_identity_does_not_collapse_isolated_accounts(mock_read, mock_write):
    mock_read.return_value = {"accounts": [{
        "id": "acct_first111", "platform": "douyin", "username": "douyin_session",
    }]}
    result = json.loads(add_account({
        "account_id": "acct_second22", "platform": "douyin", "username": "douyin_session",
    }))
    assert result["success"] is True
    assert result["created"] is True
    assert result["account"]["id"] == "acct_second22"
    assert len(mock_write.call_args.args[0]["accounts"]) == 2


@patch("marketing_tools.account._write_accounts_db")
@patch("marketing_tools.account._read_accounts_db")
def test_account_status_can_be_disconnected_without_deleting_metadata(mock_read, mock_write):
    mock_read.return_value = {"accounts": [{
        "id": "acct_1", "platform": "douyin", "status": "connected",
    }]}
    result = json.loads(update_account_status({"account_id": "acct_1", "status": "disconnected"}))
    assert result["success"] is True
    assert result["account"]["status"] == "disconnected"


@patch("marketing_tools.account._write_accounts_db")
@patch("marketing_tools.account._read_accounts_db")
def test_electron_can_replace_placeholder_with_public_identity(mock_read, mock_write):
    mock_read.return_value = {"accounts": [{
        "id": "acct_1", "platform": "douyin", "username": "douyin_session",
        "label": "douyin账号", "status": "connected",
    }]}
    result = json.loads(update_account_identity({
        "account_id": "acct_1", "username": "public-user-1", "label": "真实昵称",
    }))
    assert result["success"] is True
    assert result["account"]["username"] == "public-user-1"
    assert result["account"]["label"] == "真实昵称"


def test_account_backend_rejects_secrets():
    for field in ("password", "cookie", "token", "api_key"):
        result = json.loads(add_account({"platform": "douyin", "username": "tester", field: "secret"}))
        assert result["success"] is False
        assert result["code"] == "secret_boundary_violation"


def test_required_fields_return_structured_error():
    assert json.loads(add_account({"platform": "douyin"}))["success"] is False
    assert json.loads(add_account({"username": "tester"}))["success"] is False


@patch("marketing_tools.account._read_accounts_db")
def test_list_accounts_can_filter_platform(mock_read):
    mock_read.return_value = {"accounts": [
        {"id": "a", "platform": "douyin"},
        {"id": "b", "platform": "weibo"},
    ]}
    result = json.loads(list_accounts({"platform": "douyin"}))
    assert result["total"] == 1
    assert result["accounts"][0]["id"] == "a"


@patch("marketing_tools.account._write_accounts_db")
@patch("marketing_tools.account._read_accounts_db")
def test_remove_metadata_requests_electron_session_cleanup(mock_read, mock_write):
    mock_read.return_value = {"accounts": [{"id": "acct_1", "platform": "douyin"}]}
    result = json.loads(remove_account({"account_id": "acct_1"}))
    assert result["success"] is True
    assert result["session_cleanup_required"] is True


@patch("marketing_tools.account._read_accounts_db")
def test_get_stats_never_returns_browser_instruction(mock_read):
    mock_read.return_value = {"accounts": [{
        "id": "acct_1", "platform": "douyin", "username": "u1",
        "stats": {"followers": 120, "updated_at": "2026-06-29T10:00:00"},
    }]}
    result = json.loads(get_account_stats({"account_id": "acct_1"}))
    assert result["success"] is True
    assert result["source"] == "electron_session_snapshot"
    assert "stats_instruction" not in result


@patch("marketing_tools.account._read_accounts_db")
def test_monitor_all_reads_persisted_snapshots(mock_read):
    mock_read.return_value = {"accounts": [{"id": "acct_1", "stats": {"followers": 1}}]}
    result = json.loads(monitor_all_accounts({}))
    assert result["total_accounts"] == 1
    assert result["source"] == "persisted_snapshots"
