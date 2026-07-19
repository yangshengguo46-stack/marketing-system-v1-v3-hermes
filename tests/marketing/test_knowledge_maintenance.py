from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agent.epistemic_contract import _issue_system_authority
from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.evidence import EvidenceRepository
from agent.marketing.domains.account_strategy import AccountStrategyRepository
from agent.marketing.domains.account_lifecycle import AccountLifecycleRepository
from agent.marketing.domains.knowledge_bases import KnowledgeBaseRepository
from agent.marketing.domains.public_content_observations import (
    PUBLIC_CONTENT_SCHEMA,
    PublicContentObservationRepository,
)
from agent.marketing.intelligence.store import OperatingLoopRepository
from agent.marketing.intelligence.learning_governance import (
    propose_weight_candidate_from_recent_retros,
)
from agent.marketing.knowledge_loop import KnowledgeMaintenanceRunner
from agent.marketing.learning import SystemLearningProjector
from hermes_state import SessionDB


def _paths(tmp_path):
    state_path = tmp_path / "state.db"
    SessionDB(db_path=state_path).close()
    return MarketingDataPaths(tmp_path, tmp_path / "config", state_path)


def _evidence(paths, *, suffix="rule"):
    records = EvidenceRepository(paths).capture_web_extract_result(
        user_id="default",
        account_id="acct-1",
        session_id="session-1",
        result={
            "results": [
                {
                    "url": f"https://example.com/{suffix}",
                    "title": suffix,
                    "content": f"verified source body {suffix}",
                }
            ]
        },
    )
    return records[0]["id"]


def _public_payload(*, observed_at: str, multiplier: int):
    return {
        "schema": PUBLIC_CONTENT_SCHEMA,
        "platform": "douyin",
        "observed_at": observed_at,
        "items": [
            {
                "source_item_id": f"video-{index}",
                "source_url": f"https://www.douyin.com/video/video-{index}",
                "creator": {
                    "platform_account_id": f"creator-{index}",
                    "name": f"creator {index}",
                },
                "content": {
                    "content_type": "video",
                    "title": f"case {index}",
                    "caption": "observable public post",
                },
                "published_at": "2026-07-18T00:00:00+00:00",
                "feedback": {
                    "metrics": {
                        "views": multiplier * index * 100,
                        "likes": multiplier * index * 10,
                    }
                },
            }
            for index in range(1, 4)
        ],
    }


def test_volatile_platform_knowledge_expires_silently(tmp_path):
    paths = _paths(tmp_path)
    knowledge = KnowledgeBaseRepository(paths)
    evidence_id = _evidence(paths)
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    entry = knowledge.add_evidence_knowledge(
        knowledge_base="platform",
        user_id="default",
        account_id="acct-1",
        platform="douyin",
        topic="publishing_rule",
        statement={"rule": "old verified rule"},
        evidence_refs=[evidence_id],
        version="old-v1",
        valid_from=old.isoformat(),
        authority=_issue_system_authority("test_knowledge_maintenance"),
    )

    audit = knowledge.audit_freshness_and_conflicts(
        as_of=(old + timedelta(days=91)).isoformat()
    )

    assert audit["stale_entry_ids"] == [entry["id"]]
    assert knowledge.get_entry(entry["id"])["status"] == "stale"
    assert knowledge.retrieve(knowledge_base="platform", platform="douyin")["entries"] == []


