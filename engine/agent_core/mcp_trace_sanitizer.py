"""MCP-11: Trace sanitization and debug guard.

Debug traces must be explicitly enabled, and all captured content
is stripped of secrets before landing on disk or in logs.
"""

from __future__ import annotations

import os
import re
from typing import Any

_TRACE_ENABLED = os.environ.get("MARKETING_OS_MCP_TRACE") == "1"

# Patterns to redact from any captured content
_SANITIZE_PATTERNS = [
    (re.compile(r"(?i)\b(cookie|set-cookie)\s*[:=]\s*[^\n;]+"), r"\1=[REDACTED]"),
    (re.compile(r"(?i)\b(authorization)\s*[:=]\s*[^\n]+"), r"\1=[REDACTED]"),
    (re.compile(r"(?i)\b(access_token|refresh_token)\s*[:=]\s*[^\n]+"), r"\1=[REDACTED]"),
    (re.compile(r"\b(1[3-9]\d{9})\b"), "[PHONE_REDACTED]"),           # 中国手机号
    (re.compile(r"\b\d{6}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dxX]\b"),
     "[ID_REDACTED]"),                                                    # 中国身份证
    (re.compile(r'(?i)(sk-[A-Za-z0-9_-]{16,})'), "[API_KEY_REDACTED]"),
    (re.compile(r'(eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+)'), "[JWT_REDACTED]"),
]

_MAX_LOG_LINE = 2000
_MAX_LOG_FILE_BYTES = 10 * 1024 * 1024


def trace_enabled() -> bool:
    return _TRACE_ENABLED


def sanitize_line(line: str) -> str:
    line = line[: _MAX_LOG_LINE]
    for pattern, replacement in _SANITIZE_PATTERNS:
        line = pattern.sub(replacement, line)
    return line


def sanitize_snapshot_content(snapshot: str) -> str:
    """Sanitize a browser snapshot (accessibility tree text)."""
    if not snapshot:
        return ""
    result = snapshot[:100_000]
    for pattern, replacement in _SANITIZE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result
