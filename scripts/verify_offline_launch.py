#!/usr/bin/env python3
"""Verify the canonical Marketing OS Desktop package and offline delivery gate.

The former checker validated the retired outer Electron/FastAPI package.  The
canonical app now lives in ``runtime/hermes-agent/apps/desktop``.  Structural
packaging and true offline first launch are deliberately separate: a thin app
shell can be structurally valid while still failing the C-end delivery goal.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESKTOP_ROOT = PROJECT_ROOT / "runtime" / "hermes-agent" / "apps" / "desktop"


def check_file(path: Path, description: str) -> bool:
    if path.is_file():
        print(f"  OK {description}: {path.name}")
        return True
    print(f"  MISSING {description}: {path}")
    return False


def check_executable(path: Path, description: str) -> bool:
    if not check_file(path, description):
        return False
    if os.access(path, os.X_OK):
        return True
    print(f"  NOT EXECUTABLE {description}: {path}")
    return False


def _find_marketing_os_app(release_dir: Path) -> Path | None:
    direct = release_dir / "Marketing OS.app"
    if direct.is_dir():
        return direct
    candidates = sorted(release_dir.rglob("Marketing OS.app"))
    return candidates[0] if candidates else None


def verify_packaged_app(release_dir: Path) -> list[str]:
    """Validate the native app shell without pretending runtime is embedded."""
    errors: list[str] = []
    app_path = _find_marketing_os_app(release_dir)
    if app_path is None:
        return ["Marketing OS.app not found in release directory"]

    resources = app_path / "Contents" / "Resources"
    binary = app_path / "Contents" / "MacOS" / "Marketing OS"
    if not check_executable(binary, "Marketing OS executable"):
        errors.append("Marketing OS executable missing or not executable")
    if not check_file(resources / "app.asar", "native desktop app.asar"):
        errors.append("native desktop app.asar missing")

    stamp_path = resources / "install-stamp.json"
    if not check_file(stamp_path, "runtime install stamp"):
        errors.append("runtime install stamp missing")
    else:
        try:
            stamp = json.loads(stamp_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid runtime install stamp: {exc}")
        else:
            if not str(stamp.get("commit") or "").strip():
                errors.append("runtime install stamp has no commit")
            if "branch" not in stamp:
                errors.append("runtime install stamp has no branch")

    native_deps = resources / "native-deps" / "node-pty"
    if not check_file(native_deps / "package.json", "node-pty package metadata"):
        errors.append("node-pty native dependency missing")

    # These resources prove the retired outer UI/FastAPI package was built.
    forbidden = (
        resources / "backend" / "marketing-os-server",
        resources / "engine" / "marketing-os" / "server.py",
        resources / "mcp-runtime" / "runtime-manifest.json",
    )
    for path in forbidden:
        if path.exists():
            errors.append(f"retired outer desktop resource is still packaged: {path.name}")
    return errors


def verify_offline_runtime(app_path: Path) -> list[str]:
    """Require the future self-contained runtime; current thin builds fail here."""
    resources = app_path / "Contents" / "Resources"
    runtime = resources / "marketing-os-runtime"
    manifest = runtime / "runtime-manifest.json"
    python = runtime / "python" / "bin" / "python3"
    errors: list[str] = []
    if not manifest.is_file():
        errors.append(
            "self-contained Marketing OS runtime missing; first launch still depends on "
            "network bootstrap"
        )
    if not python.is_file() or not os.access(python, os.X_OK):
        errors.append("embedded Python runtime missing or not executable")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Marketing OS offline delivery verifier")
    parser.add_argument(
        "--release-dir",
        default=str(DESKTOP_ROOT / "release"),
        help="canonical Hermes-native desktop release directory",
    )
    parser.add_argument(
        "--structure-only",
        action="store_true",
        help="validate the app shell but do not claim offline first-launch readiness",
    )
    args = parser.parse_args()
    release_dir = Path(args.release_dir)

    errors = verify_packaged_app(release_dir)
    app_path = _find_marketing_os_app(release_dir)
    if not errors and app_path is not None and not args.structure_only:
        errors.extend(verify_offline_runtime(app_path))

    if errors:
        print("\nFAILED")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("\nPASS")
    if args.structure_only:
        print("  App shell is valid; offline runtime readiness was not asserted.")
    else:
        print("  App shell and self-contained runtime are present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
