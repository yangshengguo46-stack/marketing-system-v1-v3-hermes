"""marketing-os 独立 API 服务器 — 不走 Hermes Dashboard 认证

Electron main 进程 spawn: python3 server.py --port 19519
"""

import json
import sys
import os
import tempfile
import shutil
import asyncio
import threading
import secrets
import re
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime, timedelta

# 确保能导入 marketing_tools 和 agent_core（显式优先，不依赖 spawn 环境）
_ENGINE_ROOT = Path(__file__).resolve().parent.parent
_MARKETING_ROOT = Path(__file__).resolve().parent
if str(_MARKETING_ROOT) not in sys.path:
    sys.path.insert(0, str(_MARKETING_ROOT))
if str(_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINE_ROOT))

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn
from agent_core.mcp_broker import ProductMCPBroker, load_mcp_manifest

@asynccontextmanager
async def lifespan(_app):
    scheduler = asyncio.create_task(_scheduler_loop())
    try:
        yield
    finally:
        scheduler.cancel()
        try:
            await scheduler
        except asyncio.CancelledError:
            pass
        service = globals().get("_agent_service")
        if service is not None:
            service.shutdown()
        for task in list(globals().get("_mcp_login_monitor_tasks", {}).values()):
            task.cancel()
        manager = globals().get("_mcp_manager")
        if manager is not None:
            await manager.stop_all(timeout=10)


app = FastAPI(title="marketing-os API", lifespan=lifespan)

API_TOKEN = os.environ.get("MARKETING_OS_API_TOKEN", "")


@app.middleware("http")
async def require_local_api_token(request: Request, call_next):
    """Only localhost clients with the correct token may call the API."""
    if API_TOKEN and request.url.path.startswith(("/api/", "/agent/")):
        # Block non-localhost origins (prevents remote web pages from calling API)
        origin = (request.headers.get("origin") or "").lower()
        if origin and not origin.startswith(("http://localhost", "http://127.0.0.1", "http://[::1]", "file://", "app://")):
            return JSONResponse(status_code=403, content={"detail": "origin not allowed"})

        supplied = request.headers.get("X-Marketing-OS-Token", "")
        if not secrets.compare_digest(supplied, API_TOKEN):
            return JSONResponse(status_code=401, content={"detail": "unauthorized local client"})
    return await call_next(request)

BUNDLED_CONFIG_DIR = Path(__file__).parent / "config"
CONFIG_DIR = Path(os.environ.get("MARKETING_OS_CONFIG_DIR", BUNDLED_CONFIG_DIR))
MCP_MANIFEST = _MARKETING_ROOT / "config" / "mcp-servers.json"
_mcp_broker: ProductMCPBroker | None = None
_mcp_manager: "AccountScopedMCPManager | None" = None


def _get_mcp_broker() -> ProductMCPBroker:
    global _mcp_broker
    if _mcp_broker is None:
        _mcp_broker = ProductMCPBroker(load_mcp_manifest(MCP_MANIFEST))
    return _mcp_broker


def _get_mcp_manager() -> "AccountScopedMCPManager":
    global _mcp_manager
    if _mcp_manager is None:
        from agent_core.mcp_process_manager import AccountScopedMCPManager
        user_data = Path(os.environ.get("MARKETING_OS_USER_DATA",
                         str(CONFIG_DIR.parent / "userData")))
        _mcp_manager = AccountScopedMCPManager(user_data)
    return _mcp_manager


def _ensure_config() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    defaults = {
        "accounts.json": {"accounts": [], "updated_at": None},
        "trending-cache.json": {"status": "no_data", "cached_at": None, "top_trends": []},
        "suggestions-cache.json": {"status": "no_data", "suggestions": []},
        "publishing.json": {"tasks": []},
        "workflow-state.json": {"enabled": False, "schedule_time": "08:03", "last_run": None, "last_result": None},
        "intelligence-config.json": {"industries": [], "platforms": ["douyin"], "sync_accounts": True},
        "intelligence-report.json": {"status": "never_run", "steps": [], "errors": []},
    }
    for name, default in defaults.items():
        target = CONFIG_DIR / name
        if not target.exists():
            source = BUNDLED_CONFIG_DIR / name
            if source.exists() and source != target:
                shutil.copy2(source, target)
            else:
                _write_json(target, default)
    profile_target = CONFIG_DIR / "user-profiles.yaml"
    profile_source = BUNDLED_CONFIG_DIR / "user-profiles.yaml"
    if not profile_target.exists() and profile_source.exists() and profile_source != profile_target:
        shutil.copy2(profile_source, profile_target)


