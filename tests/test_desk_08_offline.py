"""DESK-08: Offline launch verification tests.

Validates the offline launch checker and build pipeline structure.
Does NOT require an actual build — tests the verification logic.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from verify_offline_launch import (
    check_file,
    check_executable,
    verify_packaged_app,
    verify_backend_health,
)


class TestCheckFile:
    def test_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert check_file(f, "test file") is True

    def test_missing_file(self, tmp_path):
        f = tmp_path / "nonexistent.txt"
        assert check_file(f, "missing file") is False


class TestCheckExecutable:
    def test_executable_file(self, tmp_path):
        f = tmp_path / "run.sh"
        f.write_text("#!/bin/bash\nexit 0\n")
        os.chmod(f, stat.S_IRWXU)
        assert check_executable(f, "executable script") is True

    def test_non_executable_file(self, tmp_path):
        f = tmp_path / "notexec.sh"
        f.write_text("hello")
        os.chmod(f, stat.S_IRUSR | stat.S_IWUSR)
        assert check_executable(f, "non-executable script") is False

    def test_missing_file(self, tmp_path):
        f = tmp_path / "nonexistent"
        assert check_executable(f, "missing") is False


class TestVerifyPackagedApp:
    def test_valid_app_structure(self, tmp_path):
        app = tmp_path / "MarketingOS.app"
        resources = app / "Contents" / "Resources"
        resources.mkdir(parents=True)

        # Backend binary
        backend_bin = resources / "backend" / "marketing-os-server"
        backend_bin.parent.mkdir(parents=True)
        backend_bin.write_text("#!/bin/bash\nexit 0\n")
        os.chmod(backend_bin, stat.S_IRWXU)

        # MCP runtime
        mcp_runtime = resources / "mcp-runtime"
        mcp_runtime.mkdir(parents=True)
        manifest = {
            "mcp": "0.0.77",
            "playwright": "1.62.0-alpha-2026-06-29",
            "browserRevision": "chromium-1229",
            "executableRelativePath": "browsers/chromium-1229/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
        }
        (mcp_runtime / "runtime-manifest.json").write_text(json.dumps(manifest))

        # Chromium binary
        chromium = mcp_runtime / "browsers" / "chromium-1229" / "chrome-mac" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"
        chromium.parent.mkdir(parents=True)
        chromium.write_text("#!/bin/bash\nexit 0\n")
        os.chmod(chromium, stat.S_IRWXU)

        # MCP CLI
        mcp_cli = mcp_runtime / "node_modules" / "@playwright" / "mcp" / "cli.js"
        mcp_cli.parent.mkdir(parents=True)
        mcp_cli.write_text("// cli")

        # Engine
        engine = resources / "engine" / "marketing-os"
        engine.mkdir(parents=True)
        (engine / "server.py").write_text("# server")

        errors = verify_packaged_app(tmp_path)
        assert errors == []

    def test_missing_backend(self, tmp_path):
        app = tmp_path / "TestApp.app"
        resources = app / "Contents" / "Resources"
        resources.mkdir(parents=True)
        # No backend binary
        errors = verify_packaged_app(tmp_path)
        assert any("backend" in e for e in errors)

    def test_missing_chromium(self, tmp_path):
        app = tmp_path / "TestApp.app"
        resources = app / "Contents" / "Resources"
        resources.mkdir(parents=True)

        backend_bin = resources / "backend" / "marketing-os-server"
        backend_bin.parent.mkdir(parents=True)
        backend_bin.write_text("#!/bin/bash\nexit 0\n")
        os.chmod(backend_bin, stat.S_IRWXU)

        mcp_runtime = resources / "mcp-runtime"
        mcp_runtime.mkdir(parents=True)
        manifest = {
            "mcp": "0.0.77",
            "playwright": "1.62.0",
            "browserRevision": "chromium-1229",
            "executableRelativePath": "browsers/chromium-1229/chrome-mac/Chromium",
        }
        (mcp_runtime / "runtime-manifest.json").write_text(json.dumps(manifest))
        # No actual Chromium binary

        errors = verify_packaged_app(tmp_path)
        assert any("Chromium" in e for e in errors)

    def test_no_app_found(self, tmp_path):
        errors = verify_packaged_app(tmp_path)
        assert any("no .app" in e for e in errors)


class TestVerifyBackendHealth:
    def test_no_server_running(self):
        # Port 1 is reserved and should never respond
        errors = verify_backend_health(port=1, timeout=2)
        assert len(errors) > 0
        assert "health" in errors[0].lower()


class TestBuildConfig:
    def test_package_json_has_build_config(self):
        import json
        pkg = json.loads((Path(__file__).parent.parent / "package.json").read_text())
        assert "build" in pkg
        build = pkg["build"]
        assert build["appId"] == "com.marketing-os.desktop"
        assert "dmg" in build["mac"]["target"]
        assert "zip" in build["mac"]["target"]

    def test_extra_resources_configured(self):
        import json
        pkg = json.loads((Path(__file__).parent.parent / "package.json").read_text())
        resources = pkg["build"]["extraResources"]
        resource_targets = [r.get("to", "") for r in resources]
        assert "backend" in resource_targets
        assert "mcp-runtime" in resource_targets
        assert "engine" in resource_targets

    def test_build_mac_script_exists(self):
        import json
        pkg = json.loads((Path(__file__).parent.parent / "package.json").read_text())
        assert "build:mac" in pkg["scripts"]

    def test_build_backend_script_exists(self):
        assert (Path(__file__).parent.parent / "scripts" / "build-backend.mjs").exists()

    def test_prepare_mcp_runtime_script_exists(self):
        assert (Path(__file__).parent.parent / "scripts" / "prepare-mcp-runtime.mjs").exists()

    def test_build_electron_script_exists(self):
        assert (Path(__file__).parent.parent / "scripts" / "build-electron.mjs").exists()

    def test_verify_offline_launch_script_exists(self):
        assert (Path(__file__).parent.parent / "scripts" / "verify_offline_launch.py").exists()
