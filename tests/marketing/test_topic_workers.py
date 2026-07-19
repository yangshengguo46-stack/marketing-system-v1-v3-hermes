from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.harness import PermanentStepError, RetryableStepError
from agent.marketing.domains.content_assets import _validated_sound_plan
from agent.marketing.domains.account_context import AccountContextRepository
from agent.marketing.workflows.topic_workers import (
    TopicProductionWorkers,
    _evidence_pack_projection,
    _knowledge_for_production_target,
    _normalize_material_judgment,
    _normalize_shot,
    _normalize_video_treatment,
    _video_ir,
)


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


def test_material_worker_uses_visual_judge_for_relevance_and_layout():
    class Materials:
        def search(self, **_kwargs):
            return {
                "id": "search-1",
                "candidates": [
                    {
                        "id": "candidate-irrelevant",
                        "provider": "pexels",
                        "provider_asset_id": "irrelevant",
                        "preview_url": "https://images.example/irrelevant.jpg",
                        "license_name": "Pexels License",
                        "license_url": "https://www.pexels.com/license/",
                        "source_url": "https://www.pexels.com/video/1/",
                        "score": 0.9,
                    },
                    {
                        "id": "candidate-relevant",
                        "provider": "pexels",
                        "provider_asset_id": "relevant",
                        "preview_url": "https://images.example/relevant.jpg",
                        "license_name": "Pexels License",
                        "license_url": "https://www.pexels.com/license/",
                        "source_url": "https://www.pexels.com/video/2/",
                        "score": 0.5,
                    },
                ],
            }

        def materialize(self, **kwargs):
            assert kwargs["candidate_id"] == "candidate-relevant"
            return {"asset": {"id": "media-relevant"}}

    def judge(**kwargs):
        assert len(kwargs["candidates"]) == 2
        return {
            "ranked_candidates": [
                {
                    "candidate_id": "candidate-relevant",
                    "relevance_score": 0.92,
                    "presentation": "inset_card",
                    "fit": "contain",
                    "subject_anchor": "left",
                },
                {
                    "candidate_id": "candidate-irrelevant",
                    "relevance_score": 0.1,
                    "presentation": "full_bleed",
                    "fit": "cover",
                    "subject_anchor": "center",
                },
            ]
        }

    worker = object.__new__(TopicProductionWorkers)
    worker.materials = Materials()
    worker.media = SimpleNamespace()
    worker.judge_material = judge
    worker.resolve_media = lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("a visually accepted candidate already exists")
    )

    result = worker.search_video_materials(_context())

    assert result.output["selected_assets"] == {"scene-1": "media-relevant"}
    assert result.output["visual_layouts"]["scene-1"] == {
        "presentation": "inset_card",
        "fit": "contain",
        "subject_anchor": "left",
    }
    assert result.output["material_reviews"][0]["accepted_candidate_ids"] == [
        "candidate-relevant"
    ]


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


def test_material_worker_falls_back_from_requested_video_to_licensed_image(tmp_path):
    frozen = tmp_path / "resolved.jpg"
    frozen.write_bytes(b"image")
    resolve_types: list[str] = []

    class Materials:
        def search(self, **kwargs):
            assert kwargs["media_type"] == "either"
            return {"id": "search-1", "candidates": []}

    class Media:
        def import_generated_file(self, **_kwargs):
            return {"id": "media-image-1"}

    def resolve_media(**kwargs):
        resolve_types.append(kwargs["media_type"])
        if kwargs["media_type"] == "video":
            raise RuntimeError("media-use does not resolve this media type: video")
        return {
            "id": "resolver-image-1",
            "_source": "search",
            "absolute_path": str(frozen),
            "mime_type": "image/jpeg",
            "provenance": {"provider": "open-image-search"},
        }

    context = _context()
    context.workflow["steps"][0]["output"]["video_direction"]["shot_list"][0][
        "media_type"
    ] = "video"
    worker = object.__new__(TopicProductionWorkers)
    worker.materials = Materials()
    worker.media = Media()
    worker.resolve_media = resolve_media

    result = worker.search_video_materials(context)

    assert resolve_types == ["video", "image"]
    assert result.output["selected_assets"] == {"scene-1": "media-image-1"}


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
            scene = ref.split(":")[-3]
            query_index = ref.split(":")[-2]
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


