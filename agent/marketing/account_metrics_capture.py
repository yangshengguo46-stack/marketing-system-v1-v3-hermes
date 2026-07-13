"""Trusted projection of first-party account collectors into account truth."""

from __future__ import annotations

import json
from typing import Any

from agent.account_registry import AccountRegistry
from agent.marketing.domains.account_portfolio import (
    PORTFOLIO_SCHEMA as WECHAT_PORTFOLIO_SCHEMA,
)
from agent.marketing.domains.browser_payloads import decode_schema_payload
from agent.marketing.session_scope import read_tool_session_scope


DOUYIN_PORTFOLIO_SCHEMA = "marketing_douyin_owned_portfolio.v1"
DOUYIN_TOOL_NAMES = {
    "browser_collect_douyin_portfolio",
    "mcp_marketing_browser_browser_collect_douyin_portfolio",
}
WECHAT_TOOL_NAMES = {
    "browser_collect_wechat_official_portfolio",
    "mcp_marketing_browser_browser_collect_wechat_official_portfolio",
}


def decode_account_metrics_result(result: Any) -> dict[str, Any] | None:
    for schema in (DOUYIN_PORTFOLIO_SCHEMA, WECHAT_PORTFOLIO_SCHEMA):
        payload = decode_schema_payload(result, schema)
        if payload is not None:
            return payload
    return None


def apply_account_metrics(
    payload: dict[str, Any],
    *,
    user_id: str,
    account_id: str,
    session_db: Any = None,
) -> dict[str, Any]:
    """Update canonical stats only from one schema-bound account collector."""

    platform = str(payload.get("platform") or "")
    schema = str(payload.get("schema") or "")
    if (platform, schema) not in {
        ("douyin", DOUYIN_PORTFOLIO_SCHEMA),
        ("wechat_official", WECHAT_PORTFOLIO_SCHEMA),
    }:
        raise ValueError("unsupported account metrics payload")
    registry = AccountRegistry(session_db)
    try:
        current = registry.get(account_id, user_id=user_id)
        if current.get("platform") != platform:
            raise ValueError("account metrics do not match the bound account scope")
        stats = (
            _douyin_stats(payload)
            if platform == "douyin"
            else _wechat_stats(payload)
        )
        account_name = str((payload.get("account") or {}).get("name") or "").strip()
        updated = registry.mark_authenticated(
            account_id,
            user_id=user_id,
            platform_user_id=current.get("platform_user_id"),
            username=account_name or current.get("username"),
            stats=stats,
        )
    finally:
        registry.close()
    return {
        "schema": "marketing_account_metrics_projection.v1",
        "account_id": account_id,
        "platform": platform,
        "stats": updated.get("stats") or {},
        "auth_state": updated.get("auth_state"),
    }


def enrich_tool_result_with_account_metrics(
    *,
    tool_name: str,
    result: Any,
    task_id: str = "",
    session_id: str = "",
) -> Any:
    if tool_name not in DOUYIN_TOOL_NAMES | WECHAT_TOOL_NAMES:
        return result
    payload = decode_account_metrics_result(result)
    scope = read_tool_session_scope(task_id=task_id, session_id=session_id)
    if payload is None or not scope:
        return result
    projection = apply_account_metrics(
        payload,
        user_id=str(scope["user_id"]),
        account_id=str(scope["account_id"]),
    )
    return str(result) + "\n\nMarketing OS account metrics projection:\n" + json.dumps(
        projection, ensure_ascii=False, indent=2
    )


def _douyin_stats(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    collection = payload.get("collection") if isinstance(payload.get("collection"), dict) else {}
    public_count = _integer(raw.get("public_work_count"))
    if public_count is None and collection.get("complete") is True:
        public_count = sum(
            1
            for work in payload.get("works") or []
            if isinstance(work, dict)
            and work.get("visibility") == "public"
            and work.get("publication_state") == "published"
        )
    complete = collection.get("complete") is True
    values = {
        "followers": _integer(raw.get("followers")),
        "following": _integer(raw.get("following")),
        "total_likes": _integer(raw.get("total_likes")),
        "total_views": _integer(raw.get("public_view_count")) if complete else None,
        "videos_count": public_count,
        "all_videos_count": _integer(raw.get("all_work_count")),
        "private_videos_count": _integer(raw.get("private_work_count")),
        "public_video_likes": _integer(raw.get("public_like_count")) if complete else None,
    }
    return {
        **{key: value for key, value in values.items() if value is not None},
        "observed_at": str(payload.get("observed_at") or ""),
        "metrics_provenance": {
            "source": "douyin_creator_center_work_list",
            "work_count_scope": "public_published",
            "all_work_count_includes_private": True,
            "collection_complete": complete,
        },
    }


def _wechat_stats(payload: dict[str, Any]) -> dict[str, Any]:
    articles = [item for item in payload.get("articles") or [] if isinstance(item, dict)]
    measured = [item for item in articles if isinstance(item.get("metrics"), dict) and item["metrics"]]
    sums = {
        "read_users": "read_users",
        "share_users": "share_users",
        "like_count": "like_count",
        "recommend_count": "recommend_count",
        "comment_count": "comment_count",
        "collection_users": "collection_users",
        "followers_gained": "followers_gained",
    }
    stats = {
        output: sum(_integer(item["metrics"].get(source)) or 0 for item in measured)
        for output, source in sums.items()
    }
    return {
        **stats,
        "articles_count": len(articles),
        "measured_articles_count": len(measured),
        "observed_at": str(payload.get("observed_at") or ""),
        "metrics_provenance": {
            "source": "wechat_content_analysis_detail",
            "window": "first_30_days_after_publish",
            "read_unit": "unique_users",
            "share_unit": "unique_users",
            "aggregation": "sum_across_collected_articles",
        },
    }


def _integer(value: Any) -> int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return int(number)
