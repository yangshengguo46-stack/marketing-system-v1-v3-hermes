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
from datetime import date, datetime, timedelta, timezone

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
from agent_core import MemoryKind
from agent_core.mcp_broker import ProductMCPBroker, load_mcp_manifest

# Electron starts this file as ``python server.py``, so the live module name is
# ``__main__``. Agent tools later resolve server actions via ``import server``.
# Without this alias Python loads a second copy of this file, creating a second
# AgentService that pauses the currently running task as "runtime restarted".
if __name__ == "__main__":
    sys.modules.setdefault("server", sys.modules[__name__])

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
NATIVE_API_PREFIX = "/api/marketing-os"
LEGACY_PLUGIN_API_PREFIX = "/api/plugins/marketing-os"


@app.middleware("http")
async def require_local_api_token(request: Request, call_next):
    """Only localhost clients with the correct token may call the API."""
    if request.scope.get("path", "").startswith(NATIVE_API_PREFIX):
        request.scope["path"] = (
            LEGACY_PLUGIN_API_PREFIX
            + request.scope["path"][len(NATIVE_API_PREFIX):]
        )
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
DISABLED_TREND_PLATFORMS = {"weibo"}

def _without_disabled_trend_platforms(items):
    if not isinstance(items, list):
        return []
    return [
        item for item in items
        if not isinstance(item, dict)
        or str(item.get("source_platform", "")).lower() not in DISABLED_TREND_PLATFORMS
    ]

def _without_invalid_trends(items):
    if not isinstance(items, list):
        return []
    from marketing_tools.content import _invalid_trend_reason

    filtered = []
    for item in items:
        if not isinstance(item, dict):
            continue
        reason = _invalid_trend_reason(
            str(item.get("title") or item.get("trend") or ""),
            str(item.get("source_platform") or item.get("trend_source") or ""),
            str(item.get("source_category") or item.get("category") or ""),
        )
        if not reason:
            filtered.append(item)
    return filtered

def _sanitize_trending_payload(data: dict) -> dict:
    if not isinstance(data, dict):
        return data
    sanitized = {**data}
    sanitized["top_trends"] = _without_invalid_trends(_without_disabled_trend_platforms(sanitized.get("top_trends") or []))
    if isinstance(sanitized.get("categories"), dict):
        sanitized["categories"] = {
            category: filtered
            for category, items in sanitized["categories"].items()
            if (filtered := _without_invalid_trends(_without_disabled_trend_platforms(items)))
        }
    for key in ("platforms_scraped", "platforms_succeeded"):
        if isinstance(sanitized.get(key), list):
            sanitized[key] = [platform for platform in sanitized[key] if str(platform).lower() not in DISABLED_TREND_PLATFORMS]
    return sanitized

def _sanitize_suggestions_payload(data: dict) -> dict:
    if not isinstance(data, dict):
        return data
    sanitized = {**data}
    if isinstance(sanitized.get("suggestions"), list):
        sanitized["suggestions"] = _without_invalid_trends([
            suggestion for suggestion in sanitized["suggestions"]
            if not isinstance(suggestion, dict)
            or str(suggestion.get("trend_source", "")).lower() not in DISABLED_TREND_PLATFORMS
        ])
        sanitized["matched_trends_count"] = len(sanitized["suggestions"])
    return sanitized

def _account_trend_context(account_id: str = "", user_id: str = "default") -> dict:
    account_id = str(account_id or "").strip()
    user_id = str(user_id or "default").strip() or "default"
    if not account_id:
        return {}
    account = next(
        (item for item in _read_json(CONFIG_DIR / "accounts.json", {"accounts": []}).get("accounts", [])
         if str(item.get("id") or "") == account_id),
        {},
    )
    dna: dict = {}
    try:
        from agent_core import AccountLifecycleService
        lifecycle = AccountLifecycleService(_get_agent_service().get_store())
        project = lifecycle.get_active_project(user_id=user_id, account_id=account_id)
        if project is not None:
            projection = lifecycle.account_dna_projection(
                user_id=user_id, account_id=account_id, project_id=project["id"],
            )
            if isinstance(projection, dict):
                dna.update(projection)
    except Exception:
        pass
    if not dna:
        try:
            dna.update(_get_agent_service().get_store().get_account_dna(
                user_id=user_id, account_id=account_id,
            ))
        except Exception:
            pass
    return {
        "account_id": account_id,
        "platform": account.get("platform") or "",
        "dna": dna,
    }

