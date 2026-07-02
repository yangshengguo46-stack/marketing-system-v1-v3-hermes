"""Marketing account metadata tools.

Platform credentials and cookies are owned exclusively by Electron.  This
module stores only non-secret account metadata and the latest sanitized metric
snapshot that Electron has explicitly supplied.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import datetime
from pathlib import Path


def _default_config_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "marketing-os-desktop" / "config"


CONFIG_DIR = Path(os.environ.get("MARKETING_OS_CONFIG_DIR", _default_config_dir()))
ACCOUNTS_DB = CONFIG_DIR / "accounts.json"


def _read_accounts_db() -> dict:
    try:
        return json.loads(ACCOUNTS_DB.read_text()) if ACCOUNTS_DB.exists() else {"accounts": [], "updated_at": None}
    except (OSError, json.JSONDecodeError):
        return {"accounts": [], "updated_at": None}


def _write_accounts_db(data: dict) -> None:
    ACCOUNTS_DB.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now().isoformat()
    fd, temp_name = tempfile.mkstemp(prefix=".accounts.", dir=ACCOUNTS_DB.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(temp_name, ACCOUNTS_DB)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def add_account(params, **_kwargs) -> str:
    """Persist account metadata after Electron has completed platform login."""
    if any(params.get(key) for key in ("password", "cookie", "token", "api_key")):
        return json.dumps({
            "success": False,
            "error": "账号秘密只能保存在 Electron 登录会话中，后端拒绝接收密码、Cookie 或 Token",
            "code": "secret_boundary_violation",
        }, ensure_ascii=False)

    platform = str(params.get("platform", "")).strip()
    username = str(params.get("username", "")).strip()
    requested_id = str(params.get("account_id") or params.get("id") or "").strip()
    if not platform or not username:
        return json.dumps({"success": False, "error": "platform and username required"}, ensure_ascii=False)
    if requested_id and not re.fullmatch(r"acct_[a-zA-Z0-9_-]{6,64}", requested_id):
        return json.dumps({"success": False, "error": "invalid account_id"}, ensure_ascii=False)

    db = _read_accounts_db()
    by_id = next((item for item in db.get("accounts", []) if item.get("id") == requested_id), None) if requested_id else None
    if by_id:
        if by_id.get("platform") != platform:
            return json.dumps({"success": False, "error": "account_id platform mismatch"}, ensure_ascii=False)
        by_id.update({
            "username": username,
            "label": str(params.get("label") or by_id.get("label") or f"{platform}账号").strip(),
            "status": "connected",
            "updated_at": datetime.now().isoformat(),
        })
        _write_accounts_db(db)
        return json.dumps({"success": True, "account": by_id, "created": False}, ensure_ascii=False)

    # Creator centers do not always expose a stable public user id immediately
    # after QR login.  Placeholder identities such as ``douyin_session`` must
    # never be used to collapse two independently isolated Electron sessions.
    placeholder_identity = username.endswith("_session")
    existing = None if placeholder_identity else next(
        (item for item in db.get("accounts", []) if item.get("platform") == platform and item.get("username") == username),
        None,
    )
    if existing:
        if requested_id and existing.get("id") != requested_id:
            return json.dumps({
                "success": False,
                "error": "该平台账号已经连接，请使用原账号重新登录",
                "code": "account_identity_conflict",
                "existing_account_id": existing.get("id"),
            }, ensure_ascii=False)
        if params.get("label"):
            existing["label"] = str(params["label"]).strip()
        existing["status"] = "connected"
        existing["updated_at"] = datetime.now().isoformat()
        _write_accounts_db(db)
        return json.dumps({"success": True, "account": existing, "created": False}, ensure_ascii=False)

    account = {
        "id": requested_id or f"acct_{uuid.uuid4().hex[:12]}",
        "platform": platform,
        "username": username,
        "label": str(params.get("label") or f"{platform}账号").strip(),
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "status": "connected",
        "stats": {},
    }
    db.setdefault("accounts", []).append(account)
    _write_accounts_db(db)
    return json.dumps({"success": True, "account": account, "created": True}, ensure_ascii=False)


def list_accounts(params=None, **_kwargs) -> str:
    db = _read_accounts_db()
    platform = str((params or {}).get("platform", "")).strip()
    accounts = db.get("accounts", [])
    if platform:
        accounts = [item for item in accounts if item.get("platform") == platform]
    return json.dumps({"total": len(accounts), "accounts": accounts}, ensure_ascii=False)


def remove_account(params, **_kwargs) -> str:
    """Remove metadata only; Electron separately owns session cleanup."""
    account_id = str(params.get("account_id", "")).strip()
    db = _read_accounts_db()
    before = len(db.get("accounts", []))
    db["accounts"] = [item for item in db.get("accounts", []) if item.get("id") != account_id]
    if len(db["accounts"]) == before:
        return json.dumps({"success": False, "error": "账号不存在"}, ensure_ascii=False)
    _write_accounts_db(db)
    return json.dumps({"success": True, "removed": account_id, "session_cleanup_required": True}, ensure_ascii=False)


def update_account_status(params, **_kwargs) -> str:
    account_id = str(params.get("account_id", "")).strip()
    status = str(params.get("status", "")).strip()
    if status not in {"connected", "disconnected", "expired", "error"}:
        return json.dumps({"success": False, "error": "invalid account status"}, ensure_ascii=False)
    db = _read_accounts_db()
    account = next((item for item in db.get("accounts", []) if item.get("id") == account_id), None)
    if not account:
        return json.dumps({"success": False, "error": "账号不存在"}, ensure_ascii=False)
    account["status"] = status
    account["updated_at"] = datetime.now().isoformat()
    _write_accounts_db(db)
    return json.dumps({"success": True, "account": account}, ensure_ascii=False)


def update_account_identity(params, **_kwargs) -> str:
    """Update public account identity fields supplied by the Electron session."""
    if any(params.get(key) for key in ("password", "cookie", "token", "api_key")):
        return json.dumps({"success": False, "error": "secret boundary violation"}, ensure_ascii=False)
    account_id = str(params.get("account_id", "")).strip()
    username = str(params.get("username", "")).strip()[:128]
    label = str(params.get("label", "")).strip()[:128]
    db = _read_accounts_db()
    account = next((item for item in db.get("accounts", []) if item.get("id") == account_id), None)
    if not account:
        return json.dumps({"success": False, "error": "账号不存在"}, ensure_ascii=False)
    if username and not username.endswith("_session"):
        conflict = next((
            item for item in db.get("accounts", [])
            if item.get("id") != account_id
            and item.get("platform") == account.get("platform")
            and item.get("username") == username
        ), None)
        if conflict:
            return json.dumps({"success": False, "error": "该真实账号标识已绑定另一会话"}, ensure_ascii=False)
        account["username"] = username
    if label:
        account["label"] = label
    account["updated_at"] = datetime.now().isoformat()
    _write_accounts_db(db)
    return json.dumps({"success": True, "account": account}, ensure_ascii=False)


def get_account_stats(params, **_kwargs) -> str:
    """Read the latest Electron-supplied snapshot; never launch a browser."""
    account_id = str(params.get("account_id", "")).strip()
    account = next((item for item in _read_accounts_db().get("accounts", []) if item.get("id") == account_id), None)
    if not account:
        return json.dumps({"success": False, "error": "账号不存在"}, ensure_ascii=False)
    stats = account.get("stats") or {}
    return json.dumps({
        "success": bool(stats),
        "account": account,
        "stats": stats,
        "source": "electron_session_snapshot",
        "message": None if stats else "尚无指标快照，请通过 Electron 登录会话同步",
    }, ensure_ascii=False)


def monitor_all_accounts(params=None, **_kwargs) -> str:
    accounts = _read_accounts_db().get("accounts", [])
    return json.dumps({
        "monitored_at": datetime.now().isoformat(),
        "total_accounts": len(accounts),
        "results": [json.loads(get_account_stats({"account_id": item["id"]})) for item in accounts],
        "source": "persisted_snapshots",
    }, ensure_ascii=False)


TOOLS = [
    {
        "name": "list_accounts",
        "description": "读取已连接账号的脱敏元信息和最近指标快照",
        "schema": {"type": "object", "properties": {"platform": {"type": "string"}}},
        "handler": list_accounts,
    },
    {
        "name": "get_account_stats",
        "description": "读取 Electron 登录会话最近同步的账号指标，不启动浏览器",
        "schema": {
            "type": "object",
            "properties": {"account_id": {"type": "string"}},
            "required": ["account_id"],
        },
        "handler": get_account_stats,
    },
]
