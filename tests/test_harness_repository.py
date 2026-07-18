from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agent.harness import HarnessRepository


@pytest.fixture
def harness(tmp_path: Path) -> HarnessRepository:
    return HarnessRepository(tmp_path / "state.db")


def _workflow(harness: HarnessRepository, *, steps=None):
    return harness.create_workflow(
        namespace="marketing",
        owner_user_id="user-1",
        owner_entity_id="entity-1",
        source_kind="marketing.operation",
        source_ref="operation-1",
        kind="daily-topic",
        title="今日选题",
        input={"date": "2026-07-18"},
        steps=steps
        or [
            {"key": "collect", "worker_role": "researcher"},
            {
                "key": "preflight",
                "worker_role": "evaluator",
                "depends_on": ["collect"],
            },
        ],
    )


def test_workflow_dag_promotes_only_after_parent_succeeds(
    harness: HarnessRepository,
) -> None:
    workflow = _workflow(harness)
    assert [(step["key"], step["state"]) for step in workflow["steps"]] == [
        ("collect", "ready"),
        ("preflight", "blocked"),
    ]

    claim = harness.claim_ready_step(
        worker_id="research-worker", workflow_id=workflow["id"]
    )
    assert claim is not None
    assert claim["key"] == "collect"
    harness.start_step(step_id=claim["id"], lease_token=claim["lease_token"])
    workflow = harness.complete_step(
        step_id=claim["id"],
        lease_token=claim["lease_token"],
        output={"evidence_pack_id": "evidence-1"},
        artifacts=[
            {
                "kind": "domain_ref",
                "object_type": "evidence_pack",
                "object_id": "evidence-1",
            }
        ],
    )

    assert workflow["state"] == "running"
    assert [(step["key"], step["state"]) for step in workflow["steps"]] == [
        ("collect", "succeeded"),
        ("preflight", "ready"),
    ]
    next_claim = harness.claim_ready_step(
        worker_id="preflight-worker", workflow_id=workflow["id"]
    )
    assert next_claim is not None
    assert next_claim["key"] == "preflight"
    workflow = harness.complete_step(
        step_id=next_claim["id"],
        lease_token=next_claim["lease_token"],
        output={"decision": "recommended"},
    )
    assert workflow["state"] == "completed"
    assert [event["kind"] for event in harness.list_events(workflow["id"])][-2:] == [
        "step.succeeded",
        "workflow.completed",
    ]


def test_claim_is_atomic_and_token_scoped(harness: HarnessRepository) -> None:
    workflow = _workflow(harness, steps=[{"key": "only"}])

    def claim(worker: str):
        return harness.claim_ready_step(worker_id=worker, workflow_id=workflow["id"])

    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(claim, [f"worker-{index}" for index in range(8)]))
    winners = [claim for claim in claims if claim is not None]
    assert len(winners) == 1

    winner = winners[0]
    with pytest.raises(PermissionError):
        harness.heartbeat(step_id=winner["id"], lease_token="not-the-token")
    heartbeat = harness.heartbeat(
        step_id=winner["id"], lease_token=winner["lease_token"], extend_seconds=60
    )
    assert heartbeat["lease_owner"].startswith("worker-")


def test_resource_scope_prevents_conflicting_parallel_writes(
    harness: HarnessRepository,
) -> None:
    first = _workflow(
        harness,
        steps=[{"key": "revise", "resource_scope": "content-asset:asset-1"}],
    )
    second = harness.create_workflow(
        namespace="marketing",
        owner_user_id="user-1",
        kind="content.revise",
        title="第二次修改",
        steps=[{"key": "revise", "resource_scope": "content-asset:asset-1"}],
    )
    first_claim = harness.claim_ready_step(
        worker_id="writer-1", workflow_id=first["id"]
    )
    assert first_claim is not None
    assert harness.claim_ready_step(
        worker_id="writer-2", workflow_id=second["id"]
    ) is None

    harness.complete_step(
        step_id=first_claim["id"],
        lease_token=first_claim["lease_token"],
        output={"revision": 2},
    )
    second_claim = harness.claim_ready_step(
        worker_id="writer-2", workflow_id=second["id"]
    )
    assert second_claim is not None


