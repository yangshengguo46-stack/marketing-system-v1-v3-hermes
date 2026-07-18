from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.harness import PermanentStepError
from agent.marketing.domains.content_assets import _validated_sound_plan
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


def test_material_worker_tries_next_licensed_candidate_after_download_failure():
    class Materials:
        def search(self, **_kwargs):
            return {
                "id": "search-1",
                "candidates": [
                    {
                        "id": "candidate-broken",
                        "provider": "wikimedia_commons",
                        "provider_asset_id": "broken",
                        "license_name": "CC0",
                        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                        "source_url": "https://commons.wikimedia.org/wiki/File:broken.webm",
                    },
                    {
                        "id": "candidate-working",
                        "provider": "wikimedia_commons",
                        "provider_asset_id": "working",
                        "license_name": "CC0",
                        "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                        "source_url": "https://commons.wikimedia.org/wiki/File:working.jpg",
                    },
                ],
            }

        def materialize(self, **kwargs):
            if kwargs["candidate_id"] == "candidate-broken":
                raise RuntimeError("remote file disappeared")
            return {"asset": {"id": "media-working"}}

    worker = object.__new__(TopicProductionWorkers)
    worker.materials = Materials()
    worker.media = SimpleNamespace()
    worker.resolve_media = lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("second licensed candidate should be used")
    )

    result = worker.search_video_materials(_context())

    assert result.output["selected_assets"] == {"scene-1": "media-working"}


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


def test_material_worker_requires_semantically_distinct_sources_for_half_the_cut():
    context = _context()
    context.workflow["steps"][0]["output"]["video_direction"]["shot_list"] = [
        {"id": f"scene-{index}", "duration": 3, "visual_query": f"query {index}"}
        for index in range(1, 5)
    ]
    class Materials:
        def search(self, **kwargs):
            ref = str(kwargs["request_ref"])
            scene = ref.split(":")[-2]
            query_index = ref.split(":")[-1]
            return {
                "id": f"search-{scene}-{query_index}",
                "candidates": [{
                    "id": f"candidate-{scene}-{query_index}",
                    "provider": "wikimedia_commons",
                    "provider_asset_id": f"provider-{scene}",
                    "license_name": "CC0",
                    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                    "source_url": f"https://commons.wikimedia.org/wiki/File:{scene}.webm",
                }],
            }

        def materialize(self, **kwargs):
            return {"asset": {"id": kwargs["candidate_id"].replace("candidate", "media")}}

    worker = object.__new__(TopicProductionWorkers)
    worker.materials = Materials()
    worker.media = SimpleNamespace()
    worker.resolve_media = lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("licensed search should resolve each shot")
    )

    result = worker.search_video_materials(context)

    assert result.output["selected_assets"] == {
        "scene-1": "media-scene-1-0",
        "scene-2": "media-scene-2-0",
        "scene-3": "media-scene-3-0",
        "scene-4": "media-scene-4-0",
    }
    assert result.output["diversity"] == {
        "minimum_unique_assets": 2,
        "unique_assets": 4,
        "maximum_uses_per_asset": 2,
    }


def test_material_worker_blocks_one_clip_repeated_across_a_four_shot_cut():
    context = _context()
    context.workflow["steps"][0]["output"]["video_direction"]["shot_list"] = [
        {"id": f"scene-{index}", "duration": 3, "visual_query": f"query {index}"}
        for index in range(1, 5)
    ]

    class Materials:
        def search(self, **kwargs):
            return {
                "id": str(kwargs["request_ref"]),
                "candidates": [{
                    "id": "candidate-shared",
                    "provider": "wikimedia_commons",
                    "provider_asset_id": "shared-clip",
                    "license_name": "CC0",
                    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                    "source_url": "https://commons.wikimedia.org/wiki/File:shared.webm",
                }],
            }

        def materialize(self, **_kwargs):
            return {"asset": {"id": "media-shared"}}

    worker = object.__new__(TopicProductionWorkers)
    worker.materials = Materials()
    worker.media = SimpleNamespace()
    worker.resolve_media = lambda **_kwargs: (_ for _ in ()).throw(
        RuntimeError("no second licensed source")
    )

    with pytest.raises(PermanentStepError, match="required_unique=2; resolved_unique=1"):
        worker.search_video_materials(context)


def test_audio_worker_executes_durable_default_voiceover_when_authorized():
    calls: list[tuple[str, dict]] = []

    class Audio:
        def prepare_voice(self, **kwargs):
            calls.append(("prepare", kwargs))
            return {"id": "audio-job-1", "status": "prepared"}

        def approve(self, **kwargs):
            calls.append(("approve", kwargs))
            return {"id": "audio-job-1", "status": "approved"}

        def execute(self, **kwargs):
            calls.append(("execute", kwargs))
            return {
                "id": "audio-job-1",
                "status": "completed",
                "output_asset_id": "voice-media-1",
            }

    context = _context()
    context.workflow["policy"] = {"automatic_voiceover_authorized": True}
    context.workflow["steps"][0]["output"]["video_direction"].update({
        "title": "AI 泡沫",
        "voiceover_script": "这是一段真实旁白。",
    })
    worker = object.__new__(TopicProductionWorkers)
    worker.audio = Audio()

    result = worker.plan_video_audio(context)

    assert [name for name, _ in calls] == ["prepare", "approve", "execute"]
    assert result.output == {
        "voice_job_id": "audio-job-1",
        "voice_status": "completed",
        "draft_mix": "voiceover",
        "render_voice_asset_id": "voice-media-1",
    }
    assert [artifact["object_type"] for artifact in result.artifacts] == [
        "marketing_audio_job",
        "media_asset",
    ]


def test_audio_worker_keeps_paid_tts_prepared_without_durable_authorization():
    class Audio:
        def prepare_voice(self, **_kwargs):
            return {"id": "audio-job-1", "status": "prepared"}

        def approve(self, **_kwargs):
            raise AssertionError("approval must remain explicit when auto voiceover is off")

        def execute(self, **_kwargs):
            raise AssertionError("paid TTS must not execute without durable authorization")

    context = _context()
    context.workflow["policy"] = {"automatic_voiceover_authorized": False}
    context.workflow["steps"][0]["output"]["video_direction"].update({
        "title": "AI 泡沫",
        "voiceover_script": "这是一段待批准旁白。",
    })
    worker = object.__new__(TopicProductionWorkers)
    worker.audio = Audio()

    result = worker.plan_video_audio(context)

    assert result.output["draft_mix"] == "captions_only"
    assert result.output["render_voice_asset_id"] is None


def test_optional_voice_job_survives_content_asset_sound_plan_validation():
    result = _validated_sound_plan(
        {
            "mode": "original_voice_only",
            "mix_role": "captions_first_preview",
            "voice_job_id": "audio-job-1",
            "voice_required": False,
            "voice_status": "prepared",
        },
        repository=SimpleNamespace(),
        user_id="default",
        account_id="acct-1",
        platform="douyin",
    )

    assert result["voice_job_id"] == "audio-job-1"
    assert result["voice_required"] is False
    assert result["voice_status"] == "prepared"
