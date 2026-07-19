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

from agent.harness import (
    PermanentStepError,
    RetryableStepError,
    StepExecutionContext,
    StepResult,
)
from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.account_context import AccountContextRepository
from agent.marketing.domains.content_assets import ContentAssetRepository
from agent.marketing.domains.content_policy import ContentProductionPolicy
from agent.marketing.domains.evidence import EvidenceRepository
from agent.marketing.domains.knowledge_bases import KnowledgeBaseRepository
from agent.marketing.domains.material_sourcing import MaterialSourcingRepository
from agent.marketing.domains.media_assets import MediaAssetRepository
from agent.marketing.domains.production_audio import ProductionAudioRepository
from agent.marketing.domains.operating_entities import OperatingEntityRepository
from agent.marketing.domains.topic_recommendations import TopicRecommendationRepository
from agent.marketing.domains.video_ir import VIDEO_IR_VERSION
from agent.marketing.domains.video_production import VideoProductionRepository
from agent.marketing.intelligence.production_preflight import (
    create_article_draft_preflight,
    create_content_production_preflight,
    create_video_cut_preflight,
    create_video_treatment_preflight,
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


class MaterialJudge(Protocol):
    """Use one bounded visual model call to rank candidate materials for a shot."""

    def __call__(
        self,
        *,
        shot: dict[str, Any],
        candidates: list[dict[str, Any]],
        aspect_ratio: str,
        task_id: str,
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
        material_judge: MaterialJudge | None = None,
        paths: MarketingDataPaths | None = None,
    ) -> None:
        self.paths = paths or MarketingDataPaths.from_env()
        self.creative = creative_runner
        self.resolve_media = media_resolver
        self.judge_material = material_judge
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
            "video.treatment_preflight": self.preflight_video_treatment,
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
        workflow_input = workflow.get("input") or {}
        selected_platforms = workflow_input.get("selected_platforms")
        brief = _topic_brief(
            candidate,
            selected_platforms=(
                [str(item) for item in selected_platforms]
                if workflow_input.get("explicit_user_platform_override") is True
                and isinstance(selected_platforms, list)
                else None
            ),
        )
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
        entity = OperatingEntityRepository(self.paths).get(
            entity_id=entity_id,
            user_id=user_id,
        )
        evidence_records = EvidenceRepository(self.paths).require_verified_across_accounts(
            user_id=user_id,
            account_ids=list(entity.get("account_ids") or []),
            evidence_ids=list(brief["evidence_refs"]),
            require_any=True,
        )
        brief = {
            **brief,
            "evidence_pack": _evidence_pack_projection(evidence_records),
        }

        article_platforms = self._platforms_for_prefix(context, "article.write.")
        if not article_platforms:
            # Durable v1 workflows used a parent article plus platform adapters.
            article_platforms = self._platforms_for_prefix(context, "article.adapt.")
        video_platforms = self._platforms_for_prefix(context, "video.adapt.")
        if not video_platforms:
            video_platforms = self._platforms_for_prefix(context, "video.direct.")
        lane_orders: dict[str, Any] = {}
        if article_platforms:
            article_orders: dict[str, Any] = {}
            for platform in article_platforms:
                production_target = brief["platform_targets"].get(platform) or {}
                target_account_id = _execution_account_id(
                    brief, platform=platform, fallback_account_id=account_id
                )
                target_context = self._platform_account_context(
                    user_id=user_id,
                    account_id=target_account_id,
                    production_target=production_target,
                )
                article_orders[platform] = self._ensure_lane_order(
                    lane="article",
                    # The legacy article_soft owner requires a parent bundle.
                    # New platform-native drafts intentionally avoid that
                    # schema and use one single-platform campaign order.
                    kind="cross_platform_campaign",
                    platforms=[platform],
                    brief=brief,
                    user_id=user_id,
                    account_id=target_account_id,
                    account_context=target_context,
                    origin_plan=origin_plan,
                )
            lane_orders["article"] = article_orders
        if video_platforms:
            video_orders: dict[str, Any] = {}
            for platform in video_platforms:
                production_target = brief["platform_targets"].get(platform) or {}
                target_account_id = _execution_account_id(
                    brief, platform=platform, fallback_account_id=account_id
                )
                target_context = self._platform_account_context(
                    user_id=user_id,
                    account_id=target_account_id,
                    production_target=production_target,
                )
                video_orders[platform] = self._ensure_lane_order(
                    lane="video",
                    kind="faceless_video",
                    platforms=[platform],
                    brief=brief,
                    user_id=user_id,
                    account_id=target_account_id,
                    account_context=target_context,
                    origin_plan=origin_plan,
                )
            lane_orders["video"] = video_orders
        output = {
            "topic_brief": brief,
            "lane_orders": lane_orders,
            "origin_preflight_id": origin_preflight["id"],
        }
        orders = _flatten_lane_orders(lane_orders)
        artifacts = [
            _artifact("topic_brief", "marketing.topic_candidate", candidate_id),
            *[
                _artifact("production_plan", "content_production_plan", order["plan_id"])
                for order in orders
            ],
            *[
                _artifact("preflight", "marketing_preflight", order["preflight_id"])
                for order in orders
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
        platform = str(context.step["input"].get("platform") or "").strip()
        if platform:
            brief = frozen["topic_brief"]
            order = frozen["lane_orders"]["article"][platform]
            user_id, account_id = self._scope(context, platform=platform)
            production_target = brief["platform_targets"].get(platform) or {}
            account_context = self._platform_account_context(
                user_id=user_id,
                account_id=account_id,
                production_target=production_target,
            )
            knowledge = KnowledgeBaseRepository(self.paths).retrieve_for_preflight(
                user_id=user_id,
                account_id=_personalization_account_id(
                    production_target,
                    fallback_account_id=account_id,
                ),
                platforms=[platform],
                content_kind=str(order["kind"]),
            )
            knowledge = _knowledge_for_production_target(
                knowledge,
                production_target=production_target,
            )
            result = self._creative(
                context,
                role="platform_article_writer",
                instruction=(
                    "Write the final platform-native article or image-text deliverable directly "
                    "from TopicBrief. Do not create a universal parent article and do not adapt a "
                    "draft from another platform. Use the supplied platform mechanism, account "
                    "model and governed knowledge; if the personal model is absent, continue from "
                    "public platform/content priors and mark the basis as cold-start. Use only the "
                    "supplied evidence IDs for factual claims. Return JSON only with: platform, "
                    "format, title, hook, thesis, body_markdown or caption/short_text/thread/"
                    "carousel_cards, claim_evidence_map (array of {claim,evidence_refs}), "
                    "visual_brief, and adaptation_basis containing audience_intent, opening, "
                    "structure, cta. Keep [evidence_xxx] markers beside factual claims."
                ),
                payload={
                    "platform": platform,
                    "platform_profile": self._platform_profile(context, platform),
                    "topic_brief": brief,
                    "account_context": account_context,
                    "knowledge_context": knowledge,
                    "production_target": production_target,
                },
            )
            try:
                article = _normalize_article_deliverable(
                    result,
                    platform=platform,
                    allowed_evidence_refs=set(brief["evidence_refs"]),
                )
            except PermanentStepError as exc:
                # A malformed creative response is not a permanent domain
                # failure. Preserve the failed attempt and let Harness ask the
                # bounded writer again without rebuilding the work order.
                raise RetryableStepError(str(exc)) from exc
            return StepResult(output={"platform": platform, "article": article})

        # Compatibility for durable v1 workflows.
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
        platform = str(context.step["input"].get("platform") or "").strip()
        if platform:
            order = frozen["lane_orders"]["article"][platform]
            article = dict(
                self._output(context, f"article.write.{platform}")["article"]
            )
            user_id, account_id = self._scope(context, platform=platform)
            evaluations: list[dict[str, Any]] = []
            for revision in range(3):
                review = self._creative(
                    context,
                    role="platform_article_reviewer",
                    instruction=(
                        "Review the supplied final platform article itself. Do not reward generic "
                        "prose or assume that another platform's structure is acceptable. Check "
                        "platform-native opening/structure/CTA, claim-to-evidence markers, factual "
                        "traceability, completeness and account fit when account evidence exists. "
                        "Missing personal history lowers account_fit but is not by itself a failure. "
                        "Return JSON only with boolean keys: platform_native, "
                        "factual_claims_traceable, hook_effective, structure_complete, cta_present, "
                        "deliverable_complete; scores object with 0-10 audience_fit, platform_fit, "
                        "account_fit, knowledge_fit, strategy_fit, evidence_strength, hook, emotion, "
                        "structure, viewpoint; and issues array of "
                        "{code,severity,observation,fix}."
                    ),
                    payload={
                        "platform": platform,
                        "platform_profile": self._platform_profile(context, platform),
                        "topic_brief": brief,
                        "article": article,
                    },
                )
                evaluated = create_article_draft_preflight(
                    self.loop,
                    {
                        "user_id": user_id,
                        "account_id": account_id,
                        "session_id": f"{context.attempt_id}:article:{revision}",
                        "plan_id": order["plan_id"],
                        "platform": platform,
                        "article": article,
                        "draft_review": review,
                    },
                )
                evaluations.append(evaluated)
                if evaluated["preflight_decision"].get("go") is True:
                    break
                if revision >= 2:
                    raise PermanentStepError(
                        "platform article failed preflight after two revisions: "
                        + json.dumps(
                            evaluated["preflight_decision"],
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                    )
                revised = self._creative(
                    context,
                    role="platform_article_writer_revision",
                    instruction=(
                        "Rewrite the complete platform-native article to resolve every supplied "
                        "preflight blocker. Preserve TopicBrief meaning, use no evidence outside the "
                        "allowlist, and return the same complete JSON contract as the original "
                        "platform_article_writer."
                    ),
                    payload={
                        "platform": platform,
                        "platform_profile": self._platform_profile(context, platform),
                        "topic_brief": brief,
                        "previous_article": article,
                        "preflight_findings": _bounded_preflight_projection(evaluated),
                    },
                )
                try:
                    article = _normalize_article_deliverable(
                        revised,
                        platform=platform,
                        allowed_evidence_refs=set(brief["evidence_refs"]),
                    )
                except PermanentStepError as exc:
                    raise RetryableStepError(str(exc)) from exc
            approved = evaluations[-1]
            asset = self.content.create_draft(
                user_id=user_id,
                account_id=account_id,
                title=str(article["title"]),
                plan_id=str(order["plan_id"]),
                asset_type="script",
                platform=platform,
                production_kind=str(order["kind"]),
                content={
                    "schema": "marketing.platform_article.v1",
                    "platform": platform,
                    "format": article["format"],
                    "thesis": article["thesis"],
                    "deliverable": article["deliverable"],
                    "claim_evidence_map": article["claim_evidence_map"],
                    "visual_brief": article["visual_brief"],
                    "production_basis": {
                        **article["adaptation_basis"],
                        "production_target": brief["platform_targets"].get(platform)
                        or {},
                    },
                    "draft_preflight": {
                        "preflight_id": approved["preflight_id"],
                        **_bounded_preflight_projection(approved),
                    },
                },
                topic=str(brief["topic"]),
                hook=str(article["hook"]),
                evidence_refs=list(brief["evidence_refs"]),
                reaction_scenarios=[],
            )
            return StepResult(
                output={
                    "platform": platform,
                    "asset_id": asset["id"],
                    "status": asset["status"],
                    "preflight_id": approved["preflight_id"],
                    "revision_count": len(evaluations) - 1,
                },
                artifacts=[
                    *[
                        _artifact(
                            "article_draft_preflight",
                            "marketing_preflight",
                            item["preflight_id"],
                        )
                        for item in evaluations
                    ],
                    _artifact("content_asset", "content_asset", asset["id"]),
                ],
            )

        # Compatibility for durable v1 workflows.
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
        brief = frozen["topic_brief"]
        platform = str(context.step["input"].get("platform") or "").strip()
        if not platform:
            # Durable v1 workflows may still be resumed after the v2 rollout.
            legacy_platforms = context.step["input"].get("platforms") or []
            platform = str(legacy_platforms[0] if legacy_platforms else brief["target_platforms"][0])
        user_id, account_id = self._scope(context, platform=platform)
        production_target = brief["platform_targets"].get(platform) or {}
        account_context = self._platform_account_context(
            user_id=user_id,
            account_id=account_id,
            production_target=production_target,
        )
        knowledge = KnowledgeBaseRepository(self.paths).retrieve_for_preflight(
            user_id=user_id,
            account_id=_personalization_account_id(
                production_target,
                fallback_account_id=account_id,
            ),
            platforms=[platform],
            content_kind="faceless_video",
        )
        knowledge = _knowledge_for_production_target(
            knowledge,
            production_target=production_target,
        )
        result = self._creative(
            context,
            role="platform_video_showrunner",
            instruction=(
                "Act as the platform-native short-video showrunner. Plan independently from every "
                "article branch and never request an article script. Use the supplied account model "
                "when available; otherwise keep working from explicit public platform, market and "
                "content priors and mark the plan as cold-start. Return JSON only with: platform, "
                "format, title, thesis, audience_promise, hook, hook_hypothesis "
                "({first_three_seconds,tension,payoff}), aspect_ratio, target_duration, pacing, "
                "caption_style, cta, voiceover_script, beat_sheet (array), claim_evidence_map "
                "(array of {claim,evidence_refs}), sound_strategy "
                "({voice_style,music_role,sfx_cues}), and shot_list. shot_list must contain 2-12 "
                "objects with id, duration, purpose, narration, visual_query, media_type, "
                "on_screen_text, evidence_refs, motion_intent, and preferred_renderer. Each "
                "visual_query must be a concise English stock-media search phrase. Use only evidence "
                "IDs supplied by TopicBrief. The durations must add up to target_duration."
            ),
            payload={
                "platform": platform,
                "platform_profile": self._platform_profile(context, platform),
                "topic_brief": brief,
                "account_context": account_context,
                "knowledge_context": knowledge,
                "production_target": production_target,
            },
        )
        try:
            treatment = _normalize_video_treatment(
                result,
                platform=platform,
                allowed_evidence_refs=set(brief["evidence_refs"]),
            )
        except PermanentStepError as exc:
            # JSON can be syntactically valid while missing one semantic field.
            # That is a retryable model-contract miss, not a terminal workflow
            # failure. Native evidence/preflight owners still fail closed.
            raise RetryableStepError(str(exc)) from exc
        return StepResult(
            output={
                "platform": platform,
                "video_treatment": treatment,
                # Compatibility projection for already-rendered UI/readers.
                "video_direction": treatment,
            }
        )

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

    def preflight_video_treatment(self, context: StepExecutionContext) -> StepResult:
        """Run plan-level simulation and at most two bounded showrunner revisions."""

        frozen = self._output(context, "topic_brief.freeze")
        brief = frozen["topic_brief"]
        platform = str(context.step["input"].get("platform") or "").strip()
        directed = self._output(context, f"video.direct.{platform}")
        treatment = dict(directed["video_treatment"])
        user_id, account_id = self._scope(context, platform=platform)
        order = frozen["lane_orders"]["video"][platform]
        production_target = brief["platform_targets"].get(platform) or {}
        account_context = self._platform_account_context(
            user_id=user_id,
            account_id=account_id,
            production_target=production_target,
        )
        knowledge = KnowledgeBaseRepository(self.paths).retrieve_for_preflight(
            user_id=user_id,
            account_id=_personalization_account_id(
                production_target,
                fallback_account_id=account_id,
            ),
            platforms=[platform],
            content_kind="faceless_video",
        )
        knowledge = _knowledge_for_production_target(
            knowledge,
            production_target=production_target,
        )
        evaluations: list[dict[str, Any]] = []
        for revision in range(3):
            evaluated = create_video_treatment_preflight(
                self.loop,
                {
                    "user_id": user_id,
                    "account_id": account_id,
                    "session_id": f"{context.attempt_id}:treatment:{revision}",
                    "plan_id": order["plan_id"],
                    "platform": platform,
                    "treatment": treatment,
                    "evidence_refs": list(brief["evidence_refs"]),
                    "knowledge_context": knowledge,
                    "account_context": account_context,
                },
            )
            evaluations.append(evaluated)
            if evaluated["preflight_decision"].get("go") is True:
                return StepResult(
                    output={
                        "platform": platform,
                        "approved_treatment": treatment,
                        "preflight_id": evaluated["preflight_id"],
                        "preflight": _bounded_preflight_projection(evaluated),
                        "revision_count": revision,
                    },
                    artifacts=[
                        _artifact(
                            "treatment_preflight",
                            "marketing_preflight",
                            item["preflight_id"],
                        )
                        for item in evaluations
                    ],
                )
            if revision >= 2:
                break
            revised = self._creative(
                context,
                role="platform_video_showrunner_revision",
                instruction=(
                    "Revise the supplied platform-native VideoTreatment to resolve every preflight "
                    "blocker without changing the TopicBrief's factual meaning or inventing evidence. "
                    "Return the complete replacement treatment using exactly the same JSON contract "
                    "as the original showrunner output. Durations must add up exactly."
                ),
                payload={
                    "platform": platform,
                    "topic_brief": brief,
                    "platform_profile": self._platform_profile(context, platform),
                    "account_context": account_context,
                    "knowledge_context": knowledge,
                    "previous_treatment": treatment,
                    "preflight_findings": _bounded_preflight_projection(evaluated),
                },
            )
            try:
                treatment = _normalize_video_treatment(
                    revised,
                    platform=platform,
                    allowed_evidence_refs=set(brief["evidence_refs"]),
                )
            except PermanentStepError as exc:
                raise RetryableStepError(str(exc)) from exc
        final = evaluations[-1]
        raise PermanentStepError(
            "video treatment failed preflight after two revisions: "
            + json.dumps(
                final["preflight_decision"], ensure_ascii=False, sort_keys=True
            )
        )

    def search_video_materials(self, context: StepExecutionContext) -> StepResult:
        platform = str(context.step["input"].get("platform") or "").strip()
        direction = self._approved_treatment(context, platform=platform)
        user_id, account_id = self._scope(context, platform=platform)
        orientation = "landscape" if direction.get("aspect_ratio") == "16:9" else "portrait"
        searches: list[dict[str, Any]] = []
        selected: dict[str, str] = {}
        reusable_assets: list[str] = []
        asset_use_counts: dict[str, int] = {}
        used_provider_assets: set[tuple[str, str]] = set()
        skill_resolutions: list[dict[str, Any]] = []
        material_reviews: list[dict[str, Any]] = []
        visual_layouts: dict[str, dict[str, str]] = {}
        resolver_errors: list[str] = []
        unresolved: list[str] = []
        distinct_target = max(1, (len(direction["shot_list"]) + 1) // 2)
        for shot in direction["shot_list"]:
            search_attempts: list[dict[str, Any]] = []
            candidates_by_source: dict[tuple[str, str], dict[str, Any]] = {}
            # Commons and other documentary sources respond much better to
            # compact concepts than to stock-site prompt prose. Keep the
            # original query as evidence, then broaden every shot independently.
            queries = [str(shot["visual_query"])]
            queries.extend(_broad_material_queries(str(shot["visual_query"])))
            for query_index, query in enumerate(dict.fromkeys(queries)):
                search = self.materials.search(
                    user_id=user_id,
                    account_id=account_id,
                    query=query,
                    role="broll",
                    orientation=orientation,
                    # The showrunner's media_type is a preference, not a hard
                    # rights/source constraint. A relevant licensed still is a
                    # valid fallback for a motion-composed shot when no clip is
                    # available, and avoids hammering providers with a second
                    # search for the same concept.
                    media_type="either",
                    target_duration=float(shot["duration"]),
                    limit=8,
                    request_ref=(
                        f"{context.workflow['id']}:video-v5:{platform or 'legacy'}:"
                        f"{shot['id']}:{query_index}:{context.attempt_id}"
                    ),
                )
                search_attempts.append(search)
                for candidate in search.get("candidates") or []:
                    source_key = (
                        str(candidate.get("provider") or ""),
                        str(candidate.get("provider_asset_id") or candidate.get("id") or ""),
                    )
                    if all(source_key):
                        candidates_by_source.setdefault(source_key, candidate)
            candidates = list(candidates_by_source.values())
            judge = getattr(self, "judge_material", None)
            review_by_id: dict[str, dict[str, Any]] = {}
            reviewed_candidates: list[dict[str, Any]] | None = None
            reviewable = [
                item
                for item in sorted(
                    candidates,
                    key=lambda candidate: -float(candidate.get("score") or 0),
                )
                if str(item.get("preview_url") or "").strip()
                and (
                    item.get("provider") == "user_library"
                    or (
                        item.get("license_name")
                        and item.get("license_url")
                        and item.get("source_url")
                    )
                )
            ][:6]
            if judge is not None and reviewable:
                try:
                    review = _normalize_material_judgment(
                        judge(
                            shot=shot,
                            candidates=[
                                _material_candidate_projection(item)
                                for item in reviewable
                            ],
                            aspect_ratio=str(direction.get("aspect_ratio") or "9:16"),
                            task_id=context.attempt_id,
                        ),
                        allowed_candidate_ids={str(item["id"]) for item in reviewable},
                    )
                except Exception as exc:
                    raise RetryableStepError(
                        f"visual material judge failed for {shot['id']}: {exc}",
                        delay_seconds=1,
                    ) from exc
                material_reviews.append({"shot_id": shot["id"], **review})
                review_by_id = {
                    str(item["candidate_id"]): item
                    for item in review["ranked_candidates"]
                }
                reviewed_candidates = [
                    next(
                        item
                        for item in reviewable
                        if str(item["id"]) == candidate_id
                    )
                    for candidate_id in review["accepted_candidate_ids"]
                ]
            elif judge is not None:
                reviewed_candidates = []
                resolver_errors.append(
                    f"{shot['id']}: no previewable candidate reached the visual relevance gate"
                )

            selection_pool = candidates if reviewed_candidates is None else reviewed_candidates
            owned = next(
                (
                    item for item in selection_pool
                    if item.get("provider") == "user_library"
                    and (
                        str(item.get("provider") or ""),
                        str(item.get("provider_asset_id") or item.get("id") or ""),
                    )
                    not in used_provider_assets
                ),
                None,
            )
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
                    asset_use_counts[selected[str(shot["id"])]] = 1
                used_provider_assets.add(
                    (str(owned.get("provider") or ""), str(owned.get("provider_asset_id") or owned["id"]))
                )
                visual_layouts[str(shot["id"])] = _review_layout(
                    review_by_id.get(str(owned["id"]))
                )
            # Official/search providers are the second tier. Their candidate
            # records already carry a durable source URL, creator and licence
            # URL. For a reversible local preview the workflow may freeze the
            # top result automatically; publication still has its own rights
            # gate for people/property/trademark context.
            licensed_candidates = [
                item
                for item in selection_pool
                if item.get("provider") != "user_library"
                and (
                    str(item.get("provider") or ""),
                    str(item.get("provider_asset_id") or item.get("id") or ""),
                )
                not in used_provider_assets
                and item.get("license_name")
                and item.get("license_url")
                and item.get("source_url")
            ]
            for licensed in licensed_candidates:
                if str(shot["id"]) in selected:
                    break
                try:
                    materialized = self.materials.materialize(
                        candidate_id=str(licensed["id"]),
                        user_id=user_id,
                        account_id=account_id,
                        rights_reviewed=True,
                    )
                except Exception as exc:
                    resolver_errors.append(
                        f"{shot['id']}/{licensed.get('provider')}: {exc}"
                    )
                    continue
                selected[str(shot["id"])] = str(materialized["asset"]["id"])
                if selected[str(shot["id"])] not in reusable_assets:
                    reusable_assets.append(selected[str(shot["id"])])
                    asset_use_counts[selected[str(shot["id"])]] = 1
                used_provider_assets.add(
                    (
                        str(licensed.get("provider") or ""),
                        str(licensed.get("provider_asset_id") or licensed["id"]),
                    )
                )
                visual_layouts[str(shot["id"])] = _review_layout(
                    review_by_id.get(str(licensed["id"]))
                )
            if str(shot["id"]) not in selected:
                try:
                    requested_media_type = str(shot.get("media_type") or "either")
                    resolve_types = (
                        ["image"]
                        if requested_media_type == "image"
                        else ["video", "image"]
                    )
                    resolved: dict[str, Any] | None = None
                    resolution_failures: list[str] = []
                    for resolve_type in resolve_types:
                        try:
                            resolved = self.resolve_media(
                                intent=str(shot["visual_query"]),
                                media_type=resolve_type,
                                task_id=context.attempt_id,
                            )
                            break
                        except Exception as exc:
                            resolution_failures.append(f"{resolve_type}: {exc}")
                    if resolved is None:
                        raise RuntimeError("; ".join(resolution_failures))
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
                    resolved_mime = str(resolved.get("mime_type") or "")
                    resolved_media_type = (
                        "image" if resolved_mime.startswith("image/") else "video"
                    )
                    resolved_review: dict[str, Any] | None = None
                    if judge is not None:
                        resolved_candidate_id = f"skill:{shot['id']}"
                        resolved_review = _normalize_material_judgment(
                            judge(
                                shot=shot,
                                candidates=[{
                                    "id": resolved_candidate_id,
                                    "provider": f"skill:{provider}",
                                    "media_type": resolved_media_type,
                                    "preview_url": str(resolved_path),
                                    "source_url": str(provenance.get("source_url") or ""),
                                    "width": 0,
                                    "height": 0,
                                    "description": str(
                                        resolved.get("description") or shot["visual_query"]
                                    )[:500],
                                }],
                                aspect_ratio=str(direction.get("aspect_ratio") or "9:16"),
                                task_id=context.attempt_id,
                            ),
                            allowed_candidate_ids={resolved_candidate_id},
                        )
                        material_reviews.append({
                            "shot_id": shot["id"],
                            "source": "media_skill",
                            **resolved_review,
                        })
                        if not resolved_review["accepted_candidate_ids"]:
                            raise RuntimeError(
                                "media skill result failed visual relevance gate"
                            )
                    asset = self.media.import_generated_file(
                        user_id=user_id,
                        account_id=account_id,
                        name=str(resolved.get("description") or shot["visual_query"]),
                        media_type=resolved_media_type,
                        role="broll",
                        path=Path(str(resolved_path)),
                        mime_type=resolved_mime
                        or ("image/jpeg" if resolved_media_type == "image" else "video/mp4"),
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
                    asset_id = str(asset["id"])
                    if asset_id in reusable_assets:
                        resolver_errors.append(
                            f"{shot['id']}: media skill returned a duplicate frozen asset"
                        )
                    else:
                        selected[str(shot["id"])] = asset_id
                        visual_layouts[str(shot["id"])] = _review_layout(
                            (
                                resolved_review["ranked_candidates"][0]
                                if resolved_review is not None
                                else None
                            )
                        )
                        reusable_assets.append(asset_id)
                        asset_use_counts[asset_id] = 1
                        skill_resolutions.append({
                            "shot_id": shot["id"],
                            "asset_id": asset_id,
                            "resolver_id": resolved.get("id"),
                            "source": source,
                        })
                except Exception as exc:
                    resolver_errors.append(f"{shot['id']}: {exc}")
            if str(shot["id"]) not in selected:
                unresolved.append(str(shot["id"]))
            searches.append({
                "shot_id": shot["id"],
                "search_id": search_attempts[-1]["id"],
                "search_ids": [item["id"] for item in search_attempts],
                "candidate_count": len(candidates),
                "requested_media_type": str(shot.get("media_type") or "either"),
                "selected_asset_id": selected.get(str(shot["id"])),
                "external_candidates_require_rights_review": sum(
                    1 for item in candidates if item.get("provider") != "user_library"
                ),
            })
        if len(reusable_assets) >= distinct_target:
            for shot_id in unresolved:
                available = [
                    asset_id
                    for asset_id in reusable_assets
                    if asset_use_counts.get(asset_id, 0) < 2
                ]
                if not available:
                    break
                asset_id = min(available, key=lambda item: asset_use_counts.get(item, 0))
                selected[shot_id] = asset_id
                visual_layouts[shot_id] = _review_layout(None)
                asset_use_counts[asset_id] = asset_use_counts.get(asset_id, 0) + 1
                next(
                    item.update({"selected_asset_id": asset_id, "reused": True})
                    for item in searches
                    if item["shot_id"] == shot_id
                )
        missing = [
            str(shot["id"])
            for shot in direction["shot_list"]
            if str(shot["id"]) not in selected
        ]
        if missing:
            message = (
                "material diversity gate blocked rendering; "
                f"required_unique={distinct_target}; resolved_unique={len(reusable_assets)}; "
                f"missing={missing}; errors={resolver_errors}"
            )
            transient_markers = (
                "429",
                "timed out",
                "timeout",
                "handshake",
                "temporarily",
                "connection reset",
                "remote disconnected",
            )
            if any(
                marker in str(error).lower()
                for error in resolver_errors
                for marker in transient_markers
            ):
                raise RetryableStepError(message, delay_seconds=2)
            raise PermanentStepError(message)
        return StepResult(
            output={
                "platform": platform or None,
                "searches": searches,
                "selected_assets": selected,
                "visual_layouts": visual_layouts,
                "material_reviews": material_reviews,
                "diversity": {
                    "minimum_unique_assets": distinct_target,
                    "unique_assets": len(reusable_assets),
                    "maximum_uses_per_asset": 2,
                },
                "skill_resolutions": skill_resolutions,
            },
            artifacts=[
                _artifact("material_search", "material_search", search_id)
                for item in searches
                for search_id in item["search_ids"]
            ],
            receipts=[{
                "kind": "material.search",
                "idempotency_key": f"material-search:{context.workflow['id']}:{platform or 'legacy'}",
                "input": {
                    "platform": platform or None,
                    "orientation": orientation,
                    "shot_count": len(direction["shot_list"]),
                },
                "output": {
                    "search_ids": [item["search_id"] for item in searches],
                    "skill_resolutions": skill_resolutions,
                },
            }],
        )


    def plan_video_audio(self, context: StepExecutionContext) -> StepResult:
        platform = str(context.step["input"].get("platform") or "").strip()
        direction = self._approved_treatment(context, platform=platform)
        user_id, account_id = self._scope(context, platform=platform)
        sound_strategy = (
            direction.get("sound_strategy")
            if isinstance(direction.get("sound_strategy"), dict)
            else {}
        )
        job = self.audio.prepare_voice(
            user_id=user_id,
            account_id=account_id,
            name=f"{direction['title']} · {platform or '视频'} 旁白",
            script_text=str(direction["voiceover_script"])[:4000],
        )
        automatic = (
            (context.workflow.get("policy") or {}).get(
                "automatic_voiceover_authorized"
            )
            is True
        )
        if automatic and job.get("status") != "completed":
            job = self.audio.approve(
                job_id=str(job["id"]),
                user_id=user_id,
                account_id=account_id,
                approval_ref="user-config:marketing.video.auto_voiceover",
                confirmed_by_user=True,
            )
            try:
                job = self.audio.execute(
                    job_id=str(job["id"]),
                    user_id=user_id,
                    account_id=account_id,
                )
            except (OSError, RuntimeError) as exc:
                # Cloud TTS may end a chunked response before its terminal
                # event. The audio repository already records the provider
                # failure and resets the same idempotent job on approval; ask
                # Harness to retry that job instead of terminating the video.
                raise RetryableStepError(str(exc), delay_seconds=1) from exc
        voice_asset_id = str(job.get("output_asset_id") or "").strip() or None
        artifacts = [_artifact("audio_job", "marketing_audio_job", job["id"])]
        if voice_asset_id:
            artifacts.append(_artifact("voiceover", "media_asset", voice_asset_id))
        output = {
            "voice_job_id": job["id"],
            "voice_status": job["status"],
            "draft_mix": "voiceover" if voice_asset_id else "captions_only",
            "render_voice_asset_id": voice_asset_id,
        }
        if platform:
            output.update({"platform": platform, "sound_strategy": sound_strategy})
        return StepResult(output=output, artifacts=artifacts)

    def previsualize_video(self, context: StepExecutionContext) -> StepResult:
        frozen = self._output(context, "topic_brief.freeze")
        brief = frozen["topic_brief"]
        platform = str(context.step["input"].get("platform") or "")
        order = frozen["lane_orders"]["video"][platform]
        treatment_preflight = self._output(context, f"video.preflight.{platform}")
        direction = treatment_preflight["approved_treatment"]
        materials = self._output(context, f"video.material.{platform}")
        audio = self._output(context, f"video.audio.{platform}")
        user_id, account_id = self._scope(context, platform=platform)

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
                "schema": "marketing.faceless_video.v3",
                "video_treatment": direction,
                "video_direction": direction,
                "platform_plan": _platform_plan_projection(direction),
                "production_target": brief["platform_targets"].get(platform) or {},
                "treatment_preflight": {
                    "preflight_id": treatment_preflight["preflight_id"],
                    **treatment_preflight["preflight"],
                },
                "material_manifest": {"searches": materials["searches"], "asset_ids": list(visuals.values())},
                "sound_strategy": audio.get("sound_strategy") or {},
                "sound_plan": {
                    "mode": "original_voice_only",
                    "mix_role": "voice_first" if audio["render_voice_asset_id"] else "captions_first_preview",
                    "opening_cue_ms": 0,
                    "voice_required": bool(audio["render_voice_asset_id"]),
                    "voice_job_id": audio["voice_job_id"],
                    "voice_status": audio["voice_status"],
                },
                "voiceover_script": direction["voiceover_script"],
            },
            topic=str(brief["topic"]),
            hook=str(direction["hook"]),
            evidence_refs=list(brief["evidence_refs"]),
            reaction_scenarios=[],
        )
        video_ir = _video_ir(
            treatment=direction,
            visual_asset_ids=visuals,
            visual_layouts=dict(materials.get("visual_layouts") or {}),
            voice_asset_id=audio["render_voice_asset_id"],
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
        user_id, account_id = self._scope(context, platform=platform)
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
        user_id, account_id = self._scope(context, platform=platform)
        production = self.video.get(
            production_id=str(rendered["production_id"]),
            user_id=user_id,
            account_id=account_id,
        )
        quality = (((production.get("receipt") or {}).get("summary") or {}).get("technical") or {}).get("quality_assurance")
        if production.get("status") != "completed":
            raise PermanentStepError("video QA requires a completed production")
        if not isinstance(quality, dict):
            raise PermanentStepError("video QA has no deterministic technical report")
        final_path = self.media.resolve_local_path(
            asset_id=str(rendered["final_video_asset_id"]),
            user_id=user_id,
        )
        if not final_path:
            raise PermanentStepError("video QA cannot resolve the rendered local file")
        treatment = self._approved_treatment(context, platform=platform)
        visual_review = self._creative(
            context,
            role="platform_video_cut_reviewer",
            instruction=(
                "You are the cut reviewer, not the renderer and not the showrunner. Judge the "
                "observed sampled frames of the final cut itself; do not infer "
                "success from filenames, treatment JSON, or render receipts. Check the first three "
                "seconds, representative middle transitions, captions, material relevance, ending "
                "CTA, and audio when the analysis evidence includes audio. Return JSON only with "
                "boolean keys: playable, hook_first_three_seconds_visible, treatment_parity, "
                "caption_readability, material_relevance, evidence_alignment, audio_present, "
                "audio_sync, ending_cta_present; scores object with 0-10 audience_fit, platform_fit, "
                "account_fit, emotional_pull, pacing, information_density, evidence_alignment; "
                "and issues array of {code,severity,at_seconds,observation,fix}. Never claim exact "
                "view counts. If audio was not observable, set audio fields false and explain why."
            ),
            payload={
                "platform": platform,
                "final_video_path": final_path,
                "approved_treatment": treatment,
                "technical_qa": quality,
            },
            toolsets=("video",),
        )
        frozen = self._output(context, "topic_brief.freeze")
        order = frozen["lane_orders"]["video"][platform]
        cut_preflight = create_video_cut_preflight(
            self.loop,
            {
                "user_id": user_id,
                "account_id": account_id,
                "session_id": f"{context.attempt_id}:cut-review",
                "plan_id": order["plan_id"],
                "platform": platform,
                "treatment": treatment,
                "visual_review": visual_review,
                "technical_qa": quality,
                "audio_expected": bool((production.get("edl") or {}).get("voice_asset_id")),
                "final_video_asset_id": rendered["final_video_asset_id"],
            },
        )
        if cut_preflight["preflight_decision"].get("go") is not True:
            raise PermanentStepError(
                "rendered cut failed canonical cut preflight: "
                + json.dumps(
                    cut_preflight["preflight_decision"],
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        return StepResult(
            output={
                **rendered,
                "qa": {
                    "technical": quality,
                    "visual": visual_review,
                    "preflight": _bounded_preflight_projection(cut_preflight),
                },
                "cut_preflight_id": cut_preflight["preflight_id"],
            },
            artifacts=[
                _artifact(
                    "cut_preflight",
                    "marketing_preflight",
                    cut_preflight["preflight_id"],
                )
            ],
            receipts=[
                {
                    "kind": "video.cut_review",
                    "idempotency_key": f"video-cut-review:{production['id']}",
                    "input": {
                        "production_id": production["id"],
                        "final_video_asset_id": rendered["final_video_asset_id"],
                    },
                    "output": {
                        "cut_preflight_id": cut_preflight["preflight_id"],
                        "status": cut_preflight["status"],
                    },
                }
            ],
        )

    def settle_draft_branch(self, context: StepExecutionContext) -> StepResult:
        lane = str(context.step["input"].get("lane") or "")
        if lane == "article":
            refs = [
                {
                    "object_id": step["output"]["asset_id"],
                    "object_type": "content_asset",
                    "title": f"{step['output']['platform']} 图文草稿",
                }
                for step in context.workflow["steps"]
                if step["key"].startswith("article.qa.")
                and step["state"] == "succeeded"
            ]
            if not refs:
                article = self._output(context, "article.qa")
                refs = [
                    {
                        "object_id": article["asset_id"],
                        "object_type": "content_asset",
                        "title": "图文草稿",
                    }
                ]
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
            "kind": saved["kind"],
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

    def _approved_treatment(
        self, context: StepExecutionContext, *, platform: str
    ) -> dict[str, Any]:
        if platform:
            try:
                return dict(
                    self._output(context, f"video.preflight.{platform}")[
                        "approved_treatment"
                    ]
                )
            except KeyError:
                try:
                    directed = self._output(context, f"video.direct.{platform}")
                    return dict(
                        directed.get("video_treatment")
                        or directed["video_direction"]
                    )
                except KeyError:
                    pass
        # Compatibility for v1 workflows and focused unit tests.
        legacy = self._output(context, "video.direct")
        return dict(legacy.get("video_treatment") or legacy["video_direction"])

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

    def _scope(
        self, context: StepExecutionContext, *, platform: str = ""
    ) -> tuple[str, str]:
        user_id = str(context.workflow["owner_user_id"])
        fallback = str(
            (context.workflow.get("input") or {}).get("account_id") or ""
        )
        if not platform:
            return user_id, fallback
        try:
            brief = self._output(context, "topic_brief.freeze")["topic_brief"]
        except KeyError:
            return user_id, fallback
        return user_id, _execution_account_id(
            brief, platform=platform, fallback_account_id=fallback
        )

    def _platform_account_context(
        self,
        *,
        user_id: str,
        account_id: str,
        production_target: dict[str, Any],
    ) -> dict[str, Any]:
        """Keep compatibility execution ownership separate from personalization."""

        if production_target.get("personalization_available") is not True:
            return {
                "account_id": account_id,
                "connected": False,
                "personalization_available": False,
                "binding_status": production_target.get("binding_status"),
            }
        personalization_account_id = _personalization_account_id(
            production_target,
            fallback_account_id=account_id,
        )
        target_context = AccountContextRepository(self.paths).read(
            user_id=user_id,
            account_id=personalization_account_id,
        )
        return {
            **target_context,
            # Until every repository is entity-first, plans/preflights/assets
            # must share the TopicOrder's compatibility storage owner. The
            # real platform account remains explicit modelling/effect context.
            "account_id": account_id,
            # The plan's compatibility account is not the publish target.
            # Keep publish eligibility fail-closed until the publish effect
            # explicitly consumes target_account_id.
            "connected": False,
            "target_connected": target_context.get("connected") is True,
            "execution_account_id": account_id,
            "target_account_id": personalization_account_id,
            "target_account": target_context.get("account") or {},
            "personalization_available": True,
            "binding_status": production_target.get("binding_status"),
        }


def build_topic_production_handlers(
    *,
    creative_runner: CreativeRunner,
    media_resolver: MediaResolver,
    material_judge: MaterialJudge | None = None,
    paths: MarketingDataPaths | None = None,
) -> dict[str, Callable[[StepExecutionContext], StepResult]]:
    return TopicProductionWorkers(
        creative_runner=creative_runner,
        media_resolver=media_resolver,
        material_judge=material_judge,
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


def _normalize_article_deliverable(
    value: Any,
    *,
    platform: str,
    allowed_evidence_refs: set[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PermanentStepError("platform article deliverable must be an object")
    supplied_platform = str(value.get("platform") or platform).strip()
    if supplied_platform != platform:
        raise PermanentStepError("platform article does not match its work order")
    for field in ("format", "title", "hook", "thesis"):
        _required_text(value.get(field), field)
    _validate_variant(value, platform=platform)
    deliverable_fields = (
        "body_markdown",
        "caption",
        "short_text",
        "thread",
        "carousel_cards",
    )
    deliverable = {
        field: value[field]
        for field in deliverable_fields
        if value.get(field) not in (None, "", [])
    }
    claims = value.get("claim_evidence_map")
    if not isinstance(claims, list) or not claims:
        raise PermanentStepError("platform article requires claim_evidence_map")
    normalized_claims: list[dict[str, Any]] = []
    for raw in claims[:100]:
        if not isinstance(raw, dict):
            raise PermanentStepError("article claim evidence mapping must be an object")
        refs = _evidence_refs(raw.get("evidence_refs") or raw.get("evidence_ref"))
        if not refs:
            raise PermanentStepError(
                "every article claim must reference verified TopicBrief evidence"
            )
        unknown = sorted(set(refs) - allowed_evidence_refs)
        if unknown:
            raise PermanentStepError(
                "platform article references evidence outside TopicBrief: "
                + ", ".join(unknown)
            )
        normalized_claims.append(
            {
                "claim": _required_text(raw.get("claim"), "claim")[:2000],
                "evidence_refs": refs,
            }
        )
    return {
        "schema": "marketing.platform_article_treatment.v1",
        "platform": platform,
        "format": str(value["format"]).strip()[:120],
        "title": str(value["title"]).strip()[:300],
        "hook": str(value["hook"]).strip()[:1000],
        "thesis": str(value["thesis"]).strip()[:2000],
        "deliverable": deliverable,
        "claim_evidence_map": normalized_claims,
        "visual_brief": (
            value.get("visual_brief")
            if isinstance(value.get("visual_brief"), dict)
            else {}
        ),
        "adaptation_basis": dict(value["adaptation_basis"]),
    }


def _normalize_video_treatment(
    value: Any,
    *,
    platform: str,
    allowed_evidence_refs: set[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PermanentStepError("video treatment must be an object")
    supplied_platform = str(value.get("platform") or platform).strip()
    if supplied_platform != platform:
        raise PermanentStepError("video treatment platform does not match its work order")
    for field in (
        "format",
        "title",
        "thesis",
        "audience_promise",
        "hook",
        "aspect_ratio",
        "pacing",
        "caption_style",
        "cta",
        "voiceover_script",
    ):
        _required_text(value.get(field), field)
    aspect = str(value.get("aspect_ratio") or "").strip()
    if aspect not in {"9:16", "16:9", "1:1", "4:5"}:
        raise PermanentStepError("video treatment aspect_ratio is unsupported")
    try:
        target_duration = max(3.0, min(float(value.get("target_duration")), 600.0))
    except (TypeError, ValueError) as exc:
        raise PermanentStepError("video treatment target_duration is invalid") from exc
    hook_hypothesis = (
        value.get("hook_hypothesis")
        if isinstance(value.get("hook_hypothesis"), dict)
        else {}
    )
    first_three_seconds = _required_text(
        hook_hypothesis.get("first_three_seconds")
        or hook_hypothesis.get("first_3_seconds"),
        "hook_hypothesis.first_three_seconds",
    )
    beats = value.get("beat_sheet")
    if not isinstance(beats, list) or not beats:
        raise PermanentStepError("video treatment beat_sheet must be a non-empty array")
    normalized_beats: list[dict[str, Any]] = []
    for index, beat in enumerate(beats[:30]):
        if not isinstance(beat, dict):
            raise PermanentStepError("video treatment beat must be an object")
        normalized_beats.append(
            {
                "id": str(beat.get("id") or f"beat_{index + 1:02d}")[:120],
                "purpose": _required_text(
                    beat.get("purpose")
                    or beat.get("summary")
                    or beat.get("description")
                    or beat.get("title")
                    or beat.get("beat")
                    or beat.get("step")
                    or beat.get("phase"),
                    "beat purpose",
                )[:1000],
                "payoff": str(beat.get("payoff") or "").strip()[:1000],
            }
        )
    claim_map = value.get("claim_evidence_map")
    if not isinstance(claim_map, list) or not claim_map:
        raise PermanentStepError(
            "video treatment claim_evidence_map must be a non-empty array"
        )
    normalized_claims: list[dict[str, Any]] = []
    for raw in claim_map[:100]:
        if not isinstance(raw, dict):
            raise PermanentStepError("claim evidence mapping must be an object")
        refs = _evidence_refs(raw.get("evidence_refs") or raw.get("evidence_ref"))
        if not refs:
            raise PermanentStepError(
                "every video treatment claim must reference verified TopicBrief evidence"
            )
        unknown = sorted(set(refs) - allowed_evidence_refs)
        if unknown:
            raise PermanentStepError(
                "video treatment references evidence outside TopicBrief: "
                + ", ".join(unknown)
            )
        normalized_claims.append(
            {
                "claim": _required_text(raw.get("claim"), "claim")[:2000],
                "evidence_refs": refs,
            }
        )
    shots = value.get("shot_list")
    if not isinstance(shots, list) or not 2 <= len(shots) <= 12:
        raise PermanentStepError("video treatment requires 2-12 shots")
    normalized_shots = [
        _normalize_shot(item, index, allowed_evidence_refs=allowed_evidence_refs)
        for index, item in enumerate(shots)
    ]
    sound_strategy = (
        value.get("sound_strategy")
        if isinstance(value.get("sound_strategy"), dict)
        else {}
    )
    return {
        "schema": "marketing.platform_video_treatment.v1",
        "platform": platform,
        "format": str(value["format"]).strip()[:120],
        "title": str(value["title"]).strip()[:300],
        "thesis": str(value["thesis"]).strip()[:2000],
        "audience_promise": str(value["audience_promise"]).strip()[:1000],
        "hook": str(value["hook"]).strip()[:1000],
        "hook_hypothesis": {
            "first_three_seconds": first_three_seconds[:1000],
            "tension": str(hook_hypothesis.get("tension") or "").strip()[:1000],
            "payoff": str(hook_hypothesis.get("payoff") or "").strip()[:1000],
        },
        "aspect_ratio": aspect,
        "target_duration": round(target_duration, 3),
        "pacing": str(value["pacing"]).strip()[:1000],
        "caption_style": str(value["caption_style"]).strip()[:1000],
        "cta": str(value["cta"]).strip()[:1000],
        "voiceover_script": str(value["voiceover_script"]).strip()[:12_000],
        "beat_sheet": normalized_beats,
        "claim_evidence_map": normalized_claims,
        "sound_strategy": {
            "voice_style": str(sound_strategy.get("voice_style") or "").strip()[:500],
            "music_role": str(sound_strategy.get("music_role") or "").strip()[:500],
            "sfx_cues": [
                str(item).strip()[:300]
                for item in (sound_strategy.get("sfx_cues") or [])[:30]
                if str(item).strip()
            ],
        },
        "shot_list": normalized_shots,
    }


def _normalize_shot(
    value: Any,
    index: int,
    *,
    allowed_evidence_refs: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PermanentStepError("video shot must be an object")
    shot_id = str(value.get("id") or f"scene_{index + 1:03d}").strip()[:120]
    try:
        duration = max(1.2, min(float(value.get("duration") or 3.0), 12.0))
    except (TypeError, ValueError) as exc:
        raise PermanentStepError("video shot duration is invalid") from exc
    motion = value.get("motion_intent") or ["kinetic_typography"]
    if isinstance(motion, str):
        # A one-item enum array is often collapsed to the enum string by a
        # creative model. The semantic value is unambiguous, so canonicalize it
        # instead of wasting a durable workflow attempt.
        motion = [motion]
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
    refs = _evidence_refs(value.get("evidence_refs") or value.get("evidence_ref"))
    unknown = sorted(set(refs) - set(allowed_evidence_refs or refs))
    if unknown:
        raise PermanentStepError(
            "video shot references evidence outside TopicBrief: " + ", ".join(unknown)
        )
    return {
        "id": shot_id,
        "duration": round(duration, 3),
        "purpose": _required_text(value.get("purpose"), "shot purpose")[:1000],
        "visual_query": _required_text(value.get("visual_query"), "visual_query")[:300],
        "media_type": (
            str(value.get("media_type") or "either").strip().lower()
            if str(value.get("media_type") or "either").strip().lower()
            in {"image", "video", "either"}
            else "either"
        ),
        "on_screen_text": _required_text(value.get("on_screen_text"), "on_screen_text")[:300],
        "narration": str(value.get("narration") or "").strip()[:2000],
        "evidence_refs": refs,
        "motion_intent": normalized_motion or ["kinetic_typography"],
        "preferred_renderer": str(value.get("preferred_renderer") or "auto").strip().lower(),
    }


_MATERIAL_PRESENTATIONS = {"full_bleed", "inset_card", "letterbox"}
_MATERIAL_ANCHORS = {"center", "left", "right", "top", "bottom"}


def _material_candidate_projection(value: dict[str, Any]) -> dict[str, Any]:
    """Expose only visual/ranking inputs; never leak provider download details."""

    metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
    return {
        "id": str(value.get("id") or ""),
        "provider": str(value.get("provider") or ""),
        "media_type": str(value.get("media_type") or ""),
        "preview_url": str(value.get("preview_url") or ""),
        "source_url": str(value.get("source_url") or ""),
        "width": int(value.get("width") or 0),
        "height": int(value.get("height") or 0),
        "duration": float(value.get("duration") or 0),
        "description": str(
            metadata.get("title") or metadata.get("asset_name") or ""
        )[:500],
    }


def _normalize_material_judgment(
    value: Any,
    *,
    allowed_candidate_ids: set[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PermanentStepError("visual material judge must return an object")
    raw_rankings = value.get("ranked_candidates")
    if not isinstance(raw_rankings, list) or not raw_rankings:
        raise PermanentStepError("visual material judge returned no candidate rankings")
    rankings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_rankings[:6]:
        if not isinstance(raw, dict):
            continue
        candidate_id = str(raw.get("candidate_id") or raw.get("id") or "").strip()
        if candidate_id not in allowed_candidate_ids or candidate_id in seen:
            continue
        try:
            score = float(raw.get("relevance_score"))
        except (TypeError, ValueError):
            score = 0.0
        if score > 1:
            score /= 10
        score = max(0.0, min(score, 1.0))
        presentation = str(raw.get("presentation") or "inset_card").strip().lower()
        if presentation not in _MATERIAL_PRESENTATIONS:
            presentation = "inset_card"
        fit = str(raw.get("fit") or "contain").strip().lower()
        if fit not in {"cover", "contain"}:
            fit = "contain"
        if presentation != "full_bleed":
            fit = "contain"
        anchor = str(raw.get("subject_anchor") or "center").strip().lower()
        if anchor not in _MATERIAL_ANCHORS:
            anchor = "center"
        rankings.append({
            "candidate_id": candidate_id,
            "relevance_score": round(score, 4),
            "presentation": presentation,
            "fit": fit,
            "subject_anchor": anchor,
            "reason": str(raw.get("reason") or "").strip()[:800],
        })
        seen.add(candidate_id)
    if not rankings:
        raise PermanentStepError("visual material judge ranked no known candidate")
    rankings.sort(key=lambda item: -float(item["relevance_score"]))
    accepted = [
        str(item["candidate_id"])
        for item in rankings
        if float(item["relevance_score"]) >= 0.68
    ]
    raw_budget = value.get("budget") if isinstance(value.get("budget"), dict) else {}
    return {
        "model_lane": "auxiliary.vision",
        "candidate_budget": min(len(allowed_candidate_ids), 6),
        "billing_guard": {
            "candidate_count": min(int(raw_budget.get("candidate_count") or len(rankings)), 6),
            "image_detail": "low",
            "max_output_tokens": min(int(raw_budget.get("max_output_tokens") or 900), 900),
        },
        "acceptance_threshold": 0.68,
        "accepted_candidate_ids": accepted,
        "ranked_candidates": rankings,
    }


def _review_layout(value: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(value, dict):
        return {
            "presentation": "inset_card",
            "fit": "contain",
            "subject_anchor": "center",
        }
    return {
        "presentation": str(value.get("presentation") or "inset_card"),
        "fit": str(value.get("fit") or "contain"),
        "subject_anchor": str(value.get("subject_anchor") or "center"),
    }


def _video_ir(
    *,
    treatment: dict[str, Any],
    visual_asset_ids: dict[str, str],
    visual_layouts: dict[str, dict[str, str]] | None = None,
    voice_asset_id: str | None = None,
) -> dict[str, Any]:
    aspect = str(treatment.get("aspect_ratio") or "9:16")
    width, height = {
        "16:9": (1920, 1080),
        "1:1": (1080, 1080),
        "4:5": (1080, 1350),
    }.get(aspect, (1080, 1920))
    scenes = []
    captions = []
    cursor = 0.0
    layouts = visual_layouts or {}
    for shot in treatment["shot_list"]:
        duration = float(shot["duration"])
        preference = str(shot.get("preferred_renderer") or "auto")
        if preference not in {"auto", "remotion", "hyperframes"}:
            preference = "auto"
        layout = _review_layout(layouts.get(str(shot["id"])))
        scenes.append({
            "id": shot["id"],
            "duration": duration,
            "purpose": shot["purpose"],
            "visuals": [{
                "media_asset_id": visual_asset_ids[shot["id"]],
                "source_in": 0,
                "fit": layout["fit"],
                "presentation": layout["presentation"],
                "subject_anchor": layout["subject_anchor"],
            }],
            "text": [{
                "text": shot["on_screen_text"],
                "role": "headline",
                "style_token": "marketing.headline",
            }],
            "motion_intent": shot["motion_intent"],
            "constraints": {
                "safe_area": "short_vertical" if height > width else "landscape_video",
                "rights_required": True,
            },
            "renderer_policy": {"preference": preference, "fallback": "remotion"},
            "review_rules": ["headline remains readable inside the platform safe area"],
        })
        captions.append({
            "start": round(cursor, 3),
            "end": round(cursor + duration, 3),
            "text": shot.get("narration") or shot["on_screen_text"],
        })
        cursor += duration
    return {
        "version": VIDEO_IR_VERSION,
        "canvas": {"width": width, "height": height, "fps": 30},
        "scenes": scenes,
        "captions": captions,
        "audio": ({"voice_asset_id": voice_asset_id} if voice_asset_id else {}),
        "review_rules": [
            "playable MP4 is required before the production may enter the draft box",
            "every source visual must carry a durable rights state",
            "the rendered cut must preserve the approved platform hook, evidence map and CTA",
        ],
    }


def _evidence_refs(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else ([value] if value else [])
    return list(
        dict.fromkeys(str(item).strip() for item in raw if str(item).strip())
    )[:100]


def _evidence_pack_projection(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Bound verified evidence for creative Workers without losing lineage."""

    return [
        {
            "id": str(item.get("id") or ""),
            "title": str(item.get("title") or "")[:500],
            "source_url": str(
                item.get("canonical_url") or item.get("source_url") or ""
            )[:2000],
            "excerpt": str(item.get("excerpt") or "")[:2500],
            "captured_at": item.get("captured_at"),
            "verification_level": item.get("verification_level"),
        }
        for item in records[:30]
        if str(item.get("id") or "").strip()
    ]


def _platform_plan_projection(treatment: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": treatment["platform"],
        "format": treatment["format"],
        "aspect_ratio": treatment["aspect_ratio"],
        "target_duration": treatment["target_duration"],
        "opening": treatment["hook_hypothesis"]["first_three_seconds"],
        "pacing": treatment["pacing"],
        "caption_style": treatment["caption_style"],
        "cta": treatment["cta"],
    }


def _bounded_preflight_projection(value: dict[str, Any]) -> dict[str, Any]:
    decision = value.get("preflight_decision") or {}
    return {
        "formula_version": value.get("formula_version"),
        "status": decision.get("status"),
        "go": decision.get("go") is True,
        "score": decision.get("score"),
        "confidence": decision.get("confidence"),
        "prior_mode": value.get("prior_mode"),
        "blockers": list(decision.get("blockers") or []),
        "warnings": list(decision.get("warnings") or []),
        "required_next_steps": list(decision.get("required_next_steps") or []),
        "prediction_contract": value.get("prediction_contract") or {},
        "treatment_features": value.get("treatment_features") or {},
        "cut_features": value.get("cut_features") or {},
        "draft_features": value.get("draft_features") or {},
    }


def _execution_account_id(
    brief: dict[str, Any], *, platform: str, fallback_account_id: str
) -> str:
    target = (brief.get("platform_targets") or {}).get(platform)
    if isinstance(target, dict):
        resolved = str(
            target.get("execution_account_id") or target.get("account_id") or ""
        ).strip()
        if resolved:
            return resolved
    return str(fallback_account_id or "").strip()


def _knowledge_for_production_target(
    value: dict[str, Any], *, production_target: dict[str, Any]
) -> dict[str, Any]:
    """Remove account-personal evidence from an unbound platform cold start."""

    result = dict(value or {})
    if production_target.get("personalization_available") is not True:
        result["account"] = []
    return result


def _personalization_account_id(
    production_target: dict[str, Any], *, fallback_account_id: str
) -> str:
    if production_target.get("personalization_available") is True:
        target = str(production_target.get("account_id") or "").strip()
        if target:
            return target
    return str(fallback_account_id or "").strip()


def _flatten_lane_orders(value: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for lane in value.values():
        if isinstance(lane, dict) and "plan_id" in lane:
            result.append(lane)
        elif isinstance(lane, dict):
            result.extend(
                item
                for item in lane.values()
                if isinstance(item, dict) and "plan_id" in item
            )
    return result
