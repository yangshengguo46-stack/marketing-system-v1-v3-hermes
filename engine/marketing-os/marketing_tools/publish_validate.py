"""PUB-06: Pre-publish validation checks.

Catches invalid publish requests before they reach the effect layer.
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any

PLATFORM_CONSTRAINTS = {
    "douyin": {"title_max": 55, "max_tags": 10},
    "bilibili": {"title_max": 80, "max_tags": 10},
    "default": {"title_max": 100, "max_tags": 10},
}


def validate_publish_request(
    asset: dict[str, Any], *, now: str | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    platform = str(asset.get("platform", "")).strip().lower()
    if not platform:
        return {"valid": False, "errors": ["missing platform"]}
    constraints = PLATFORM_CONSTRAINTS.get(platform, PLATFORM_CONSTRAINTS["default"])
    title = str(asset.get("title", "")).strip()
    if not title:
        errors.append("missing title")
    elif len(title) > constraints["title_max"]:
        errors.append(f"title too long: {len(title)} > {constraints['title_max']}")
    if asset.get("status") not in ("approved", "review"):
        errors.append(f"not publishable from status {asset.get('status')!r}")
    account_id = asset.get("account_id")
    if not account_id:
        errors.append("missing account_id")
    if asset.get("type") == "video":
        content = asset.get("content") or {}
        duration = content.get("duration") if isinstance(content, dict) else None
        if duration is not None and not isinstance(duration, (int, float)):
            errors.append("invalid duration")
    return {"valid": len(errors) == 0, "errors": errors}
