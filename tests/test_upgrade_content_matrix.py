"""Tests for UPGRADE-04: Content matrix decomposition (1→N platform adaptation).

Tests platform specs, title/tag/CTA adaptation, and decompose_content.
"""

import pytest
from engine.agent_core.content_matrix import (
    PlatformSpec, PLATFORM_SPECS, CTA_TEMPLATES,
    adapt_title, adapt_tags, adapt_cta, decompose_content, get_platform_spec,
)


class TestPlatformSpecs:
    def test_all_platforms_present(self):
        for p in ["douyin", "bilibili", "xiaohongshu", "kuaishou", "zhihu", "wechat_official"]:
            assert p in PLATFORM_SPECS
        assert "weibo" not in PLATFORM_SPECS

    def test_douyin_spec(self):
        spec = PLATFORM_SPECS["douyin"]
        assert spec.title_max == 55
        assert spec.tag_range == (3, 5)
        assert spec.video_orientation == "vertical"

    def test_xiaohongshu_short_title(self):
        assert PLATFORM_SPECS["xiaohongshu"].title_max == 20

    def test_zhihu_no_hashtag_prefix(self):
        assert PLATFORM_SPECS["zhihu"].tag_prefix == ""

    def test_wechat_official_soft_article_spec(self):
        spec = PLATFORM_SPECS["wechat_official"]
        assert spec.title_max == 64
        assert spec.tag_prefix == ""
        assert spec.content_format == "long_article"
        assert spec.cta_style == "trust_conversion"

    def test_get_platform_spec(self):
        spec = get_platform_spec("douyin")
        assert spec is not None
        assert spec.name == "douyin"

    def test_get_unknown_platform(self):
        assert get_platform_spec("unknown") is None


class TestAdaptTitle:
    def test_short_title_unchanged(self):
        assert adapt_title("AI改变世界", "douyin") == "AI改变世界"

    def test_long_title_truncated_douyin(self):
        long_title = "这是一个非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常非常长的标题超过五十五个字符"
        result = adapt_title(long_title, "douyin")
        assert len(result) <= 55
        assert result.endswith("…")

    def test_xiaohongshu_very_short(self):
        title = "这是一个关于AI如何改变短视频行业的深度分析报告"
        result = adapt_title(title, "xiaohongshu")
        assert len(result) <= 20

    def test_bilibili_longer_allowed(self):
        title = "这是一个关于AI如何改变短视频行业的深度分析报告，从技术到商业模式"
        result_bili = adapt_title(title, "bilibili")
        result_douyin = adapt_title(title, "douyin")
        assert len(result_bili) >= len(result_douyin)


class TestAdaptTags:
    def test_too_many_tags_truncated(self):
        tags = ["a", "b", "c", "d", "e", "f", "g", "h"]
        result = adapt_tags(tags, "douyin")
        assert len(result) <= 5

    def test_too_few_tags_padded(self):
        tags = ["科技"]
        result = adapt_tags(tags, "douyin")
        assert len(result) >= 3

    def test_bilibili_no_prefix(self):
        tags = ["科技", "AI"]
        result = adapt_tags(tags, "bilibili")
        # bilibili uses no prefix
        assert all(not t.startswith("#") for t in result)

    def test_douyin_hashtag_prefix(self):
        tags = ["科技", "AI"]
        result = adapt_tags(tags, "douyin")
        assert all(t.startswith("#") for t in result)

    def test_zhihu_min_zero_tags(self):
        tags = []
        result = adapt_tags(tags, "zhihu")
        # zhihu min is 0, no padding needed
        assert len(result) == 0

    def test_wechat_official_min_zero_tags(self):
        assert adapt_tags([], "wechat_official") == []


class TestAdaptCTA:
    def test_empty_cta_gets_template(self):
        cta = adapt_cta("douyin", "")
        assert len(cta) > 5

    def test_existing_cta_preserved(self):
        cta = adapt_cta("douyin", "关注我了解更多")
        assert cta == "关注我了解更多"

    def test_emotional_style_for_douyin(self):
        cta = adapt_cta("douyin", "")
        assert "评论" in cta or "点赞" in cta or "关注" in cta

    def test_community_style_for_bilibili(self):
        cta = adapt_cta("bilibili", "")
        assert "三连" in cta or "弹幕" in cta or "关注" in cta

    def test_trust_conversion_style_for_wechat_official(self):
        cta = adapt_cta("wechat_official", "")
        assert "收藏" in cta or "方案" in cta or "转给" in cta


class TestDecomposeContent:
    def _parent(self):
        return {
            "id": "asset_001",
            "title": "AI如何改变短视频行业",
            "tags": ["AI", "短视频", "科技", "创业", "职场"],
            "cta": "",
            "content": {"body": "..."},
            "type": "script",
        }

    def test_decompose_to_multiple_platforms(self):
        variants = decompose_content(self._parent(), ["douyin", "bilibili", "kuaishou"])
        assert len(variants) == 3
        platforms = {v["platform"] for v in variants}
        assert platforms == {"douyin", "bilibili", "kuaishou"}

    def test_each_variant_has_parent_id(self):
        variants = decompose_content(self._parent(), ["douyin", "bilibili"])
        for v in variants:
            assert v["parent_id"] == "asset_001"

    def test_each_variant_has_adaptation_notes(self):
        variants = decompose_content(self._parent(), ["douyin", "xiaohongshu"])
        for v in variants:
            assert "adaptation_notes" in v

    def test_each_variant_has_platform_spec(self):
        variants = decompose_content(self._parent(), ["douyin"])
        assert "platform_spec" in variants[0]
        assert variants[0]["platform_spec"]["title_max"] == 55

    def test_invalid_platform_skipped(self):
        variants = decompose_content(self._parent(), ["douyin", "invalid_platform"])
        assert len(variants) == 1
        assert variants[0]["platform"] == "douyin"

    def test_duplicate_platforms_deduped(self):
        variants = decompose_content(self._parent(), ["douyin", "douyin", "bilibili"])
        assert len(variants) == 2

    def test_xiaohongshu_title_adapted(self):
        parent = self._parent()
        variants = decompose_content(parent, ["xiaohongshu"])
        assert len(variants[0]["title"]) <= 20

    def test_content_preserved(self):
        variants = decompose_content(self._parent(), ["douyin"])
        assert variants[0]["content"] == {"body": "..."}

    def test_all_target_platforms(self):
        variants = decompose_content(
            self._parent(),
            ["douyin", "bilibili", "xiaohongshu", "kuaishou", "zhihu", "wechat_official"],
        )
        assert len(variants) == 6

    def test_decompose_to_wechat_official(self):
        variants = decompose_content(self._parent(), ["wechat_official"])
        assert len(variants) == 1
        assert variants[0]["platform"] == "wechat_official"
        assert variants[0]["platform_spec"]["content_format"] == "long_article"