def test_audio_worker_retries_an_incomplete_cloud_tts_response():
    class Audio:
        def prepare_voice(self, **_kwargs):
            return {"id": "audio-job-1", "status": "failed"}

        def approve(self, **_kwargs):
            return {"id": "audio-job-1", "status": "approved"}

        def execute(self, **_kwargs):
            raise RuntimeError("speech provider returned no completed audio")

    context = _context()
    context.workflow["policy"] = {"automatic_voiceover_authorized": True}
    context.workflow["steps"][0]["output"]["video_direction"].update({
        "title": "AI 泡沫",
        "voiceover_script": "这是一段待重试旁白。",
    })
    worker = object.__new__(TopicProductionWorkers)
    worker.audio = Audio()

    with pytest.raises(RetryableStepError, match="no completed audio"):
        worker.plan_video_audio(context)


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


def test_cut_qa_observes_rendered_file_then_persists_canonical_preflight(tmp_path):
    final = tmp_path / "final.mp4"
    final.write_bytes(b"rendered-video")
    treatment = {
        "platform": "douyin",
        "title": "AI 是泡沫吗",
        "hook": "三秒钩子",
    }
    context = SimpleNamespace(
        workflow={
            "id": "workflow-cut",
            "owner_user_id": "default",
            "input": {"account_id": "acct-anchor"},
            "steps": [
                {
                    "key": "topic_brief.freeze",
                    "state": "succeeded",
                    "output": {
                        "topic_brief": {
                            "platform_targets": {
                                "douyin": {"execution_account_id": "acct-douyin"}
                            }
                        },
                        "lane_orders": {
                            "video": {"douyin": {"plan_id": "plan-douyin"}}
                        },
                    },
                },
                {
                    "key": "video.preflight.douyin",
                    "state": "succeeded",
                    "output": {"approved_treatment": treatment},
                },
                {
                    "key": "video.render.douyin",
                    "state": "succeeded",
                    "output": {
                        "platform": "douyin",
                        "production_id": "production-1",
                        "output_asset_id": "content-1",
                        "final_video_asset_id": "media-final",
                    },
                },
            ],
        },
        step={"input": {"platform": "douyin"}},
        attempt_id="attempt-cut",
    )

    class Video:
        def get(self, **kwargs):
            assert kwargs["account_id"] == "acct-douyin"
            return {
                "id": "production-1",
                "status": "completed",
                "edl": {"voice_asset_id": "voice-1"},
                "receipt": {
                    "summary": {
                        "technical": {
                            "quality_assurance": {"disposition": "ready"}
                        }
                    }
                },
            }

    class Media:
        def resolve_local_path(self, **kwargs):
            assert kwargs["asset_id"] == "media-final"
            return str(final)

    class Loop:
        def create_preflight(self, **kwargs):
            assert kwargs["plan_id"] == "plan-douyin"
            assert kwargs["input"]["final_video_asset_id"] == "media-final"
            return {"id": "preflight-cut-1", **kwargs}

    creative_calls: list[dict] = []

    def creative(**kwargs):
        creative_calls.append(kwargs)
        assert kwargs["toolsets"] == ("video",)
        assert kwargs["context"]["final_video_path"] == str(final)
        return {
            **{
                key: True
                for key in (
                    "playable",
                    "hook_first_three_seconds_visible",
                    "treatment_parity",
                    "caption_readability",
                    "material_relevance",
                    "evidence_alignment",
                    "audio_present",
                    "audio_sync",
                    "ending_cta_present",
                )
            },
            "scores": {
                "audience_fit": 8,
                "platform_fit": 8,
                "account_fit": 8,
                "emotional_pull": 8,
                "pacing": 8,
                "information_density": 8,
                "evidence_alignment": 8,
            },
            "issues": [],
        }

    worker = object.__new__(TopicProductionWorkers)
    worker.video = Video()
    worker.media = Media()
    worker.loop = Loop()
    worker.creative = creative

    result = worker.qa_video(context)

    assert len(creative_calls) == 1
    assert result.output["cut_preflight_id"] == "preflight-cut-1"
    assert result.output["qa"]["preflight"]["go"] is True
    assert result.artifacts[0]["object_id"] == "preflight-cut-1"


