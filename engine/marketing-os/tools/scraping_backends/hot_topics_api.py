"""Hot Topics API 后端 — curl 实现，兼容所有代理

API: https://60s.viki.moe/v2 (开源, MIT)
"""

import json
import subprocess
from .base import ScrapingBackend

API_BASE = "https://60s.viki.moe/v2"
PLATFORM_MAP = {"weibo": "weibo", "douyin": "douyin", "zhihu": "zhihu", "baidu": "baidu", "toutiao": "toutiao"}


def _curl_get(url: str, timeout: int = 15) -> str:
    """用 curl 发 GET 请求，比 urllib 更稳"""
    result = subprocess.run(
        ["curl", "-s", "--max-time", str(timeout), "-H", "User-Agent: marketing-os/0.2", url],
        capture_output=True, text=True, timeout=timeout + 5,
    )
    if result.returncode != 0:
        raise RuntimeError(f"curl 失败 ({result.returncode}): {result.stderr[:200]}")
    return result.stdout


class HotTopicsApiBackend(ScrapingBackend):
    name = "hot_topics_api"
    priority = 80
    platforms = ["weibo", "douyin", "zhihu", "baidu", "toutiao"]

    def available(self) -> bool:
        try:
            out = _curl_get(f"{API_BASE}/weibo", timeout=10)
            data = json.loads(out)
            return isinstance(data, (list, dict))
        except Exception:
            return False

    def fetch_trending(self, platform: str, count: int = 30) -> list[dict]:
        api_platform = PLATFORM_MAP.get(platform, platform)
        url = f"{API_BASE}/{api_platform}"
        raw = _curl_get(url)
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
