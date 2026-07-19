from cron import product_tasks


def _background(monkeypatch, calls):
    monkeypatch.setattr(
        "agent.marketing.metric_loop.reconcile_observed_metric_checkpoints",
        lambda: calls.append("reconcile") or {"reconciled": []},
    )
    monkeypatch.setattr(
        "agent.marketing.knowledge_loop.run_knowledge_maintenance",
        lambda: calls.append("knowledge") or {"audit": {}},
    )
    monkeypatch.setattr(
        "agent.human_observer.run_human_observer_maintenance",
        lambda: calls.append("human_observer") or {"mode": "silent_system_owned"},
    )


def test_product_task_dispatch_calls_metric_owner_only_when_provider_exists(monkeypatch):
    calls = []
    _background(monkeypatch, calls)

    monkeypatch.setattr(
        "agent.marketing.metric_loop.has_due_metric_collection_support", lambda: True
    )
    monkeypatch.setattr(
        "agent.marketing.providers.knowledge_sync.has_knowledge_sync_provider",
        lambda: False,
    )
    monkeypatch.setattr(
        "agent.marketing.metric_loop.run_due_metric_checkpoints",
        lambda: calls.append("metrics") or {"due_count": 0},
    )

    result = product_tasks.run_product_tasks(sync=True)

    assert calls == ["reconcile", "metrics", "knowledge", "human_observer"]
    assert result == [
        {"task": "marketing_metric_reconciliation", "result": {"reconciled": []}},
        {"task": "marketing_metric_checkpoints", "result": {"due_count": 0}},
        {"task": "marketing_knowledge_maintenance", "result": {"audit": {}}},
        {"task": "human_observer_maintenance", "result": {"mode": "silent_system_owned"}},
    ]


def test_product_task_dispatch_is_silent_without_registered_provider(monkeypatch):
    calls = []
    _background(monkeypatch, calls)
    monkeypatch.setattr(
        "agent.marketing.metric_loop.has_due_metric_collection_support", lambda: False
    )
    monkeypatch.setattr(
        "agent.marketing.providers.knowledge_sync.has_knowledge_sync_provider",
        lambda: False,
    )

    assert product_tasks.run_product_tasks(sync=True) == [
        {"task": "marketing_metric_reconciliation", "result": {"reconciled": []}},
        {"task": "marketing_knowledge_maintenance", "result": {"audit": {}}},
        {"task": "human_observer_maintenance", "result": {"mode": "silent_system_owned"}},
    ]
    assert calls == ["reconcile", "knowledge", "human_observer"]


def test_product_task_dispatch_calls_native_knowledge_sync_owner(monkeypatch):
    calls = []
    _background(monkeypatch, calls)
    monkeypatch.setattr(
        "agent.marketing.metric_loop.has_due_metric_collection_support", lambda: False
    )
    monkeypatch.setattr(
        "agent.marketing.providers.knowledge_sync.has_knowledge_sync_provider",
        lambda: True,
    )
    monkeypatch.setattr(
        "agent.marketing.providers.knowledge_sync.run_knowledge_sync",
        lambda: {"uploaded": ["contrib-1"], "installed": []},
    )

    assert product_tasks.run_product_tasks(sync=True) == [
        {"task": "marketing_metric_reconciliation", "result": {"reconciled": []}},
        {"task": "marketing_knowledge_maintenance", "result": {"audit": {}}},
        {"task": "human_observer_maintenance", "result": {"mode": "silent_system_owned"}},
        {
            "task": "marketing_knowledge_sync",
            "result": {"uploaded": ["contrib-1"], "installed": []},
        },
    ]
