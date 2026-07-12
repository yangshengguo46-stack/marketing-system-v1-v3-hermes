from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from marketing_knowledge_protocol import CONTRIBUTION_PROTOCOL
from services.marketing_knowledge import CentralKnowledgeStore, KnowledgeAggregator


OWNER = "a" * 64


def _contribution(index: int) -> dict:
    return {
        "protocol": CONTRIBUTION_PROTOCOL,
        "contribution_ref": f"contrib_{index:04d}",
        "schema_version": "knowledge.v1",
        "cohort": {
            "platform": "douyin",
            "region": "cn",
            "knowledge_type": "content_prior",
            "audience_bucket": "founders",
        },
        "features": {"hook_type": "contrarian", "duration_bucket": "15_30s"},
        "outcomes": {"completion_rate": 0.4 + index / 1_000},
        "observed_at": (
            datetime(2026, 7, 1, tzinfo=timezone.utc) + timedelta(hours=index)
        ).isoformat(),
    }


def test_persistent_ingest_is_idempotent_and_rejects_reference_collision(tmp_path):
    store = CentralKnowledgeStore(tmp_path / "central.db")
    first = store.ingest_contribution(_contribution(1), deletion_owner_sha256=OWNER)
    repeated = CentralKnowledgeStore(tmp_path / "central.db").ingest_contribution(
        _contribution(1), deletion_owner_sha256=OWNER
    )
    collision = _contribution(1)
    collision["outcomes"]["completion_rate"] = 0.99

    assert first["operation"] == "ingested"
    assert repeated["operation"] == "already_ingested"
    assert repeated["content_sha256"] == first["content_sha256"]
    with pytest.raises(ValueError, match="different content"):
        store.ingest_contribution(collision, deletion_owner_sha256=OWNER)


def test_central_edge_rejects_nested_identity_and_specific_values(tmp_path):
    store = CentralKnowledgeStore(tmp_path / "central.db")
    identity = _contribution(1)
    identity["features"]["user_id"] = "u-1"
    url = _contribution(2)
    url["outcomes"]["source"] = "https://private.example/item"
    missing_platform = _contribution(3)
    del missing_platform["cohort"]["platform"]

    with pytest.raises(ValueError, match="forbidden field"):
        store.ingest_contribution(identity, deletion_owner_sha256=OWNER)
    with pytest.raises(ValueError, match="identifying data"):
        store.ingest_contribution(url, deletion_owner_sha256=OWNER)
    with pytest.raises(ValueError, match="safe platform"):
        store.ingest_contribution(missing_platform, deletion_owner_sha256=OWNER)


def test_deletion_removes_payload_and_blocks_future_replay(tmp_path):
    store = CentralKnowledgeStore(tmp_path / "central.db")
    store.ingest_contribution(_contribution(1), deletion_owner_sha256=OWNER)

    deleted = store.delete_contribution(
        "contrib_0001", deletion_ref="delete_0001", deletion_owner_sha256=OWNER
    )
    repeated = store.delete_contribution(
        "contrib_0001", deletion_ref="delete_0001", deletion_owner_sha256=OWNER
    )

    assert deleted["operation"] == "deleted"
    assert repeated["operation"] == "already_deleted"
    assert store.list_contributions() == []
    with pytest.raises(ValueError, match="cannot be replayed"):
        store.ingest_contribution(_contribution(1), deletion_owner_sha256=OWNER)


def test_builds_and_persists_signed_pack_from_durable_rows(tmp_path):
    store = CentralKnowledgeStore(tmp_path / "central.db")
    for index in range(4):
        store.ingest_contribution(_contribution(index), deletion_owner_sha256=OWNER)
    aggregator = KnowledgeAggregator(
        signing_key=Ed25519PrivateKey.generate(),
        key_id="product-2026-01",
        min_cohort_size=4,
        min_category_size=2,
    )

    packs = store.build_and_store_packs(
        aggregator,
        version="2026.07.12.1",
        now=datetime(2026, 7, 12, tzinfo=timezone.utc),
    )

    assert len(packs) == 1
    assert store.get_pack(packs[0]["id"]) == packs[0]
    assert packs[0]["sample_size"] == 4

    store.delete_contribution(
        "contrib_0000", deletion_ref="delete_0000", deletion_owner_sha256=OWNER
    )
    with pytest.raises(KeyError, match="not found"):
        store.get_pack(packs[0]["id"])
    assert store.build_and_store_packs(
        aggregator,
        version="2026.07.12.2",
        now=datetime(2026, 7, 12, tzinfo=timezone.utc),
    ) == []
