"""Cookie-free Bilibili popular-video source."""

import httpx

from .base import ScrapingBackend


class BilibiliPublicBackend(ScrapingBackend):
    name = "bilibili_public"
    priority = 100
    platforms = ["bilibili"]

    def available(self) -> bool:
        return True

    def fetch_trending(self, platform: str, count: int = 30) -> list[dict]:
        response = httpx.get(
            "https://api.bilibili.com/x/web-interface/popular",
            params={"pn": 1, "ps": min(max(count, 1), 50)},
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0 marketing-os/0.2"},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(payload.get("message") or "Bilibili API error")
        results = []
        for index, item in enumerate((payload.get("data") or {}).get("list") or []):
            bvid = str(item.get("bvid") or "")
            stat = item.get("stat") or {}
            results.append({
                "rank": index + 1,
                "title": str(item.get("title") or "").strip(),
                "heat_value": stat.get("view", ""),
                "url": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
            })
        return [item for item in results if item["title"]][:count]
