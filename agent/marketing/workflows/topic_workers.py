"""Typed Workers for the durable topic-production Harness workflow.

The model is used only for bounded creative judgments.  Marketing repositories
remain the sole owners of plans, preflights, content, media, render jobs and
draft-box state; a model response is never treated as a completion receipt.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from agent.harness import (
    PermanentStepError,
    RetryableStepError,
    StepExecutionContext,
    StepResult,
)
from agent.human_observer import HumanObserverReader
from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.account_context import AccountContextRepository
from agent.marketing.domains.content_assets import ContentAssetRepository
from agent.marketing.domains.content_policy import ContentProductionPolicy
from agent.marketing.domains.evidence import EvidenceRepository
from agent.marketing.domains.knowledge_bases import KnowledgeBaseRepository
from agent.marketing.domains.operating_entities import OperatingEntityRepository
from agent.marketing.domains.topic_recommendations import TopicRecommendationRepository
from agent.marketing.domains.video_kanban import VideoKanbanExecutionRepository
from agent.marketing.intelligence.production_preflight import (
    CONTENT_PREFLIGHT_VERSION,
    create_article_draft_preflight,
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


HandlerRegistry = Mapping[
    str, Callable[[StepExecutionContext], StepResult | dict[str, Any] | None]
]


class TopicProductionWorkers:
    """Native Worker registry for independent article and video branches."""

    def __init__(
        self,
        *,
        creative_runner: CreativeRunner,
        paths: MarketingDataPaths | None = None,
    ) -> None:
        self.paths = paths or MarketingDataPaths.from_env()
        self.creative = creative_runner
        self.content = ContentAssetRepository(self.paths)
        self.topics = TopicRecommendationRepository(self.paths)
        self.loop = OperatingLoopRepository(self.paths)
        self.video_kanban = VideoKanbanExecutionRepository(self.paths)

    def handlers(self) -> dict[str, Callable[[StepExecutionContext], StepResult]]:
        return {
            "domain.validate": self.freeze_topic_brief,
            "platform.research": self.research_platform,
            "article.direction": self.direct_article,
            "article.qa": self.qa_article,
            "video.official_kanban": self.submit_official_video,
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
        video_platforms = self._platforms_for_prefix(context, "video.kanban_submit.")
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

    def submit_official_video(self, context: StepExecutionContext) -> StepResult:
        """Hand one platform brief to the official Hermes video Kanban owner."""

        frozen = self._output(context, "topic_brief.freeze")
        brief = frozen["topic_brief"]
        platform = str(context.step["input"].get("platform") or "").strip()
        if not platform or platform not in (frozen.get("lane_orders", {}).get("video") or {}):
            raise PermanentStepError("official video intake has no platform lane order")
        user_id, account_id = self._scope(context, platform=platform)
        entity_id = str(context.workflow.get("owner_entity_id") or "")
        production_target = brief["platform_targets"].get(platform) or {}
        account_context = self._platform_account_context(
            user_id=user_id,
            account_id=account_id,
            production_target=production_target,
        )
        knowledge_context = KnowledgeBaseRepository(self.paths).retrieve_for_preflight(
            user_id=user_id,
            account_id=_personalization_account_id(
                production_target,
                fallback_account_id=account_id,
            ),
            platforms=[platform],
            content_kind="faceless_video",
        )
        human_observer_projection = _read_human_observer_projection()
        origin_preflight = self.loop.get_preflight(str(brief["preflight_id"]))
        platform_profile = self._platform_profile(context, platform)
        blueprint = brief["platform_blueprints"].get(platform) or {}
        execution = self.video_kanban.submit(
            user_id=user_id,
            entity_id=entity_id,
            account_id=account_id,
            candidate_id=str(brief["candidate_id"]),
            plan_id=str(brief["plan_id"]),
            preflight_id=str(brief["preflight_id"]),
            platform=platform,
            topic=str(brief["topic"]),
            context={
                "topic_brief": brief,
                "evidence_refs": list(brief.get("evidence_refs") or []),
                "evidence_pack": list(brief.get("evidence_pack") or []),
                "signal_refs": list(brief.get("signal_refs") or []),
                "account_context": account_context,
                "knowledge_context": knowledge_context,
                "platform_profile": platform_profile,
                "platform_blueprint": blueprint,
                "production_target": production_target,
                "lane_order": frozen["lane_orders"]["video"][platform],
                "origin_preflight": {
                    "id": origin_preflight["id"],
                    "scores": origin_preflight.get("scores") or {},
                    "decision": origin_preflight.get("decision") or {},
                },
                "human_observer_projection": human_observer_projection,
                "workflow_id": str(
                    context.workflow.get("id") or f"attempt:{context.attempt_id}"
                ),
                "production_revision": int(
                    (context.workflow.get("input") or {}).get("production_revision") or 1
                ),
                "target_duration": int(
                    blueprint.get("target_duration_seconds")
                    or blueprint.get("duration_seconds")
                    or 60
                ),
            },
        )
        output = {
            "platform": platform,
            "execution_id": execution["id"],
            "root_task_id": execution.get("root_task_id"),
            "tenant": execution["tenant"],
            "workspace_path": execution["workspace_path"],
            "status": execution["status"],
            "draft_destination": "draft_box",
        }
        return StepResult(
            output=output,
            artifacts=[
                _artifact(
                    "video_kanban_execution",
                    "marketing.video.execution.v2",
                    execution["id"],
                )
            ],
            receipts=[
                {
                    "kind": "video.official_kanban.submitted",
                    "idempotency_key": f"video-kanban-submit:{execution['id']}",
                    "input": {
                        "candidate_id": brief["candidate_id"],
                        "platform": platform,
                    },
                    "output": {
                        "execution_id": execution["id"],
                        "root_task_id": execution.get("root_task_id"),
                        "tenant": execution["tenant"],
                        "status": execution["status"],
                    },
                }
            ],
        )

    def direct_article(self, context: StepExecutionContext) -> StepResult:
        frozen = self._output(context, "topic_brief.freeze")
        platform = str(context.step["input"].get("platform") or "").strip()
        if not platform:
            raise PermanentStepError("platform-native article work requires a platform")
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
                "IDs in evidence_allowlist for factual claims; copy every ID exactly without "
                "shortening it. Evidence IDs elsewhere in the context are background only. "
                "Return JSON only with: platform, format, title, hook, thesis, body_markdown or "
                "caption/short_text/thread/carousel_cards, claim_evidence_map (array of "
                "{claim,evidence_refs}), visual_brief, and adaptation_basis containing "
                "audience_intent, opening, structure, cta. Keep [evidence_xxx] markers beside "
                "factual claims."
            ),
            payload={
                "platform": platform,
                "platform_profile": self._platform_profile(context, platform),
                "topic_brief": brief,
                "evidence_allowlist": list(brief["evidence_refs"]),
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
            raise RetryableStepError(str(exc)) from exc
        return StepResult(output={"platform": platform, "article": article})

    def qa_article(self, context: StepExecutionContext) -> StepResult:
        frozen = self._output(context, "topic_brief.freeze")
        brief = frozen["topic_brief"]
        platform = str(context.step["input"].get("platform") or "").strip()
        if not platform:
            raise PermanentStepError("platform-native article QA requires a platform")
        order = frozen["lane_orders"]["article"][platform]
        article = dict(self._output(context, f"article.write.{platform}")["article"])
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
                    "article": _article_writer_projection(article),
                    "platform": platform,
                    "platform_profile": self._platform_profile(context, platform),
                    "topic_brief": brief,
                    "evidence_allowlist": list(brief["evidence_refs"]),
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
                    "evidence_allowlist": list(brief["evidence_refs"]),
                    "previous_article": _article_writer_projection(article),
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
                    "production_target": brief["platform_targets"].get(platform) or {},
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

    def settle_draft_branch(self, context: StepExecutionContext) -> StepResult:
        lane = str(context.step["input"].get("lane") or "")
        if lane != "article":
            raise PermanentStepError("draft settlement lane is invalid")
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
            raise PermanentStepError("article branch has no platform-native draft")
        return StepResult(output={"lane": lane, "results": refs})

    def reduce_workflow(self, context: StepExecutionContext) -> StepResult:
        results: list[dict[str, Any]] = []
        for key in ("article.draft_box",):
            try:
                results.extend(self._output(context, key).get("results") or [])
            except KeyError:
                continue
        results.extend(
            {
                "object_id": str(step["output"]["execution_id"]),
                "object_type": "video_kanban_execution",
                "title": f"{step['output']['platform']} 视频制作任务",
                "status": str(step["output"].get("status") or "queued"),
                "tenant": str(step["output"].get("tenant") or ""),
            }
            for step in context.workflow["steps"]
            if step["key"].startswith("video.kanban_submit.")
            and step["state"] == "succeeded"
        )
        if not results:
            raise PermanentStepError("topic production completed without durable results")
        return StepResult(
            output={
                "results": results,
                "draft_destination": "draft_box",
                "video_owner": "hermes.official.kanban-video-orchestrator",
            }
        )

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
                "source": "marketing.topic-production.workflow.v3",
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
                plan_id=saved["plan_id"],
                user_id=user_id,
                account_id=account_id,
                formula_version=CONTENT_PREFLIGHT_VERSION,
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
    paths: MarketingDataPaths | None = None,
) -> dict[str, Callable[[StepExecutionContext], StepResult]]:
    return TopicProductionWorkers(
        creative_runner=creative_runner,
        paths=paths,
    ).handlers()


def _read_human_observer_projection() -> dict[str, Any]:
    """Read a bounded upstream research projection without making it product truth."""

    try:
        return HumanObserverReader().projection(namespace="global", limit=40)
    except Exception:
        return {
            "contract": "human-observer-read-projection-v1",
            "namespace": "global",
            "interpretations": [],
            "model_revisions": [],
            "authority": "read_only_no_product_writeback",
            "data_state": "unavailable_cold_start",
        }


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
        refs = _evidence_refs(
            raw.get("evidence_refs") or raw.get("evidence_ref"),
            allowed_evidence_refs=allowed_evidence_refs,
        )
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


def _article_writer_projection(article: dict[str, Any]) -> dict[str, Any]:
    """Restore a normalized article to the writer/reviewer JSON contract."""

    deliverable = article.get("deliverable")
    return {
        "platform": article.get("platform"),
        "format": article.get("format"),
        "title": article.get("title"),
        "hook": article.get("hook"),
        "thesis": article.get("thesis"),
        **(dict(deliverable) if isinstance(deliverable, dict) else {}),
        "claim_evidence_map": article.get("claim_evidence_map") or [],
        "visual_brief": article.get("visual_brief") or {},
        "adaptation_basis": article.get("adaptation_basis") or {},
    }


def _evidence_refs(
    value: Any,
    *,
    allowed_evidence_refs: set[str] | None = None,
) -> list[str]:
    raw = value if isinstance(value, list) else ([value] if value else [])
    refs = list(
        dict.fromkeys(str(item).strip() for item in raw if str(item).strip())
    )[:100]
    if not allowed_evidence_refs:
        return refs
    canonical: list[str] = []
    for ref in refs:
        resolved = ref
        if ref not in allowed_evidence_refs and len(ref) >= 24:
            matches = [item for item in allowed_evidence_refs if item.startswith(ref)]
            if len(matches) == 1:
                # Creative models occasionally drop a few trailing hash chars.
                # A unique, long prefix can only resolve to an ID already in
                # the immutable TopicBrief, so this improves JSON robustness
                # without admitting evidence outside the allowlist.
                resolved = matches[0]
        if resolved not in canonical:
            canonical.append(resolved)
    return canonical


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
            "source_type": item.get("source_type"),
            "provider": item.get("provider"),
        }
        for item in records[:30]
        if str(item.get("id") or "").strip()
    ]


def _bounded_preflight_projection(value: dict[str, Any]) -> dict[str, Any]:
    """Keep only the durable, non-internal result of a production preflight."""

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
