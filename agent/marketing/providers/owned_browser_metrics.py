"""Silent first-party metric collection from account-scoped browser profiles."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from agent.marketing.account_metrics_capture import (
    apply_account_metrics,
    decode_account_metrics_result,
)
from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.account_portfolio import AccountPortfolioRepository
from agent.marketing.intelligence.store import OperatingLoopRepository


SUPPORTED_OWNED_METRIC_PLATFORMS = {"douyin", "wechat_official"}


def collect_owned_browser_metrics(
    paths: MarketingDataPaths,
    action: dict[str, Any],
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    """Read one published work without exposing cookies or browser credentials."""

    platform = str(action.get("platform") or "")
    if platform not in SUPPORTED_OWNED_METRIC_PLATFORMS:
        raise KeyError(f"no silent first-party metric collector for {platform}")
    receipt_id = str(action.get("receipt_id") or "")
    if not receipt_id:
        return _unavailable_or_wait(checkpoint, "publish receipt is unavailable")
    receipt = OperatingLoopRepository(paths).get_receipt(receipt_id)
    summary = receipt.get("summary") or {}
    post_id = str(summary.get("platform_post_id") or "").strip()
    published_url = _canonical_url(summary.get("published_url"))
    if not post_id and not published_url:
        return _unavailable_or_wait(checkpoint, "publish receipt has no stable work identity")

    from tools.mcp_tool import execute_marketing_account_browser_tool

    tool_name, arguments = (
        ("browser_collect_douyin_portfolio", {"max_works": 50})
        if platform == "douyin"
        else ("browser_collect_wechat_official_portfolio", {"max_articles": 50})
    )
    raw = execute_marketing_account_browser_tool(
        account_id=str(action.get("account_id") or ""),
        user_id=str(action.get("user_id") or "default"),
        tool_name=tool_name,
        arguments=arguments,
    )
    payload = decode_account_metrics_result(raw)
    if payload is None:
        return _unavailable_or_wait(checkpoint, "account collector returned no schema-bound metrics")
    apply_account_metrics(
        payload,
        user_id=str(action.get("user_id") or "default"),
        account_id=str(action.get("account_id") or ""),
    )
    if platform == "wechat_official":
        AccountPortfolioRepository(paths).capture_browser_result(
            user_id=str(action.get("user_id") or "default"),
            account_id=str(action.get("account_id") or ""),
            payload=payload,
            session_id=f"metric-checkpoint-{checkpoint['id']}",
            tool_call_id="system-owned-metric-loop",
        )
    items = payload.get("works") if platform == "douyin" else payload.get("articles")
    item = next(
        (
            value
            for value in (items or [])
            if isinstance(value, dict)
            and (
                (post_id and str(value.get("source_item_id") or "") == post_id)
                or (published_url and _canonical_url(value.get("source_url")) == published_url)
            )
        ),
        None,
    )
    if item is None:
        return _unavailable_or_wait(checkpoint, "published work is not visible in owned portfolio")
    metrics = _normalized_metrics(platform, item.get("metrics"))
    if not metrics:
        return _unavailable_or_wait(checkpoint, "owned work metrics are not ready")
    provenance = item.get("metrics_provenance") or {}
    return {
        "state": "observed",
        "metrics": metrics,
        "verification_source": str(provenance.get("source") or tool_name),
        "observed_at": str(payload.get("observed_at") or checkpoint.get("due_at") or ""),
    }


def _normalized_metrics(platform: str, value: Any) -> dict[str, int | float]:
    raw = value if isinstance(value, dict) else {}
    aliases = (
        {
            "view_count": "views",
            "like_count": "likes",
            "comment_count": "comments",
            "share_count": "shares",
            "favorite_count": "saves",
            "homepage_visit_count": "profile_visits",
            "followers_gained": "new_followers",
            "followers_lost": "unfollows",
        }
        if platform == "douyin"
        else {
            "read_users": "views",
            "share_users": "shares",
            "like_count": "likes",
            "comment_count": "comments",
            "collection_users": "saves",
            "followers_gained": "new_followers",
        }
    )
    result: dict[str, int | float] = {}
    for key, item in raw.items():
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            continue
        result[str(key)] = item
        alias = aliases.get(str(key))
        if alias:
            result[alias] = item
    return result


def _unavailable_or_wait(checkpoint: dict[str, Any], reason: str) -> dict[str, Any]:
    if str(checkpoint.get("label") or "") == "7d":
        return {"state": "unavailable", "reason": reason}
    return {"state": "not_ready", "reason": reason, "retry_after_seconds": 21_600}


def _canonical_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parts = urlsplit(text)
    except ValueError:
        return ""
    if parts.scheme != "https" or not parts.hostname:
        return ""
    return urlunsplit(("https", parts.hostname.lower(), parts.path.rstrip("/") or "/", "", ""))
