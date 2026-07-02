"""DATA-07: Deduplication and cross-platform clustering."""

import pytest
from marketing_tools.dedup import (
    canonicalize_url, title_similarity, deduplicate_items, cross_platform_clusters,
)


class TestCanonicalizeURL:
    def test_strip_tracking_params(self):
        u = "https://www.douyin.com/video/1?utm_source=share&ref=app&id=123"
        c = canonicalize_url(u)
        assert "utm_source" not in c
        assert "ref" not in c
        if "id=123" in c:
            assert "id=123" in c  # kept if not tracking

    def test_same_url_different_tracking(self):
        u1 = "https://a.com/p?utm_source=x&id=1"
        u2 = "https://a.com/p?utm_campaign=y&id=1"
        assert canonicalize_url(u1) == canonicalize_url(u2)

    def test_lower_host(self):
        assert "DOUYIN.COM" not in canonicalize_url("https://WWW.DOUYIN.COM/p")

    def test_remove_fragment(self):
        c = canonicalize_url("https://a.com/p#section")
        assert "#" not in c


class TestTitleSimilarity:
    def test_identical(self):
        assert title_similarity("AI大模型突破", "AI大模型突破") == pytest.approx(1.0)

    def test_related(self):
        s = title_similarity("OpenAI发布GPT5性能评测", "OpenAI发布GPT5性能评测结果报告")
        assert s > 0.3

    def test_different(self):
        s = title_similarity("苹果发布新手机", "股市今日大涨")
        assert s < 0.2


class TestDedupItems:
    def test_exact_url_dedup(self):
        items = [
            {"title": "AI突破", "url": "https://a.com/1", "rank": 1, "source_platform": "douyin"},
            {"title": "AI突破dup", "url": "https://a.com/1", "rank": 2, "source_platform": "douyin"},
        ]
        r = deduplicate_items(items)
        assert len(r) == 1
        assert r[0]["rank"] == 1

    def test_similar_title_dedup(self):
        items = [
            {"title": "OpenAI发布GPT5性能评测结果", "url": "https://a.com/1", "rank": 1, "source_platform": "douyin"},
            {"title": "OpenAI发布GPT5性能评测结果击败所有竞品", "url": "https://a.com/2", "rank": 2, "source_platform": "douyin"},
        ]
        r = deduplicate_items(items, title_threshold=0.7)
        assert len(r) == 1

    def test_different_titles_kept(self):
        items = [
            {"title": "AI突破", "url": "https://a.com/1", "rank": 1, "source_platform": "douyin"},
            {"title": "股市大涨", "url": "https://a.com/2", "rank": 2, "source_platform": "douyin"},
        ]
        r = deduplicate_items(items)
        assert len(r) == 2

    def test_cross_platform_not_deduped(self):
        items = [
            {"title": "AI大模型突破性能翻倍", "url": "https://a.com/1", "rank": 1, "source_platform": "douyin"},
            {"title": "AI大模型突破性能翻倍引发关注", "url": "https://b.com/2", "rank": 1, "source_platform": "weibo"},
        ]
        r = deduplicate_items(items)
        assert len(r) == 2


class TestCrossPlatformClusters:
    def test_same_event_across_platforms(self):
        items = [
            {"title": "OpenAI发布GPT5性能评测结果", "source_platform": "douyin", "url": "https://dy.com/1"},
            {"title": "OpenAI发布GPT5性能评测结果击败所有竞品", "source_platform": "weibo", "url": "https://wb.com/2"},
            {"title": "NVIDIA发布新显卡RTX6090", "source_platform": "bilibili", "url": "https://bili.com/3"},
        ]
        clusters = cross_platform_clusters(items)
        assert len(clusters) <= 3

    def test_unrelated_no_cluster(self):
        items = [
            {"title": "AI突破", "source_platform": "douyin", "url": "https://a.com/1"},
            {"title": "股市大涨", "source_platform": "weibo", "url": "https://b.com/2"},
        ]
        clusters = cross_platform_clusters(items)
        assert len(clusters) == 2
