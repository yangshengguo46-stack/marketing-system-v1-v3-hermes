"""热点抓取工具 — 可插拔后端架构

后端优先级: Agent-Reach > HotTopics API > MediaCrawler > Browser CDP(兜底)
前端 3 个后端能直接返回数据，CDP 返回 agent-browser 指令
"""

import json
import logging
from datetime import datetime
from .scraping_backends import BACKENDS

logger = logging.getLogger("marketing-os.scraping")


def _list_available_backends() -> list[str]:
    return [b.name for b in BACKENDS if b.available()]


def _fetch_with_backend(platform: str, count: int) -> dict:
    """Try every available backend in priority order until one succeeds."""
    errors = {}
    candidates = sorted(BACKENDS, key=lambda backend: backend.priority, reverse=True)
    for backend in candidates:
        if not backend.supports(platform):
            continue
        try:
            if not backend.available():
                continue
            items = backend.fetch_trending(platform, count)
            return {
                "success": True,
                "backend_used": backend.name,
                "data": items,
                "count": len(items),
                "fallback_errors": errors,
            }
        except Exception as exc:
            logger.warning(f"后端 {backend.name} 抓取 {platform} 失败: {exc}")
            errors[backend.name] = str(exc)

    return {
        "success": False,
        "backend_used": None,
        "error": "; ".join(f"{name}: {message}" for name, message in errors.items()) or "没有可用抓取后端",
        "available_backends": _list_available_backends(),
    }


# ---- 各平台抓取工具 ----

def scrape_douyin_trending(params=None, **kwargs) -> str:
    count = (params or {}).get("count", 30)
    result = _fetch_with_backend("douyin", count)
    result["platform"] = "douyin"
    result["scraped_at"] = datetime.now().isoformat()
    return json.dumps(result, ensure_ascii=False)


def scrape_weibo_trending(params=None, **kwargs) -> str:
    count = (params or {}).get("count", 50)
    result = _fetch_with_backend("weibo", count)
    result["platform"] = "weibo"
    result["scraped_at"] = datetime.now().isoformat()
    return json.dumps(result, ensure_ascii=False)


def scrape_bilibili_popular(params=None, **kwargs) -> str:
    count = (params or {}).get("count", 30)
    result = _fetch_with_backend("bilibili", count)
    result["platform"] = "bilibili"
    result["scraped_at"] = datetime.now().isoformat()
    return json.dumps(result, ensure_ascii=False)


def scrape_xiaohongshu_trending(params=None, **kwargs) -> str:
    result = _fetch_with_backend("xiaohongshu", 30)
    result["platform"] = "xiaohongshu"
    result["scraped_at"] = datetime.now().isoformat()
    return json.dumps(result, ensure_ascii=False)


def scrape_kuaishou_trending(params=None, **kwargs) -> str:
    count = (params or {}).get("count", 30)
    result = _fetch_with_backend("kuaishou", count)
    result["platform"] = "kuaishou"
    result["scraped_at"] = datetime.now().isoformat()
    return json.dumps(result, ensure_ascii=False)


def scrape_zhihu_trending(params=None, **kwargs) -> str:
    count = (params or {}).get("count", 30)
    result = _fetch_with_backend("zhihu", count)
    result["platform"] = "zhihu"
    result["scraped_at"] = datetime.now().isoformat()
    return json.dumps(result, ensure_ascii=False)


def scrape_wechat_trending(params=None, **kwargs) -> str:
    result = _fetch_with_backend("wechat_article", 30)
    result["platform"] = "wechat_article"
    result["scraped_at"] = datetime.now().isoformat()
    return json.dumps(result, ensure_ascii=False)


def scrape_tiktok_trending(params=None, **kwargs) -> str:
    count = (params or {}).get("count", 30)
    result = _fetch_with_backend("tiktok", count)
    result["platform"] = "tiktok"
    result["scraped_at"] = datetime.now().isoformat()
    return json.dumps(result, ensure_ascii=False)


def scrape_youtube_trending(params=None, **kwargs) -> str:
    count = (params or {}).get("count", 30)
    result = _fetch_with_backend("youtube", count)
    result["platform"] = "youtube"
    result["scraped_at"] = datetime.now().isoformat()
    return json.dumps(result, ensure_ascii=False)


def scrape_twitter_trending(params=None, **kwargs) -> str:
    count = (params or {}).get("count", 30)
    result = _fetch_with_backend("twitter", count)
    result["platform"] = "twitter"
    result["scraped_at"] = datetime.now().isoformat()
    return json.dumps(result, ensure_ascii=False)


