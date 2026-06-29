"""集成测试 — 跨模块数据流验证"""

import json
import pytest
from tools.scraping import aggregate_all_trending
from tools.content import analyze_trends, generate_content_suggestions


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
            assert all(k in s for k in ["id", "trend", "angles", "hot_level", "estimated_traffic"])


class TestPluginRegistration:
    """验证 Hermes plugin 注册入口 (需 Hermes 运行时)"""

    @pytest.mark.skip(reason="相对导入需 Hermes 运行时包上下文，工具函数已有独立单元测试覆盖")
    def test_register_calls_all_modules(self, mock_hermes_ctx):
        from importlib import import_module
        plugin = import_module("marketing-os")
        plugin.register(mock_hermes_ctx)
        assert mock_hermes_ctx.register_tool.call_count >= 12


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
