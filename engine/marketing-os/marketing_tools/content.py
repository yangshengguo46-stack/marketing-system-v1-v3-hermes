"""Marketing evidence normalization for trends and suggestion candidates.

Semantic interpretation belongs to the persistent Hermes session.  This domain
module performs deterministic, auditable normalization only; it never calls a
second model endpoint or invents traffic predictions.
"""

from __future__ import annotations

import json
import re
from datetime import datetime


CATEGORY_KEYWORDS = {
    "科技/AI": ("ai", "人工智能", "gpt", "大模型", "芯片", "机器人", "deepseek", "openai"),
    "教育": ("教育", "高考", "考研", "大学", "学校", "学习", "教师"),
    "财经/商业": ("财经", "商业", "股市", "基金", "融资", "ipo", "电商", "品牌", "创业"),
    "娱乐/影视": ("电影", "综艺", "电视剧", "明星", "演唱会", "音乐"),
}

GENERIC_TAG_TOKENS = {
    "fyp", "fy", "foryou", "foryoupage", "foru", "viral", "trending",
    "hot", "trend", "热门", "热点", "上热门", "推荐", "流量", "挑战",
    "搞笑", "短剧", "短剧推荐", "好剧推荐", "剧集推荐", "追剧", "日常", "生活", "记录", "好物", "种草", "娱乐",
    "douyin", "抖音", "tiktok", "tik tok",
}

GENERIC_TAG_PATTERNS = (
    re.compile(r"(因为.*片段.*看.*整部剧|短剧|好剧|追剧|剧荒|影视推荐|电视剧推荐|全集|完整版)"),
    re.compile(r"(搞笑|沙雕|段子|名场面|解压|治愈|反转|爽文|爽剧)"),
    re.compile(r"(上热门|热门推荐|热门话题|流量密码|推荐一下|挑战赛?)"),
)


def _extract(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "result", "list", "items"):
            value = data.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                for nested in ("list", "items", "realtime", "hot"):
                    nested_value = value.get(nested)
                    if isinstance(nested_value, list):
                        return nested_value
    return []


def _identity(title: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]", "", title).lower()


def _tag_tokens(title: str) -> list[str]:
    return [
        token.strip().lower()
        for token in re.findall(r"#\s*([A-Za-z0-9_\-\u4e00-\u9fff]{1,30})", title)
        if token.strip()
    ]


def _invalid_trend_reason(title: str, platform: str = "", source_category: str = "") -> str:
    text = re.sub(r"\s+", " ", str(title or "")).strip()
    if not text:
        return "empty_title"
    lowered = text.lower()
    identity = _identity(text)
    tags = _tag_tokens(text)
    without_tags = re.sub(r"#\s*[A-Za-z0-9_\-\u4e00-\u9fff]{1,30}", "", text).strip()

    if lowered in GENERIC_TAG_TOKENS or identity in GENERIC_TAG_TOKENS:
        return "generic_tag_title"
    if tags and not without_tags:
        normalized_tags = {re.sub(r"[^\w\u4e00-\u9fff]", "", tag).lower() for tag in tags}
        if normalized_tags and normalized_tags.issubset(GENERIC_TAG_TOKENS):
            return "generic_hashtag_only"
        if any(pattern.search(tag) for pattern in GENERIC_TAG_PATTERNS for tag in normalized_tags):
            return "generic_promo_hashtag_only"
    if re.fullmatch(r"#?\s*(?:fyp|fy|foryou|foryoupage|foru|viral|trending)[\W_]*", lowered):
        return "fyp_distribution_tag"
    if str(platform).lower() in {"douyin", "tiktok"} and tags and not without_tags:
        normalized_tags = {re.sub(r"[^\w\u4e00-\u9fff]", "", tag).lower() for tag in tags}
        if normalized_tags & GENERIC_TAG_TOKENS:
            return "platform_distribution_hashtag_only"
    if source_category and any(marker in source_category for marker in ("热门话题", "热门挑战")):
        if tags and not without_tags:
            return "creator_center_tag_topic"
    return ""


def _term_candidates(value) -> set[str]:
    terms: set[str] = set()
    if value is None:
        return terms
    if isinstance(value, dict):
        for item in value.values():
            terms |= _term_candidates(item)
        return terms
    if isinstance(value, (list, tuple, set)):
        for item in value:
            terms |= _term_candidates(item)
        return terms

    text = re.sub(r"\s+", " ", str(value or "")).strip().lower()
    if not text:
        return terms
    for part in re.split(r"[\s,，、/|;；:：()（）【】\[\]<>《》]+|和|与|及|或", text):
        part = part.strip(" -_")
        if 2 <= len(part) <= 24:
            terms.add(part)
    for token in re.findall(r"[a-z][a-z0-9+\-.]{1,24}|[\u4e00-\u9fff]{2,12}", text):
        if 2 <= len(token) <= 24:
            terms.add(token)
    return terms


def _trend_search_text(item: dict) -> str:
    return " ".join(str(item.get(key) or "") for key in (
        "title", "category", "source_category", "source_platform",
    )).lower()


