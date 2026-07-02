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
    for platform, result in hot_data.get("results", {}).items():
        if not isinstance(result, dict) or not result.get("success"):
            continue
        for index, item in enumerate(_extract(result)):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            if not title:
                continue
            per_platform.setdefault(platform, []).append({
                "title": title[:200],
                "source_platform": platform,
                "source_backend": item.get("source_backend") or result.get("backend_used"),
                "rank": item.get("rank", index + 1),
                "heat_value": item.get("heat_value", item.get("heat", "")),
                "url": str(item.get("url", ""))[:1000],
                "collected_at": item.get("collected_at") or collected_at,
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
        "categories": categories,
        "top_trends": deduped[:30],
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
