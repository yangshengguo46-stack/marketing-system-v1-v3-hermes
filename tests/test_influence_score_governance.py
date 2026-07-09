from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from agent_core.account_lifecycle import AccountLifecycleService
from agent_core.influence_score import build_influence_score
from agent_core.learning_governance import (
    decide_weight_candidate_with_replay,
    propose_weight_candidate_from_recent_retros,
    replay_weight_candidate,
)
from agent_core.learning_pipeline import reconcile_published_metrics
from agent_core.store import AgentCoreStore


def _store(tmp_path) -> AgentCoreStore:
    return AgentCoreStore(tmp_path / "influence.db")


def _retro_candidate(
    store: AgentCoreStore,
    *,
    attention: str = "high",
    retention: str = "low",
    action: str = "zero",
    trust: str = "mid",
    risk: str = "low",
    bias: str = "over",
    score: float = 46.0,
    account_id: str = "acct1",
):
    return store.create_learning_candidate(
        candidate_type="memory",
        user_id="u1",
        account_id=account_id,
        platform="douyin",
        proposal={
            "kind": "published_metric_retro",
            "metric_labels": {
                "labels": {
                    "attention": {"bucket": attention},
                    "retention": {"bucket": retention},
                    "action": {"bucket": action},
                    "trust": {"bucket": trust},
                    "risk": {"bucket": risk},
                },
            },
            "retro": {"bias_direction": bias},
            "influence_score": {
                "score": score,
                "components": {
                    "PlatformReachPotential": {"value": 0.78 if attention in {"high", "spike"} else 0.28},
                    "RetentionDesign": {"value": 0.78 if retention in {"high", "spike"} else 0.28},
                    "BusinessValue": {"value": 0.78 if action in {"high", "spike"} else 0.08},
                    "PersuasionScore": {"value": 0.78 if trust in {"high", "spike"} else 0.42},
                    "RiskPenalty": {"value": 0.78 if risk in {"high", "spike"} else 0.25},
                },
            },
        },
        confidence=0.7,
    )


def test_influence_score_is_explainable_and_does_not_fake_missing_dimensions():
    result = build_influence_score({
        "content_score": {
            "scores": {
                "hook": 8,
                "topic": 7,
                "emotion": 8,
                "density": 6,
                "pacing": 4,
                "viewpoint": 7,
                "cta": 3,
            },
            "risk_flags": ["title_bait_risk"],
        },
        "preflight_scores": {
            "platform_fit": 0.72,
            "audience_fit": 0.66,
            "evidence_strength": 0.58,
        },
    })

    assert result["version"] == "influenceos-score-v0.1"
    assert 0 <= result["score"] <= 100
    assert result["components"]["RiskPenalty"]["value"] > 0
    assert result["components"]["HumanAttentionKernel"]["source"] == "content_score.hook_emotion_topic"
    assert "RetentionDesign" in result["components"]
    assert result["missing_dimensions"] == []
    assert result["decision"] in {
        "strong_go",
        "go_with_watchpoints",
        "revise_before_action",
        "do_not_open_or_publish_yet",
    }


def test_learning_governance_requires_repeated_patterns_before_weight_candidate(tmp_path):
    store = _store(tmp_path)
    base = {
        "kind": "published_metric_retro",
        "metric_labels": {
            "labels": {
                "attention": {"bucket": "high"},
                "retention": {"bucket": "low"},
                "action": {"bucket": "zero"},
            },
        },
        "retro": {"bias_direction": "over"},
        "influence_score": {"score": 46.0},
    }
    first = store.create_learning_candidate(
        candidate_type="memory",
        user_id="u1",
        account_id="acct1",
        platform="douyin",
        proposal=base,
        confidence=0.7,
    )

    insufficient = propose_weight_candidate_from_recent_retros(
        store, user_id="u1", account_id="acct1", platform="douyin",
    )
    assert insufficient["status"] == "insufficient_evidence"
    assert insufficient["weight_candidate_id"] is None

    for _ in range(2):
        store.create_learning_candidate(
            candidate_type="memory",
            user_id="u1",
            account_id="acct1",
            platform="douyin",
            proposal=base,
            evidence_refs=[f"learning_candidate:{first['id']}"],
            confidence=0.7,
        )

    created = propose_weight_candidate_from_recent_retros(
        store, user_id="u1", account_id="acct1", platform="douyin",
    )
    assert created["status"] == "candidate_created"
    weight = store.get_learning_candidate(created["weight_candidate_id"])
    assert weight["candidate_type"] == "weight"
    assert weight["status"] == "pending"
    assert weight["proposal"]["kind"] == "influence_weight_adjustment"
    assert weight["proposal"]["rule_key"] in {
        "retention_gap_after_attention",
        "action_gap_after_attention",
        "prediction_over_optimistic",
    }
    assert weight["proposal"]["guardrail"].startswith("pending weight candidate only")

    duplicate = propose_weight_candidate_from_recent_retros(
        store, user_id="u1", account_id="acct1", platform="douyin",
    )
    assert duplicate["status"] == "candidate_exists"
    assert duplicate["weight_candidate_id"] == weight["id"]


