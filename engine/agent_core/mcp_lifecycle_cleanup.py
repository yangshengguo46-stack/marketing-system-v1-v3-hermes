"""MCP-10: Account-scoped lifecycle cleanup utilities.

Guarantees for profile deletion, residual process reaping, and
crash lock recovery.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any


def delete_account_profile(
    user_data_root: Path, platform: str, account_id: str,
    *, dry_run: bool = False,
) -> dict[str, Any]:
    """Safely delete one account's browser profile directory.

    Returns actions taken and any errors encountered.
    """
    profile_dir = user_data_root / "mcp-browser" / platform / account_id
    lock_dir = user_data_root / "mcp-runtime" / "locks" / platform / account_id
    log_dir = user_data_root / "mcp-runtime" / "logs" / platform / account_id

    actions: list[str] = []
    errors: list[str] = []

    for label, path in [("profile", profile_dir), ("lock", lock_dir), ("log", log_dir)]:
        if not path.exists():
            continue
        if dry_run:
            actions.append(f"would remove {label}: {path}")
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            actions.append(f"removed {label}: {path}")
        except OSError as e:
            errors.append(f"failed to remove {label} {path}: {e}")

    return {"actions": actions, "errors": errors, "dry_run": dry_run}


def recover_stale_locks(locks_root: Path) -> list[str]:
    """Scan locks directory and remove entries whose PID no longer exists."""
    removed: list[str] = []
    if not locks_root.exists():
        return removed
    for lock_file in list(locks_root.rglob("*.lock")):
        try:
            data = json.loads(lock_file.read_text())
            pid = data.get("pid") or data.get("manager_pid")
            if pid:
                try:
                    os.kill(int(pid), 0)
                    continue  # still alive
                except (ProcessLookupError, OSError):
                    pass
            lock_file.unlink()
            removed.append(str(lock_file))
        except (json.JSONDecodeError, OSError):
            try:
                lock_file.unlink()
                removed.append(str(lock_file))
            except OSError:
                pass
    return removed
