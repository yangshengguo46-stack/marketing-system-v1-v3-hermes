"""MEM-10: Industry knowledge base with user/public permissions.

Documents don't silently become preferences. Access control, versioning,
and explicit reference required.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

DOC_SCOPE_USER = "user"
DOC_SCOPE_PUBLIC = "public"
DOC_SCOPES = frozenset({DOC_SCOPE_USER, DOC_SCOPE_PUBLIC})


def create_document(
    title: str, content: str, *, scope: str = DOC_SCOPE_USER,
    user_id: str = "", tags: list[str] | None = None,
    source_url: str = "", **extra,
) -> dict[str, Any]:
    if scope not in DOC_SCOPES:
        raise ValueError(f"scope must be one of {DOC_SCOPES}")
    doc: dict[str, Any] = {
        "title": str(title)[:500], "content": str(content)[:100_000],
        "scope": scope, "user_id": user_id,
        "tags": list(tags or [])[:20],
        "source_url": str(source_url)[:2048],
        "version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    doc.update({k: v for k, v in extra.items() if k not in doc})
    return doc


def can_read(doc: dict[str, Any], user_id: str) -> bool:
    if doc.get("scope") == DOC_SCOPE_PUBLIC:
        return True
    return doc.get("user_id") == user_id


def can_modify(doc: dict[str, Any], user_id: str) -> bool:
    return doc.get("user_id") == user_id and doc.get("scope") == DOC_SCOPE_USER