# ---- 聚合 ----

def aggregate_all_trending(params=None, **kwargs) -> str:
    platforms = (params or {}).get("platforms", ["douyin", "weibo", "bilibili", "xiaohongshu", "kuaishou", "zhihu", "tiktok", "youtube"])
    results = {}
    backends_used = set()

    for p in platforms:
        raw = _fetch_with_backend(p, 30)
        results[p] = raw
        backends_used.add(raw.get("backend_used", "unknown"))

    return json.dumps({
        "aggregated_at": datetime.now().isoformat(),
        "platforms_scraped": platforms,
        "backends_used": list(backends_used),
        "results": results,
    }, ensure_ascii=False)


# ---- 后端状态查询 ----

def list_scraping_backends(params=None, **kwargs) -> str:
    """查询所有抓取后端的可用状态"""
    info = []
    for b in BACKENDS:
        info.append({
            "name": b.name,
            "priority": b.priority,
            "available": b.available(),
            "platforms": b.platforms,
        })
    return json.dumps({
        "backends": info,
        "checked_at": datetime.now().isoformat(),
    }, ensure_ascii=False)


TOOLS = [
    {
        "name": "scrape_douyin_trending",
        "description": "抓取抖音实时热搜榜 TOP30，自动选择最佳可用后端",
        "schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "抓取条数，默认30", "default": 30}
            }
        },
        "handler": scrape_douyin_trending,
    },
    {
        "name": "scrape_weibo_trending",
        "description": "抓取微博实时热搜榜 TOP50，自动选择最佳可用后端",
        "schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "抓取条数，默认50", "default": 50}
            }
        },
        "handler": scrape_weibo_trending,
    },
    {
        "name": "scrape_bilibili_popular",
        "description": "抓取B站热门视频 TOP30，自动选择最佳可用后端",
        "schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "抓取条数，默认30", "default": 30}
            }
        },
        "handler": scrape_bilibili_popular,
    },
    {
        "name": "scrape_xiaohongshu_trending",
        "description": "抓取小红书探索页热门笔记",
        "schema": {
            "type": "object",
            "properties": {}
        },
        "handler": scrape_xiaohongshu_trending,
    },
    {
        "name": "scrape_kuaishou_trending",
        "description": "抓取快手热门推荐",
        "schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "抓取条数，默认30", "default": 30}
            }
        },
        "handler": scrape_kuaishou_trending,
    },
    {
        "name": "scrape_zhihu_trending",
        "description": "抓取知乎热榜",
        "schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "抓取条数，默认30", "default": 30}
            }
        },
        "handler": scrape_zhihu_trending,
    },
    {
        "name": "scrape_kuaishou_trending",
        "description": "抓取快手热门推荐",
        "schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "抓取条数", "default": 30}
            }
        },
        "handler": scrape_kuaishou_trending,
    },
    {
        "name": "scrape_wechat_trending",
        "description": "抓取微信公众号热门文章",
        "schema": {"type": "object", "properties": {}},
        "handler": scrape_wechat_trending,
    },
    {
        "name": "scrape_tiktok_trending",
        "description": "抓取 TikTok 全球热门",
        "schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "抓取条数", "default": 30}
            }
        },
        "handler": scrape_tiktok_trending,
    },
    {
        "name": "scrape_youtube_trending",
        "description": "抓取 YouTube 热门视频",
        "schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "抓取条数", "default": 30}
            }
        },
        "handler": scrape_youtube_trending,
    },
    {
        "name": "scrape_twitter_trending",
        "description": "抓取 Twitter/X 热门话题",
        "schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "抓取条数", "default": 30}
            }
        },
        "handler": scrape_twitter_trending,
    },
    {
        "name": "aggregate_all_trending",
        "description": "一次性抓取所有主流平台热搜并聚合，自动选择最佳后端",
        "schema": {
            "type": "object",
            "properties": {
                "platforms": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["douyin", "weibo", "bilibili", "xiaohongshu", "kuaishou", "zhihu", "wechat_article", "tiktok", "youtube", "twitter"]},
                    "description": "要抓取的平台列表，默认 ['douyin', 'weibo', 'bilibili']"
                }
            }
        },
        "handler": aggregate_all_trending,
    },
    {
        "name": "list_scraping_backends",
        "description": "查询所有抓取后端的可用状态和覆盖平台",
        "schema": {
            "type": "object",
            "properties": {}
        },
        "handler": list_scraping_backends,
    },
]
