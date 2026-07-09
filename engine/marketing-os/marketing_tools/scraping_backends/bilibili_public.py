"""Cookie-free Bilibili popular and keyword-video source."""

import re
from datetime import datetime, timezone
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
            owner = item.get("owner") or {}
            owner_id = str(owner.get("mid") or "")
            results.append({
                "rank": index + 1,
                "title": str(item.get("title") or "").strip(),
                "heat_value": stat.get("view", ""),
                "url": f"https://www.bilibili.com/video/{bvid}" if bvid else "",
                "video_id": bvid or None,
                "metrics": {
                    "views": stat.get("view"), "likes": stat.get("like"),
                    "comments": stat.get("reply"), "shares": stat.get("share"),
                },
                "author": {
                    "id": owner_id,
                    "name": str(owner.get("name") or "").strip(),
                    "profile_url": f"https://space.bilibili.com/{owner_id}" if owner_id else "",
                },
            })
        return [item for item in results if item["title"]][:count]

    def search_content(self, keyword: str, count: int = 30) -> list[dict]:
        """Search public video results while preserving stable creator identity."""
        keyword = str(keyword or "").strip()
        if not keyword or len(keyword) > 100:
            raise ValueError("keyword is required and must be <= 100 characters")
        response = httpx.get(
            "https://api.bilibili.com/x/web-interface/search/type",
            params={"search_type": "video", "keyword": keyword, "page": 1},
            timeout=8,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.bilibili.com/",
                "Accept": "application/json, text/plain, */*",
            },
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(payload.get("message") or "Bilibili search API error")
        captured_at = datetime.now(timezone.utc).isoformat()
        results = []
        for index, item in enumerate((payload.get("data") or {}).get("result") or []):
            owner_id = str(item.get("mid") or "")
            bvid = str(item.get("bvid") or "")
            title = re.sub(r"<[^>]+>", "", str(item.get("title") or "")).strip()
            if not owner_id or not title:
                continue
            results.append({
                "rank": index + 1, "title": title[:200], "video_id": bvid or None,
                "heat_value": item.get("play"),
                "url": f"https://www.bilibili.com/video/{bvid}" if bvid else
                       str(item.get("arcurl") or "").replace("http://", "https://", 1),
                "collected_at": captured_at,
                "source_platform": "bilibili", "source_backend": self.name,
                "metrics": {
                    "views": item.get("play"), "likes": item.get("like"),
                    "comments": item.get("video_review"), "favorites": item.get("favorites"),
                },
                "author": {
                    "id": owner_id, "name": str(item.get("author") or owner_id).strip(),
                    "profile_url": f"https://space.bilibili.com/{owner_id}",
                },
            })
            if len(results) >= min(max(int(count), 1), 50):
                break
        return results