def test_unbound_platform_keeps_execution_owner_but_cannot_borrow_personal_model():
    worker = object.__new__(TopicProductionWorkers)
    context = worker._platform_account_context(
        user_id="default",
        account_id="acct-douyin-anchor",
        production_target={
            "binding_status": "public_prior_only_no_linked_account",
            "personalization_available": False,
        },
    )
    knowledge = _knowledge_for_production_target(
        {
            "platform": [{"id": "platform-public"}],
            "market": [{"id": "market-public"}],
            "content": [{"id": "content-public"}],
            "account": [{"id": "douyin-private"}],
        },
        production_target={"personalization_available": False},
    )

    assert context == {
        "account_id": "acct-douyin-anchor",
        "connected": False,
        "personalization_available": False,
        "binding_status": "public_prior_only_no_linked_account",
    }
    assert knowledge["account"] == []
    assert knowledge["platform"] == [{"id": "platform-public"}]


def test_linked_platform_model_is_read_from_target_but_stored_under_compat_owner(
    monkeypatch,
):
    monkeypatch.setattr(
        AccountContextRepository,
        "read",
        lambda self, **kwargs: {
            "account_id": kwargs["account_id"],
            "connected": True,
            "account": {"id": kwargs["account_id"], "platform": "douyin"},
            "lifecycle": {"audience_hypothesis": {"segments": ["创业者"]}},
        },
    )
    worker = object.__new__(TopicProductionWorkers)
    worker.paths = SimpleNamespace()

    context = worker._platform_account_context(
        user_id="default",
        account_id="acct-anchor",
        production_target={
            "account_id": "acct-douyin",
            "binding_status": "linked_platform_account",
            "personalization_available": True,
        },
    )

    assert context["account_id"] == "acct-anchor"
    assert context["connected"] is False
    assert context["target_connected"] is True
    assert context["execution_account_id"] == "acct-anchor"
    assert context["target_account_id"] == "acct-douyin"
    assert context["target_account"]["platform"] == "douyin"
    assert context["lifecycle"]["audience_hypothesis"]["segments"] == ["创业者"]


def test_topic_brief_evidence_projection_keeps_source_content_and_lineage_bounded():
    projection = _evidence_pack_projection(
        [
            {
                "id": "evidence-1",
                "title": "AI infrastructure report",
                "canonical_url": "https://example.com/report",
                "excerpt": "x" * 3000,
                "captured_at": "2026-07-19T00:00:00Z",
                "verification_level": "source_integrity",
            }
        ]
    )

    assert projection[0]["id"] == "evidence-1"
    assert projection[0]["source_url"] == "https://example.com/report"
    assert len(projection[0]["excerpt"]) == 2500
    assert projection[0]["verification_level"] == "source_integrity"


def test_video_shot_canonicalizes_single_motion_enum_string():
    shot = _normalize_shot(
        {
            "id": "scene-1",
            "duration": 3,
            "purpose": "打开冲突",
            "visual_query": "AI data center",
            "media_type": "video",
            "on_screen_text": "模型越强越要判断",
            "motion_intent": "kinetic_typography",
        },
        0,
    )

    assert shot["motion_intent"] == ["kinetic_typography"]


