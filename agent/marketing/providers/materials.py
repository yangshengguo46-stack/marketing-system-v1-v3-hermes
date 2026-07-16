"""Provider seam for licensed stock media discovery and download."""

from __future__ import annotations

import json
import os
import threading
import urllib.parse
import urllib.request
from typing import Any, Protocol


PEXELS_API_BASE = "https://api.pexels.com/v1"
PEXELS_LICENSE_URL = "https://www.pexels.com/license/"
MAX_PROVIDER_DOWNLOAD_BYTES = 200 * 1024 * 1024


class MaterialProvider(Protocol):
    name: str

    def search(self, request: dict[str, Any]) -> list[dict[str, Any]]: ...

    def download(self, candidate: dict[str, Any]) -> tuple[bytes, str, str]: ...


_PROVIDERS: dict[str, MaterialProvider] = {}
_LOCK = threading.RLock()


def register_material_provider(provider: MaterialProvider) -> None:
    name = str(getattr(provider, "name", "") or "").strip()
    if not name:
        raise ValueError("material provider requires a stable name")
    if not callable(getattr(provider, "search", None)) or not callable(
        getattr(provider, "download", None)
    ):
        raise TypeError("material provider must implement search() and download()")
    with _LOCK:
        _PROVIDERS[name] = provider


def get_material_provider(name: str) -> MaterialProvider:
    with _LOCK:
        provider = _PROVIDERS.get(str(name or "").strip())
    if provider is None:
        raise KeyError(f"material provider is unavailable: {name}")
    return provider


def list_material_providers() -> list[MaterialProvider]:
    with _LOCK:
        return list(_PROVIDERS.values())


def clear_material_providers() -> None:
    with _LOCK:
        _PROVIDERS.clear()


def ensure_default_material_providers() -> None:
    """Register configured first-party integrations without exposing secrets."""

    api_key = str(os.environ.get("PEXELS_API_KEY") or "").strip()
    if not api_key:
        return
    with _LOCK:
        if "pexels" not in _PROVIDERS:
            _PROVIDERS["pexels"] = PexelsMaterialProvider(api_key=api_key)


class PexelsMaterialProvider:
    """Official Pexels video API adapter; durable state remains in Hermes."""

    name = "pexels"
    _download_hosts = {"videos.pexels.com"}

    def __init__(self, *, api_key: str, timeout: float = 30.0) -> None:
        key = str(api_key or "").strip()
        if not key:
            raise ValueError("Pexels API key is required")
        self._api_key = key
        self._timeout = timeout

    def search(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        query = str(request.get("query") or "").strip()
        if not query:
            raise ValueError("material search query is required")
        orientation = str(request.get("orientation") or "").strip().lower()
        if orientation not in {"", "landscape", "portrait", "square"}:
            raise ValueError("unsupported Pexels orientation")
        per_page = max(1, min(int(request.get("limit") or 12), 40))
        params = {
            "query": query,
            "per_page": per_page,
            "locale": str(request.get("locale") or "zh-CN"),
        }
        if orientation:
            params["orientation"] = orientation
        url = f"{PEXELS_API_BASE}/videos/search?{urllib.parse.urlencode(params)}"
        payload = self._json_request(url)
        results = []
        for video in payload.get("videos") or []:
            candidate = self._candidate(video)
            if candidate:
                results.append(candidate)
        return results

    def download(self, candidate: dict[str, Any]) -> tuple[bytes, str, str]:
        url = str(candidate.get("download_url") or "").strip()
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in self._download_hosts:
            raise ValueError("Pexels download URL is not trusted")
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "MarketingOS/1.0", "Accept": "video/mp4"},
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            content_type = str(response.headers.get_content_type() or "").lower()
            if content_type != "video/mp4":
                raise ValueError("Pexels material response is not an MP4 video")
            content_length = int(response.headers.get("Content-Length") or 0)
            if content_length > MAX_PROVIDER_DOWNLOAD_BYTES:
                raise ValueError("Pexels material exceeds the 200 MB product limit")
            payload = response.read(MAX_PROVIDER_DOWNLOAD_BYTES + 1)
        if not payload or len(payload) > MAX_PROVIDER_DOWNLOAD_BYTES:
            raise ValueError("Pexels material is empty or exceeds the product limit")
        filename = f"pexels-{candidate['provider_asset_id']}.mp4"
        return payload, filename, "video/mp4"

    def _json_request(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": self._api_key,
                "User-Agent": "MarketingOS/1.0",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            payload = response.read(4 * 1024 * 1024 + 1)
        if len(payload) > 4 * 1024 * 1024:
            raise ValueError("Pexels response exceeds the product limit")
        value = json.loads(payload.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Pexels returned an invalid response")
        return value

    @staticmethod
    def _candidate(video: dict[str, Any]) -> dict[str, Any] | None:
        files = [
            item
            for item in (video.get("video_files") or [])
            if item.get("file_type") == "video/mp4"
            and str(item.get("link") or "").startswith("https://videos.pexels.com/")
        ]
        if not files:
            return None
        # Prefer a useful HD source without pulling a needlessly large 4K file.
        files.sort(
            key=lambda item: (
                abs(max(int(item.get("width") or 0), int(item.get("height") or 0)) - 1920),
                -int(item.get("width") or 0) * int(item.get("height") or 0),
            )
        )
        selected = files[0]
        provider_id = str(video.get("id") or "").strip()
        source_url = str(video.get("url") or "").strip()
        if not provider_id or not source_url.startswith("https://www.pexels.com/"):
            return None
        user = video.get("user") or {}
        pictures = video.get("video_pictures") or []
        return {
            "provider": "pexels",
            "provider_asset_id": provider_id,
            "media_type": "video",
            "source_url": source_url,
            "preview_url": str((pictures[0] if pictures else {}).get("picture") or ""),
            "download_url": selected["link"],
            "creator": str(user.get("name") or ""),
            "creator_url": str(user.get("url") or ""),
            "license_name": "Pexels License",
            "license_url": PEXELS_LICENSE_URL,
            "provider_home_url": "https://www.pexels.com/",
            "width": int(selected.get("width") or video.get("width") or 0),
            "height": int(selected.get("height") or video.get("height") or 0),
            "duration": float(video.get("duration") or 0),
            "metadata": {
                "api_width": int(video.get("width") or 0),
                "api_height": int(video.get("height") or 0),
                "selected_quality": str(selected.get("quality") or ""),
            },
        }
