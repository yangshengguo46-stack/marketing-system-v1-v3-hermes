"""DESK-08 canonical desktop packaging and honest offline gate tests."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_offline_launch import (  # noqa: E402
    check_executable,
    check_file,
    verify_offline_runtime,
    verify_packaged_app,
)


def _write_native_app(root: Path) -> Path:
    app = root / "mac-arm64" / "Marketing OS.app"
    resources = app / "Contents" / "Resources"
    resources.mkdir(parents=True)
    binary = app / "Contents" / "MacOS" / "Marketing OS"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(binary, stat.S_IRWXU)
    (resources / "app.asar").write_bytes(b"native-desktop")
    (resources / "install-stamp.json").write_text(
        json.dumps({"commit": "a" * 40, "branch": "codex/marketing-os-runtime"}),
        encoding="utf-8",
    )
    node_pty = resources / "native-deps" / "node-pty"
    node_pty.mkdir(parents=True)
    (node_pty / "package.json").write_text("{}", encoding="utf-8")
    return app


def test_file_and_executable_helpers(tmp_path):
    target = tmp_path / "tool"
    target.write_text("#!/bin/sh\n", encoding="utf-8")
    assert check_file(target, "tool") is True
    assert check_executable(target, "tool") is False
    os.chmod(target, stat.S_IRWXU)
    assert check_executable(target, "tool") is True


def test_native_desktop_structure_passes_without_claiming_offline(tmp_path):
    _write_native_app(tmp_path)
    assert verify_packaged_app(tmp_path) == []


def test_retired_outer_desktop_payload_is_rejected(tmp_path):
    app = _write_native_app(tmp_path)
    old_server = app / "Contents" / "Resources" / "engine" / "marketing-os" / "server.py"
    old_server.parent.mkdir(parents=True)
    old_server.write_text("# retired", encoding="utf-8")
    errors = verify_packaged_app(tmp_path)
    assert any("retired outer desktop resource" in error for error in errors)


def test_thin_installer_does_not_pass_offline_first_launch(tmp_path):
    app = _write_native_app(tmp_path)
    errors = verify_offline_runtime(app)
    assert any("network bootstrap" in error for error in errors)
    assert any("embedded Python" in error for error in errors)


def test_embedded_runtime_contract_can_pass(tmp_path):
    app = _write_native_app(tmp_path)
    runtime = app / "Contents" / "Resources" / "marketing-os-runtime"
    python = runtime / "python" / "bin" / "python3"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(python, stat.S_IRWXU)
    (runtime / "runtime-manifest.json").write_text(
        json.dumps({"productTree": "b" * 40}), encoding="utf-8"
    )
    assert verify_offline_runtime(app) == []


def test_root_build_and_dev_delegate_to_the_canonical_desktop():
    root_package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    scripts = root_package["scripts"]
    assert "main" not in root_package
    assert "build" not in root_package
    assert "runtime/hermes-agent/apps/desktop" in scripts["dev"]
    assert "runtime/hermes-agent/apps/desktop" in scripts["build"]
    assert "runtime/hermes-agent/apps/desktop" in scripts["build:mac"]


def test_canonical_desktop_owns_installer_metadata():
    package = json.loads(
        (ROOT / "runtime" / "hermes-agent" / "apps" / "desktop" / "package.json").read_text(
            encoding="utf-8"
        )
    )
    build = package["build"]
    assert build["appId"] == "com.marketing-os.desktop"
    assert build["productName"] == "Marketing OS"
    assert {item["to"] for item in build["extraResources"]} >= {
        "install-stamp.json",
        "native-deps",
    }