def test_repeated_public_cases_refresh_market_knowledge_without_user_write(tmp_path):
    paths = _paths(tmp_path)
    public = PublicContentObservationRepository(paths)
    public.capture_browser_result(
        user_id="default",
        account_id="acct-1",
        payload=_public_payload(
            observed_at="2026-07-19T00:00:00+00:00", multiplier=1
        ),
        session_id="session-1",
    )
    second_capture = public.capture_browser_result(
        user_id="default",
        account_id="acct-1",
        payload=_public_payload(
            observed_at="2026-07-19T06:00:00+00:00", multiplier=2
        ),
        session_id="session-1",
    )
    for index, captured in enumerate(second_capture["captured"], start=1):
        public.interpret_observation(
            user_id="default",
            account_id="acct-1",
            observation_id=captured["observation_id"],
            model_observation={
                "content_features": {"hook": "observable claim"},
                "audience": {"cohort": "anonymous public cohort"},
                "reaction": {
                    "sample_size": index * 3,
                    "clusters": [
                        {
                            "cohort": "anonymous public cohort",
                            "stance": "experience_sharing",
                            "need_projection": "belonging",
                            "cognitive_projection": "Fe",
                            "existence_strategy": "confirm",
                            "collective_mechanism": "identity_convergence",
                            "themes": ["shared identity"],
                            "count": index * 3,
                        }
                    ],
                    "question_patterns": [],
                    "objection_patterns": [],
                },
                "disconfirming_signals": ["later samples diverge"],
                "data_gaps": ["distribution allocation unknown"],
            },
            confidence=0.55,
            session_id="session-1",
        )

    first = KnowledgeMaintenanceRunner(paths).run(
        as_of="2026-07-19T07:00:00+00:00"
    )
    second = KnowledgeMaintenanceRunner(paths).run(
        as_of="2026-07-19T08:00:00+00:00"
    )
    market = KnowledgeBaseRepository(paths).retrieve(
        knowledge_base="market", platform="douyin", content_kind="video"
    )
    candidates = OperatingLoopRepository(paths).list_learning_candidates(
        user_id="default", account_id="acct-1", status="accepted"
    )

    assert len(first["public_market_entry_ids"]) == 1
    assert second["public_market_entry_ids"] == first["public_market_entry_ids"]
    assert len(market["entries"]) == 1
    assert market["entries"][0]["statement"]["case_count"] == 3
    assert market["entries"][0]["statement"]["latest_metric_medians"] == {
        "likes": 40,
        "views": 400,
    }
    human = market["entries"][0]["statement"]["anonymous_human_projections"]
    assert human["status"] == "repeated_anonymous_projection_clusters"
    assert human["interpreted_case_count"] == 3
    assert human["dimensions"]["collective_mechanism"][
        "observed_reaction_counts"
    ] == {"identity_convergence": 18}
    assert market["entries"][0]["statement"]["observer_contract"][
        "conversation_mutable"
    ] is False
    assert sum(
        (item.get("proposal") or {}).get("kind") == "evidence_knowledge_candidate"
        for item in candidates
    ) == 1
    assert sum(
        (item.get("proposal") or {}).get("kind")
        == "public_content_natural_experiment"
        for item in candidates
    ) == 3
    assert any(
        str(item.get("decision_reason") or "").startswith(
            "system-owned deterministic"
        )
        for item in candidates
    )


def test_conversation_governance_cannot_accept_or_modify_system_knowledge(tmp_path):
    paths = _paths(tmp_path)
    evidence_id = _evidence(paths, suffix="market")
    candidate = KnowledgeBaseRepository(paths).propose_evidence_knowledge(
        knowledge_base="market",
        user_id="default",
        account_id="acct-1",
        platform="douyin",
        topic="market_rule",
        statement={"claim": "pending system observation"},
        evidence_refs=[evidence_id],
        version="v1",
    )

    with pytest.raises(ValueError, match="system-governed"):
        SystemLearningProjector(
            paths,
            authority=_issue_system_authority("test_knowledge_maintenance"),
        ).accept_and_project(
            candidate["id"], reason="user tried to rewrite shared truth"
        )


def test_metric_retros_and_replay_passed_weights_project_silently(tmp_path):
    paths = _paths(tmp_path)
    AccountLifecycleRepository(paths).begin_project(
        user_id="default",
        account_id="acct-1",
        business_goal="让跨天真实回执持续校准预演",
    )
    loop = OperatingLoopRepository(paths)
    for index in range(3):
        receipt = loop.create_receipt(
            source_kind="metric:douyin:owned_browser",
            source_id=f"checkpoint-{index}",
            receipt_type="metric_checkpoint_observed",
            user_id="default",
            account_id="acct-1",
            platform="douyin",
            summary={"metrics": {"views": 100 + index}},
        )
        loop.create_learning_candidate(
            source_key=f"retro-{index}",
            candidate_type="memory",
            user_id="default",
            account_id="acct-1",
            platform="douyin",
            receipt_refs=[receipt["id"]],
            proposal={
                "kind": "published_metric_retro",
                "content_kind": "faceless_video",
                "metric_labels": {
                    "labels": {
                        "attention": {"bucket": "high"},
                        "retention": {"bucket": "low"},
                        "action": {"bucket": "mid"},
                        "risk": {"bucket": "low"},
                    }
                },
                "retro": {"bias_direction": "over"},
                "influence_score": {"score": 52.0},
            },
            confidence=0.75,
        )
    weight = propose_weight_candidate_from_recent_retros(
        loop,
        user_id="default",
        account_id="acct-1",
        platform="douyin",
    )

    result = KnowledgeMaintenanceRunner(paths).run()
    calibration = AccountStrategyRepository(paths).get_active_influence_calibration(
        user_id="default", account_id="acct-1"
    )

    assert weight["weight_candidate_id"] in result["learning"]["projected_candidate_ids"]
    assert calibration is not None
    assert calibration["weights"]["RetentionDesign"] > 0.16
    assert len(
        KnowledgeBaseRepository(paths).retrieve(
            knowledge_base="account", user_id="default", account_id="acct-1"
        )["entries"]
    ) == 3
