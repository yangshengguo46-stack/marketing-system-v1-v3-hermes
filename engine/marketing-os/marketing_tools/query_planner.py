"""DATA-08: Industry query planning.

Expand a user goal ("AI教育行业") into concrete search keywords,
synonyms, exclusions, and platform differences.
"""

from __future__ import annotations
from typing import Any

INDUSTRY_KEYWORDS: dict[str, list[str]] = {
    "AI": ["AI", "人工智能", "大模型", "深度学习", "机器学习", "AIGC"],
    "教育": ["教育", "学习", "培训", "课程", "教学", "知识付费"],
    "美妆": ["美妆", "护肤", "彩妆", "化妆", "化妆品", "护肤品"],
    "餐饮": ["餐饮", "美食", "探店", "餐厅", "小吃", "外卖"],
    "汽车": ["汽车", "新能源", "电动车", "智能驾驶", "买车"],
}


def plan_queries(industries: list[str], platforms: list[str] | None = None) -> list[dict[str, Any]]:
    """Generate (keyword, platform, priority) tuples from industry names."""
    platforms = platforms or ["douyin", "bilibili"]
    queries: list[dict[str, Any]] = []
    for industry in industries:
        keywords = INDUSTRY_KEYWORDS.get(industry, [industry])
        for i, kw in enumerate(keywords):
            for p in platforms:
                queries.append({
                    "keyword": kw, "platform": p,
                    "industry": industry, "priority": i + 1,  # lower = higher priority
                })
    queries.sort(key=lambda q: (q["industry"], q["priority"]))
    seen = set()
    result = []
    for q in queries:
        key = f"{q['keyword']}:{q['platform']}"
        if key not in seen:
            seen.add(key)
            result.append(q)
    return result
