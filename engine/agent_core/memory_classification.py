"""UPGRADE-03 (Q15): Three-layer knowledge classification for memory candidates.

Inspired by Cheat on Content's knowledge base structure:
  - source: where the knowledge came from (tool/agent/user/published_result)
  - entity: what the knowledge is about (account/platform/industry/audience)
  - topic: specific subject within the entity (e.g. "optimal_posting_time",
           "title_patterns", "audience_age_distribution")

This module provides deterministic classification helpers that produce
structured classification dicts to be stored in memory_candidates.classification_json.

Classification is used for:
  1. Retrieval: filter memories by source/entity/topic
  2. Conflict detection: same entity+topic from different sources → potential conflict
  3. Knowledge graph: build entity→topic→source relationships
  4. Strategy derivation: group related memories for pattern detection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Source types: where the knowledge originated ──────────────────────

SOURCE_TOOL = "tool"
SOURCE_AGENT = "agent"
SOURCE_USER = "user"
SOURCE_PUBLISHED_RESULT = "published_result"
SOURCE_FAILURE_RECOVERY = "failure_recovery"
SOURCE_BENCHMARK = "benchmark"

VALID_SOURCES = frozenset({
    SOURCE_TOOL, SOURCE_AGENT, SOURCE_USER,
    SOURCE_PUBLISHED_RESULT, SOURCE_FAILURE_RECOVERY, SOURCE_BENCHMARK,
})


# ── Entity types: what the knowledge is about ─────────────────────────

ENTITY_ACCOUNT = "account"
ENTITY_PLATFORM = "platform"
ENTITY_INDUSTRY = "industry"
ENTITY_AUDIENCE = "audience"
ENTITY_USER = "user"
ENTITY_CONTENT = "content"
ENTITY_WORKFLOW = "workflow"

VALID_ENTITIES = frozenset({
    ENTITY_ACCOUNT, ENTITY_PLATFORM, ENTITY_INDUSTRY,
    ENTITY_AUDIENCE, ENTITY_USER, ENTITY_CONTENT, ENTITY_WORKFLOW,
})


# ── Topic taxonomy: specific subjects within entities ─────────────────

# Account-level topics
TOPIC_ACCOUNT_DNA = "account_dna"
TOPIC_ACCOUNT_POSITIONING = "account_positioning"
TOPIC_ACCOUNT_PERSONA = "account_persona"
TOPIC_ACCOUNT_CONTENT_PILLARS = "content_pillars"
TOPIC_ACCOUNT_STYLE = "content_style"
TOPIC_ACCOUNT_STAGE = "growth_stage"
TOPIC_ACCOUNT_TABOO = "content_taboo"

# Platform-level topics
TOPIC_PLATFORM_RULES = "platform_rules"
TOPIC_PLATFORM_ALGORITHM = "platform_algorithm"
TOPIC_PLATFORM_FORMAT = "platform_format"
TOPIC_PLATFORM_POSTING_TIME = "optimal_posting_time"
TOPIC_PLATFORM_TAGGING = "platform_tagging"

# Industry-level topics
TOPIC_INDUSTRY_TRENDS = "industry_trends"
TOPIC_INDUSTRY_HOTSPOTS = "industry_hotspots"
TOPIC_INDUSTRY_COMPETITORS = "industry_competitors"

# Audience-level topics
TOPIC_AUDIENCE_DEMOGRAPHICS = "audience_demographics"
TOPIC_AUDIENCE_INTERESTS = "audience_interests"
TOPIC_AUDIENCE_LANGUAGE = "audience_language"
TOPIC_AUDIENCE_SENTIMENT = "audience_sentiment"

# Content-level topics
TOPIC_CONTENT_HOOK_PATTERNS = "hook_patterns"
TOPIC_CONTENT_TITLE_PATTERNS = "title_patterns"
TOPIC_CONTENT_CTA_PATTERNS = "cta_patterns"
TOPIC_CONTENT_PACING = "content_pacing"
TOPIC_CONTENT_EMOTION = "content_emotion"
TOPIC_CONTENT_VIEWPOINT = "content_viewpoint"

# Workflow-level topics
TOPIC_WORKFLOW_PUBLISHING = "publishing_workflow"
TOPIC_WORKFLOW_RECOVERY = "failure_recovery"
TOPIC_WORKFLOW_APPROVAL = "approval_patterns"

VALID_TOPICS = frozenset({
    TOPIC_ACCOUNT_DNA, TOPIC_ACCOUNT_POSITIONING, TOPIC_ACCOUNT_PERSONA,
    TOPIC_ACCOUNT_CONTENT_PILLARS, TOPIC_ACCOUNT_STYLE, TOPIC_ACCOUNT_STAGE,
    TOPIC_ACCOUNT_TABOO,
    TOPIC_PLATFORM_RULES, TOPIC_PLATFORM_ALGORITHM, TOPIC_PLATFORM_FORMAT,
    TOPIC_PLATFORM_POSTING_TIME, TOPIC_PLATFORM_TAGGING,
    TOPIC_INDUSTRY_TRENDS, TOPIC_INDUSTRY_HOTSPOTS, TOPIC_INDUSTRY_COMPETITORS,
    TOPIC_AUDIENCE_DEMOGRAPHICS, TOPIC_AUDIENCE_INTERESTS,
    TOPIC_AUDIENCE_LANGUAGE, TOPIC_AUDIENCE_SENTIMENT,
    TOPIC_CONTENT_HOOK_PATTERNS, TOPIC_CONTENT_TITLE_PATTERNS,
    TOPIC_CONTENT_CTA_PATTERNS, TOPIC_CONTENT_PACING,
    TOPIC_CONTENT_EMOTION, TOPIC_CONTENT_VIEWPOINT,
    TOPIC_WORKFLOW_PUBLISHING, TOPIC_WORKFLOW_RECOVERY, TOPIC_WORKFLOW_APPROVAL,
})


@dataclass
class KnowledgeClassification:
    """Three-layer classification for a memory candidate."""

    source: str  # one of VALID_SOURCES
    entity: str  # one of VALID_ENTITIES
    topic: str  # one of VALID_TOPICS
    entity_id: str = ""  # e.g. account_id, platform name, industry name
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "entity": self.entity,
            "topic": self.topic,
            "entity_id": self.entity_id,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KnowledgeClassification:
        return cls(
            source=data.get("source", SOURCE_AGENT),
            entity=data.get("entity", ENTITY_USER),
            topic=data.get("topic", ""),
            entity_id=data.get("entity_id", ""),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )


def classify_memory(
    kind: str,
    content: str,
    *,
    source: str = SOURCE_AGENT,
    account_id: str | None = None,
    platform: str | None = None,
    evidence: list[dict[str, Any]] | None = None,
) -> KnowledgeClassification:
    """Auto-classify a memory candidate based on its kind, content, and context.

    Uses keyword matching on content to determine entity and topic.
    The source is determined from evidence provenance.
    """
    # Determine source from evidence
    if evidence:
        sources = {e.get("source", "") for e in evidence if isinstance(e, dict)}
        if "published_result" in sources or any("receipt" in str(e) for e in evidence):
            source = SOURCE_PUBLISHED_RESULT
        elif "user" in sources or any(e.get("provenance") == "user_stated" for e in evidence if isinstance(e, dict)):
            source = SOURCE_USER
        elif any("failure" in str(e.get("provenance", "")) for e in evidence if isinstance(e, dict)):
            source = SOURCE_FAILURE_RECOVERY
        elif any("benchmark" in str(e.get("source", "")) for e in evidence if isinstance(e, dict)):
            source = SOURCE_BENCHMARK

    # Determine entity and topic from kind + content
    content_lower = content.lower()
    entity = ENTITY_USER
    topic = ""
    entity_id = ""

    if kind == "account":
        entity = ENTITY_ACCOUNT
        entity_id = account_id or ""
        topic = _match_account_topic(content_lower)
    elif kind == "semantic":
        if any(kw in content_lower for kw in ["平台", "算法", "规则", "限流", "审核", "platform", "algorithm"]):
            entity = ENTITY_PLATFORM
            entity_id = platform or ""
            topic = _match_platform_topic(content_lower)
        elif any(kw in content_lower for kw in ["行业", "趋势", "热点", "竞品", "industry", "trend"]):
            entity = ENTITY_INDUSTRY
            topic = _match_industry_topic(content_lower)
        elif any(kw in content_lower for kw in ["受众", "画像", "年龄", "兴趣", "audience", "persona"]):
            entity = ENTITY_AUDIENCE
            topic = _match_audience_topic(content_lower)
        else:
            topic = _match_content_topic(content_lower)
    elif kind == "procedural":
        entity = ENTITY_WORKFLOW
        topic = _match_workflow_topic(content_lower)
    elif kind == "episodic":
        entity = ENTITY_CONTENT
        topic = _match_content_topic(content_lower)
    elif kind == "user":
        entity = ENTITY_USER
        entity_id = account_id or ""
        topic = _match_account_topic(content_lower) or TOPIC_ACCOUNT_POSITIONING

    # Extract simple tags from content
    tags = _extract_tags(content_lower)

    return KnowledgeClassification(
        source=source,
        entity=entity,
        topic=topic,
        entity_id=entity_id,
        tags=tags,
    )


def _match_account_topic(content: str) -> str:
    if any(kw in content for kw in ["定位", "positioning"]):
        return TOPIC_ACCOUNT_POSITIONING
    if any(kw in content for kw in ["人设", "persona", "人设"]):
        return TOPIC_ACCOUNT_PERSONA
    if any(kw in content for kw in ["内容支柱", "内容方向", "content pillar"]):
        return TOPIC_ACCOUNT_CONTENT_PILLARS
    if any(kw in content for kw in ["风格", "style", "调性"]):
        return TOPIC_ACCOUNT_STYLE
    if any(kw in content for kw in ["阶段", "stage", "成长"]):
        return TOPIC_ACCOUNT_STAGE
    if any(kw in content for kw in ["禁区", " taboo", "不做"]):
        return TOPIC_ACCOUNT_TABOO
    if any(kw in content for kw in ["dna", "dna"]):
        return TOPIC_ACCOUNT_DNA
    return TOPIC_ACCOUNT_POSITIONING


def _match_platform_topic(content: str) -> str:
    if any(kw in content for kw in ["规则", "rule", "条款"]):
        return TOPIC_PLATFORM_RULES
    if any(kw in content for kw in ["算法", "algorithm", "推荐"]):
        return TOPIC_PLATFORM_ALGORITHM
    if any(kw in content for kw in ["格式", "format", "分辨率", "时长"]):
        return TOPIC_PLATFORM_FORMAT
    if any(kw in content for kw in ["发布时间", "posting time", "最佳时间"]):
        return TOPIC_PLATFORM_POSTING_TIME
    if any(kw in content for kw in ["标签", "tag", "话题标签"]):
        return TOPIC_PLATFORM_TAGGING
    return TOPIC_PLATFORM_RULES


def _match_industry_topic(content: str) -> str:
    if any(kw in content for kw in ["趋势", "trend"]):
        return TOPIC_INDUSTRY_TRENDS
    if any(kw in content for kw in ["热点", "hotspot", "热搜"]):
        return TOPIC_INDUSTRY_HOTSPOTS
    if any(kw in content for kw in ["竞品", "competitor", "对标"]):
        return TOPIC_INDUSTRY_COMPETITORS
    return TOPIC_INDUSTRY_TRENDS


def _match_audience_topic(content: str) -> str:
    if any(kw in content for kw in ["年龄", "age", "00后", "90后", "80后"]):
        return TOPIC_AUDIENCE_DEMOGRAPHICS
    if any(kw in content for kw in ["兴趣", "interest", "偏好"]):
        return TOPIC_AUDIENCE_INTERESTS
    if any(kw in content for kw in ["语言", "language", "中文", "英文"]):
        return TOPIC_AUDIENCE_LANGUAGE
    if any(kw in content for kw in ["情绪", "sentiment", "情感"]):
        return TOPIC_AUDIENCE_SENTIMENT
    return TOPIC_AUDIENCE_DEMOGRAPHICS


def _match_content_topic(content: str) -> str:
    if any(kw in content for kw in ["钩子", "hook", "开头", "前3秒"]):
        return TOPIC_CONTENT_HOOK_PATTERNS
    if any(kw in content for kw in ["标题", "title", "封面"]):
        return TOPIC_CONTENT_TITLE_PATTERNS
    if any(kw in content for kw in ["引导", "cta", "互动", "点赞", "评论"]):
        return TOPIC_CONTENT_CTA_PATTERNS
    if any(kw in content for kw in ["节奏", "pacing", "快慢"]):
        return TOPIC_CONTENT_PACING
    if any(kw in content for kw in ["情绪", "emotion", "共鸣"]):
        return TOPIC_CONTENT_EMOTION
    if any(kw in content for kw in ["观点", "viewpoint", "立场"]):
        return TOPIC_CONTENT_VIEWPOINT
    return TOPIC_CONTENT_HOOK_PATTERNS


def _match_workflow_topic(content: str) -> str:
    if any(kw in content for kw in ["发布", "publish", "排期"]):
        return TOPIC_WORKFLOW_PUBLISHING
    if any(kw in content for kw in ["恢复", "recovery", "失败", "重试"]):
        return TOPIC_WORKFLOW_RECOVERY
    if any(kw in content for kw in ["审批", "approval", "授权"]):
        return TOPIC_WORKFLOW_APPROVAL
    return TOPIC_WORKFLOW_PUBLISHING


_TAG_KEYWORDS = [
    "短视频", "直播", "图文", "横屏", "竖屏",
    "抖音", "b站", "bilibili", "小红书", "知乎",
    "ai", "科技", "创业", "职场", "情感", "健康", "教育", "消费",
    "爆款", "涨粉", "转化", "留存",
]


def _extract_tags(content: str) -> list[str]:
    return [kw for kw in _TAG_KEYWORDS if kw in content]


def find_conflicting_classifications(
    memories: list[dict[str, Any]],
) -> list[tuple[str, str, str]]:
    """Find memories with same entity+topic but different sources (potential conflicts).

    Returns list of (entity, topic, [memory_ids]) tuples.
    """
    by_key: dict[tuple[str, str], list[str]] = {}
    for mem in memories:
        cls = mem.get("classification") or {}
        entity = cls.get("entity", "")
        topic = cls.get("topic", "")
        if not entity or not topic:
            continue
        key = (entity, topic)
        by_key.setdefault(key, []).append(mem["id"])

    conflicts = []
    for (entity, topic), ids in by_key.items():
        if len(ids) > 1:
            conflicts.append((entity, topic, ",".join(ids)))
    return conflicts
