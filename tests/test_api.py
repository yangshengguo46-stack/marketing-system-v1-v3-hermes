"""Dashboard API — 接口契约测试"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

CONFIG_DIR = Path(__file__).resolve().parents[1] / "engine" / "marketing-os" / "config"


@pytest.fixture
def api_client():
    from dashboard.plugin_api import router
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestAccountsAPI:
    def test_get_empty(self, api_client, tmp_path):
        acct_file = tmp_path / "empty.json"
        acct_file.write_text(json.dumps({"accounts": [], "updated_at": None}))
        with patch("dashboard.plugin_api.ACCOUNTS_DB", acct_file):
            resp = api_client.get("/api/plugins/marketing-os/accounts")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 0

    def test_create_account(self, api_client):
        resp = api_client.post("/api/plugins/marketing-os/accounts", json={
            "platform": "douyin", "username": "testuser"
        })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_create_missing_fields(self, api_client):
        resp = api_client.post("/api/plugins/marketing-os/accounts", json={})
        assert resp.status_code == 400
        resp2 = api_client.post("/api/plugins/marketing-os/accounts", json={"platform": "douyin"})
        assert resp2.status_code == 400

    def test_delete_account(self, api_client, tmp_path):
        acct_file = tmp_path / "accounts.json"
        acct_file.write_text(json.dumps({
            "accounts": [{"id": "acct_0001", "platform": "douyin", "username": "u1"}]
        }))
        with patch("dashboard.plugin_api.ACCOUNTS_DB", acct_file):
            resp = api_client.delete("/api/plugins/marketing-os/accounts/acct_0001")
            assert resp.status_code == 200


class TestTrendingAPI:
    def test_get_no_data(self, api_client):
        with patch("dashboard.plugin_api.CONFIG_DIR", CONFIG_DIR):
            with patch.object(Path, "exists", return_value=False):
                resp = api_client.get("/api/plugins/marketing-os/trending")
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "no_data"

    def test_refresh_trigger(self, api_client):
        resp = api_client.post("/api/plugins/marketing-os/trending/refresh")
        assert resp.status_code == 200
        assert resp.json()["status"] == "triggered"


class TestSuggestionsAPI:
    def test_get_no_data(self, api_client):
        with patch.object(Path, "exists", return_value=False):
            resp = api_client.get("/api/plugins/marketing-os/suggestions")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "no_data"


class TestDashboardOverview:
    def test_overview_schema(self, api_client):
        resp = api_client.get("/api/plugins/marketing-os/dashboard/overview")
        assert resp.status_code == 200
        data = resp.json()
        required_fields = [
            "accounts_connected", "trending_topics_today",
            "suggestions_generated", "videos_published",
            "total_followers", "follower_growth_today"
        ]
        for field in required_fields:
            assert field in data, f"缺少字段: {field}"
            assert isinstance(data[field], (int, float)), f"{field} 应该是数字"


class TestAPIContract:
    """所有 API 端点返回符合契约的 JSON"""

    ENDPOINTS = [
        ("GET", "/api/plugins/marketing-os/accounts"),
        ("GET", "/api/plugins/marketing-os/dashboard/overview"),
    ]

    def test_all_get_endpoints_return_json(self, api_client):
        for method, path in self.ENDPOINTS:
            resp = api_client.get(path)
            assert resp.status_code == 200, f"{path} 返回 {resp.status_code}"
            assert resp.headers.get("content-type", "").startswith("application/json"), \
                f"{path} 未返回 JSON"

    def test_all_endpoints_no_500(self, api_client):
        # trending/suggestions 需要读缓存，mock 掉文件exists
        with patch.object(Path, "exists", return_value=False):
            for method, path in [
                ("GET", "/api/plugins/marketing-os/accounts"),
                ("GET", "/api/plugins/marketing-os/trending"),
                ("GET", "/api/plugins/marketing-os/suggestions"),
                ("GET", "/api/plugins/marketing-os/dashboard/overview"),
            ]:
                resp = api_client.get(path)
                assert resp.status_code != 500, f"{path} 返回 500: {resp.text[:200]}"
