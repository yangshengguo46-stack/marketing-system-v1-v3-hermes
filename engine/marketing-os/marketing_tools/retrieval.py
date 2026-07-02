"""MEM-11: Structured memory retrieval with FTS scoring.

Filter by scope first, then rank by relevance.  Keep metrics for
later evaluation.
"""

from __future__ import annotations
from typing import Any


def filter_by_scope(
    memories: list[dict[str, Any]], *,
    user_id: str = "", account_id: str = "",
    platform: str = "", kind: str = "",
    workspace: str = "",
) -> list[dict[str, Any]]:
    results = []
    for m in memories:
        if user_id and m.get("user_id") != user_id:
            continue
        if account_id and m.get("account_id") and m["account_id"] != account_id:
            continue
        if platform and m.get("platform") and m["platform"] != platform:
            continue
        if kind and m.get("kind") != kind:
            continue
        if workspace and m.get("workspace") and m["workspace"] != workspace:
            continue
        results.append(m)
    return results


def rank_by_confidence(
    memories: list[dict[str, Any]], query: str = "",
) -> list[dict[str, Any]]:
    """Simple relevance scoring: confidence * content similarity.

    Returns memories sorted by score descending.
    """
    scored: list[tuple[float, dict[str, Any]]] = []
    q_lower = query.lower()
    for m in memories:
        score = m.get("confidence", 0.5)
        content = str(m.get("content", "")).lower()
        if q_lower and q_lower in content:
            score += 0.2
        if m.get("status") == "locked":
            score += 0.1
        scored.append((score, m))
    scored.sort(key=lambda x: -x[0])
    return [m for _, m in scored]


def retrieve(
    memories: list[dict[str, Any]], query: str = "",
    *, user_id: str = "", account_id: str = "",
    limit: int = 20, **filters,
) -> dict[str, Any]:
    """Full retrieval pipeline: filter → rank → limit."""
    filtered = filter_by_scope(memories, user_id=user_id, account_id=account_id, **filters)
    ranked = rank_by_confidence(filtered, query=query)
    return {
        "results": ranked[:limit],
        "total_candidates": len(memories),
        "filtered_count": len(filtered),
        "returned_count": min(limit, len(ranked)),
    }