def test_expired_attempt_is_reclaimed_without_replaying_completed_work(
    harness: HarnessRepository,
) -> None:
    workflow = _workflow(
        harness,
        steps=[{"key": "render", "max_attempts": 2, "resource_scope": "video:1"}],
    )
    started_at = workflow["created_at"] + 1
    claim = harness.claim_ready_step(
        worker_id="renderer-1",
        workflow_id=workflow["id"],
        lease_seconds=5,
        now=started_at,
    )
    assert claim is not None
    harness.start_step(
        step_id=claim["id"], lease_token=claim["lease_token"], now=started_at + 1
    )

    assert harness.reclaim_expired(workflow_id=workflow["id"], now=started_at + 6) == 1
    recovered = harness.get_workflow(workflow["id"], include_events=True)
    assert recovered["state"] == "retrying"
    assert recovered["steps"][0]["state"] == "ready"
    assert recovered["steps"][0]["attempt_count"] == 1
    assert any(event["kind"] == "step.reclaimed" for event in recovered["events"])

    retry = harness.claim_ready_step(
        worker_id="renderer-2", workflow_id=workflow["id"], now=started_at + 7
    )
    assert retry is not None
    assert retry["attempt_count"] == 2
    completed = harness.complete_step(
        step_id=retry["id"], lease_token=retry["lease_token"], output={"asset": "v1"}
    )
    assert completed["state"] == "completed"


def test_retry_limit_trips_workflow_failure(harness: HarnessRepository) -> None:
    workflow = _workflow(harness, steps=[{"key": "effect", "max_attempts": 1}])
    claim = harness.claim_ready_step(worker_id="provider", workflow_id=workflow["id"])
    assert claim is not None
    failed = harness.fail_step(
        step_id=claim["id"],
        lease_token=claim["lease_token"],
        error={"code": "permanent"},
        retryable=True,
    )
    assert failed["state"] == "failed"
    assert failed["steps"][0]["state"] == "failed"


def test_approval_survives_repository_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    first = HarnessRepository(db_path)
    workflow = _workflow(first, steps=[{"key": "publish"}])
    claim = first.claim_ready_step(worker_id="publisher", workflow_id=workflow["id"])
    assert claim is not None
    approval = first.request_approval(
        step_id=claim["id"],
        lease_token=claim["lease_token"],
        approval_key="publish:asset-1",
        request={"platform": "douyin", "asset_id": "asset-1"},
        requested_by="publish-policy",
        contract_version="marketing.publish.v1",
    )

    second = HarnessRepository(db_path)
    waiting = second.get_workflow(workflow["id"])
    assert waiting["state"] == "waiting_approval"
    assert waiting["steps"][0]["state"] == "waiting_approval"
    decided = second.decide_approval(
        approval_id=approval["id"],
        approved=True,
        decided_by="human:user-1",
        decision={"confirmed": True},
    )
    assert decided["state"] == "approved"
    resumed = second.claim_ready_step(worker_id="publisher", workflow_id=workflow["id"])
    assert resumed is not None
    assert resumed["attempt_count"] == 2


def test_completion_is_idempotent_for_same_attempt_and_output(
    harness: HarnessRepository,
) -> None:
    workflow = _workflow(harness, steps=[{"key": "reduce"}])
    claim = harness.claim_ready_step(worker_id="reducer", workflow_id=workflow["id"])
    assert claim is not None
    first = harness.complete_step(
        step_id=claim["id"], lease_token=claim["lease_token"], output={"value": 1}
    )
    second = harness.complete_step(
        step_id=claim["id"], lease_token=claim["lease_token"], output={"value": 1}
    )
    assert first["state"] == second["state"] == "completed"
    assert len([event for event in harness.list_events(workflow["id"]) if event["kind"] == "step.succeeded"]) == 1


def test_invalid_dag_is_rejected_before_any_rows_are_written(
    harness: HarnessRepository,
) -> None:
    with pytest.raises(ValueError, match="cycle"):
        _workflow(
            harness,
            steps=[
                {"key": "a", "depends_on": ["b"]},
                {"key": "b", "depends_on": ["a"]},
            ],
        )
    assert harness.find_by_source(
        namespace="marketing",
        source_kind="marketing.operation",
        source_ref="operation-1",
    ) is None


