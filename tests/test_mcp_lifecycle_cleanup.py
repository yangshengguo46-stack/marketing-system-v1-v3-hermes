"""MCP-10: profile deletion, stale lock recovery, and traversal guards."""

import json
import os

import pytest

from agent_core.mcp_lifecycle_cleanup import delete_account_profile, recover_stale_locks
from agent_core.mcp_process_manager import MCPManagerError


ACCT_A = "acct_16646b260407"
ACCT_B = "acct_ffffffffffff"


def _make_account_dirs(root, platform, account_id):
    paths = [
        root / "mcp-browser" / platform / account_id,
        root / "mcp-runtime" / "locks" / platform / account_id,
        root / "mcp-runtime" / "logs" / platform / account_id,
    ]
    for path in paths:
        path.mkdir(parents=True)
        (path / "marker.txt").write_text("data", encoding="utf-8")
    return paths


def test_delete_removes_profile_lock_and_log_for_one_account_only(tmp_path):
    a_paths = _make_account_dirs(tmp_path, "douyin", ACCT_A)
    b_paths = _make_account_dirs(tmp_path, "douyin", ACCT_B)

    result = delete_account_profile(tmp_path, "douyin", ACCT_A)

    assert result["errors"] == []
    assert len(result["actions"]) == 3
    assert all(not path.exists() for path in a_paths)
    assert all(path.exists() for path in b_paths)


def test_dry_run_reports_actions_without_deleting(tmp_path):
    paths = _make_account_dirs(tmp_path, "douyin", ACCT_A)

    result = delete_account_profile(tmp_path, "douyin", ACCT_A, dry_run=True)

    assert result["dry_run"] is True
    assert len(result["actions"]) == 3
    assert all(action.startswith("would remove") for action in result["actions"])
    assert all(path.exists() for path in paths)


def test_missing_directories_are_skipped_without_error(tmp_path):
    result = delete_account_profile(tmp_path, "douyin", ACCT_A)
    assert result["actions"] == []
    assert result["errors"] == []


@pytest.mark.parametrize("platform,account_id", [
    ("../..", ACCT_A),
    ("douyin/../..", ACCT_A),
    ("douyin", "../../outside"),
    ("douyin", "acct_XYZ"),
    ("douyin", "not_an_account"),
    ("", ACCT_A),
    ("douyin", ""),
])
def test_traversal_and_malformed_ids_are_rejected(tmp_path, platform, account_id):
    outside = tmp_path.parent / "outside-victim"
    outside.mkdir(exist_ok=True)
    with pytest.raises(MCPManagerError):
        delete_account_profile(tmp_path, platform, account_id)
    assert outside.exists()


def _write_lock(locks_root, platform, account_id, payload):
    lock_dir = locks_root / platform
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = lock_dir / f"{account_id}.lock"
    lock_file.write_text(payload, encoding="utf-8")
    return lock_file


def test_recover_removes_dead_pid_lock_and_keeps_live_pid_lock(tmp_path):
    dead_pid = 4194304 - 1  # near pid_max, extremely unlikely to be alive
    dead = _write_lock(tmp_path, "douyin", ACCT_A, json.dumps({"pid": dead_pid}))
    alive = _write_lock(tmp_path, "douyin", ACCT_B, json.dumps({"pid": os.getpid()}))

    removed = recover_stale_locks(tmp_path)

    assert str(dead) in removed
    assert not dead.exists()
    assert alive.exists()


def test_recover_removes_corrupt_lock_files(tmp_path):
    corrupt = _write_lock(tmp_path, "douyin", ACCT_A, "{not-json")

    removed = recover_stale_locks(tmp_path)

    assert str(corrupt) in removed
    assert not corrupt.exists()


def test_recover_supports_manager_pid_field(tmp_path):
    alive = _write_lock(
        tmp_path, "douyin", ACCT_A, json.dumps({"manager_pid": os.getpid()})
    )

    removed = recover_stale_locks(tmp_path)

    assert removed == []
    assert alive.exists()


def test_recover_on_missing_root_returns_empty(tmp_path):
    assert recover_stale_locks(tmp_path / "does-not-exist") == []
