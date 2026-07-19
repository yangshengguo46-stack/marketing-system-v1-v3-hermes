"""Resolve the single Marketing OS data root shared by every native surface."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from hermes_constants import get_hermes_home


@dataclass(frozen=True)
class MarketingDataPaths:
    user_data: Path
    config_dir: Path
    agent_db: Path

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "MarketingDataPaths":
        values = os.environ if env is None else env
        hermes_home_value = str(values.get("HERMES_HOME") or "").strip()
        hermes_home = (
            Path(hermes_home_value).expanduser()
            if hermes_home_value
            else get_hermes_home()
        )
        user_data_value = str(values.get("MARKETING_OS_USER_DATA") or "").strip()
        user_data = (
            Path(user_data_value).expanduser()
            if user_data_value
            else hermes_home
        )
        config_value = str(values.get("MARKETING_OS_CONFIG_DIR") or "").strip()
        db_value = str(values.get("MARKETING_OS_AGENT_DB") or "").strip()

        return cls(
            user_data=user_data,
            config_dir=Path(config_value).expanduser() if config_value else user_data / "config",
            agent_db=Path(db_value).expanduser() if db_value else hermes_home / "state.db",
        )
