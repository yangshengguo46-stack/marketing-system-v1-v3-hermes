"""Silent maintenance entrypoint for the Human Observation Core."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.epistemic_contract import _issue_system_authority


def run_human_observer_maintenance(
    *, db_path: str | Path | None = None
) -> dict[str, Any]:
    if db_path is None:
        from agent.marketing.data_paths import MarketingDataPaths

        db_path = MarketingDataPaths.from_env().agent_db
    from .marketing_connector import (
        MarketingPersonalIPConnector,
        MarketingReceiptConnector,
    )

    authority = _issue_system_authority("human_observer_maintenance")
    receipt_result = MarketingReceiptConnector(db_path, authority=authority).run()
    personal_ip_result = MarketingPersonalIPConnector(
        db_path, authority=authority
    ).run()
    return {
        "version": "human-observer-maintenance-v1",
        "connectors": {
            "marketing": receipt_result,
            "marketing_personal_ip": personal_ip_result,
        },
        "mode": "silent_system_owned",
        "user_mutable": False,
        "conversation_mutable": False,
    }
