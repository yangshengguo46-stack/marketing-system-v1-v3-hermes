"""TopicBrief → independent article/video production DAG."""

from __future__ import annotations

from typing import Any

from agent.harness import HarnessRepository
from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.topic_recommendations import TopicRecommendationRepository
from agent.marketing.platform_catalog import platform_content_blueprints


TOPIC_PRODUCTION_WORKFLOW_VERSION = "marketing.topic-production.workflow.v1"

_ARTICLE_FORMATS = frozenset(
    {"long_article", "article", "image_text", "carousel", "image", "text", "document", "short_text", "thread"}
)
_VIDEO_FORMATS = frozenset(
    {"short_video", "video", "long_video", "reel", "live"}
)


def _automatic_voiceover_authorized() -> bool:
    """Read the user's durable paid-TTS preference from Hermes config."""

    try:
        from hermes_cli.config import load_config

        config = load_config()
    except Exception:
        return False
    marketing = config.get("marketing")
    if not isinstance(marketing, dict):
        return False
    video = marketing.get("video")
    return isinstance(video, dict) and video.get("auto_voiceover") is True


def create_topic_production_workflow(
    *,
    candidate_id: str,
    user_id: str,
    entity_id: str,
    paths: MarketingDataPaths | None = None,
) -> dict[str, Any]:
    """Create one idempotent production DAG from a preflighted candidate."""

    candidate = TopicRecommendationRepository(paths).get_candidate(
        candidate_id=candidate_id,
        user_id=user_id,
        entity_id=entity_id,
    )
    if candidate.get("recommendation_eligible") is not True:
        raise ValueError("topic production requires a preflight-approved candidate")
    brief = _topic_brief(candidate)
    harness = HarnessRepository((paths or MarketingDataPaths.from_env()).agent_db)
    existing = harness.find_by_source(
        namespace="marketing",
        source_kind="marketing.topic_candidate",
        source_ref=str(candidate["id"]),
    )
    if existing is not None:
        return existing
    automatic_voiceover = _automatic_voiceover_authorized()
    return harness.create_workflow(
        namespace="marketing",
        owner_user_id=user_id,
        owner_entity_id=entity_id,
        source_kind="marketing.topic_candidate",
        source_ref=str(candidate["id"]),
        kind="topic.production",
        title=str(candidate["topic"]),
        input={
            "contract": TOPIC_PRODUCTION_WORKFLOW_VERSION,
            "account_id": str(candidate.get("account_id") or ""),
            "topic_brief_ref": {
                "candidate_id": candidate["id"],
                "plan_id": candidate["plan_id"],
                "preflight_id": candidate["preflight_id"],
            },
        },
        policy={
            "branches_are_siblings": True,
            "draft_destination": "draft_box",
            # Clicking “制作选题” authorizes reversible local production through
            # the first reviewable cut.  Paid generation, rights exceptions and
            # publishing remain separate effects with their own approval gates.
            "local_draft_render_authorized": True,
            "paid_generation_allowed": False,
            # This is intentionally narrower than paid_generation_allowed:
            # material/image/video generation remains zero-cost-only.  The
            # user may separately make their configured TTS provider the
            # durable default for finished video drafts.
            "automatic_voiceover_authorized": automatic_voiceover,
            "material_cost_policy": "zero_cost_only",
            "publish_requires_effect_approval": True,
            "unknown_platform_requires_research": True,
        },
        steps=_steps(brief),
        actor="marketing.topic-production",
    )


