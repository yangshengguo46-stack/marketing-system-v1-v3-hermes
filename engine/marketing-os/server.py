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

# 确保能导入 tools 模块
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import uvicorn

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


app = FastAPI(title="marketing-os API", lifespan=lifespan)

API_TOKEN = os.environ.get("MARKETING_OS_API_TOKEN", "")


@app.middleware("http")
async def require_local_api_token(request: Request, call_next):
    """Only the Electron main process may call the fixed loopback API."""
    if API_TOKEN and request.url.path.startswith("/api/"):
        supplied = request.headers.get("X-Marketing-OS-Token", "")
        if not secrets.compare_digest(supplied, API_TOKEN):
            return JSONResponse(status_code=401, content={"detail": "unauthorized local client"})
    return await call_next(request)

BUNDLED_CONFIG_DIR = Path(__file__).parent / "config"
CONFIG_DIR = Path(os.environ.get("MARKETING_OS_CONFIG_DIR", BUNDLED_CONFIG_DIR))


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


# ---- 热点趋势 ----

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


@app.post("/api/plugins/marketing-os/trending/refresh")
def refresh_trending(body: dict | None = None):
    """Run the built-in scraper, analyze its output, and persist both UI caches."""
    from tools.scraping import aggregate_all_trending

    requested = (body or {}).get("platforms")
    platforms = requested or ["douyin", "weibo", "bilibili", "zhihu"]
    raw = json.loads(aggregate_all_trending({"platforms": platforms}))
    return _persist_trending_analysis(raw, {"platforms_scraped": platforms})


