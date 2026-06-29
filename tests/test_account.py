"""账号管理工具 — 单元测试"""

import json
import pytest
from unittest.mock import patch, MagicMock
from tools.account import (
    add_account,
    list_accounts,
    remove_account,
    get_account_stats,
    monitor_all_accounts,
)


class TestAddAccount:
    @patch("tools.account.subprocess.run")
    @patch("tools.account._write_accounts_db")
    @patch("tools.account._read_accounts_db")
    def test_add_new_account(self, mock_read, mock_write, mock_run):
        mock_read.return_value = {"accounts": [], "updated_at": None}
        # 模拟 Bitwarden 创建成功
        mock_template = MagicMock()
        mock_template.stdout = json.dumps({
            "name": "marketing-os:test",
            "login": {"username": "testuser", "password": "secret"},
        })
        mock_create = MagicMock()
        mock_create.stdout = json.dumps({"id": "bw-item-001"})
        mock_run.side_effect = [mock_template, mock_create]

        result = json.loads(add_account({
            "platform": "douyin",
            "username": "testuser",
            "password": "secret",
            "label": "公司主号",
        }))

        assert result["success"] is True
        assert result["account"]["platform"] == "douyin"
        assert result["account"]["bitwarden_id"] == "bw-item-001"

    @patch("tools.account._write_accounts_db")
    @patch("tools.account._read_accounts_db")
    def test_add_without_password(self, mock_read, mock_write):
        mock_read.return_value = {"accounts": [], "updated_at": None}
        result = json.loads(add_account({
            "platform": "bilibili",
            "username": "testuser",
        }))
        assert result["success"] is True
        assert result["account"]["bitwarden_id"] is None  # Bitwarden 调用失败，但不阻塞

    def test_required_fields(self):
        """platform 和 username 必填"""
        with pytest.raises(KeyError):
            add_account({"platform": "douyin"})
        with pytest.raises(KeyError):
            add_account({"username": "test"})


class TestListAccounts:
    @patch("tools.account._read_accounts_db")
    def test_empty(self, mock_read):
        mock_read.return_value = {"accounts": [], "updated_at": None}
        result = json.loads(list_accounts({}))
        assert result["total"] == 0
        assert result["accounts"] == []

    @patch("tools.account._read_accounts_db")
    def test_list_all(self, mock_read):
        mock_read.return_value = {
            "accounts": [
                {"id": "acct_0001", "platform": "douyin", "username": "u1", "status": "active"},
                {"id": "acct_0002", "platform": "weibo", "username": "u2", "status": "active"},
            ]
        }
        result = json.loads(list_accounts({}))
        assert result["total"] == 2

    @patch("tools.account._read_accounts_db")
    def test_filter_by_platform(self, mock_read):
        mock_read.return_value = {
            "accounts": [
                {"id": "acct_0001", "platform": "douyin", "username": "u1"},
                {"id": "acct_0002", "platform": "weibo", "username": "u2"},
            ]
        }
        result = json.loads(list_accounts({"platform": "douyin"}))
        assert result["total"] == 1
        assert result["accounts"][0]["platform"] == "douyin"


class TestRemoveAccount:
    @patch("tools.account._write_accounts_db")
    @patch("tools.account._read_accounts_db")
    def test_remove_existing(self, mock_read, mock_write):
        mock_read.return_value = {
            "accounts": [
                {"id": "acct_0001", "platform": "douyin", "username": "u1"},
            ]
        }
        result = json.loads(remove_account({"account_id": "acct_0001"}))
        assert result["success"] is True
        assert result["removed"] == "acct_0001"

    @patch("tools.account._read_accounts_db")
    def test_remove_nonexistent(self, mock_read):
        mock_read.return_value = {"accounts": []}
        result = json.loads(remove_account({"account_id": "nonexistent"}))
        assert result["success"] is False
        assert "不存在" in result["error"]


class TestGetAccountStats:
    @patch("tools.account._read_accounts_db")
    def test_unsupported_platform(self, mock_read):
        mock_read.return_value = {
            "accounts": [{"id": "acct_0001", "platform": "unknown", "username": "u1"}]
        }
        result = json.loads(get_account_stats({"account_id": "acct_0001"}))
        assert result["success"] is False

    @patch("tools.account._read_accounts_db")
    def test_supported_platform(self, mock_read):
        mock_read.return_value = {
            "accounts": [{"id": "acct_0001", "platform": "douyin", "username": "u1"}]
        }
        result = json.loads(get_account_stats({"account_id": "acct_0001"}))
        assert result["success"] is True
        assert "stats_instruction" in result


class TestMonitorAll:
    @patch("tools.account._read_accounts_db")
    def test_monitor_empty(self, mock_read):
        mock_read.return_value = {"accounts": []}
        result = json.loads(monitor_all_accounts({}))
        assert result["total_accounts"] == 0
        assert result["results"] == []

    @patch("tools.account._read_accounts_db")
    def test_monitor_with_accounts(self, mock_read):
        mock_read.return_value = {
            "accounts": [
                {"id": "acct_0001", "platform": "douyin", "username": "u1", "label": "主号", "status": "active"},
                {"id": "acct_0002", "platform": "bilibili", "username": "u2", "label": "副号", "status": "active"},
            ]
        }
        result = json.loads(monitor_all_accounts({}))
        assert result["total_accounts"] == 2
        assert len(result["results"]) == 2
