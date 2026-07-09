"""Auditable stock-image search providers.

Pexels is the first provider.  The normalized contract deliberately keeps
attribution and source-page evidence so a downloaded image never becomes an
untraceable local file.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class StockImageError(RuntimeError):
    pass


@dataclass(frozen=True)
class PexelsProvider:
    api_key: str
    endpoint: str = "https://api.pexels.com/v1/search"

    @classmethod
    def from_environment(cls) -> "PexelsProvider":
        return cls(os.environ.get("PEXELS_API_KEY", "").strip())

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, *, limit: int = 12, orientation: str = "portrait") -> dict:
        query = str(query or "").strip()
        if not query or len(query) > 100:
            raise ValueError("query required and must be <= 100 characters")
        if not self.configured:
            raise StockImageError("PEXELS_API_KEY is not configured")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 30:
            raise ValueError("limit must be between 1 and 30")
        if orientation not in {"portrait", "landscape", "square"}:
            raise ValueError("invalid orientation")
        url = f"{self.endpoint}?{urlencode({'query': query, 'per_page': limit, 'orientation': orientation, 'locale': 'zh-CN'})}"
        request = Request(url, headers={"Authorization": self.api_key, "User-Agent": "MarketingOS/0.1"})
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
                remaining = response.headers.get("X-Ratelimit-Remaining")
                reset = response.headers.get("X-Ratelimit-Reset")
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise StockImageError("Pexels API key was rejected") from exc
            if exc.code == 429:
                raise StockImageError("Pexels rate limit exceeded") from exc
            raise StockImageError(f"Pexels request failed with HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise StockImageError(f"Pexels request failed: {type(exc).__name__}") from exc

        candidates = []
        for photo in payload.get("photos", []):
            if not isinstance(photo, dict):
                continue
            src = photo.get("src") if isinstance(photo.get("src"), dict) else {}
            download_url = str(src.get("portrait") or src.get("large2x") or src.get("original") or "")
            source_url = str(photo.get("url") or "")
            if not download_url.startswith("https://images.pexels.com/") or not source_url.startswith("https://www.pexels.com/"):
                continue
            candidates.append({
                "provider": "pexels", "provider_id": str(photo.get("id") or ""),
                "preview_url": str(src.get("medium") or download_url),
                "download_url": download_url, "source_url": source_url,
                "author": str(photo.get("photographer") or "Unknown"),
                "author_url": str(photo.get("photographer_url") or ""),
                "alt": str(photo.get("alt") or ""),
                "width": int(photo.get("width") or 0), "height": int(photo.get("height") or 0),
                "license": "Pexels License", "attribution_required_in_search": True,
            })
        return {
            "provider": "pexels", "query": query, "orientation": orientation,
            "candidates": candidates, "total": int(payload.get("total_results") or 0),
            "rate_limit_remaining": int(remaining) if remaining and remaining.isdigit() else None,
            "rate_limit_reset": int(reset) if reset and reset.isdigit() else None,
            "attribution": "Photos provided by Pexels",
            "provider_url": "https://www.pexels.com",
        }