def test_weight_candidate_replay_accepts_only_supported_non_harmful_candidates(tmp_path):
    store = _store(tmp_path)
    lifecycle = AccountLifecycleService(store)
    project = lifecycle.create_project(user_id="u1", account_id="acct1", business_goal="经营 AI 教育账号")
    for _ in range(3):
        _retro_candidate(store, bias="")

    created = propose_weight_candidate_from_recent_retros(
        store, user_id="u1", account_id="acct1", platform="douyin",
    )
    assert created["status"] == "candidate_created"

    replay = replay_weight_candidate(store, created["weight_candidate_id"])
    assert replay["status"] == "passed"
    assert replay["can_accept"] is True
    assert replay["support_count"] >= 3
    assert replay["guardrail"] == "replay only; no durable weights changed"

    decided = decide_weight_candidate_with_replay(
        store,
        created["weight_candidate_id"],
        decision="accepted",
        reason="历史回放通过",
    )
    assert decided["status"] == "accepted"
    assert decided["candidate"]["status"] == "accepted"
    assert "no durable weights changed" in decided["guardrail"]
    assert decided["strategy_candidate_id"]
    strategy = lifecycle.get_strategy_candidate(
        user_id="u1",
        account_id="acct1",
        project_id=project["id"],
        candidate_id=decided["strategy_candidate_id"],
    )
    assert strategy["trigger"] == "weight_candidate_replay"
    assert strategy["proposal"]["type"] == "calibrate_influence_weight"
    assert strategy["proposal"]["source_weight_candidate_id"] == created["weight_candidate_id"]
    assert strategy["proposal"]["replay_summary"]["status"] == "passed"

    repeated = decide_weight_candidate_with_replay(
        store,
        created["weight_candidate_id"],
        decision="accepted",
    )
    assert repeated["already_decided"] is True
    assert repeated["strategy_candidate_id"] == strategy["id"]


def test_weight_candidate_acceptance_blocks_when_history_has_too_many_conflicts(tmp_path):
    store = _store(tmp_path)
    for _ in range(3):
        _retro_candidate(store, bias="")
    for _ in range(3):
        _retro_candidate(store, retention="high", action="high", bias="")

    weight = store.create_learning_candidate(
        candidate_type="weight",
        user_id="u1",
        account_id="acct1",
        platform="douyin",
        proposal={
            "kind": "influence_weight_adjustment",
            "version": "learning-governance-v0.1",
            "score_version": "influenceos-score-v0.1",
            "rule_key": "retention_gap_after_attention",
            "support_count": 3,
            "sample_size": 6,
            "proposed_adjustment": {
                "component": "RetentionDesign",
                "direction": "increase_weight",
                "amount": 0.04,
            },
        },
        confidence=0.8,
    )

    replay = replay_weight_candidate(store, weight["id"])
    assert replay["status"] == "failed_conflict"
    assert replay["can_accept"] is False
    assert replay["conflict_ratio"] > 0.25

    blocked = decide_weight_candidate_with_replay(
        store,
        weight["id"],
        decision="accepted",
        reason="尝试接受",
    )
    assert blocked["status"] == "blocked"
    assert blocked["reason"] == "replay_not_passed"
    assert store.get_learning_candidate(weight["id"])["status"] == "pending"


def test_metric_retro_creates_influence_score_and_weight_candidate_after_three_posts(tmp_path):
    store = _store(tmp_path)
    session = store.create_or_get_session(user_id="u1", workspace="workspace")
    task = store.create_task(session_id=session["id"], user_id="u1", account_id="acct1", objective="复盘三条内容")
    for idx in range(3):
        asset = store.create_content_asset(
            title=f"AI 副业内容 {idx}",
            type="script",
            user_id="u1",
            account_id="acct1",
            platform="douyin",
            topic="AI 副业",
            hook="普通人如何避坑",
            content={"script": "开头冲突，中段路径，结尾行动"},
        )
        store.record_content_score(
            asset_id=asset["id"],
            scores={
                "hook": 8,
                "topic": 8,
                "emotion": 7,
                "density": 6,
                "pacing": 4,
                "viewpoint": 7,
                "cta": 2,
                "title_bait_risk": 1,
                "controversy_overload_risk": 1,
            },
            task_id=task["id"],
        )
        prediction = store.create_prediction(
            asset_id=asset["id"],
            task_id=task["id"] if idx == 0 else None,
            prediction={
                "expected_views": {"low": 50000, "mid": 80000, "high": 120000},
                "expected_completion_rate": {"low": 0.35, "mid": 0.45, "high": 0.55},
                "expected_engagement_rate": {"low": 0.06, "mid": 0.1, "high": 0.18},
            },
        )
        store.create_preflight_record(
            user_id="u1",
            account_id="acct1",
            platform="douyin",
            asset_id=asset["id"],
            task_id=task["id"],
            prediction_id=prediction["id"],
            input={"topic": "AI 副业"},
            scores={"platform_fit": 0.72, "audience_fit": 0.68, "evidence_strength": 0.55},
            decision={"go": True},
        )
        publish = store.create_publishing_task(asset_id=asset["id"], platform="douyin")
        store.complete_publishing_task(
            publish["id"], effect_id=f"effect_{idx}", receipt={"status": "success"},
        )
        result = store.collect_metrics(
            publish["id"],
            {"views": 20000, "completion_rate": 0.18, "engagement_rate": 0.04, "new_followers": 0},
            provenance={"source_kind": "manual_entry"},
        )

    learning = result["learning"]
    assert learning["influence_score"]["version"] == "influenceos-score-v0.1"
    assert learning["weight_candidate_id"]
    weight = store.get_learning_candidate(learning["weight_candidate_id"])
    assert weight["candidate_type"] == "weight"
    assert weight["status"] == "pending"
    assert weight["proposal"]["support_count"] >= 3
    assert weight["proposal"]["guardrail"].startswith("pending weight candidate only")
