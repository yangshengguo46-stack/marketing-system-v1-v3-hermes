#!/usr/bin/env python3
"""DESK-03: Secret scanner — verify no raw secrets leak into DB, events, logs, or traces.

Scans:
1. SQLite DB tables (agent_tasks, task_events, memory_candidates, etc.)
2. JSON config files (accounts.json, trending-cache.json, etc.)
3. Log files (*.log under userData)
4. MCP trace files (if trace enabled)

Exit code 0 = clean, 1 = secrets found, 2 = error.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

# --- Secret patterns ---

# High-confidence: actual secret values (not just key names)
SECRET_VALUE_PATTERNS = [
    # DeepSeek / OpenAI API keys: sk- followed by 16+ alphanumeric chars
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "api_key_pattern"),
    # JWT tokens: eyJxxx.yyy.zzz
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+\b"), "jwt_pattern"),
    # Long hex tokens (64+ chars, likely API tokens)
    (re.compile(r"\b[0-9a-f]{64,}\b"), "hex_token_pattern"),
    # Bearer tokens
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_-]{20,}\b"), "bearer_token_pattern"),
]

# Key-name patterns: detect "api_key": "actual_value" or password=actual_value
SECRET_KEY_PATTERN = re.compile(
    r'(?i)["\']?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|'
    r'cookie|set[_-]?cookie|authorization|bearer)["\']?\s*[:=]\s*["\']?'
    r'([^"\'}\s,;]{4,})["\']?',
)

# Patterns that are NOT secrets (false positive guards)
SAFE_VALUES = {
    "[redacted]", "[redacted]", "[api_key_redacted]", "[jwt_redacted]",
    "[phone_redacted]", "[id_redacted]", "redacted", "null", "none",
    "true", "false", "", "0", "1",
}

# Phone numbers (China) — flagged but lower severity
PHONE_PATTERN = re.compile(r"\b1[3-9]\d{9}\b")

# ID card numbers (China) — flagged
ID_CARD_PATTERN = re.compile(r"\b\d{6}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dxX]\b")


def is_safe_value(value: str) -> bool:
    """Check if a value is clearly a redaction marker or safe placeholder."""
    lower = value.strip().lower()
    if lower in SAFE_VALUES:
        return True
    if lower.startswith("[") and lower.endswith("redacted]"):
        return True
    if len(value) < 4:
        return True
    return False


def scan_text(text: str, source: str) -> list[dict[str, Any]]:
    """Scan a text string for secrets. Returns list of findings."""
    findings: list[dict[str, Any]] = []

    # Check high-confidence patterns
    for pattern, name in SECRET_VALUE_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(0)
            if is_safe_value(value):
                continue
            findings.append({
                "source": source,
                "type": name,
                "value_preview": value[:8] + "..." + value[-4:] if len(value) > 12 else value[:4] + "...",
                "position": match.start(),
            })

    # Check key=value patterns
    for match in SECRET_KEY_PATTERN.finditer(text):
        value = match.group(1)
        if is_safe_value(value):
            continue
        # Extract key name safely
        raw = match.group(0)
        key_name = raw.split("=")[0].split(":")[0].strip().strip("'").strip('"').strip()
        findings.append({
            "source": source,
            "type": f"secret_key_value ({key_name})",
            "value_preview": value[:8] + "..." + value[-4:] if len(value) > 12 else value[:4] + "...",
            "position": match.start(),
        })

    # Check phone numbers (medium severity)
    for match in PHONE_PATTERN.finditer(text):
        findings.append({
            "source": source,
            "type": "phone_number",
            "value_preview": match.group(0)[:3] + "****" + match.group(0)[-4:],
            "position": match.start(),
            "severity": "medium",
        })

    # Check ID card numbers (high severity)
    for match in ID_CARD_PATTERN.finditer(text):
        findings.append({
            "source": source,
            "type": "id_card_number",
            "value_preview": match.group(0)[:6] + "********" + match.group(0)[-4:],
            "position": match.start(),
            "severity": "high",
        })

    return findings


def scan_sqlite(db_path: Path) -> list[dict[str, Any]]:
    """Scan all text columns in all tables of a SQLite database."""
    findings: list[dict[str, Any]] = []
    if not db_path.exists():
        return findings

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        for table in tables:
            table_name = table["name"]
            # Skip internal SQLite tables
            if table_name.startswith("sqlite_"):
                continue
            try:
                columns = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
                text_cols = [col["name"] for col in columns if col["type"].upper() in ("TEXT", "BLOB")]
                if not text_cols:
                    continue
                rows = conn.execute(f"SELECT rowid as _rowid, {', '.join(text_cols)} FROM {table_name}").fetchall()
                for row in rows:
                    for col in text_cols:
                        value = row[col]
                        if value is None:
                            continue
                        if isinstance(value, bytes):
                            try:
                                value = value.decode("utf-8", errors="replace")
                            except Exception:
                                continue
                        if not isinstance(value, str):
                            continue
                        source = f"{db_path.name}:{table_name}:row{row['_rowid']}:{col}"
                        findings.extend(scan_text(value, source))
            except sqlite3.OperationalError:
                continue
    finally:
        conn.close()

    return findings


def scan_json_file(file_path: Path) -> list[dict[str, Any]]:
    """Scan a JSON file for secrets by serializing and pattern matching."""
    if not file_path.exists():
        return []
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return scan_text(text, str(file_path.name))


def scan_log_file(file_path: Path) -> list[dict[str, Any]]:
    """Scan a log file for secrets."""
    if not file_path.exists():
        return []
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return scan_text(text, str(file_path.name))


def scan_directory(dir_path: Path, extensions: tuple[str, ...]) -> list[dict[str, Any]]:
    """Scan all files with given extensions in a directory."""
    findings: list[dict[str, Any]] = []
    if not dir_path.exists():
        return findings
    for file_path in dir_path.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix in extensions:
            findings.extend(scan_json_file(file_path))
    return findings


def main() -> int:
    """Run the secret scanner. Exit 0 = clean, 1 = secrets found, 2 = error."""
    # Determine user data directory
    home = Path(os.environ.get("HOME", "~")).expanduser()
    user_data = Path(os.environ.get(
        "MARKETING_OS_USER_DATA",
        str(home / "Library" / "Application Support" / "marketing-os-desktop"),
    ))

    if not user_data.exists():
        print(f"[secret-scanner] user data directory not found: {user_data}")
        return 2

    all_findings: list[dict[str, Any]] = []

    # 1. Scan SQLite databases
    db_paths = [
        user_data / "agent-runtime" / "agent_core.db",
        user_data / "agent-runtime" / "hermes-state.db",
    ]
    for db_path in db_paths:
        if db_path.exists():
            print(f"[secret-scanner] scanning DB: {db_path.name}")
            findings = scan_sqlite(db_path)
            all_findings.extend(findings)

    # 2. Scan JSON config files
    config_dir = user_data / "config"
    if config_dir.exists():
        print(f"[secret-scanner] scanning config: {config_dir}")
        all_findings.extend(scan_directory(config_dir, (".json",)))

    # Also scan top-level config files
    for json_file in user_data.glob("*.json"):
        print(f"[secret-scanner] scanning: {json_file.name}")
        all_findings.extend(scan_json_file(json_file))

    # 3. Scan log files
    log_dirs = [
        user_data / "logs",
        user_data / "agent-runtime" / "logs",
        user_data / "mcp-runtime" / "logs",
    ]
    for log_dir in log_dirs:
        if log_dir.exists():
            print(f"[secret-scanner] scanning logs: {log_dir}")
            for log_file in log_dir.rglob("*.log"):
                all_findings.extend(scan_log_file(log_file))

    # 4. Scan MCP trace files
    trace_dir = user_data / "mcp-runtime" / "traces"
    if trace_dir.exists():
        print(f"[secret-scanner] scanning traces: {trace_dir}")
        all_findings.extend(scan_directory(trace_dir, (".txt", ".json", ".log")))

    # 5. Scan providers.env (should exist but not contain raw secrets in DB)
    secrets_file = user_data / "secrets" / "providers.env"
    if secrets_file.exists():
        print(f"[secret-scanner] checking secrets file exists: {secrets_file.name}")
        # The secrets file itself is expected to contain API keys — that's OK.
        # We just verify it has correct permissions.
        stat = secrets_file.stat()
        perms = stat.st_mode & 0o777
        if perms & 0o077:
            all_findings.append({
                "source": "providers.env",
                "type": "insecure_file_permissions",
                "value_preview": f"perms={oct(perms)} (should be 0o600)",
                "severity": "high",
            })

    # Report
    if not all_findings:
        print("[secret-scanner] ✅ No secrets found in DB, events, logs, or traces.")
        return 0

    # Deduplicate by source+type+value_preview
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for f in all_findings:
        key = f"{f['source']}:{f['type']}:{f['value_preview']}"
        if key not in seen:
            seen.add(key)
            unique.append(f)

    high = [f for f in unique if f.get("severity", "high") == "high"]
    medium = [f for f in unique if f.get("severity") == "medium"]

    print(f"[secret-scanner] ❌ Found {len(unique)} potential secret(s): {len(high)} high, {len(medium)} medium")
    for f in unique:
        severity = f.get("severity", "high")
        print(f"  [{severity.upper()}] {f['source']}: {f['type']} → {f['value_preview']}")

    return 1


if __name__ == "__main__":
    sys.exit(main())
