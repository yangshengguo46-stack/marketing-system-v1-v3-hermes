"""账号管理工具 — Bitwarden 集成 + 多平台账号监控

Bitwarden CLI (bw) 集成方式:
- Hermes 通过 bw CLI 读取/存储账号凭据
- 命令行: bw get item <item-id>
- 所有敏感信息在 Bitwarden vault 中加密存储
"""

import json
import subprocess
import os
import uuid
from pathlib import Path
from datetime import datetime

CONFIG_DIR = Path(os.environ.get(
    "MARKETING_OS_CONFIG_DIR",
    Path.home() / ".hermes" / "plugins" / "marketing-os" / "config",
))
ACCOUNTS_DB = CONFIG_DIR / "accounts.json"


def _read_accounts_db() -> dict:
    if ACCOUNTS_DB.exists():
        return json.loads(ACCOUNTS_DB.read_text())
    return {"accounts": [], "updated_at": None}


def _write_accounts_db(data: dict):
    ACCOUNTS_DB.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now().isoformat()
    ACCOUNTS_DB.write_text(json.dumps(data, ensure_ascii=False, indent=2))


# ---- 账号 CRUD ----

def add_account(params, **kwargs) -> str:
    """添加一个平台账号 (凭据存入Bitwarden)"""
    platform = params["platform"]
    username = params["username"]
    password = params.get("password", "")
    label = params.get("label") or f"{platform}-{username}"

    # 将密码存入 Bitwarden (仅当密码非空时)
    bitwarden_id = None
    credential_warning = None
    if password:
        try:
            result = subprocess.run(
                ["bw", "get", "template", "item.login"],
                capture_output=True, text=True, timeout=10,
                env={**os.environ, "BW_SESSION": os.environ.get("BW_SESSION", "")}
            )
            template = json.loads(result.stdout)
            template["name"] = f"marketing-os:{label}"
            template["login"]["username"] = username
            template["login"]["password"] = password
            template["notes"] = f"platform={platform}"

            create_result = subprocess.run(
                ["bw", "create", "item", json.dumps(template)],
                capture_output=True, text=True, timeout=10,
                env={**os.environ, "BW_SESSION": os.environ.get("BW_SESSION", "")}
            )
            created = json.loads(create_result.stdout)
            bitwarden_id = created.get("id")
        except Exception as e:
            credential_warning = f"Bitwarden存储失败: {str(e)}。已保存账号元信息，但凭据未持久化"

    # 存储 cookie（如果有的话）
    if password and "=" in password and len(password) > 50:
        # Cookie 已存入 Bitwarden，仅在当前进程中暴露给后端工具。
        os.environ[f"{platform.upper()}_COOKIE"] = password

    # 本地存元信息 (不含密码/cookie)
    db = _read_accounts_db()
    account = {
        "id": f"acct_{uuid.uuid4().hex[:12]}",
        "platform": platform,
        "username": username,
        "label": label,
        "bitwarden_id": bitwarden_id,
        "created_at": datetime.now().isoformat(),
        "status": "active",
        "stats": {}
    }
    db["accounts"].append(account)
    _write_accounts_db(db)

    result = {"success": True, "account": account}
    if credential_warning:
        result["warning"] = credential_warning
    return json.dumps(result, ensure_ascii=False)


def list_accounts(params, **kwargs) -> str:
    """列出所有已添加的账号"""
    db = _read_accounts_db()
    platform = params.get("platform", "")
    accounts = db["accounts"]
    if platform:
        accounts = [a for a in accounts if a["platform"] == platform]
    return json.dumps({
        "total": len(accounts),
        "accounts": accounts,
    }, ensure_ascii=False)


def remove_account(params, **kwargs) -> str:
    """删除一个账号"""
    account_id = params["account_id"]
    db = _read_accounts_db()
    account = next((a for a in db["accounts"] if a["id"] == account_id), None)
    if not account:
        return json.dumps({"success": False, "error": "账号不存在"})

    # 从Bitwarden删除凭据
    if account.get("bitwarden_id"):
        try:
            subprocess.run(
                ["bw", "delete", "item", account["bitwarden_id"]],
                capture_output=True, text=True, timeout=10,
                env={**os.environ, "BW_SESSION": os.environ.get("BW_SESSION", "")}
            )
        except Exception:
            pass  # Bitwarden 删除失败不阻塞

    db["accounts"] = [a for a in db["accounts"] if a["id"] != account_id]
    _write_accounts_db(db)
    return json.dumps({"success": True, "removed": account_id}, ensure_ascii=False)


