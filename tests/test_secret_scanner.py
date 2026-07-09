"""DESK-03: Secret scanner tests.

Verifies that the secret scanner correctly detects leaked secrets in
DB, JSON, and log files, and that the existing redaction infrastructure
prevents secrets from landing in the DB in the first place.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from scripts.secret_scanner import (
    scan_text,
    scan_sqlite,
    scan_json_file,
    scan_log_file,
    is_safe_value,
    main,
)


class TestScanText:
    def test_detects_api_key(self):
        findings = scan_text("DEEPSEEK_API_KEY=sk-abcdef1234567890xyz", "test")
        assert len(findings) >= 1
        assert any("api_key" in f["type"] for f in findings)

    def test_detects_jwt(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        findings = scan_text(f"token={jwt}", "test")
        assert any("jwt" in f["type"] for f in findings)

    def test_detects_bearer_token(self):
        findings = scan_text("Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456", "test")
        assert any("bearer" in f["type"].lower() for f in findings)

    def test_detects_phone_number(self):
        findings = scan_text("联系电话：13812345678", "test")
        assert any(f["type"] == "phone_number" for f in findings)

    def test_detects_id_card(self):
        findings = scan_text("身份证：110101199001011234", "test")
        assert any(f["type"] == "id_card_number" for f in findings)

    def test_detects_key_value_secret(self):
        findings = scan_text('{"api_key": "sk-test1234567890abcdef"}', "test")
        assert len(findings) >= 1

    def test_ignores_redacted_values(self):
        findings = scan_text('{"api_key": "[REDACTED]"}', "test")
        assert len(findings) == 0

    def test_ignores_null_and_empty(self):
        findings = scan_text('{"password": null, "token": ""}', "test")
        assert len(findings) == 0

    def test_ignores_short_values(self):
        findings = scan_text('{"key": "abc"}', "test")
        assert len(findings) == 0

    def test_detects_hex_token(self):
        findings = scan_text("token=" + "a" * 64, "test")
        assert any("hex_token" in f["type"] for f in findings)

    def test_clean_text_no_findings(self):
        findings = scan_text("这是一段正常的营销文本，没有秘密", "test")
        assert len(findings) == 0


class TestIsSafeValue:
    def test_redacted_is_safe(self):
        assert is_safe_value("[REDACTED]") is True

    def test_api_key_redacted_is_safe(self):
        assert is_safe_value("[API_KEY_REDACTED]") is True

    def test_short_value_is_safe(self):
        assert is_safe_value("abc") is True

    def test_null_is_safe(self):
        assert is_safe_value("null") is True

    def test_real_secret_not_safe(self):
        assert is_safe_value("sk-abcdef1234567890") is False


class TestScanSqlite:
    def test_detects_secret_in_db(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE events (id TEXT, payload TEXT)")
        conn.execute(
            "INSERT INTO events VALUES (?, ?)",
            ("evt_1", json.dumps({"api_key": "sk-abcdef1234567890xyz"})),
        )
        conn.commit()
        conn.close()

        findings = scan_sqlite(db_path)
        assert len(findings) >= 1

    def test_clean_db_no_findings(self, tmp_path):
        db_path = tmp_path / "clean.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE tasks (id TEXT, objective TEXT)")
        conn.execute("INSERT INTO tasks VALUES (?, ?)", ("task_1", "分析今天的热点"))
        conn.commit()
        conn.close()

        findings = scan_sqlite(db_path)
        assert len(findings) == 0

    def test_redacted_db_no_findings(self, tmp_path):
        db_path = tmp_path / "redacted.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE events (id TEXT, payload TEXT)")
        conn.execute(
            "INSERT INTO events VALUES (?, ?)",
            ("evt_1", json.dumps({"api_key": "[REDACTED]", "cookie": "[REDACTED]"})),
        )
        conn.commit()
        conn.close()

        findings = scan_sqlite(db_path)
        assert len(findings) == 0


class TestScanJsonFile:
    def test_detects_secret_in_json(self, tmp_path):
        f = tmp_path / "config.json"
        f.write_text('{"api_key": "sk-abcdef1234567890xyz", "name": "test"}')
        findings = scan_json_file(f)
        assert len(findings) >= 1

    def test_clean_json_no_findings(self, tmp_path):
        f = tmp_path / "clean.json"
        f.write_text('{"name": "test", "platform": "douyin", "count": 10}')
        findings = scan_json_file(f)
        assert len(findings) == 0


class TestScanLogFile:
    def test_detects_secret_in_log(self, tmp_path):
        f = tmp_path / "app.log"
        f.write_text("Starting server...\nAPI key: sk-abcdef1234567890xyz\nDone.")
        findings = scan_log_file(f)
        assert len(findings) >= 1

    def test_clean_log_no_findings(self, tmp_path):
        f = tmp_path / "clean.log"
        f.write_text("Starting server...\nTask completed successfully.\nDone.")
        findings = scan_log_file(f)
        assert len(findings) == 0


class TestMainIntegration:
    def test_clean_user_data_returns_zero(self, tmp_path, monkeypatch):
        # Create minimal clean user data structure
        (tmp_path / "agent-runtime").mkdir()
        (tmp_path / "config").mkdir()
        db = tmp_path / "agent-runtime" / "agent_core.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE agent_tasks (id TEXT, objective TEXT)")
        conn.execute("INSERT INTO agent_tasks VALUES (?, ?)", ("task_1", "分析热点"))
        conn.commit()
        conn.close()
        (tmp_path / "config" / "accounts.json").write_text('{"accounts": []}')

        monkeypatch.setenv("MARKETING_OS_USER_DATA", str(tmp_path))
        result = main()
        assert result == 0

    def test_dirty_user_data_returns_one(self, tmp_path, monkeypatch):
        (tmp_path / "agent-runtime").mkdir()
        (tmp_path / "config").mkdir()
        db = tmp_path / "agent-runtime" / "agent_core.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE task_events (id TEXT, payload TEXT)")
        conn.execute(
            "INSERT INTO task_events VALUES (?, ?)",
            ("evt_1", json.dumps({"api_key": "sk-abcdef1234567890xyz"})),
        )
        conn.commit()
        conn.close()

        monkeypatch.setenv("MARKETING_OS_USER_DATA", str(tmp_path))
        result = main()
        assert result == 1

    def test_insecure_secrets_file_permissions(self, tmp_path, monkeypatch):
        (tmp_path / "secrets").mkdir()
        secrets_file = tmp_path / "secrets" / "providers.env"
        secrets_file.write_text("DEEPSEEK_API_KEY=sk-test1234567890")
        os.chmod(secrets_file, 0o644)  # World-readable — insecure

        monkeypatch.setenv("MARKETING_OS_USER_DATA", str(tmp_path))
        result = main()
        assert result == 1


class TestRedactionInfrastructure:
    """Verify that the existing _redact function in store.py prevents secrets from landing in DB."""

    def test_redact_strips_api_key(self):
        from agent_core.store import _redact
        data = {"api_key": "sk-abcdef1234567890", "name": "test"}
        redacted = _redact(data)
        assert redacted["api_key"] == "[REDACTED]"
        assert redacted["name"] == "test"

    def test_redact_strips_nested_cookie(self):
        from agent_core.store import _redact
        data = {"result": {"cookies": "sessionid=abc123", "status": "ok"}}
        redacted = _redact(data)
        assert redacted["result"]["cookies"] == "[REDACTED]"
        assert redacted["result"]["status"] == "ok"

    def test_redact_strips_secret_in_string(self):
        from agent_core.store import _redact
        data = "api_key=sk-abcdef1234567890xyz and more text"
        redacted = _redact(data)
        assert redacted == "[REDACTED]"

    def test_redact_preserves_normal_text(self):
        from agent_core.store import _redact
        data = {"objective": "分析今天的热点", "status": "running"}
        redacted = _redact(data)
        assert redacted == data
