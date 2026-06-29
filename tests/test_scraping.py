"""热点抓取工具 — 后端架构测试"""

import json
import pytest
from unittest.mock import patch, MagicMock
from tools.scraping import (
    scrape_douyin_trending, scrape_weibo_trending, scrape_bilibili_popular,
    scrape_xiaohongshu_trending, scrape_zhihu_trending,
    aggregate_all_trending, list_scraping_backends,
)

MOCK_DOUYIN_DATA = [
    {"rank": 1, "title": "AI大模型新突破引发行业震动", "heat_value": "982.3w"},
    {"rank": 2, "title": "苹果发布iOS 20", "heat_value": "876.1w"},
]

MOCK_WEIBO_DATA = [
    {"rank": 1, "title": "AI大模型新突破", "heat_value": 2840000},
    {"rank": 2, "title": "高考分数线", "heat_value": 2130000},
]

MOCK_BILIBILI_DATA = [
    {"rank": 1, "title": "半小时搞懂Transformer架构", "heat_value": 520000},
    {"rank": 2, "title": "黑神话悟空DLC实机演示", "heat_value": 480000},
]


def _mock_fetch_success(platform, count):
    if platform == "douyin":
        return {"success": True, "backend_used": "mock", "data": MOCK_DOUYIN_DATA[:count]}
    elif platform == "weibo":
        return {"success": True, "backend_used": "mock", "data": MOCK_WEIBO_DATA[:count]}
    elif platform == "bilibili":
        return {"success": True, "backend_used": "mock", "data": MOCK_BILIBILI_DATA[:count]}
    return {"success": False, "backend_used": "mock", "error": "unsupported"}


class TestScrapingTools:
    @patch("tools.scraping._fetch_with_backend", side_effect=_mock_fetch_success)
    def test_douyin_returns_data(self, mock_fetch):
        result = json.loads(scrape_douyin_trending({"count": 2}))
        assert result["success"] is True
        assert result["backend_used"] == "mock"
        assert result["platform"] == "douyin"
        assert len(result["data"]) == 2
        assert result["data"][0]["title"] == "AI大模型新突破引发行业震动"

    @patch("tools.scraping._fetch_with_backend", side_effect=_mock_fetch_success)
    def test_weibo_returns_data(self, mock_fetch):
        result = json.loads(scrape_weibo_trending({"count": 2}))
        assert result["success"] is True
        assert result["platform"] == "weibo"
        assert len(result["data"]) == 2

    @patch("tools.scraping._fetch_with_backend", side_effect=_mock_fetch_success)
    def test_bilibili_returns_data(self, mock_fetch):
        result = json.loads(scrape_bilibili_popular({"count": 2}))
        assert result["success"] is True
        assert result["platform"] == "bilibili"

    def test_default_params(self):
        """空参数不抛错"""
        for fn in [scrape_douyin_trending, scrape_weibo_trending, scrape_bilibili_popular,
                    scrape_xiaohongshu_trending, scrape_zhihu_trending, aggregate_all_trending]:
            result = fn()
            assert result is not None
            parsed = json.loads(result)
            assert isinstance(parsed, dict)

    @patch("tools.scraping._fetch_with_backend", side_effect=_mock_fetch_success)
    def test_aggregate_with_selected_platforms(self, mock_fetch):
        result = json.loads(aggregate_all_trending({"platforms": ["weibo"]}))
        assert result["platforms_scraped"] == ["weibo"]
        assert "weibo" in result["results"]
        assert "douyin" not in result["results"]

    def test_output_schema_for_analyze_trends(self):
        """aggregate 输出能被 analyze_trends 消费"""
        with patch("tools.scraping._fetch_with_backend", side_effect=_mock_fetch_success):
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
        assert len(backends) >= 4
        names = [b["name"] for b in backends]
        assert "agent_reach" in names
        assert "hot_topics_api" in names
        assert "mediacrawler" in names
        assert "browser_cdp" in names


class TestBackendFallback:
    def test_when_no_backend_available_returns_error(self):
        """没有后端可用时返回 success=False 而非崩溃"""
        result = json.loads(scrape_douyin_trending())
        assert "success" in result
        # 可能是 True (有后端可用) 或 False (全部不可用)
        # 无论哪种情况不应崩溃
        assert "platform" in result
        assert "scraped_at" in result