# ---- 账号数据拉取 ----

def get_account_stats(params, **kwargs) -> str:
    """获取指定平台账号的数据统计"""
    account_id = params["account_id"]
    db = _read_accounts_db()
    account = next((a for a in db["accounts"] if a["id"] == account_id), None)
    if not account:
        return json.dumps({"success": False, "error": "账号不存在"})

    platform = account["platform"]
    username = account["username"]

    # 根据平台类型构造抓取指令 (需agent-browser)
    scrapers = {
        "douyin": {
            "url": f"https://www.douyin.com/user/{username}",
            "extract": """() => JSON.stringify({
                follower_count: document.querySelector('[data-e2e="follower-count"]')?.textContent,
                like_count: document.querySelector('[data-e2e="like-count"]')?.textContent,
                video_count: document.querySelector('[data-e2e="video-count"]')?.textContent,
            })"""
        },
        "bilibili": {
            "url": f"https://api.bilibili.com/x/space/acc/info?mid={username}",
            "extract": "() => document.body.innerText"
        },
        "weibo": {
            "url": f"https://weibo.com/u/{username}",
            "extract": """() => JSON.stringify({
                follower_count: document.querySelector('.f-num')?.textContent,
            })"""
        }
    }

    scraper = scrapers.get(platform, {})
    if not scraper:
        return json.dumps({"success": False, "error": f"不支持的平台: {platform}"})

    return json.dumps({
        "success": True,
        "account": account,
        "stats_instruction": {
            "tool": "agent-browser",
            "url": scraper["url"],
            "extract_js": scraper["extract"],
            "note": "由agent执行浏览器自动化获取实时数据"
        },
        "fetched_at": datetime.now().isoformat(),
    }, ensure_ascii=False)


def monitor_all_accounts(params, **kwargs) -> str:
    """拉取所有账号的数据，生成监控报告"""
    db = _read_accounts_db()
    accounts = db["accounts"]
    results = []
    for acct in accounts:
        stats_result = json.loads(get_account_stats({"account_id": acct["id"]}))
        results.append({
            "account_id": acct["id"],
            "platform": acct["platform"],
            "label": acct["label"],
            "status": acct["status"],
            **stats_result
        })
    return json.dumps({
        "monitored_at": datetime.now().isoformat(),
        "total_accounts": len(accounts),
        "results": results,
    }, ensure_ascii=False)


TOOLS = [
    {
        "name": "add_account",
        "description": "添加一个新平台账号，凭据安全存储在 Bitwarden",
        "schema": {
            "type": "object",
            "properties": {
                "platform": {"type": "string", "enum": [
                    "douyin", "wechat_channels", "weibo", "bilibili",
                    "xiaohongshu", "kuaishou", "zhihu", "tiktok",
                    "youtube", "instagram", "facebook", "twitter"
                ]},
                "username": {"type": "string"},
                "password": {"type": "string", "description": "账号密码或cookie"},
                "label": {"type": "string", "description": "账号标签，如'公司主号'"}
            },
            "required": ["platform", "username"]
        },
        "handler": add_account,
    },
    {
        "name": "list_accounts",
        "description": "列出所有已添加的平台账号",
        "schema": {
            "type": "object",
            "properties": {
                "platform": {"type": "string", "description": "筛选平台，不传则全部"}
            }
        },
        "handler": list_accounts,
    },
    {
        "name": "remove_account",
        "description": "删除一个已添加的平台账号及其Bitwarden凭据",
        "schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"}
            },
            "required": ["account_id"]
        },
        "handler": remove_account,
    },
    {
        "name": "get_account_stats",
        "description": "获取指定账号的实时数据 (粉丝数/播放量/互动)",
        "schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "string"}
            },
            "required": ["account_id"]
        },
        "handler": get_account_stats,
    },
    {
        "name": "monitor_all_accounts",
        "description": "拉取所有已连接账号的数据，生成综合监控报告",
        "schema": {
            "type": "object",
            "properties": {}
        },
        "handler": monitor_all_accounts,
    },
]