def test_video_treatment_accepts_model_beat_description_contract():
    treatment = _normalize_video_treatment(
        {
            "platform": "douyin",
            "format": "short_video",
            "title": "AI 越强越要判断",
            "thesis": "判断力是底牌",
            "audience_promise": "给出一个判断框架",
            "hook": "模型越强，你越危险",
            "hook_hypothesis": {"first_three_seconds": "用反常识打开"},
            "aspect_ratio": "9:16",
            "target_duration": 6,
            "pacing": "快",
            "caption_style": "大字",
            "cta": "评论",
            "voiceover_script": "模型越强，越要判断。",
            "beat_sheet": [{"step": "hook", "description": "热点开场"}],
            "claim_evidence_map": [
                {"claim": "模型发布", "evidence_refs": ["evidence-1"]}
            ],
            "shot_list": [
                {
                    "id": "scene-1",
                    "duration": 3,
                    "purpose": "开场",
                    "visual_query": "AI data center",
                    "on_screen_text": "模型越强",
                    "motion_intent": "kinetic_typography",
                    "evidence_refs": ["evidence-1"],
                },
                {
                    "id": "scene-2",
                    "duration": 3,
                    "purpose": "结论",
                    "visual_query": "human thinking",
                    "on_screen_text": "越要判断",
                },
            ],
        },
        platform="douyin",
        allowed_evidence_refs={"evidence-1"},
    )

    assert treatment["beat_sheet"][0]["purpose"] == "热点开场"


def test_video_treatment_rejects_claim_without_verified_evidence():
    value = {
        "platform": "douyin",
        "format": "short_video",
        "title": "AI 判断力",
        "thesis": "判断力是底牌",
        "audience_promise": "给出判断框架",
        "hook": "模型越强越要判断",
        "hook_hypothesis": {"first_three_seconds": "模型越强，你越危险"},
        "aspect_ratio": "9:16",
        "target_duration": 6,
        "pacing": "快",
        "caption_style": "大字",
        "cta": "评论",
        "voiceover_script": "不要把模型输出当事实。",
        "beat_sheet": [{"purpose": "hook"}],
        "claim_evidence_map": [{"claim": "超过 60% 的人被 AI 误导", "evidence_refs": []}],
        "shot_list": [
            {
                "id": "s1",
                "duration": 3,
                "purpose": "hook",
                "visual_query": "office worker checking AI answer",
                "on_screen_text": "AI 会出错",
            },
            {
                "id": "s2",
                "duration": 3,
                "purpose": "close",
                "visual_query": "person verifying information",
                "on_screen_text": "先核验",
            },
        ],
    }

    with pytest.raises(PermanentStepError, match="must reference verified"):
        _normalize_video_treatment(
            value,
            platform="douyin",
            allowed_evidence_refs={"evidence-1"},
        )


def test_material_judgment_and_video_ir_preserve_non_fullscreen_layout():
    judgment = _normalize_material_judgment(
        {
            "ranked_candidates": [{
                "candidate_id": "candidate-1",
                "relevance_score": 9.1,
                "presentation": "inset_card",
                "fit": "cover",
                "subject_anchor": "right",
            }]
        },
        allowed_candidate_ids={"candidate-1"},
    )
    assert judgment["accepted_candidate_ids"] == ["candidate-1"]
    assert judgment["ranked_candidates"][0]["fit"] == "contain"

    ir = _video_ir(
        treatment={
            "aspect_ratio": "9:16",
            "shot_list": [{
                "id": "s1",
                "duration": 3,
                "purpose": "show evidence",
                "on_screen_text": "先看证据",
                "narration": "先看证据",
                "motion_intent": ["brand_layout"],
                "preferred_renderer": "remotion",
            }],
        },
        visual_asset_ids={"s1": "media-1"},
        visual_layouts={
            "s1": {
                "presentation": "inset_card",
                "fit": "contain",
                "subject_anchor": "right",
            }
        },
    )
    assert ir["scenes"][0]["visuals"][0] == {
        "media_asset_id": "media-1",
        "source_in": 0,
        "fit": "contain",
        "presentation": "inset_card",
        "subject_anchor": "right",
    }
