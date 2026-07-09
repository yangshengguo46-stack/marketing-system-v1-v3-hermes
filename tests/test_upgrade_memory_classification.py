"""Tests for UPGRADE-03: Three-layer knowledge classification.

Tests source/entity/topic classification, conflict detection,
and integration with memory_candidates storage.
"""

import pytest
from engine.agent_core.memory_classification import (
    KnowledgeClassification,
    classify_memory,
    find_conflicting_classifications,
    SOURCE_AGENT, SOURCE_USER, SOURCE_PUBLISHED_RESULT, SOURCE_TOOL,
    ENTITY_ACCOUNT, ENTITY_PLATFORM, ENTITY_INDUSTRY, ENTITY_AUDIENCE,
    ENTITY_USER, ENTITY_CONTENT, ENTITY_WORKFLOW,
    TOPIC_ACCOUNT_POSITIONING, TOPIC_PLATFORM_RULES, TOPIC_INDUSTRY_TRENDS,
    TOPIC_AUDIENCE_DEMOGRAPHICS, TOPIC_CONTENT_HOOK_PATTERNS,
    TOPIC_WORKFLOW_PUBLISHING,
    VALID_SOURCES, VALID_ENTITIES, VALID_TOPICS,
)


class TestClassificationStructure:
    def test_source_types_complete(self):
        assert SOURCE_AGENT in VALID_SOURCES
        assert SOURCE_USER in VALID_SOURCES
        assert SOURCE_PUBLISHED_RESULT in VALID_SOURCES
        assert SOURCE_TOOL in VALID_SOURCES

    def test_entity_types_complete(self):
        for e in [ENTITY_ACCOUNT, ENTITY_PLATFORM, ENTITY_INDUSTRY,
                  ENTITY_AUDIENCE, ENTITY_USER, ENTITY_CONTENT, ENTITY_WORKFLOW]:
            assert e in VALID_ENTITIES

    def test_topic_taxonomy_non_empty(self):
        assert len(VALID_TOPICS) >= 20

    def test_to_dict_roundtrip(self):
        cls = KnowledgeClassification(
            source=SOURCE_AGENT, entity=ENTITY_ACCOUNT,
            topic=TOPIC_ACCOUNT_POSITIONING, entity_id="acct_123",
            tags=["抖音", "短视频"],
        )
        d = cls.to_dict()
        assert d["source"] == SOURCE_AGENT
        assert d["entity"] == ENTITY_ACCOUNT
        assert d["topic"] == TOPIC_ACCOUNT_POSITIONING
        assert d["entity_id"] == "acct_123"
        assert "抖音" in d["tags"]

        restored = KnowledgeClassification.from_dict(d)
        assert restored.source == SOURCE_AGENT
        assert restored.entity == ENTITY_ACCOUNT


class TestClassifyMemory:
    def test_account_kind_classifies_as_account_entity(self):
        cls = classify_memory("account", "账号定位是科技博主", account_id="acct_123")
        assert cls.entity == ENTITY_ACCOUNT
        assert cls.entity_id == "acct_123"
        assert cls.topic == TOPIC_ACCOUNT_POSITIONING

    def test_semantic_platform_rules(self):
        cls = classify_memory("semantic", "抖音平台的算法规则和限流机制", platform="douyin")
        assert cls.entity == ENTITY_PLATFORM
        assert cls.entity_id == "douyin"
        assert cls.topic == TOPIC_PLATFORM_RULES

    def test_semantic_industry_trends(self):
        cls = classify_memory("semantic", "AI行业最新趋势分析")
        assert cls.entity == ENTITY_INDUSTRY
        assert cls.topic == TOPIC_INDUSTRY_TRENDS

    def test_semantic_audience_demographics(self):
        cls = classify_memory("semantic", "受众画像：主要年龄分布在00后和90后")
        assert cls.entity == ENTITY_AUDIENCE
        assert cls.topic == TOPIC_AUDIENCE_DEMOGRAPHICS

    def test_procedural_workflow(self):
        cls = classify_memory("procedural", "发布排期和审核流程")
        assert cls.entity == ENTITY_WORKFLOW
        assert cls.topic == TOPIC_WORKFLOW_PUBLISHING

    def test_episodic_content(self):
        cls = classify_memory("episodic", "这期视频的钩子开头效果很好")
        assert cls.entity == ENTITY_CONTENT
        assert cls.topic == TOPIC_CONTENT_HOOK_PATTERNS

    def test_user_kind(self):
        cls = classify_memory("user", "用户偏好科技内容")
        assert cls.entity == ENTITY_USER

    def test_source_from_evidence_user_stated(self):
        evidence = [{"source": "user", "provenance": "user_stated"}]
        cls = classify_memory("user", "用户说喜欢短视频", evidence=evidence)
        assert cls.source == SOURCE_USER

    def test_source_from_evidence_published_result(self):
        evidence = [{"source": "published_result", "receipt": {"post_id": "123"}}]
        cls = classify_memory("account", "发布后数据表现", evidence=evidence)
        assert cls.source == SOURCE_PUBLISHED_RESULT

    def test_source_from_evidence_benchmark(self):
        evidence = [{"source": "benchmark_sample"}]
        cls = classify_memory("account", "对标账号分析", evidence=evidence)
        assert cls.source == "benchmark"

    def test_tags_extracted(self):
        cls = classify_memory("semantic", "抖音短视频AI科技行业趋势")
        assert "抖音" in cls.tags or "短视频" in cls.tags
        assert "ai" in cls.tags

    def test_default_source_is_agent(self):
        cls = classify_memory("user", "用户偏好")
        assert cls.source == SOURCE_AGENT


class TestConflictDetection:
    def test_no_conflict_different_topics(self):
        memories = [
            {"id": "m1", "classification": {"entity": "account", "topic": "account_positioning"}},
            {"id": "m2", "classification": {"entity": "account", "topic": "account_style"}},
        ]
        conflicts = find_conflicting_classifications(memories)
        assert conflicts == []

    def test_conflict_same_entity_topic(self):
        memories = [
            {"id": "m1", "classification": {"entity": "platform", "topic": "platform_rules"}},
            {"id": "m2", "classification": {"entity": "platform", "topic": "platform_rules"}},
        ]
        conflicts = find_conflicting_classifications(memories)
        assert len(conflicts) == 1
        assert conflicts[0][0] == "platform"
        assert conflicts[0][1] == "platform_rules"

    def test_no_classification_skipped(self):
        memories = [
            {"id": "m1", "classification": {}},
            {"id": "m2", "classification": {}},
        ]
        conflicts = find_conflicting_classifications(memories)
        assert conflicts == []

    def test_multiple_conflicts(self):
        memories = [
            {"id": "m1", "classification": {"entity": "account", "topic": "account_positioning"}},
            {"id": "m2", "classification": {"entity": "account", "topic": "account_positioning"}},
            {"id": "m3", "classification": {"entity": "platform", "topic": "platform_algorithm"}},
            {"id": "m4", "classification": {"entity": "platform", "topic": "platform_algorithm"}},
        ]
        conflicts = find_conflicting_classifications(memories)
        assert len(conflicts) == 2
