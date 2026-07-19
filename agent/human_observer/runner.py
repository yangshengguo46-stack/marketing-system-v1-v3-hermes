"""Silent maintenance entrypoint for the Human Observation Core."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def run_human_observer_maintenance(*, db_path: str | Path | None = None) -> dict[str, Any]:
    if db_path is None:
        from agent.marketing.data_paths import MarketingDataPaths

        db_path = MarketingDataPaths.from_env().agent_db
    from .marketing_connector import MarketingReceiptConnector

    result = MarketingReceiptConnector(db_path).run()
    return {
        "version": "human-observer-maintenance-v1",
        "connectors": {"marketing": result},
        "mode": "silent_system_owned",
        "user_mutable": False,
        "conversation_mutable": False,
    }
