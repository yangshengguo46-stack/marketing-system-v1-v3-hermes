"""Deterministic benchmark discovery over product-owned evidence.

The service never invents creators from topic titles.  A candidate is emitted
only when the source item carries a stable creator identity and a traceable URL.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


def _terms(value: Any) -> set[str]:
    text = str(value or "").lower()
    return {
        token for token in re.findall(r"[a-z0-9]{2,}|[\u4e00-\u9fff]{2,}", text)
        if token not in {"用户", "内容", "账号", "人群", "平台"}
    }


def _hypothesis_terms(hypothesis: dict[str, Any] | None) -> set[str]:
    if not hypothesis:
        return set()
    values: list[Any] = []
    for key in ("segments", "pains", "scenarios", "exclusions"):
        for item in hypothesis.get(key, []) or []:
            if isinstance(item, dict):
                values.extend(item.values())
            else:
                values.append(item)
    result: set[str] = set()
    for value in values:
        result.update(_terms(value))
    return result


def discover_benchmark_candidates(
    *, query: str, items: list[dict[str, Any]],
    audience_hypothesis: dict[str, Any] | None = None,
    platform: str | None = None, limit: int = 10,
) -> dict[str, Any]:
    """Group source items by creator and rank evidence-backed candidates."""
    query_terms = _terms(query)
    audience_terms = _hypothesis_terms(audience_hypothesis)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    skipped = {"missing_creator": 0, "missing_source": 0, "platform_mismatch": 0}

    for item in items:
        if not isinstance(item, dict):
            continue
        item_platform = str(item.get("source_platform") or item.get("platform") or "").strip().lower()
        if platform and item_platform != platform:
            skipped["platform_mismatch"] += 1
            continue
        author = item.get("author") if isinstance(item.get("author"), dict) else {}
        handle = str(
            author.get("id") or author.get("handle") or item.get("author_id") or ""
        ).strip()
        name = str(author.get("name") or item.get("author_name") or "").strip()
        if not handle:
            skipped["missing_creator"] += 1
            continue
        source_ref = str(item.get("url") or "").strip()
        if not source_ref:
            skipped["missing_source"] += 1
            continue
        normalized = dict(item)
        normalized["_author"] = {
            "id": handle,
            "name": name or handle,
            "profile_url": str(author.get("profile_url") or "").strip(),
            "bio": str(author.get("bio") or "").strip(),
            "followers": author.get("followers"),
        }
        grouped[(item_platform, handle)].append(normalized)

    candidates = []
    for (item_platform, handle), samples in grouped.items():
        author = samples[0]["_author"]
        text = " ".join(
            [author["name"], author["bio"]]
            + [str(sample.get("title") or "") for sample in samples]
        ).lower()
        query_hits = sorted(term for term in query_terms if term in text)
        audience_hits = sorted(term for term in audience_terms if term in text)
        query_score = len(query_hits) / max(1, len(query_terms))
        audience_score = min(1.0, len(audience_hits) / max(1, min(len(audience_terms), 5)))
        depth_score = min(1.0, len(samples) / 5)
        source_score = max(
            float(sample.get("quality_score") or 0.7) for sample in samples
        )
        score = round(
            0.45 * query_score + 0.25 * audience_score
            + 0.20 * depth_score + 0.10 * source_score,
            4,
        )
        if query_terms and not query_hits:
            continue
        source_refs = [str(sample.get("url")) for sample in samples]
        candidates.append({
            "platform": item_platform,
            "account_handle": handle,
            "account_name": author["name"],
            "profile_url": author["profile_url"],
            "suggested_relation": "direct" if (
                query_score >= 0.8 and audience_score >= 0.4 and len(samples) >= 3
            ) else "adjacent",
            "score": score,
            "score_components": {
                "query_match": round(query_score, 4),
                "audience_overlap": round(audience_score, 4),
                "sample_depth": round(depth_score, 4),
                "source_quality": round(source_score, 4),
            },
            "matched_query_terms": query_hits,
            "matched_audience_terms": audience_hits,
            "selection_reason": (
                f"关键词命中：{'、'.join(query_hits) or '无'}；"
                f"目标受众信号：{'、'.join(audience_hits) or '待验证'}；"
                f"当前有 {len(samples)} 条可追溯样本"
            ),
            "source_ref": author["profile_url"] or source_refs[0],
            "samples": [{
                "video_id": str(sample.get("video_id") or sample.get("bvid") or "") or None,
                "title": str(sample.get("title") or "")[:200],
                "transcript": None,
                "metrics": sample.get("metrics") if isinstance(sample.get("metrics"), dict) else {
                    "views": sample.get("heat_value")
                },
                "provenance": {
                    "source_kind": "public_web",
                    "source_ref": str(sample.get("url")),
                    "captured_at": str(sample.get("collected_at") or ""),
                    "source_backend": str(sample.get("source_backend") or "unknown"),
                },
            } for sample in samples[:5]],
        })

    candidates.sort(key=lambda item: (-item["score"], -len(item["samples"]), item["account_handle"]))
    return {
        "query": query,
        "platform": platform,
        "candidates": candidates[:max(1, min(int(limit), 20))],
        "candidate_count": min(len(candidates), max(1, min(int(limit), 20))),
        "source_item_count": len(items),
        "skipped": skipped,
        "method": "deterministic_creator_evidence_ranking_v1",
        "limitations": [
            "候选只来自带稳定作者身份的已采集内容",
            "匹配分数用于排序，不代表账号质量或因果结论",
            "negative 对标必须由用户明确选择",
        ],
    }
