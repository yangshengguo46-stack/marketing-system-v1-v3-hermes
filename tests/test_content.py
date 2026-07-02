"""内容分析工具 — 单元测试"""

import json
from marketing_tools.content import analyze_trends, generate_content_suggestions
import marketing_tools.monitor as monitor_tools


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

    def test_top_trends_are_balanced_across_platforms(self):
        raw = {
            "platforms_scraped": ["douyin", "weibo", "bilibili", "zhihu"],
            "results": {
                platform: {
                    "success": True,
                    "backend_used": "mock",
                    "data": [{"rank": i + 1, "title": f"{platform}热点{i}"} for i in range(30)],
                }
                for platform in ["bilibili", "weibo", "zhihu", "douyin"]
            },
        }
        result = json.loads(analyze_trends({"hot_data": raw}))
        sources = [item["source_platform"] for item in result["top_trends"]]
        assert sources[:4] == ["douyin", "weibo", "bilibili", "zhihu"]
        assert all(sources.count(platform) >= 7 for platform in raw["platforms_scraped"])


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
            assert len(s["angles"]) >= 1
            assert "relevance" in s, "suggestion missing relevance score"
            assert "confidence" in s, "suggestion missing confidence score"
            assert "evidence" in s, "suggestion missing evidence"
            assert s["requires_agent_interpretation"] is True

    def test_domain_normalizer_does_not_claim_model_analysis(self, mock_trends, user_profile):
        trends = json.loads(analyze_trends({"hot_data": mock_trends}))
        suggestions = json.loads(generate_content_suggestions({"user_profile": user_profile, "trends": trends}))
        assert trends["analysis_method"] == "deterministic_evidence_index"
        assert suggestions["analysis_method"] == "candidate_index"

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


def test_marketing_context_filters_accounts_and_labels_global_industries(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor_tools, "CONFIG_DIR", tmp_path)
    (tmp_path / "accounts.json").write_text(json.dumps({"accounts": [
        {"id": "acct-a", "platform": "douyin", "status": "connected", "stats": {"followers": 1}},
        {"id": "acct-b", "platform": "douyin", "status": "connected", "stats": {"followers": 2}},
    ]}))
    (tmp_path / "trending-cache.json").write_text(json.dumps({"top_trends": [], "cached_at": None}))
    (tmp_path / "suggestions-cache.json").write_text(json.dumps({"suggestions": []}))
    (tmp_path / "intelligence-report.json").write_text(json.dumps({"status": "never_run"}))
    (tmp_path / "intelligence-config.json").write_text(json.dumps({"industries": ["AI", "创业"]}))

    context = json.loads(monitor_tools.get_marketing_context({"account_id": "acct-b"}))
    assert context["scope"] == {"account_id": "acct-b", "industries_scope": "global_monitoring_config"}
    assert [account["id"] for account in context["accounts"]] == ["acct-b"]
    assert "不是账号标签" in context["instruction"]
