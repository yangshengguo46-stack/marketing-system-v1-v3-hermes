"""PUB-01: ContentAsset model with version chain, topic, hook."""

import pytest
from agent_core import AgentCoreStore


def test_create_with_topic_hook(tmp_path):
    store = AgentCoreStore(tmp_path / "ca.db")
    a = store.create_content_asset(
        title="AI教育选题", type="script", platform="douyin",
        topic="AI教育", hook="10倍效率提升",
    )
    assert a["title"] == "AI教育选题"
    assert a["topic"] == "AI教育"
    assert a["hook"] == "10倍效率提升"
    assert a["version"] == 1


def test_version_chain(tmp_path):
    store = AgentCoreStore(tmp_path / "ca.db")
    v1 = store.create_content_asset(title="v1", platform="douyin")
    assert v1["version"] == 1
    v2 = store.create_content_asset(title="v2", platform="douyin", parent_id=v1["id"])
    assert v2["version"] == 2
    assert v2["parent_id"] == v1["id"]


def test_parent_not_found_does_not_block(tmp_path):
    store = AgentCoreStore(tmp_path / "ca.db")
    a = store.create_content_asset(title="orphan", parent_id="asset_nonexistent")
    assert a["version"] == 1


def test_migration_adds_columns(tmp_path):
    """New columns should be present after migration on reopened store."""
    path = tmp_path / "ca.db"
    s1 = AgentCoreStore(path)
    s1.create_content_asset(title="test")
    s2 = AgentCoreStore(path)
    a = s2.create_content_asset(title="test2", topic="AI", hook="h")
    assert a["topic"] == "AI"