def test_receipt_idempotency_rejects_same_key_with_different_input(
    harness: HarnessRepository,
) -> None:
    workflow = _workflow(harness, steps=[{"key": "publish"}])
    first = harness.record_receipt(
        workflow_id=workflow["id"],
        receipt_kind="provider.effect",
        idempotency_key="publish:asset-1:douyin",
        input={"asset_id": "asset-1", "platform": "douyin"},
        status="completed",
        output={"platform_post_id": "post-1"},
    )
    repeated = harness.record_receipt(
        workflow_id=workflow["id"],
        receipt_kind="provider.effect",
        idempotency_key="publish:asset-1:douyin",
        input={"asset_id": "asset-1", "platform": "douyin"},
        status="completed",
        output={"ignored_duplicate": True},
    )
    assert repeated == first
    with pytest.raises(ValueError, match="different input"):
        harness.record_receipt(
            workflow_id=workflow["id"],
            receipt_kind="provider.effect",
            idempotency_key="publish:asset-1:douyin",
            input={"asset_id": "asset-2", "platform": "douyin"},
            status="completed",
        )


def test_explicit_retry_requires_budget_override_and_cancel_closes_workflow(
    harness: HarnessRepository,
) -> None:
    workflow = _workflow(harness, steps=[{"key": "effect", "max_attempts": 1}])
    claim = harness.claim_ready_step(worker_id="provider", workflow_id=workflow["id"])
    assert claim is not None
    harness.fail_step(
        step_id=claim["id"],
        lease_token=claim["lease_token"],
        error="provider rejected request",
        retryable=False,
    )
    with pytest.raises(ValueError, match="budget is exhausted"):
        harness.retry_step(step_id=claim["id"], actor="human:user-1")
    retried = harness.retry_step(
        step_id=claim["id"],
        actor="human:user-1",
        allow_additional_attempt=True,
    )
    assert retried["state"] == "retrying"
    assert retried["steps"][0]["state"] == "ready"
    assert harness.list_workflows(
        namespace="marketing", owner_user_id="user-1", states=["retrying"]
    )[0]["id"] == workflow["id"]

    cancelled = harness.cancel_workflow(
        workflow_id=workflow["id"], actor="human:user-1", reason="用户停止"
    )
    assert cancelled["state"] == "cancelled"
    assert cancelled["steps"][0]["state"] == "cancelled"


def test_restart_cancelled_workflow_preserves_success_and_requeues_frontier(
    harness: HarnessRepository,
) -> None:
    workflow = _workflow(
        harness,
        steps=[
            {"key": "freeze"},
            {"key": "direct", "depends_on": ["freeze"]},
            {"key": "render", "depends_on": ["direct"]},
        ],
    )
    freeze = harness.claim_ready_step(worker_id="worker-1", workflow_id=workflow["id"])
    assert freeze is not None
    harness.complete_step(
        step_id=freeze["id"],
        lease_token=freeze["lease_token"],
        output={"brief": "kept"},
    )
    cancelled = harness.cancel_workflow(
        workflow_id=workflow["id"], actor="human:user-1", reason="pause"
    )

    restarted = harness.restart_cancelled_workflow(
        workflow_id=cancelled["id"], actor="human:user-1"
    )

    by_key = {step["key"]: step for step in restarted["steps"]}
    assert restarted["state"] == "retrying"
    assert by_key["freeze"]["state"] == "succeeded"
    assert by_key["freeze"]["output"] == {"brief": "kept"}
    assert by_key["direct"]["state"] == "ready"
    assert by_key["render"]["state"] == "blocked"
    assert harness.list_events(restarted["id"])[-1]["kind"] == "workflow.restart_requested"


def test_successful_parallel_sibling_does_not_hide_workflow_failure(
    harness: HarnessRepository,
) -> None:
    workflow = _workflow(harness, steps=[{"key": "article"}, {"key": "video"}])
    article = harness.claim_ready_step(worker_id="article", workflow_id=workflow["id"])
    video = harness.claim_ready_step(worker_id="video", workflow_id=workflow["id"])
    assert article is not None and video is not None
    failed = harness.fail_step(
        step_id=video["id"],
        lease_token=video["lease_token"],
        error="material unavailable",
        retryable=False,
    )
    completed = harness.complete_step(
        step_id=article["id"],
        lease_token=article["lease_token"],
        output={"draft": "kept"},
    )

    assert failed["state"] == "failed"
    assert completed["state"] == "failed"
    assert completed["error"]["message"] == "material unavailable"
