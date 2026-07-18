from __future__ import annotations

from types import SimpleNamespace

from agent.harness import PermanentStepError
from agent.marketing.workflows.topic_workers import TopicProductionWorkers


def _context() -> SimpleNamespace:
    return SimpleNamespace(
        workflow={
            "id": "workflow-1",
            "owner_user_id": "default",
            "input": {"account_id": "acct-1"},
            "steps": [
                {
                    "key": "video.direct",
                    "state": "succeeded",
                    "output": {
                        "video_direction": {
                            "shot_list": [
                                {
                                    "id": "scene-1",
                                    "duration": 3,
                                    "visual_query": "AI 数据中心实拍",
                                }
                            ]
                        }
                    },
                }
            ],
        },
        step={"input": {}},
        attempt_id="attempt-1",
    )


def test_material_worker_freezes_licensed_search_result_before_skill_fallback():
    calls: list[tuple[str, object]] = []

    class Materials:
        def search(self, **_kwargs):
            return {
                "id": "search-1",
                "candidates": [
                    {
                        "id": "candidate-1",
                        "provider": "pexels",
                        "license_name": "Pexels License",
                        "license_url": "https://www.pexels.com/license/",
                        "source_url": "https://www.pexels.com/video/1/",
                    }
                ],
            }

        def materialize(self, **kwargs):
            calls.append(("materialize", kwargs))
            return {"asset": {"id": "media-1"}}

    worker = object.__new__(TopicProductionWorkers)
    worker.materials = Materials()
    worker.media = SimpleNamespace()
    worker.resolve_media = lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("media-use must not run when licensed search already matched")
    )

    result = worker.search_video_materials(_context())

    assert result.output["selected_assets"] == {"scene-1": "media-1"}
    assert calls[0][1]["candidate_id"] == "candidate-1"
    assert calls[0][1]["rights_reviewed"] is True
    assert result.output["skill_resolutions"] == []


def test_material_worker_uses_media_skill_only_after_search_miss(tmp_path):
    frozen = tmp_path / "resolved.mp4"
    frozen.write_bytes(b"video")
    imported: list[dict] = []

    class Materials:
        def search(self, **_kwargs):
            return {"id": "search-1", "candidates": []}

    class Media:
        def import_generated_file(self, **kwargs):
            imported.append(kwargs)
            return {"id": "media-skill-1"}

    worker = object.__new__(TopicProductionWorkers)
    worker.materials = Materials()
    worker.media = Media()
    worker.resolve_media = lambda **_kwargs: {
        "id": "resolver-1",
        "_source": "search",
        "absolute_path": str(frozen),
        "mime_type": "video/mp4",
        "description": "AI data center",
        "provenance": {"provider": "heygen.asset.search"},
    }

    result = worker.search_video_materials(_context())

    assert result.output["selected_assets"] == {"scene-1": "media-skill-1"}
    assert imported[0]["media_type"] == "video"
    assert imported[0]["source_type"] == "licensed_provider"
    assert imported[0]["rights_status"] == "licensed"
    assert imported[0]["metadata"]["publication_rights_review_required"] is True


def test_material_worker_surfaces_missing_capability_instead_of_fake_asset():
    class Materials:
        def search(self, **_kwargs):
            return {"id": "search-1", "candidates": []}

    worker = object.__new__(TopicProductionWorkers)
    worker.materials = Materials()
    worker.media = SimpleNamespace()
    worker.resolve_media = lambda **_kwargs: (_ for _ in ()).throw(
        RuntimeError("heygen not authenticated")
    )

    try:
        worker.search_video_materials(_context())
    except PermanentStepError as exc:
        assert "heygen not authenticated" in str(exc)
    else:
        raise AssertionError("unresolved shots must fail visibly")


def test_material_worker_reuses_licensed_clip_after_distinct_source_target():
    context = _context()
    context.workflow["steps"][0]["output"]["video_direction"]["shot_list"] = [
        {"id": f"scene-{index}", "duration": 3, "visual_query": f"query {index}"}
        for index in range(1, 5)
    ]
    calls = 0

    class Materials:
        def search(self, **_kwargs):
            nonlocal calls
            calls += 1
            return {
                "id": f"search-{calls}",
                "candidates": [{
                    "id": f"candidate-{calls}",
                    "provider": "wikimedia_commons",
                    "license_name": "CC0",
                    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                    "source_url": "https://commons.wikimedia.org/wiki/File:clip.webm",
                }] if calls <= 2 else [],
            }

        def materialize(self, **kwargs):
            return {"asset": {"id": kwargs["candidate_id"].replace("candidate", "media")}}

    worker = object.__new__(TopicProductionWorkers)
    worker.materials = Materials()
    worker.media = SimpleNamespace()
    worker.resolve_media = lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("two licensed clips are sufficient for this four-shot cut")
    )

    result = worker.search_video_materials(context)

    assert result.output["selected_assets"] == {
        "scene-1": "media-1",
        "scene-2": "media-2",
        "scene-3": "media-1",
        "scene-4": "media-2",
    }
