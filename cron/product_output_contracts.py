"""Fail-closed delivery contracts for product-owned Cron jobs."""

from __future__ import annotations

from typing import Any


DAILY_TOPIC_CONTRACT = "marketing.daily_topic_recommendations.v1"


def validate_product_cron_output(
    *, job: dict[str, Any], session_id: str, content: str
) -> dict[str, Any] | None:
    """Validate product-owned output before it can enter generic delivery."""

    contract = str(job.get("product_contract") or "").strip()
    if not contract:
        return None
    if contract == DAILY_TOPIC_CONTRACT:
        from agent.marketing.domains import TopicRecommendationRepository

        return TopicRecommendationRepository().validate_delivery(
            source_session_id=session_id,
            content=content,
        )
    raise ValueError(f"unsupported Cron product output contract: {contract}")
