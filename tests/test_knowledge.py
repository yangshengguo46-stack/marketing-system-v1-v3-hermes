"""MEM-09: Platform knowledge entries."""

import pytest
from marketing_tools.knowledge import create_knowledge_entry, knowledge_is_expired, supersedes_knowledge


def test_create_entry():
    e = create_knowledge_entry("douyin视频最长60秒", source="official_docs", region="cn", version="2.0")
    assert e["source"] == "official_docs"
    assert e["region"] == "cn"
    assert e["version"] == "2.0"
    assert "content" in e


def test_expired():
    e = create_knowledge_entry("rule", source="x", valid_to="2020-01-01T00:00:00")
    assert knowledge_is_expired(e, now="2026-07-02T00:00:00") is True


def test_not_expired_no_valid_to():
    e = create_knowledge_entry("rule", source="x")
    assert knowledge_is_expired(e) is False


def test_newer_supersedes():
    older = create_knowledge_entry("rule v1", source="douyin_docs", version="1.0")
    newer = create_knowledge_entry("rule v2", source="douyin_docs", version="2.0")
    assert supersedes_knowledge(newer, older) is True


def test_different_source_no_supersede():
    a = create_knowledge_entry("r1", source="src_a")
    b = create_knowledge_entry("r2", source="src_b")
    assert supersedes_knowledge(b, a) is False
