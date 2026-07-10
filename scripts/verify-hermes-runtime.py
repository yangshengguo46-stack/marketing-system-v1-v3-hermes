#!/usr/bin/env python3
"""Verify the reproducible Hermes source boundary used by Marketing OS.

The nested checkout is intentionally not tracked by the outer repository.
The outer repository instead tracks an upstream baseline plus an ordered,
checksummed patch series.  This verifier prevents a locally dirty or different
Hermes tree from silently entering tests or release builds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "runtime" / "hermes-runtime.lock.json"
DEFAULT_SOURCE = ROOT / "runtime" / "hermes-agent"


def _git(source: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(source), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def verify(source: Path, *, require_source: bool = True) -> dict[str, object]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    errors: list[str] = []
    patches: list[dict[str, str]] = []

    for item in lock.get("patches", []):
        relative = str(item.get("file") or "")
        patch = ROOT / "runtime" / relative
        if not patch.is_file():
            errors.append(f"missing patch: {relative}")
            continue
        digest = hashlib.sha256(patch.read_bytes()).hexdigest()
        expected = str(item.get("sha256") or "")
        if digest != expected:
            errors.append(f"patch checksum mismatch: {relative}")
        patches.append({"file": relative, "sha256": digest})

    source_state: dict[str, object] = {"present": (source / ".git").is_dir()}
    if not source_state["present"]:
        if require_source:
            errors.append(f"Hermes source checkout missing: {source}")
    else:
        try:
            dirty = _git(source, "status", "--porcelain")
            head = _git(source, "rev-parse", "HEAD")
            tree = _git(source, "rev-parse", "HEAD^{tree}")
            source_state.update({"head": head, "tree": tree, "dirty": bool(dirty)})
            if dirty:
                errors.append("Hermes source checkout is dirty")
            if tree != lock.get("product_tree"):
                errors.append(
                    f"Hermes product tree mismatch: {tree} != {lock.get('product_tree')}"
                )
        except (OSError, subprocess.CalledProcessError) as exc:
            errors.append(f"cannot inspect Hermes checkout: {exc}")

    result: dict[str, object] = {
        "status": "ok" if not errors else "error",
        "lock": {
            "repository": lock.get("repository"),
            "baseline_commit": lock.get("baseline_commit"),
            "product_tree": lock.get("product_tree"),
        },
        "patches": patches,
        "source": source_state,
        "errors": errors,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--allow-missing-source", action="store_true")
    args = parser.parse_args()
    result = verify(args.source, require_source=not args.allow_missing_source)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
