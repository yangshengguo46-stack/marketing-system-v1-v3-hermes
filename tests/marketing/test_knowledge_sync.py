from __future__ import annotations

import base64
import sqlite3

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import KnowledgeFlywheelRepository
from agent.marketing.providers.knowledge_sync import KnowledgeSyncClient, from_environment
from agent.secret_scope import set_multiplex_active
from hermes_state import SessionDB
from services.marketing_knowledge import KnowledgeAggregator


class _Response:
    def __init__(self, payload, *, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class _HTTP:
    def __init__(self, packs, *, upload_status: int = 200):
        self.packs = packs
        self.upload_status = upload_status
        self.posts = []
        self.deletes = []
        self.gets = []
        self.on_post = None

    def post(self, path, *, headers, json):
        self.posts.append((path, headers, json))
        if self.on_post is not None:
            self.on_post()
        return _Response({"operation": "ingested"}, status_code=self.upload_status)

    def request(self, method, path, *, headers, json):
        self.deletes.append((method, path, headers, json))
        return _Response({"operation": "deleted"})

    def get(self, path, *, headers):
        self.gets.append((path, headers))
        return _Response({"packs": self.packs})


def _repository(tmp_path):
    state_path = tmp_path / "state.db"
    SessionDB(db_path=state_path).close()
    db = sqlite3.connect(state_path)
    try:
        db.execute(
            """INSERT INTO marketing_learning_candidates
            (id,candidate_type,user_id,account_id,receipt_refs_json,evidence_refs_json,
             proposal_json,confidence,status,created_at)
            VALUES ('learn-sync','strategy','default','acct-1','[]','[]','{}',0.8,
                    'accepted','t0')"""
        )
        db.commit()
    finally:
        db.close()
    repository = KnowledgeFlywheelRepository(
        MarketingDataPaths(tmp_path, tmp_path / "config", state_path)
    )
    contribution = repository.create_contribution(
        user_id="default",
        account_id="acct-1",
        source_candidate_id="learn-sync",
        consent_ref="consent-sync",
        schema_version="knowledge.v1",
        cohort={"platform": "zhihu", "knowledge_type": "content_prior"},
        features={"hook_type": "contrarian"},
        outcomes={"save_rate": 0.08},
    )
    return repository, contribution


def _pack(repository, contribution_id, private_key):
    envelope = repository.export_contribution(contribution_id)
    return KnowledgeAggregator(
        signing_key=private_key,
        key_id="product-sync-1",
        min_cohort_size=2,
        min_category_size=2,
    ).build_packs(
        [envelope, {**envelope, "contribution_ref": "contrib_sync_second"}],
        version="sync-v1",
    )[0]


def test_sync_uploads_pending_outbox_and_installs_verified_pack(tmp_path):
    repository, contribution = _repository(tmp_path)
    private_key = Ed25519PrivateKey.generate()
    pack = _pack(repository, contribution["id"], private_key)
    http = _HTTP([pack])
    client = KnowledgeSyncClient(
        base_url="https://knowledge.example",
        client_id="desktop-install-1",
        token="token-" + "x" * 40,
        public_keys={"product-sync-1": private_key.public_key()},
        repository=repository,
        http_client=http,
    )

    result = client.sync_once()

    assert result["uploaded"] == [contribution["id"]]
    assert result["installed"] == [pack["id"]]
    assert repository.get_contribution(contribution["id"])["status"] == "submitted"
    assert repository.get_knowledge_pack(pack["id"])["status"] == "verified"
    assert http.posts[0][2]["contribution_ref"] == contribution["id"]
    assert "user_id" not in http.posts[0][2]
    assert "account_id" not in http.posts[0][2]


def test_failed_upload_stays_pending_and_tampered_pack_is_rejected(tmp_path):
    repository, contribution = _repository(tmp_path)
    private_key = Ed25519PrivateKey.generate()
    pack = _pack(repository, contribution["id"], private_key)
    pack["payload"] = {}
    client = KnowledgeSyncClient(
        base_url="https://knowledge.example",
        client_id="desktop-install-1",
        token="token-" + "x" * 40,
        public_keys={"product-sync-1": private_key.public_key()},
        repository=repository,
        http_client=_HTTP([pack], upload_status=503),
    )

    result = client.sync_once()

    assert result["uploaded"] == []
    assert result["upload_errors"][0]["error"] == "RuntimeError"
    assert result["installed"] == []
    assert result["pack_errors"][0]["error"] == "ValueError"
    assert repository.get_contribution(contribution["id"])["status"] == "pending"
    with pytest.raises(KeyError):
        repository.get_knowledge_pack(pack["id"])


def test_sync_refuses_plaintext_remote_service():
    with pytest.raises(ValueError, match="HTTPS"):
        KnowledgeSyncClient(
            base_url="http://knowledge.example",
            client_id="desktop-install-1",
            token="token-" + "x" * 40,
            public_keys={"key": b"x" * 32},
            http_client=_HTTP([]),
        )


def test_installation_sync_credentials_remain_global_in_multiplex_mode(monkeypatch):
    private_key = Ed25519PrivateKey.generate()
    public = private_key.public_key().public_bytes_raw()
    monkeypatch.setenv("MARKETING_KNOWLEDGE_URL", "https://knowledge.example")
    monkeypatch.setenv("MARKETING_KNOWLEDGE_CLIENT_ID", "desktop-install-global")
    monkeypatch.setenv("MARKETING_KNOWLEDGE_CLIENT_TOKEN", "token-" + "g" * 40)
    monkeypatch.setenv(
        "MARKETING_KNOWLEDGE_PUBLIC_KEYS_JSON",
        '{"product-global":"' + base64.b64encode(public).decode("ascii") + '"}',
    )
    set_multiplex_active(True)
    try:
        client = from_environment()
        assert client is not None
        assert client.client_id == "desktop-install-global"
        client.close()
    finally:
        set_multiplex_active(False)


def test_sync_executes_submitted_consent_withdrawal(tmp_path):
    repository, contribution = _repository(tmp_path)
    repository.update_contribution_status(contribution["id"], "submitted")
    withdrawal = repository.request_contribution_withdrawal(
        contribution["id"], user_id="default", account_id="acct-1"
    )
    http = _HTTP([])
    client = KnowledgeSyncClient(
        base_url="https://knowledge.example",
        client_id="desktop-install-1",
        token="token-" + "x" * 40,
        public_keys={"product-sync-1": b"x" * 32},
        repository=repository,
        http_client=http,
    )

    result = client.sync_once()

    assert result["deleted"] == [contribution["id"]]
    assert result["deletion_errors"] == []
    assert repository.get_contribution(contribution["id"])["status"] == "deleted"
    assert http.deletes[0][1] == f"/v1/contributions/{contribution['id']}"
    assert http.deletes[0][3]["deletion_ref"] == withdrawal["deletion_ref"]


def test_withdrawal_racing_upload_cannot_be_overwritten_by_submit_settlement(tmp_path):
    repository, contribution = _repository(tmp_path)
    http = _HTTP([])
    http.on_post = lambda: repository.request_contribution_withdrawal(
        contribution["id"], user_id="default", account_id="acct-1"
    )
    client = KnowledgeSyncClient(
        base_url="https://knowledge.example",
        client_id="desktop-install-1",
        token="token-" + "x" * 40,
        public_keys={"product-sync-1": b"x" * 32},
        repository=repository,
        http_client=http,
    )

    first = client.sync_once()
    after_upload = repository.get_contribution(contribution["id"])
    http.on_post = None
    second = client.sync_once()

    assert first["uploaded"] == [contribution["id"]]
    assert after_upload["status"] == "delete_pending"
    assert second["deleted"] == [contribution["id"]]
    assert repository.get_contribution(contribution["id"])["status"] == "deleted"
