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
    asset: dict[str, Any], *, attachment: dict[str, Any] | None = None,
    attachments: list[dict[str, Any]] | None = None,
    now: str | None = None,
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
        if isinstance(content, dict) and any(
            content.get(key) for key in ("file_path", "local_path", "media_path")
        ):
            errors.append("raw local media paths are forbidden; import a managed attachment")
        if not attachment or attachment.get("status") != "active":
            errors.append("missing active media attachment")
        elif attachment.get("asset_id") != asset.get("id"):
            errors.append("media attachment asset mismatch")
        elif attachment.get("account_id") != account_id:
            errors.append("media attachment account mismatch")
        elif not str(attachment.get("sha256") or ""):
            errors.append("media attachment hash missing")
        duration = content.get("duration") if isinstance(content, dict) else None
        if duration is not None and not isinstance(duration, (int, float)):
            errors.append("invalid duration")
    if asset.get("type") == "image":
        active = attachments or ([attachment] if attachment else [])
        if not 1 <= len(active) <= 9:
            errors.append("image posts require 1 to 9 active media attachments")
        for item in active:
            if item.get("status") != "active":
                errors.append("image attachment is not active")
            elif item.get("asset_id") != asset.get("id"):
                errors.append("media attachment asset mismatch")
            elif item.get("account_id") != account_id:
                errors.append("media attachment account mismatch")
            elif not str(item.get("mime_type") or "").startswith("image/"):
                errors.append("image posts require image attachments")
            elif not str(item.get("sha256") or ""):
                errors.append("media attachment hash missing")
    return {"valid": len(errors) == 0, "errors": errors}
