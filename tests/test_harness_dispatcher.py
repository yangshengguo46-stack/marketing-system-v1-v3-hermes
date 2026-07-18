from __future__ import annotations

import threading
import time

from agent.harness import (
    HarnessDispatcher,
    HarnessRepository,
    RetryableStepError,
    StepResult,
)


def test_dispatcher_runs_sibling_steps_in_parallel_and_respects_dag(tmp_path):
    repository = HarnessRepository(tmp_path / "state.db")
    workflow = repository.create_workflow(
        namespace="marketing",
        owner_user_id="user-1",
        kind="topic.production",
        title="同选题双分支",
        steps=[
            {"key": "brief", "kind": "freeze"},
            {"key": "article", "kind": "lane", "depends_on": ["brief"]},
            {"key": "video", "kind": "lane", "depends_on": ["brief"]},
        ],
    )
    lock = threading.Lock()
    running = 0
    peak = 0
    release = threading.Event()

    def freeze(_context):
        return {"brief": "frozen"}

    def lane(context):
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
            if peak == 2:
                release.set()
        assert release.wait(timeout=2)
        time.sleep(0.02)
        with lock:
            running -= 1
        return {"lane": context.step["key"]}

    dispatcher = HarnessDispatcher(
        repository,
        handlers={"freeze": freeze, "lane": lane},
        max_concurrency=2,
        lease_seconds=30,
    )
    try:
        assert dispatcher.dispatch_once(workflow_id=workflow["id"]) == 1
        dispatcher.wait_for_idle(timeout=3)
        assert dispatcher.dispatch_once(workflow_id=workflow["id"]) == 2
        dispatcher.wait_for_idle(timeout=3)
    finally:
        dispatcher.shutdown()

    completed = repository.get_workflow(workflow["id"])
    assert completed["state"] == "completed"
    assert peak == 2


def test_dispatcher_leaves_unregistered_step_unclaimed(tmp_path):
    repository = HarnessRepository(tmp_path / "state.db")
    workflow = repository.create_workflow(
        namespace="marketing",
        owner_user_id="user-1",
        kind="topic.production",
        title="缺少执行器",
        steps=[{"key": "video", "kind": "video.render"}],
    )
    dispatcher = HarnessDispatcher(
        repository,
        handlers={"article.qa": lambda context: {}},
    )
    try:
        assert dispatcher.dispatch_once(workflow_id=workflow["id"]) == 0
    finally:
        dispatcher.shutdown()
    assert repository.get_workflow(workflow["id"])["steps"][0]["state"] == "ready"


def test_dispatcher_retries_typed_transient_failure_and_records_receipt(tmp_path):
    repository = HarnessRepository(tmp_path / "state.db")
    workflow = repository.create_workflow(
        namespace="marketing",
        owner_user_id="user-1",
        kind="effect",
        title="可重试活动",
        steps=[{"key": "download", "kind": "download", "max_attempts": 2}],
    )
    calls = 0

    def download(_context):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RetryableStepError("temporary timeout")
        return StepResult(
            output={"asset_id": "asset-1"},
            receipts=[
                {
                    "kind": "provider.download",
                    "idempotency_key": "download:asset-1",
                    "input": {"url": "https://example.test/asset"},
                    "output": {"asset_id": "asset-1"},
                }
            ],
        )

    dispatcher = HarnessDispatcher(repository, handlers={"download": download})
    try:
        assert dispatcher.dispatch_once(workflow_id=workflow["id"]) == 1
        dispatcher.wait_for_idle(timeout=3)
        retrying = repository.get_workflow(workflow["id"])
        assert retrying["state"] == "retrying"
        assert retrying["steps"][0]["state"] == "retry_wait"
        assert dispatcher.dispatch_once(workflow_id=workflow["id"]) == 1
        dispatcher.wait_for_idle(timeout=3)
    finally:
        dispatcher.shutdown()

    completed = repository.get_workflow(workflow["id"], include_events=True)
    assert completed["state"] == "completed"
    assert calls == 2
    assert any(event["kind"] == "receipt.recorded" for event in completed["events"])
