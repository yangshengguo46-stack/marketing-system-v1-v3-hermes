import json
import sqlite3
from pathlib import Path

import pytest

from agent.human_observer import HumanObserverReader, SystemHumanObserver
from agent.human_observer.marketing_connector import MarketingReceiptConnector


def _event(owner: SystemHumanObserver):
    return owner.record_observation(
        event_key="source:event-1",
        source_kind="test_sensor",
        source_ref="receipt-1",
        modality="aggregate_behavior",
        occurred_at="2026-07-18T00:00:00+00:00",
        observed_at="2026-07-18T00:01:00+00:00",
        observation={"action": "shared", "count": 12},
        context={"environment": "public_feed"},
        provenance={"collector": "test_fixture", "verified": True},
        rights={"basis": "consent", "retention": "30_days"},
        namespace="human_research",
        cohort_ref=owner.pseudonymous_ref("cohort", "test cohort", namespace="human_research"),
    )


def test_observation_is_immutable_and_separate_from_candidate_interpretation(tmp_path):
    owner = SystemHumanObserver(tmp_path / "state.db")
    event = _event(owner)
    interpretation = owner.record_interpretation(
        interpretation_key="interpretation-1",
        event_id=event["id"],
        theory_id="maslow_hierarchy",
        theory_version="1.0",
        construct="safety",
        claim={"projected_value": "safety", "not_direct_observation": True},
        context_scope={"environment": "public_feed"},
        confidence=0.4,
        namespace="human_research",
    )

    assert owner.get_observation(event["id"])["observation"] == {"action": "shared", "count": 12}
    assert interpretation["status"] == "candidate"
    assert interpretation["claim"]["not_direct_observation"] is True
    with pytest.raises(ValueError, match="immutable observation"):
        owner.record_observation(
            event_key="source:event-1", source_kind="test_sensor", source_ref="receipt-1",
            modality="aggregate_behavior", occurred_at="2026-07-18T00:00:00+00:00",
            observed_at="2026-07-18T00:01:00+00:00", observation={"action": "deleted"},
            context={"environment": "public_feed"}, provenance={"collector": "test_fixture"},
            rights={"basis": "consent", "retention": "30_days"},
        )


def test_theories_are_versioned_competing_lenses_and_existence_is_revisable(tmp_path):
    owner = SystemHumanObserver(tmp_path / "state.db")
    theories = {item["theory_id"]: item for item in owner.list_theories()}
    assert theories["le_bon_crowd_lens"]["epistemic_status"] == "historical_and_contested_not_universal_law"
    assert "social_identity" in theories
    projection = owner.projection(namespace="human_research")
    seed = next(item for item in projection["model_revisions"] if item["model_name"] == "human_existence_meta_model")
    assert seed["ontology"]["fixed_axiom"] is False
    assert seed["status"] == "seed"
    candidate = owner.propose_model_revision(
        model_name="human_existence_meta_model",
        parent_revision_id=seed["id"],
        ontology={"fixed_axiom": False, "claim": "alternative candidate"},
        theory_weights={"existence_strategy": 0.1},
        evidence_event_ids=[], counterevidence_event_ids=[],
        evaluation={"status": "awaiting_sealed_predictions"},
    )
    assert candidate["status"] == "candidate"
    assert candidate["version"] == 2


def test_identity_fields_are_rejected_and_product_reader_has_no_write_seam(tmp_path):
    owner = SystemHumanObserver(tmp_path / "state.db")
    with pytest.raises(ValueError, match="direct identity fields"):
        owner.record_observation(
            event_key="pii", source_kind="test", source_ref="1", modality="text",
            occurred_at="2026-01-01T00:00:00Z", observed_at="2026-01-01T00:00:00Z",
            observation={"username": "alice"}, context={},
            provenance={"collector": "test"}, rights={"basis": "consent", "retention": "1d"},
        )
    reader = HumanObserverReader(tmp_path / "state.db")
    assert not hasattr(reader, "record_observation")
    assert not hasattr(reader, "propose_model_revision")


def test_sealed_prediction_can_only_be_settled_by_a_later_observation(tmp_path):
    owner = SystemHumanObserver(tmp_path / "state.db")
    event = _event(owner)
    prediction = owner.seal_prediction(
        prediction_key="prediction-1", target={"metric": "shares"},
        prediction={"range": [10, 20]}, due_at="2026-07-20T00:00:00Z",
        evidence_event_ids=[event["id"]], namespace="human_research",
    )
    assert prediction["status"] == "sealed"
    outcome = owner.settle_prediction(
        prediction_id=prediction["id"], observation_event_id=event["id"],
        outcome={"shares": 12}, evaluation={"inside_range": True},
    )
    assert outcome["evaluation"]["inside_range"] is True


def test_marketing_connector_is_one_way_idempotent_and_never_auto_promotes(tmp_path):
    db_path = Path(tmp_path / "state.db")
    SystemHumanObserver(db_path)
    summary = {
        "version": "public-content-natural-experiment-v0.3",
        "observed_at": "2026-07-18T00:00:00Z",
        "content": {"content_type": "video", "title": "AI泡沫"},
        "metrics": {"views": 1000, "shares": 12},
        "model_observation": {
            "reaction": {"clusters": [{
                "cohort": "risk-aware viewers", "stance": "skeptical", "count": 12,
                "themes": ["risk"], "need_projection": "safety",
                "cognitive_projection": "Te", "existence_strategy": "preserve",
                "collective_mechanism": "normative_pressure",
            }]}
        },
    }
    db = sqlite3.connect(db_path)
    db.execute(
        """INSERT INTO marketing_receipt_refs
        (id,source_kind,source_id,receipt_type,user_id,account_id,platform,summary_json,created_at)
        VALUES ('receipt-public-1','public_content:douyin','obs-1',
                'public_content_natural_experiment','source-user','source-account','douyin',?,
                '2026-07-18T00:01:00Z')""",
        (json.dumps(summary, ensure_ascii=False),),
    )
    db.commit()
    db.close()

    connector = MarketingReceiptConnector(db_path)
    first = connector.run()
    second = connector.run()
    projection = HumanObserverReader(db_path).projection(namespace="human_research")

    assert first["ingested_receipt_ids"] == ["receipt-public-1"]
    assert second["pending_count"] == 0
    assert len(projection["interpretations"]) == 4
    assert {item["status"] for item in projection["interpretations"]} == {"candidate"}
    assert projection["authority"] == "read_only_no_product_writeback"
