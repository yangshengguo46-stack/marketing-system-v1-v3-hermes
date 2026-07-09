"""DESK-01: Process responsibility diagram verification tests.

Validates that the architecture document matches the actual code:
- Health endpoint exists and returns expected shape
- Startup sequence steps are present in code
- Shutdown sequence steps are present in code
- Port allocation matches
- Token generation and storage matches
- IPC allowlist exists
- Crash recovery logic exists
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
MAIN_JS = PROJECT_ROOT / "electron" / "main.js"
SERVER_PY = PROJECT_ROOT / "engine" / "marketing-os" / "server.py"
DIAGRAM_MD = PROJECT_ROOT / "docs" / "architecture" / "process-responsibility.md"


class TestDiagramExists:
    def test_diagram_file_exists(self):
        assert DIAGRAM_MD.exists(), "process-responsibility.md not found"

    def test_diagram_has_process_topology(self):
        content = DIAGRAM_MD.read_text()
        assert "Process Topology" in content
        assert "Electron Main" in content
        assert "Backend Server" in content
        assert "MCP" in content

    def test_diagram_has_startup_sequence(self):
        content = DIAGRAM_MD.read_text()
        assert "Startup Sequence" in content
        assert "startServer" in content
        assert "waitForServer" in content

    def test_diagram_has_shutdown_sequence(self):
        content = DIAGRAM_MD.read_text()
        assert "Shutdown Sequence" in content
        assert "SIGTERM" in content
        assert "stop_all" in content

    def test_diagram_has_health_endpoints(self):
        content = DIAGRAM_MD.read_text()
        assert "Health Endpoints" in content
        assert "/health" in content

    def test_diagram_has_port_allocation(self):
        content = DIAGRAM_MD.read_text()
        assert "Port Allocation" in content
        assert "19519" in content

    def test_diagram_has_crash_recovery(self):
        content = DIAGRAM_MD.read_text()
        assert "Crash Recovery" in content
        assert "Backend crash" in content


class TestHealthEndpoint:
    def test_health_endpoint_defined(self):
        content = SERVER_PY.read_text()
        assert "@app.get('/health')" in content or '@app.get("/health")' in content
        assert "def health" in content

    def test_health_returns_status_ok(self):
        content = SERVER_PY.read_text()
        # Verify the health function returns a dict with "status" and "ok"
        match = re.search(r'def health\(\).*?return\s*\{[^}]*"status"[^}]*"ok"', content, re.DOTALL)
        assert match, "health() must return {'status': 'ok', ...}"


class TestStartupSequence:
    def test_token_generation_exists(self):
        content = MAIN_JS.read_text()
        assert "loadOrCreateApiToken" in content
        assert "randomBytes" in content
        assert "0o600" in content

    def test_port_finding_exists(self):
        content = MAIN_JS.read_text()
        assert "findAvailablePort" in content
        assert "19519" in content

    def test_start_server_exists(self):
        content = MAIN_JS.read_text()
        assert "async function startServer" in content
        assert "waitForServer" in content

    def test_start_server_with_recovery_exists(self):
        content = MAIN_JS.read_text()
        assert "startServerWithRecovery" in content

    def test_app_when_ready_starts_server(self):
        content = MAIN_JS.read_text()
        assert "app.whenReady" in content
        # Verify startServerWithRecovery is called in whenReady
        ready_section = content[content.index("app.whenReady"):]
        assert "startServerWithRecovery" in ready_section[:500]


class TestShutdownSequence:
    def test_before_quit_handler_exists(self):
        content = MAIN_JS.read_text()
        assert "before-quit" in content
        assert "isQuitting" in content

    def test_stop_server_exists(self):
        content = MAIN_JS.read_text()
        assert "function stopServer" in content
        assert "SIGTERM" in content
        assert "SIGKILL" in content

    def test_event_streams_cleaned_on_stop(self):
        content = MAIN_JS.read_text()
        assert "agentEventStreams" in content
        stop_section = content[content.index("function stopServer"):]
        assert "destroy" in stop_section[:300]

    def test_backend_lifespan_shutdown(self):
        content = SERVER_PY.read_text()
        assert "lifespan" in content
        assert "service.shutdown" in content
        assert "stop_all" in content


class TestCrashRecovery:
    def test_crash_monitor_exists(self):
        content = MAIN_JS.read_text()
        assert "serverCrashCount" in content
        assert "serverRestartPending" in content

    def test_crash_restart_delay(self):
        content = MAIN_JS.read_text()
        # 3 second delay before restart
        assert re.search(r"setTimeout.*3000", content) or "3s" in content

    def test_mcp_crash_retry_exists(self):
        content = (PROJECT_ROOT / "engine" / "agent_core" / "mcp_process_manager.py").read_text()
        assert "crash_max_retries" in content or "crash_count" in content
        assert "transport_error" in content


class TestIpcAllowlist:
    def test_allowlist_exists(self):
        content = MAIN_JS.read_text()
        assert "API_ALLOWLIST" in content

    def test_allowlist_has_entries(self):
        content = MAIN_JS.read_text()
        # Count entries (lines with [METHOD, RegExp])
        entries = re.findall(r"\['(GET|POST|PUT|DELETE)',\s*new RegExp", content)
        assert len(entries) >= 30, f"only {len(entries)} allowlist entries found"

    def test_allowlist_includes_agent_endpoints(self):
        content = MAIN_JS.read_text()
        assert "/agent/sessions" in content
        assert "/agent/messages" in content
        assert "/agent/tasks" in content
        assert "/agent/approvals" in content


class TestTokenSecurity:
    def test_token_file_permissions(self):
        content = MAIN_JS.read_text()
        assert "0o700" in content  # directory
        assert "0o600" in content  # file

    def test_api_token_comparison_uses_compare_digest(self):
        content = SERVER_PY.read_text()
        assert "secrets.compare_digest" in content

    def test_origin_check_exists(self):
        content = SERVER_PY.read_text()
        assert "origin" in content
        assert "not allowed" in content or "forbidden" in content.lower() or "403" in content


class testDataPaths:
    def test_config_dir_env_var(self):
        content = SERVER_PY.read_text()
        assert "MARKETING_OS_CONFIG_DIR" in content

    def test_user_data_env_var(self):
        content = SERVER_PY.read_text()
        assert "MARKETING_OS_USER_DATA" in content

    def test_mcp_data_dir_structure(self):
        content = (PROJECT_ROOT / "engine" / "agent_core" / "mcp_process_manager.py").read_text()
        assert "mcp-browser" in content
        assert "mcp-runtime" in content
        assert "locks" in content
        assert "logs" in content
