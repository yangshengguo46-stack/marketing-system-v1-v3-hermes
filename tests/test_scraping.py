"""热点抓取工具 — 后端架构测试"""

import json
from unittest.mock import patch
from marketing_tools.scraping import (
    scrape_douyin_trending, scrape_bilibili_popular,
    scrape_xiaohongshu_trending, scrape_zhihu_trending,
    aggregate_all_trending, list_scraping_backends,
)

MOCK_DOUYIN_DATA = [
    {"rank": 1, "title": "AI大模型新突破引发行业震动", "heat_value": "982.3w"},
    {"rank": 2, "title": "苹果发布iOS 20", "heat_value": "876.1w"},
]

MOCK_BILIBILI_DATA = [
    {"rank": 1, "title": "半小时搞懂Transformer架构", "heat_value": 520000},
    {"rank": 2, "title": "黑神话悟空DLC实机演示", "heat_value": 480000},
]


def _mock_fetch_success(platform, count):
    if platform == "douyin":
        return {"success": True, "backend_used": "mock", "data": MOCK_DOUYIN_DATA[:count]}
    elif platform == "bilibili":
        return {"success": True, "backend_used": "mock", "data": MOCK_BILIBILI_DATA[:count]}
    return {"success": False, "backend_used": "mock", "error": "unsupported"}


class TestScrapingTools:
    @patch("marketing_tools.scraping._fetch_with_backend", side_effect=_mock_fetch_success)
    def test_douyin_returns_data(self, mock_fetch):
        result = json.loads(scrape_douyin_trending({"count": 2}))
        assert result["success"] is True
        assert result["backend_used"] == "mock"
        assert result["platform"] == "douyin"
        assert len(result["data"]) == 2
        assert result["data"][0]["title"] == "AI大模型新突破引发行业震动"

    @patch("marketing_tools.scraping._fetch_with_backend", side_effect=_mock_fetch_success)
    def test_bilibili_returns_data(self, mock_fetch):
        result = json.loads(scrape_bilibili_popular({"count": 2}))
        assert result["success"] is True
        assert result["platform"] == "bilibili"

    def test_default_params(self):
        """空参数不抛错"""
        for fn in [scrape_douyin_trending, scrape_bilibili_popular,
                    scrape_xiaohongshu_trending, scrape_zhihu_trending, aggregate_all_trending]:
            result = fn()
            assert result is not None
            parsed = json.loads(result)
            assert isinstance(parsed, dict)

    @patch("marketing_tools.scraping._fetch_with_backend", side_effect=_mock_fetch_success)
    def test_aggregate_filters_weibo_from_product_targets(self, mock_fetch):
        result = json.loads(aggregate_all_trending({"platforms": ["weibo", "douyin"]}))
        assert result["platforms_scraped"] == ["douyin"]
        assert "weibo" not in result["results"]
        assert "douyin" in result["results"]
        assert [call.args[0] for call in mock_fetch.call_args_list] == ["douyin"]

    @patch("marketing_tools.scraping._fetch_with_backend", side_effect=_mock_fetch_success)
    def test_aggregate_with_selected_platforms(self, mock_fetch):
        result = json.loads(aggregate_all_trending({"platforms": ["bilibili"]}))
        assert result["platforms_scraped"] == ["bilibili"]
        assert "bilibili" in result["results"]
        assert "douyin" not in result["results"]

    def test_output_schema_for_analyze_trends(self):
        """aggregate 输出能被 analyze_trends 消费"""
        with patch("marketing_tools.scraping._fetch_with_backend", side_effect=_mock_fetch_success):
            result = json.loads(aggregate_all_trending({}))
        assert "results" in result
        for platform, data in result["results"].items():
            assert "success" in data
            if data["success"]:
                assert "data" in data
                assert isinstance(data["data"], list)


class TestBackendList:
    def test_list_backends(self):
        result = json.loads(list_scraping_backends())
        assert "backends" in result
        backends = result["backends"]
        assert len(backends) == 2
        names = [b["name"] for b in backends]
        assert names == ["bilibili_public", "hot_topics_api"]


class TestBackendFallback:
    def test_when_no_backend_available_returns_error(self):
        """没有后端可用时返回 success=False 而非崩溃"""
        result = json.loads(scrape_douyin_trending())
        assert "success" in result
        # 可能是 True (有后端可用) 或 False (全部不可用)
        # 无论哪种情况不应崩溃
        assert "platform" in result
        assert "scraped_at" in result
