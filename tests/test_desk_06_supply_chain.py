"""DESK-06: Dependency supply chain audit tests."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from dependency_audit import (
    parse_requirements,
    parse_package_lock,
    check_pinned_versions,
    get_hermes_commit,
    generate_sbom,
)


class TestRequirementsTxt:
    def test_file_exists(self):
        assert (PROJECT_ROOT / "backend" / "requirements.txt").exists()

    def test_all_pinned_with_exact_version(self):
        deps = parse_requirements(PROJECT_ROOT / "backend" / "requirements.txt")
        assert len(deps) >= 5
        for dep in deps:
            assert dep["operator"] == "==", f"{dep['name']} not pinned with =="

    def test_mcp_pinned_at_126(self):
        deps = parse_requirements(PROJECT_ROOT / "backend" / "requirements.txt")
        mcp = [d for d in deps if d["name"] == "mcp"]
        assert len(mcp) == 1
        assert mcp[0]["version"] == "1.26.0"

    def test_no_floating_versions(self):
        deps = parse_requirements(PROJECT_ROOT / "backend" / "requirements.txt")
        warnings = check_pinned_versions(deps)
        assert warnings == []


class TestPackageLock:
    def test_file_exists(self):
        assert (PROJECT_ROOT / "package-lock.json").exists()

    def test_has_packages(self):
        deps = parse_package_lock(PROJECT_ROOT / "package-lock.json")
        assert len(deps) >= 50

    def test_playwright_mcp_pinned(self):
        data = json.loads((PROJECT_ROOT / "package-lock.json").read_text())
        packages = data.get("packages", {})
        mcp_key = "node_modules/@playwright/mcp"
        assert mcp_key in packages
        assert packages[mcp_key]["version"] == "0.0.77"

    def test_integrity_hashes_present(self):
        deps = parse_package_lock(PROJECT_ROOT / "package-lock.json")
        with_integrity = [d for d in deps if d.get("integrity")]
        # Most packages should have integrity hashes
        assert len(with_integrity) > len(deps) * 0.5


class TestHermesCommit:
    def test_hermes_dir_exists(self):
        assert (PROJECT_ROOT / "runtime" / "hermes-agent").exists()

    def test_hermes_commit_is_sha(self):
        info = get_hermes_commit(PROJECT_ROOT / "runtime" / "hermes-agent")
        assert "commit" in info
        commit = info["commit"]
        assert re.match(r"^[0-9a-f]{40}$", commit), f"not a valid SHA: {commit}"


class TestPinnedVersions:
    def test_playwright_mcp_in_package_json(self):
        pkg = json.loads((PROJECT_ROOT / "package.json").read_text())
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        assert deps.get("@playwright/mcp") == "0.0.77"

    def test_electron_version_pinned(self):
        pkg = json.loads((PROJECT_ROOT / "package.json").read_text())
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        assert "electron" in deps
        # Should not use "latest" or "*"
        assert deps["electron"] != "latest"
        assert deps["electron"] != "*"


class TestSbomGeneration:
    def test_generate_sbom(self, tmp_path):
        sbom = generate_sbom(tmp_path)
        assert "sbomVersion" in sbom
        assert "components" in sbom
        assert "python" in sbom["components"]
        assert "npm" in sbom["components"]
        assert "pinnedVersions" in sbom

    def test_sbom_file_written(self, tmp_path):
        generate_sbom(tmp_path)
        assert (tmp_path / "sbom.json").exists()
        assert (tmp_path / "license-inventory.json").exists()

    def test_sbom_contains_hermes(self, tmp_path):
        sbom = generate_sbom(tmp_path)
        hermes = sbom["components"].get("hermes-agent", {})
        assert "commit" in hermes

    def test_sbom_warnings_empty(self, tmp_path):
        sbom = generate_sbom(tmp_path)
        assert sbom["warnings"] == []


class TestLicenseInventory:
    def test_license_inventory_generated(self, tmp_path):
        generate_sbom(tmp_path)
        licenses = json.loads((tmp_path / "license-inventory.json").read_text())
        assert "python" in licenses
        assert "npm" in licenses

    def test_python_licenses_present(self, tmp_path):
        generate_sbom(tmp_path)
        licenses = json.loads((tmp_path / "license-inventory.json").read_text())
        # At least some Python packages should have license info
        assert len(licenses["python"]) >= 3


class TestBuildConfigPinned:
    def test_build_backend_checks_mcp_version(self):
        content = (PROJECT_ROOT / "scripts" / "build-backend.mjs").read_text()
        assert "1.26.0" in content
        assert "mcp" in content

    def test_prepare_mcp_runtime_uses_pinned(self):
        content = (PROJECT_ROOT / "scripts" / "prepare-mcp-runtime.mjs").read_text()
        assert "@playwright/mcp" in content
        assert "playwright" in content