def rank_trends_for_context(payload: dict, context: dict | None = None, *, limit: int = 30) -> dict:
    """Score trends against account DNA without inventing semantic facts.

    No positioning/DNA means exploration mode: keep quality-filtered evidence.
    With positioning/DNA, require at least one positive account match and drop
    taboo matches. Heat/rank only break ties after fit.
    """
    if not isinstance(payload, dict):
        return payload
    context = context or {}
    dna = context.get("dna") if isinstance(context.get("dna"), dict) else {}
    account_platform = str(context.get("platform") or "").lower()

    positive_terms = (
        _term_candidates(dna.get("audience"))
        | _term_candidates(dna.get("persona"))
        | _term_candidates(dna.get("content_pillars"))
        | _term_candidates(dna.get("goals"))
        | _term_candidates(dna.get("promise"))
    )
    taboo_terms = _term_candidates(dna.get("taboos")) | _term_candidates(dna.get("exclusions"))
    has_positioning = bool(positive_terms)

    scored: list[dict] = []
    rejected: list[dict] = []
    for item in payload.get("top_trends") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("trend") or "")
        invalid = _invalid_trend_reason(
            title,
            str(item.get("source_platform") or item.get("trend_source") or ""),
            str(item.get("source_category") or item.get("category") or ""),
        )
        if invalid:
            rejected.append({"title": title[:200], "reason": invalid})
            continue
        search_text = _trend_search_text(item)
        taboo_hits = sorted(term for term in taboo_terms if term and term in search_text)[:5]
        if taboo_hits:
            rejected.append({"title": title[:200], "reason": "account_taboo", "matches": taboo_hits})
            continue
        matches = sorted(term for term in positive_terms if term and term in search_text)[:8]
        platform_bonus = 0.08 if account_platform and str(item.get("source_platform", "")).lower() == account_platform else 0
        rank = item.get("rank")
        try:
            evidence_bonus = max(0, 0.12 - min(max(int(rank or 999), 1), 30) * 0.003)
        except (TypeError, ValueError):
            evidence_bonus = 0.03
        if has_positioning and not matches:
            rejected.append({"title": title[:200], "reason": "account_mismatch"})
            continue
        score = min(1.0, (0.34 if has_positioning else 0.18) + len(matches) * 0.12 + platform_bonus + evidence_bonus)
        label = "适合当前账号" if score >= 0.62 else "可观察" if score >= 0.42 else "探索"
        scored.append({
            **item,
            "relevance_score": round(score, 3),
            "relevance_label": label,
            "match_reasons": matches,
            "fit_mode": "account_positioning" if has_positioning else "exploration",
        })

    if has_positioning:
        scored.sort(key=lambda item: (item.get("relevance_score", 0), -(item.get("rank") or 999)), reverse=True)

    ranked = scored[: max(1, min(int(limit or 30), 30))]
    categories: dict[str, list[dict]] = {}
    for item in ranked:
        categories.setdefault(str(item.get("category") or "其他"), []).append(item)
    return {
        **payload,
        "top_trends": ranked,
        "categories": categories,
        "matched": len(ranked),
        "relevance_mode": "account_positioning" if has_positioning else "exploration",
        "relevance_context": {
            "account_id": context.get("account_id"),
            "platform": account_platform or None,
            "has_positioning": has_positioning,
            "positive_terms_count": len(positive_terms),
        },
        "relevance_rejections": rejected[:80],
    }


def _category(title: str) -> str:
    lowered = title.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    return "其他"