def _persist_trending_analysis(raw: dict, metadata: dict | None = None) -> dict:
    from tools.content import analyze_trends, generate_content_suggestions

    analysis = json.loads(analyze_trends({"hot_data": raw}))
    successful = [
        platform for platform, result in raw.get("results", {}).items()
        if result.get("success")
    ]
    trending_cache = {
        **analysis,
        "status": "ok" if successful else "error",
        "cached_at": datetime.now().isoformat(),
        "platforms_scraped": raw.get("platforms_scraped", list(raw.get("results", {}))),
        "platforms_succeeded": successful,
        "backends_used": raw.get("backends_used", []),
        "errors": {
            platform: result.get("error", "抓取失败")
            for platform, result in raw.get("results", {}).items()
            if not result.get("success")
        },
        **(metadata or {}),
    }
    _write_json(CONFIG_DIR / "trending-cache.json", trending_cache)

    suggestions = json.loads(generate_content_suggestions({
        "user_profile": _default_profile(),
        "trends": analysis,
    }))
    suggestions_cache = {
        **suggestions,
        "status": "ok",
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
    items = []
    for index, item in enumerate(incoming[:100]):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        items.append({
            "rank": int(item.get("rank", index + 1) or index + 1),
            "title": title[:200],
            "url": str(item.get("url", ""))[:1000],
            "heat_value": item.get("heat_value", ""),
        })
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
    result = _persist_trending_analysis(raw, {"query": keyword, "source": "electron_session"})
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
    result = _persist_trending_analysis(raw, {"queries": list(dict.fromkeys(queries)), "source": "electron_session_batch"})
    return {**result, "imported_count": len(items), "queries": list(dict.fromkeys(queries))}


# ---- 账号管理 ----

@app.get("/api/plugins/marketing-os/accounts")
def get_accounts():
    acct_file = CONFIG_DIR / "accounts.json"
    if acct_file.exists():
        data = json.loads(acct_file.read_text())
        return {"accounts": data.get("accounts", []), "total": len(data.get("accounts", []))}
    return {"accounts": [], "total": 0}


@app.post("/api/plugins/marketing-os/accounts")
async def create_account(body: dict):
    if not body.get("platform") or not body.get("username"):
        raise HTTPException(400, "platform and username required")
    from tools.account import add_account
    params = {
        "platform": body["platform"],
        "username": body["username"],
        "label": body.get("label", ""),
        "password": body.get("password") or body.get("cookie", ""),
    }
    result = json.loads(add_account(params))
    if not result.get("success"):
        raise HTTPException(422, result.get("error", "账号保存失败"))
    return result


@app.delete("/api/plugins/marketing-os/accounts/{account_id}")
def delete_account(account_id: str):
    from tools.account import remove_account
    result = json.loads(remove_account({"account_id": account_id}))
    if not result.get("success"):
        raise HTTPException(404, result.get("error", "账号不存在"))
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


@app.post("/api/plugins/marketing-os/accounts/{account_id}/sync")
def sync_account_stats(account_id: str):
    from tools.monitor import analyze_account_trend, _parse_number
    data = _read_json(CONFIG_DIR / "accounts.json", {"accounts": []})
    account = next((item for item in data.get("accounts", []) if item.get("id") == account_id), None)
    if not account:
        raise HTTPException(404, "账号不存在")
    result = analyze_account_trend(account_id, account.get("platform", ""), account.get("username", ""))
    if result.get("status") == "error" or result.get("error"):
        raise HTTPException(422, result.get("error", "账号同步失败"))
    current = result.get("current_stats") or {}
    normalized = {
        key: int(_parse_number(value))
        for key, value in {
            "followers": current.get("followers"),
            "total_views": current.get("total_plays"),
            "total_likes": current.get("total_likes"),
        }.items()
        if value not in (None, "")
    }
    updated = _update_account_stats(account_id, {**normalized, "raw": current})
    return {"success": True, "account": updated, "alerts": result.get("alerts", []), "suggestions": result.get("content_suggestions", [])}


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


def _hermes_command() -> str | None:
    candidates = [
        os.environ.get("HERMES_CLI"),
        shutil.which("hermes"),
        str(Path.home() / ".local" / "bin" / "hermes"),
    ]
    return next((candidate for candidate in candidates if candidate and Path(candidate).exists()), None)


@app.get("/api/plugins/marketing-os/assistant/status")
def assistant_status():
    command = _hermes_command()
    return {"available": bool(command), "backend": "hermes" if command else None}


@app.post("/api/plugins/marketing-os/assistant/message")
def assistant_message(body: dict):
    import subprocess
    message = str(body.get("message", "")).strip()
    if not message:
        raise HTTPException(400, "message required")
    if len(message) > 2000:
        raise HTTPException(400, "message too long")
    history = []
    if isinstance(body.get("history"), list):
        for item in body["history"][-12:]:
            if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
                continue
            content = str(item.get("content", "")).strip()[:2000]
            if content:
                history.append({"role": item["role"], "content": content})
    command = _hermes_command()
    if not command:
        raise HTTPException(503, "Hermes CLI 未安装")

    trending = _read_json(CONFIG_DIR / "trending-cache.json", {})
    suggestions = _read_json(CONFIG_DIR / "suggestions-cache.json", {})
    context = {
        "top_trends": trending.get("top_trends", [])[:10],
        "suggestions": suggestions.get("suggestions", [])[:5],
        "overview": dashboard_overview(),
    }
    casual_only = bool(re.fullmatch(
        r"\s*(你好|您好|你好呀|嗨|hi|hello|在吗|你是谁|你能做什么)[!！。.，,？?\s]*",
        message,
        flags=re.IGNORECASE,
    ))
    history_text = "\n".join(
        f"{'用户' if item['role'] == 'user' else '助手'}：{item['content']}"
        for item in history
    ) or "（这是本次对话的第一句话）"
    data_text = (
        "本轮是寒暄或能力询问，不提供营销数据，也不要主动分析营销数据。"
        if casual_only
        else f"营销参考数据（只在问题相关时使用）：{json.dumps(context, ensure_ascii=False)}"
    )
    prompt = (
        "你是智能营销桌面应用中的助手。先判断用户是在寒暄、询问能力、讨论一般问题，还是明确请求营销分析。"
        "寒暄时自然简短回应，绝不能主动汇报热点、账号或选题；只有用户明确询问营销数据、策略或方案时才引用参考数据。"
        "你当前处于只读模式，不调用工具、不执行命令、不修改文件、不发布内容；如果数据不足必须说明。"
        "回答使用自然中文，不要每句话都强调自己是营销顾问。\n\n"
        f"最近对话：\n{history_text}\n\n"
        f"{data_text}\n\n"
        f"用户本轮消息：{message}"
    )
    try:
        result = subprocess.run(
            [command, "chat", "-q", prompt, "-t", "__none__", "--max-turns", "1", "--safe-mode", "--source", "tool", "-Q"],
            capture_output=True, text=True, timeout=90,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Hermes 响应超时")
    if result.returncode != 0:
        raise HTTPException(502, (result.stderr or result.stdout or "Hermes 调用失败")[-500:])
    lines = [
        line for line in result.stdout.splitlines()
        if line.strip() and not line.startswith("Warning:") and not line.startswith("session_id:")
    ]
    reply = "\n".join(lines).strip()
    if not reply:
        raise HTTPException(502, "Hermes 未返回内容")
    return {"reply": reply, "backend": "hermes", "read_only": True}


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


async def _scheduler_loop():
    """Small persistent scheduler; the Electron-owned backend is the single worker."""
    await asyncio.sleep(2)
    while True:
        try:
            if os.environ.get("MARKETING_OS_SESSION_ORCHESTRATOR") == "electron":
                await asyncio.sleep(int(os.environ.get("MARKETING_OS_SCHEDULER_INTERVAL", "30")))
                continue
            state = _workflow_state()
            if _workflow_due(state):
                await asyncio.to_thread(run_workflow, {"source": "schedule"})
        except Exception as exc:
            state = _workflow_state()
            state["scheduler_error"] = str(exc)
            _write_json(CONFIG_DIR / "workflow-state.json", state)
        await asyncio.sleep(int(os.environ.get("MARKETING_OS_SCHEDULER_INTERVAL", "30")))

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
        if tool_name == "pipeline_status":
            from tools.orchestration import pipeline_status
            return json.loads(pipeline_status(body))
        elif tool_name == "aggregate_all_trending":
            from tools.scraping import aggregate_all_trending
            return json.loads(aggregate_all_trending(body))
        elif tool_name == "scrape_douyin_trending":
            from tools.scraping import scrape_douyin_trending
            return json.loads(scrape_douyin_trending(body))
        elif tool_name == "scrape_weibo_trending":
            from tools.scraping import scrape_weibo_trending
            return json.loads(scrape_weibo_trending(body))
        elif tool_name == "scrape_bilibili_popular":
            from tools.scraping import scrape_bilibili_popular
            return json.loads(scrape_bilibili_popular(body))
        elif tool_name == "scrape_xiaohongshu_trending":
            from tools.scraping import scrape_xiaohongshu_trending
            return json.loads(scrape_xiaohongshu_trending(body))
        elif tool_name == "scrape_kuaishou_trending":
            from tools.scraping import scrape_kuaishou_trending
            return json.loads(scrape_kuaishou_trending(body))
        elif tool_name == "scrape_zhihu_trending":
            from tools.scraping import scrape_zhihu_trending
            return json.loads(scrape_zhihu_trending(body))
        elif tool_name == "scrape_wechat_trending":
            from tools.scraping import scrape_wechat_trending
            return json.loads(scrape_wechat_trending(body))
        elif tool_name == "scrape_tiktok_trending":
            from tools.scraping import scrape_tiktok_trending
            return json.loads(scrape_tiktok_trending(body))
        elif tool_name == "scrape_youtube_trending":
            from tools.scraping import scrape_youtube_trending
            return json.loads(scrape_youtube_trending(body))
        elif tool_name == "scrape_twitter_trending":
            from tools.scraping import scrape_twitter_trending
            return json.loads(scrape_twitter_trending(body))
        elif tool_name == "monitor_all":
            from tools.monitor import monitor_all
            return json.loads(monitor_all(body))
        elif tool_name == "analyze_trends":
            from tools.content import analyze_trends
            return json.loads(analyze_trends(body))
        elif tool_name == "generate_content_suggestions":
            from tools.content import generate_content_suggestions
            return json.loads(generate_content_suggestions(body))
        elif tool_name == "generate_media":
            from tools.orchestration import generate_media
            return json.loads(generate_media(body))
        elif tool_name == "list_scraping_backends":
            from tools.scraping import list_scraping_backends
            return json.loads(list_scraping_backends(body))
        else:
            raise HTTPException(404, f"未知工具: {tool_name}")
    except Exception as e:
        raise HTTPException(500, str(e))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=19519)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    import sys
    print(f"marketing-os API server starting on {args.host}:{args.port}", file=sys.stderr)
    uvicorn.run(app, host=args.host, port=args.port, log_level="error")