def _topic_brief(candidate: dict[str, Any]) -> dict[str, Any]:
    nested = candidate.get("candidate") if isinstance(candidate.get("candidate"), dict) else {}
    platforms = [str(item) for item in candidate.get("target_platforms") or []]
    blueprints = nested.get("platform_blueprints")
    if not isinstance(blueprints, dict):
        blueprints = {}
    catalog_blueprints = platform_content_blueprints(platforms)
    resolved_blueprints = {
        platform: {
            **catalog_blueprints[platform],
            **(
                blueprints.get(platform)
                if isinstance(blueprints.get(platform), dict)
                else {}
            ),
        }
        for platform in platforms
    }
    lanes = {platform: _lanes(resolved_blueprints[platform]) for platform in platforms}
    return {
        "candidate_id": str(candidate["id"]),
        "topic": str(candidate["topic"]),
        "angle": str(candidate.get("angle") or ""),
        "plan_id": str(candidate["plan_id"]),
        "preflight_id": str(candidate["preflight_id"]),
        "evidence_refs": list(candidate.get("evidence_refs") or []),
        "signal_refs": list(candidate.get("signal_refs") or []),
        "target_platforms": platforms,
        "recommended_platforms": list(nested.get("recommended_platforms") or []),
        "recommendation_type": str(nested.get("recommendation_type") or "general"),
        "platform_matches": list(nested.get("platform_matches") or []),
        "platform_blueprints": resolved_blueprints,
        "lanes": lanes,
    }


def _lanes(blueprint: dict[str, Any]) -> list[str]:
    formats = {str(item) for item in blueprint.get("recommended_formats") or []}
    result: list[str] = []
    if formats & _ARTICLE_FORMATS:
        result.append("article")
    if formats & _VIDEO_FORMATS:
        result.append("video")
    if not result or str(blueprint.get("guidance_status") or "").startswith("generic_"):
        return ["article", "video"]
    return result


