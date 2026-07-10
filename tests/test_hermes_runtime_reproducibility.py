"""Reproducible Hermes fork boundary and patch-series tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / "runtime" / "hermes-runtime.lock.json").read_text())


def _verifier_module():
    path = ROOT / "scripts" / "verify-hermes-runtime.py"
    spec = importlib.util.spec_from_file_location("verify_hermes_runtime", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lock_patch_series_is_complete_and_checksummed():
    assert LOCK["repository"] == "https://github.com/NousResearch/hermes-agent.git"
    assert re.fullmatch(r"[0-9a-f]{40}", LOCK["baseline_commit"])
    assert re.fullmatch(r"[0-9a-f]{40}", LOCK["product_tree"])
    assert LOCK["patches"]
    for item in LOCK["patches"]:
        patch = ROOT / "runtime" / item["file"]
        assert patch.is_file()
        assert hashlib.sha256(patch.read_bytes()).hexdigest() == item["sha256"]


def test_bootstrap_uses_the_locked_revision_and_refuses_dirty_overwrite():
    script = (ROOT / "scripts" / "bootstrap-hermes-runtime.sh").read_text()
    assert f'HERMES_BASELINE="{LOCK["baseline_commit"]}"' in script
    assert f'HERMES_PRODUCT_TREE="{LOCK["product_tree"]}"' in script
    assert "git clone --filter=blob:none --no-checkout" in script
    assert "status --porcelain" in script
    assert "refusing to overwrite" in script
    assert "git -C \"$HERMES_SOURCE\" am" in script


def test_current_nested_checkout_matches_product_tree_and_is_clean():
    verifier = _verifier_module()
    result = verifier.verify(ROOT / "runtime" / "hermes-agent")
    assert result["status"] == "ok", result["errors"]
    assert result["source"]["tree"] == LOCK["product_tree"]
    assert result["source"]["dirty"] is False


def test_patch_series_reconstructs_product_tree_from_baseline(tmp_path):
    source = ROOT / "runtime" / "hermes-agent"
    rebuilt = tmp_path / "hermes-agent"
    subprocess.run(
        ["git", "clone", "--quiet", "--no-checkout", "--shared", str(source), str(rebuilt)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(rebuilt), "checkout", "--quiet", "--detach", LOCK["baseline_commit"]],
        check=True,
    )
    patches = [str(ROOT / "runtime" / item["file"]) for item in LOCK["patches"]]
    subprocess.run(
        ["git", "-C", str(rebuilt), "am", "--quiet", "--committer-date-is-author-date", *patches],
        check=True,
    )
    tree = subprocess.run(
        ["git", "-C", str(rebuilt), "rev-parse", "HEAD^{tree}"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert tree == LOCK["product_tree"]
    assert subprocess.run(
        ["git", "-C", str(rebuilt), "status", "--porcelain"],
        check=True, capture_output=True, text=True,
    ).stdout == ""


def test_verifier_can_validate_patch_contract_without_checkout(tmp_path):
    verifier = _verifier_module()
    result = verifier.verify(tmp_path / "missing", require_source=False)
    assert result["status"] == "ok"
    assert result["source"] == {"present": False}
