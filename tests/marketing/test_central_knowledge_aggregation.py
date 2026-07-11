from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from marketing_knowledge_protocol import CONTRIBUTION_PROTOCOL, verify_knowledge_pack
from services.marketing_knowledge import KnowledgeAggregator


def _contribution(index: int, *, cohort: str = "founders") -> dict:
    return {
        "protocol": CONTRIBUTION_PROTOCOL,
        "contribution_ref": f"contrib_{index:04d}",
        "schema_version": "knowledge.v1",
        "cohort": {
            "platform": "douyin",
            "region": "cn",
            "knowledge_type": "content_prior",
            "audience_bucket": cohort,
        },
        "features": {
            "hook_type": "contrarian" if index < 18 else "rare_hook",
            "duration_bucket": "15_30s",
        },
        "outcomes": {
            "completion_rate": 0.35 + index / 1_000,
            "performance_bucket": "above_baseline",
        },
        "observed_at": (
            datetime(2026, 7, 1, tzinfo=timezone.utc) + timedelta(hours=index)
        ).isoformat(),
    }


def test_central_aggregator_suppresses_small_cohorts_and_signs_packs():
    private_key = Ed25519PrivateKey.generate()
    aggregator = KnowledgeAggregator(
        signing_key=private_key,
        key_id="product-2026-01",
        min_cohort_size=20,
        min_category_size=5,
    )
    contributions = [_contribution(index) for index in range(20)] + [
        _contribution(100 + index, cohort="tiny") for index in range(3)
    ]

    packs = aggregator.build_packs(
        contributions,
        version="2026.07.11.1",
        now=datetime(2026, 7, 11, tzinfo=timezone.utc),
    )

    assert len(packs) == 1
    pack = packs[0]
    assert pack["sample_size"] == 20
    assert pack["payload"]["cohort"]["audience_bucket"] == "founders"
    hook_values = pack["payload"]["features"]["hook_type"]["values"]
    assert '"contrarian"' in hook_values
    assert '"rare_hook"' not in hook_values
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    assert verify_knowledge_pack(pack, public_keys={"product-2026-01": public_bytes})["id"] == pack["id"]


def test_central_rejects_identity_fields_and_client_detects_tampering():
    private_key = Ed25519PrivateKey.generate()
    aggregator = KnowledgeAggregator(
        signing_key=private_key,
        key_id="product-2026-01",
        min_cohort_size=2,
        min_category_size=2,
    )
    invalid = {**_contribution(1), "user_id": "should-never-leave-device"}
    with pytest.raises(ValueError, match="forbidden fields"):
        aggregator.build_packs([invalid, _contribution(2)], version="v1")

    pack = aggregator.build_packs(
        [_contribution(1), _contribution(2)], version="v1"
    )[0]
    pack["payload"]["outcomes"] = {}
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_knowledge_pack(
            pack,
            public_keys={"product-2026-01": private_key.public_key()},
        )
