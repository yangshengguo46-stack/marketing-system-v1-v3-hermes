"""RUN-23: Audience persona derivation.

Clusters comment samples into audience inference candidates.  These are not
first-party follower facts and must never overwrite actual audience snapshots.

This is a lightweight clustering implementation that doesn't require
external ML libraries — it uses keyword frequency analysis and
rule-based grouping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AudiencePersona:
    """A derived audience persona cluster."""

    label: str
    size: int  # number of comments in this cluster
    age_range: str | None = None
    interests: list[str] = field(default_factory=list)
    language: str = "zh"
    sentiment: str = "neutral"  # positive, neutral, negative
    keywords: list[tuple[str, int]] = field(default_factory=list)


# Age-related keywords for Chinese comments
AGE_KEYWORDS = {
    "00后": ["00后", "05后", "大学生", "学生党", "考研", "高考"],
    "90后": ["90后", "95后", "打工人", "社畜", "加班", "996"],
    "80后": ["80后", "85后", "房贷", "二胎", "中年", "上有老下有小"],
    "70后": ["70后", "退休", "更年期"],
}

# Interest-related keywords
INTEREST_KEYWORDS = {
    "科技": ["AI", "人工智能", "芯片", "编程", "代码", "科技", "互联网", "大模型", "GPT"],
    "创业": ["创业", "副业", "赚钱", "搞钱", "商业模式", "融资", "上市"],
    "职场": ["职场", "跳槽", "升职", "老板", "领导", "同事", "HR", "面试"],
    "情感": ["恋爱", "分手", "结婚", "离婚", "单身", "相亲", "渣男", "渣女"],
    "健康": ["健身", "减肥", "养生", "体检", "失眠", "焦虑", "抑郁"],
    "教育": ["教育", "鸡娃", "学区房", "辅导班", "孩子", "家长"],
    "消费": ["消费", "买", "购物", "性价比", "踩雷", "种草", "拔草"],
}

# Sentiment keywords
POSITIVE_KEYWORDS = {"赞", "支持", "说的好", "太对了", "牛", "厉害", "学到了", "感谢", "谢谢", "喜欢", "收藏"}
NEGATIVE_KEYWORDS = {"反对", "不同意", "胡说", "扯淡", "假的", "营销号", "带节奏", "不喜欢", "差评", "踩"}


def _detect_age_range(text: str) -> str | None:
    """Detect age range from a comment text."""
    for age, keywords in AGE_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return age
    return None


def _detect_interests(text: str) -> list[str]:
    """Detect interest categories from a comment text."""
    interests = []
    for category, keywords in INTEREST_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                interests.append(category)
                break
    return interests


def _detect_sentiment(text: str) -> str:
    """Detect sentiment from a comment text."""
    pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in text)
    neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def _detect_language(text: str) -> str:
    """Detect language (simplified: zh vs en)."""
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    if chinese_chars > len(text) * 0.3:
        return "zh"
    return "en"


def _extract_keywords(comments: list[str], top_n: int = 5) -> list[tuple[str, int]]:
    """Extract top keywords from a list of comments.

    Uses simple 2-gram frequency for Chinese text.
    """
    freq: dict[str, int] = {}
    for comment in comments:
        # Simple 2-gram extraction for Chinese
        for i in range(len(comment) - 1):
            gram = comment[i:i+2]
            if '\u4e00' <= gram[0] <= '\u9fff' and '\u4e00' <= gram[1] <= '\u9fff':
                freq[gram] = freq.get(gram, 0) + 1
    sorted_kw = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return sorted_kw[:top_n]


def derive_personas(
    comments: list[dict[str, Any]],
    *,
    min_cluster_size: int = 3,
) -> list[AudiencePersona]:
    """Derive audience personas from comment data.

    Args:
        comments: List of comment dicts with 'text' and optionally 'author', 'likes'
        min_cluster_size: Minimum comments to form a persona cluster

    Returns:
        List of AudiencePersona clusters sorted by size descending.
    """
    if not comments:
        return []

    # Classify each comment
    classified: list[dict[str, Any]] = []
    for comment in comments:
        text = comment.get("text", "")
        if not text:
            continue
        classified.append({
            "text": text,
            "age_range": _detect_age_range(text),
            "interests": _detect_interests(text),
            "sentiment": _detect_sentiment(text),
            "language": _detect_language(text),
            "likes": comment.get("likes", 0),
        })

    if not classified:
        return []

    # Group by (age_range, primary_interest) combination
    clusters: dict[tuple[str | None, str], list[dict[str, Any]]] = {}
    for item in classified:
        age = item["age_range"]
        primary_interest = item["interests"][0] if item["interests"] else "other"
        key = (age, primary_interest)
        clusters.setdefault(key, []).append(item)

    # Build personas
    personas: list[AudiencePersona] = []
    for (age, interest), members in clusters.items():
        if len(members) < min_cluster_size:
            continue

        # Aggregate interests
        all_interests: dict[str, int] = {}
        sentiments: dict[str, int] = {}
        languages: dict[str, int] = {}
        for m in members:
            for i in m["interests"]:
                all_interests[i] = all_interests.get(i, 0) + 1
            sentiments[m["sentiment"]] = sentiments.get(m["sentiment"], 0) + 1
            languages[m["language"]] = languages.get(m["language"], 0) + 1

        sorted_interests = sorted(all_interests.items(), key=lambda x: x[1], reverse=True)
        dominant_sentiment = max(sentiments, key=sentiments.get)
        dominant_language = max(languages, key=languages.get)

        keywords = _extract_keywords([m["text"] for m in members])

        label_parts = []
        if age:
            label_parts.append(age)
        label_parts.append(interest)
        label = "-".join(label_parts)

        personas.append(AudiencePersona(
            label=label,
            size=len(members),
            age_range=age,
            interests=[i for i, _ in sorted_interests],
            sentiment=dominant_sentiment,
            language=dominant_language,
            keywords=keywords,
        ))

    # Sort by size descending
    personas.sort(key=lambda p: p.size, reverse=True)
    return personas


def persona_to_dict(persona: AudiencePersona) -> dict[str, Any]:
    """Serialize persona to dict for storage."""
    return {
        "label": persona.label,
        "size": persona.size,
        "age_range": persona.age_range,
        "interests": persona.interests,
        "language": persona.language,
        "sentiment": persona.sentiment,
        "keywords": persona.keywords,
        "evidence_basis": "comment_sample_keyword_inference",
        "is_first_party_audience_fact": False,
    }


def personas_to_inference_candidate(personas: list[AudiencePersona]) -> dict[str, Any]:
    """Build a governed candidate without retaining raw comment text."""
    return {
        "kind": "audience_inference_candidate",
        "status": "pending",
        "source_kind": "comment_sample_inference",
        "audience_inferences": [persona_to_dict(p) for p in personas],
        "total_clusters": len(personas),
        "total_comments": sum(p.size for p in personas),
        "dominant_age_ranges": list({p.age_range for p in personas if p.age_range}),
        "dominant_interests": list({i for p in personas for i in p.interests}),
        "dominant_languages": list({p.language for p in personas}),
        "limitations": [
            "仅代表参与评论的样本，不能外推为全部粉丝",
            "年龄和兴趣来自关键词规则推断，不是平台官方画像",
            "不得覆盖 actual_audience_snapshot 或已确认目标受众",
        ],
        "can_update_actual_audience_snapshot": False,
        "raw_comments_retained": False,
    }


def personas_to_dna(personas: list[AudiencePersona]) -> dict[str, Any]:
    """Backward-compatible name; returns an inference candidate, not account DNA."""
    return personas_to_inference_candidate(personas)
