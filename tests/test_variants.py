"""PUB-03: Platform variants."""

import pytest
from marketing_tools.variants import create_variants, is_variant_of


def test_create_two_variants():
    parent = {"id": "asset_1", "title": "AI选题", "platform": "douyin"}
    variants = create_variants(parent, ["bilibili", "weibo"])
    assert len(variants) == 2
    assert variants[0]["platform"] in ("bilibili", "weibo")
    assert variants[0]["_variant_of"] == "asset_1"


def test_skips_invalid_platform():
    variants = create_variants({"id": "a1", "title": "t"}, ["douyin", "invalid_plat", "weibo"])
    assert len(variants) == 2


def test_dedup_duplicate_platforms():
    variants = create_variants({"id": "a1", "title": "t"}, ["bilibili", "bilibili"])
    assert len(variants) == 1


def test_is_variant():
    child = {"_variant_of": "asset_1", "platform": "bilibili"}
    assert is_variant_of(child, "asset_1") is True


def test_is_not_variant():
    child = {"parent_id": "asset_2", "platform": "bilibili"}
    assert is_variant_of(child, "asset_1") is False
