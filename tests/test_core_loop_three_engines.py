"""CORE-LOOP: Memory × Receipt × Preflight minimum data protocol.

These tests pin the product spine we discussed:

    Memory -> Preflight -> Action -> Receipt -> Retro -> Candidate -> Memory

The store layer should preserve hard facts as receipt refs, forecasts as
preflight records, and proposed learnings as governed candidates.  The key
safety property is that a learning candidate is not automatically durable
memory just because an outcome happened.
"""

import pytest

from engine.agent_core.models import MemoryKind
from engine.agent_core.store import AgentCoreStore


@pytest.fixture
def store(tmp_path):
    return AgentCoreStore(tmp_path / "core_loop.db")


@pytest.fixture
def agent_task(store):
    session = store.create_or_get_session(user_id="user_1", workspace="workspace_1")
    return store.create_task(
        session_id=session["id"],
        user_id="user_1",
        account_id="acct_douyin_1",
        objective="为抖音账号做一条 AI 教育内容预演",
    )


@pytest.fixture
def asset(store):
    return store.create_content_asset(
        title="AI 教育行业热点软文/短视频脚本",
        type="script",
        user_id="user_1",
        account_id="acct_douyin_1",
        platform="douyin",
        topic="AI 教育",
        hook="普通人如何用 AI 做副业",
        content={"script": "先给出冲突，再给出可操作路径"},
    )


def test_preflight_record_links_prediction_and_redacted_context(store, asset, agent_task):
    prediction = store.create_prediction(
        asset_id=asset["id"],
        task_id=agent_task["id"],
        prediction={
            "expected_views": {"low": 500, "mid": 5000, "high": 30000},
            "attention_bet": "AI 教育 + 普通人副业有明确受众张力",
        },
    )

    preflight = store.create_preflight_record(
        user_id="user_1",
        account_id="acct_douyin_1",
        platform="douyin",
        asset_id=asset["id"],
        task_id=agent_task["id"],
        prediction_id=prediction["id"],
        formula_version="influenceos-v0.1",
        input={
            "audience": "想用 AI 提升收入的普通人",
            "api_key": "should-never-leak",
        },
        scores={
            "identity_tension": 0.74,
            "platform_fit": 0.68,
            "evidence_strength": 0.55,
        },
        decision={
            "go": True,
            "why": "受众明确，证据仍需补强",
            "cookie": "douyin-session-cookie",
        },
    )

    assert preflight["asset_id"] == asset["id"]
    assert preflight["task_id"] == agent_task["id"]
    assert preflight["prediction_id"] == prediction["id"]
    assert preflight["formula_version"] == "influenceos-v0.1"
    assert preflight["status"] == "created"
    assert preflight["input"]["api_key"] == "[REDACTED]"
    assert preflight["decision"]["cookie"] == "[REDACTED]"

    events = store.list_events(agent_task["id"])
    assert [event["event_type"] for event in events].count("core.preflight_created") == 1

    used = store.mark_preflight_used(preflight["id"])
    assert used["status"] == "used_for_action"


def test_publish_and_metric_receipts_are_created_and_idempotent(store, asset):
    publish_task = store.create_publishing_task(asset_id=asset["id"], platform="douyin")

    published = store.complete_publishing_task(
        publish_task["id"],
        effect_id="effect_external_publish",
        receipt={
            "status": "success",
            "url": "https://www.douyin.com/video/1",
            "access_token": "secret-token",
        },
    )
    assert published["status"] == "published"

    publish_receipts = store.list_receipt_refs(
        asset_id=asset["id"],
        receipt_type="publish_receipt",
    )
    assert len(publish_receipts) == 1
    assert publish_receipts[0]["source_kind"] == "publishing"
    assert publish_receipts[0]["summary"]["receipt"]["access_token"] == "[REDACTED]"

    checkpoints = store.list_metric_checkpoints(publish_task["id"])
    metric = store.record_metric_snapshot(
        publish_task["id"],
        {"views": 12000, "likes": 600, "comments": 88, "shares": 31},
        checkpoint_id=checkpoints[0]["id"],
        provenance={"source_kind": "creator_center_mcp", "captured_at": "2026-07-09T12:00:00+00:00"},
    )
    assert metric["metrics"]["views"] == 12000

    metric_receipts = store.list_receipt_refs(
        asset_id=asset["id"],
        receipt_type="metric_snapshot",
    )
    assert len(metric_receipts) == 1
    assert metric_receipts[0]["source_id"] == metric["id"]
    assert metric_receipts[0]["summary"]["metrics"]["likes"] == 600

    duplicate = store.create_receipt_ref(
        source_kind="metric_snapshot",
        source_id=metric["id"],
        source_table="publishing_metric_snapshots",
        receipt_type="metric_snapshot",
        asset_id=asset["id"],
        task_id=publish_task["id"],
        summary={"metrics": {"views": 1}},
    )
    assert duplicate["id"] == metric_receipts[0]["id"]
    assert duplicate["summary"]["metrics"]["views"] == 12000


def test_learning_candidate_cites_preflight_and_receipts_without_auto_memory_mutation(store, asset, agent_task):
    prediction = store.create_prediction(
        asset_id=asset["id"],
        task_id=agent_task["id"],
        prediction={"expected_views": {"mid": 3000}},
    )
    receipt = store.create_receipt_ref(
        source_kind="manual",
        source_id="operator_note_1",
        source_table="manual_notes",
        receipt_type="audience_feedback",
        user_id="user_1",
        account_id="acct_douyin_1",
        platform="douyin",
        asset_id=asset["id"],
        summary={"comment": "用户更关心副业路径，不关心模型参数"},
    )
    preflight = store.create_preflight_record(
        user_id="user_1",
        account_id="acct_douyin_1",
        platform="douyin",
        asset_id=asset["id"],
        task_id=agent_task["id"],
        prediction_id=prediction["id"],
        input={"topic": "AI 教育"},
        scores={"audience_fit": 0.72},
        decision={"go": True},
        receipt_refs=[receipt["id"]],
    )

    candidate = store.create_learning_candidate(
        candidate_type="memory",
        user_id="user_1",
        account_id="acct_douyin_1",
        platform="douyin",
        asset_id=asset["id"],
        preflight_id=preflight["id"],
        prediction_id=prediction["id"],
        receipt_refs=[receipt["id"]],
        evidence_refs=[receipt["id"], preflight["id"]],
        proposal={
            "kind": "audience_preference",
            "content": "该账号受众更吃可落地副业路径，不吃模型参数科普",
        },
        confidence=0.81,
    )

    assert candidate["status"] == "pending"
    assert candidate["receipt_refs"] == [receipt["id"]]
    assert candidate["proposal"]["kind"] == "audience_preference"

    assert store.list_memories(user_id="user_1") == []

    rejected = store.decide_learning_candidate(
        candidate["id"], status="rejected", reason="样本量不足，先观察 3 条内容",
    )
    assert rejected["status"] == "rejected"
    assert rejected["decision_reason"] == "样本量不足，先观察 3 条内容"
    assert store.list_memories(user_id="user_1") == []


def test_existing_memory_promotion_remains_explicit(store):
    memory = store.add_memory_candidate(
        kind=MemoryKind.ACCOUNT,
        user_id="user_1",
        account_id="acct_douyin_1",
        platform="douyin",
        content="标题必须先给用户具体收益，再解释 AI 工具。",
        evidence=[{"type": "receipt_ref", "id": "receipt_example"}],
        confidence=0.78,
        provenance="publish_result",
    )
    assert memory["status"] == "verified"
    assert store.list_memories(user_id="user_1", status="verified")[0]["id"] == memory["id"]
