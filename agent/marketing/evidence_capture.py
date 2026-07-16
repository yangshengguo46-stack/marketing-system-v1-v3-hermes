"""Native Hermes tool-result seam for Marketing OS EvidencePack capture."""

from __future__ import annotations

import json
from typing import Any

from agent.marketing.domains.evidence import EvidenceRepository
from agent.marketing.domains.account_portfolio import (
    AccountPortfolioRepository,
    decode_browser_portfolio_result,
)
from agent.marketing.domains.short_video_signals import (
    ShortVideoSignalRepository,
    decode_browser_signal_result,
)
from agent.marketing.domains.public_content_observations import (
    PublicContentObservationRepository,
    decode_browser_public_content_result,
)
from agent.marketing.session_scope import read_tool_session_scope


SHORT_VIDEO_SIGNAL_TOOL_NAMES = {
    "browser_extract_short_video_signals",
    "mcp_marketing_browser_browser_extract_short_video_signals",
}

ACCOUNT_PORTFOLIO_TOOL_NAMES = {
    "browser_collect_wechat_official_portfolio",
    "mcp_marketing_browser_browser_collect_wechat_official_portfolio",
}

PUBLIC_CONTENT_TOOL_NAMES = {
    "browser_capture_public_content",
    "mcp_marketing_browser_browser_capture_public_content",
}


def enrich_tool_result_with_evidence(
    *,
    tool_name: str,
    args: dict[str, Any],
    result: Any,
    task_id: str = "",
    session_id: str = "",
    tool_call_id: str = "",
) -> Any:
    """Capture successful native extraction output and expose generated IDs.

    This is intentionally invoked *after* the real tool handler.  There is no
    model-facing evidence-create operation, so an arbitrary URL or model-written
    excerpt cannot enter the verified store through the marketing toolset.
    """

    if tool_name in ACCOUNT_PORTFOLIO_TOOL_NAMES:
        scope = read_tool_session_scope(task_id=task_id, session_id=session_id)
        payload = decode_browser_portfolio_result(result)
        if not scope or payload is None:
            return result
        capture = AccountPortfolioRepository().capture_browser_result(
            user_id=str(scope["user_id"]),
            account_id=str(scope["account_id"]),
            payload=payload,
            session_id=str(session_id or task_id),
            tool_call_id=str(tool_call_id or ""),
        )
        return str(result) + "\n\nMarketing OS owned-account capture:\n" + json.dumps(
            capture, ensure_ascii=False, indent=2
        )
    if tool_name in SHORT_VIDEO_SIGNAL_TOOL_NAMES:
        scope = read_tool_session_scope(task_id=task_id, session_id=session_id)
        payload = decode_browser_signal_result(result)
        if not scope or payload is None:
            return result
        capture = ShortVideoSignalRepository().capture_browser_result(
            user_id=str(scope["user_id"]),
            account_id=str(scope["account_id"]),
            payload=payload,
            session_id=str(session_id or task_id),
            tool_call_id=str(tool_call_id or ""),
        )
        return str(result) + "\n\nMarketing OS verified capture:\n" + json.dumps(
            capture, ensure_ascii=False, indent=2
        )
    if tool_name in PUBLIC_CONTENT_TOOL_NAMES:
        scope = read_tool_session_scope(task_id=task_id, session_id=session_id)
        payload = decode_browser_public_content_result(result)
        if not scope or payload is None:
            return result
        capture = PublicContentObservationRepository().capture_browser_result(
            user_id=str(scope["user_id"]),
            account_id=str(scope["account_id"]),
            payload=payload,
            session_id=str(session_id or task_id),
            tool_call_id=str(tool_call_id or ""),
        )
        return str(result) + "\n\nMarketing OS public natural-experiment capture:\n" + json.dumps(
            capture, ensure_ascii=False, indent=2
        )
    if tool_name != "web_extract" or not isinstance(result, str):
        return result
    scope = read_tool_session_scope(task_id=task_id, session_id=session_id)
    if not scope:
        return result
    try:
        payload = json.loads(result)
    except (TypeError, ValueError):
        return result
    if not isinstance(payload, dict) or payload.get("error"):
        return result

    records = EvidenceRepository().capture_web_extract_result(
        user_id=str(scope["user_id"]),
        account_id=str(scope["account_id"]),
        result=payload,
        session_id=str(session_id or task_id),
        tool_call_id=str(tool_call_id or ""),
        requested_urls=args.get("urls") if isinstance(args.get("urls"), list) else [],
    )
    if not records:
        return result
    payload["marketing_evidence"] = {
        "records": [
            {
                "evidence_id": record["id"],
                "url": record["canonical_url"],
                "status": record["status"],
                "verification_level": record["verification_level"],
                "content_sha256": record["content_sha256"],
            }
            for record in records
        ],
        "citation_rule": (
            "Use these evidence_id values in marketing content tools; raw URLs and source: strings are not valid evidence_refs."
        ),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
