"""DATA-13: Data quality scoring."""

import pytest
from marketing_tools.quality import score_quality, QUALITY_THRESHOLD


def test_high_quality():
    item = {
        "title": "AI突破", "url": "https://a.com/1",
        "source_platform": "douyin", "source_backend": "playwright_mcp_creator_center",
        "collected_at": "2026-07-02T10:00:00", "rank": 1,
        "author": "creator1", "published_at": "2026-07-02T09:00:00",
        "metrics": {"views": 10000, "likes": 500},
    }
    r = score_quality(item, now="2026-07-02T11:00:00")
    assert r["score"] > 0.7
    assert r["quality_tier"] == "high"


def test_low_quality_stale():
    item = {
        "title": "AI突破", "url": "https://a.com/1",
        "source_platform": "douyin", "source_backend": "unknown",
        "collected_at": "2026-06-01T10:00:00", "rank": 500,
    }
    r = score_quality(item, now="2026-07-02T11:00:00")
    assert r["score"] < QUALITY_THRESHOLD


def test_short_title_penalized():
    item = {
        "title": "ab", "url": "https://a.com/1",
        "source_platform": "douyin", "source_backend": "hot_topics_api",
        "collected_at": "2026-07-02T10:00:00",
    }
    r = score_quality(item, now="2026-07-02T10:30:00")
    assert r["anomaly_penalty"] < 0


def test_breakdown_keys():
    r = score_quality({
        "title": "test", "url": "https://a.com", "source_platform": "douyin",
        "source_backend": "bilibili_public", "collected_at": "2026-07-02T10:00:00",
    }, now="2026-07-02T10:30:00")
    for k in ("score", "completeness", "freshness", "source_credibility", "anomaly_penalty", "quality_tier"):
        assert k in r


def test_score_bounded_0_1():
    for item in [
        {"title": "a" * 10, "url": "https://a.com", "source_platform": "douyin",
         "source_backend": "unknown", "collected_at": "2020-01-01T00:00:00"},
        {"title": "b" * 10, "url": "https://b.com", "source_platform": "douyin",
         "source_backend": "playwright_mcp_creator_center", "collected_at": "2026-07-02T10:00:00",
         "rank": 1, "author": "x", "metrics": {"views": 100}},
    ]:
        r = score_quality(item, now="2026-07-02T10:00:00")
        assert 0.0 <= r["score"] <= 1.0
