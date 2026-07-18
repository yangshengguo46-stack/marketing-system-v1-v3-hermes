"""Provider seam for licensed stock media discovery and download."""

from __future__ import annotations

import html
import json
import os
import re
import threading
import urllib.parse
import urllib.request
from typing import Any, Protocol


PEXELS_API_BASE = "https://api.pexels.com/v1"
PEXELS_LICENSE_URL = "https://www.pexels.com/license/"
WIKIMEDIA_COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIMEDIA_COMMONS_HOME = "https://commons.wikimedia.org/"
MAX_PROVIDER_DOWNLOAD_BYTES = 200 * 1024 * 1024
_HTML_TAG = re.compile(r"<[^>]+>")


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
    if api_key:
        with _LOCK:
            if "pexels" not in _PROVIDERS:
                _PROVIDERS["pexels"] = PexelsMaterialProvider(api_key=api_key)
    commons_enabled = str(
        os.environ.get("MARKETING_WIKIMEDIA_MATERIALS", "1")
    ).strip().lower() not in {"0", "false", "no", "off"}
    if commons_enabled:
        with _LOCK:
            if "wikimedia_commons" not in _PROVIDERS:
                _PROVIDERS["wikimedia_commons"] = WikimediaCommonsMaterialProvider()


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
        if str(request.get("media_type") or "either") == "image":
            return []
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


class WikimediaCommonsMaterialProvider:
    """No-key licensed image/video search through the official Commons API."""

    name = "wikimedia_commons"
    _download_hosts = {"upload.wikimedia.org"}
    _video_mimes = {"video/mp4", "video/webm", "video/ogg"}
    _image_mimes = {"image/jpeg", "image/png", "image/webp"}
    _media_mimes = _video_mimes | _image_mimes

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._timeout = timeout

    def search(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        query = str(request.get("query") or "").strip()
        if not query:
            raise ValueError("material search query is required")
        limit = max(1, min(int(request.get("limit") or 12), 20))
        requested_type = str(request.get("media_type") or "either").strip().lower()
        if requested_type not in {"either", "image", "video"}:
            raise ValueError("unsupported Wikimedia Commons media type")
        if requested_type == "either":
            video_limit = max(1, limit // 2)
            image_limit = max(1, limit - video_limit)
            results = self._search_type(query, "video", video_limit)
            results.extend(self._search_type(query, "image", image_limit))
            return results[:limit]
        return self._search_type(query, requested_type, limit)

    def _search_type(
        self, query: str, media_type: str, limit: int
    ) -> list[dict[str, Any]]:
        filetype = "video" if media_type == "video" else "bitmap"
        params = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "generator": "search",
            "gsrsearch": f"{query} filetype:{filetype}",
            "gsrnamespace": "6",
            "gsrlimit": str(limit),
            "prop": "imageinfo",
            "iiprop": "url|mime|size|sha1|extmetadata",
            "iiextmetadatafilter": (
                "LicenseShortName|LicenseUrl|Artist|Credit|UsageTerms"
            ),
            "iiextmetadatalanguage": "en",
        }
        payload = self._json_request(
            f"{WIKIMEDIA_COMMONS_API}?{urllib.parse.urlencode(params)}"
        )
        pages = (payload.get("query") or {}).get("pages") or []
        if isinstance(pages, dict):
            pages = list(pages.values())
        results = []
        for page in pages:
            candidate = self._candidate(page)
            if candidate is not None:
                results.append(candidate)
        return results

    def download(self, candidate: dict[str, Any]) -> tuple[bytes, str, str]:
        url = str(candidate.get("download_url") or "").strip()
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in self._download_hosts:
            raise ValueError("Wikimedia Commons download URL is not trusted")
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "MarketingOS/1.0 (licensed-media-resolver)",
                "Accept": "video/mp4,video/webm,video/ogg,image/jpeg,image/png,image/webp",
            },
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            content_type = str(response.headers.get_content_type() or "").lower()
            if content_type not in self._media_mimes:
                raise ValueError("Wikimedia Commons material is not a supported image or video")
            content_length = int(response.headers.get("Content-Length") or 0)
            if content_length > MAX_PROVIDER_DOWNLOAD_BYTES:
                raise ValueError("Wikimedia Commons material exceeds the 200 MB product limit")
            payload = response.read(MAX_PROVIDER_DOWNLOAD_BYTES + 1)
        if not payload or len(payload) > MAX_PROVIDER_DOWNLOAD_BYTES:
            raise ValueError("Wikimedia Commons material is empty or exceeds the product limit")
        extension = {
            "video/mp4": "mp4",
            "video/webm": "webm",
            "video/ogg": "ogv",
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
        }[content_type]
        provider_id = re.sub(
            r"[^a-zA-Z0-9._-]+", "-", str(candidate["provider_asset_id"])
        )[:120]
        return payload, f"commons-{provider_id}.{extension}", content_type

    def _json_request(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "MarketingOS/1.0 (licensed-media-resolver)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            payload = response.read(8 * 1024 * 1024 + 1)
        if len(payload) > 8 * 1024 * 1024:
            raise ValueError("Wikimedia Commons response exceeds the product limit")
        value = json.loads(payload.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Wikimedia Commons returned an invalid response")
        return value

    def _candidate(self, page: dict[str, Any]) -> dict[str, Any] | None:
        info = ((page.get("imageinfo") or [{}])[0])
        mime_type = str(info.get("mime") or "").lower()
        if mime_type not in self._media_mimes:
            return None
        size_bytes = int(info.get("size") or 0)
        if size_bytes <= 0 or size_bytes > MAX_PROVIDER_DOWNLOAD_BYTES:
            return None
        download_url = str(info.get("url") or "").strip()
        parsed_download = urllib.parse.urlparse(download_url)
        source_url = str(info.get("descriptionurl") or "").strip()
        if (
            parsed_download.scheme != "https"
            or parsed_download.hostname not in self._download_hosts
            or not source_url.startswith(WIKIMEDIA_COMMONS_HOME)
        ):
            return None
        metadata = info.get("extmetadata") or {}
        license_name = _metadata_text(metadata, "LicenseShortName")
        license_url = _metadata_text(metadata, "LicenseUrl")
        if not license_name or not license_url.startswith("http"):
            return None
        provider_id = str(page.get("pageid") or info.get("sha1") or page.get("title") or "")
        if not provider_id:
            return None
        creator = _metadata_text(metadata, "Artist") or "Wikimedia Commons contributor"
        media_type = "video" if mime_type in self._video_mimes else "image"
        return {
            "provider": self.name,
            "provider_asset_id": provider_id,
            "media_type": media_type,
            "source_url": source_url,
            "preview_url": "",
            "download_url": download_url,
            "creator": creator[:500],
            "creator_url": source_url,
            "license_name": license_name[:200],
            "license_url": license_url[:2048],
            "provider_home_url": WIKIMEDIA_COMMONS_HOME,
            "width": int(info.get("width") or 0),
            "height": int(info.get("height") or 0),
            "duration": 0,
            "metadata": {
                "title": str(page.get("title") or ""),
                "mime_type": mime_type,
                "sha1": str(info.get("sha1") or ""),
                "size_bytes": size_bytes,
                "credit": _metadata_text(metadata, "Credit")[:1000],
                "usage_terms": _metadata_text(metadata, "UsageTerms")[:500],
            },
        }


def _metadata_text(metadata: dict[str, Any], key: str) -> str:
    item = metadata.get(key) if isinstance(metadata, dict) else None
    raw = item.get("value") if isinstance(item, dict) else item
    return " ".join(html.unescape(_HTML_TAG.sub(" ", str(raw or ""))).split())
