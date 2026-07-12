from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from marketing_knowledge_protocol import CONTRIBUTION_PROTOCOL
from services.marketing_knowledge import CentralKnowledgeStore, create_app


TOKEN_A = "client-a-token-" + "a" * 32
TOKEN_B = "client-b-token-" + "b" * 32
DELETION_KEY = b"central-deletion-key-" + b"z" * 32
NEXT_DELETION_KEY = b"central-deletion-key-" + b"y" * 32


def _contribution(reference: str = "contrib_api0001") -> dict:
    return {
        "protocol": CONTRIBUTION_PROTOCOL,
        "contribution_ref": reference,
        "schema_version": "knowledge.v1",
        "cohort": {
            "platform": "douyin",
            "region": "cn",
            "knowledge_type": "content_prior",
        },
        "features": {"hook_type": "contrarian"},
        "outcomes": {"completion_rate": 0.42},
        "observed_at": datetime(2026, 7, 12, tzinfo=timezone.utc).isoformat(),
    }


def _headers(
    request_id: str,
    *,
    client_id: str = "desktop-install-a",
    token: str = TOKEN_A,
    timestamp: float | None = None,
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Marketing-Client": client_id,
        "X-Marketing-Request-Id": request_id,
        "X-Marketing-Timestamp": str(timestamp if timestamp is not None else time.time()),
    }


def _runtime(tmp_path, *, limit: int = 60):
    store = CentralKnowledgeStore(tmp_path / "central.db")
    store.provision_client("desktop-install-a", TOKEN_A, requests_per_minute=limit)
    return store, TestClient(
        create_app(
            store,
            deletion_keys={"delete-2026-01": DELETION_KEY},
            active_deletion_key_id="delete-2026-01",
        )
    )


def test_http_ingest_authenticates_and_rejects_nonce_replay(tmp_path):
    store, client = _runtime(tmp_path)

    response = client.post(
        "/v1/contributions",
        headers=_headers("req_upload_api0001"),
        json=_contribution(),
    )
    replay = client.post(
        "/v1/contributions",
        headers=_headers("req_upload_api0001"),
        json=_contribution(),
    )

    assert response.status_code == 200
    assert response.json()["operation"] == "ingested"
    assert replay.status_code == 409
    assert len(store.list_contributions()) == 1


def test_http_rejects_bad_stale_and_rotated_credentials(tmp_path):
    store, client = _runtime(tmp_path)
    bad = client.get(
        "/v1/packs",
        headers=_headers("req_bad_token0001", token="wrong-" + "x" * 32),
    )
    stale = client.get(
        "/v1/packs",
        headers=_headers("req_stale_time001", timestamp=time.time() - 601),
    )

    store.rotate_client_token("desktop-install-a", TOKEN_B)
    old = client.get("/v1/packs", headers=_headers("req_old_token0001"))
    new = client.get(
        "/v1/packs",
        headers=_headers("req_new_token0001", token=TOKEN_B),
    )
    store.revoke_client("desktop-install-a")
    revoked = client.get(
        "/v1/packs",
        headers=_headers("req_revoked_tok01", token=TOKEN_B),
    )

    assert bad.status_code == 401
    assert stale.status_code == 401
    assert old.status_code == 401
    assert new.status_code == 200
    assert revoked.status_code == 401


def test_only_original_authenticated_client_can_delete_contribution(tmp_path):
    store, client = _runtime(tmp_path)
    store.provision_client("desktop-install-b", TOKEN_B)
    uploaded = client.post(
        "/v1/contributions",
        headers=_headers("req_owner_upload01"),
        json=_contribution(),
    )

    forbidden = client.request(
        "DELETE",
        "/v1/contributions/contrib_api0001",
        headers=_headers(
            "req_other_delete01",
            client_id="desktop-install-b",
            token=TOKEN_B,
        ),
        json={"deletion_ref": "delete_api0001"},
    )
    deleted = client.request(
        "DELETE",
        "/v1/contributions/contrib_api0001",
        headers=_headers("req_owner_delete01"),
        json={"deletion_ref": "delete_api0001"},
    )
    repeat_by_other = client.request(
        "DELETE",
        "/v1/contributions/contrib_api0001",
        headers=_headers(
            "req_other_repeat01",
            client_id="desktop-install-b",
            token=TOKEN_B,
        ),
        json={"deletion_ref": "delete_api0001"},
    )

    assert uploaded.status_code == 200
    assert forbidden.status_code == 403
    assert deleted.status_code == 200
    assert repeat_by_other.status_code == 403
    assert store.list_contributions() == []


def test_persistent_rate_limit_returns_retry_after(tmp_path):
    _store, client = _runtime(tmp_path, limit=1)
    first = client.get("/v1/packs", headers=_headers("req_rate_limit001"))
    limited = client.get("/v1/packs", headers=_headers("req_rate_limit002"))

    assert first.status_code == 200
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1


def test_deletion_owner_key_ring_allows_safe_rotation(tmp_path):
    store, old_app = _runtime(tmp_path)
    uploaded = old_app.post(
        "/v1/contributions",
        headers=_headers("req_before_rotate1"),
        json=_contribution(),
    )
    rotated_app = TestClient(
        create_app(
            store,
            deletion_keys={
                "delete-2026-01": DELETION_KEY,
                "delete-2026-02": NEXT_DELETION_KEY,
            },
            active_deletion_key_id="delete-2026-02",
        )
    )
    deleted = rotated_app.request(
        "DELETE",
        "/v1/contributions/contrib_api0001",
        headers=_headers("req_after_rotate01"),
        json={"deletion_ref": "delete_after_rotate"},
    )

    assert uploaded.status_code == 200
    assert deleted.status_code == 200
    assert store.list_contributions() == []
