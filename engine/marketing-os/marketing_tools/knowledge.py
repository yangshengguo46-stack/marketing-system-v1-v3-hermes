"""MEM-09: Structured platform knowledge entries.

Knowledge entries have source, region, version, valid_from, valid_to.
Older rules never silently overwrite newer ones.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any


def create_knowledge_entry(
    content: str, *, source: str, region: str = "cn",
    version: str = "1.0", valid_from: str = "", valid_to: str = "",
    **extra,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "content": str(content)[:2000], "source": str(source),
        "region": str(region)[:50], "version": str(version)[:50],
        "valid_from": valid_from or datetime.now(timezone.utc).isoformat(),
        "valid_to": valid_to or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    entry.update({k: v for k, v in extra.items() if k not in entry})
    return entry


def knowledge_is_expired(entry: dict[str, Any], *, now: str | None = None) -> bool:
    if not entry.get("valid_to"):
        return False
    try:
        ref = datetime.fromisoformat(now) if now else datetime.now(timezone.utc)
        return datetime.fromisoformat(entry["valid_to"]) < ref
    except (ValueError, TypeError):
        return False


def supersedes_knowledge(newer: dict[str, Any], older: dict[str, Any]) -> bool:
    """True if *newer* should replace *older* (same source + region)."""
    if newer.get("source") != older.get("source"):
        return False
    if newer.get("region") != older.get("region"):
        return False
    try:
        nv = tuple(int(x) for x in str(newer.get("version", "0")).split("."))
        ov = tuple(int(x) for x in str(older.get("version", "0")).split("."))
        return nv > ov
    except (ValueError, TypeError):
        return newer.get("created_at", "") > older.get("created_at", "")
