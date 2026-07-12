"""Hermes-owned client for the central anonymous knowledge service."""

from __future__ import annotations

import base64
import json
import threading
import time
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx

from agent.marketing.domains.knowledge_flywheel import KnowledgeFlywheelRepository
from agent.secret_scope import get_secret


class KnowledgeSyncClient:
    """Upload governed outbox rows and install only signed aggregate priors."""

    name = "marketing-central-knowledge-v1"

    def __init__(
        self,
        *,
        base_url: str,
        client_id: str,
        token: str,
        public_keys: dict[str, bytes | Any],
        repository: KnowledgeFlywheelRepository | None = None,
        http_client: Any | None = None,
        timeout_seconds: float = 15.0,
    ):
        self.base_url = _validate_base_url(base_url)
        self.client_id = str(client_id or "").strip()
        self._token = str(token or "")
        if not self.client_id or len(self._token) < 32:
            raise ValueError("knowledge sync requires an installation client and token")
        if not public_keys:
            raise ValueError("knowledge sync requires at least one trusted signing key")
        self.public_keys = dict(public_keys)
        self.repository = repository or KnowledgeFlywheelRepository()
        self._owns_http = http_client is None
        self.http = http_client or httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
        )

    def close(self) -> None:
        if self._owns_http:
            self.http.close()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "X-Marketing-Client": self.client_id,
            "X-Marketing-Request-Id": f"req_{uuid.uuid4().hex}",
            "X-Marketing-Timestamp": str(time.time()),
        }

    def sync_once(self, *, upload_limit: int = 100) -> dict[str, Any]:
        uploaded: list[str] = []
        upload_errors: list[dict[str, str]] = []
        for contribution in self.repository.list_contributions(
            statuses=("pending",), limit=upload_limit
        ):
            contribution_id = str(contribution["id"])
            try:
                response = self.http.post(
                    "/v1/contributions",
                    headers=self._headers(),
                    json=self.repository.export_contribution(contribution_id),
                )
                response.raise_for_status()
                self.repository.update_contribution_status(contribution_id, "submitted")
                uploaded.append(contribution_id)
            except Exception as exc:
                upload_errors.append(
                    {"contribution_ref": contribution_id, "error": type(exc).__name__}
                )

        installed: list[str] = []
        pack_errors: list[dict[str, str]] = []
        try:
            response = self.http.get("/v1/packs", headers=self._headers())
            response.raise_for_status()
            payload = response.json()
            packs = payload.get("packs") if isinstance(payload, dict) else None
            if not isinstance(packs, list):
                raise ValueError("central knowledge pack response is invalid")
            for pack in packs:
                try:
                    result = self.repository.install_knowledge_pack(
                        pack,
                        public_keys=self.public_keys,
                    )
                    installed.append(str(result["id"]))
                except Exception as exc:
                    pack_id = str(pack.get("id") or "") if isinstance(pack, dict) else ""
                    pack_errors.append({"pack_id": pack_id, "error": type(exc).__name__})
        except Exception as exc:
            pack_errors.append({"pack_id": "", "error": type(exc).__name__})

        return {
            "uploaded": uploaded,
            "installed": installed,
            "upload_errors": upload_errors,
            "pack_errors": pack_errors,
        }


def _validate_base_url(value: str) -> str:
    url = str(value or "").strip().rstrip("/")
    parsed = urlparse(url)
    if (
        parsed.scheme == "https"
        and parsed.netloc
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
        and parsed.path in {"", "/"}
    ):
        return url
    if (
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
        and parsed.path in {"", "/"}
    ):
        return url
    raise ValueError("knowledge service URL must use HTTPS except on loopback")


def _public_keys_from_json(value: str) -> dict[str, bytes]:
    try:
        payload = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("knowledge signing key ring must be valid JSON") from exc
    if not isinstance(payload, dict) or not payload:
        raise ValueError("knowledge signing key ring must be a non-empty object")
    result: dict[str, bytes] = {}
    for key_id, encoded in payload.items():
        name = str(key_id or "").strip()
        try:
            raw = base64.b64decode(str(encoded or ""), validate=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("knowledge signing key ring contains invalid base64") from exc
        if not name or len(raw) != 32:
            raise ValueError("knowledge signing keys must be 32-byte Ed25519 public keys")
        result[name] = raw
    return result


def from_environment() -> KnowledgeSyncClient | None:
    url = str(get_secret("MARKETING_KNOWLEDGE_URL", "") or "").strip()
    client_id = str(get_secret("MARKETING_KNOWLEDGE_CLIENT_ID", "") or "").strip()
    token = str(get_secret("MARKETING_KNOWLEDGE_CLIENT_TOKEN", "") or "").strip()
    key_ring = str(get_secret("MARKETING_KNOWLEDGE_PUBLIC_KEYS_JSON", "") or "").strip()
    if not any((url, client_id, token, key_ring)):
        return None
    if not all((url, client_id, token, key_ring)):
        raise ValueError("knowledge sync environment is incomplete")
    return KnowledgeSyncClient(
        base_url=url,
        client_id=client_id,
        token=token,
        public_keys=_public_keys_from_json(key_ring),
    )


_LOCK = threading.RLock()
_PROVIDER: KnowledgeSyncClient | None = None
_ENV_CHECKED = False


def register_knowledge_sync_provider(provider: KnowledgeSyncClient) -> None:
    if not callable(getattr(provider, "sync_once", None)):
        raise TypeError("knowledge sync provider must implement sync_once()")
    global _PROVIDER, _ENV_CHECKED
    with _LOCK:
        if _PROVIDER is not None and _PROVIDER is not provider:
            _PROVIDER.close()
        _PROVIDER = provider
        _ENV_CHECKED = True


def get_knowledge_sync_provider() -> KnowledgeSyncClient:
    global _PROVIDER, _ENV_CHECKED
    with _LOCK:
        if not _ENV_CHECKED:
            _PROVIDER = from_environment()
            _ENV_CHECKED = True
        if _PROVIDER is None:
            raise KeyError("central knowledge sync provider is unavailable")
        return _PROVIDER


def has_knowledge_sync_provider() -> bool:
    try:
        get_knowledge_sync_provider()
    except KeyError:
        return False
    return True


def clear_knowledge_sync_provider() -> None:
    global _PROVIDER, _ENV_CHECKED
    with _LOCK:
        if _PROVIDER is not None:
            _PROVIDER.close()
        _PROVIDER = None
        _ENV_CHECKED = False


def run_knowledge_sync() -> dict[str, Any]:
    return get_knowledge_sync_provider().sync_once()