def _read_json(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, data: dict) -> None:
    """Write config atomically so a terminated refresh cannot corrupt the cache."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


_ensure_config()


def _default_profile() -> dict:
    profile_file = CONFIG_DIR / "user-profiles.yaml"
    if not profile_file.exists():
        return {}
    import yaml
    data = yaml.safe_load(profile_file.read_text()) or {}
    return next((p for p in data.get("profiles", []) if p.get("id") == "default"), {})


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/api/plugins/marketing-os/mcp/status")
def mcp_status():
    """Return reviewed MCP configuration status without starting servers."""
    return _get_mcp_broker().status()


# ---- 热点趋势 ----

_trending_refresh_lock = threading.Lock()

@app.get("/api/plugins/marketing-os/trending")
def get_trending():
    cache_file = CONFIG_DIR / "trending-cache.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text())
        cached_at = data.get("cached_at")
        if cached_at and isinstance(cached_at, str):
            age = max(0, int((datetime.now() - datetime.fromisoformat(cached_at)).total_seconds()))
        else:
            age = 999999
        return {**data, "cache_age_seconds": age}
    return {"status": "no_data", "message": "尚未执行热点抓取", "cached_at": None}


def query_trending_cache(params: dict | None = None) -> dict:
    """Read and filter the trending cache deterministically.

    Args via params dict (from agent tool call):
        query (str, optional): Substring match on title and category (lowered).
        platform (str, optional): Exact match on source_platform.
        limit (int, optional): 1-30, default 30.

    Returns the full cache envelope with filtered top_trends and match metadata.
    """
    params = params or {}
    query = str(params.get("query", "")).strip() or None
    raw_platform = params.get("platform")
    platform = str(raw_platform).strip().lower() if raw_platform else None
    try:
        limit = max(1, min(int(params.get("limit", 30)), 30))
    except (TypeError, ValueError):
        limit = 30

    cache_file = CONFIG_DIR / "trending-cache.json"
    if not cache_file.exists():
        return {
            "status": "no_data", "cached_at": None,
            "message": "尚未执行热点抓取",
            "top_trends": [], "matched": 0, "total_available": 0,
            "cache_age_seconds": 999999,
        }

    data = json.loads(cache_file.read_text())
    cached_at = data.get("cached_at")
    if cached_at and isinstance(cached_at, str):
        age = max(0, int((datetime.now() - datetime.fromisoformat(cached_at)).total_seconds()))
    else:
        age = 999999

    trends = data.get("top_trends", [])
    total_available = len(trends)

    if platform:
        trends = [t for t in trends if str(t.get("source_platform", "")).lower() == platform]

    if query:
        q = query.lower()
        trends = [
            t for t in trends
            if q in str(t.get("title", "")).lower()
            or q in str(t.get("category", "")).lower()
        ]

    matched = len(trends)
    limited = trends[:limit]

    return {
        **data,
        "cache_age_seconds": age,
        "top_trends": limited,
        "matched": matched,
        "total_available": total_available,
    }


@app.post("/api/plugins/marketing-os/trending/refresh")
def refresh_trending(body: dict | None = None):
    """Run the built-in scraper, analyze its output, and persist both UI caches."""
    from marketing_tools.scraping import aggregate_all_trending

    if not _trending_refresh_lock.acquire(blocking=False):
        current = get_trending()
        return {
            "status": "refreshing",
            "message": "后台更新正在进行",
            "trends_count": len(current.get("top_trends", [])),
        }
    requested = (body or {}).get("platforms")
    platforms = requested or ["douyin", "weibo", "bilibili", "zhihu"]
    try:
        raw = json.loads(aggregate_all_trending({"platforms": platforms}))
        return _persist_trending_analysis(raw, {"platforms_scraped": platforms, "refresh_mode": "background"})
    finally:
        _trending_refresh_lock.release()


def _persist_trending_analysis(
    raw: dict, metadata: dict | None = None,
    session_overlay_update: dict | None = None,
) -> dict:
    from marketing_tools.content import analyze_trends, generate_content_suggestions

    previous = _read_json(CONFIG_DIR / "trending-cache.json", {})
    overlays = dict(previous.get("session_overlays") or {})
    if session_overlay_update:
        overlays.update(session_overlay_update)
    # Account-scoped evidence augments public feeds and survives their periodic
    # refresh. It never deletes another platform's last good evidence.
    raw = json.loads(json.dumps(raw))
    for platform, overlay in overlays.items():
        overlay_items = list((overlay or {}).get("items") or [])
        if not overlay_items:
            continue
        for item in overlay_items:
            if isinstance(item, dict):
                item.setdefault("source_backend", "playwright_mcp_creator_center")
        existing = raw.setdefault("results", {}).get(platform)
        if isinstance(existing, dict) and existing.get("success"):
            existing["data"] = overlay_items + list(existing.get("data") or [])
            existing["count"] = len(existing["data"])
            existing["backend_used"] = "mixed_public_and_session"
        else:
            raw["results"][platform] = {
                "success": True, "backend_used": "playwright_mcp_creator_center",
                "data": overlay_items, "count": len(overlay_items),
            }
        if platform not in raw.setdefault("platforms_scraped", []):
            raw["platforms_scraped"].insert(0, platform)

    analysis = json.loads(analyze_trends({"hot_data": raw}))
    successful = [
        platform for platform, result in raw.get("results", {}).items()
        if result.get("success")
    ]
    attempted_at = datetime.now().isoformat()
    refresh_errors = {
        platform: result.get("error", "抓取失败")
        for platform, result in raw.get("results", {}).items()
        if not result.get("success")
    }
    if not successful:
        previous = _read_json(CONFIG_DIR / "trending-cache.json", {})
        if previous.get("top_trends"):
            stale_cache = {
                **previous,
                "status": "stale",
                "stale": True,
                "refresh_status": "failed",
                "last_refresh_attempt": attempted_at,
                "refresh_errors": refresh_errors,
            }
            _write_json(CONFIG_DIR / "trending-cache.json", stale_cache)
            return {
                "status": "stale",
                "message": "本次更新失败，继续使用上次有效数据",
                "trends_count": len(previous.get("top_trends", [])),
                "suggestions_count": len(_read_json(CONFIG_DIR / "suggestions-cache.json", {}).get("suggestions", [])),
                "platforms_succeeded": [],
                "errors": refresh_errors,
            }
    trending_cache = {
        **analysis,
        "status": "ok" if successful else "error",
        "cached_at": attempted_at,
        "last_refresh_attempt": attempted_at,
        "refresh_status": "completed" if successful else "failed",
        "stale": False,
        "platforms_scraped": raw.get("platforms_scraped", list(raw.get("results", {}))),
        "platforms_succeeded": successful,
        "backends_used": raw.get("backends_used", []),
        "errors": refresh_errors,
        "session_overlays": overlays,
        **(metadata or {}),
    }
    _write_json(CONFIG_DIR / "trending-cache.json", trending_cache)

    suggestions = json.loads(generate_content_suggestions({
        "user_profile": _default_profile(),
        "trends": analysis,
    }))
    suggestions_cache = {
        **suggestions,
        "status": "ok" if suggestions.get("suggestions") else "no_data",
        "cached_at": datetime.now().isoformat(),
    }
    _write_json(CONFIG_DIR / "suggestions-cache.json", suggestions_cache)

    return {
        "status": trending_cache["status"],
        "message": f"完成 {len(successful)}/{len(raw.get('results', {}))} 个平台抓取",
        "trends_count": len(analysis.get("top_trends", [])),
        "suggestions_count": len(suggestions.get("suggestions", [])),
        "platforms_succeeded": successful,
        "errors": trending_cache["errors"],
    }


@app.post("/api/plugins/marketing-os/trending/import")
def import_session_trending(body: dict):
    platform = str(body.get("platform", "")).strip()
    keyword = str(body.get("keyword", "")).strip()
    incoming = body.get("items") or []
    if platform not in {"douyin"}:
        raise HTTPException(400, "unsupported session platform")
    if not keyword:
        raise HTTPException(400, "keyword required")
    if not isinstance(incoming, list) or not incoming:
        raise HTTPException(400, "items required")
    from agent_core.models import validate_source_batch
    items = []
    for index, item in enumerate(incoming[:100]):
        if not isinstance(item, dict):
            continue
        item.setdefault("source", "electron_session")
        item.setdefault("platform", platform)
        item.setdefault("collected_at", datetime.now().isoformat())
        item.setdefault("query", keyword)
        if not item.get("url"):
            item["url"] = f"douyin://video/{item.get('rank', index + 1)}"
        items.append(item)
    items = validate_source_batch(items)
    items = [{
        "rank": it.get("rank", i + 1),
        "title": it["title"],
        "url": it["url"],
        "heat_value": it.get("additional", {}).get("heat_value", ""),
        "source": it["source"],
        "platform": it["platform"],
        "collected_at": it["collected_at"],
    } for i, it in enumerate(items)]
    if not items:
        raise HTTPException(400, "no valid items")
    raw = {
        "aggregated_at": datetime.now().isoformat(),
        "platforms_scraped": [platform],
        "backends_used": ["electron_session"],
        "results": {
            platform: {"success": True, "backend_used": "electron_session", "data": items, "count": len(items)},
        },
    }
    result = _persist_trending_analysis(
        raw, {"query": keyword, "source": "playwright_mcp_session"},
        {platform: {"items": items, "query": keyword, "updated_at": datetime.now().isoformat()}},
    )
    return {**result, "imported_count": len(items), "query": keyword}


@app.post("/api/plugins/marketing-os/trending/import-batch")
def import_session_trending_batch(body: dict):
    collections = body.get("collections") or []
    if not isinstance(collections, list) or not collections:
        raise HTTPException(400, "collections required")
    items = []
    queries = []
    seen = set()
    for collection in collections[:20]:
        if not isinstance(collection, dict) or collection.get("platform") != "douyin":
            continue
        keyword = str(collection.get("keyword", "")).strip()
        if keyword:
            queries.append(keyword)
        for item in (collection.get("items") or [])[:100]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", ""))[:1000]
            identity = url or title
            if not title or identity in seen:
                continue
            seen.add(identity)
            items.append({
                "rank": len(items) + 1,
                "title": title[:200],
                "url": url,
                "heat_value": item.get("heat_value", ""),
                "query": keyword,
            })
    if not items:
        raise HTTPException(400, "no valid items")
    raw = {
        "aggregated_at": datetime.now().isoformat(),
        "platforms_scraped": ["douyin"],
        "backends_used": ["electron_session"],
        "results": {
            "douyin": {"success": True, "backend_used": "electron_session", "data": items, "count": len(items)},
        },
    }
    result = _persist_trending_analysis(
        raw, {"queries": list(dict.fromkeys(queries)), "source": "playwright_mcp_session_batch"},
        {"douyin": {"items": items, "queries": list(dict.fromkeys(queries)),
                    "updated_at": datetime.now().isoformat()}},
    )
    return {**result, "imported_count": len(items), "queries": list(dict.fromkeys(queries))}


# ---- 账号管理 ----

@app.get("/api/plugins/marketing-os/accounts")
def get_accounts():
    acct_file = CONFIG_DIR / "accounts.json"
    if acct_file.exists():
        data = json.loads(acct_file.read_text())
        return {"accounts": data.get("accounts", []), "total": len(data.get("accounts", []))}
    return {"accounts": [], "total": 0}


def get_accounts_for_tool(params: dict | None = None):
    data = get_accounts()
    account_id = str((params or {}).get("account_id", "")).strip()
    if not account_id:
        return data
    accounts = [item for item in data.get("accounts", []) if item.get("id") == account_id]
    return {"accounts": accounts, "total": len(accounts), "scope": {"account_id": account_id}}


@app.post("/api/plugins/marketing-os/accounts")
async def create_account(body: dict):
    if not body.get("platform") or not body.get("username"):
        raise HTTPException(400, "platform and username required")
    if any(body.get(key) for key in ("password", "cookie", "token", "api_key")):
        raise HTTPException(400, "账号秘密只能保存在 Electron 登录会话中")
    from marketing_tools.account import add_account
    params = {
        "account_id": body.get("account_id"),
        "platform": body["platform"],
        "username": body["username"],
        "label": body.get("label", ""),
    }
    result = json.loads(add_account(params))
    if not result.get("success"):
        raise HTTPException(422, result.get("error", "账号保存失败"))
    return result


@app.delete("/api/plugins/marketing-os/accounts/{account_id}")
def delete_account(account_id: str):
    from marketing_tools.account import remove_account
    result = json.loads(remove_account({"account_id": account_id}))
    if not result.get("success"):
        raise HTTPException(404, result.get("error", "账号不存在"))
    return result


@app.put("/api/plugins/marketing-os/accounts/{account_id}/status")
def update_account_connection_status(account_id: str, body: dict):
    from marketing_tools.account import update_account_status
    result = json.loads(update_account_status({
        "account_id": account_id,
        "status": body.get("status"),
    }))
    if not result.get("success"):
        raise HTTPException(422, result.get("error", "账号状态更新失败"))
    return result


@app.put("/api/plugins/marketing-os/accounts/{account_id}/identity")
def update_account_public_identity(account_id: str, body: dict):
    from marketing_tools.account import update_account_identity
    result = json.loads(update_account_identity({
        "account_id": account_id,
        "username": body.get("username"),
        "label": body.get("label"),
    }))
    if not result.get("success"):
        raise HTTPException(422, result.get("error", "账号身份更新失败"))
    return result


def _update_account_stats(account_id: str, stats: dict) -> dict:
    data = _read_json(CONFIG_DIR / "accounts.json", {"accounts": []})
    account = next((item for item in data.get("accounts", []) if item.get("id") == account_id), None)
    if not account:
        raise HTTPException(404, "账号不存在")
    previous = account.get("stats") or {}
    followers = int(stats.get("followers", previous.get("followers", 0)) or 0)
    previous_followers = int(previous.get("followers", 0) or 0)
    account["stats"] = {
        **previous,
        **stats,
        "followers": followers,
        "follower_growth_today": followers - previous_followers,
        "updated_at": datetime.now().isoformat(),
    }
    _write_json(CONFIG_DIR / "accounts.json", data)
    from marketing_tools.monitor import analyze_account_snapshot
    analyze_account_snapshot(
        account_id,
        str(account.get("platform", "")),
        account["stats"],
        persist=True,
        data_dir=CONFIG_DIR / "monitor_data",
    )
    return account


@app.put("/api/plugins/marketing-os/accounts/{account_id}/stats")
def update_account_stats(account_id: str, body: dict):
    allowed = {"followers", "total_views", "engagements", "comments", "total_likes"}
    stats = {}
    for key in allowed:
        if key in body:
            try:
                stats[key] = int(body[key])
            except (TypeError, ValueError):
                raise HTTPException(400, f"{key} must be an integer")
    if not stats:
        raise HTTPException(400, "no supported metrics supplied")
    return {"success": True, "account": _update_account_stats(account_id, stats)}


# ---- MCP headed 登录 API（MCP-06） ----

_OFFICIAL_LOGIN_URLS = {"douyin": "https://creator.douyin.com/"}
_LOGIN_TIMEOUT_MIN = 30
_LOGIN_TIMEOUT_MAX = 600
_LOGIN_TIMEOUT_DEFAULT = 120
_mcp_login_attempts: dict = {}
_mcp_login_timeout_tasks: dict = {}
_mcp_login_monitor_tasks: dict = {}
_mcp_account_operation_locks: dict[str, asyncio.Lock] = {}
_mcp_login_counter = 0

_DOUYIN_AUTH_MARKERS = (
    "发布作品", "发布视频", "内容管理", "作品管理", "数据中心",
    "互动管理", "粉丝管理", "创作灵感", "创作者服务中心",
)
_DOUYIN_LOGIN_MARKERS = (
    "扫码登录", "验证码登录", "手机号登录", "请输入手机号",
    "获取验证码", "登录后即可", "抖音扫码", "二维码已失效",
)


def _mcp_login_enabled() -> bool:
    return os.environ.get("MARKETING_OS_MCP_LOGIN_ENABLED") == "1"


async def _expire_mcp_login(account_id: str, attempt_id: str, timeout: int) -> None:
    try:
        await asyncio.sleep(timeout)
        attempt = _mcp_login_attempts.get(account_id)
        if not attempt or attempt.get("login_attempt_id") != attempt_id:
            return
        if attempt.get("status") not in ("starting", "browser_open"):
            return
        await _get_mcp_manager().stop(attempt["platform"], account_id)
        monitor_task = _mcp_login_monitor_tasks.pop(account_id, None)
        if monitor_task and monitor_task is not asyncio.current_task():
            monitor_task.cancel()
        _mcp_login_attempts[account_id] = {
            **attempt, "status": "timed_out", "ended_at": datetime.now().isoformat(),
        }
    finally:
        current = _mcp_login_timeout_tasks.get(account_id)
        if current is asyncio.current_task():
            _mcp_login_timeout_tasks.pop(account_id, None)


def _mcp_text(result: dict) -> str:
    return "\n".join(
        str(item.get("text", ""))
        for item in result.get("content", [])
        if isinstance(item, dict) and item.get("type") == "text"
    )


def _classify_douyin_login_snapshot(text: str) -> dict:
    """Classify only from user-visible creator-center accessibility text."""
    auth_hits = sorted({marker for marker in _DOUYIN_AUTH_MARKERS if marker in text})
    login_hits = sorted({marker for marker in _DOUYIN_LOGIN_MARKERS if marker in text})
    authenticated = len(auth_hits) >= 2 and not login_hits
    return {
        "authenticated": authenticated,
        "auth_markers": auth_hits[:5],
        "login_markers": login_hits[:5],
    }


def _persist_mcp_authenticated_account(account_id: str, platform: str) -> dict:
    from marketing_tools.account import add_account
    suffix = account_id.removeprefix("acct_")[-6:]
    result = json.loads(add_account({
        "account_id": account_id,
        "platform": platform,
        "username": f"{platform}_session_{suffix}",
        "label": f"抖音账号 · {suffix}",
    }))
    if not result.get("success"):
        raise RuntimeError(result.get("error", "账号元数据保存失败"))
    return result["account"]


def _require_connected_account(account_id: str) -> dict:
    accounts = _read_json(CONFIG_DIR / "accounts.json", {"accounts": []}).get("accounts", [])
    account = next((item for item in accounts if item.get("id") == account_id), None)
    if account is None:
        raise HTTPException(404, "账号不存在")
    if account.get("status") != "connected":
        raise HTTPException(409, "账号未连接，请先完成登录")
    if account.get("platform") != "douyin":
        raise HTTPException(400, "MCP browser currently supports douyin only")
    return account


async def _monitor_mcp_login(account_id: str, attempt_id: str) -> None:
    """Require two consecutive authenticated snapshots, then close headed UI."""
    from agent_core.mcp_browser_policy import BrowserActionContext
    consecutive = 0
    try:
        while True:
            await asyncio.sleep(2)
            attempt = _mcp_login_attempts.get(account_id)
            if not attempt or attempt.get("login_attempt_id") != attempt_id:
                return
            if attempt.get("status") != "browser_open":
                return
            platform = attempt["platform"]
            ctx = BrowserActionContext(
                platform=platform, account_id=account_id,
                capability="marketing_session_login", user_id="default", approved=True,
            )
            result = await _get_mcp_broker().call_account_scoped_browser(
                _get_mcp_manager(), "playwright_browser", platform, account_id,
                "browser_snapshot", {"depth": 8}, browser_ctx=ctx, approved=True,
            )
            if result.get("status") != "ok":
                consecutive = 0
                continue
            evidence = _classify_douyin_login_snapshot(_mcp_text(result))
            consecutive = consecutive + 1 if evidence["authenticated"] else 0
            _mcp_login_attempts[account_id] = {
                **attempt, "detection": {
                    "state": "authenticated_candidate" if consecutive else "awaiting_user",
                    "consecutive": consecutive,
                    **evidence,
                },
            }
            if consecutive < 2:
                continue
            account = _persist_mcp_authenticated_account(account_id, platform)
            close_result = await _get_mcp_broker().call_account_scoped_browser(
                _get_mcp_manager(), "playwright_browser", platform, account_id,
                "browser_close", {}, browser_ctx=ctx, approved=True,
            )
            await _get_mcp_manager().stop(platform, account_id)
            timeout_task = _mcp_login_timeout_tasks.pop(account_id, None)
            if timeout_task:
                timeout_task.cancel()
            _mcp_login_attempts[account_id] = {
                **_mcp_login_attempts[account_id], "status": "authenticated",
                "ended_at": datetime.now().isoformat(), "account": account,
                "window_closed": close_result.get("status") == "ok",
            }
            return
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        attempt = _mcp_login_attempts.get(account_id)
        if attempt and attempt.get("login_attempt_id") == attempt_id:
            _mcp_login_attempts[account_id] = {
                **attempt, "status": "error", "reason": str(exc)[:500],
                "ended_at": datetime.now().isoformat(),
            }
            await _get_mcp_manager().stop(attempt["platform"], account_id)
    finally:
        current = _mcp_login_monitor_tasks.get(account_id)
        if current is asyncio.current_task():
            _mcp_login_monitor_tasks.pop(account_id, None)


@app.post("/api/plugins/marketing-os/accounts/{account_id}/mcp-login/start")
async def mcp_login_start(account_id: str, body: dict):
    if not _mcp_login_enabled():
        raise HTTPException(409, "MCP login is not enabled (MARKETING_OS_MCP_LOGIN_ENABLED=1)")

    platform = str(body.get("platform", "douyin")).strip().lower()
    if platform != "douyin":
        raise HTTPException(400, f"only douyin supported, got {platform!r}")

    # reject renderer-supplied dangerous fields
    for forbidden in ("command", "args", "url", "tool_name", "executable_path",
                       "cookie", "approved", "capability_level", "user_data_dir"):
        if forbidden in body:
            raise HTTPException(400, f"field {forbidden!r} not allowed in start body")

    timeout = int(body.get("timeout", _LOGIN_TIMEOUT_DEFAULT))
    timeout = max(_LOGIN_TIMEOUT_MIN, min(timeout, _LOGIN_TIMEOUT_MAX))

    global _mcp_login_counter
    _mcp_login_counter += 1
    attempt_id = f"login_{account_id}_{_mcp_login_counter}"

    # Check existing attempt
    existing = _mcp_login_attempts.get(account_id)
    if existing and existing.get("status") in ("starting", "browser_open"):
        return existing

    mgr = _get_mcp_manager()
    _mcp_login_attempts[account_id] = {
        "login_attempt_id": attempt_id, "account_id": account_id,
        "platform": platform, "status": "starting",
        "started_at": datetime.now().isoformat(), "timeout": timeout,
    }
    result = await mgr.start(platform, account_id, headless=False)

    if result.get("status") not in ("healthy",):
        return {"login_attempt_id": attempt_id, "account_id": account_id,
                "status": "error", "reason": result.get("reason", "mcp_start_failed"),
                "detail": result}

    # navigate to official login URL
    from agent_core.mcp_browser_policy import BrowserActionContext
    ctx = BrowserActionContext(
        platform=platform, account_id=account_id,
        capability="marketing_session_login",
        user_id="default", approved=True,
    )
    try:
        nav_result = await _get_mcp_broker().call_account_scoped_browser(
            mgr, "playwright_browser", platform, account_id,
            "browser_navigate", {"url": _OFFICIAL_LOGIN_URLS[platform]},
            browser_ctx=ctx, approved=True,
        )
    except (PermissionError, ValueError) as exc:
        await mgr.stop(platform, account_id)
        attempt = {**_mcp_login_attempts[account_id], "status": "error", "reason": str(exc)}
        _mcp_login_attempts[account_id] = attempt
        return attempt
    if nav_result.get("status") != "ok":
        await mgr.stop(platform, account_id)
        attempt = {**_mcp_login_attempts[account_id], "status": "error",
                   "reason": nav_result.get("reason", "navigation_failed")}
        _mcp_login_attempts[account_id] = attempt
        return attempt

    attempt = {
        "login_attempt_id": attempt_id, "account_id": account_id,
        "platform": platform, "status": "browser_open",
        "started_at": datetime.now().isoformat(),
        "timeout": timeout,
    }
    _mcp_login_attempts[account_id] = attempt
    old_task = _mcp_login_timeout_tasks.pop(account_id, None)
    if old_task:
        old_task.cancel()
    _mcp_login_timeout_tasks[account_id] = asyncio.create_task(
        _expire_mcp_login(account_id, attempt_id, timeout)
    )
    old_monitor = _mcp_login_monitor_tasks.pop(account_id, None)
    if old_monitor:
        old_monitor.cancel()
    _mcp_login_monitor_tasks[account_id] = asyncio.create_task(
        _monitor_mcp_login(account_id, attempt_id)
    )
    return {**attempt, "navigate_result": nav_result.get("status")}


@app.get("/api/plugins/marketing-os/accounts/{account_id}/mcp-login/status")
def mcp_login_status(account_id: str):
    if not _mcp_login_enabled():
        raise HTTPException(409, "MCP login is not enabled")
    attempt = _mcp_login_attempts.get(account_id)
    if attempt is None:
        return {"account_id": account_id, "status": "idle"}
    return attempt


@app.post("/api/plugins/marketing-os/accounts/{account_id}/mcp-login/cancel")
async def mcp_login_cancel(account_id: str, body=None):
    if not _mcp_login_enabled():
        raise HTTPException(409, "MCP login is not enabled")

    body = body or {}
    req_attempt_id = str(body.get("login_attempt_id", "")).strip()
    attempt = _mcp_login_attempts.get(account_id)

    if req_attempt_id and attempt and attempt.get("login_attempt_id") != req_attempt_id:
        raise HTTPException(409, "login_attempt_id does not match current attempt")

    mgr = _get_mcp_manager()
    timeout_task = _mcp_login_timeout_tasks.pop(account_id, None)
    if timeout_task:
        timeout_task.cancel()
    monitor_task = _mcp_login_monitor_tasks.pop(account_id, None)
    if monitor_task:
        monitor_task.cancel()
    await mgr.stop(attempt["platform"], account_id) if attempt else None

    _mcp_login_attempts[account_id] = {
        "account_id": account_id, "status": "cancelled",
        "login_attempt_id": req_attempt_id or (attempt.get("login_attempt_id") if attempt else ""),
    }
    return _mcp_login_attempts[account_id]


# ---- MCP-08 headed/headless handoff ----

@app.get("/api/plugins/marketing-os/accounts/{account_id}/mcp-browser/status")
async def mcp_browser_status(account_id: str):
    account = _require_connected_account(account_id)
    state = await _get_mcp_manager().get(account["platform"], account_id)
    return state or {"account_id": account_id, "platform": account["platform"],
                     "status": "absent", "headless": None}


@app.post("/api/plugins/marketing-os/accounts/{account_id}/mcp-browser/background")
async def mcp_browser_background(account_id: str):
    if not _mcp_login_enabled():
        raise HTTPException(409, "MCP browser is not enabled")
    account = _require_connected_account(account_id)
    result = await _get_mcp_manager().ensure_mode(
        account["platform"], account_id, headless=True,
    )
    if result.get("status") != "healthy":
        raise HTTPException(503, result.get("reason", "MCP browser unavailable"))
    return result


@app.post("/api/plugins/marketing-os/accounts/{account_id}/mcp-browser/takeover")
async def mcp_browser_takeover(account_id: str):
    if not _mcp_login_enabled():
        raise HTTPException(409, "MCP browser is not enabled")
    account = _require_connected_account(account_id)
    platform = account["platform"]
    manager = _get_mcp_manager()
    result = await manager.ensure_mode(platform, account_id, headless=False)
    if result.get("status") != "healthy":
        raise HTTPException(503, result.get("reason", "MCP browser unavailable"))
    from agent_core.mcp_browser_policy import BrowserActionContext
    ctx = BrowserActionContext(
        platform=platform, account_id=account_id,
        capability="marketing_session_login", user_id="default", approved=True,
    )
    navigation = await _get_mcp_broker().call_account_scoped_browser(
        manager, "playwright_browser", platform, account_id, "browser_navigate",
        {"url": _OFFICIAL_LOGIN_URLS[platform]}, browser_ctx=ctx, approved=True,
    )
    if navigation.get("status") != "ok":
        await manager.stop(platform, account_id)
        raise HTTPException(503, navigation.get("reason", "browser navigation failed"))
    return {**result, "takeover": True}


@app.post("/api/plugins/marketing-os/accounts/{account_id}/mcp-browser/stop")
async def mcp_browser_stop(account_id: str):
    account = _require_connected_account(account_id)
    await _get_mcp_manager().stop(account["platform"], account_id)
    return {"account_id": account_id, "status": "absent", "stopped": True}


def _parse_compact_number(value: str) -> int:
    text = str(value or "").replace(",", "").strip().strip('"')
    match = re.search(r"([\d.]+)\s*([万亿]?)", text)
    if not match:
        return 0
    number = float(match.group(1))
    return round(number * ({"万": 10_000, "亿": 100_000_000}.get(match.group(2), 1)))


def _parse_creator_account_snapshot(text: str) -> dict:
    username_match = re.search(r"抖音号[：:]\s*([^\s\n]+)", text)
    label_match = re.search(
        r"^[ \t]*- generic \[ref=e\d+\]:[ \t]*([^\n]+)\n"
        r"[ \t]*- generic \[ref=e\d+\]:[ \t]*抖音号[：:]",
        text, re.MULTILINE,
    )
    def metric(label: str) -> int:
        match = re.search(
            rf"text:\s*{re.escape(label)}\s*\n\s*- generic \[ref=e\d+\]:\s*([^\n]+)", text,
        )
        return _parse_compact_number(match.group(1)) if match else 0
    latest_view = re.search(
        r"generic \[ref=e\d+\]:\s*播放量\s*\n\s*- generic \[ref=e\d+\]:\s*([^\n]+)", text,
    )
    return {
        "identity": {
            "username": username_match.group(1).strip('"') if username_match else "",
            "label": label_match.group(1).strip().strip('"') if label_match else "",
        },
        "stats": {
            "followers": metric("粉丝"),
            "total_likes": metric("获赞"),
            "total_views": _parse_compact_number(latest_view.group(1)) if latest_view else 0,
        },
    }


def _parse_creator_trend_snapshot(text: str) -> list[dict]:
    pattern = re.compile(
        r"^[ \t]*- generic \[ref=e\d+\]:[ \t]*(?!\"?\d+\"?[ \t]*$)([^\n]{2,240})\n"
        r"[ \t]*- generic \[ref=e\d+\]:[ \t]*\n"
        r"[ \t]*- text:[ \t]*(播放量|热度)[ \t]*\n"
        r"[ \t]*- generic \[ref=e\d+\]:[ \t]*([^\n]+)",
        re.MULTILINE,
    )
    items, seen = [], set()
    for match in pattern.finditer(text):
        title = match.group(1).strip().strip('"')
        if title in seen or title in {"粉丝", "获赞", "关注"}:
            continue
        seen.add(title)
        heat_text = match.group(3).strip().strip('"')
        items.append({
            "rank": len(items) + 1, "title": title[:200],
            "heat_text": heat_text, "heat_value": _parse_compact_number(heat_text),
            "metric": match.group(2), "url": "",
        })
    return items[:30]


async def _mcp_snapshot_for_account(account: dict, capability: str, *, depth: int = 15) -> str:
    from agent_core.mcp_browser_policy import BrowserActionContext
    platform, account_id = account["platform"], account["id"]
    manager = _get_mcp_manager()
    state = await manager.ensure_mode(platform, account_id, headless=True)
    if state.get("status") != "healthy":
        raise HTTPException(503, state.get("reason", "MCP browser unavailable"))
    ctx = BrowserActionContext(
        platform=platform, account_id=account_id, capability=capability,
        user_id="default", approved=True,
    )
    navigation = await _get_mcp_broker().call_account_scoped_browser(
        manager, "playwright_browser", platform, account_id, "browser_navigate",
        {"url": "https://creator.douyin.com/creator-micro/home"},
        browser_ctx=ctx, approved=True,
    )
    if navigation.get("status") != "ok":
        raise HTTPException(503, navigation.get("reason", "navigation failed"))
    latest = ""
    for delay in (2, 2, 3):
        await _get_mcp_broker().call_account_scoped_browser(
            manager, "playwright_browser", platform, account_id, "browser_wait_for",
            {"time": delay}, browser_ctx=ctx, approved=True,
        )
        snapshot = await _get_mcp_broker().call_account_scoped_browser(
            manager, "playwright_browser", platform, account_id, "browser_snapshot",
            {"depth": depth}, browser_ctx=ctx, approved=True,
        )
        if snapshot.get("status") != "ok":
            continue
        latest = _mcp_text(snapshot)
        if len(latest) > 10_000 and _classify_douyin_login_snapshot(latest)["authenticated"]:
            return latest
    if latest:
        return latest
    raise HTTPException(503, "creator center snapshot failed")


@app.post("/api/plugins/marketing-os/accounts/{account_id}/mcp-sync")
async def mcp_sync_account(account_id: str):
    if not _mcp_login_enabled():
        raise HTTPException(409, "MCP browser is not enabled")
    lock = _mcp_account_operation_locks.setdefault(account_id, asyncio.Lock())
    async with lock:
        account = _require_connected_account(account_id)
        parsed = _parse_creator_account_snapshot(
            await _mcp_snapshot_for_account(account, "marketing_accounts_sync")
        )
        if parsed["identity"]["username"] or parsed["identity"]["label"]:
            from marketing_tools.account import update_account_identity
            update_account_identity({"account_id": account_id, **parsed["identity"]})
        if not any(parsed["stats"].values()):
            raise HTTPException(422, "创作者中心已打开，但未识别到账号指标")
        return {**parsed["stats"], "source": "playwright_mcp_creator_center",
                "identity": parsed["identity"]}


@app.post("/api/plugins/marketing-os/accounts/{account_id}/mcp-trending")
async def mcp_collect_trending(account_id: str, body: dict):
    if not _mcp_login_enabled():
        raise HTTPException(409, "MCP browser is not enabled")
    keyword = str(body.get("keyword", "")).strip()
    if not keyword or len(keyword) > 100:
        raise HTTPException(400, "keyword required and must be <= 100 characters")
    lock = _mcp_account_operation_locks.setdefault(account_id, asyncio.Lock())
    async with lock:
        return await _mcp_collect_trending_locked(account_id, keyword)


async def _mcp_collect_trending_locked(account_id: str, keyword: str):
    account = _require_connected_account(account_id)
    text = await _mcp_snapshot_for_account(account, "marketing_trending_search")
    from agent_core.mcp_browser_policy import BrowserActionContext
    match = re.search(r'tab "热门话题"[^\n]*\[ref=(e\d+)\]', text)
    if match:
        ctx = BrowserActionContext(
            platform="douyin", account_id=account_id,
            capability="marketing_trending_search", user_id="default", approved=True,
        )
        manager = _get_mcp_manager()
        clicked = await _get_mcp_broker().call_account_scoped_browser(
            manager, "playwright_browser", "douyin", account_id, "browser_click",
            {"element": "热门话题", "target": match.group(1)},
            browser_ctx=ctx, approved=True,
        )
        if clicked.get("status") == "ok":
            await _get_mcp_broker().call_account_scoped_browser(
                manager, "playwright_browser", "douyin", account_id, "browser_wait_for",
                {"time": 1}, browser_ctx=ctx, approved=True,
            )
            snapshot = await _get_mcp_broker().call_account_scoped_browser(
                manager, "playwright_browser", "douyin", account_id, "browser_snapshot",
                {"depth": 15}, browser_ctx=ctx, approved=True,
            )
            if snapshot.get("status") == "ok":
                text = _mcp_text(snapshot)
    items = _parse_creator_trend_snapshot(text)
    print(
        f"[mcp:trending] account={account_id} snapshot_chars={len(text)} "
        f"items={len(items)} redacted={text == '[REDACTED]'}",
        file=sys.stderr,
    )
    terms = [term.lower() for term in re.split(r"[\s,，/]+", keyword) if term]
    matched = [item for item in items if any(term in item["title"].lower() for term in terms)]
    selected = matched or items
    if not selected:
        raise HTTPException(422, "创作者中心未返回可解析热点")
    return {
        "platform": "douyin", "keyword": keyword, "items": selected[:30],
        "collected_at": datetime.now().isoformat(),
        "source": "playwright_mcp_creator_center",
        "matched_keyword": bool(matched),
        "note": "来自当前登录账号创作者中心；无关键词命中时返回账号个性化热点",
    }


# ---- 记忆系统 ----

@app.get("/api/plugins/marketing-os/memories")
def list_agent_memories(kind: str | None = None, account_id: str | None = None):
    try:
        svc = _get_agent_service()
        store = svc.get_store()
        return store.list_memories(user_id="default", kind=kind, account_id=account_id, status=None)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/plugins/marketing-os/memories")
def create_agent_memory(body: dict):
    try:
        svc = _get_agent_service()
        store = svc.get_store()
        kind = str(body.get("kind", "user"))
        content = str(body.get("content", ""))
        if not content.strip():
            raise HTTPException(400, "content is required")
        candidate = store.add_memory_candidate(
            kind=MemoryKind(kind),
            user_id="default",
            content=content[:2000],
            confidence=float(body.get("confidence", 0.8)),
            evidence=[{"source": "user_explicit", "surface": "memory_page"}],
            account_id=body.get("account_id"),
            platform=body.get("platform"),
        )
        if candidate["status"] == "pending":
            candidate = store.update_memory_candidate(candidate["id"], status="verified")
        return candidate
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "failed to create memory")


@app.put("/api/plugins/marketing-os/memories/{candidate_id}")
def update_agent_memory(candidate_id: str, body: dict):
    try:
        svc = _get_agent_service()
        return svc.get_store().update_memory_candidate(
            candidate_id, status=body.get("status"), content=body.get("content"),
        )
    except KeyError:
        raise HTTPException(404, "memory not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/plugins/marketing-os/memories/{candidate_id}")
def delete_agent_memory(candidate_id: str):
    try:
        svc = _get_agent_service()
        store = svc.get_store()
        store.delete_memory(candidate_id)
        return {"deleted": True, "id": candidate_id}
    except KeyError:
        raise HTTPException(404, "memory not found")


# ---- 授权管理 ----

@app.get("/api/plugins/marketing-os/authorizations")
def list_authorizations():
    try:
        svc = _get_agent_service()
        store = svc.get_store()
        return store.list_authorizations("default")
    except Exception:
        return []


@app.delete("/api/plugins/marketing-os/authorizations/{capability}")
def revoke_authorization_endpoint(capability: str):
    try:
        svc = _get_agent_service()
        svc.revoke_authorization("default", capability)
        return {"revoked": True, "capability": capability}
    except KeyError:
        raise HTTPException(404, "authorization not found")


# ---- 内容资产 ----

@app.get("/api/plugins/marketing-os/content/assets")
def list_content_assets(status: str | None = None, type: str | None = None, account_id: str | None = None):
    try:
        svc = _get_agent_service()
        return svc.get_store().list_content_assets(status=status, type=type, account_id=account_id)
    except Exception:
        return []


@app.post("/api/plugins/marketing-os/content/assets")
def create_content_asset_endpoint(body: dict):
    try:
        svc = _get_agent_service()
        store = svc.get_store()
        title = str(body.get("title", ""))
        if not title.strip():
            raise HTTPException(400, "title is required")
        asset = store.create_content_asset(
            title=title[:200],
            type=str(body.get("type", "script")),
            account_id=body.get("account_id"),
            platform=body.get("platform"),
            content=body.get("content"),
        )
        return asset
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.put("/api/plugins/marketing-os/content/assets/{asset_id}/status")
def transition_content_asset(asset_id: str, body: dict):
    new_status = str(body.get("status", ""))
    if not new_status:
        raise HTTPException(400, "status is required")
    try:
        svc = _get_agent_service()
        return svc.get_store().transition_content_asset(asset_id, new_status)
    except KeyError:
        raise HTTPException(404, "asset not found")
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/plugins/marketing-os/content/assets/{asset_id}/metrics")
def update_content_metrics(asset_id: str, body: dict):
    try:
        svc = _get_agent_service()
        return svc.get_store().update_content_metrics(asset_id, body)
    except KeyError:
        raise HTTPException(404, "asset not found")


@app.delete("/api/plugins/marketing-os/content/assets/{asset_id}")
def delete_content_asset(asset_id: str):
    try:
        svc = _get_agent_service()
        svc.get_store().delete_content_asset(asset_id)
        return {"deleted": True, "id": asset_id}
    except KeyError:
        raise HTTPException(404, "asset not found")


# ---- 选题建议 ----

@app.get("/api/plugins/marketing-os/suggestions")
def get_suggestions():
    cache_file = CONFIG_DIR / "suggestions-cache.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    return {"status": "no_data", "message": "尚未生成内容建议"}


# ---- 概览 ----

@app.get("/api/plugins/marketing-os/dashboard/overview")
def dashboard_overview():
    accounts = _read_json(CONFIG_DIR / "accounts.json", {"accounts": []}).get("accounts", [])
    trending = _read_json(CONFIG_DIR / "trending-cache.json", {})
    suggestions = _read_json(CONFIG_DIR / "suggestions-cache.json", {})
    total_followers = sum(
        int((account.get("stats") or {}).get("followers", 0) or 0)
        for account in accounts
    )
    follower_growth = sum(
        int((account.get("stats") or {}).get("follower_growth_today", 0) or 0)
        for account in accounts
    )
    return {
        "today": datetime.now().isoformat(),
        "accounts_connected": len(accounts),
        "trending_topics_today": len(trending.get("top_trends", [])),
        "suggestions_generated": len(suggestions.get("suggestions", [])),
        "videos_published": 0,
        "total_followers": total_followers,
        "follower_growth_today": follower_growth,
    }


# ---- 画像 ----

@app.get("/api/plugins/marketing-os/profiles")
def get_profiles():
    pf = CONFIG_DIR / "user-profiles.yaml"
    if pf.exists():
        import yaml
        data = yaml.safe_load(pf.read_text())
        return {"profiles": data.get("profiles", [])}
    return {"profiles": []}


@app.put("/api/plugins/marketing-os/profiles/{profile_id}")
def update_profile(profile_id: str, body: dict):
    import yaml
    profile_file = CONFIG_DIR / "user-profiles.yaml"
    data = yaml.safe_load(profile_file.read_text()) if profile_file.exists() else {"profiles": []}
    data = data or {"profiles": []}
    profiles = data.setdefault("profiles", [])
    for index, profile in enumerate(profiles):
        if profile.get("id") == profile_id:
            profiles[index] = {**profile, **body, "id": profile_id}
            break
    else:
        profiles.append({**body, "id": profile_id})
    profile_file.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    return {"success": True, "profile": next(p for p in profiles if p.get("id") == profile_id)}


@app.get("/api/plugins/marketing-os/assistant/status")
def assistant_status():
    try:
        return _get_agent_service().runtime_status()
    except Exception as exc:
        return {"available": False, "backend": "hermes-source", "error": str(exc)}


# ---- 发布、分析与自动化 ----

WORKFLOW_DEFAULT = {"enabled": False, "schedule_time": "08:03", "last_run": None, "last_result": None}
_workflow_lock = threading.Lock()


def _workflow_state() -> dict:
    return {**WORKFLOW_DEFAULT, **_read_json(CONFIG_DIR / "workflow-state.json", WORKFLOW_DEFAULT.copy())}


def _parse_schedule_time(value: str) -> tuple[int, int]:
    try:
        hour, minute = (int(part) for part in value.split(":", 1))
    except (AttributeError, TypeError, ValueError):
        raise HTTPException(400, "schedule_time must use HH:MM")
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise HTTPException(400, "schedule_time must use HH:MM")
    return hour, minute


def _workflow_due(state: dict, now: datetime | None = None) -> bool:
    if not state.get("enabled"):
        return False
    now = now or datetime.now()
    hour, minute = _parse_schedule_time(state.get("schedule_time", "08:03"))
    scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    last_run = state.get("last_run")
    last_date = datetime.fromisoformat(last_run).date() if last_run else None
    return now >= scheduled and last_date != now.date()


def _next_workflow_run(state: dict, now: datetime | None = None) -> str | None:
    if not state.get("enabled"):
        return None
    now = now or datetime.now()
    hour, minute = _parse_schedule_time(state.get("schedule_time", "08:03"))
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    last_run = state.get("last_run")
    last_date = datetime.fromisoformat(last_run).date() if last_run else None
    if candidate < now and last_date == now.date():
        candidate += timedelta(days=1)
    return candidate.isoformat()


def _approval_timeout_seconds() -> float:
    """Read a bounded approval timeout; reject unsafe or malformed values."""
    try:
        configured = float(os.environ.get("MARKETING_OS_APPROVAL_TIMEOUT_SECONDS", "300"))
    except (TypeError, ValueError):
        configured = 300.0
    return min(max(configured, 30.0), 3600.0)


async def _run_scheduler_cycle() -> dict:
    """Run one production scheduler cycle, including desktop-owned sessions."""
    result = {"expired_approvals": 0, "workflow_started": False}
    svc = _get_agent_service()
    if svc is not None:
        expired = await asyncio.to_thread(
            svc.get_store().expire_stale_approvals,
            _approval_timeout_seconds(),
        )
        result["expired_approvals"] = len(expired)

    # Electron owns the interactive workflow worker, but the Python durable
    # store still owns approval expiry.  Only the daily workflow is skipped.
    if os.environ.get("MARKETING_OS_SESSION_ORCHESTRATOR") != "electron":
        state = _workflow_state()
        if _workflow_due(state):
            await asyncio.to_thread(run_workflow, {"source": "schedule"})
            result["workflow_started"] = True
    return result


async def _scheduler_loop():
    """Small persistent scheduler; the Electron-owned backend is the single worker.

    On each cycle the scheduler:
    1. Expires stale pending approvals (default 5 min, configurable via
       ``MARKETING_OS_APPROVAL_TIMEOUT_SECONDS``).
    2. Runs the daily trending-refresh workflow if due.
    """
    await asyncio.sleep(2)
    while True:
        try:
            await _run_scheduler_cycle()
        except Exception as exc:
            state = _workflow_state()
            state["scheduler_error"] = str(exc)
            _write_json(CONFIG_DIR / "workflow-state.json", state)
        try:
            interval = int(os.environ.get("MARKETING_OS_SCHEDULER_INTERVAL", "30"))
        except (TypeError, ValueError):
            interval = 30
        await asyncio.sleep(min(max(interval, 1), 300))

@app.get("/api/plugins/marketing-os/publishing/tasks")
def publishing_tasks():
    data = _read_json(CONFIG_DIR / "publishing.json", {"tasks": []})
    return {"tasks": data.get("tasks", []), "total": len(data.get("tasks", []))}


@app.post("/api/plugins/marketing-os/publishing/tasks")
def create_publishing_task(body: dict):
    import uuid
    title = str(body.get("title", "")).strip()
    if not title:
        raise HTTPException(400, "title required")
    data = _read_json(CONFIG_DIR / "publishing.json", {"tasks": []})
    task = {
        "id": f"pub_{uuid.uuid4().hex[:12]}",
        "title": title,
        "platform": body.get("platform", "douyin"),
        "status": body.get("status", "review"),
        "scheduled_at": body.get("scheduled_at"),
        "created_at": datetime.now().isoformat(),
        "metrics": {},
    }
    data.setdefault("tasks", []).append(task)
    _write_json(CONFIG_DIR / "publishing.json", data)
    return {"success": True, "task": task}


@app.delete("/api/plugins/marketing-os/publishing/tasks/{task_id}")
def delete_publishing_task(task_id: str):
    data = _read_json(CONFIG_DIR / "publishing.json", {"tasks": []})
    before = len(data.get("tasks", []))
    data["tasks"] = [task for task in data.get("tasks", []) if task.get("id") != task_id]
    if len(data["tasks"]) == before:
        raise HTTPException(404, "发布任务不存在")
    _write_json(CONFIG_DIR / "publishing.json", data)
    return {"success": True, "removed": task_id}


# ---- SQL-backed publishing tasks (agent-facing) ----

@app.get("/api/plugins/marketing-os/publishing/sql-tasks")
def list_sql_publishing_tasks(status: str | None = None, platform: str | None = None):
    svc = _get_agent_service()
    if svc is None:
        return {"tasks": [], "total": 0}
    tasks = svc.get_store().list_publishing_tasks(status=status, platform=platform)
    return {"tasks": tasks, "total": len(tasks)}


@app.post("/api/plugins/marketing-os/publishing/sql-tasks")
def create_sql_publishing_task(body: dict):
    svc = _get_agent_service()
    asset_id = str(body.get("asset_id", "")).strip()
    if not asset_id:
        raise HTTPException(400, "asset_id required")
    platform = str(body.get("platform", "douyin"))
    try:
        task = svc.get_store().create_publishing_task(asset_id=asset_id, platform=platform)
        return {"success": True, "task": task}
    except KeyError:
        raise HTTPException(404, "asset not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/plugins/marketing-os/publishing/sql-tasks/{task_id}/complete")
def complete_sql_publishing_task(task_id: str, body: dict):
    svc = _get_agent_service()
    effect_id = str(body.get("effect_id", "")).strip()
    receipt = body.get("receipt") or {}
    try:
        task = svc.get_store().complete_publishing_task(
            task_id, effect_id=effect_id, receipt=receipt,
        )
        return {"success": True, "task": task}
    except KeyError:
        raise HTTPException(404, "task not found")


@app.post("/api/plugins/marketing-os/publishing/sql-tasks/{task_id}/metrics")
def collect_publishing_metrics(task_id: str, body: dict):
    svc = _get_agent_service()
    metrics = body.get("metrics") or {}
    try:
        task = svc.get_store().collect_metrics(task_id, metrics)
        return {"success": True, "task": task}
    except KeyError:
        raise HTTPException(404, "task not found")


@app.get("/api/plugins/marketing-os/analytics/summary")
def analytics_summary():
    accounts = _read_json(CONFIG_DIR / "accounts.json", {"accounts": []}).get("accounts", [])
    publishing = _read_json(CONFIG_DIR / "publishing.json", {"tasks": []}).get("tasks", [])
    metrics = [task.get("metrics") or {} for task in publishing]
    return {
        "views": sum(int(item.get("views", 0) or 0) for item in metrics),
        "engagements": sum(int(item.get("engagements", 0) or 0) for item in metrics),
        "comments": sum(int(item.get("comments", 0) or 0) for item in metrics),
        "follower_growth": sum(int((account.get("stats") or {}).get("follower_growth_today", 0) or 0) for account in accounts),
        "published_count": sum(1 for task in publishing if task.get("status") == "published"),
        "connected_accounts": len(accounts),
        "daily_views": [],
    }


@app.get("/api/plugins/marketing-os/intelligence/config")
def intelligence_config():
    return _read_json(CONFIG_DIR / "intelligence-config.json", {
        "industries": [], "platforms": ["douyin"], "sync_accounts": True,
    })


@app.put("/api/plugins/marketing-os/intelligence/config")
def update_intelligence_config(body: dict):
    current = intelligence_config()
    if "industries" in body:
        if not isinstance(body["industries"], list):
            raise HTTPException(400, "industries must be a list")
        industries = []
        for value in body["industries"][:10]:
            normalized = str(value).strip()
            if normalized and normalized not in industries:
                industries.append(normalized[:50])
        current["industries"] = industries
    if "platforms" in body:
        requested = body["platforms"] if isinstance(body["platforms"], list) else []
        current["platforms"] = [platform for platform in requested if platform in {"douyin"}] or ["douyin"]
    if "sync_accounts" in body:
        current["sync_accounts"] = bool(body["sync_accounts"])
    _write_json(CONFIG_DIR / "intelligence-config.json", current)
    return current


@app.get("/api/plugins/marketing-os/intelligence/report")
def intelligence_report():
    return _read_json(CONFIG_DIR / "intelligence-report.json", {"status": "never_run", "steps": [], "errors": []})


@app.post("/api/plugins/marketing-os/intelligence/report")
def save_intelligence_report(body: dict):
    allowed_status = {"completed", "partial", "failed", "running"}
    report = {
        "status": body.get("status") if body.get("status") in allowed_status else "failed",
        "started_at": body.get("started_at"),
        "completed_at": body.get("completed_at") or datetime.now().isoformat(),
        "steps": body.get("steps") if isinstance(body.get("steps"), list) else [],
        "errors": body.get("errors") if isinstance(body.get("errors"), list) else [],
        "summary": body.get("summary") if isinstance(body.get("summary"), dict) else {},
    }
    _write_json(CONFIG_DIR / "intelligence-report.json", report)
    return report


@app.get("/api/plugins/marketing-os/workflow/status")
def workflow_status():
    state = _workflow_state()
    return {**state, "running": _workflow_lock.locked(), "due": _workflow_due(state), "next_run": _next_workflow_run(state)}


def get_memories(params: dict | None = None) -> list:
    params = params or {}
    svc = _get_agent_service()
    store = svc.get_store()
    memories = []
    for status in ("verified", "locked"):
        memories.extend(store.list_memories(
            user_id=str(params.get("__user_id", "default")),
            kind=params.get("kind"), account_id=params.get("account_id"),
            workspace=params.get("workspace") or None, status=status,
        ))
    return memories[:max(1, min(int(params.get("limit", 20)), 50))]


def get_content_assets(params: dict | None = None) -> list:
    params = params or {}
    svc = _get_agent_service()
    return svc.get_store().list_content_assets(
        status=params.get("status"), type=params.get("type"), account_id=params.get("account_id"),
    )


def create_content_asset(params: dict) -> dict:
    svc = _get_agent_service()
    store = svc.get_store()
    title = str(params.get("title", ""))
    if not title.strip():
        return {"status": "error", "reason": "title is required"}
    asset = store.create_content_asset(
        title=title[:200],
        type=str(params.get("type", "script")),
        account_id=params.get("account_id"),
        platform=params.get("platform"),
        content=params.get("content"),
    )
    return {"status": "ok", "id": asset["id"], "title": asset["title"]}


def add_memory(params: dict) -> dict:
    svc = _get_agent_service()
    store = svc.get_store()
    kind = str(params.get("kind", "user"))
    content = str(params.get("content", ""))
    if not content:
        return {"status": "rejected", "reason": "content is empty"}
    valid_kinds = {k.value for k in MemoryKind}
    if kind not in valid_kinds:
        return {"status": "rejected", "reason": f"unknown kind: {kind}"}
    user_id = str(params.get("__user_id", "default"))
    task_id = str(params.get("__task_id", ""))
    evidence = []
    if task_id:
        try:
            task = store.get_task(task_id)
            if task["user_id"] == user_id:
                evidence = [{"source": "agent_task", "task_id": task_id}]
        except KeyError:
            pass
    candidate = store.add_memory_candidate(
        kind=MemoryKind(kind),
        user_id=user_id,
        content=content[:2000],
        confidence=float(params.get("confidence", 0.8)),
        evidence=evidence,
        account_id=params.get("account_id"),
        platform=params.get("platform"),
        workspace=params.get("workspace") or None,
        supersede_previous=bool(params.get("supersede_previous", False)),
    )
    return {"status": candidate["status"], "id": candidate["id"], "kind": kind}


@app.put("/api/plugins/marketing-os/workflow/status")
def update_workflow_status(body: dict):
    state = _workflow_state()
    if "enabled" in body:
        state["enabled"] = bool(body["enabled"])
    if "schedule_time" in body:
        _parse_schedule_time(body["schedule_time"])
        state["schedule_time"] = body["schedule_time"]
    _write_json(CONFIG_DIR / "workflow-state.json", state)
    return workflow_status()


@app.post("/api/plugins/marketing-os/workflow/run")
def run_workflow(body: dict | None = None):
    if not _workflow_lock.acquire(blocking=False):
        raise HTTPException(409, "工作流正在运行")
    try:
        params = {key: value for key, value in (body or {}).items() if key != "source"}
        result = refresh_trending(params)
        state = _workflow_state()
        state.update({"last_run": datetime.now().isoformat(), "last_result": result, "scheduler_error": None})
        _write_json(CONFIG_DIR / "workflow-state.json", state)
        return {"status": "completed", "result": result, "last_run": state["last_run"]}
    finally:
        _workflow_lock.release()


@app.post("/api/plugins/marketing-os/workflow/complete")
def complete_workflow(body: dict):
    state = _workflow_state()
    state.update({
        "last_run": body.get("completed_at") or datetime.now().isoformat(),
        "last_result": body.get("summary") or {},
        "scheduler_error": None,
    })
    _write_json(CONFIG_DIR / "workflow-state.json", state)
    return workflow_status()


# ---- 工具直调 ----

@app.post("/api/tools/{tool_name}")
def call_tool(tool_name: str, body: dict = {}):
    """直接调用 marketing-os 工具"""
    try:
        if tool_name == "aggregate_all_trending":
            from marketing_tools.scraping import aggregate_all_trending
            return json.loads(aggregate_all_trending(body))
        elif tool_name == "scrape_douyin_trending":
            from marketing_tools.scraping import scrape_douyin_trending
            return json.loads(scrape_douyin_trending(body))
        elif tool_name == "scrape_weibo_trending":
            from marketing_tools.scraping import scrape_weibo_trending
            return json.loads(scrape_weibo_trending(body))
        elif tool_name == "scrape_bilibili_popular":
            from marketing_tools.scraping import scrape_bilibili_popular
            return json.loads(scrape_bilibili_popular(body))
        elif tool_name == "scrape_xiaohongshu_trending":
            from marketing_tools.scraping import scrape_xiaohongshu_trending
            return json.loads(scrape_xiaohongshu_trending(body))
        elif tool_name == "scrape_kuaishou_trending":
            from marketing_tools.scraping import scrape_kuaishou_trending
            return json.loads(scrape_kuaishou_trending(body))
        elif tool_name == "scrape_zhihu_trending":
            from marketing_tools.scraping import scrape_zhihu_trending
            return json.loads(scrape_zhihu_trending(body))
        elif tool_name == "scrape_wechat_trending":
            from marketing_tools.scraping import scrape_wechat_trending
            return json.loads(scrape_wechat_trending(body))
        elif tool_name == "scrape_tiktok_trending":
            from marketing_tools.scraping import scrape_tiktok_trending
            return json.loads(scrape_tiktok_trending(body))
        elif tool_name == "scrape_youtube_trending":
            from marketing_tools.scraping import scrape_youtube_trending
            return json.loads(scrape_youtube_trending(body))
        elif tool_name == "scrape_twitter_trending":
            from marketing_tools.scraping import scrape_twitter_trending
            return json.loads(scrape_twitter_trending(body))
        elif tool_name == "monitor_all":
            from marketing_tools.monitor import monitor_all
            return json.loads(monitor_all(body))
        elif tool_name == "analyze_trends":
            from marketing_tools.content import analyze_trends
            return json.loads(analyze_trends(body))
        elif tool_name == "generate_content_suggestions":
            from marketing_tools.content import generate_content_suggestions
            return json.loads(generate_content_suggestions(body))
        elif tool_name == "list_scraping_backends":
            from marketing_tools.scraping import list_scraping_backends
            return json.loads(list_scraping_backends(body))
        else:
            raise HTTPException(404, f"未知工具: {tool_name}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# ---- Agent runtime (new) ----

_agent_service: "HermesAgentService | None" = None
_agent_lock = threading.Lock()


def _get_agent_service() -> "HermesAgentService | None":
    global _agent_service
    if _agent_service is not None:
        return _agent_service

    with _agent_lock:
        if _agent_service is not None:
            return _agent_service

        # Ensure Hermes runtime paths before any agent_core imports
        _hermes_root = Path(os.environ.get("HERMES_AGENT_ROOT",
                            str(Path(__file__).parent.parent.parent / "runtime" / "hermes-agent")))
        _hermes_src = str(_hermes_root)
        if _hermes_src not in sys.path:
            sys.path.insert(0, _hermes_src)
        _hermes_site = str(_hermes_root / ".venv" / "lib" /
                           f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages")
        if Path(_hermes_site).exists() and _hermes_site not in sys.path:
            sys.path.insert(0, _hermes_site)

        try:
            from agent_core import HermesAgentService, AgentCoreStore, MemoryKind, TaskStatus
        except ImportError as exc:
            raise RuntimeError(f"Agent core 模块不可用: {exc}")

        agent_runtime_home = Path(os.environ.get("HERMES_HOME", CONFIG_DIR.parent / "agent-runtime"))
        agent_root = Path(os.environ.get("HERMES_AGENT_ROOT",
                          str(Path(__file__).parent.parent.parent / "runtime" / "hermes-agent")))
        store_path = CONFIG_DIR.parent / "agent-runtime" / "agent_core.db"

        store = AgentCoreStore(store_path)

        provider_env: dict[str, str] = {}
        secrets_env = os.environ.get(
            "MARKETING_OS_SECRETS_FILE",
            str(CONFIG_DIR.parent / "secrets" / "providers.env"),
        )
        try:
            with open(secrets_env) as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("export "):
                        line = line[7:]
                    sep = line.find("=")
                    if sep > 0:
                        key = line[:sep].strip()
                        value = line[sep+1:].strip().strip("\"'")
                        if key.isupper():
                            provider_env[key] = value
        except OSError:
            pass

        model = os.environ.get("MARKETING_OS_MODEL", provider_env.get("DEEPSEEK_MODEL", "deepseek-chat"))
        base_url = os.environ.get("MARKETING_OS_BASE_URL", provider_env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
        api_key = os.environ.get("MARKETING_OS_API_KEY", provider_env.get("DEEPSEEK_API_KEY", ""))

        _agent_service = HermesAgentService(
            store=store,
            hermes_home=agent_runtime_home,
            agent_root=agent_root,
            provider_env=provider_env,
            model=model,
            base_url=base_url,
            api_key=api_key,
            enabled_toolsets=["marketing-desktop"],
        )
        return _agent_service


@app.post("/agent/sessions")
async def agent_create_session(body: dict):
    user_id = str(body.get("user_id", "default") or "default").strip() or "default"
    svc = _get_agent_service()
    return await svc.create_session(user_id, body.get("workspace"))


@app.get("/agent/sessions/{session_id}")
async def agent_get_session(session_id: str):
    svc = _get_agent_service()
    result = await svc.get_session(session_id)
    if result is None:
        raise HTTPException(404, "会话不存在")
    return result


@app.post("/agent/messages")
async def agent_send_message(body: dict):
    session_id = str(body.get("session_id", "")).strip()
    message = str(body.get("message", "")).strip()
    if not session_id or not message:
        raise HTTPException(400, "session_id and message required")
    if len(message) > 8000:
        raise HTTPException(400, "message too long")
    account_id = str(body.get("account_id") or "").strip() or None
    account_specific = any(marker in message for marker in (
        "当前账号", "这个账号", "该账号", "抖音账号", "账号数据",
        "粉丝", "点赞", "播放", "同步账号",
    ))
    connected_accounts = [
        item for item in get_accounts().get("accounts", [])
        if item.get("status") == "connected"
    ]
    if account_id:
        if not any(item.get("id") == account_id for item in connected_accounts):
            raise HTTPException(409, "所选账号不存在或未连接，请重新选择账号")
    elif account_specific:
        if len(connected_accounts) == 1:
            account_id = connected_accounts[0].get("id")
        elif len(connected_accounts) > 1:
            raise HTTPException(409, "该任务需要指定账号，请先选择一个已连接账号")
        else:
            raise HTTPException(409, "该任务需要账号上下文，请先连接账号")

    svc = _get_agent_service()
    try:
        return await svc.send_message(session_id, message, account_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))


@app.get("/agent/runs/{task_id}")
async def agent_task_status(task_id: str):
    svc = _get_agent_service()
    return await svc.get_task_status(task_id)


@app.get("/agent/runs/{task_id}/events")
async def agent_task_events(task_id: str):
    svc = _get_agent_service()

    async def event_stream():
        async for event in svc.stream_events(task_id):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/agent/tasks/{task_id}/cancel")
async def agent_cancel_task(task_id: str):
    svc = _get_agent_service()
    return await svc.cancel_task(task_id)


@app.post("/agent/tasks/{task_id}/pause")
async def agent_pause_task(task_id: str):
    svc = _get_agent_service()
    try:
        return await svc.pause_task(task_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc))


@app.post("/agent/tasks/{task_id}/resume")
async def agent_resume_task(task_id: str):
    svc = _get_agent_service()
    try:
        return await svc.resume_task(task_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.get("/agent/approvals/{approval_id}")
async def agent_get_approval(approval_id: str):
    svc = _get_agent_service()
    store = svc.get_store()
    try:
        return store.get_approval(approval_id)
    except KeyError:
        raise HTTPException(404, "approval not found")


@app.post("/agent/approvals/{approval_id}/approve")
async def agent_approve(approval_id: str, body: dict | None = None):
    svc = _get_agent_service()
    reason = (body or {}).get("reason")
    scope = (body or {}).get("scope", "once")
    if scope not in {"once", "session", "permanent"}:
        raise HTTPException(400, "scope must be once, session, or permanent")
    store = svc.get_store()
    try:
        approval = store.get_approval(approval_id)
    except KeyError:
        raise HTTPException(404, "approval not found")
    task = store.get_task(approval["task_id"])
    if task["status"] == "cancelled":
        raise HTTPException(409, "task has been cancelled")
    if approval["status"] == "pending":
        result = await svc.decide_approval(approval_id, True, reason, transition_task=False)
    elif approval["status"] == "approved":
        result = approval
    else:
        raise HTTPException(409, f"approval is {approval['status']}")
    if scope != "once":
        task = store.get_task(approval["task_id"])
        svc.grant_authorization(
            task["user_id"], approval["capability"], scope=scope,
            session_id=task["session_id"], arguments=approval["arguments"],
        )
    return {**result, "scope": scope}


@app.post("/agent/approvals/{approval_id}/reject")
async def agent_reject(approval_id: str, body: dict | None = None):
    svc = _get_agent_service()
    reason = (body or {}).get("reason")
    result = await svc.decide_approval(
        approval_id, False, reason, transition_task=False,
    )
    await svc.resume_after_rejection(result["task_id"])
    return result


@app.post("/agent/effects/submit")
async def agent_submit_effect(body: dict):
    svc = _get_agent_service()
    approval_id = str(body.get("approval_id", "")).strip()
    receipt = body.get("receipt") or body.get("result") or {}
    idempotency_key = str(body.get("idempotency_key", "")).strip()

    if not approval_id:
        raise HTTPException(400, "approval_id is required")

    store = svc.get_store()

    try:
        approval = store.get_approval(approval_id)
    except KeyError:
        raise HTTPException(404, "approval not found")

    if approval["status"] != "approved":
        raise HTTPException(409, "approval must be approved before submitting effect")

    if not idempotency_key:
        idempotency_key = f"effect_{approval_id}"

    effect = store.create_effect_intent(
        task_id=approval["task_id"],
        capability=approval["capability"],
        idempotency_key=idempotency_key,
        preview=approval["arguments"],
        approval_id=approval_id,
    )

    result = store.record_effect_receipt(effect["id"], receipt)

    task = store.get_task(approval["task_id"])
    if task["status"] == "waiting_user":
        await svc.resume_after_effect(approval["task_id"])

    return {
        **result,
        "capability": approval["capability"],
        "arguments": approval["arguments"],
        "task_id": approval["task_id"],
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=19519)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    import sys
    print(f"marketing-os API server starting on {args.host}:{args.port}", file=sys.stderr)
    uvicorn.run(app, host=args.host, port=args.port, log_level="error")
