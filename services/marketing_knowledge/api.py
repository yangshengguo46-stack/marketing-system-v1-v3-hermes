"""Authenticated HTTP owner for the central anonymous knowledge service."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from services.marketing_knowledge.storage import (
    CentralKnowledgeStore,
    ContributionAuthorizationError,
    ServiceAuthenticationError,
    ServiceRateLimitError,
    ServiceReplayError,
)


def _bearer_token(request: Request) -> str:
    value = str(request.headers.get("authorization") or "")
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ServiceAuthenticationError("missing service bearer credential")
    return token


def _deletion_owner(deletion_key: bytes, client_id: str, contribution_ref: str) -> str:
    return hmac.new(
        deletion_key,
        f"{client_id}\0{contribution_ref}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def _authorize(
    request: Request,
    store: CentralKnowledgeStore,
) -> tuple[dict[str, Any], bytes]:
    body = await request.body()
    try:
        timestamp = float(request.headers.get("x-marketing-timestamp") or "")
    except ValueError as exc:
        raise ServiceAuthenticationError("invalid service request timestamp") from exc
    auth = store.authorize_request(
        client_id=str(request.headers.get("x-marketing-client") or ""),
        token=_bearer_token(request),
        request_id=str(request.headers.get("x-marketing-request-id") or ""),
        request_sha256=hashlib.sha256(body).hexdigest(),
        timestamp=timestamp,
    )
    return auth, body


def create_app(
    store: CentralKnowledgeStore,
    *,
    deletion_keys: dict[str, bytes],
    active_deletion_key_id: str,
) -> FastAPI:
    """Build the service surface; provisioning remains an offline operation."""

    active_key_id = str(active_deletion_key_id or "").strip()
    if active_key_id not in deletion_keys:
        raise ValueError("active central deletion key is missing from the key ring")
    if not deletion_keys or any(
        not isinstance(key, bytes) or len(key) < 32 for key in deletion_keys.values()
    ):
        raise ValueError("every central deletion key must contain at least 32 bytes")
    app = FastAPI(title="Marketing OS Knowledge Service", version="1")

    def owner_proofs(client_id: str, contribution_ref: str) -> tuple[str, tuple[str, ...]]:
        active = _deletion_owner(
            deletion_keys[active_key_id], client_id, contribution_ref
        )
        accepted = tuple(
            _deletion_owner(key, client_id, contribution_ref)
            for key_id, key in deletion_keys.items()
            if key_id != active_key_id
        )
        return active, accepted

    @app.exception_handler(ServiceAuthenticationError)
    async def _authentication_error(_request: Request, exc: ServiceAuthenticationError):
        return JSONResponse(status_code=401, content={"error": str(exc)})

    @app.exception_handler(ServiceReplayError)
    async def _replay_error(_request: Request, exc: ServiceReplayError):
        return JSONResponse(status_code=409, content={"error": str(exc)})

    @app.exception_handler(ServiceRateLimitError)
    async def _rate_error(_request: Request, exc: ServiceRateLimitError):
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(exc.retry_after)},
            content={"error": str(exc)},
        )

    @app.exception_handler(ContributionAuthorizationError)
    async def _contribution_auth_error(
        _request: Request, exc: ContributionAuthorizationError
    ):
        return JSONResponse(status_code=403, content={"error": str(exc)})

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/contributions")
    async def ingest(request: Request):
        auth, body = await _authorize(request, store)
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError("contribution body must be an object")
            contribution_ref = str(payload.get("contribution_ref") or "")
            active_owner, accepted_owners = owner_proofs(
                str(auth["client_id"]), contribution_ref
            )
            result = store.ingest_contribution(
                payload,
                deletion_owner_sha256=active_owner,
                accepted_deletion_owner_sha256=accepted_owners,
            )
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="invalid JSON body") from exc
        except ContributionAuthorizationError:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result

    @app.delete("/v1/contributions/{contribution_ref}")
    async def delete(contribution_ref: str, request: Request):
        auth, body = await _authorize(request, store)
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError("deletion body must be an object")
            active_owner, accepted_owners = owner_proofs(
                str(auth["client_id"]), contribution_ref
            )
            result = store.delete_contribution(
                contribution_ref,
                deletion_ref=str(payload.get("deletion_ref") or ""),
                deletion_owner_sha256=active_owner,
                accepted_deletion_owner_sha256=accepted_owners,
            )
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="invalid JSON body") from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ContributionAuthorizationError:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result

    @app.get("/v1/packs")
    async def list_packs(request: Request):
        await _authorize(request, store)
        return {"packs": store.list_packs()}

    @app.get("/v1/packs/{pack_id}")
    async def get_pack(pack_id: str, request: Request):
        await _authorize(request, store)
        try:
            return store.get_pack(pack_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app
