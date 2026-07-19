from __future__ import annotations


def test_video_creative_roles_route_to_doubao_without_constructing_deepseek_agent(
    monkeypatch,
):
    from tui_gateway import server

    calls = []

    def fake_visual_worker(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(server, "_run_marketing_doubao_text_worker", fake_visual_worker)
    monkeypatch.setattr(
        server,
        "_make_agent",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("video planning must not construct the DeepSeek agent")
        ),
    )

    result = server._run_marketing_creative_worker(
        role="platform_video_showrunner",
        instruction="plan the cut",
        context={"topic": "AI"},
        task_id="attempt-1",
    )

    assert result == {"ok": True}
    assert calls[0]["role"] == "platform_video_showrunner"


def test_marketing_workflow_rpc_reads_events_and_enforces_owner(tmp_path, monkeypatch):
    from agent.harness import HarnessRepository
    from tui_gateway import server

    db_path = tmp_path / "state.db"
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(db_path))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    workflow = HarnessRepository(db_path).create_workflow(
        namespace="marketing",
        owner_user_id="user-1",
        owner_entity_id="entity-1",
        kind="daily-topic",
        title="今日选题",
        source_kind="cron",
        source_ref="daily-topic:2026-07-18",
        steps=[{"key": "collect"}],
    )

    listed = server._methods["marketing.workflow.list"](
        "list-workflows", {"user_id": "user-1", "entity_id": "entity-1"}
    )
    assert [item["id"] for item in listed["result"]["workflows"]] == [workflow["id"]]
    fetched = server._methods["marketing.workflow.get"](
        "get-workflow", {"workflow_id": workflow["id"], "user_id": "user-1"}
    )
    assert fetched["result"]["steps"][0]["key"] == "collect"
    denied = server._methods["marketing.workflow.get"](
        "get-other-workflow", {"workflow_id": workflow["id"], "user_id": "user-2"}
    )
    assert denied["error"]["code"] == 4045
    events = server._methods["marketing.workflow.events"](
        "workflow-events", {"workflow_id": workflow["id"], "user_id": "user-1"}
    )
    assert [event["kind"] for event in events["result"]["events"]] == [
        "workflow.created",
        "step.created",
    ]


def test_marketing_workflow_cancel_and_approval_are_explicit(tmp_path, monkeypatch):
    from agent.harness import HarnessRepository
    from tui_gateway import server

    db_path = tmp_path / "state.db"
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(db_path))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    harness = HarnessRepository(db_path)
    workflow = harness.create_workflow(
        namespace="marketing",
        owner_user_id="default",
        kind="publish",
        title="发布审批",
        steps=[{"key": "publish"}],
    )
    claim = harness.claim_ready_step(worker_id="publisher", workflow_id=workflow["id"])
    assert claim is not None
    approval = harness.request_approval(
        step_id=claim["id"],
        lease_token=claim["lease_token"],
        approval_key="publish:asset-1",
        request={"asset_id": "asset-1"},
        requested_by="publish-policy",
    )

    pending = server._methods["marketing.workflow.approvals"](
        "pending-approvals", {"workflow_id": workflow["id"]}
    )
    assert pending["result"]["approvals"][0]["id"] == approval["id"]
    approved = server._methods["marketing.workflow.approval.respond"](
        "approve-workflow",
        {
            "workflow_id": workflow["id"],
            "approval_id": approval["id"],
            "approved": True,
            "decision": {"confirmed": True},
        },
    )
    assert approved["result"]["state"] == "approved"

    missing_confirmation = server._methods["marketing.workflow.cancel"](
        "cancel-without-confirmation", {"workflow_id": workflow["id"]}
    )
    assert missing_confirmation["error"]["code"] == 4095
    cancelled = server._methods["marketing.workflow.cancel"](
        "cancel-workflow",
        {"workflow_id": workflow["id"], "confirmed": True, "reason": "用户停止"},
    )
    assert cancelled["result"]["state"] == "cancelled"
