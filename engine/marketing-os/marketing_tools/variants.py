"""PUB-03: Platform-specific content variants.

One creative idea → independent versions per platform (douyin/bilibili/etc).
Each variant inherits from the parent but has its own metadata.
"""

from __future__ import annotations
from typing import Any

VALID_PLATFORMS = frozenset({"douyin", "bilibili", "weibo", "xiaohongshu", "kuaishou", "zhihu"})


def create_variants(
    parent: dict[str, Any],
    platforms: list[str],
) -> list[dict[str, Any]]:
    variants = []
    seen = set()
    for p in platforms:
        p = str(p).strip().lower()
        if p not in VALID_PLATFORMS:
            continue
        if p in seen:
            continue
        seen.add(p)
        variant = dict(parent)
        variant["platform"] = p
        variant["parent_id"] = parent.get("id")
        variant["id"] = None  # caller assigns
        variant.pop("id", None)
        variant.setdefault("_variant_of", parent.get("id"))
        variants.append(variant)
    return variants


def is_variant_of(child: dict[str, Any], parent_id: str) -> bool:
    return str(child.get("_variant_of") or child.get("parent_id") or "") == parent_id