def analyze_trends(params, **_kwargs) -> str:
    raw = params.get("hot_data", {})
    try:
        hot_data = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        hot_data = {}
    if not isinstance(hot_data, dict):
        hot_data = {}

    collected_at = hot_data.get("aggregated_at")
    per_platform: dict[str, list[dict]] = {}
    rejected: list[dict] = []
    for platform, result in hot_data.get("results", {}).items():
        if not isinstance(result, dict) or not result.get("success"):
            continue
        for index, item in enumerate(_extract(result)):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            if not title:
                continue
            source_category = str(item.get("category") or item.get("source_category") or "")
            invalid_reason = _invalid_trend_reason(title, platform, source_category)
            if invalid_reason:
                rejected.append({
                    "title": title[:200],
                    "source_platform": platform,
                    "source_backend": item.get("source_backend") or result.get("backend_used"),
                    "rank": item.get("rank", index + 1),
                    "reason": invalid_reason,
                    "source_category": source_category,
                })
                continue
            per_platform.setdefault(platform, []).append({
                "title": title[:200],
                "source_platform": platform,
                "source_backend": item.get("source_backend") or result.get("backend_used"),
                "rank": item.get("rank", index + 1),
                "heat_value": item.get("heat_value", item.get("heat", "")),
                "url": str(item.get("url", ""))[:1000],
                "collected_at": item.get("collected_at") or collected_at,
                "source_category": source_category or None,
                "video_id": item.get("video_id"),
                "author": item.get("author") if isinstance(item.get("author"), dict) else None,
                "metrics": item.get("metrics") if isinstance(item.get("metrics"), dict) else None,
            })

    # Network completion order must not decide the feed. Interleave each
    # platform's rank 1, then rank 2, and so on, using the requested platform
    # order. This keeps one fast source from occupying the entire top 30.
    requested_order = [
        platform for platform in hot_data.get("platforms_scraped", [])
        if platform in per_platform
    ]
    platform_order = requested_order + sorted(set(per_platform) - set(requested_order))
    flat: list[dict] = []
    max_items = max((len(items) for items in per_platform.values()), default=0)
    for index in range(max_items):
        for platform in platform_order:
            items = per_platform[platform]
            if index < len(items):
                flat.append(items[index])

    deduped: list[dict] = []
    seen: set[str] = set()
    for item in flat:
        identity = _identity(item["title"])
        if not identity or identity in seen:
            continue
        seen.add(identity)
        deduped.append({**item, "category": _category(item["title"])})

    categories: dict[str, list[dict]] = {}
    for item in deduped:
        categories.setdefault(item["category"], []).append(item)

    failures = {
        platform: result.get("error", "抓取失败")
        for platform, result in hot_data.get("results", {}).items()
        if isinstance(result, dict) and not result.get("success")
    }
    note = "结构化证据已整理，语义判断由 Hermes Agent 在用户与账号上下文中完成。"
    if not deduped:
        note = "没有可用的真实热点证据，禁止生成选题结论。"

    return json.dumps({
        "analyzed_at": datetime.now().isoformat(),
        "total_raw": len(flat),
        "total_deduped": len(deduped),
        "total_rejected": len(rejected),
        "categories": categories,
        "top_trends": deduped[:30],
        "quality_rejections": rejected[:50],
        "source_errors": failures,
        "data_quality_note": note,
        "analysis_method": "deterministic_evidence_index",
        "requires_agent_interpretation": True,
    }, ensure_ascii=False)


def _profile_terms(profile: dict) -> set[str]:
    text = " ".join(str(profile.get(key, "")) for key in ("category", "niche", "profession", "interests"))
    return {term.lower() for term in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2,}", text) if term}


def _profile_summary(profile: dict) -> str:
    values = [str(profile.get(key, "")).strip() for key in ("category", "niche", "profession", "interests")]
    return " / ".join(value for value in values if value) or "未设置"


def generate_content_suggestions(params, **_kwargs) -> str:
    profile = params.get("user_profile", {})
    trends = params.get("trends", {})
    try:
        profile = json.loads(profile) if isinstance(profile, str) else profile
    except (json.JSONDecodeError, TypeError):
        profile = {}
    try:
        trends = json.loads(trends) if isinstance(trends, str) else trends
    except (json.JSONDecodeError, TypeError):
        trends = {}
    if not isinstance(profile, dict):
        profile = {}
    if not isinstance(trends, dict):
        trends = {}

    terms = _profile_terms(profile)
    candidates = []
    for index, trend in enumerate(trends.get("top_trends", [])):
        if not isinstance(trend, dict):
            continue
        title = str(trend.get("title", ""))
        lowered = title.lower()
        matches = sorted(term for term in terms if term in lowered)
        candidates.append({
            "id": f"candidate_{index + 1:03d}",
            "trend": title,
            "trend_source": trend.get("source_platform", ""),
            "category": trend.get("category", "其他"),
            "relevance": min(1.0, 0.2 + 0.2 * len(matches)) if terms else 0.2,
            "confidence": 0.35 if matches else 0.2,
            "why": f"画像词命中：{'、'.join(matches)}" if matches else "仅作为待 Agent 判断的真实热点候选",
            "angles": [f"请 Agent 结合账号定位分析：{title}"],
            "target_audience": "待结合账号 DNA 判断",
            "evidence": {
                "platform": trend.get("source_platform"),
                "backend": trend.get("source_backend"),
                "url": trend.get("url"),
                "rank": trend.get("rank"),
                "collected_at": trend.get("collected_at"),
            },
            "requires_agent_interpretation": True,
        })

    candidates.sort(key=lambda item: (item["relevance"], -(item["evidence"].get("rank") or 9999)), reverse=True)
    return json.dumps({
        "generated_at": datetime.now().isoformat(),
        "user_profile_summary": _profile_summary(profile),
        "matched_trends_count": len(candidates),
        "suggestions": candidates[:20],
        "data_disclaimer": "这里只整理真实证据候选；最终选题由同一 Hermes 会话结合用户和账号上下文生成。",
        "analysis_method": "candidate_index",
    }, ensure_ascii=False)


TOOLS = [
    {
        "name": "analyze_trends",
        "description": "把真实热点整理为带来源、时间和失败信息的证据索引",
        "schema": {
            "type": "object",
            "properties": {"hot_data": {"type": "object"}},
            "required": ["hot_data"],
        },
        "handler": analyze_trends,
    },
    {
        "name": "generate_content_suggestions",
        "description": "生成待 Hermes Agent 解释的热点候选，不预测流量",
        "schema": {
            "type": "object",
            "properties": {"user_profile": {"type": "object"}, "trends": {"type": "object"}},
            "required": ["user_profile", "trends"],
        },
        "handler": generate_content_suggestions,
    },
]
