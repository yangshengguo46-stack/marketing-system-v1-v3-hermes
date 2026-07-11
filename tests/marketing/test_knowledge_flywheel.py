from __future__ import annotations

import sqlite3

import pytest

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import KnowledgeFlywheelRepository
from hermes_state import SessionDB


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