@app.get("/api/plugins/marketing-os/trending")
def get_trending(account_id: str = "", user_id: str = "default"):
    cache_file = CONFIG_DIR / "trending-cache.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text())
        cached_at = data.get("cached_at")
        if cached_at and isinstance(cached_at, str):
            age = max(0, int((datetime.now() - datetime.fromisoformat(cached_at)).total_seconds()))
        else:
            age = 999999
        payload = _sanitize_trending_payload({**data, "cache_age_seconds": age})
        if account_id:
            from marketing_tools.content import rank_trends_for_context
            payload = rank_trends_for_context(
                payload, _account_trend_context(account_id, user_id), limit=30,
            )
        return payload
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
    account_id = str(params.get("account_id") or "").strip()
    user_id = str(params.get("__user_id") or params.get("user_id") or "default").strip() or "default"
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

    data = _sanitize_trending_payload(json.loads(cache_file.read_text()))
    if account_id:
        from marketing_tools.content import rank_trends_for_context
        data = rank_trends_for_context(data, _account_trend_context(account_id, user_id), limit=30)
    cached_at = data.get("cached_at")
    if cached_at and isinstance(cached_at, str):
        age = max(0, int((datetime.now() - datetime.fromisoformat(cached_at)).total_seconds()))
    else:
        age = 999999

    # Categories and top_trends are two views over the same cache. Flatten and
    # deduplicate them before filtering; returning unfiltered categories would
    # leak unrelated evidence back into the Agent even when top_trends matched
    # the query correctly.
    trends: list[dict] = []
    seen: set[tuple[str, str]] = set()
    groups = list((data.get("categories") or {}).values()) + [data.get("top_trends") or []]
    for group in groups:
        if not isinstance(group, list):
            continue
        for item in group:
            if not isinstance(item, dict) or not item.get("title"):
                continue
            key = (str(item.get("source_platform", "")), str(item["title"]))
            if key in seen:
                continue
            seen.add(key)
            trends.append(item)
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
    filtered_categories: dict[str, list[dict]] = {}
    for item in limited:
        filtered_categories.setdefault(str(item.get("category") or "其他"), []).append(item)

    return {
        **data,
        "query": query,
        "cache_age_seconds": age,
        "top_trends": limited,
        "categories": filtered_categories,
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
    platforms = [platform for platform in (requested or ["douyin", "bilibili", "xiaohongshu", "kuaishou", "zhihu"]) if str(platform).lower() not in DISABLED_TREND_PLATFORMS]
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

    raw["results"] = {
        platform: result for platform, result in (raw.get("results") or {}).items()
        if str(platform).lower() not in DISABLED_TREND_PLATFORMS
    }
    raw["platforms_scraped"] = [
        platform for platform in (raw.get("platforms_scraped") or list(raw["results"]))
        if str(platform).lower() not in DISABLED_TREND_PLATFORMS
    ]

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
    allowed = {
        "followers", "total_views", "engagements", "comments", "total_likes",
        "following", "videos_count", "total_shares", "total_collects",
        "total_comments", "interaction",
        "views_30d", "likes_30d", "comments_30d", "shares_30d",
        "new_followers_30d", "recent_30d",
    }
    stats = {}
    for key in allowed:
        if key in body:
            val = body[key]
            if key == "recent_30d":
                if isinstance(val, dict):
                    stats[key] = val
                continue
            try:
                stats[key] = int(val)
            except (TypeError, ValueError):
                raise HTTPException(400, f"{key} must be an integer")
    if not stats:
        raise HTTPException(400, "no supported metrics supplied")
    return {"success": True, "account": _update_account_stats(account_id, stats)}


@app.post("/api/plugins/marketing-os/accounts/{account_id}/video-metrics")
def upload_video_metrics(account_id: str, body: dict):
    _require_connected_account(account_id)
    videos = body.get("videos", [])
    if not isinstance(videos, list) or not videos:
        raise HTTPException(400, "videos must be a non-empty list")
    store = _get_agent_service().get_store()
    saved = 0
    for v in videos[:50]:
        if not isinstance(v, dict):
            continue
        title = str(v.get("title", "")).strip()[:500]
        if not title and not v.get("url"):
            continue
        try:
            metrics = {
                key: max(0, int(v.get(key, 0) or 0))
                for key in ("play_count", "like_count", "comment_count", "share_count", "collect_count")
            }
        except (TypeError, ValueError):
            raise HTTPException(400, "video metrics must be non-negative integers")
        store.add_video_metric(
            account_id=account_id, title=title,
            url=str(v.get("url", "")).strip()[:1000] or None, **metrics,
        )
        saved += 1
    return {"success": True, "saved": saved}


@app.get("/api/plugins/marketing-os/accounts/{account_id}/video-metrics")
def list_video_metrics(account_id: str):
    _require_connected_account(account_id)
    store = _get_agent_service().get_store()
    videos = store.list_video_metrics(account_id=account_id, limit=50)
    return {"videos": videos, "total": len(videos)}


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
    from marketing_tools.account import add_account, update_account_status, _read_accounts_db
    # If the account already exists (e.g. re-login), just mark it connected.
    db = _read_accounts_db()
    existing = next((item for item in db.get("accounts", []) if item.get("id") == account_id), None)
    if existing:
        result = json.loads(update_account_status({
            "account_id": account_id, "status": "connected",
        }))
        if result.get("success"):
            return result["account"]
        raise RuntimeError(result.get("error", "账号状态更新失败"))
    # New account — create with placeholder identity (real identity filled by sync).
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
    def metric_near(label: str) -> int:
        match = re.search(
            rf"generic \[ref=e\d+\]:\s*{re.escape(label)}\s*\n\s*- generic \[ref=e\d+\]:\s*([^\n]+)", text,
        )
        return _parse_compact_number(match.group(1)) if match else 0
    # Data center total views: nested structure like
    # generic: 播放量 \n - generic: \n - generic: "14"
    # or the tab pattern: generic: 播放量 \n - generic: \n - generic: 播放量 \n - generic: \n - generic: "14"
    dc_views = re.search(
        r'generic \[ref=e\d+\]:\s*播放量\s*\n'
        r'(?:\s*- generic \[ref=e\d+\]:\s*\n)?'
        r'\s*- generic \[ref=e\d+\]:\s*"?([\d.万亿]+)"?',
        text,
    )
    # Profile header views (播放量 near 粉丝/获赞)
    profile_views = re.search(
        r'text:\s*播放量\s*\n\s*- generic \[ref=e\d+\]:\s*"?([^"\n]+)"?',
        text,
    )
    followers = metric("粉丝")
    total_likes = metric("获赞")
    total_views = _parse_compact_number(dc_views.group(1)) if dc_views else (
        _parse_compact_number(profile_views.group(1)) if profile_views else 0
    )
    following = metric("关注") or metric_near("关注")
    videos_count = metric("作品") or metric_near("作品") or metric("视频") or metric_near("视频")
    total_shares = metric("分享") or metric_near("分享") or metric("转发") or metric_near("转发")
    total_collects = metric("收藏") or metric_near("收藏")
    total_comments = metric("评论") or metric_near("评论")

    # Recent 30-day data (from data center section)
    recent_30d = {}
    for label_30d, key in [
        ("近30天播放", "views_30d"), ("30天播放", "views_30d"),
        ("近30天点赞", "likes_30d"), ("30天点赞", "likes_30d"),
        ("近30天评论", "comments_30d"), ("30天评论", "comments_30d"),
        ("近30天分享", "shares_30d"), ("30天分享", "shares_30d"),
        ("近30天新增粉丝", "new_followers_30d"), ("30天新增粉丝", "new_followers_30d"),
        ("近30日涨粉", "new_followers_30d"),
    ]:
        val = metric_near(label_30d)
        if val and key not in recent_30d:
            recent_30d[key] = val

    stats = {
        "followers": followers,
        "total_likes": total_likes,
        "total_views": total_views,
        "following": following,
        "videos_count": videos_count,
        "total_shares": total_shares,
        "total_collects": total_collects,
        "total_comments": total_comments,
    }
    if recent_30d:
        stats["recent_30d"] = recent_30d
    return {
        "identity": {
            "username": username_match.group(1).strip('"') if username_match else "",
            "label": label_match.group(1).strip().strip('"') if label_match else "",
        },
        "stats": stats,
    }


def _parse_creator_trend_snapshot(text: str) -> list[dict]:
    from marketing_tools.content import _invalid_trend_reason

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
        invalid_reason = _invalid_trend_reason(title, "douyin")
        if invalid_reason:
            continue
        seen.add(title)
        heat_text = match.group(3).strip().strip('"')
        items.append({
            "rank": len(items) + 1, "title": title[:200],
            "heat_text": heat_text, "heat_value": _parse_compact_number(heat_text),
            "metric": match.group(2), "url": "",
        })
    return items[:30]


def _parse_creator_video_list(text: str) -> list[dict]:
    """Extract per-video metrics from creator center accessibility snapshot."""
    videos, seen = [], set()
    # Pattern: title line followed by 播放量/点赞/评论/分享/收藏 metric lines
    # In accessibility tree, videos appear as blocks with title + metric labels
    pattern = re.compile(
        r'generic \[ref=e\d+\]:\s*["\']?([^"\n]{3,240})["\']?\s*\n'
        r'(.*?)(?=\ngeneric \[ref=e\d+\]:\s*["\']?[^"\n]{3,240}["\']?\s*\n|\Z)',
        re.DOTALL,
    )
    for match in pattern.finditer(text):
        title = match.group(1).strip().strip('"')
        block = match.group(2)
        if title in seen or title in {"粉丝", "获赞", "关注", "播放量", "抖音号"}:
            continue
        if len(title) < 3:
            continue
        def extract_metric(label: str) -> int:
            m = re.search(
                rf'{re.escape(label)}\s*\n\s*- generic \[ref=e\d+\]:\s*([^\n]+)',
                block,
            )
            return _parse_compact_number(m.group(1)) if m else 0
        play = extract_metric("播放量")
        likes = extract_metric("点赞") or extract_metric("获赞")
        comments = extract_metric("评论")
        shares = extract_metric("分享") or extract_metric("转发")
        collects = extract_metric("收藏")
        if play or likes or comments:
            seen.add(title)
            videos.append({
                "title": title[:200],
                "play_count": play,
                "like_count": likes,
                "comment_count": comments,
                "share_count": shares,
                "collect_count": collects,
                "url": "",
            })
        if len(videos) >= 20:
            break
    return videos


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


async def _mcp_snapshot_for_url(account: dict, capability: str, url: str, *, depth: int = 15) -> str:
    """Navigate to a specific URL and take a snapshot. Returns empty string on failure.

    For Douyin creator center (SPA), browser_navigate alone may not trigger
    route changes. We navigate by URL first, then click the corresponding menu
    item to force SPA routing. We also wait longer and validate that the
    snapshot contains main content (not just sidebar/navigation).
    """
    from agent_core.mcp_browser_policy import BrowserActionContext
    platform, account_id = account["platform"], account["id"]
    manager = _get_mcp_manager()
    ctx = BrowserActionContext(
        platform=platform, account_id=account_id, capability=capability,
        user_id="default", approved=True,
    )

    # Map URL to menu item label for SPA click navigation
    # For data-center sub-pages, click the parent 数据中心 menu first,
    # then navigate to the specific sub-page URL.
    click_label = None
    nav_after_click = False
    if "content-manage" in url:
        click_label = "作品管理"
    elif "data-center" in url:
        click_label = "数据中心"
        nav_after_click = False  # SPA handles routing after click

    # First try the reviewed official URL. Some creator-center routes are SPA
    # only, so a menu click remains a bounded fallback.
    try:
        await _get_mcp_broker().call_account_scoped_browser(
            manager, "playwright_browser", platform, account_id, "browser_navigate",
            {"url": url}, browser_ctx=ctx, approved=True,
        )
    except Exception:
        pass

    # 1. Click menu item to trigger SPA routing (if mapped)
    # browser_click requires a snapshot ref as target, so we first take a
    # snapshot to find the menu item's ref, then click it.
    if click_label:
        try:
            # Take a snapshot to find the menu item ref
            snap = await _get_mcp_broker().call_account_scoped_browser(
                manager, "playwright_browser", platform, account_id, "browser_snapshot",
                {"depth": 8}, browser_ctx=ctx, approved=True,
            )
            if snap.get("status") == "ok":
                snap_text = _mcp_text(snap)
                # Find ref for the menu item label (e.g. menuitem "作品管理" [ref=e54])
                import re as _re
                ref_match = _re.search(
                    rf'menuitem\s+"{re.escape(click_label)}"\s+\[ref=([a-z0-9]+)\]',
                    snap_text,
                )
                if not ref_match:
                    # Fallback: find generic with the label text
                    ref_match = _re.search(
                        rf'\[ref=([a-z0-9]+)\]:\s*{re.escape(click_label)}\s*$',
                        snap_text, _re.MULTILINE,
                    )
                if ref_match:
                    target_ref = ref_match.group(1)
                    await _get_mcp_broker().call_account_scoped_browser(
                        manager, "playwright_browser", platform, account_id, "browser_click",
                        {"element": click_label, "target": target_ref},
                        browser_ctx=ctx, approved=True,
                    )
                    # Wait for SPA route to settle
                    await _get_mcp_broker().call_account_scoped_browser(
                        manager, "playwright_browser", platform, account_id, "browser_wait_for",
                        {"time": 2}, browser_ctx=ctx, approved=True,
                    )
        except Exception:
            pass

    # 2. For data-center sub-pages, navigate to specific URL after clicking parent menu
    if nav_after_click:
        try:
            await _get_mcp_broker().call_account_scoped_browser(
                manager, "playwright_browser", platform, account_id, "browser_navigate",
                {"url": url},
                browser_ctx=ctx, approved=True,
            )
        except Exception:
            pass

    # 3. Wait and retry snapshot — content pages need more time to render
    # Validate that snapshot has substantial content beyond sidebar (~3K chars
    # is just sidebar+header; real content should be >10K).
    # Also dismiss any blocking dialog popups that prevent content rendering.
    text = ""
    snapshot = {}
    for delay in (3, 4, 5, 5):
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
        text = _mcp_text(snapshot)
        # Check for blocking dialog and dismiss it
        if "我知道了" in text:
            import re as _re2
            dialog_ref = _re2.search(r'button\s+"我知道了"\s+\[ref=([a-z0-9]+)\]', text)
            if dialog_ref:
                try:
                    await _get_mcp_broker().call_account_scoped_browser(
                        manager, "playwright_browser", platform, account_id, "browser_click",
                        {"element": "我知道了", "target": dialog_ref.group(1)},
                        browser_ctx=ctx, approved=True,
                    )
                    await _get_mcp_broker().call_account_scoped_browser(
                        manager, "playwright_browser", platform, account_id, "browser_wait_for",
                        {"time": 2}, browser_ctx=ctx, approved=True,
                    )
                    # Re-snapshot after dismissing dialog
                    snapshot = await _get_mcp_broker().call_account_scoped_browser(
                        manager, "playwright_browser", platform, account_id, "browser_snapshot",
                        {"depth": depth}, browser_ctx=ctx, approved=True,
                    )
                    if snapshot.get("status") == "ok":
                        text = _mcp_text(snapshot)
                except Exception:
                    pass
        # Fail closed on route-specific evidence. A long home-page snapshot is
        # not proof that navigation succeeded.
        if "content-manage" in url and _parse_creator_video_list(text):
            return text
        if "data-center" in url and _parse_creator_account_snapshot(text)["stats"].get("recent_30d"):
            return text
    return ""


@app.post("/api/plugins/marketing-os/accounts/{account_id}/mcp-sync")
async def mcp_sync_account(account_id: str):
    if not _mcp_login_enabled():
        raise HTTPException(409, "MCP browser is not enabled")
    lock = _mcp_account_operation_locks.setdefault(account_id, asyncio.Lock())
    async with lock:
        account = _require_connected_account(account_id)
        # 1. Home page — account overview stats
        home_text = await _mcp_snapshot_for_account(account, "marketing_accounts_sync")
        parsed = _parse_creator_account_snapshot(home_text)
        if parsed["identity"]["username"] or parsed["identity"]["label"]:
            from marketing_tools.account import update_account_identity
            update_account_identity({"account_id": account_id, **parsed["identity"]})
        if not any(parsed["stats"].values()):
            raise HTTPException(422, "创作者中心已打开，但未识别到账号指标")

        # 2. Content manage page — per-video metrics
        videos = _parse_creator_video_list(home_text)
        content_text = await _mcp_snapshot_for_url(
            account, "marketing_accounts_sync",
            "https://creator.douyin.com/creator-micro/content-manage",
        )
        if content_text:
            content_videos = _parse_creator_video_list(content_text)
            if len(content_videos) > len(videos):
                videos = content_videos

        # 3. Data-center navigation is not yet stable. Keep it behind an
        # explicit experiment flag so normal sync neither waits ~20 seconds
        # nor risks treating the home page as data-center evidence.
        data_center_status = "disabled"
        if os.environ.get("MARKETING_OS_MCP_DATA_CENTER_EXPERIMENTAL") == "1":
            data_text = await _mcp_snapshot_for_url(
                account, "marketing_accounts_sync",
                "https://creator.douyin.com/creator-micro/data-center/follow-data",
            )
            data_center_status = "unavailable"
            if data_text:
                data_center_status = "ok"
                data_parsed = _parse_creator_account_snapshot(data_text)
                for key, val in data_parsed["stats"].items():
                    if val and not parsed["stats"].get(key):
                        parsed["stats"][key] = val

        # Persist per-video metrics
        if videos:
            store = _get_agent_service().get_store()
            for v in videos[:50]:
                store.add_video_metric(
                    account_id=account_id, title=v["title"],
                    play_count=v.get("play_count", 0), like_count=v.get("like_count", 0),
                    comment_count=v.get("comment_count", 0), share_count=v.get("share_count", 0),
                    collect_count=v.get("collect_count", 0),
                )

        return {**parsed["stats"], "source": "playwright_mcp_creator_center",
                "identity": parsed["identity"], "videos_count_parsed": len(videos),
                "data_center_status": data_center_status}


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


def _summarize_douyin_publish_snapshot(text: str, mode: str = "video") -> dict:
    """Return non-sensitive upload-page evidence, never the full account snapshot."""
    markers = (
        "上传视频", "点击上传", "拖拽上传", "选择文件", "发布视频",
        "上传图片", "选择图片", "添加图片", "发布图文", "图文发布",
        "作品描述", "标题", "封面", "定时发布", "发布设置",
    )
    visible_markers = [marker for marker in markers if marker in text]
    ready_markers = (
        ("上传图片", "选择图片", "添加图片") if mode == "image"
        else ("上传视频", "点击上传", "拖拽上传", "选择文件")
    )
    return {
        "ready": any(marker in visible_markers for marker in ready_markers),
        "visible_markers": visible_markers,
        "snapshot_chars": len(text),
    }


@app.post("/api/plugins/marketing-os/content/assets/{asset_id}/publish-prepare")
async def prepare_content_asset_publish(asset_id: str, body: dict):
    """Open the official upload page and inspect it without uploading or publishing."""
    if not _mcp_login_enabled():
        raise HTTPException(409, "MCP browser is not enabled")
    store = _get_agent_service().get_store()
    try:
        asset = store.get_content_asset(asset_id)
    except KeyError as exc:
        raise HTTPException(404, "asset not found") from exc
    account_id = str(asset.get("account_id") or "")
    if not account_id:
        raise HTTPException(409, "content asset is not bound to an account")
    if asset.get("platform") not in (None, "", "douyin") or str(body.get("platform") or "douyin") != "douyin":
        raise HTTPException(400, "publish prepare currently supports douyin only")
    _require_connected_account(account_id)
    mode = "image" if asset.get("type") == "image" else "video"
    navigation_label = "发布图文" if mode == "image" else "发布视频"
    lock = _mcp_account_operation_locks.setdefault(account_id, asyncio.Lock())
    async with lock:
        text = await _mcp_snapshot_for_account(
            {"id": account_id, "platform": "douyin"}, "marketing_publish_prepare", depth=15,
        )
        match = re.search(rf'(?:button|link|generic) "?{navigation_label}"?[^\n]*\[ref=(e\d+)\]', text)
        if not match:
            match = re.search(rf'{navigation_label}[^\n]*\[ref=(e\d+)\]', text)
        if not match:
            return {"status": "blocked", "reason": f"publish_{mode}_control_not_found", **_summarize_douyin_publish_snapshot(text, mode)}

        from agent_core.mcp_browser_policy import BrowserActionContext
        ctx = BrowserActionContext(
            platform="douyin", account_id=account_id,
            capability="marketing_publish_prepare", user_id="default", approved=True,
        )
        manager = _get_mcp_manager()
        clicked = await _get_mcp_broker().call_account_scoped_browser(
            manager, "playwright_browser", "douyin", account_id, "browser_click",
            {"element": navigation_label, "target": match.group(1)},
            browser_ctx=ctx, approved=True,
        )
        if clicked.get("status") != "ok":
            raise HTTPException(503, clicked.get("reason", "publish page navigation failed"))
        await _get_mcp_broker().call_account_scoped_browser(
            manager, "playwright_browser", "douyin", account_id, "browser_wait_for",
            {"time": 2}, browser_ctx=ctx, approved=True,
        )
        snapshot = await _get_mcp_broker().call_account_scoped_browser(
            manager, "playwright_browser", "douyin", account_id, "browser_snapshot",
            {"depth": 20}, browser_ctx=ctx, approved=True,
        )
        if snapshot.get("status") != "ok":
            raise HTTPException(503, snapshot.get("reason", "publish page snapshot failed"))
        summary = _summarize_douyin_publish_snapshot(_mcp_text(snapshot), mode)
        return {"status": "ready" if summary["ready"] else "blocked", "account_id": account_id,
                "asset_id": asset_id, "mode": mode, "uploaded": False, "published": False, **summary}


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


@app.get("/api/plugins/marketing-os/content/assets/{asset_id}")
def get_content_asset_endpoint(asset_id: str):
    try:
        return _get_agent_service().get_store().get_content_asset(asset_id)
    except KeyError:
        raise HTTPException(404, "asset not found")


@app.get("/api/plugins/marketing-os/content/assets/{asset_id}/attachment")
def get_content_asset_attachment(asset_id: str, user_id: str = "default", account_id: str = ""):
    store = _get_agent_service().get_store()
    attachments = store.list_active_media_attachments(
        asset_id=asset_id, user_id=user_id, account_id=account_id,
    )
    attachment = store.get_active_media_attachment(
        asset_id=asset_id, user_id=user_id, account_id=account_id,
    )
    return {"attachment": attachment, "attachments": attachments}


@app.get("/api/plugins/marketing-os/stock-images/status")
def stock_images_status():
    from marketing_tools.stock_images import PexelsProvider
    provider = PexelsProvider.from_environment()
    return {
        "provider": "pexels", "configured": provider.configured,
        "attribution": "Photos provided by Pexels",
        "provider_url": "https://www.pexels.com",
    }


@app.post("/api/plugins/marketing-os/stock-images/search")
def search_stock_images(body: dict):
    from marketing_tools.stock_images import PexelsProvider, StockImageError
    try:
        return PexelsProvider.from_environment().search(
            str(body.get("query") or ""), limit=int(body.get("limit", 12)),
            orientation=str(body.get("orientation") or "portrait"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except StockImageError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/plugins/marketing-os/firecrawl/status")
def firecrawl_status():
    from marketing_tools.firecrawl_provider import FirecrawlProvider
    try:
        provider = FirecrawlProvider()
        return {"configured": provider.configured, "mode": provider.mode, "api_url": provider.api_url}
    except ValueError as exc:
        return {"configured": False, "mode": "invalid", "error": str(exc)}


@app.post("/api/plugins/marketing-os/firecrawl/search")
def firecrawl_search_endpoint(body: dict):
    from marketing_tools.firecrawl_provider import FirecrawlError, FirecrawlProvider
    try:
        return FirecrawlProvider().search(
            str(body.get("query") or ""), limit=int(body.get("limit", 8)),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FirecrawlError as exc:
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/plugins/marketing-os/tts/index-tts2/status")
def index_tts2_status_endpoint():
    from agent_core.local_tts_provider import index_tts2_status

    return index_tts2_status()


@app.post("/api/plugins/marketing-os/tts/volcengine/v1/synthesize")
def volcengine_tts_v1_synthesize_endpoint(body: dict):
    from agent_core.volcengine_tts_provider import VolcengineTTSError, synthesize_volcengine_tts_v1

    try:
        return synthesize_volcengine_tts_v1(
            text=str(body.get("text") or ""),
            api_key=str(body.get("api_key") or os.environ.get("VOLCENGINE_TTS_API_KEY") or ""),
            output_dir=body.get("output_dir") or (CONFIG_DIR.parent / "tts-cache"),
            voice_type=str(body.get("voice_type") or "zh_female_shuangkuaisisi_moon_bigtts"),
            cluster=str(body.get("cluster") or "volcano_tts"),
            encoding=str(body.get("encoding") or "mp3"),
            speed_ratio=float(body.get("speed_ratio") or 1.0),
            uid=str(body.get("uid") or "marketing-os"),
            timeout=int(body.get("timeout") or 45),
        )
    except VolcengineTTSError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/plugins/marketing-os/content/production/plan")
def content_production_plan_endpoint(body: dict):
    from agent_core.content_production import build_content_production_plan

    return build_content_production_plan(body)


@app.post("/api/plugins/marketing-os/content/production/preflight")
def content_production_preflight_endpoint(body: dict):
    return create_content_preflight(body)


@app.post("/api/plugins/marketing-os/content/production/article-soft")
def content_production_article_soft_endpoint(body: dict):
    return create_soft_article_asset(body)


@app.post("/api/plugins/marketing-os/content/production/faceless-video")
def content_production_faceless_video_endpoint(body: dict):
    return create_faceless_video_asset(body)


@app.post("/api/plugins/marketing-os/content/production/from-experiment")
def content_production_from_experiment_endpoint(body: dict):
    return create_content_from_experiment(body)


@app.post("/api/plugins/marketing-os/content/production/faceless-render/prepare")
def content_production_faceless_render_prepare_endpoint(body: dict):
    return prepare_faceless_render(body)


@app.post("/api/plugins/marketing-os/content/production/faceless-render/animatic")
def content_production_faceless_render_animatic_endpoint(body: dict):
    return render_faceless_animatic(body)


@app.post("/api/plugins/marketing-os/content/production/faceless-render/fill-image-materials")
def content_production_faceless_render_fill_image_materials_endpoint(body: dict):
    return fill_faceless_image_materials(body)


@app.post("/api/plugins/marketing-os/content/production/faceless-render/final")
def content_production_faceless_render_final_endpoint(body: dict):
    return render_faceless_final(body)


@app.post("/api/plugins/marketing-os/content/assets")
def create_content_asset_endpoint(body: dict):
    try:
        svc = _get_agent_service()
        store = svc.get_store()
        title = str(body.get("title", ""))
        if not title.strip():
            raise HTTPException(400, "title is required")
        asset_type, content = _normalise_content_asset_payload(body)
        asset = store.create_content_asset(
            title=title[:200],
            type=asset_type,
            user_id=str(body.get("user_id", "default")),
            account_id=body.get("account_id"),
            platform=body.get("platform"),
            content=content,
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


# ---- User-imported media attachments (Electron host only) ----

@app.post("/api/plugins/marketing-os/media/attachments")
def register_media_attachment_endpoint(body: dict):
    try:
        return _get_agent_service().get_store().register_media_attachment(
            user_id=str(body.get("user_id") or "default"),
            account_id=str(body.get("account_id") or ""),
            asset_id=str(body.get("asset_id") or ""),
            original_name=str(body.get("original_name") or ""),
            mime_type=str(body.get("mime_type") or ""),
            byte_size=body.get("byte_size"),
            sha256=str(body.get("sha256") or ""),
            storage_key=str(body.get("storage_key") or ""),
            position=body.get("position"),
            provenance=body.get("provenance") if isinstance(body.get("provenance"), dict) else None,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/plugins/marketing-os/media/attachments/active")
def get_active_media_attachment_endpoint(
    asset_id: str, user_id: str = "default", account_id: str = "",
):
    attachment = _get_agent_service().get_store().get_active_media_attachment(
        asset_id=asset_id, user_id=user_id, account_id=account_id,
        include_storage_key=True,
    )
    if attachment is None:
        raise HTTPException(404, "active media attachment not found")
    return attachment


@app.get("/api/plugins/marketing-os/media/attachments")
def list_active_media_attachments_endpoint(
    asset_id: str, user_id: str = "default", account_id: str = "",
):
    return {"attachments": _get_agent_service().get_store().list_active_media_attachments(
        asset_id=asset_id, user_id=user_id, account_id=account_id,
        include_storage_key=True,
    )}


@app.get("/api/plugins/marketing-os/media/attachments/{attachment_id}")
def get_media_attachment_endpoint(
    attachment_id: str, user_id: str = "default", account_id: str = "",
):
    try:
        return _get_agent_service().get_store().get_media_attachment(
            attachment_id, user_id=user_id, account_id=account_id,
            include_storage_key=True,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.delete("/api/plugins/marketing-os/media/attachments/{attachment_id}")
def delete_media_attachment_endpoint(
    attachment_id: str, user_id: str = "default", account_id: str = "",
):
    try:
        return _get_agent_service().get_store().delete_media_attachment(
            attachment_id, user_id=user_id, account_id=account_id,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


# ---- 选题建议 ----

@app.get("/api/plugins/marketing-os/suggestions")
def get_suggestions(account_id: str = "", user_id: str = "default"):
    cache_file = CONFIG_DIR / "suggestions-cache.json"
    if cache_file.exists():
        payload = _sanitize_suggestions_payload(json.loads(cache_file.read_text()))
        if account_id:
            from marketing_tools.content import rank_trends_for_context
            ranked = rank_trends_for_context(
                {
                    "top_trends": [
                        {
                            **item,
                            "title": item.get("trend") or item.get("title") or "",
                            "source_platform": item.get("trend_source") or item.get("source_platform") or "",
                        }
                        for item in payload.get("suggestions", [])
                        if isinstance(item, dict)
                    ]
                },
                _account_trend_context(account_id, user_id),
                limit=20,
            )
            allowed = {
                (item.get("title"), item.get("source_platform"))
                for item in ranked.get("top_trends", [])
            }
            payload["suggestions"] = [
                item for item in payload.get("suggestions", [])
                if (item.get("trend") or item.get("title"), item.get("trend_source") or item.get("source_platform")) in allowed
            ]
            payload["matched_trends_count"] = len(payload["suggestions"])
            payload["relevance_mode"] = ranked.get("relevance_mode")
        return payload
    return {"status": "no_data", "message": "尚未生成内容建议"}


# ---- 概览 ----

def _empty_dashboard_content_pipeline() -> dict:
    return {
        "total_assets": 0,
        "drafts": 0,
        "in_review": 0,
        "approved": 0,
        "published": 0,
        "ready_to_publish": 0,
        "latest_draft": None,
    }


def _empty_dashboard_publishing_summary() -> dict:
    return {
        "total": 0,
        "verified": 0,
        "pending_verification": 0,
        "failed": 0,
        "metric_checkpoints": {
            "total": 0,
            "scheduled": 0,
            "collected": 0,
            "due": 0,
        },
        "next_metrics_at": None,
        "latest": None,
    }


def _parse_dashboard_time(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _dashboard_content_pipeline(store) -> dict:
    summary = _empty_dashboard_content_pipeline()
    try:
        assets = store.list_content_assets()
    except Exception:
        return summary
    summary["total_assets"] = len(assets)
    for asset in assets:
        status = str(asset.get("status") or "draft")
        if status == "draft":
            summary["drafts"] += 1
        elif status == "review":
            summary["in_review"] += 1
        elif status == "approved":
            summary["approved"] += 1
        elif status in {"published", "metrics_collected"}:
            summary["published"] += 1
        if status == "approved":
            summary["ready_to_publish"] += 1
    latest = next((asset for asset in assets if asset.get("status") == "draft"), None)
    if latest:
        summary["latest_draft"] = {
            "id": latest.get("id"),
            "title": latest.get("title"),
            "platform": latest.get("platform"),
            "updated_at": latest.get("updated_at"),
        }
    return summary


def _dashboard_publishing_summary(store) -> dict:
    summary = _empty_dashboard_publishing_summary()
    try:
        tasks = store.list_publishing_tasks()
    except Exception:
        return summary
    now = datetime.now(timezone.utc)
    latest_task = None
    next_metric_time: datetime | None = None
    for task in tasks:
        summary["total"] += 1
        receipt = task.get("receipt") or {}
        verified = bool(receipt.get("published_url") or receipt.get("platform_post_id") or receipt.get("post_id"))
        status = str(task.get("status") or "")
        if verified:
            summary["verified"] += 1
        elif status == "failed":
            summary["failed"] += 1
        else:
            summary["pending_verification"] += 1

        try:
            checkpoints = store.list_metric_checkpoints(task["id"])
        except Exception:
            checkpoints = []
        for checkpoint in checkpoints:
            ckpt_status = str(checkpoint.get("status") or "")
            summary["metric_checkpoints"]["total"] += 1
            if ckpt_status == "collected":
                summary["metric_checkpoints"]["collected"] += 1
            elif ckpt_status == "scheduled":
                summary["metric_checkpoints"]["scheduled"] += 1
                due_at = _parse_dashboard_time(checkpoint.get("due_at"))
                if due_at and due_at <= now:
                    summary["metric_checkpoints"]["due"] += 1
                if due_at and (next_metric_time is None or due_at < next_metric_time):
                    next_metric_time = due_at

        if latest_task is None or str(task.get("updated_at") or task.get("created_at") or "") > str(latest_task.get("updated_at") or latest_task.get("created_at") or ""):
            latest_task = task

    if next_metric_time:
        summary["next_metrics_at"] = next_metric_time.isoformat()
    if latest_task:
        latest_receipt = latest_task.get("receipt") or {}
        summary["latest"] = {
            "id": latest_task.get("id"),
            "asset_id": latest_task.get("asset_id"),
            "platform": latest_task.get("platform"),
            "status": latest_task.get("status"),
            "verified": bool(latest_receipt.get("published_url") or latest_receipt.get("platform_post_id") or latest_receipt.get("post_id")),
            "published_at": latest_task.get("published_at"),
            "next_metrics_at": latest_task.get("next_metrics_at"),
        }
    return summary


def _dashboard_store():
    service = globals().get("_agent_service")
    if service is not None:
        return service.get_store()
    from agent_core import AgentCoreStore
    return AgentCoreStore(CONFIG_DIR.parent / "agent-runtime" / "agent_core.db")


@app.get("/api/plugins/marketing-os/dashboard/overview")
def dashboard_overview():
    accounts = _read_json(CONFIG_DIR / "accounts.json", {"accounts": []}).get("accounts", [])
    trending = _sanitize_trending_payload(_read_json(CONFIG_DIR / "trending-cache.json", {}))
    suggestions = _sanitize_suggestions_payload(_read_json(CONFIG_DIR / "suggestions-cache.json", {}))
    total_followers = sum(
        int((account.get("stats") or {}).get("followers", 0) or 0)
        for account in accounts
    )
    follower_growth = sum(
        int((account.get("stats") or {}).get("follower_growth_today", 0) or 0)
        for account in accounts
    )
    from marketing_tools.monitor import load_monitor_history
    platform_accounts = []
    for account in accounts:
        stats = account.get("stats") or {}
        history = load_monitor_history(
            str(account.get("id") or ""), days=30, data_dir=CONFIG_DIR / "monitor_data",
        )
        platform_accounts.append({
            "id": account.get("id"), "platform": account.get("platform"),
            "label": account.get("label") or account.get("username") or account.get("platform"),
            "status": account.get("status"),
            "stats": {
                key: stats.get(key, 0) for key in (
                    "followers", "follower_growth_today", "total_views", "total_likes",
                    "engagements", "comments", "videos_count", "updated_at",
                )
            },
            "history": [{
                "at": item.get("updated_at") or item.get("saved_at"),
                "followers": item.get("followers", 0),
                "views": item.get("total_views", 0),
            } for item in history[-30:]],
        })
    content_pipeline = _empty_dashboard_content_pipeline()
    publishing_summary = _empty_dashboard_publishing_summary()
    try:
        store = _dashboard_store()
        if store:
            content_pipeline = _dashboard_content_pipeline(store)
            publishing_summary = _dashboard_publishing_summary(store)
    except Exception:
        pass
    return {
        "today": datetime.now().isoformat(),
        "accounts_connected": len(accounts),
        "trending_topics_today": len(trending.get("top_trends", [])),
        "suggestions_generated": len(suggestions.get("suggestions", [])),
        "videos_published": publishing_summary["verified"],
        "total_followers": total_followers,
        "follower_growth_today": follower_growth,
        "platform_accounts": platform_accounts,
        "content_pipeline": content_pipeline,
        "publishing_receipts": publishing_summary,
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


def _workflow_last_run_date(last_run: str | None, now: datetime) -> date | None:
    """Return the last workflow run date in the same local day boundary as ``now``.

    Electron persists completion timestamps with ``Date.toISOString()``, i.e. UTC.
    The desktop scheduler uses local wall-clock schedule_time, so comparing the
    raw UTC date with a local date makes early-morning runs look like "yesterday"
    in Asia/Shanghai and causes the scheduler to fire every 30 seconds.
    """
    if not last_run:
        return None
    try:
        parsed = datetime.fromisoformat(str(last_run).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is not None:
        local_tz = now.astimezone().tzinfo
        parsed = parsed.astimezone(local_tz)
    return parsed.date()


def _workflow_due(state: dict, now: datetime | None = None) -> bool:
    if not state.get("enabled"):
        return False
    now = now or datetime.now()
    hour, minute = _parse_schedule_time(state.get("schedule_time", "08:03"))
    scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    last_date = _workflow_last_run_date(state.get("last_run"), now)
    return now >= scheduled and last_date != now.date()


def _next_workflow_run(state: dict, now: datetime | None = None) -> str | None:
    if not state.get("enabled"):
        return None
    now = now or datetime.now()
    hour, minute = _parse_schedule_time(state.get("schedule_time", "08:03"))
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    last_date = _workflow_last_run_date(state.get("last_run"), now)
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


def _metric_scheduler_limit() -> int:
    try:
        configured = int(os.environ.get("MARKETING_OS_METRIC_CHECKPOINT_LIMIT", "5"))
    except (TypeError, ValueError):
        configured = 5
    return min(max(configured, 1), 20)


def _metric_retry_minutes(reason: str) -> int:
    if reason == "adapter_missing":
        return 6 * 60
    return 60


def _metrics_from_publishing_receipt(task: dict, checkpoint: dict) -> tuple[dict, dict] | None:
    """Compatibility adapter for tests/imported receipts; never invent values."""
    receipt = task.get("receipt") or {}
    metrics = receipt.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        return None
    provenance = {
        "source_kind": "imported_report",
        "source_ref": f"publishing_receipt:{task['id']}",
        "captured_at": receipt.get("metrics_captured_at") or datetime.now().isoformat(),
        "checkpoint_label": checkpoint.get("checkpoint_label"),
    }
    return metrics, provenance


def _normalize_match_text(value: object) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)


def _task_metric_match_hints(store, task: dict) -> dict:
    asset = store.get_content_asset(task["asset_id"])
    receipt = task.get("receipt") or {}
    content = asset.get("content") if isinstance(asset.get("content"), dict) else {}
    title_candidates = [
        receipt.get("title"), receipt.get("caption"), receipt.get("description"),
        asset.get("title"), asset.get("topic"), asset.get("hook"),
        content.get("title"), content.get("caption"), content.get("headline"),
    ]
    url_candidates = [
        receipt.get("published_url"), receipt.get("url"), receipt.get("share_url"),
        receipt.get("permalink"),
    ]
    post_candidates = [
        receipt.get("platform_post_id"), receipt.get("post_id"), receipt.get("aweme_id"),
        receipt.get("item_id"), receipt.get("video_id"),
    ]
    return {
        "account_id": asset.get("account_id"),
        "platform": asset.get("platform") or task.get("platform"),
        "titles": [str(item).strip() for item in title_candidates if str(item or "").strip()],
        "urls": [str(item).strip() for item in url_candidates if str(item or "").strip()],
        "post_ids": [str(item).strip() for item in post_candidates if str(item or "").strip()],
    }


def _score_video_metric_match(video: dict, hints: dict) -> int:
    video_url = str(video.get("url") or "")
    video_title_norm = _normalize_match_text(video.get("title"))
    best = 0
    for url in hints.get("urls", []):
        if url and video_url and (url in video_url or video_url in url):
            best = max(best, 100)
    for post_id in hints.get("post_ids", []):
        if post_id and video_url and post_id in video_url:
            best = max(best, 95)
    for title in hints.get("titles", []):
        title_norm = _normalize_match_text(title)
        if len(title_norm) < 4 or len(video_title_norm) < 4:
            continue
        if title_norm == video_title_norm:
            best = max(best, 85)
        elif title_norm in video_title_norm or video_title_norm in title_norm:
            best = max(best, 70)
    return best


def _metrics_from_creator_center_cache(store, task: dict, checkpoint: dict) -> tuple[dict, dict] | None:
    hints = _task_metric_match_hints(store, task)
    if hints.get("platform") != "douyin" or not hints.get("account_id"):
        return None
    videos = store.list_video_metrics(account_id=hints["account_id"], limit=100)
    scored = sorted(
        ((_score_video_metric_match(video, hints), video) for video in videos),
        key=lambda item: item[0],
        reverse=True,
    )
    if not scored or scored[0][0] < 70:
        return None
    score, video = scored[0]
    views = int(video.get("play_count", 0) or 0)
    likes = int(video.get("like_count", 0) or 0)
    comments = int(video.get("comment_count", 0) or 0)
    shares = int(video.get("share_count", 0) or 0)
    collects = int(video.get("collect_count", 0) or 0)
    metrics = {
        "views": views,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "collects": collects,
    }
    if views > 0:
        metrics["engagement_rate"] = round((likes + comments + shares + collects) / views, 6)
    provenance = {
        "source_kind": "creator_center_mcp",
        "source_ref": video.get("url") or f"creator_center_video_metrics:{video['id']}",
        "captured_at": video.get("collected_at") or datetime.now().isoformat(),
        "checkpoint_label": checkpoint.get("checkpoint_label"),
        "match_score": score,
        "matched_title": video.get("title"),
        "video_metric_id": video.get("id"),
    }
    return metrics, provenance


def _extract_platform_post_id(url: str) -> str | None:
    text = str(url or "")
    patterns = (
        r"/video/(\d{6,32})",
        r"/note/(\d{6,32})",
        r"[?&](?:modal_id|aweme_id|item_id|video_id)=(\d{6,32})",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def _best_creator_center_publication_match(store, task: dict) -> dict | None:
    hints = _task_metric_match_hints(store, task)
    if hints.get("platform") != "douyin" or not hints.get("account_id"):
        return None
    videos = store.list_video_metrics(account_id=hints["account_id"], limit=100)
    scored = sorted(
        ((_score_video_metric_match(video, hints), video) for video in videos),
        key=lambda item: item[0],
        reverse=True,
    )
    if not scored or scored[0][0] < 70:
        return None
    score, video = scored[0]
    url = str(video.get("url") or "")
    post_id = _extract_platform_post_id(url)
    return {
        "score": score,
        "video": video,
        "stable": bool(url or post_id),
        "published_url": url or None,
        "platform_post_id": post_id,
        "matched_title": video.get("title"),
        "video_metric_id": video.get("id"),
        "collected_at": video.get("collected_at"),
    }


def _publication_match_receipt(task: dict, match: dict) -> dict:
    video = match["video"]
    receipt = {
        "status": "verified",
        "provider": "creator_center_mcp",
        "platform": task.get("platform"),
        "publishing_task_id": task.get("id"),
        "verification_source": "creator_center_content_manage",
        "verified_at": datetime.now().isoformat(),
        "match_score": match["score"],
        "matched_title": match.get("matched_title"),
        "video_metric_id": match.get("video_metric_id"),
        "metrics_captured_at": match.get("collected_at"),
        "metrics": {
            "views": int(video.get("play_count", 0) or 0),
            "likes": int(video.get("like_count", 0) or 0),
            "comments": int(video.get("comment_count", 0) or 0),
            "shares": int(video.get("share_count", 0) or 0),
            "collects": int(video.get("collect_count", 0) or 0),
        },
    }
    if match.get("published_url"):
        receipt["published_url"] = match["published_url"]
    if match.get("platform_post_id"):
        receipt["platform_post_id"] = match["platform_post_id"]
    return receipt


async def _query_publishing_task_receipt(store, task_id: str, *, refresh: bool = True) -> dict:
    task = store.get_publishing_task(task_id)
    if task.get("receipt") and (
        task["receipt"].get("published_url") or task["receipt"].get("platform_post_id")
    ):
        return {"status": "already_verified", "task": task, "receipt": task["receipt"]}
    match = _best_creator_center_publication_match(store, task)
    if match is None and refresh:
        try:
            hints = _task_metric_match_hints(store, task)
            if hints.get("platform") == "douyin" and hints.get("account_id") and _mcp_login_enabled():
                await mcp_sync_account(str(hints["account_id"]))
                match = _best_creator_center_publication_match(store, task)
        except HTTPException as exc:
            return {"status": "unavailable", "reason": str(exc.detail), "task": task}
        except Exception as exc:
            return {"status": "unavailable", "reason": type(exc).__name__, "task": task}
    if match is None:
        return {
            "status": "not_found",
            "reason": "creator_center_work_not_matched",
            "task": task,
        }
    if not match["stable"]:
        return {
            "status": "found_unverified",
            "reason": "matched creator-center work has no stable platform URL or post id",
            "match": {key: value for key, value in match.items() if key != "video"},
            "task": task,
        }
    receipt = _publication_match_receipt(task, match)
    if task["status"] != "published":
        verified = store.complete_publishing_task(
            task_id,
            effect_id=str(task.get("effect_id") or f"query_{task_id}"),
            receipt=receipt,
        )
    else:
        verified = task
    return {
        "status": "verified",
        "task": verified,
        "receipt": receipt,
        "match": {key: value for key, value in match.items() if key != "video"},
    }


def _collect_one_metric_checkpoint(store, checkpoint: dict) -> dict:
    task = store.get_publishing_task(checkpoint["task_id"])
    adapted = (
        _metrics_from_publishing_receipt(task, checkpoint)
        or _metrics_from_creator_center_cache(store, task, checkpoint)
    )
    if adapted is None:
        updated = store.defer_metric_checkpoint(
            checkpoint["id"],
            reason="adapter_missing: no official_api/creator_center_mcp metrics adapter for this platform yet",
            retry_after_minutes=_metric_retry_minutes("adapter_missing"),
        )
        return {"status": "deferred", "checkpoint": updated, "reason": updated.get("last_error")}
    metrics, provenance = adapted
    collected = store.collect_metrics(
        checkpoint["task_id"],
        metrics,
        checkpoint_id=checkpoint["id"],
        provenance=provenance,
    )
    return {
        "status": "collected",
        "checkpoint_id": checkpoint["id"],
        "task_id": checkpoint["task_id"],
        "snapshot_id": collected["metric_snapshot"]["id"],
    }


async def _collect_one_metric_checkpoint_with_refresh(store, checkpoint: dict) -> dict:
    task = store.get_publishing_task(checkpoint["task_id"])
    adapted = (
        _metrics_from_publishing_receipt(task, checkpoint)
        or _metrics_from_creator_center_cache(store, task, checkpoint)
    )
    if adapted is not None:
        metrics, provenance = adapted
        collected = store.collect_metrics(
            checkpoint["task_id"], metrics,
            checkpoint_id=checkpoint["id"], provenance=provenance,
        )
        return {
            "status": "collected",
            "checkpoint_id": checkpoint["id"],
            "task_id": checkpoint["task_id"],
            "snapshot_id": collected["metric_snapshot"]["id"],
            "source_kind": provenance.get("source_kind"),
        }
    try:
        hints = _task_metric_match_hints(store, task)
        if hints.get("platform") == "douyin" and hints.get("account_id") and _mcp_login_enabled():
            await mcp_sync_account(str(hints["account_id"]))
            adapted = _metrics_from_creator_center_cache(store, task, checkpoint)
            if adapted is not None:
                metrics, provenance = adapted
                collected = store.collect_metrics(
                    checkpoint["task_id"], metrics,
                    checkpoint_id=checkpoint["id"], provenance=provenance,
                )
                return {
                    "status": "collected",
                    "checkpoint_id": checkpoint["id"],
                    "task_id": checkpoint["task_id"],
                    "snapshot_id": collected["metric_snapshot"]["id"],
                    "source_kind": provenance.get("source_kind"),
                    "refreshed": True,
                }
    except HTTPException as exc:
        updated = store.defer_metric_checkpoint(
            checkpoint["id"],
            reason=f"creator_center_mcp_unavailable: {exc.detail}",
            retry_after_minutes=60,
        )
        return {"status": "deferred", "checkpoint": updated, "reason": updated.get("last_error")}
    except Exception as exc:
        updated = store.defer_metric_checkpoint(
            checkpoint["id"],
            reason=f"creator_center_mcp_error: {type(exc).__name__}",
            retry_after_minutes=60,
        )
        return {"status": "deferred", "checkpoint": updated, "reason": updated.get("last_error")}
    return _collect_one_metric_checkpoint(store, checkpoint)


def _collect_due_metric_checkpoints(store, *, limit: int | None = None) -> dict:
    checkpoints = store.list_due_metric_checkpoints(limit=limit or _metric_scheduler_limit())
    result = {"due": len(checkpoints), "collected": 0, "deferred": 0, "errors": 0, "items": []}
    for checkpoint in checkpoints:
        try:
            item = _collect_one_metric_checkpoint(store, checkpoint)
        except Exception as exc:
            result["errors"] += 1
            item = {"status": "error", "checkpoint_id": checkpoint.get("id"), "reason": str(exc)}
        if item.get("status") == "collected":
            result["collected"] += 1
        elif item.get("status") == "deferred":
            result["deferred"] += 1
        result["items"].append(item)
    return result


async def _collect_due_metric_checkpoints_async(store, *, limit: int | None = None) -> dict:
    checkpoints = store.list_due_metric_checkpoints(limit=limit or _metric_scheduler_limit())
    result = {"due": len(checkpoints), "collected": 0, "deferred": 0, "errors": 0, "items": []}
    for checkpoint in checkpoints:
        try:
            item = await _collect_one_metric_checkpoint_with_refresh(store, checkpoint)
        except Exception as exc:
            result["errors"] += 1
            item = {"status": "error", "checkpoint_id": checkpoint.get("id"), "reason": str(exc)}
        if item.get("status") == "collected":
            result["collected"] += 1
        elif item.get("status") == "deferred":
            result["deferred"] += 1
        result["items"].append(item)
    return result


async def _run_scheduler_cycle() -> dict:
    """Run one production scheduler cycle, including desktop-owned sessions."""
    result = {
        "expired_approvals": 0, "workflow_started": False,
        "tasks_auto_resumed": 0, "metric_checkpoints": {"due": 0, "collected": 0, "deferred": 0, "errors": 0, "items": []},
    }
    svc = _get_agent_service()
    if svc is not None:
        store = svc.get_store()
        expired = await asyncio.to_thread(
            store.expire_stale_approvals,
            _approval_timeout_seconds(),
        )
        result["expired_approvals"] = len(expired)
        result["metric_checkpoints"] = await _collect_due_metric_checkpoints_async(store)
        resume_safe = getattr(svc, "resume_safe_interrupted_tasks", None)
        if resume_safe is not None:
            resumed = await resume_safe(limit=1)
            result["tasks_auto_resumed"] = len(resumed)

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
    3. Resumes at most one process-interrupted safe task; approvals/effects stay paused.
    4. Collects due publishing metric checkpoints when a safe adapter exists;
       otherwise records the missing adapter and retries later without fake data.
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

def _sql_publishing_tasks_payload(status: str | None = None, platform: str | None = None) -> dict:
    svc = _get_agent_service()
    if svc is None:
        return {"tasks": [], "total": 0, "source": "sql_store"}
    store = svc.get_store()
    tasks = store.list_publishing_tasks(status=status, platform=platform)
    enriched = []
    for task in tasks:
        receipt = task.get("receipt") or {}
        needs_query = (
            task.get("status") in {"queued", "executing", "failed"}
            or (task.get("status") == "published" and not (receipt.get("published_url") or receipt.get("platform_post_id")))
        )
        enriched.append({
            **task,
            "metric_checkpoints": store.list_metric_checkpoints(task["id"]),
            "metric_snapshots": store.list_metric_snapshots(task["id"]),
            "recommended_next_action": "marketing_publish_query" if needs_query else None,
        })
    return {"tasks": enriched, "total": len(enriched), "source": "sql_store"}


def agent_publishing_tasks(params: dict | None = None):
    params = params or {}
    status = str(params.get("status") or "").strip() or None
    platform = str(params.get("platform") or "").strip() or None
    return _sql_publishing_tasks_payload(status=status, platform=platform)

@app.get("/api/plugins/marketing-os/publishing/sql-tasks")
def list_sql_publishing_tasks(status: str | None = None, platform: str | None = None):
    return _sql_publishing_tasks_payload(status=status, platform=platform)


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


@app.post("/api/plugins/marketing-os/publishing/sql-tasks/{task_id}/query")
async def query_sql_publishing_task(task_id: str, body: dict | None = None):
    svc = _get_agent_service()
    refresh = bool((body or {}).get("refresh", True))
    try:
        return await _query_publishing_task_receipt(
            svc.get_store(), task_id, refresh=refresh,
        )
    except KeyError:
        raise HTTPException(404, "task not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/plugins/marketing-os/publishing/sql-tasks/{task_id}/metrics")
def collect_publishing_metrics(task_id: str, body: dict):
    svc = _get_agent_service()
    metrics = body.get("metrics") or {}
    checkpoint_id = str(body.get("checkpoint_id") or "").strip() or None
    provenance = body.get("provenance") if isinstance(body.get("provenance"), dict) else None
    try:
        task = svc.get_store().collect_metrics(
            task_id, metrics, checkpoint_id=checkpoint_id, provenance=provenance,
        )
        return {"success": True, "task": task}
    except KeyError:
        raise HTTPException(404, "task not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


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


def _normalise_content_asset_payload(params: dict) -> tuple[str, dict]:
    raw_type = str(params.get("type", "script") or "script")
    asset_type = raw_type
    if raw_type not in {"script", "video", "image", "caption"}:
        lowered = raw_type.lower()
        if "script" in lowered or "文案" in lowered or "脚本" in lowered:
            asset_type = "script"
        elif "video" in lowered or "视频" in lowered:
            asset_type = "video"
        elif "image" in lowered or "图" in lowered:
            asset_type = "image"
        elif "caption" in lowered or "标题" in lowered:
            asset_type = "caption"
        else:
            asset_type = "script"
    raw_content = params.get("content")
    if raw_content in (None, "") and params.get("body") not in (None, ""):
        raw_content = params.get("body")
    if isinstance(raw_content, dict):
        content = raw_content
    elif isinstance(raw_content, list):
        content = {"items": raw_content}
    elif raw_content in (None, ""):
        content = {}
    else:
        content = {"body": str(raw_content)}
    return asset_type, content


def create_content_asset(params: dict) -> dict:
    svc = _get_agent_service()
    store = svc.get_store()
    title = str(params.get("title", ""))
    if not title.strip():
        return {"status": "error", "reason": "title is required"}
    asset_type, content = _normalise_content_asset_payload(params)
    asset = store.create_content_asset(
        title=title[:200],
        type=asset_type,
        user_id=str(params.get("__user_id", "default")),
        account_id=params.get("account_id"),
        platform=params.get("platform"),
        content=content,
    )
    return {"status": "ok", "id": asset["id"], "title": asset["title"], "type": asset["type"]}


def create_content_preflight(params: dict) -> dict:
    from agent_core.production_preflight import create_content_production_preflight

    return create_content_production_preflight(_get_agent_service().get_store(), params)


def create_soft_article_asset(params: dict) -> dict:
    from agent_core.article_soft_production import create_soft_article_asset as run_soft_article

    return run_soft_article(_get_agent_service().get_store(), params)


def create_faceless_video_asset(params: dict) -> dict:
    from agent_core.faceless_video_production import create_faceless_video_asset as run_faceless_video

    return run_faceless_video(_get_agent_service().get_store(), params)


def create_content_from_experiment(params: dict) -> dict:
    from agent_core.experiment_driven_production import create_content_from_experiment as run_from_experiment

    return run_from_experiment(_get_agent_service().get_store(), params)


def prepare_faceless_render(params: dict) -> dict:
    from agent_core.faceless_video_production import prepare_faceless_render as run_prepare_render

    return run_prepare_render(_get_agent_service().get_store(), params)


def render_faceless_animatic(params: dict) -> dict:
    from agent_core.faceless_video_production import render_faceless_animatic as run_render_animatic

    return run_render_animatic(_get_agent_service().get_store(), params)


def fill_faceless_image_materials(params: dict) -> dict:
    from agent_core.faceless_video_production import fill_faceless_image_materials as run_fill_image_materials

    return run_fill_image_materials(_get_agent_service().get_store(), params)


def render_faceless_final(params: dict) -> dict:
    from agent_core.faceless_video_production import render_faceless_final as run_render_final

    return run_render_final(_get_agent_service().get_store(), params)


def review_content_asset(params: dict) -> dict:
    from agent_core.learning_pipeline import review_content_asset as run_review

    asset_id = str(params.get("asset_id", "")).strip()
    scores = params.get("scores")
    if not asset_id:
        return {"status": "error", "reason": "asset_id is required"}
    if not isinstance(scores, dict):
        return {"status": "error", "reason": "scores object is required"}
    return run_review(
        _get_agent_service().get_store(),
        asset_id=asset_id,
        scores=scores,
        prediction=params.get("prediction") if isinstance(params.get("prediction"), dict) else None,
        task_id=str(params.get("__task_id", "")) or None,
        notes=str(params.get("notes", ""))[:1000],
    )


def learning_status(params: dict | None = None) -> dict:
    from agent_core.learning_pipeline import get_learning_status

    params = params or {}
    return get_learning_status(
        _get_agent_service().get_store(),
        user_id=str(params.get("__user_id", "default")),
        account_id=params.get("account_id"),
    )


def learning_candidates(params: dict | None = None) -> dict:
    params = params or {}
    store = _get_agent_service().get_store()
    return {
        "candidates": store.list_learning_candidates(
            candidate_type=params.get("candidate_type"),
            status=params.get("status"),
            user_id=str(params.get("__user_id", "default")),
            account_id=params.get("account_id"),
            platform=params.get("platform"),
            limit=int(params.get("limit") or 50),
        ),
        "note": "pending 候选只是复盘观察，不能静默晋升为正式记忆或策略权重",
    }


def weight_candidate_replay(params: dict | None = None) -> dict:
    from agent_core.learning_governance import replay_weight_candidate

    params = params or {}
    candidate_id = str(params.get("candidate_id") or "").strip()
    if not candidate_id:
        raise ValueError("candidate_id is required")
    return replay_weight_candidate(
        _get_agent_service().get_store(),
        candidate_id,
        window=int(params.get("window") or 50),
        min_support=int(params["min_support"]) if params.get("min_support") else None,
    )


def decide_weight_candidate(params: dict | None = None) -> dict:
    from agent_core.learning_governance import decide_weight_candidate_with_replay

    params = params or {}
    candidate_id = str(params.get("candidate_id") or "").strip()
    if not candidate_id:
        raise ValueError("candidate_id is required")
    return decide_weight_candidate_with_replay(
        _get_agent_service().get_store(),
        candidate_id,
        decision=str(params.get("decision") or params.get("status") or ""),
        reason=str(params.get("reason") or "").strip() or None,
        window=int(params.get("window") or 50),
        min_support=int(params["min_support"]) if params.get("min_support") else None,
    )


def influence_score(params: dict | None = None) -> dict:
    from agent_core.influence_score import build_asset_influence_score, build_influence_score

    params = params or {}
    store = _get_agent_service().get_store()
    asset_id = str(params.get("asset_id") or "").strip()
    metric_labels = params.get("metric_labels") if isinstance(params.get("metric_labels"), dict) else None
    if asset_id:
        return build_asset_influence_score(store, asset_id, metric_labels=metric_labels)
    return build_influence_score({
        "metric_labels": metric_labels or {},
        "content_score": params.get("content_score") if isinstance(params.get("content_score"), dict) else {},
        "preflight_scores": params.get("preflight_scores") if isinstance(params.get("preflight_scores"), dict) else {},
    })


def preflight_decision(params: dict | None = None) -> dict:
    from agent_core.preflight_decision import (
        build_asset_preflight_decision,
        build_score_preflight_decision,
    )

    params = params or {}
    store = _get_agent_service().get_store()
    asset_id = str(params.get("asset_id") or "").strip()
    stage = str(params.get("stage") or "production_draft").strip() or "production_draft"
    context = params.get("context") if isinstance(params.get("context"), dict) else {}
    metric_labels = params.get("metric_labels") if isinstance(params.get("metric_labels"), dict) else None
    if asset_id:
        return build_asset_preflight_decision(
            store,
            asset_id,
            stage=stage,
            metric_labels=metric_labels,
            context=context,
        )
    return build_score_preflight_decision(params, stage=stage)


@app.get("/api/plugins/marketing-os/learning/candidates")
def get_learning_candidates(
    account_id: str | None = None,
    platform: str | None = None,
    candidate_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
):
    try:
        return learning_candidates({
            "account_id": account_id,
            "platform": platform,
            "candidate_type": candidate_type,
            "status": status,
            "limit": limit,
        })
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/plugins/marketing-os/learning/weight-replay")
def get_weight_candidate_replay(
    candidate_id: str,
    window: int = 50,
    min_support: int | None = None,
):
    try:
        return weight_candidate_replay({
            "candidate_id": candidate_id,
            "window": window,
            "min_support": min_support,
        })
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/plugins/marketing-os/learning/weight-decision")
def post_weight_candidate_decision(body: dict):
    try:
        return decide_weight_candidate(body)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/plugins/marketing-os/influence/score")
def get_influence_score(asset_id: str):
    try:
        return influence_score({"asset_id": asset_id})
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/plugins/marketing-os/preflight/decision")
def get_preflight_decision(asset_id: str, stage: str = "publish_review"):
    try:
        return preflight_decision({"asset_id": asset_id, "stage": stage})
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/plugins/marketing-os/preflight/decision")
def post_preflight_decision(body: dict):
    try:
        return preflight_decision(body)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def _lifecycle_identity(params: dict | None) -> tuple[str, str]:
    """Resolve a real account or a stable pre-login strategy workspace."""
    params = params or {}
    user_id = str(params.get("__user_id") or params.get("user_id") or "default").strip() or "default"
    account_id = str(params.get("account_id") or "").strip()
    if not account_id and params.get("__task_id"):
        try:
            task = _get_agent_service().get_store().get_task(str(params["__task_id"]))
            account_id = str(task.get("account_id") or "").strip()
        except KeyError:
            pass
    if not account_id:
        safe_user = re.sub(r"[^A-Za-z0-9_-]", "_", user_id)[:80] or "default"
        account_id = f"prospect_{safe_user}"
    return user_id, account_id


def account_lifecycle_status(params: dict | None = None) -> dict:
    from agent_core import AccountLifecycleService

    params = params or {}
    user_id, account_id = _lifecycle_identity(params)
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    return lifecycle.read_account_status(user_id=user_id, account_id=account_id)


def bind_prospect_strategy(params: dict) -> dict:
    """Attach the current user's pre-login strategy to a connected account."""
    from agent_core import AccountLifecycleService

    user_id = str(params.get("__user_id") or params.get("user_id") or "default").strip() or "default"
    target_account_id = str(params.get("account_id") or "").strip()
    if not target_account_id:
        raise ValueError("account_id is required")
    safe_user = re.sub(r"[^A-Za-z0-9_-]", "_", user_id)[:80] or "default"
    prospect_account_id = str(params.get("prospect_account_id") or f"prospect_{safe_user}").strip()
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    return lifecycle.bind_prospect_project(
        user_id=user_id,
        prospect_account_id=prospect_account_id,
        target_account_id=target_account_id,
        project_id=str(params.get("project_id") or "").strip(),
    )


def draft_audience_hypothesis(params: dict) -> dict:
    from agent_core import AccountLifecycleService

    user_id, account_id = _lifecycle_identity(params)
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    project = lifecycle.get_active_project(user_id=user_id, account_id=account_id)
    if project is None:
        goal = str(params.get("business_goal") or "").strip()
        if not goal:
            raise ValueError("business_goal is required when starting an account strategy")
        project = lifecycle.create_project(
            user_id=user_id, account_id=account_id, business_goal=goal,
            constraints=params.get("constraints") if isinstance(params.get("constraints"), dict) else {},
        )
    draft = lifecycle.draft_audience_hypothesis(
        user_id=user_id, account_id=account_id, project_id=project["id"],
        segments=params.get("segments") if isinstance(params.get("segments"), list) else [],
        pains=params.get("pains") if isinstance(params.get("pains"), list) else [],
        scenarios=params.get("scenarios") if isinstance(params.get("scenarios"), list) else [],
        exclusions=params.get("exclusions") if isinstance(params.get("exclusions"), list) else [],
        data_gaps=params.get("data_gaps") if isinstance(params.get("data_gaps"), list) else [],
    )
    return {"project": project, "draft": draft, "next_action": "ask_user_to_confirm_audience"}


def confirm_audience_hypothesis(params: dict) -> dict:
    from agent_core import AccountLifecycleService

    user_id, account_id = _lifecycle_identity(params)
    project_id = str(params.get("project_id") or "").strip()
    hypothesis_id = str(params.get("hypothesis_id") or "").strip()
    if not all((account_id, project_id, hypothesis_id)):
        raise ValueError("account_id, project_id and hypothesis_id are required")
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    confirmed = lifecycle.confirm_audience_hypothesis(
        user_id=user_id, account_id=account_id, project_id=project_id,
        hypothesis_id=hypothesis_id,
    )
    return {
        "confirmed": confirmed,
        "lifecycle": lifecycle.read_status(
            user_id=user_id, account_id=account_id, project_id=project_id,
        ),
    }


def benchmark_research(params: dict | None = None) -> dict:
    from agent_core import AccountLifecycleService

    params = params or {}
    user_id, account_id = _lifecycle_identity(params)
    project_id = str(params.get("project_id") or "").strip()
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    if not project_id:
        project = lifecycle.get_active_project(user_id=user_id, account_id=account_id)
        if project is None:
            return {"status": "not_started", "accounts": [], "observations": []}
        project_id = project["id"]
    return {
        "project_id": project_id,
        "readiness": lifecycle.benchmark_readiness(
            user_id=user_id, account_id=account_id, project_id=project_id,
        ),
        "accounts": lifecycle.list_benchmark_accounts(
            user_id=user_id, account_id=account_id, project_id=project_id,
        ),
        "observations": lifecycle.list_benchmark_observations(
            user_id=user_id, account_id=account_id, project_id=project_id,
        ),
        "samples": lifecycle.list_benchmark_samples(
            user_id=user_id, account_id=account_id, project_id=project_id,
        ),
    }


def discover_benchmarks(params: dict) -> dict:
    """Discover and persist benchmark candidates from product-owned evidence."""
    from agent_core import AccountLifecycleService
    from agent_core.benchmark_discovery import discover_benchmark_candidates

    user_id, account_id = _lifecycle_identity(params)
    query = str(params.get("query") or "").strip()
    if not query:
        raise ValueError("query is required")
    platform = str(params.get("platform") or "").strip().lower() or None
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    project_id = str(params.get("project_id") or "").strip()
    if not project_id:
        project = lifecycle.get_active_project(user_id=user_id, account_id=account_id)
        if project is None:
            raise ValueError("an active strategy project is required")
        project_id = project["id"]
    status = lifecycle.read_status(user_id=user_id, account_id=account_id, project_id=project_id)

    cached = query_trending_cache({"platform": platform, "limit": 30})
    result = discover_benchmark_candidates(
        query=query,
        items=list(cached.get("top_trends") or []),
        audience_hypothesis=status.get("audience_hypothesis"),
        platform=platform,
        limit=int(params.get("limit") or 10),
    )
    source_errors: dict[str, str] = {}
    source_mode = "cache"
    if not result["candidates"] and platform in (None, "bilibili"):
        try:
            from marketing_tools.scraping_backends.bilibili_public import BilibiliPublicBackend
            live_items = BilibiliPublicBackend().search_content(query, count=30)
            result = discover_benchmark_candidates(
                query=query, items=live_items,
                audience_hypothesis=status.get("audience_hypothesis"),
                platform="bilibili", limit=int(params.get("limit") or 10),
            )
            source_mode = "bilibili_public_search"
        except Exception as exc:
            source_errors["bilibili_public_search"] = str(exc)[:300]
    if platform == "douyin" and not result["candidates"]:
        source_errors["douyin_creator_discovery"] = (
            "current creator-center evidence has no third-party creator identity; "
            "public Douyin search may require a separate login or human verification"
        )
    existing = {
        (item["platform"], item["account_handle"]): item
        for item in lifecycle.list_benchmark_accounts(
            user_id=user_id, account_id=account_id, project_id=project_id,
        )
    }
    persisted = []
    suppressed_rejected = 0
    for candidate in result["candidates"]:
        key = (candidate["platform"], candidate["account_handle"])
        benchmark = existing.get(key)
        if benchmark is not None and benchmark["selection_status"] == "rejected":
            suppressed_rejected += 1
            continue
        if benchmark is None:
            benchmark = lifecycle.add_benchmark_account(
                user_id=user_id, account_id=account_id, project_id=project_id,
                platform=candidate["platform"], account_handle=candidate["account_handle"],
                account_name=candidate["account_name"], relation=candidate["suggested_relation"],
                selection_reason=candidate["selection_reason"],
                source_ref=candidate["source_ref"], selection_status="candidate",
            )
            existing[key] = benchmark
        prior_refs = {
            str(item.get("provenance", {}).get("source_ref") or "")
            for item in lifecycle.list_benchmark_samples(
                user_id=user_id, account_id=account_id, project_id=project_id,
            ) if item["benchmark_account_id"] == benchmark["id"]
        }
        imported = 0
        for sample in candidate["samples"]:
            provenance = sample["provenance"]
            if (
                not sample["title"] or not provenance.get("source_ref")
                or not provenance.get("captured_at")
                or provenance["source_ref"] in prior_refs
            ):
                continue
            lifecycle.add_benchmark_sample(
                user_id=user_id, account_id=account_id, project_id=project_id,
                benchmark_account_id=benchmark["id"], video_id=sample["video_id"],
                title=sample["title"], transcript=None, metrics=sample["metrics"],
                provenance=provenance,
            )
            prior_refs.add(provenance["source_ref"])
            imported += 1
        persisted.append({
            **candidate, "benchmark_account_id": benchmark["id"],
            "selection_status": benchmark["selection_status"],
            "samples_imported": imported,
        })
    return {
        **result, "project_id": project_id, "candidates": persisted,
        "candidate_count": len(persisted),
        "discovered_count": result["candidate_count"],
        "suppressed_rejected": suppressed_rejected,
        "cache_status": cached.get("status"),
        "cache_age_seconds": cached.get("cache_age_seconds"),
        "source_mode": source_mode, "source_errors": source_errors,
        "source_coverage": {
            "bilibili": "public_keyword_search_and_cache",
            "douyin": "cache_only_when_creator_identity_is_present",
        },
        "next_action": "ask_user_to_select_positive_and_negative_benchmarks"
        if persisted else "refresh_or_add_benchmark_source",
    }


def add_benchmark_account(params: dict) -> dict:
    from agent_core import AccountLifecycleService

    user_id, account_id = _lifecycle_identity(params)
    project_id = str(params.get("project_id") or "").strip()
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    return lifecycle.add_benchmark_account(
        user_id=user_id, account_id=account_id, project_id=project_id,
        platform=str(params.get("platform") or ""),
        account_handle=str(params.get("account_handle") or ""),
        account_name=params.get("account_name"), relation=str(params.get("relation") or ""),
        selection_reason=str(params.get("selection_reason") or ""),
        source_ref=str(params.get("source_ref") or ""),
        selection_status=str(params.get("selection_status") or "candidate"),
    )


def decide_benchmark_account(params: dict) -> dict:
    from agent_core import AccountLifecycleService

    user_id, account_id = _lifecycle_identity(params)
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    return lifecycle.decide_benchmark_account(
        user_id=user_id, account_id=account_id,
        project_id=str(params.get("project_id") or ""),
        benchmark_account_id=str(params.get("benchmark_account_id") or ""),
        decision=str(params.get("decision") or ""),
        relation=str(params.get("relation") or "") or None,
    )


def add_benchmark_observation(params: dict) -> dict:
    from agent_core import AccountLifecycleService

    user_id, account_id = _lifecycle_identity(params)
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    return lifecycle.add_benchmark_observation(
        user_id=user_id, account_id=account_id,
        project_id=str(params.get("project_id") or ""),
        benchmark_account_id=str(params.get("benchmark_account_id") or ""),
        dimension=str(params.get("dimension") or ""),
        value=params.get("value") if isinstance(params.get("value"), dict) else {},
        provenance=params.get("provenance") if isinstance(params.get("provenance"), dict) else {},
        confidence=float(params.get("confidence", 0)),
    )


def add_benchmark_sample(params: dict) -> dict:
    from agent_core import AccountLifecycleService

    user_id, account_id = _lifecycle_identity(params)
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    return lifecycle.add_benchmark_sample(
        user_id=user_id, account_id=account_id,
        project_id=str(params.get("project_id") or ""),
        benchmark_account_id=str(params.get("benchmark_account_id") or ""),
        video_id=str(params.get("video_id") or "") or None,
        title=str(params.get("title") or ""),
        transcript=str(params.get("transcript") or "") or None,
        metrics=params.get("metrics") if isinstance(params.get("metrics"), dict) else {},
        provenance=params.get("provenance") if isinstance(params.get("provenance"), dict) else {},
    )


def positioning_versions(params: dict | None = None) -> dict:
    from agent_core import AccountLifecycleService

    params = params or {}
    user_id, account_id = _lifecycle_identity(params)
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    project_id = str(params.get("project_id") or "").strip()
    if not project_id:
        project = lifecycle.get_active_project(user_id=user_id, account_id=account_id)
        if project is None:
            return {"project_id": None, "versions": [], "active_dna": None}
        project_id = project["id"]
    return {
        "project_id": project_id,
        "versions": lifecycle.list_positioning_versions(
            user_id=user_id, account_id=account_id, project_id=project_id,
        ),
        "active_dna": lifecycle.account_dna_projection(
            user_id=user_id, account_id=account_id, project_id=project_id,
        ),
    }


def draft_positioning(params: dict) -> dict:
    from agent_core import AccountLifecycleService

    user_id, account_id = _lifecycle_identity(params)
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    return lifecycle.draft_positioning(
        user_id=user_id, account_id=account_id,
        project_id=str(params.get("project_id") or ""),
        positioning=params.get("positioning") if isinstance(params.get("positioning"), dict) else {},
        evidence_refs=params.get("evidence_refs") if isinstance(params.get("evidence_refs"), list) else [],
    )


def approve_positioning(params: dict) -> dict:
    from agent_core import AccountLifecycleService

    user_id, account_id = _lifecycle_identity(params)
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    return lifecycle.approve_positioning(
        user_id=user_id, account_id=account_id,
        project_id=str(params.get("project_id") or ""),
        positioning_id=str(params.get("positioning_id") or ""),
    )


def rollback_positioning(params: dict) -> dict:
    from agent_core import AccountLifecycleService

    user_id, account_id = _lifecycle_identity(params)
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    return lifecycle.rollback_positioning(
        user_id=user_id, account_id=account_id,
        project_id=str(params.get("project_id") or ""),
        target_positioning_id=str(params.get("target_positioning_id") or ""),
    )


def audience_snapshots(params: dict | None = None) -> dict:
    from agent_core import AccountLifecycleService

    params = params or {}
    user_id, account_id = _lifecycle_identity(params)
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    project_id = str(params.get("project_id") or "").strip()
    if not project_id:
        project = lifecycle.get_active_project(user_id=user_id, account_id=account_id)
        if project is None:
            return {"project_id": None, "snapshots": [], "latest": None}
        project_id = project["id"]
    snapshots = lifecycle.list_audience_snapshots(
        user_id=user_id, account_id=account_id, project_id=project_id,
        platform=str(params.get("platform") or "") or None,
        limit=int(params.get("limit", 20)),
    )
    return {
        "project_id": project_id,
        "snapshots": snapshots,
        "latest": snapshots[0] if snapshots else None,
    }


def ingest_audience_snapshot(params: dict) -> dict:
    from agent_core import AccountLifecycleService

    user_id, account_id = _lifecycle_identity(params)
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    return lifecycle.add_audience_snapshot(
        user_id=user_id, account_id=account_id,
        project_id=str(params.get("project_id") or ""),
        platform=str(params.get("platform") or ""),
        dimensions=params.get("dimensions") if isinstance(params.get("dimensions"), dict) else {},
        provenance=params.get("provenance") if isinstance(params.get("provenance"), dict) else {},
        window_start=str(params.get("window_start") or "") or None,
        window_end=str(params.get("window_end") or "") or None,
    )


def account_experiments(params: dict | None = None) -> dict:
    from agent_core import AccountLifecycleService

    params = params or {}
    user_id, account_id = _lifecycle_identity(params)
    project_id = str(params.get("project_id") or "").strip()
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    if not project_id:
        project = lifecycle.get_active_project(user_id=user_id, account_id=account_id)
        if project is None:
            return {"project_id": None, "experiments": []}
        project_id = project["id"]
    experiment_id = str(params.get("experiment_id") or "").strip()
    if experiment_id:
        return lifecycle.experiment_timeline(
            user_id=user_id, account_id=account_id, project_id=project_id,
            experiment_id=experiment_id,
        )
    return {
        "project_id": project_id,
        "experiments": lifecycle.list_experiments(
            user_id=user_id, account_id=account_id, project_id=project_id,
        ),
    }


def create_account_experiment(params: dict) -> dict:
    from agent_core import AccountLifecycleService

    user_id, account_id = _lifecycle_identity(params)
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    return lifecycle.create_experiment(
        user_id=user_id, account_id=account_id,
        project_id=str(params.get("project_id") or ""),
        hypothesis=str(params.get("hypothesis") or ""),
        variable=params.get("variable") if isinstance(params.get("variable"), dict) else {},
        prediction=params.get("prediction") if isinstance(params.get("prediction"), dict) else {},
        success_criteria=params.get("success_criteria") if isinstance(params.get("success_criteria"), dict) else {},
    )


def attach_account_experiment_asset(params: dict) -> dict:
    from agent_core import AccountLifecycleService

    user_id, account_id = _lifecycle_identity(params)
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    return lifecycle.attach_experiment_asset(
        user_id=user_id, account_id=account_id,
        project_id=str(params.get("project_id") or ""),
        experiment_id=str(params.get("experiment_id") or ""),
        asset_id=str(params.get("asset_id") or ""),
    )


def audience_gap(params: dict | None = None) -> dict:
    from agent_core import AccountLifecycleService

    params = params or {}
    user_id, account_id = _lifecycle_identity(params)
    project_id = str(params.get("project_id") or "").strip()
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    if not project_id:
        project = lifecycle.get_active_project(user_id=user_id, account_id=account_id)
        if project is None:
            return {"status": "not_started", "dimension_comparisons": {}, "unknown_dimensions": []}
        project_id = project["id"]
    return lifecycle.compare_audience_gap(
        user_id=user_id, account_id=account_id, project_id=project_id,
    )


def strategy_candidates(params: dict | None = None) -> dict:
    from agent_core import AccountLifecycleService

    params = params or {}
    user_id, account_id = _lifecycle_identity(params)
    project_id = str(params.get("project_id") or "").strip()
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    if not project_id:
        project = lifecycle.get_active_project(user_id=user_id, account_id=account_id)
        if project is None:
            return {"project_id": None, "candidates": []}
        project_id = project["id"]
    return {
        "project_id": project_id,
        "candidates": lifecycle.list_strategy_candidates(
            user_id=user_id, account_id=account_id, project_id=project_id,
            status=str(params.get("status") or "") or None,
        ),
    }


def propose_strategy_candidate(params: dict) -> dict:
    from agent_core import AccountLifecycleService

    user_id, account_id = _lifecycle_identity(params)
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    return lifecycle.create_strategy_candidate(
        user_id=user_id, account_id=account_id,
        project_id=str(params.get("project_id") or ""),
        trigger=str(params.get("trigger") or ""),
        proposal=params.get("proposal") if isinstance(params.get("proposal"), dict) else {},
        evidence_refs=params.get("evidence_refs") if isinstance(params.get("evidence_refs"), list) else [],
        confidence=float(params.get("confidence", 0)),
    )


def decide_strategy_candidate(params: dict) -> dict:
    from agent_core import AccountLifecycleService

    user_id, account_id = _lifecycle_identity(params)
    lifecycle = AccountLifecycleService(_get_agent_service().get_store())
    return lifecycle.decide_strategy_candidate(
        user_id=user_id, account_id=account_id,
        project_id=str(params.get("project_id") or ""),
        candidate_id=str(params.get("candidate_id") or ""),
        decision=str(params.get("decision") or ""), reason=str(params.get("reason") or ""),
    )


@app.get("/api/plugins/marketing-os/accounts/{account_id}/lifecycle")
def get_account_lifecycle(account_id: str, user_id: str = "default"):
    return account_lifecycle_status({"account_id": account_id, "user_id": user_id})


@app.get("/api/plugins/marketing-os/lifecycle/prospect")
def get_prospect_lifecycle(user_id: str = "default"):
    return account_lifecycle_status({"user_id": user_id})


@app.post("/api/plugins/marketing-os/accounts/{account_id}/lifecycle/bind-prospect")
def post_bind_prospect_strategy(account_id: str, body: dict):
    params = dict(body)
    params["account_id"] = account_id
    try:
        return bind_prospect_strategy(params)
    except (ValueError, KeyError) as exc:
        raise HTTPException(409 if "already has" in str(exc) else 400, str(exc)) from exc


@app.post("/api/plugins/marketing-os/accounts/{account_id}/audience-hypotheses")
def post_audience_hypothesis(account_id: str, body: dict):
    params = dict(body)
    params["account_id"] = account_id
    return draft_audience_hypothesis(params)


@app.post("/api/plugins/marketing-os/accounts/{account_id}/audience-hypotheses/{hypothesis_id}/confirm")
def post_confirm_audience_hypothesis(account_id: str, hypothesis_id: str, body: dict):
    params = dict(body)
    params["account_id"] = account_id
    params["hypothesis_id"] = hypothesis_id
    return confirm_audience_hypothesis(params)


@app.get("/api/plugins/marketing-os/accounts/{account_id}/benchmarks")
def get_benchmark_research(account_id: str, project_id: str = "", user_id: str = "default"):
    return benchmark_research({
        "account_id": account_id, "project_id": project_id, "user_id": user_id,
    })


@app.post("/api/plugins/marketing-os/accounts/{account_id}/benchmarks/discover")
def post_discover_benchmarks(account_id: str, body: dict):
    params = dict(body)
    params["account_id"] = account_id
    try:
        return discover_benchmarks(params)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/plugins/marketing-os/accounts/{account_id}/benchmarks")
def post_benchmark_account(account_id: str, body: dict):
    params = dict(body)
    params["account_id"] = account_id
    return add_benchmark_account(params)


@app.post("/api/plugins/marketing-os/accounts/{account_id}/benchmarks/{benchmark_account_id}/observations")
def post_benchmark_observation(account_id: str, benchmark_account_id: str, body: dict):
    params = dict(body)
    params["account_id"] = account_id
    params["benchmark_account_id"] = benchmark_account_id
    return add_benchmark_observation(params)


@app.post("/api/plugins/marketing-os/accounts/{account_id}/benchmarks/{benchmark_account_id}/samples")
def post_benchmark_sample(account_id: str, benchmark_account_id: str, body: dict):
    params = dict(body)
    params["account_id"] = account_id
    params["benchmark_account_id"] = benchmark_account_id
    return add_benchmark_sample(params)


@app.post("/api/plugins/marketing-os/accounts/{account_id}/benchmarks/{benchmark_account_id}/decision")
def post_benchmark_decision(account_id: str, benchmark_account_id: str, body: dict):
    params = dict(body)
    params["account_id"] = account_id
    params["benchmark_account_id"] = benchmark_account_id
    return decide_benchmark_account(params)


@app.get("/api/plugins/marketing-os/accounts/{account_id}/positioning")
def get_positioning_versions(account_id: str, project_id: str = "", user_id: str = "default"):
    return positioning_versions({
        "account_id": account_id, "project_id": project_id, "user_id": user_id,
    })


@app.post("/api/plugins/marketing-os/accounts/{account_id}/positioning")
def post_positioning_draft(account_id: str, body: dict):
    params = dict(body)
    params["account_id"] = account_id
    return draft_positioning(params)


@app.post("/api/plugins/marketing-os/accounts/{account_id}/positioning/{positioning_id}/approve")
def post_positioning_approve(account_id: str, positioning_id: str, body: dict):
    params = dict(body)
    params["account_id"] = account_id
    params["positioning_id"] = positioning_id
    return approve_positioning(params)


@app.post("/api/plugins/marketing-os/accounts/{account_id}/positioning/{positioning_id}/rollback")
def post_positioning_rollback(account_id: str, positioning_id: str, body: dict):
    params = dict(body)
    params["account_id"] = account_id
    params["target_positioning_id"] = positioning_id
    return rollback_positioning(params)


@app.get("/api/plugins/marketing-os/accounts/{account_id}/audience-snapshots")
def get_audience_snapshots(
    account_id: str, project_id: str = "", platform: str = "",
    user_id: str = "default", limit: int = 20,
):
    return audience_snapshots({
        "account_id": account_id, "project_id": project_id, "platform": platform,
        "user_id": user_id, "limit": limit,
    })


@app.post("/api/plugins/marketing-os/accounts/{account_id}/audience-snapshots")
def post_audience_snapshot(account_id: str, body: dict):
    params = dict(body)
    params["account_id"] = account_id
    try:
        return ingest_audience_snapshot(params)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/plugins/marketing-os/accounts/{account_id}/experiments")
def get_account_experiments(
    account_id: str, project_id: str = "", experiment_id: str = "", user_id: str = "default",
):
    return account_experiments({
        "account_id": account_id, "project_id": project_id,
        "experiment_id": experiment_id, "user_id": user_id,
    })


@app.post("/api/plugins/marketing-os/accounts/{account_id}/experiments")
def post_account_experiment(account_id: str, body: dict):
    params = dict(body)
    params["account_id"] = account_id
    try:
        return create_account_experiment(params)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/plugins/marketing-os/accounts/{account_id}/experiments/{experiment_id}/assets")
def post_account_experiment_asset(account_id: str, experiment_id: str, body: dict):
    params = dict(body)
    params["account_id"] = account_id
    params["experiment_id"] = experiment_id
    try:
        return attach_account_experiment_asset(params)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/plugins/marketing-os/accounts/{account_id}/audience-gap")
def get_audience_gap(account_id: str, project_id: str = "", user_id: str = "default"):
    return audience_gap({
        "account_id": account_id, "project_id": project_id, "user_id": user_id,
    })


@app.get("/api/plugins/marketing-os/accounts/{account_id}/strategy-candidates")
def get_strategy_candidates(
    account_id: str, project_id: str = "", status: str = "", user_id: str = "default",
):
    return strategy_candidates({
        "account_id": account_id, "project_id": project_id, "status": status, "user_id": user_id,
    })


@app.post("/api/plugins/marketing-os/accounts/{account_id}/strategy-candidates")
def post_strategy_candidate(account_id: str, body: dict):
    params = dict(body)
    params["account_id"] = account_id
    try:
        return propose_strategy_candidate(params)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/plugins/marketing-os/accounts/{account_id}/strategy-candidates/{candidate_id}/decision")
def post_strategy_candidate_decision(account_id: str, candidate_id: str, body: dict):
    params = dict(body)
    params["account_id"] = account_id
    params["candidate_id"] = candidate_id
    try:
        return decide_strategy_candidate(params)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


def add_memory(params: dict) -> dict:
    svc = _get_agent_service()
    store = svc.get_store()
    kind = str(params.get("kind") or params.get("scope") or "user")
    memory_type = str(params.get("memory_type", ""))
    if kind not in {k.value for k in MemoryKind} and memory_type:
        if memory_type in {"user_preference", "preference", "user"}:
            kind = "user"
        elif memory_type in {"account_dna", "account"}:
            kind = "account"
        elif memory_type in {"project_event", "event", "episodic"}:
            kind = "episodic"
        elif memory_type in {"knowledge", "semantic"}:
            kind = "semantic"
        elif memory_type in {"workflow", "skill", "procedural"}:
            kind = "procedural"
    content_value = params.get("content")
    if content_value in (None, "") and params.get("value") not in (None, ""):
        key = str(params.get("key", "")).strip()
        value = params.get("value")
        if isinstance(value, (dict, list)):
            value_text = json.dumps(value, ensure_ascii=False)
        else:
            value_text = str(value)
        content_value = f"{key}：{value_text}" if key else value_text
    if isinstance(content_value, (dict, list)):
        content = json.dumps(content_value, ensure_ascii=False)
    else:
        content = str(content_value or "").strip()
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

        # Electron decrypts providers.env.encrypted with safeStorage and passes
        # provider variables only to this child process. Keep MARKETING_OS_*
        # overrides, but also consume the decrypted DEEPSEEK_* environment;
        # the legacy plaintext file is now only a direct-server fallback.
        model = os.environ.get(
            "MARKETING_OS_MODEL",
            os.environ.get("DEEPSEEK_MODEL", provider_env.get("DEEPSEEK_MODEL", "deepseek-chat")),
        )
        base_url = os.environ.get(
            "MARKETING_OS_BASE_URL",
            os.environ.get("DEEPSEEK_BASE_URL", provider_env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")),
        )
        api_key = os.environ.get(
            "MARKETING_OS_API_KEY",
            os.environ.get("DEEPSEEK_API_KEY", provider_env.get("DEEPSEEK_API_KEY", "")),
        )

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


def _agent_session_title(objective: str | None) -> str:
    title = str(objective or "").strip().replace("\n", " ")
    return title[:32] + ("…" if len(title) > 32 else "") if title else "新对话"


def _agent_session_messages(session_id: str) -> list[dict]:
    store = _get_agent_service().get_store()
    messages: list[dict] = []
    with store._connect() as db:
        tasks = db.execute(
            """SELECT id, objective, status, created_at, updated_at
            FROM agent_tasks WHERE session_id=? ORDER BY created_at""",
            (session_id,),
        ).fetchall()
        for task in tasks:
            messages.append({
                "role": "user",
                "content": task["objective"],
                "task_id": task["id"],
                "created_at": task["created_at"],
            })
            event = db.execute(
                """SELECT payload_json, event_type, created_at
                FROM task_events
                WHERE task_id=? AND event_type IN ('task.completed','task.failed','task.cancelled')
                ORDER BY sequence DESC LIMIT 1""",
                (task["id"],),
            ).fetchone()
            if event:
                payload = json.loads(event["payload_json"])
                if event["event_type"] == "task.completed":
                    content = str(payload.get("reply") or "").strip()
                    role = "assistant"
                elif event["event_type"] == "task.failed":
                    content = f"任务失败：{payload.get('error') or task['status']}"
                    role = "system"
                else:
                    content = "任务已取消"
                    role = "system"
                if content:
                    messages.append({
                        "role": role,
                        "content": content,
                        "task_id": task["id"],
                        "created_at": event["created_at"],
                    })
    return messages


@app.get("/agent/sessions")
async def agent_list_sessions(user_id: str = "default", limit: int = 30):
    store = _get_agent_service().get_store()
    safe_limit = max(1, min(int(limit or 30), 100))
    sessions: list[dict] = []
    with store._connect() as db:
        rows = db.execute(
            """SELECT * FROM agent_sessions
            WHERE user_id=?
            ORDER BY updated_at DESC
            LIMIT ?""",
            (user_id, safe_limit),
        ).fetchall()
        for row in rows:
            latest = db.execute(
                """SELECT id, objective, status, account_id, created_at, updated_at
                FROM agent_tasks
                WHERE session_id=?
                ORDER BY updated_at DESC LIMIT 1""",
                (row["id"],),
            ).fetchone()
            task_count = db.execute(
                "SELECT COUNT(*) FROM agent_tasks WHERE session_id=?",
                (row["id"],),
            ).fetchone()[0]
            sessions.append({
                "session_id": row["id"],
                "user_id": row["user_id"],
                "workspace": row["workspace"],
                "active_task_id": row["active_task_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "title": _agent_session_title(latest["objective"] if latest else None),
                "last_objective": latest["objective"] if latest else None,
                "last_task_id": latest["id"] if latest else None,
                "last_task_status": latest["status"] if latest else None,
                "account_id": latest["account_id"] if latest else None,
                "task_count": task_count,
            })
    return {"sessions": sessions, "total": len(sessions)}


@app.get("/agent/sessions/{session_id}")
async def agent_get_session(session_id: str):
    svc = _get_agent_service()
    result = await svc.get_session(session_id)
    if result is None:
        raise HTTPException(404, "会话不存在")
    return result


@app.get("/agent/sessions/{session_id}/messages")
async def agent_get_session_messages(session_id: str):
    svc = _get_agent_service()
    result = await svc.get_session(session_id)
    if result is None:
        raise HTTPException(404, "会话不存在")
    return {"session_id": session_id, "messages": _agent_session_messages(session_id)}


@app.post("/agent/messages")
async def agent_send_message(body: dict):
    session_id = str(body.get("session_id", "")).strip()
    message = str(body.get("message", "")).strip()
    if not session_id or not message:
        raise HTTPException(400, "session_id and message required")
    if len(message) > 8000:
        raise HTTPException(400, "message too long")
    account_id = str(body.get("account_id") or "").strip() or None
    requires_connected_account = any(marker in message for marker in (
        "当前账号", "这个账号", "该账号", "抖音账号", "账号数据",
        "粉丝", "点赞", "播放", "同步账号", "粉丝画像",
        "实验结果", "实际粉丝", "发布结果",
    ))
    pre_account_strategy = any(marker in message for marker in (
        "起号", "账号定位", "目标受众", "想做账号", "做什么内容",
        "怎么变现", "变现方向", "个人IP", "个人 IP",
    ))
    connected_accounts = [
        item for item in get_accounts().get("accounts", [])
        if item.get("status") == "connected"
    ]
    if account_id:
        if not any(item.get("id") == account_id for item in connected_accounts):
            raise HTTPException(409, "所选账号不存在或未连接，请重新选择账号")
    elif requires_connected_account:
        if len(connected_accounts) == 1:
            account_id = connected_accounts[0].get("id")
        elif len(connected_accounts) > 1:
            raise HTTPException(409, "该任务需要指定账号，请先选择一个已连接账号")
        else:
            raise HTTPException(409, "该任务需要账号上下文，请先连接账号")
    elif pre_account_strategy and len(connected_accounts) == 1:
        # A single connected account is a useful default. With zero or many
        # accounts, keep the strategy unbound so natural onboarding can proceed.
        account_id = connected_accounts[0].get("id")

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


@app.post("/agent/tasks/{task_id}/replan")
async def agent_replan_task(task_id: str, body: dict):
    new_objective = str(body.get("message", "") or body.get("objective", "")).strip()
    if not new_objective:
        raise HTTPException(400, "message or objective required")
    svc = _get_agent_service()
    try:
        return await svc.replan_task(task_id, new_objective)
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
