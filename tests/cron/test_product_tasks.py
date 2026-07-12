from cron import product_tasks


def test_product_task_dispatch_calls_metric_owner_only_when_provider_exists(monkeypatch):
    calls = []

    monkeypatch.setattr(
        "agent.marketing.providers.metrics.has_metric_provider", lambda: True
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

    assert calls == ["metrics"]
    assert result == [
        {"task": "marketing_metric_checkpoints", "result": {"due_count": 0}}
    ]


def test_product_task_dispatch_is_silent_without_registered_provider(monkeypatch):
    monkeypatch.setattr(
        "agent.marketing.providers.metrics.has_metric_provider", lambda: False
    )
    monkeypatch.setattr(
        "agent.marketing.providers.knowledge_sync.has_knowledge_sync_provider",
        lambda: False,
    )

    assert product_tasks.run_product_tasks(sync=True) == []


def test_product_task_dispatch_calls_native_knowledge_sync_owner(monkeypatch):
    monkeypatch.setattr(
        "agent.marketing.providers.metrics.has_metric_provider", lambda: False
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
        {
            "task": "marketing_knowledge_sync",
            "result": {"uploaded": ["contrib-1"], "installed": []},
        }
    ]
