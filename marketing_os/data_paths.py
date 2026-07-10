"""Resolve the single Marketing OS data root shared by every native surface."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class MarketingDataPaths:
    user_data: Path
    config_dir: Path
    agent_db: Path

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "MarketingDataPaths":
        values = os.environ if env is None else env
        user_data_value = str(values.get("MARKETING_OS_USER_DATA") or "").strip()
        user_data = Path(user_data_value).expanduser() if user_data_value else _default_user_data()
        config_value = str(values.get("MARKETING_OS_CONFIG_DIR") or "").strip()
        db_value = str(values.get("MARKETING_OS_AGENT_DB") or "").strip()

        return cls(
            user_data=user_data,
            config_dir=Path(config_value).expanduser() if config_value else user_data / "config",
            agent_db=Path(db_value).expanduser() if db_value else user_data / "agent-runtime" / "agent_core.db",
        )


def _default_user_data() -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "marketing-os-desktop"
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        return Path(local_app_data) / "marketing-os-desktop" if local_app_data else home / "AppData" / "Local" / "marketing-os-desktop"
    xdg_data = os.environ.get("XDG_DATA_HOME")
    return Path(xdg_data) / "marketing-os-desktop" if xdg_data else home / ".local" / "share" / "marketing-os-desktop"
