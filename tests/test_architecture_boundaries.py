"""Regression tests for the 2026-06-29 rebuild boundaries."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_root_commands_only_launch_and_build_the_hermes_native_desktop():
    """The frozen React/Electron shell must never remain the default product."""
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    scripts = package["scripts"]
    desktop_prefix = "npm --prefix runtime/hermes-agent/apps/desktop run "

    assert "main" not in package
    assert "build" not in package
    assert scripts["dev"] == f"{desktop_prefix}dev"
    assert scripts["dev:web"] == f"{desktop_prefix}dev:renderer"
    assert scripts["dev:electron"] == f"{desktop_prefix}dev:electron"
    assert scripts["build"] == f"{desktop_prefix}build"
    assert scripts["build:mac"] == f"{desktop_prefix}dist:mac"
    assert scripts["build:win"] == f"{desktop_prefix}dist:win"
    assert scripts["preview"] == f"{desktop_prefix}preview"
    assert "build:backend" not in scripts
    assert "prepare:mcp-runtime" not in scripts


def test_legacy_business_tools_namespace_is_removed():
    assert not (ROOT / "engine" / "marketing-os" / "tools").exists()
    assert (ROOT / "engine" / "marketing-os" / "marketing_tools").is_dir()
    assert not (ROOT / "engine" / "marketing-os" / "plugin.yaml").exists()


def test_marketing_engine_cannot_launch_external_collectors():
    production = ROOT / "engine" / "marketing-os"
    forbidden = (
        "chrome-ws",
        "opencli",
        "agent_reach",
        "mediacrawler",
        "XHS_COOKIE",
        "Bitwarden",
        ".agents/skills",
        ".hermes/plugins",
    )
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in production.rglob("*.py")
        if "__pycache__" not in path.parts
    )
    for marker in forbidden:
        assert marker not in sources


def test_electron_owns_contained_platform_sessions():
    source = (ROOT / "electron" / "main.js").read_text(encoding="utf-8")
    assert "persist:marketing-os-platform-" in source
    assert "const loginWindows = new Map()" in source
    assert "defaultSession" not in source
    assert "mode: 'detach'" not in source
    assert "LOGIN_SUCCESS_HOSTS" not in source
    assert "return { action: 'deny' }" in source
    login_source = source.split("// ---- 平台登录：", 1)[1].split("function hermesExecutable", 1)[0]
    assert "new BrowserWindow" in login_source
    assert "show: false" in login_source
    assert "loginWindow.show()" in login_source
    assert "new WebContentsView" not in login_source


def test_platform_sessions_are_account_scoped_end_to_end():
    main = (ROOT / "electron" / "main.js").read_text(encoding="utf-8")
    preload = (ROOT / "electron" / "preload.js").read_text(encoding="utf-8")
    accounts = (ROOT / "src" / "pages" / "Accounts.tsx").read_text(encoding="utf-8")

    assert "persist:marketing-os-platform-${safePlatform}-${safeAccount}" in main
    assert "platformSession(platform)" not in main
    assert "session: platformSession(platform, accountId)" in main
    assert "syncAccountWithSession(account.platform, account.username, account.id)" in main
    assert "clearAccountSession: (platform, accountId)" in preload
    assert "account_id: data.account_id" in accounts
    assert "mOS.clearAccountSession(account.platform, account.id)" in accounts


def test_logged_in_douyin_collection_uses_session_network_before_dom():
    main = (ROOT / "electron" / "main.js").read_text(encoding="utf-8")
    capture = main.split("async function captureDouyinSearchResponses", 1)[1].split(
        "async function scrapeIndustryWithSession", 1,
    )[0]
    scrape = main.split("async function scrapeIndustryWithSession", 1)[1].split(
        "async function syncAccountWithSession", 1,
    )[0]

    assert "Network.responseReceived" in capture
    assert "Network.getResponseBody" in capture
    assert "extractDouyinItemsFromPayload" in capture
    assert "scrapeDouyinCreatorRecommendations(accountId)" in scrape
    assert "await captureDouyinSearchResponses(webContents)" in scrape
    assert scrape.index("scrapeDouyinCreatorRecommendations") < scrape.index("captureDouyinSearchResponses")
    assert scrape.index("captureDouyinSearchResponses") < scrape.index("executeJavaScript")
    assert "douyin_creator_center" in scrape
    assert "electron_session_network" in scrape
    assert "electron_session_dom_fallback" in scrape


def test_mcp_is_primary_for_douyin_trending_and_account_sync_with_explicit_fallback():
    main = (ROOT / "electron" / "main.js").read_text(encoding="utf-8")
    scrape = main.split("async function scrapeIndustryWithSession", 1)[1].split(
        "async function syncAccountWithSession", 1,
    )[0]
    sync = main.split("async function syncAccountWithSession", 1)[1].split(
        "async function publishContentAsset", 1,
    )[0]
    assert "mcp-trending" in scrape
    assert scrape.index("mcp-trending") < scrape.index("scrapeDouyinCreatorRecommendations")
    assert "mcp:trending:fallback" in scrape
    assert "mcp-sync" in sync
    assert sync.index("mcp-sync") < sync.index("withSessionWindow")
    assert "mcp:account-sync:fallback" in sync


def test_backend_recovery_does_not_depend_on_stale_ready_flag():
    main = (ROOT / "electron" / "main.js").read_text(encoding="utf-8")
    recovery = main.split("async function startServerWithRecovery", 1)[1].split("// ---- Lifecycle ----", 1)[0]
    assert "serverRestartPending" in recovery
    assert "&& !serverRestartPending" in recovery
    assert "if (serverReady)" not in recovery


def test_renderer_api_waits_for_backend_readiness():
    main = (ROOT / "electron" / "main.js").read_text(encoding="utf-8")
    preload = (ROOT / "electron" / "preload.js").read_text(encoding="utf-8")
    client = (ROOT / "src" / "api" / "client.ts").read_text(encoding="utf-8")
    handler = main.split("const handleRuntimeApi", 1)[1].split("ipcMain.handle('runtime:api'", 1)[0]
    assert "await waitForBackendReady()" in handler
    assert "ipcMain.handle('runtime:api', handleRuntimeApi)" in main
    # Main keeps a compatibility handler for older packaged renderers, but the
    # current renderer surface must expose only Marketing Agent Runtime names.
    assert "ipcMain.handle('hermes:api', handleRuntimeApi)" in main
    assert "runtimeApi:" in preload
    assert "ipcRenderer.invoke('hermes:api'" not in preload
    assert "mOS.api" not in client
    assert "营销引擎启动超时" in main


def test_agent_runtime_never_shells_out_to_cli():
    source = (ROOT / "engine" / "agent_core" / "hermes_adapter.py").read_text(encoding="utf-8")
    assert "subprocess" not in source
    assert "HERMES_CLI" not in source
    assert "from run_agent import AIAgent" in source


def test_renderer_cannot_supply_capability_or_arguments_to_effect_host():
    preload = (ROOT / "electron" / "preload.js").read_text(encoding="utf-8")
    assert "agent:execute-approved-capability" in preload
    assert "session:scrape-industry" not in preload
    assert "session:sync-account" not in preload

    main = (ROOT / "electron" / "main.js").read_text(encoding="utf-8")
    assert "const capability = approval.capability" in main
    assert "const args = approval.arguments || {}" in main


def test_renderer_syncs_account_by_id_through_runtime_api():
    """Account metric sync must not let renderer provide platform/username."""
    preload = (ROOT / "electron" / "preload.js").read_text(encoding="utf-8")
    main = (ROOT / "electron" / "main.js").read_text(encoding="utf-8")
    accounts = (ROOT / "src" / "pages" / "Accounts.tsx").read_text(encoding="utf-8")

    assert "syncAccountSession" not in preload
    assert "syncAccountSession" not in accounts
    assert "syncAccountMetrics" in accounts
    assert "ipcRenderer.invoke('account:sync'" in preload
    assert "async function syncAccountById" in main
    assert "syncAccountWithSession(account.platform, account.username || account.label || '', account.id)" in main
    assert "mcp-sync" in main
    assert "session:sync-account" in main  # compatibility handler, not renderer-exposed


def test_playwright_mcp_supply_chain_pinned():
    """@playwright/mcp must be pinned exactly, no npx/latest in package.json."""
    pkg_json = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    dep = pkg_json.get("dependencies", {}).get("@playwright/mcp")
    assert dep is not None, "@playwright/mcp missing from package.json dependencies"
    assert dep == "0.0.77", f"@playwright/mcp version must be '0.0.77', got '{dep}'"
    assert not any(c in dep for c in "^~><*x"), f"version not pinned: {dep}"

    lockfile = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
    lock_entry = lockfile.get("packages", {}).get("node_modules/@playwright/mcp", {})
    assert lock_entry.get("version") == "0.0.77", "lockfile version mismatch"
    assert lock_entry.get("license") == "Apache-2.0", "license mismatch"
    assert lock_entry.get("integrity", "").startswith("sha512-"), "missing integrity"
    assert "registry.npmjs.org" in lock_entry.get("resolved", ""), "unexpected registry"

    scripts_raw = json.dumps(pkg_json.get("scripts", {}))
    assert "npx" not in scripts_raw, "npx found in scripts"
    assert "latest" not in scripts_raw, "latest found in scripts"

    cli_bin = ROOT / "node_modules" / ".bin" / "playwright-mcp"
    assert cli_bin.exists(), "playwright-mcp CLI binary missing"

    assert (ROOT / "node_modules" / "@playwright" / "mcp" / "cli.js").exists(), \
        "playwright-mcp cli.js missing"

    import os
    import subprocess

    result = subprocess.run(
        [str(cli_bin.resolve()), "--version"],
        capture_output=True, text=True, timeout=15,
        env={**os.environ, "NODE_OPTIONS": ""},
    )
    assert "0.0.77" in result.stdout, f"CLI --version mismatch: {result.stdout}"
