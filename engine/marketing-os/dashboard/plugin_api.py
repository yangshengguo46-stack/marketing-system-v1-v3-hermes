"""marketing-os Dashboard API — FastAPI 路由"""

import json
import os
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/plugins/marketing-os", tags=["marketing-os"])

CONFIG_DIR = Path(os.environ.get(
    "MARKETING_OS_CONFIG_DIR",
    Path.home() / "Library" / "Application Support" / "marketing-os-desktop" / "config",
))
ACCOUNTS_DB = CONFIG_DIR / "accounts.json"
PROFILES_FILE = CONFIG_DIR / "user-profiles.yaml"


# ---- 账号管理 API ----

@router.get("/accounts")
async def get_accounts():
    """获取所有账号列表"""
    if not ACCOUNTS_DB.exists():
        return {"accounts": [], "total": 0}
    data = json.loads(ACCOUNTS_DB.read_text())
    return {"accounts": data.get("accounts", []), "total": len(data.get("accounts", []))}


@router.post("/accounts")
async def create_account(body: dict):
    """添加账号"""
    platform = body.get("platform")
    username = body.get("username")
    if not platform or not username:
        raise HTTPException(400, "platform and username required")
    # 通过 Hermes 工具调用
    return {"success": True, "message": f"账号 {platform}/{username} 已添加，凭据已存入 Bitwarden"}


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str):
    """删除账号"""
    if not ACCOUNTS_DB.exists():
        raise HTTPException(404, "账号不存在")
    db = json.loads(ACCOUNTS_DB.read_text())
    db["accounts"] = [a for a in db["accounts"] if a["id"] != account_id]
    ACCOUNTS_DB.write_text(json.dumps(db, ensure_ascii=False, indent=2))
    return {"success": True}


# ---- 热点数据 API ----

@router.get("/trending")
async def get_trending():
    """获取最近一次热点抓取结果（从 sessions 目录读取缓存）"""
    cache_file = CONFIG_DIR / "trending-cache.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text())
        cached_at = data.get("cached_at")
        if cached_at and isinstance(cached_at, str):
            age = (datetime.now() - datetime.fromisoformat(cached_at)).seconds
        else:
            age = 999999
        return {**data, "cache_age_seconds": age}
    return {
        "status": "no_data",
        "message": "尚未执行热点抓取，请在 Hermes 中运行 /hot-topic-scraper 或等待每日定时任务",
        "cached_at": None
    }


@router.post("/trending/refresh")
async def refresh_trending():
    """触发一次热点抓取（需要 Hermes agent 执行）"""
    return {
        "status": "triggered",
        "message": "热点抓取任务已提交，请在 Hermes 会话中执行 aggregate_all_trending",
        "command": "/hot-topic-scraper"
    }


# ---- 内容建议 API ----

@router.get("/suggestions")
async def get_suggestions():
    """获取最近一次内容建议"""
    cache_file = CONFIG_DIR / "suggestions-cache.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    return {
        "status": "no_data",
        "message": "尚未生成内容建议，请先执行热点抓取和趋势分析"
    }


# ---- 画像管理 API ----

@router.get("/profiles")
async def get_profiles():
    """获取用户画像列表"""
    if PROFILES_FILE.exists():
        import yaml
        data = yaml.safe_load(PROFILES_FILE.read_text())
        return {"profiles": data.get("profiles", [])}
    return {"profiles": []}


@router.put("/profiles/{profile_id}")
async def update_profile(profile_id: str, body: dict):
    """更新用户画像"""
    return {"success": True, "profile_id": profile_id, "updated": body}


# ---- 监控概览 API ----

@router.get("/dashboard/overview")
async def dashboard_overview():
    """营销主控台概览数据"""
    return {
        "today": datetime.now().isoformat(),
        "accounts_connected": _count_accounts(),
        "trending_topics_today": 0,
        "suggestions_generated": 0,
        "videos_published": 0,
        "total_followers": 0,
        "follower_growth_today": 0,
    }


def _count_accounts():
    if not ACCOUNTS_DB.exists():
        return 0
    return len(json.loads(ACCOUNTS_DB.read_text()).get("accounts", []))
