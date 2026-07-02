"""DATA-15: Data retention TTLs and deletion paths."""

from datetime import datetime, timezone, timedelta
from typing import Any

RETENTION_TTL = {
    "trending_cache": 7,       # days
    "public_evidence": 90,     # days
    "account_metrics": 365,    # days
    "page_fixture": 7,         # days
    "downloaded_media": 30,    # days
    "mcp_stderr_logs": 7,      # days
    "debug_trace": 1,          # days
}


def is_expired(category: str, collected_at: str, *, now: str | None = None) -> bool:
    ttl = RETENTION_TTL.get(category)
    if ttl is None:
        return False
    try:
        collected = datetime.fromisoformat(collected_at)
        ref = datetime.fromisoformat(now) if now else datetime.now(timezone.utc)
        return (ref - collected) > timedelta(days=ttl)
    except (ValueError, TypeError):
        return False


def retention_policy(category: str) -> dict[str, Any]:
    ttl = RETENTION_TTL.get(category)
    return {"category": category, "ttl_days": ttl, "auto_delete": ttl is not None}
