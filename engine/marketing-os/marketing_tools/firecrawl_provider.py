"""Firecrawl-compatible web research provider (cloud or loopback self-hosted)."""

from __future__ import annotations

import json
import os
from ipaddress import ip_address
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class FirecrawlError(RuntimeError):
    pass


def _base_url(value: str) -> str:
    value = str(value or "https://api.firecrawl.dev").strip().rstrip("/")
    parsed = urlparse(value)
    if value == "https://api.firecrawl.dev":
        return value
    if parsed.scheme != "http" or parsed.port not in {3002, 3003}:
        raise ValueError("self-hosted Firecrawl must use loopback HTTP port 3002 or 3003")
    try:
        if not ip_address(parsed.hostname or "").is_loopback:
            raise ValueError("self-hosted Firecrawl must use a loopback address")
    except ValueError as exc:
        raise ValueError("self-hosted Firecrawl must use a loopback IP address") from exc
    return value


class FirecrawlProvider:
    def __init__(self, *, api_url: str | None = None, api_key: str | None = None):
        self.api_url = _base_url(api_url or os.environ.get("FIRECRAWL_API_URL", ""))
        self.api_key = str(api_key if api_key is not None else os.environ.get("FIRECRAWL_API_KEY", "")).strip()

    @property
    def mode(self) -> str:
        return "cloud" if self.api_url == "https://api.firecrawl.dev" else "self_hosted"

    @property
    def configured(self) -> bool:
        return self.mode == "self_hosted" or bool(self.api_key)

    def _post(self, path: str, body: dict) -> dict:
        if not self.configured:
            raise FirecrawlError("Firecrawl is not configured; add a free cloud key or start localhost self-hosting")
        headers = {"Content-Type": "application/json", "User-Agent": "MarketingOS/0.1"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(
            f"{self.api_url}{path}", data=json.dumps(body).encode("utf-8"),
            headers=headers, method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise FirecrawlError("Firecrawl API key was rejected") from exc
            if exc.code == 429:
                raise FirecrawlError("Firecrawl free quota or rate limit was exceeded") from exc
            raise FirecrawlError(f"Firecrawl request failed with HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise FirecrawlError(f"Firecrawl request failed: {type(exc).__name__}") from exc
        if payload.get("success") is False:
            raise FirecrawlError(str(payload.get("error") or "Firecrawl returned failure")[:300])
        return payload

    def search(self, query: str, *, limit: int = 8) -> dict:
        query = str(query or "").strip()
        if not query or len(query) > 200:
            raise ValueError("query required and must be <= 200 characters")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")
        payload = self._post("/v2/search", {
            "query": query, "limit": limit, "sources": [{"type": "web"}],
            "scrapeOptions": {"formats": ["markdown"], "onlyMainContent": True},
        })
        raw = payload.get("data", [])
        if isinstance(raw, dict):
            raw = raw.get("web", raw.get("results", []))
        results = []
        for item in raw if isinstance(raw, list) else []:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or item.get("metadata", {}).get("sourceURL") or "")
            if not url.startswith(("https://", "http://")):
                continue
            results.append({
                "title": str(item.get("title") or item.get("metadata", {}).get("title") or "")[:300],
                "url": url, "description": str(item.get("description") or "")[:1000],
                "markdown": str(item.get("markdown") or "")[:20_000],
            })
        return {"provider": "firecrawl", "mode": self.mode, "query": query, "results": results[:limit]}


def search_for_agent(params: dict) -> dict:
    return FirecrawlProvider().search(
        str(params.get("query") or ""), limit=int(params.get("limit", 8)),
    )
