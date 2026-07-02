"""Cookie-free public marketing hot-topics API backend.

API: https://60s.viki.moe/v2 (开源, MIT)
"""

import json
import httpx
from .base import ScrapingBackend

API_BASE = "https://60s.viki.moe/v2"
PLATFORM_MAP = {"weibo": "weibo", "douyin": "douyin", "zhihu": "zhihu", "baidu": "baidu", "toutiao": "toutiao"}


def _http_get(url: str, timeout: int = 8) -> str:
    response = httpx.get(url, timeout=timeout, headers={"User-Agent": "marketing-os/0.2"})
    response.raise_for_status()
    return response.text


class HotTopicsApiBackend(ScrapingBackend):
    name = "hot_topics_api"
    priority = 80
    platforms = ["weibo", "douyin", "zhihu", "baidu", "toutiao"]

    def available(self) -> bool:
        # Availability is resolved by the real fetch. A separate network probe
        # doubles latency and can turn one flaky source into a page-wide stall.
        return True

    def fetch_trending(self, platform: str, count: int = 30) -> list[dict]:
        api_platform = PLATFORM_MAP.get(platform, platform)
        url = f"{API_BASE}/{api_platform}"
        raw = _http_get(url)
        data = json.loads(raw)
        items = self._extract(data)
        return items[:count]

    def _extract(self, data) -> list[dict]:
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("data", data.get("list", data.get("items", [])))
        else:
            return []
        results = []
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                continue
            results.append({
                "rank": i + 1,
                "title": it.get("title", it.get("word", it.get("name", ""))),
                "heat_value": it.get("heat", it.get("hot", it.get("num", ""))),
                "url": it.get("url", ""),
            })
        return results
