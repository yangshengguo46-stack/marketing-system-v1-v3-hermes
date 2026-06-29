"""Agent-Reach 后端 — pip install agent-reach

22K+ GitHub stars, 16+ 平台覆盖
用 Chrome CDP 复用已登录浏览器，绕过反爬
"""

import json
from .base import ScrapingBackend


class AgentReachBackend(ScrapingBackend):
    name = "agent_reach"
    priority = 90
    platforms = ["douyin", "weibo", "bilibili", "xiaohongshu", "zhihu", "kuaishou"]

    def available(self) -> bool:
        try:
            import agent_reach
            return True
        except ImportError:
            return False

    def fetch_trending(self, platform: str, count: int = 30) -> list[dict]:
        import agent_reach

        try:
            result = agent_reach.search(
                platform=platform,
                mode="hot",
                limit=count,
            )

            if isinstance(result, str):
                result = json.loads(result)
            if isinstance(result, dict):
                items = result.get("data", result.get("list", result.get("items", [])))
            elif isinstance(result, list):
                items = result
            else:
                return []

            return [{
                "rank": i + 1,
                "title": it.get("title", it.get("word", "")),
                "heat_value": it.get("heat", it.get("hot_value", "")),
                "url": it.get("url", it.get("share_url", "")),
            } for i, it in enumerate(items) if isinstance(it, dict)]

        except Exception as e:
            raise RuntimeError(f"Agent-Reach 抓取失败 ({platform}): {e}")