def _steps(brief: dict[str, Any]) -> list[dict[str, Any]]:
    reference = {
        "candidate_id": brief["candidate_id"],
        "plan_id": brief["plan_id"],
        "preflight_id": brief["preflight_id"],
    }
    steps: list[dict[str, Any]] = [
        {
            "key": "topic_brief.freeze",
            "kind": "domain.validate",
            "worker_role": "topic_reducer",
            "toolsets": ["marketing.read"],
            "resource_scope": f"topic:{brief['candidate_id']}",
            "input": reference,
            "max_attempts": 2,
        }
    ]
    research_keys: dict[str, str] = {}
    for platform in brief["target_platforms"]:
        blueprint = brief["platform_blueprints"][platform]
        if str(blueprint.get("guidance_status") or "").startswith("generic_"):
            key = f"platform.research.{platform}"
            research_keys[platform] = key
            steps.append(
                {
                    "key": key,
                    "kind": "platform.research",
                    "worker_role": "platform_researcher",
                    "toolsets": ["marketing.read", "web"],
                    "resource_scope": f"platform-profile:{platform}",
                    "input": {**reference, "platform": platform},
                    "depends_on": ["topic_brief.freeze"],
                }
            )

    article_platforms = [
        platform for platform, lanes in brief["lanes"].items() if "article" in lanes
    ]
    video_platforms = [
        platform for platform, lanes in brief["lanes"].items() if "video" in lanes
    ]
    branch_terminals: list[str] = []
    if article_platforms:
        steps.append(
            {
                "key": "article.direct",
                "kind": "article.direction",
                "worker_role": "article_director",
                "toolsets": ["marketing.read", "marketing.draft"],
                "resource_scope": f"article-project:{brief['candidate_id']}",
                "input": {**reference, "platforms": article_platforms},
                "depends_on": ["topic_brief.freeze"],
            }
        )
        article_variants: list[str] = []
        for platform in article_platforms:
            key = f"article.adapt.{platform}"
            article_variants.append(key)
            steps.append(
                {
                    "key": key,
                    "kind": "article.platform_variant",
                    "worker_role": "article_adapter",
                    "toolsets": ["marketing.read", "marketing.draft"],
                    "resource_scope": f"article-revision:{brief['candidate_id']}:{platform}",
                    "input": {**reference, "platform": platform},
                    "depends_on": [
                        "article.direct",
                        *([research_keys[platform]] if platform in research_keys else []),
                    ],
                }
            )
        steps.extend(
            [
                {
                    "key": "article.qa",
                    "kind": "article.qa",
                    "worker_role": "content_reviewer",
                    "toolsets": ["marketing.read"],
                    "resource_scope": f"article-qa:{brief['candidate_id']}",
                    "input": reference,
                    "depends_on": article_variants,
                },
                {
                    "key": "article.draft_box",
                    "kind": "draft.settle",
                    "worker_role": "draft_reducer",
                    "toolsets": ["marketing.draft"],
                    "resource_scope": f"draft-box:article:{brief['candidate_id']}",
                    "input": {**reference, "lane": "article"},
                    "depends_on": ["article.qa"],
                },
            ]
        )
        branch_terminals.append("article.draft_box")

    if video_platforms:
        steps.append(
            {
                "key": "video.direct",
                "kind": "video.direction",
                "worker_role": "video_director",
                "toolsets": ["marketing.read", "video"],
                "resource_scope": f"video-project:{brief['candidate_id']}",
                "input": {**reference, "platforms": video_platforms},
                "depends_on": ["topic_brief.freeze"],
            }
        )
        video_variants: list[str] = []
        for platform in video_platforms:
            key = f"video.adapt.{platform}"
            video_variants.append(key)
            steps.append(
                {
                    "key": key,
                    "kind": "video.platform_plan",
                    "worker_role": "video_adapter",
                    "toolsets": ["marketing.read", "video"],
                    "resource_scope": f"video-revision:{brief['candidate_id']}:{platform}",
                    "input": {**reference, "platform": platform},
                    "depends_on": [
                        "video.direct",
                        *([research_keys[platform]] if platform in research_keys else []),
                    ],
                }
            )
        steps.extend(
            [
                {
                    "key": "video.material.search",
                    "kind": "video.material_search",
                    "worker_role": "material_researcher",
                    "toolsets": ["marketing.read", "web", "video"],
                    "resource_scope": f"material-search:{brief['candidate_id']}",
                    "input": reference,
                    "depends_on": ["video.direct"],
                },
                {
                    "key": "video.audio.plan",
                    "kind": "video.audio_plan",
                    "worker_role": "audio_director",
                    "toolsets": ["marketing.read", "tts"],
                    "resource_scope": f"video-audio:{brief['candidate_id']}",
                    "input": reference,
                    "depends_on": ["video.direct"],
                },
            ]
        )
        video_qa_keys: list[str] = []
        for platform in video_platforms:
            previs_key = f"video.previs.{platform}"
            render_key = f"video.render.{platform}"
            qa_key = f"video.qa.{platform}"
            video_qa_keys.append(qa_key)
            steps.extend(
                [
                    {
                        "key": previs_key,
                        "kind": "video.previsualization",
                        "worker_role": "video_compositor",
                        "toolsets": ["video"],
                        "resource_scope": f"video-previs:{brief['candidate_id']}:{platform}",
                        "input": {**reference, "platform": platform},
                        "depends_on": [
                            f"video.adapt.{platform}",
                            "video.material.search",
                            "video.audio.plan",
                        ],
                    },
                    {
                        "key": render_key,
                        "kind": "video.render",
                        "worker_role": "render_worker",
                        "toolsets": ["video"],
                        "resource_scope": f"video-render:{brief['candidate_id']}:{platform}",
                        "input": {**reference, "platform": platform},
                        "depends_on": [previs_key],
                        "max_attempts": 3,
                    },
                    {
                        "key": qa_key,
                        "kind": "video.qa",
                        "worker_role": "video_reviewer",
                        "toolsets": ["video", "vision"],
                        "resource_scope": f"video-qa:{brief['candidate_id']}:{platform}",
                        "input": {**reference, "platform": platform},
                        "depends_on": [render_key],
                    },
                ]
            )
        steps.append(
            {
                "key": "video.draft_box",
                "kind": "draft.settle",
                "worker_role": "draft_reducer",
                "toolsets": ["marketing.draft"],
                "resource_scope": f"draft-box:video:{brief['candidate_id']}",
                "input": {**reference, "lane": "video"},
                "depends_on": video_qa_keys,
            }
        )
        branch_terminals.append("video.draft_box")

    if not branch_terminals:
        raise ValueError("topic has no producible content lane")
    steps.append(
        {
            "key": "production.complete",
            "kind": "workflow.reduce",
            "worker_role": "production_reducer",
            "toolsets": ["marketing.read"],
            "resource_scope": f"topic-production:{brief['candidate_id']}",
            "input": reference,
            "depends_on": branch_terminals,
        }
    )
    return steps
