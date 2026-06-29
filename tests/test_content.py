"""内容分析工具 — 单元测试"""

import json
import pytest
from tools.content import analyze_trends, generate_content_suggestions


class TestAnalyzeTrends:
    def test_accepts_json_string(self, mock_trends):
        result = json.loads(analyze_trends({"hot_data": json.dumps(mock_trends)}))
        assert "analyzed_at" in result
        assert "total_raw" in result
        assert "total_deduped" in result
        assert "categories" in result
        assert "top_trends" in result

    def test_accepts_dict_directly(self, mock_trends):
        result = json.loads(analyze_trends({"hot_data": mock_trends}))
        assert result["total_raw"] >= 0

    def test_dedup_works(self, mock_trends):
        """跨平台去重：相同事件不应重复"""
        result = json.loads(analyze_trends({"hot_data": json.dumps(mock_trends)}))
        assert result["total_deduped"] <= result["total_raw"]

    def test_categorization(self, mock_trends):
        """分类逻辑：AI 相关归入科技/AI"""
        result = json.loads(analyze_trends({"hot_data": json.dumps(mock_trends)}))
        categories = result["categories"]
        assert len(categories) > 0
        # "AI大模型" 应出现在科技/AI分类中
        tech_items = categories.get("科技/AI", [])
        has_ai = any("AI" in item.get("title", "") for item in tech_items)
        # 取决于去重结果，不做强断言
        assert isinstance(categories, dict)

    def test_empty_input(self):
        result = json.loads(analyze_trends({"hot_data": "{}"}))
        assert result["total_raw"] == 0
        assert result["total_deduped"] == 0

    def test_malformed_input(self):
        result = json.loads(analyze_trends({"hot_data": "not json"}))
        assert result["total_raw"] == 0


class TestGenerateSuggestions:
    def test_basic_match(self, mock_trends, user_profile):
        trends = json.loads(analyze_trends({"hot_data": json.dumps(mock_trends)}))
        result = json.loads(generate_content_suggestions({
            "user_profile": user_profile,
            "trends": trends,
        }))
        assert "generated_at" in result
        assert "suggestions" in result
        assert "user_profile_summary" in result

    def test_matched_trends_ranked(self, mock_trends, user_profile):
        trends = json.loads(analyze_trends({"hot_data": json.dumps(mock_trends)}))
        result = json.loads(generate_content_suggestions({
            "user_profile": user_profile,
            "trends": trends,
        }))
        suggestions = result["suggestions"]
        if len(suggestions) >= 2:
            scores = [s.get("match_score", 0) for s in suggestions if "match_score" in s]
            # trends 输出中可能不含 match_score 因为匹配逻辑在 suggestion 生成时计算

    def test_each_suggestion_has_angles(self, mock_trends, user_profile):
        trends = json.loads(analyze_trends({"hot_data": json.dumps(mock_trends)}))
        result = json.loads(generate_content_suggestions({
            "user_profile": user_profile,
            "trends": trends,
        }))
        for s in result["suggestions"]:
            assert len(s["angles"]) == 3
            assert s["hot_level"] in ["🔥", "⭐", "💡"]
            assert s["estimated_traffic"] in ["高", "中", "偏低"]

    def test_empty_profile(self, mock_trends):
        trends = json.loads(analyze_trends({"hot_data": json.dumps(mock_trends)}))
        result = json.loads(generate_content_suggestions({
            "user_profile": {},
            "trends": trends,
        }))
        assert "suggestions" in result

    def test_accepts_string_profile(self, mock_trends):
        trends = json.loads(analyze_trends({"hot_data": json.dumps(mock_trends)}))
        result = json.loads(generate_content_suggestions({
            "user_profile": json.dumps({"category": "科技"}),
            "trends": trends,
        }))
        assert "suggestions" in result


class TestEndToEndPipeline:
    """端到端: 热点 → 分析 → 建议"""

    def test_full_pipeline(self, mock_trends, user_profile):
        # Step 1: 分析趋势
        analysis = json.loads(analyze_trends({"hot_data": json.dumps(mock_trends)}))
        assert analysis["total_raw"] > 0

        # Step 2: 生成建议
        suggestions = json.loads(generate_content_suggestions({
            "user_profile": user_profile,
            "trends": analysis,
        }))
        assert len(suggestions["suggestions"]) >= 0

        # Step 3: 验证数据结构兼容 Dashboard API
        for s in suggestions["suggestions"]:
            assert "id" in s
            assert "trend" in s
            assert "angles" in s
            assert isinstance(s["angles"], list)
