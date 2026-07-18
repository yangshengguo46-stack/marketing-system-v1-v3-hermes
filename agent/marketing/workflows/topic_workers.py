"""Typed Workers for the durable topic-production Harness workflow.

The model is used only for bounded creative judgments.  Marketing repositories
remain the sole owners of plans, preflights, content, media, render jobs and
draft-box state; a model response is never treated as a completion receipt.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from agent.harness import PermanentStepError, StepExecutionContext, StepResult
from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.account_context import AccountContextRepository
from agent.marketing.domains.content_assets import ContentAssetRepository
from agent.marketing.domains.content_policy import ContentProductionPolicy
from agent.marketing.domains.knowledge_bases import KnowledgeBaseRepository
from agent.marketing.domains.material_sourcing import MaterialSourcingRepository
from agent.marketing.domains.media_assets import MediaAssetRepository
from agent.marketing.domains.production_audio import ProductionAudioRepository
from agent.marketing.domains.topic_recommendations import TopicRecommendationRepository
from agent.marketing.domains.video_ir import VIDEO_IR_VERSION
from agent.marketing.domains.video_production import VideoProductionRepository
from agent.marketing.intelligence.production_preflight import (
    create_content_production_preflight,
)
from agent.marketing.intelligence.store import OperatingLoopRepository

from .topic_production import _topic_brief


class CreativeRunner(Protocol):
    """Run one isolated role and return a JSON object matching the requested contract."""

    def __call__(
        self,
        *,
        role: str,
        instruction: str,
        context: dict[str, Any],
        task_id: str,
        toolsets: tuple[str, ...] = (),
    ) -> dict[str, Any]: ...


class MediaResolver(Protocol):
    """Resolve one shot through an installed media skill into a frozen file."""

    def __call__(
        self, *, intent: str, media_type: str, task_id: str
    ) -> dict[str, Any]: ...


HandlerRegistry = Mapping[
    str, Callable[[StepExecutionContext], StepResult | dict[str, Any] | None]
]


_MATERIAL_QUERY_STOPWORDS = {
    "abstract",
    "close",
    "closeup",
    "concept",
    "digital",
    "falling",
    "futuristic",
    "glowing",
    "minimal",
    "opening",
    "panic",
    "red",
    "screen",
    "shapes",
    "with",
}


def _broad_material_queries(query: str) -> list[str]:
    """Turn a verbose visual prompt into a few provider-friendly concepts."""

    tokens = [
        token
        for token in re.findall(r"[a-zA-Z0-9]+", str(query).lower())
        if token not in _MATERIAL_QUERY_STOPWORDS
    ]
    if not tokens:
        return []
    variants = [" ".join(tokens[index : index + 2]) for index in range(len(tokens) - 1)]
    variants.extend(tokens)
    return [variant for variant in variants if len(variant) >= 3][:6]


class TopicProductionWorkers:
    """Native Worker registry for independent article and video branches."""

    def __init__(
        self,
        *,
        creative_runner: CreativeRunner,
        media_resolver: MediaResolver,
        paths: MarketingDataPaths | None = None,
    ) -> None:
        self.paths = paths or MarketingDataPaths.from_env()
        self.creative = creative_runner
        self.resolve_media = media_resolver
        self.content = ContentAssetRepository(self.paths)
        self.topics = TopicRecommendationRepository(self.paths)
        self.loop = OperatingLoopRepository(self.paths)
        self.materials = MaterialSourcingRepository(self.paths)
        self.media = MediaAssetRepository(self.paths)
        self.audio = ProductionAudioRepository(self.paths)
        self.video = VideoProductionRepository(self.paths)

    def handlers(self) -> dict[str, Callable[[StepExecutionContext], StepResult]]:
        return {
            "domain.validate": self.freeze_topic_brief,
            "platform.research": self.research_platform,
            "article.direction": self.direct_article,
            "article.platform_variant": self.adapt_article,
            "article.qa": self.qa_article,
            "video.direction": self.direct_video,
            "video.platform_plan": self.adapt_video,
            "video.material_search": self.search_video_materials,
            "video.audio_plan": self.plan_video_audio,
            "video.previsualization": self.previsualize_video,
            "video.render": self.render_video,
            "video.qa": self.qa_video,
            "draft.settle": self.settle_draft_branch,
            "workflow.reduce": self.reduce_workflow,
        }

    def freeze_topic_brief(self, context: StepExecutionContext) -> StepResult:
        workflow = context.workflow
        user_id = str(workflow["owner_user_id"])
        entity_id = str(workflow.get("owner_entity_id") or "")
        account_id = str((workflow.get("input") or {}).get("account_id") or "")
        candidate_id = str(context.step["input"].get("candidate_id") or "")
        candidate = self.topics.get_candidate(
            candidate_id=candidate_id,
            user_id=user_id,
            entity_id=entity_id,
        )
        brief = _topic_brief(candidate)
        if str(candidate.get("account_id") or "") != account_id:
            raise PermanentStepError("topic candidate is outside the workflow account scope")
        origin_preflight = self.loop.get_preflight(str(brief["preflight_id"]))
        if origin_preflight.get("plan_id") != brief["plan_id"]:
            raise PermanentStepError("topic candidate plan/preflight lineage is inconsistent")
        origin_plan = self.content.get_production_plan(
            plan_id=str(brief["plan_id"]),
            user_id=user_id,
            account_id=account_id,
        )

        article_platforms = self._platforms_for_prefix(context, "article.adapt.")
        video_platforms = self._platforms_for_prefix(context, "video.adapt.")
        account_context = AccountContextRepository(self.paths).read(
            user_id=user_id,
            account_id=account_id,
        )
        lane_orders: dict[str, Any] = {}
        if article_platforms:
            lane_orders["article"] = self._ensure_lane_order(
                lane="article",
                kind="cross_platform_campaign",
                platforms=article_platforms,
                brief=brief,
                user_id=user_id,
                account_id=account_id,
                account_context=account_context,
                origin_plan=origin_plan,
            )
        if video_platforms:
            lane_orders["video"] = self._ensure_lane_order(
                lane="video",
                kind="faceless_video",
                platforms=video_platforms,
                brief=brief,
                user_id=user_id,
                account_id=account_id,
                account_context=account_context,
                origin_plan=origin_plan,
            )
        output = {
            "topic_brief": brief,
            "lane_orders": lane_orders,
            "origin_preflight_id": origin_preflight["id"],
        }
        artifacts = [
            _artifact("topic_brief", "marketing.topic_candidate", candidate_id),
            *[
                _artifact("production_plan", "content_production_plan", order["plan_id"])
                for order in lane_orders.values()
            ],
            *[
                _artifact("preflight", "marketing_preflight", order["preflight_id"])
                for order in lane_orders.values()
            ],
        ]
        return StepResult(output=output, artifacts=artifacts)

    def research_platform(self, context: StepExecutionContext) -> StepResult:
        frozen = self._output(context, "topic_brief.freeze")
        platform = str(context.step["input"].get("platform") or "")
        result = self._creative(
            context,
            role="platform_researcher",
            instruction=(
                "Research the named content platform from current primary/public sources. "
                "Return JSON only with keys: platform, audience_mechanism, discovery_mechanism, "
                "recommended_formats (array), opening_contract, structure_contract, "
                "visual_contract, cta_contract, source_urls (array), observed_at. "
                "Distinguish verified facts from hypotheses and do not invent platform rules."
            ),
            payload={"platform": platform, "topic_brief": frozen["topic_brief"]},
            toolsets=("web",),
        )
        if result.get("platform") != platform or not result.get("source_urls"):
            raise PermanentStepError("platform research returned no traceable sources")
        return StepResult(
            output={"platform_profile": result},
            artifacts=[_artifact("platform_profile", "marketing.platform_profile", platform)],
        )

    def direct_article(self, context: StepExecutionContext) -> StepResult:
        frozen = self._output(context, "topic_brief.freeze")
        result = self._creative(
            context,
            role="article_director",
            instruction=(
                "Create the editorial parent direction independently from the video branch. "
                "Use only the supplied evidence identities for factual claims. Return JSON only "
                "with: title, hook, thesis, content_kernel, parent_body_markdown, outline (array), "
                "claim_evidence_map (array of {claim,evidence_ref}), visual_brief. "
                "The parent draft must be substantive and contain inline [evidence_xxx] markers."
            ),
            payload=frozen,
        )
        for field in ("title", "hook", "content_kernel", "parent_body_markdown"):
            _required_text(result.get(field), field)
        return StepResult(output={"article_direction": result})

    def adapt_article(self, context: StepExecutionContext) -> StepResult:
        frozen = self._output(context, "topic_brief.freeze")
        direction = self._output(context, "article.direct")["article_direction"]
        platform = str(context.step["input"].get("platform") or "")
        profile = self._platform_profile(context, platform)
        result = self._creative(
            context,
            role="article_platform_adapter",
            instruction=(
                "Adapt the parent editorial direction into one platform-native text/image-text "
                "deliverable without changing factual meaning. Return JSON only with: format, "
                "title, body_markdown or caption/short_text/thread/carousel_cards, and "
                "adaptation_basis containing audience_intent, opening, structure, cta. "
                "Keep evidence markers beside factual claims."
            ),
            payload={
                "platform": platform,
                "platform_profile": profile,
                "topic_brief": frozen["topic_brief"],
                "article_direction": direction,
            },
        )
        result["platform"] = platform
        _validate_variant(result, platform=platform)
        return StepResult(output={"platform": platform, "variant": result})

    def qa_article(self, context: StepExecutionContext) -> StepResult:
        frozen = self._output(context, "topic_brief.freeze")
        brief = frozen["topic_brief"]
        order = frozen["lane_orders"]["article"]
        direction = self._output(context, "article.direct")["article_direction"]
        variants = {
            step["output"]["platform"]: step["output"]["variant"]
            for step in context.workflow["steps"]
            if step["key"].startswith("article.adapt.") and step["state"] == "succeeded"
        }
        if set(variants) != set(order["platforms"]):
            raise PermanentStepError("article QA is missing one or more platform variants")
        asset = self.content.create_draft(
            user_id=str(context.workflow["owner_user_id"]),
            account_id=str((context.workflow.get("input") or {}).get("account_id") or ""),
            title=str(direction["title"]),
            plan_id=str(order["plan_id"]),
            asset_type="script",
            platform="multi_platform",
            production_kind="cross_platform_campaign",
            content={
                "schema": "marketing.article_campaign.v2",
                "content_kernel": direction["content_kernel"],
                "parent_body_markdown": direction["parent_body_markdown"],
                "claim_evidence_map": direction.get("claim_evidence_map") or [],
                "visual_brief": direction.get("visual_brief") or {},
                "platform_variants": variants,
            },
            topic=str(brief["topic"]),
            hook=str(direction["hook"]),
            evidence_refs=list(brief["evidence_refs"]),
            reaction_scenarios=[],
        )
        return StepResult(
            output={"asset_id": asset["id"], "status": asset["status"], "platforms": list(variants)},
            artifacts=[_artifact("content_asset", "content_asset", asset["id"])],
        )

    def direct_video(self, context: StepExecutionContext) -> StepResult:
        frozen = self._output(context, "topic_brief.freeze")
        result = self._creative(
            context,
            role="video_director",
            instruction=(
                "Plan a faceless video independently from the article branch. Do not request or "
                "reuse an article script. Return JSON only with: title, hook, thesis, "
                "voiceover_script, target_duration, sound_strategy, and shot_list. shot_list must "
                "contain 2-10 objects with id, duration, purpose, visual_query, on_screen_text, "
                "visual_query as a concise English stock-footage search phrase, and "
                "motion_intent (array chosen from straight_cut, kinetic_typography, "
                "data_visualization, brand_layout, html_css_motion, svg_motion, "
                "designed_transition), and preferred_renderer (auto/remotion/hyperframes)."
            ),
            payload=frozen,
        )
        for field in ("title", "hook", "voiceover_script"):
            _required_text(result.get(field), field)
        shots = result.get("shot_list")
        if not isinstance(shots, list) or not 2 <= len(shots) <= 10:
            raise PermanentStepError("video direction requires 2-10 shots")
        result["shot_list"] = [_normalize_shot(item, index) for index, item in enumerate(shots)]
        return StepResult(output={"video_direction": result})

    def adapt_video(self, context: StepExecutionContext) -> StepResult:
        frozen = self._output(context, "topic_brief.freeze")
        direction = self._output(context, "video.direct")["video_direction"]
        platform = str(context.step["input"].get("platform") or "")
        result = self._creative(
            context,
            role="video_platform_adapter",
            instruction=(
                "Create a platform-native cut plan from the Video Director's own plan. Return JSON "
                "only with: platform, aspect_ratio, target_duration, opening, pacing, caption_style, "
                "cta, shot_overrides (array). Do not refer to any article draft."
            ),
            payload={
                "platform": platform,
                "platform_profile": self._platform_profile(context, platform),
                "topic_brief": frozen["topic_brief"],
                "video_direction": direction,
            },
        )
        result["platform"] = platform
        _required_text(result.get("opening"), "opening")
        return StepResult(output={"platform": platform, "video_plan": result})

    def search_video_materials(self, context: StepExecutionContext) -> StepResult:
        direction = self._output(context, "video.direct")["video_direction"]
        user_id, account_id = self._scope(context)
        searches: list[dict[str, Any]] = []
        selected: dict[str, str] = {}
        reusable_assets: list[str] = []
        skill_resolutions: list[dict[str, Any]] = []
        resolver_errors: list[str] = []
        distinct_target = min(2, len(direction["shot_list"]))
        for shot_index, shot in enumerate(direction["shot_list"]):
            search_attempts: list[dict[str, Any]] = []
            candidates: list[dict[str, Any]] = []
            # Commons and other documentary sources respond much better to
            # compact concepts than to stock-site prompt prose. Keep the
            # original query as evidence, then broaden only until the cut has
            # enough distinct source clips to edit without needless downloads.
            queries = [str(shot["visual_query"])]
            if len(reusable_assets) < distinct_target:
                queries.extend(_broad_material_queries(str(shot["visual_query"])))
            for query_index, query in enumerate(dict.fromkeys(queries)):
                search = self.materials.search(
                    user_id=user_id,
                    account_id=account_id,
                    query=query,
                    role="broll",
                    orientation="portrait",
                    target_duration=float(shot["duration"]),
                    limit=8,
                    request_ref=(
                        f"{context.workflow['id']}:video-v2:{shot['id']}:{query_index}"
                    ),
                )
                search_attempts.append(search)
                candidates = list(search.get("candidates") or [])
                if candidates:
                    break
            owned = next((item for item in candidates if item.get("provider") == "user_library"), None)
            if owned:
                materialized = self.materials.materialize(
                    candidate_id=str(owned["id"]),
                    user_id=user_id,
                    account_id=account_id,
                    rights_reviewed=True,
                )
                selected[str(shot["id"])] = str(materialized["asset"]["id"])
                if selected[str(shot["id"])] not in reusable_assets:
                    reusable_assets.append(selected[str(shot["id"])])
            # Official/search providers are the second tier. Their candidate
            # records already carry a durable source URL, creator and licence
            # URL. For a reversible local preview the workflow may freeze the
            # top result automatically; publication still has its own rights
            # gate for people/property/trademark context.
            licensed = next(
                (
                    item
                    for item in candidates
                    if item.get("provider") != "user_library"
                    and item.get("license_name")
                    and item.get("license_url")
                    and item.get("source_url")
                ),
                None,
            )
            if str(shot["id"]) not in selected and licensed:
                materialized = self.materials.materialize(
                    candidate_id=str(licensed["id"]),
                    user_id=user_id,
                    account_id=account_id,
                    rights_reviewed=True,
                )
                selected[str(shot["id"])] = str(materialized["asset"]["id"])
                if selected[str(shot["id"])] not in reusable_assets:
                    reusable_assets.append(selected[str(shot["id"])])
            if str(shot["id"]) not in selected and len(reusable_assets) < distinct_target:
                try:
                    resolved = self.resolve_media(
                        intent=str(shot["visual_query"]),
                        media_type="video",
                        task_id=context.attempt_id,
                    )
                    source = str(resolved.get("_source") or "")
                    if source == "generated":
                        raise RuntimeError(
                            "generated material is disabled by the zero-cost workflow policy"
                        )
                    provenance = (
                        resolved.get("provenance")
                        if isinstance(resolved.get("provenance"), dict)
                        else {}
                    )
                    provider = str(provenance.get("provider") or "media-use")
                    resolved_path = resolved.get("absolute_path")
                    if not resolved_path:
                        raise RuntimeError("media skill returned no frozen local file")
                    asset = self.media.import_generated_file(
                        user_id=user_id,
                        account_id=account_id,
                        name=str(resolved.get("description") or shot["visual_query"]),
                        media_type="video",
                        role="broll",
                        path=Path(str(resolved_path)),
                        mime_type=str(resolved.get("mime_type") or "video/mp4"),
                        provider=f"skill:{provider}",
                        provider_asset_id=str(
                            resolved.get("sha256")
                            or resolved.get("id")
                            or f"{context.workflow['id']}:{shot['id']}"
                        ),
                        source_type="licensed_provider",
                        rights_status="licensed",
                        metadata={
                            "shot_id": shot["id"],
                            "resolver": "media-use",
                            "description": resolved.get("description"),
                            "source": source,
                            "provenance": provenance,
                            # A frozen catalog/provider receipt authorizes the
                            # reversible local preview. Publishing still runs
                            # a separate rights review; search is not treated
                            # as a blanket publication licence.
                            "publication_rights_review_required": True,
                        },
                        receipt={
                            "effect": "skill_media_resolve",
                            "resolver_record": {
                                key: value
                                for key, value in resolved.items()
                                if key != "absolute_path"
                            },
                            "workflow_id": context.workflow["id"],
                        },
                    )
                    selected[str(shot["id"])] = str(asset["id"])
                    if selected[str(shot["id"])] not in reusable_assets:
                        reusable_assets.append(selected[str(shot["id"])])
                    skill_resolutions.append({
                        "shot_id": shot["id"],
                        "asset_id": asset["id"],
                        "resolver_id": resolved.get("id"),
                        "source": source,
                    })
                except Exception as exc:
                    resolver_errors.append(f"{shot['id']}: {exc}")
            if str(shot["id"]) not in selected and reusable_assets:
                # Editing may legitimately reuse one licensed source clip with
                # a different crop/time range/overlay across adjacent shots.
                # The compositor owns that transformation; material sourcing
                # should not download ten near-duplicates for a ten-shot cut.
                selected[str(shot["id"])] = reusable_assets[
                    shot_index % len(reusable_assets)
                ]
            searches.append({
                "shot_id": shot["id"],
                "search_id": search_attempts[-1]["id"],
                "search_ids": [item["id"] for item in search_attempts],
                "candidate_count": len(candidates),
                "selected_asset_id": selected.get(str(shot["id"])),
                "external_candidates_require_rights_review": sum(
                    1 for item in candidates if item.get("provider") != "user_library"
                ),
            })
        missing = [
            str(shot["id"])
            for shot in direction["shot_list"]
            if str(shot["id"]) not in selected
        ]
        if missing:
            raise PermanentStepError(
                "material skills/providers could not resolve every shot; "
                f"missing={missing}; errors={resolver_errors}"
            )
        return StepResult(
            output={
                "searches": searches,
                "selected_assets": selected,
                "skill_resolutions": skill_resolutions,
            },
            artifacts=[
                _artifact("material_search", "material_search", search_id)
                for item in searches
                for search_id in item["search_ids"]
            ],
            receipts=[{
                "kind": "material.search",
                "idempotency_key": f"material-search:{context.workflow['id']}",
                "input": {"shot_count": len(direction["shot_list"])},
                "output": {
                    "search_ids": [item["search_id"] for item in searches],
                    "skill_resolutions": skill_resolutions,
                },
            }],
        )


    def plan_video_audio(self, context: StepExecutionContext) -> StepResult:
        direction = self._output(context, "video.direct")["video_direction"]
        user_id, account_id = self._scope(context)
        job = self.audio.prepare_voice(
            user_id=user_id,
            account_id=account_id,
            name=f"{direction['title']} 旁白",
            script_text=str(direction["voiceover_script"])[:4000],
        )
        # Paid/provider TTS remains approval-gated.  The first local cut uses
        # captions and may render immediately; the prepared job is resumable.
        return StepResult(
            output={
                "voice_job_id": job["id"],
                "voice_status": job["status"],
                "draft_mix": "captions_only",
                "render_voice_asset_id": None,
            },
            artifacts=[_artifact("audio_job", "marketing_audio_job", job["id"])],
        )

    def previsualize_video(self, context: StepExecutionContext) -> StepResult:
        frozen = self._output(context, "topic_brief.freeze")
        brief = frozen["topic_brief"]
        order = frozen["lane_orders"]["video"]
        direction = self._output(context, "video.direct")["video_direction"]
        platform = str(context.step["input"].get("platform") or "")
        platform_plan = self._output(context, f"video.adapt.{platform}")["video_plan"]
        materials = self._output(context, "video.material.search")
        audio = self._output(context, "video.audio.plan")
        user_id, account_id = self._scope(context)

        visuals: dict[str, str] = dict(materials.get("selected_assets") or {})
        missing = [
            str(shot["id"])
            for shot in direction["shot_list"]
            if str(shot["id"]) not in visuals
        ]
        if missing:
            raise PermanentStepError(
                f"previsualization has unresolved material shots: {missing}"
            )

        source = self.content.create_draft(
            user_id=user_id,
            account_id=account_id,
            title=f"{direction['title']} · {platform}",
            plan_id=str(order["plan_id"]),
            asset_type="video",
            platform=platform,
            production_kind="faceless_video",
            content={
                "schema": "marketing.faceless_video.v2",
                "video_direction": direction,
                "platform_plan": platform_plan,
                "material_manifest": {"searches": materials["searches"], "asset_ids": list(visuals.values())},
                "sound_plan": {
                    "mode": "original_voice_only",
                    "mix_role": "captions_first_preview",
                    "opening_cue_ms": 0,
                    "voice_required": False,
                    "voice_job_id": audio["voice_job_id"],
                    "voice_status": "awaiting_optional_approval",
                },
                "voiceover_script": direction["voiceover_script"],
            },
            topic=str(brief["topic"]),
            hook=str(direction["hook"]),
            evidence_refs=list(brief["evidence_refs"]),
            reaction_scenarios=[],
        )
        video_ir = _video_ir(
            direction=direction,
            platform_plan=platform_plan,
            visual_asset_ids=visuals,
        )
        production = self.video.prepare(
            user_id=user_id,
            account_id=account_id,
            source_asset_id=str(source["id"]),
            video_ir=video_ir,
        )
        readiness = self.video.render_readiness(
            production_id=str(production["id"]),
            user_id=user_id,
            account_id=account_id,
        )
        if readiness.get("ready") is not True:
            raise PermanentStepError("previsualization is not render-ready: " + json.dumps(readiness, ensure_ascii=False))
        return StepResult(
            output={
                "platform": platform,
                "source_asset_id": source["id"],
                "production_id": production["id"],
                "skill_resolutions": materials.get("skill_resolutions") or [],
                "render_plan": production["render_plan"],
                "readiness": readiness,
            },
            artifacts=[
                _artifact("content_asset", "content_asset", source["id"]),
                _artifact("video_production", "video_production", production["id"]),
            ],
        )

    def render_video(self, context: StepExecutionContext) -> StepResult:
        platform = str(context.step["input"].get("platform") or "")
        previs = self._output(context, f"video.previs.{platform}")
        user_id, account_id = self._scope(context)
        if (context.workflow.get("policy") or {}).get("local_draft_render_authorized") is not True:
            raise PermanentStepError("workflow has no local draft render authorization")
        production = self.video.approve(
            production_id=str(previs["production_id"]),
            user_id=user_id,
            account_id=account_id,
            approval_ref=f"workflow:{context.workflow['id']}:local-draft-render",
            confirmed_by_user=True,
        )
        production = self.video.execute(
            production_id=str(production["id"]),
            user_id=user_id,
            account_id=account_id,
            session_id=str(context.attempt_id),
        )
        if production.get("status") != "completed" or not production.get("final_video_asset_id"):
            raise PermanentStepError("renderer completed without a playable final video asset")
        return StepResult(
            output={
                "platform": platform,
                "production_id": production["id"],
                "output_asset_id": production["output_asset_id"],
                "final_video_asset_id": production["final_video_asset_id"],
                "receipt": production.get("receipt") or {},
            },
            artifacts=[
                _artifact("video_production", "video_production", production["id"]),
                _artifact("content_asset", "content_asset", production["output_asset_id"]),
                _artifact("playable_video", "media_asset", production["final_video_asset_id"], media_type="video/mp4"),
            ],
            receipts=[{
                "kind": "video.render",
                "idempotency_key": f"video-render:{production['id']}",
                "input": {"production_id": production["id"]},
                "output": {
                    "final_video_asset_id": production["final_video_asset_id"],
                    "output_asset_id": production["output_asset_id"],
                },
            }],
        )

    def qa_video(self, context: StepExecutionContext) -> StepResult:
        platform = str(context.step["input"].get("platform") or "")
        rendered = self._output(context, f"video.render.{platform}")
        user_id, account_id = self._scope(context)
        production = self.video.get(
            production_id=str(rendered["production_id"]),
            user_id=user_id,
            account_id=account_id,
        )
        quality = (((production.get("receipt") or {}).get("summary") or {}).get("technical") or {}).get("quality_assurance")
        if production.get("status") != "completed":
            raise PermanentStepError("video QA requires a completed production")
        return StepResult(output={**rendered, "qa": quality or {"status": "render_receipt_present"}})

    def settle_draft_branch(self, context: StepExecutionContext) -> StepResult:
        lane = str(context.step["input"].get("lane") or "")
        if lane == "article":
            article = self._output(context, "article.qa")
            refs = [{"object_id": article["asset_id"], "object_type": "content_asset", "title": "图文草稿"}]
        elif lane == "video":
            refs = [
                {
                    "object_id": step["output"]["output_asset_id"],
                    "object_type": "content_asset",
                    "title": f"{step['output']['platform']} 视频草稿",
                }
                for step in context.workflow["steps"]
                if step["key"].startswith("video.qa.") and step["state"] == "succeeded"
            ]
            if not refs:
                raise PermanentStepError("video branch has no QA-approved draft")
        else:
            raise PermanentStepError("draft settlement lane is invalid")
        return StepResult(output={"lane": lane, "results": refs})

    def reduce_workflow(self, context: StepExecutionContext) -> StepResult:
        results: list[dict[str, str]] = []
        for key in ("article.draft_box", "video.draft_box"):
            try:
                results.extend(self._output(context, key).get("results") or [])
            except KeyError:
                continue
        if not results:
            raise PermanentStepError("topic production completed without draft-box results")
        return StepResult(output={"results": results, "draft_destination": "draft_box"})

    def _ensure_lane_order(
        self,
        *,
        lane: str,
        kind: str,
        platforms: list[str],
        brief: dict[str, Any],
        user_id: str,
        account_id: str,
        account_context: dict[str, Any],
        origin_plan: dict[str, Any],
    ) -> dict[str, Any]:
        audience_model = (
            origin_plan.get("audience_model")
            if isinstance(origin_plan.get("audience_model"), dict)
            else {}
        )
        audience_segments = [
            str(item).strip()
            for item in audience_model.get("segments") or []
            if str(item).strip()
        ]
        plan = ContentProductionPolicy().plan(
            objective=f"{brief['topic']}；核心角度：{brief['angle']}",
            kind=kind,
            platforms=platforms,
            # The daily recommendation was already preflighted against this
            # audience hypothesis. Preserve it when narrowing into sibling
            # article/video work orders instead of accidentally turning a
            # strong-go TopicBrief into an audience-less plan.
            audience="；".join(audience_segments),
            evidence_refs=list(brief["evidence_refs"]),
            constraints={
                "source": "marketing.topic-production.workflow.v1",
                "lane": lane,
                "source_plan_id": brief["plan_id"],
                "source_preflight_id": brief["preflight_id"],
                "audience_inherited_from_source_plan": bool(audience_segments),
            },
            account_context=account_context,
        )
        saved = self.content.save_production_plan(
            user_id=user_id,
            account_id=account_id,
            plan=plan,
        )
        try:
            preflight = self.loop.latest_preflight_for_plan(
                plan_id=saved["plan_id"], user_id=user_id, account_id=account_id
            )
        except ValueError:
            knowledge = KnowledgeBaseRepository(self.paths).retrieve_for_preflight(
                user_id=user_id,
                account_id=account_id,
                platforms=platforms,
                content_kind=kind,
            )
            generated = create_content_production_preflight(
                self.loop,
                {
                    "user_id": user_id,
                    "account_id": account_id,
                    "session_id": f"topic-workflow:{brief['candidate_id']}:{lane}",
                    "plan_id": saved["plan_id"],
                    "plan": saved,
                    "evidence_refs": list(brief["evidence_refs"]),
                    "knowledge_context": knowledge,
                },
            )
            preflight = generated["preflight_record"]
        decision = preflight.get("decision") or {}
        preflight_decision = decision.get("preflight_decision") or {}
        if preflight_decision.get("go") is not True:
            raise PermanentStepError(f"{lane} lane failed inherited preflight")
        return {
            "lane": lane,
            "plan_id": saved["plan_id"],
            "preflight_id": preflight["id"],
            "platforms": platforms,
            "source_plan_id": brief["plan_id"],
            "source_preflight_id": brief["preflight_id"],
        }

    def _creative(
        self,
        context: StepExecutionContext,
        *,
        role: str,
        instruction: str,
        payload: dict[str, Any],
        toolsets: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        result = self.creative(
            role=role,
            instruction=instruction,
            context=payload,
            task_id=context.attempt_id,
            toolsets=toolsets,
        )
        if not isinstance(result, dict) or not result:
            raise PermanentStepError(f"{role} returned no structured result")
        return result

    @staticmethod
    def _output(context: StepExecutionContext, key: str) -> dict[str, Any]:
        for step in context.workflow["steps"]:
            if step["key"] == key and step["state"] == "succeeded":
                output = step.get("output")
                if isinstance(output, dict):
                    return output
        raise KeyError(f"required workflow output is unavailable: {key}")

    @staticmethod
    def _platforms_for_prefix(context: StepExecutionContext, prefix: str) -> list[str]:
        return [
            str(step["key"])[len(prefix) :]
            for step in context.workflow["steps"]
            if str(step["key"]).startswith(prefix)
        ]

    def _platform_profile(self, context: StepExecutionContext, platform: str) -> dict[str, Any]:
        try:
            return self._output(context, f"platform.research.{platform}")["platform_profile"]
        except KeyError:
            frozen = self._output(context, "topic_brief.freeze")
            return dict(frozen["topic_brief"]["platform_blueprints"].get(platform) or {})

    @staticmethod
    def _scope(context: StepExecutionContext) -> tuple[str, str]:
        return (
            str(context.workflow["owner_user_id"]),
            str((context.workflow.get("input") or {}).get("account_id") or ""),
        )


def build_topic_production_handlers(
    *,
    creative_runner: CreativeRunner,
    media_resolver: MediaResolver,
    paths: MarketingDataPaths | None = None,
) -> dict[str, Callable[[StepExecutionContext], StepResult]]:
    return TopicProductionWorkers(
        creative_runner=creative_runner,
        media_resolver=media_resolver,
        paths=paths,
    ).handlers()


def _artifact(
    kind: str,
    object_type: str,
    object_id: Any,
    *,
    media_type: str = "application/json",
) -> dict[str, Any]:
    return {
        "kind": kind,
        "object_type": object_type,
        "object_id": str(object_id or ""),
        "media_type": media_type,
    }


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise PermanentStepError(f"creative result is missing {field}")
    return text


def _validate_variant(value: dict[str, Any], *, platform: str) -> None:
    _required_text(value.get("format"), "format")
    if not any(
        value.get(field)
        for field in (
            "body_markdown",
            "caption",
            "carousel_cards",
            "outline",
            "script",
            "short_text",
            "thread",
            "title",
        )
    ):
        raise PermanentStepError(f"{platform} article variant has no substantive content")
    basis = value.get("adaptation_basis")
    if not isinstance(basis, dict) or not all(
        str(basis.get(field) or "").strip()
        for field in ("audience_intent", "opening", "structure", "cta")
    ):
        raise PermanentStepError(f"{platform} article variant has no adaptation basis")


def _normalize_shot(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PermanentStepError("video shot must be an object")
    shot_id = str(value.get("id") or f"scene_{index + 1:03d}").strip()[:120]
    try:
        duration = max(1.2, min(float(value.get("duration") or 3.0), 12.0))
    except (TypeError, ValueError) as exc:
        raise PermanentStepError("video shot duration is invalid") from exc
    motion = value.get("motion_intent") or ["kinetic_typography"]
    if not isinstance(motion, list):
        raise PermanentStepError("video shot motion_intent must be an array")
    allowed = {
        "straight_cut",
        "kinetic_typography",
        "data_visualization",
        "brand_layout",
        "html_css_motion",
        "svg_motion",
        "designed_transition",
    }
    normalized_motion = [str(item) for item in motion if str(item) in allowed]
    return {
        "id": shot_id,
        "duration": round(duration, 3),
        "purpose": _required_text(value.get("purpose"), "shot purpose")[:1000],
        "visual_query": _required_text(value.get("visual_query"), "visual_query")[:300],
        "on_screen_text": _required_text(value.get("on_screen_text"), "on_screen_text")[:300],
        "motion_intent": normalized_motion or ["kinetic_typography"],
        "preferred_renderer": str(value.get("preferred_renderer") or "auto").strip().lower(),
    }


def _video_ir(
    *,
    direction: dict[str, Any],
    platform_plan: dict[str, Any],
    visual_asset_ids: dict[str, str],
) -> dict[str, Any]:
    aspect = str(platform_plan.get("aspect_ratio") or "9:16")
    width, height = (1920, 1080) if aspect == "16:9" else (1080, 1920)
    scenes = []
    captions = []
    cursor = 0.0
    for shot in direction["shot_list"]:
        duration = float(shot["duration"])
        preference = str(shot.get("preferred_renderer") or "auto")
        if preference not in {"auto", "remotion", "hyperframes"}:
            preference = "auto"
        scenes.append({
            "id": shot["id"],
            "duration": duration,
            "purpose": shot["purpose"],
            "visuals": [{
                "media_asset_id": visual_asset_ids[shot["id"]],
                "source_in": 0,
                "fit": "cover",
            }],
            "text": [{
                "text": shot["on_screen_text"],
                "role": "headline",
                "style_token": "marketing.headline",
            }],
            "motion_intent": shot["motion_intent"],
            "constraints": {"safe_area": "short_vertical", "rights_required": True},
            "renderer_policy": {"preference": preference, "fallback": "remotion"},
            "review_rules": ["headline remains readable inside the platform safe area"],
        })
        captions.append({
            "start": round(cursor, 3),
            "end": round(cursor + duration, 3),
            "text": shot["on_screen_text"],
        })
        cursor += duration
    return {
        "version": VIDEO_IR_VERSION,
        "canvas": {"width": width, "height": height, "fps": 30},
        "scenes": scenes,
        "captions": captions,
        "audio": {},
        "review_rules": [
            "playable MP4 is required before the production may enter the draft box",
            "every source visual must carry a durable rights state",
        ],
    }
