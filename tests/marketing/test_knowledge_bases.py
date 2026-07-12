from __future__ import annotations

import json
import sqlite3

import pytest

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.knowledge_bases import KnowledgeBaseRepository
from hermes_state import SessionDB


def _repository(tmp_path):
    state_path = tmp_path / "state.db"
    owner = SessionDB(db_path=state_path)
    owner.close()
    paths = MarketingDataPaths(tmp_path, tmp_path / "config", state_path)
    return KnowledgeBaseRepository(paths), state_path


def test_four_knowledge_bases_bootstrap_without_user_opinion(tmp_path):
    repository, _ = _repository(tmp_path)

    platform = repository.retrieve(
        knowledge_base="platform", platform="zhihu", content_kind="article_soft"
    )
    content = repository.retrieve(
        knowledge_base="content", content_kind="faceless_video"
    )
    account = repository.retrieve(
        knowledge_base="account", user_id="default", account_id="acct-1"
    )
    market = repository.retrieve(knowledge_base="market")

    assert platform["total"] == 1
    assert platform["entries"][0]["source_kind"] == "builtin_curated"
    assert content["total"] >= 8
    assert {item["statement"]["layer"] for item in content["entries"]} >= {
        "individual_attention",
        "social_propagation",
        "persuasion",
    }
    assert account["total"] == 0
    assert market["total"] == 0


def test_user_or_model_opinion_cannot_write_any_knowledge_truth(tmp_path):
    repository, _ = _repository(tmp_path)

    for source_kind in ("user", "agent", "conversation", "model_inference"):
        with pytest.raises(ValueError, match="cannot write knowledge truth"):
            repository._upsert(
                knowledge_base="platform",
                user_id="default",
                account_id=None,
                platform="douyin",
                region="cn",
                content_kind="video",
                topic="platform_algorithm",
                statement={"claim": "用户随口说的算法结论"},
                source_kind=source_kind,
                source_ref="chat-1",
                evidence_refs=[],
                confidence=1.0,
                version="fake",
                valid_from="2026-07-12T00:00:00+00:00",
            )


def test_account_knowledge_requires_accepted_learning_and_real_receipt(tmp_path):
    repository, state_path = _repository(tmp_path)
    db = sqlite3.connect(state_path)
    try:
        db.execute(
            """INSERT INTO marketing_receipt_refs
            (id,source_kind,source_id,receipt_type,user_id,account_id,summary_json,created_at)
            VALUES ('receipt-1','metric:douyin','post-1','metric_snapshot','default','acct-1','{}','2026-07-11T00:00:00+00:00')"""
        )
        db.execute(
            """INSERT INTO marketing_learning_candidates
            (id,candidate_type,user_id,account_id,platform,receipt_refs_json,evidence_refs_json,
             proposal_json,confidence,status,created_at,decided_at)
            VALUES ('candidate-1','strategy','default','acct-1','douyin',?,'[]',?,0.84,'accepted',
                    '2026-07-11T00:00:00+00:00','2026-07-11T01:00:00+00:00')""",
            (
                json.dumps(["receipt-1"]),
                json.dumps(
                    {
                        "rule_key": "retention_gap_after_attention",
                        "content_kind": "faceless_video",
                        "conclusion": "开头获得注意但中段留存不足",
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        db.commit()
    finally:
        db.close()

    entry = repository.promote_account_learning(
        user_id="default", account_id="acct-1", candidate_id="candidate-1"
    )

    assert entry["knowledge_base"] == "account"
    assert entry["source_kind"] == "accepted_learning"
    assert entry["statement"]["receipt_refs"] == ["receipt-1"]
    retrieved = repository.retrieve(
        knowledge_base="account", user_id="default", account_id="acct-1"
    )
    assert [item["id"] for item in retrieved["entries"]] == [entry["id"]]


def test_preflight_projection_keeps_authority_order_explicit(tmp_path):
    repository, _ = _repository(tmp_path)

    result = repository.retrieve_for_preflight(
        user_id="default",
        account_id="acct-1",
        platforms=["zhihu"],
        content_kind="article_soft",
    )

    assert result["platform"]
    assert result["content"]
    assert result["market"] == []
    assert result["account"] == []
    assert result["authority_order"][0] == "local_receipt_backed_account_knowledge"
    assert result["authority_order"][-1] == "user_preference_memory_is_not_knowledge_truth"


def test_signed_category_pattern_enters_market_not_content_knowledge(tmp_path):
    repository, _ = _repository(tmp_path)

    entry = repository.install_signed_pack(
        {
            "id": "pack-market-1",
            "version": "2026-07-12.v1",
            "knowledge_type": "category_pattern",
            "platform": "douyin",
            "region": "cn",
            "window_start": "2026-07-01T00:00:00+00:00",
            "sample_size": 120,
            "payload": {
                "cohort": {"content_kind": "faceless_video", "category": "ai_education"},
                "pattern": {"trust_format": "screen_proof"},
            },
        }
    )

    assert entry["knowledge_base"] == "market"
    market = repository.retrieve(
        knowledge_base="market", platform="douyin", content_kind="faceless_video"
    )
    content = repository.retrieve(
        knowledge_base="content", platform="douyin", content_kind="faceless_video",
        topics=["category_pattern"],
    )
    assert [item["id"] for item in market["entries"]] == [entry["id"]]
    assert content["entries"] == []
