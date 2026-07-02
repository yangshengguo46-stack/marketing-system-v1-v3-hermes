"""MCP-12: Network proxy configuration for MCP subprocesses.

MCP child processes inherit or explicitly configure the system proxy.
Distinguishes between direct-connect failures, proxy errors, DNS,
and platform rate-limiting.
"""

from __future__ import annotations

import os
from typing import Any


def proxy_env() -> dict[str, str]:
    """Return proxy-related env vars that should be inherited by MCP subprocesses."""
    env: dict[str, str] = {}
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
                 "http_proxy", "https_proxy", "no_proxy"):
        val = os.environ.get(key)
        if val:
            env[key] = val
    return env


def classify_network_error(error_message: str) -> str:
    """Categorize a network error for user-friendly reporting."""
    msg = str(error_message).lower()
    if "proxy" in msg or "tunnel" in msg:
        return "proxy_error"
    if "dns" in msg or "getaddrinfo" in msg or "name resolution" in msg:
        return "dns_error"
    if "503" in msg or "service unavailable" in msg:
        return "upstream_503"
    if "429" in msg or "rate limit" in msg:
        return "rate_limited"
    if "connection refused" in msg or "econnrefused" in msg:
        return "connection_refused"
    if "connection reset" in msg:
        return "connection_reset"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "certificate" in msg or "ssl" in msg or "tls" in msg:
        return "tls_error"
    return "unknown_network_error"
