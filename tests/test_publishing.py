"""L3 publishing task lifecycle, content asset transitions, metrics."""

from __future__ import annotations

from agent_core import AgentCoreStore, CapabilityLevel


def test_publishing_task_lifecycle(tmp_path):
    store = AgentCoreStore(tmp_path / "pub.db")
    asset = store.create_content_asset(title="测试视频", type="video", platform="douyin")
    store.transition_content_asset(asset["id"], "review")
    store.transition_content_asset(asset["id"], "approved")

    task = store.create_publishing_task(asset_id=asset["id"], platform="douyin")
    assert task["status"] == "queued"
    assert task["published_version"] == 1

    store.transition_publishing_task(task["id"], "executing")
    assert store.get_publishing_task(task["id"])["status"] == "executing"

    store.complete_publishing_task(
        task["id"],
        effect_id="effect_test",
        receipt={"status": "succeeded", "published_url": "https://douyin.com/video/123"},
    )
    completed = store.get_publishing_task(task["id"])
    assert completed["status"] == "published"
    assert completed["effect_id"] == "effect_test"

    store.schedule_metrics_collection(task["id"], delay_hours=24)
    assert store.get_publishing_task(task["id"])["next_metrics_at"] is not None

    store.collect_metrics(task["id"], {"views": 1000, "likes": 50, "comments": 10})
    final = store.get_publishing_task(task["id"])
    assert final["status"] == "metrics_collected"


def test_asset_transitions_on_publish(tmp_path):
    store = AgentCoreStore(tmp_path / "pub.db")
    asset = store.create_content_asset(title="脚本A", type="script", platform="douyin")
    store.transition_content_asset(asset["id"], "review")
    store.transition_content_asset(asset["id"], "approved")

    task = store.create_publishing_task(asset_id=asset["id"], platform="douyin")
    store.complete_publishing_task(
        task["id"], effect_id="eff_1", receipt={"status": "succeeded"},
    )

    updated = store.get_content_asset(asset["id"])
    assert updated["status"] == "published"


def test_metrics_update_after_collection(tmp_path):
    store = AgentCoreStore(tmp_path / "pub.db")
    asset = store.create_content_asset(title="视频B", type="video", platform="bilibili")
    store.transition_content_asset(asset["id"], "review")
    store.transition_content_asset(asset["id"], "approved")

    task = store.create_publishing_task(asset_id=asset["id"], platform="bilibili")
    store.complete_publishing_task(task["id"], effect_id="eff_1", receipt={"status": "succeeded"})
    store.collect_metrics(task["id"], {"views": 5000, "likes": 200})

    updated = store.get_content_asset(asset["id"])
    assert updated["metrics"]["views"] == 5000
    assert updated["metrics"]["likes"] == 200


def test_publishing_task_invalid_transition(tmp_path):
    store = AgentCoreStore(tmp_path / "pub.db")
    asset = store.create_content_asset(title="test", platform="douyin")
    store.transition_content_asset(asset["id"], "review")
    store.transition_content_asset(asset["id"], "approved")
    task = store.create_publishing_task(asset_id=asset["id"], platform="douyin")

    try:
        store.transition_publishing_task(task["id"], "metrics_collected")
        assert False, "should raise"
    except ValueError:
        pass


def test_publishing_task_list_filter(tmp_path):
    store = AgentCoreStore(tmp_path / "pub.db")
    a1 = store.create_content_asset(title="A", platform="douyin")
    store.transition_content_asset(a1["id"], "review")
    store.transition_content_asset(a1["id"], "approved")
    a2 = store.create_content_asset(title="B", platform="bilibili")
    store.transition_content_asset(a2["id"], "review")
    store.transition_content_asset(a2["id"], "approved")

    store.create_publishing_task(asset_id=a1["id"], platform="douyin")
    t2 = store.create_publishing_task(asset_id=a2["id"], platform="bilibili")
    store.complete_publishing_task(t2["id"], effect_id="eff", receipt={"status": "succeeded"})

    queued = store.list_publishing_tasks(status="queued")
    published = store.list_publishing_tasks(status="published")
    assert len(queued) == 1
    assert len(published) == 1
    assert published[0]["platform"] == "bilibili"


def test_l3_tool_requires_approval(tmp_path):
    from agent_core.tool_manifest import all_tools
    l3_tools = [t for t in all_tools() if t.level is CapabilityLevel.EXTERNAL_EFFECT]
    assert len(l3_tools) == 1
    tool = l3_tools[0]
    assert tool.name == "marketing_effect_publish"
    assert tool.requires_approval is True
    assert tool.level is CapabilityLevel.EXTERNAL_EFFECT


def test_already_published_asset_rejected(tmp_path):
    store = AgentCoreStore(tmp_path / "pub.db")
    asset = store.create_content_asset(title="已发布", platform="douyin")
    store.transition_content_asset(asset["id"], "review")
    store.transition_content_asset(asset["id"], "approved")

    task = store.create_publishing_task(asset_id=asset["id"], platform="douyin")
    store.complete_publishing_task(task["id"], effect_id="eff", receipt={"status": "succeeded"})

    try:
        store.create_publishing_task(asset_id=asset["id"], platform="douyin")
        assert False, "should reject already published asset"
    except ValueError:
        pass
