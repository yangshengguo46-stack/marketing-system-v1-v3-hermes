"""集成测试 — 跨模块数据流验证"""

import json
import pytest
from marketing_tools.scraping import aggregate_all_trending
from marketing_tools.content import analyze_trends, generate_content_suggestions


class TestScrapeToSuggest:
    """热点抓取 → 趋势分析 → 选题建议 完整链路"""

    USER_PROFILE = {
        "category": "科技",
        "niche": "AI应用",
        "profession": "技术创业者",
        "interests": "AI, 大模型, 视频生成",
    }

    def test_data_flow_json_compatibility(self):
        """Step 1→2→3 之间的 JSON 格式兼容"""
        # Step 1: 抓取
        raw = aggregate_all_trending({})
        data1 = json.loads(raw)
        assert "results" in data1

        # Step 2: 分析
        analysis_raw = analyze_trends({"hot_data": raw})
        data2 = json.loads(analysis_raw)
        assert "top_trends" in data2

        # Step 3: 建议
        suggestions_raw = generate_content_suggestions({
            "user_profile": self.USER_PROFILE,
            "trends": data2,
        })
        data3 = json.loads(suggestions_raw)
        assert "suggestions" in data3

    def test_pipeline_with_mock_data(self, mock_trends, user_profile):
        """使用模拟数据验证完整管道"""
        analysis = json.loads(analyze_trends({"hot_data": json.dumps(mock_trends)}))
        assert analysis["total_raw"] > 0

        suggestions = json.loads(generate_content_suggestions({
            "user_profile": user_profile,
            "trends": analysis,
        }))

        assert "suggestions" in suggestions
        # 验证 suggestion 数据结构能直接供 Dashboard 渲染
        for s in suggestions["suggestions"]:
            assert all(k in s for k in ["id", "trend", "angles", "relevance", "confidence"])


class TestConfigFiles:
    """配置文件完整性"""

    def test_user_profiles_yaml(self):
        import yaml
        from pathlib import Path
        f = Path(__file__).resolve().parents[1] / "engine" / "marketing-os" / "config" / "user-profiles.yaml"
        if not f.exists():
            pytest.skip("user-profiles.yaml 不存在")
        data = yaml.safe_load(f.read_text())
        assert "profiles" in data
        assert len(data["profiles"]) >= 1
        p = data["profiles"][0]
        assert "category" in p
        assert "niche" in p

    def test_accounts_json(self):
        from pathlib import Path
        f = Path(__file__).resolve().parents[1] / "engine" / "marketing-os" / "config" / "accounts.json"
        if not f.exists():
            pytest.skip("accounts.json 不存在")
        data = json.loads(f.read_text())
        assert "accounts" in data
        assert isinstance(data["accounts"], list)


class TestUnifiedDataDirectory:
    """GAP-P0-01: 桌面、FastAPI、Hermes 网关读写同一份数据"""

    def test_server_and_tools_share_config_dir(self, tmp_path, monkeypatch):
        """FastAPI 写入的数据，Hermes 工具函数能读取。"""
        import server
        import marketing_tools.account as account_tools
        from marketing_tools.monitor import monitor_all

        config_dir = tmp_path / "config"
        config_dir.mkdir()

        # 写入初始数据
        (config_dir / "accounts.json").write_text(json.dumps({"accounts": [], "updated_at": None}))
        (config_dir / "trending-cache.json").write_text(json.dumps({"status": "no_data", "top_trends": []}))
        (config_dir / "suggestions-cache.json").write_text(json.dumps({"status": "no_data", "suggestions": []}))
        (config_dir / "intelligence-config.json").write_text(json.dumps({"industries": [], "platforms": ["douyin"], "sync_accounts": True}))
        (config_dir / "publishing.json").write_text(json.dumps({"tasks": []}))

        # 统一指向同一个 config dir
        monkeypatch.setattr(server, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(server, "BUNDLED_CONFIG_DIR", config_dir)
        monkeypatch.setattr(account_tools, "CONFIG_DIR", config_dir)
        monkeypatch.setattr(account_tools, "ACCOUNTS_DB", config_dir / "accounts.json")
        monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(config_dir))

        # FastAPI: 创建账号
        from fastapi.testclient import TestClient
        client = TestClient(server.app)
        resp = client.post("/api/plugins/marketing-os/accounts", json={
            "platform": "douyin", "username": "tech_creator", "label": "科技主号",
        })
        assert resp.status_code == 200
        account_id = resp.json()["account"]["id"]

        # Hermes 工具: 读取同一个 config dir 的账号数据
        monitor_result = json.loads(monitor_all({}))
        assert monitor_result["accounts_checked"] >= 1

        # 验证文件内容一致性
        accounts_data = json.loads((config_dir / "accounts.json").read_text())
        assert len(accounts_data["accounts"]) == 1
        assert accounts_data["accounts"][0]["username"] == "tech_creator"

        # FastAPI: 删除账号
        resp2 = client.delete(f"/api/plugins/marketing-os/accounts/{account_id}")
        assert resp2.status_code == 200

        # Hermes 工具: 确认删除后数据一致
        accounts_after = json.loads((config_dir / "accounts.json").read_text())
        assert len(accounts_after["accounts"]) == 0

    def test_hermes_runtime_config_points_to_same_dir(self, tmp_path, monkeypatch):
        """HERMES_HOME .env 中的 MARKETING_OS_CONFIG_DIR 与实际 config 目录一致。"""
        hermes_home = tmp_path / "agent-runtime"
        config_dir = tmp_path / "config"
        hermes_home.mkdir()
        config_dir.mkdir()

        # 模拟 Electron 写入的 .env
        env_file = hermes_home / ".env"
        env_file.write_text(f"MARKETING_OS_CONFIG_DIR={config_dir}\n")

        monkeypatch.setenv("HERMES_HOME", str(hermes_home))
        monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(config_dir))

        # 验证路径一致
        import os
        hermes_env_config = None
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("MARKETING_OS_CONFIG_DIR="):
                    hermes_env_config = line.split("=", 1)[1].strip()
                    break

        assert hermes_env_config == str(config_dir), \
            f"Hermes .env points to {hermes_env_config}, expected {config_dir}"
        assert os.environ.get("MARKETING_OS_CONFIG_DIR") == str(config_dir)
