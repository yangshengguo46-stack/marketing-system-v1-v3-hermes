from __future__ import annotations

import sqlite3

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import KnowledgeFlywheelRepository
from hermes_state import SessionDB
from services.marketing_knowledge import KnowledgeAggregator


def _repository(tmp_path, *, candidate_status: str = "accepted"):
    state_path = tmp_path / "state.db"
    owner = SessionDB(db_path=state_path)
    owner.close()
    db = sqlite3.connect(state_path)
    try:
        db.execute(
            """INSERT INTO marketing_learning_candidates
            (id,candidate_type,user_id,account_id,receipt_refs_json,evidence_refs_json,
             proposal_json,confidence,status,created_at)
            VALUES ('learn-1','strategy','default','acct-1','[]','[]','{}',0.8,?,'t0')""",
            (candidate_status,),
        )
        db.commit()
    finally:
        db.close()
    paths = MarketingDataPaths(
        user_data=tmp_path,
        config_dir=tmp_path / "config",
        agent_db=state_path,
    )
    return KnowledgeFlywheelRepository(paths)


def test_contribution_requires_governed_learning_and_explicit_consent(tmp_path):
    repository = _repository(tmp_path, candidate_status="pending")
    payload = {
        "user_id": "default",
        "account_id": "acct-1",
        "source_candidate_id": "learn-1",
        "consent_ref": "consent-1",
        "schema_version": "knowledge.v1",
        "cohort": {"platform": "zhihu", "content_kind": "article"},
        "features": {"hook_type": "contrarian", "length_bucket": "medium"},
        "outcomes": {"save_rate_bucket": "high", "views_bucket": "1k_10k"},
    }

    with pytest.raises(ValueError, match="accepted learning candidate"):
        repository.create_contribution(**payload)

    repository = _repository(tmp_path / "missing-consent")
    with pytest.raises(ValueError, match="consent_ref"):
        repository.create_contribution(**{**payload, "consent_ref": ""})


def test_contribution_is_deidentified_idempotent_and_status_governed(tmp_path):
    repository = _repository(tmp_path)
    payload = {
        "user_id": "default",
        "account_id": "acct-1",
        "source_candidate_id": "learn-1",
        "consent_ref": "consent-1",
        "schema_version": "knowledge.v1",
        "cohort": {"platform": "zhihu", "content_kind": "article"},
        "features": {"hook_type": "contrarian", "length_bucket": "medium"},
        "outcomes": {"save_rate_bucket": "high", "views_bucket": "1k_10k"},
    }

    first = repository.create_contribution(**payload)
    repeated = repository.create_contribution(**payload)

    assert first["id"] == repeated["id"]
    assert first["status"] == "pending"
    assert first["features"]["hook_type"] == "contrarian"
    submitted = repository.update_contribution_status(first["id"], "submitted")
    assert submitted["status"] == "submitted"
    with pytest.raises(ValueError, match="pending contribution"):
        repository.update_contribution_status(first["id"], "accepted")


def test_contribution_rejects_identity_and_raw_content_fields(tmp_path):
    repository = _repository(tmp_path)
    base = {
        "user_id": "default",
        "account_id": "acct-1",
        "source_candidate_id": "learn-1",
        "consent_ref": "consent-1",
        "schema_version": "knowledge.v1",
        "cohort": {"platform": "zhihu"},
        "outcomes": {"views_bucket": "1k_10k"},
    }

    with pytest.raises(ValueError, match="forbidden aggregate field"):
        repository.create_contribution(
            **base,
            features={"raw_content": "the user's complete article"},
        )
    with pytest.raises(ValueError, match="forbidden aggregate field"):
        repository.create_contribution(
            **base,
            features={"username": "creator"},
        )


def test_export_strips_local_identity_and_verified_pack_installs_as_prior(tmp_path):
    repository = _repository(tmp_path)
    contribution = repository.create_contribution(
        user_id="default",
        account_id="acct-1",
        source_candidate_id="learn-1",
        consent_ref="private-consent-record",
        schema_version="knowledge.v1",
        cohort={"platform": "zhihu", "knowledge_type": "content_prior"},
        features={"hook_type": "contrarian"},
        outcomes={"save_rate": 0.08},
    )
    envelope = repository.export_contribution(contribution["id"])

    assert "user_id" not in envelope
    assert "account_id" not in envelope
    assert "consent_ref" not in envelope
    assert "source_candidate_id" not in envelope
    private_key = Ed25519PrivateKey.generate()
    pack = KnowledgeAggregator(
        signing_key=private_key,
        key_id="product-1",
        min_cohort_size=2,
        min_category_size=2,
    ).build_packs(
        [envelope, {**envelope, "contribution_ref": "contrib_second"}],
        version="v1",
    )[0]
    installed = repository.install_knowledge_pack(
        pack,
        public_keys={"product-1": private_key.public_key()},
    )
    assert installed["status"] == "verified"
    assert installed["authority"] == "global_prior_below_local_receipt"


def test_withdrawal_never_uploads_pending_data_and_enqueues_submitted_deletion(tmp_path):
    pending_repository = _repository(tmp_path / "pending")
    pending = pending_repository.create_contribution(
        user_id="default",
        account_id="acct-1",
        source_candidate_id="learn-1",
        consent_ref="consent-pending",
        schema_version="knowledge.v1",
        cohort={"platform": "zhihu"},
        features={"hook_type": "question"},
        outcomes={"save_rate": 0.04},
    )
    withheld = pending_repository.request_contribution_withdrawal(
        pending["id"], user_id="default", account_id="acct-1"
    )

    assert withheld["status"] == "withheld"
    assert withheld["cohort"] == {}
    assert withheld["features"] == {}
    assert withheld["outcomes"] == {}
    assert pending_repository.list_contributions(statuses=("pending",)) == []

    submitted_repository = _repository(tmp_path / "submitted")
    submitted = submitted_repository.create_contribution(
        user_id="default",
        account_id="acct-1",
        source_candidate_id="learn-1",
        consent_ref="consent-submitted",
        schema_version="knowledge.v1",
        cohort={"platform": "zhihu"},
        features={"hook_type": "question"},
        outcomes={"save_rate": 0.04},
    )
    submitted_repository.update_contribution_status(submitted["id"], "submitted")
    deletion = submitted_repository.request_contribution_withdrawal(
        submitted["id"], user_id="default", account_id="acct-1"
    )

    assert deletion["status"] == "delete_pending"
    assert deletion["features"] == {}
    assert deletion["deletion_ref"].startswith("delete_")
    assert submitted_repository.export_contribution_deletion(submitted["id"]) == {
        "contribution_ref": submitted["id"],
        "deletion_ref": deletion["deletion_ref"],
    }

    reconsented = submitted_repository.create_contribution(
        user_id="default",
        account_id="acct-1",
        source_candidate_id="learn-1",
        consent_ref="consent-submitted-new",
        schema_version="knowledge.v1",
        cohort={"platform": "zhihu"},
        features={"hook_type": "question"},
        outcomes={"save_rate": 0.04},
    )
    assert reconsented["id"] != submitted["id"]
    assert reconsented["status"] == "pending"
