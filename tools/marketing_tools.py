"""Native tools for the Marketing OS account operating context."""

from __future__ import annotations

import json
from datetime import datetime

from agent.marketing.domains import (
    AccountContextRepository,
    AccountLifecycleRepository,
    AccountPortfolioRepository,
    AccountStrategyRepository,
    ContentAssetRepository,
    ContentProductionPolicy,
    EvidenceRepository,
    KnowledgeBaseRepository,
    MaterialSourcingRepository,
    MediaAssetRepository,
    OperatingEntityRepository,
    ProductionAudioRepository,
    PublishingRepository,
    PublicContentObservationRepository,
    ShortVideoSignalRepository,
    VideoProductionRepository,
)
from agent.marketing.session_scope import (
    enforce_tool_account_scope,
    read_tool_session_scope,
)
from agent.marketing.providers import get_publish_provider, has_publish_providers
from agent.marketing.intelligence import (
    OperatingLoopRepository,
    create_content_production_preflight,
)
from agent.marketing.intelligence.topic_recommendations import (
    build_daily_topic_recommendation_batch,
)
from tools.registry import registry


LIST_ACCOUNTS_SCHEMA = {
    "name": "marketing_read_accounts",
    "description": (
        "List the user's connected social-media accounts from the canonical Marketing OS store. "
        "Use this before account-specific advice when no account_id is already known. The result "
        "contains no cookies, tokens, passwords or other login secrets."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

READ_ACCOUNT_CONTEXT_SCHEMA = {
    "name": "marketing_read_account_context",
    "description": (
        "Read the bound creator/brand operating entity and all of its linked platform-account "
        "contexts: shared strategy, confirmed audience, positioning, Account DNA, first-party "
        "portfolio facts and explicit conflicts. account_id optionally focuses one linked channel; "
        "it does not hide the other channels. Use this before positioning, topic, content or growth "
        "work. Missing fields are evidence gaps and must not be invented."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "account_id": {
                "type": "string",
                "description": "Marketing OS account id returned by marketing_read_accounts.",
            },
            "user_id": {
                "type": "string",
                "description": "Optional product user scope. Defaults to 'default'.",
                "default": "default",
            },
        },
        "required": [],
    },
}

UPDATE_ACCOUNT_LIFECYCLE_SCHEMA = {
    "name": "marketing_update_account_lifecycle",
    "description": (
        "Build the bound account's versioned operating model through natural conversation: creator "
        "assets, market-route hypotheses, behavioral audience, evidence-backed benchmark graph, "
        "positioning, content system and falsifiable experiments. Important transitions require "
        "explicit confirmation. The account is conversation-bound and cannot be overridden."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "begin_project",
                    "draft_creator_profile",
                    "confirm_creator_profile",
                    "draft_market_route",
                    "select_market_route",
                    "draft_audience_hypothesis",
                    "confirm_audience_hypothesis",
                    "add_benchmark_account",
                    "decide_benchmark_account",
                    "add_benchmark_observation",
                    "draft_positioning",
                    "approve_positioning",
                    "draft_content_system",
                    "approve_content_system",
                    "propose_experiment",
                    "approve_experiment",
                ],
            },
            "business_goal": {"type": "string"},
            "constraints": {"type": "object"},
            "project_id": {"type": "string"},
            "profile_id": {"type": "string"},
            "profile": {"type": "object"},
            "source_refs": {"type": "array", "items": {"type": "string"}},
            "route_id": {"type": "string"},
            "route": {"type": "object"},
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "hypothesis_id": {"type": "string"},
            "segments": {"type": "array", "items": {}},
            "pains": {"type": "array", "items": {}},
            "scenarios": {"type": "array", "items": {}},
            "jobs": {"type": "array", "items": {}},
            "current_alternatives": {"type": "array", "items": {}},
            "trust_barriers": {"type": "array", "items": {}},
            "desired_outcomes": {"type": "array", "items": {}},
            "behavior_signals": {"type": "array", "items": {}},
            "existence_strategy_hypotheses": {
                "type": "array",
                "items": {"type": "object"},
                "description": (
                    "Revisable preserve/confirm/expand/continue behavioral strategy projections; "
                    "these are not existence itself and require observable/disconfirming signals."
                ),
            },
            "need_projection_hypotheses": {
                "type": "array",
                "items": {"type": "object"},
                "description": (
                    "Maslow-like need projections describing what embodied or social deficit/growth "
                    "a behavior may address. These are hypotheses, not directly observed motives."
                ),
            },
            "cognitive_projection_hypotheses": {
                "type": "array",
                "items": {"type": "object"},
                "description": (
                    "Confidence-bounded, reviewable soft hypotheses such as Jungian information-"
                    "processing projections. Never a diagnosis or permanent personality label."
                ),
            },
            "exclusions": {"type": "array", "items": {}},
            "data_gaps": {"type": "array", "items": {}},
            "benchmark_id": {"type": "string"},
            "platform": {"type": "string"},
            "account_handle": {"type": "string"},
            "account_name": {"type": "string"},
            "platform_account_id": {"type": "string"},
            "profile_url": {"type": "string"},
            "role": {"type": "string"},
            "selection_reason": {"type": "string"},
            "match_dimensions": {"type": "object"},
            "decision": {"type": "string"},
            "dimension": {"type": "string"},
            "value": {"type": "object"},
            "positioning_id": {"type": "string"},
            "positioning": {"type": "object"},
            "accept_data_gaps": {"type": "boolean"},
            "system_id": {"type": "string"},
            "content_system": {"type": "object"},
            "experiment_id": {"type": "string"},
            "hypothesis": {"type": "string"},
            "variable": {"type": "object"},
            "variants": {"type": "array", "items": {"type": "object"}},
            "prediction": {"type": "object"},
            "success_criteria": {"type": "object"},
            "confirmed_by_user": {
                "type": "boolean",
                "description": (
                    "Set true only when the user explicitly accepted this exact draft in the current conversation."
                ),
            },
        },
        "required": ["action"],
    },
}

PLAN_CONTENT_PRODUCTION_SCHEMA = {
    "name": "marketing_plan_content_production",
    "description": (
        "Build a Hermes-native production work order for a soft article, faceless material video, "
        "or one content kernel adapted into platform-native variants across any requested platform set. "
        "High-end human, digital-human, and AI film production belongs to the standalone video-studio "
        "product and is intentionally outside this tool. It reads the current conversation's account context, "
        "selects a lane and shared capabilities, then persists an immutable InfluenceOS preflight "
        "covering audience/evidence/rights/cost gates. The work order is a checkpoint and returns "
        "the plan_id plus the decision that every drafting action must consume."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "objective": {"type": "string"},
            "kind": {
                "type": "string",
                "enum": [
                    "auto",
                    "article_soft",
                    "faceless_video",
                    "cross_platform_campaign",
                ],
                "default": "auto",
            },
            "platforms": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Any domestic or overseas platform IDs. Use 'all' to expand every currently "
                    "linked channel, and add named unconnected targets such as instagram or a new "
                    "platform ID when planning future distribution."
                ),
            },
            "audience": {"type": "string"},
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
            "constraints": {"type": "object"},
            "experiment_id": {
                "type": "string",
                "description": (
                    "Optional running account experiment this plan and every resulting asset test."
                ),
            },
        },
        "required": ["objective"],
    },
}

PREFLIGHT_DAILY_TOPIC_RECOMMENDATIONS_SCHEMA = {
    "name": "marketing_preflight_daily_topic_recommendations",
    "description": (
        "Finalize one daily topic-candidate batch for the operating entity bound to this "
        "session. Every candidate is converted into an all-requested-platform production "
        "plan and immutable InfluenceOS preflight. Only candidates whose deterministic "
        "preflight returns go=true appear in delivery_markdown; blocked candidates remain "
        "research-only. For a scheduled recommendation, call this exactly once and return "
        "delivery_markdown verbatim as the entire final response."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "platforms": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Use 'all' for every linked platform. Named domestic or overseas targets "
                    "may be added; the list is extensible and never limited to two platforms."
                ),
            },
            "candidates": {
                "type": "array",
                "minItems": 1,
                "maxItems": 10,
                "items": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string"},
                        "angle": {"type": "string"},
                        "why_now": {"type": "string"},
                        "audience": {"type": "string"},
                        "platforms": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional extra future/overseas targets for this topic.",
                        },
                        "evidence_refs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Verified EvidencePack IDs captured by native collectors. "
                                "Without verified evidence the candidate cannot be recommended."
                            ),
                        },
                        "signal_refs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Durable IDs of the owned/public/model signals used.",
                        },
                        "platform_fit_hypotheses": {
                            "type": "array",
                            "description": (
                                "A platform-by-platform predictive hypothesis, not observed performance. "
                                "Cover every requested platform. The preflight engine recalibrates these "
                                "scores before classifying a topic as general or platform-specific."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "platform": {"type": "string"},
                                    "match_score": {
                                        "type": "number",
                                        "minimum": 0,
                                        "maximum": 100,
                                    },
                                    "rationale": {"type": "string"},
                                    "evidence_refs": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": (
                                            "Optional subset of this candidate's verified evidence IDs "
                                            "that specifically supports the platform-fit rationale."
                                        ),
                                    },
                                },
                                "required": ["platform", "match_score", "rationale"],
                            },
                        },
                    },
                    "required": ["topic", "evidence_refs"],
                },
            },
        },
        "required": ["candidates"],
    },
}

READ_CONTENT_ASSETS_SCHEMA = {
    "name": "marketing_read_content_assets",
    "description": (
        "List durable content drafts and assets across every platform account linked to the "
        "operating entity bound to this conversation. "
        "Use it to resume prior work instead of recreating or storing drafts in long-term memory."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "platform": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
        },
        "required": [],
    },
}

READ_VIDEO_PRODUCTIONS_SCHEMA = {
    "name": "marketing_read_video_productions",
    "description": (
        "List durable faceless-video render jobs for the account bound to this conversation. "
        "Use it to recover prepared, running, completed or failed work and inspect the approved "
        "EDL, final media asset, immutable content revision and render receipt."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["prepared", "approved", "running", "completed", "failed"],
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
        },
        "required": [],
    },
}

READ_EVIDENCE_PACK_SCHEMA = {
    "name": "marketing_read_evidence_pack",
    "description": (
        "Read evidence records automatically captured from successful native collectors across "
        "the bound operating entity's linked accounts. Cite the returned evidence IDs in production tools. "
        "A verified record proves source integrity, capture time and content hash; it does not by "
        "itself prove every claim on the source page is true."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["captured", "verified", "rejected", "stale"],
                "default": "verified",
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
        },
        "required": [],
    },
}

READ_SOUND_TRENDS_SCHEMA = {
    "name": "marketing_read_sound_trends",
    "description": (
        "Read verified BGM/sound momentum from real short-video browser observations for the "
        "account bound to this conversation. Use it before drafting or editing short video; "
        "hashtag popularity is not a substitute for a platform sound identity."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "platform": {
                "type": "string",
                "enum": [
                    "douyin",
                    "bilibili",
                    "xiaohongshu",
                    "kuaishou",
                    "wechat_channels",
                    "tiktok",
                    "youtube",
                ],
            },
            "objective": {"type": "string"},
            "window_hours": {
                "type": "integer",
                "minimum": 1,
                "maximum": 720,
                "default": 72,
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
        },
        "required": ["platform"],
    },
}

READ_PUBLIC_CONTENT_SCHEMA = {
    "name": "marketing_read_public_content",
    "description": (
        "Read evidence-backed public creator content cases captured by "
        "browser_capture_public_content. Repeated captures of the same post form a feedback "
        "time series. Public observations are natural experiments, not causal proof."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "platform": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
        },
        "required": [],
    },
}

INTERPRET_PUBLIC_CONTENT_SCHEMA = {
    "name": "marketing_interpret_public_content",
    "description": (
        "Interpret one verified public-content feedback snapshot with the same content, audience, "
        "existence-direction and social-reaction model used for owned work. This creates a Receipt "
        "and pending learning candidates; it never mutates the benchmark graph automatically. "
        "Do not submit commenter identities, raw comments, exact probabilities or causal claims."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "observation_id": {"type": "string"},
            "model_observation": {
                "type": "object",
                "properties": {
                    "content_features": {"type": "object"},
                    "audience": {"type": "object"},
                    "reaction": {
                        "type": "object",
                        "properties": {
                            "sample_size": {"type": "integer", "minimum": 0},
                            "clusters": {
                                "type": "array",
                                "maxItems": 12,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "cohort": {"type": "string"},
                                        "stance": {
                                            "type": "string",
                                            "enum": [
                                                "supportive",
                                                "experience_sharing",
                                                "questioning",
                                                "skeptical",
                                                "oppositional",
                                                "action_seeking",
                                                "off_target",
                                            ],
                                        },
                                        "need_projection": {
                                            "type": "string",
                                            "enum": [
                                                "physiological",
                                                "safety",
                                                "belonging",
                                                "esteem",
                                                "self_actualization",
                                                "transcendence",
                                                "unknown",
                                            ],
                                        },
                                        "cognitive_projection": {
                                            "type": "string",
                                            "enum": [
                                                "Se",
                                                "Si",
                                                "Ne",
                                                "Ni",
                                                "Te",
                                                "Ti",
                                                "Fe",
                                                "Fi",
                                                "unknown",
                                            ],
                                        },
                                        "existence_strategy": {
                                            "type": "string",
                                            "enum": [
                                                "preserve",
                                                "confirm",
                                                "expand",
                                                "continue",
                                                "unknown",
                                            ],
                                        },
                                        "themes": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "count": {"type": "integer", "minimum": 0},
                                    },
                                    "required": [
                                        "cohort",
                                        "stance",
                                        "need_projection",
                                        "cognitive_projection",
                                        "existence_strategy",
                                        "themes",
                                        "count",
                                    ],
                                },
                            },
                            "question_patterns": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "objection_patterns": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["sample_size", "clusters"],
                    },
                    "disconfirming_signals": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "data_gaps": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "content_features",
                    "audience",
                    "reaction",
                    "disconfirming_signals",
                    "data_gaps",
                ],
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 0.7},
            "project_id": {"type": "string"},
            "benchmark_id": {"type": "string"},
            "benchmark_projection": {
                "type": "object",
                "description": (
                    "Optional governed benchmark proposal. Requires project_id; benchmark_id links "
                    "an existing benchmark, otherwise acceptance creates only a benchmark candidate."
                ),
            },
        },
        "required": ["observation_id", "model_observation", "confidence"],
    },
}

READ_ACCOUNT_PORTFOLIO_SCHEMA = {
    "name": "marketing_read_account_portfolio",
    "description": (
        "Read the latest verified owned-content portfolio and transparent execution baseline for "
        "one explicitly requested platform account linked to the bound operating entity. If omitted, "
        "the action account is used. For a WeChat Official Account, call "
        "browser_collect_wechat_official_portfolio first to refresh its published articles. "
        "Separate observed facts, qualitative interpretation and recommendations; missing response "
        "metrics are data gaps and must not be invented."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "account_id": {
                "type": "string",
                "description": "Optional linked platform account id; defaults to the action account.",
            }
        },
        "required": [],
    },
}

READ_KNOWLEDGE_SCHEMA = {
    "name": "marketing_read_knowledge",
    "description": (
        "Read governed platform, market, account, or content knowledge. Platform knowledge contains "
        "current rules and operating guidance; market knowledge contains category, audience and "
        "competitive patterns; account knowledge contains only accepted receipt-backed learning; "
        "content knowledge contains attention, psychology, sociology, trust and propagation principles. "
        "User statements and model opinions are never knowledge truth."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "knowledge_base": {
                "type": "string",
                "enum": ["platform", "market", "account", "content"],
            },
            "platform": {"type": "string"},
            "content_kind": {"type": "string"},
            "topics": {"type": "array", "items": {"type": "string"}},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
        },
        "required": ["knowledge_base"],
    },
}

REACTION_SCENARIOS_SCHEMA = {
    "type": "array",
    "minItems": 3,
    "maxItems": 8,
    "description": (
        "Anonymous pre-publish commenter-cohort hypotheses. Include supportive, skeptical/opposed, "
        "and question/action scenarios. Examples must be synthetic and must not identify a real person."
    ),
    "items": {
        "type": "object",
        "properties": {
            "cohort": {"type": "string"},
            "cohort_relation": {
                "type": "string",
                "enum": ["target", "adjacent", "opposed", "off_target", "unknown"],
            },
            "stance": {
                "type": "string",
                "enum": [
                    "supportive",
                    "experience_sharing",
                    "questioning",
                    "skeptical",
                    "oppositional",
                    "action_seeking",
                    "off_target",
                ],
            },
            "need_projection": {
                "type": "string",
                "enum": [
                    "physiological",
                    "safety",
                    "belonging",
                    "esteem",
                    "self_actualization",
                    "transcendence",
                    "unknown",
                ],
                "description": "Maslow-like hypothesis about what need is projected into behavior.",
            },
            "cognitive_projection": {
                "type": "string",
                "enum": ["Se", "Si", "Ne", "Ni", "Te", "Ti", "Fe", "Fi", "unknown"],
                "description": "Jungian information-processing hypothesis, not a permanent type.",
            },
            "existence_strategy": {
                "type": "string",
                "enum": ["preserve", "confirm", "expand", "continue", "unknown"],
                "description": (
                    "Observable strategy projection: preserve boundaries, confirm identity, expand "
                    "capacity, continue meaning/legacy, or unknown. It is not existence itself."
                ),
            },
            "likelihood_band": {
                "type": "string",
                "enum": ["low", "medium", "high", "unknown"],
                "description": "Use a broad band only; never invent an exact probability.",
            },
            "trigger": {"type": "string"},
            "rationale": {"type": "string"},
            "likely_comment_themes": {
                "type": "array",
                "minItems": 1,
                "maxItems": 6,
                "items": {"type": "string"},
            },
            "synthetic_comment_examples": {
                "type": "array",
                "minItems": 1,
                "maxItems": 4,
                "items": {"type": "string"},
                "description": "Synthetic examples only, never presented as quotes from real users.",
            },
            "response_opportunity": {"type": "string"},
            "risk": {"type": "string"},
            "evidence_basis": {"type": "array", "items": {"type": "string"}},
            "disconfirming_signals": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "cohort",
            "cohort_relation",
            "stance",
            "need_projection",
            "cognitive_projection",
            "existence_strategy",
            "likelihood_band",
            "trigger",
            "rationale",
            "likely_comment_themes",
            "synthetic_comment_examples",
            "disconfirming_signals",
        ],
        "additionalProperties": False,
    },
}

CREATE_CONTENT_DRAFT_SCHEMA = {
    "name": "marketing_draft_content_create",
    "description": (
        "Save a substantive, reversible video/image/caption or cross-platform campaign draft for the "
        "operating entity bound to this conversation. Article drafts must use "
        "marketing_draft_article_create so parent/variant and "
        "citation checks cannot be bypassed. At least one verified EvidencePack ID is required. The "
        "draft must include anonymous social reaction scenarios for later comment-cluster retro. The "
        "account id is taken from the Hermes session and cannot be supplied or overridden by the model."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "plan_id": {"type": "string"},
            "type": {
                "type": "string",
                "enum": ["script", "video", "image", "caption"],
                "default": "script",
            },
            "platform": {"type": "string"},
            "production_kind": {
                "type": "string",
                "enum": ["article_soft", "faceless_video", "cross_platform_campaign"],
            },
            "topic": {"type": "string"},
            "hook": {"type": "string"},
            "content": {
                "type": "object",
                "description": (
                    "Draft payload. Video drafts should include sound_plan with mode, mix_role and "
                    "opening_cue_ms; trend_sound additionally requires a verified sound_id returned "
                    "by marketing_read_sound_trends. cross_platform_campaign drafts use "
                    "platform=multi_platform and must contain one substantive platform_variants "
                    "entry for every planned platform. Every entry needs format plus an "
                    "adaptation_basis with audience_intent, opening, structure and cta; unknown "
                    "platforms must retain the plan's explicit research gap instead of inventing rules."
                ),
            },
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
            "memory_refs": {"type": "array", "items": {"type": "string"}},
            "revision_of": {
                "type": "string",
                "description": "Existing faceless-video asset ID when creating a new immutable version.",
            },
            "reaction_scenarios": REACTION_SCENARIOS_SCHEMA,
        },
        "required": [
            "title",
            "plan_id",
            "platform",
            "production_kind",
            "content",
            "reaction_scenarios",
        ],
    },
}

CREATE_ARTICLE_DRAFT_SCHEMA = {
    "name": "marketing_draft_article_create",
    "description": (
        "Save an Agent-authored long-form parent draft and its distinct Zhihu/WeChat variants as one "
        "validated article bundle for the account bound to this conversation. Cite evidence in the "
        "same paragraph as every factual attribution or quantitative claim, using exact "
        "[evidence_xxx] markers returned by web_extract or "
        "marketing_read_evidence_pack. The tool persists useful incomplete drafts as needs_revision, "
        "but only structurally complete, cited, numerically supported and platform-distinct bundles "
        "become review_ready. Include at least three anonymous commenter-cohort scenarios covering "
        "support/experience, skepticism/opposition, and questions/action. Never invent percentages, "
        "time intervals, market prevalence, exact reaction probabilities, or real-person comments."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "plan_id": {"type": "string"},
            "topic": {"type": "string"},
            "hook": {"type": "string"},
            "parent_body_markdown": {"type": "string"},
            "platform_variants": {
                "type": "object",
                "description": "Keys must match every platform in the production plan.",
                "additionalProperties": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "body_markdown": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "cta": {"type": "string"},
                    },
                    "required": ["title", "body_markdown"],
                },
            },
            "evidence_refs": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
            "revision_of": {
                "type": "string",
                "description": (
                    "Existing ArticleBundle asset_id when revising a saved draft. The new asset "
                    "becomes the next immutable version and the parent is marked superseded."
                ),
            },
            "reaction_scenarios": REACTION_SCENARIOS_SCHEMA,
        },
        "required": [
            "title",
            "plan_id",
            "parent_body_markdown",
            "platform_variants",
            "evidence_refs",
            "reaction_scenarios",
        ],
    },
}

PREPARE_FACELESS_RENDER_SCHEMA = {
    "name": "marketing_prepare_faceless_render",
    "description": (
        "Validate and persist an immutable renderer-neutral Video IR or legacy edit decision "
        "list for an existing faceless-video ContentAsset in the current account. This prepares "
        "no external effect and performs no render. Every referenced media asset must already be "
        "materialized locally with approved rights. Repeating the same request returns the same "
        "production job."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "source_asset_id": {
                "type": "string",
                "description": "Current faceless-video ContentAsset revision to render.",
            },
            "renderer": {
                "type": "string",
                "enum": ["ffmpeg_timeline_v1"],
                "default": "ffmpeg_timeline_v1",
            },
            "edl": {
                "type": "object",
                "description": (
                    "marketing.faceless_video.edl.v1 object with width, height, fps, 1-100 clips "
                    "and optional voice_asset_id, music_asset_id and captions. Each clip requires "
                    "media_asset_id, source_in and duration. Provide exactly one of edl or video_ir."
                ),
            },
            "video_ir": {
                "type": "object",
                "description": (
                    "marketing.video.ir.v1 object with canvas, stable scenes, visuals, motion "
                    "intent, renderer policy, review rules, captions and audio references. "
                    "Unsupported renderer capabilities fail before approval. Provide exactly "
                    "one of video_ir or edl."
                ),
            },
        },
        "required": ["source_asset_id"],
    },
}

SEARCH_MATERIALS_SCHEMA = {
    "name": "marketing_search_materials",
    "description": (
        "Search the current account's user-owned visual library first, then configured licensed "
        "stock providers. Results are durable, ranked candidates with creator, source and license "
        "evidence. Search does not download or authorize any candidate."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "role": {
                "type": "string",
                "enum": ["scene", "broll", "prop", "storyboard", "other"],
                "default": "broll",
            },
            "orientation": {
                "type": "string",
                "enum": ["landscape", "portrait", "square"],
            },
            "target_duration": {
                "type": "number",
                "minimum": 0,
                "maximum": 600,
                "default": 0,
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 40, "default": 12},
            "locale": {"type": "string", "default": "zh-CN"},
        },
        "required": ["query"],
    },
}

MATERIALIZE_MATERIAL_SCHEMA = {
    "name": "marketing_effect_materialize",
    "description": (
        "After the user reviews a candidate's source and license, download the provider binary, "
        "hash it and import it into the native rights-gated media library. User-library candidates "
        "are selected without a duplicate copy."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "candidate_id": {"type": "string"},
            "rights_reviewed": {
                "type": "boolean",
                "description": "Must be true only after explicit human source/license review.",
            },
        },
        "required": ["candidate_id", "rights_reviewed"],
    },
}

KEEP_MATERIAL_SCHEMA = {
    "name": "marketing_effect_keep_material",
    "description": (
        "After the user explicitly asks to keep a numbered or identified temporary material, "
        "promote that exact account-scoped asset into the durable local library. Cloud promotion "
        "fails honestly until a cloud material provider is connected."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "asset_id": {"type": "string"},
            "target_tier": {
                "type": "string",
                "enum": ["library", "cloud"],
                "default": "library",
            },
            "confirmed": {
                "type": "boolean",
                "description": "True only after the user explicitly requested this retention action.",
            },
        },
        "required": ["asset_id", "target_tier", "confirmed"],
    },
}

PREPARE_VIDEO_VOICE_SCHEMA = {
    "name": "marketing_prepare_video_voice",
    "description": (
        "Prepare an immutable voiceover intent for the current account. This stores the exact "
        "script hash but does not call TTS or incur provider cost."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "script_text": {"type": "string", "maxLength": 4000},
        },
        "required": ["name", "script_text"],
    },
}

EXECUTE_VIDEO_VOICE_SCHEMA = {
    "name": "marketing_effect_video_voice",
    "description": (
        "After explicit human approval of the exact prepared script, call the user's configured "
        "Hermes TTS provider once and import the real audio output as a voice MediaAsset. Paid and "
        "local providers use the same receipt-bound state machine."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "job_id": {"type": "string"},
            "approval_ref": {"type": "string"},
            "confirmed_by_user": {"type": "boolean"},
        },
        "required": ["job_id", "approval_ref", "confirmed_by_user"],
    },
}

EXECUTE_FACELESS_RENDER_SCHEMA = {
    "name": "marketing_effect_faceless_render",
    "description": (
        "After explicit human review, execute one prepared faceless-video render through the native "
        "Hermes FFmpeg timeline. The effect is account-scoped and idempotent: completion creates a "
        "derived final-video MediaAsset, an immutable ContentAsset revision and a render receipt. "
        "No paid generation provider is called by this tool."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "production_id": {"type": "string"},
            "approval_ref": {
                "type": "string",
                "description": "Audit reference for the user's review of this exact EDL.",
            },
            "confirmed_by_user": {
                "type": "boolean",
                "description": "Must be true only after the user explicitly approves rendering.",
            },
        },
        "required": ["production_id", "approval_ref", "confirmed_by_user"],
    },
}

PREPARE_PUBLISH_SCHEMA = {
    "name": "marketing_prepare_publish",
    "description": (
        "Create the durable, idempotent publish action for a review-ready content asset in the "
        "account bound to this conversation. This only prepares an approval checkpoint; it does "
        "not publish and must never be described as a successful platform action. The final effect "
        "is executed separately by the trusted native provider after one-shot user approval."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "asset_id": {"type": "string"},
            "platform": {
                "type": "string",
                "enum": [
                    "zhihu",
                    "wechat_official",
                    "douyin",
                    "bilibili",
                    "xiaohongshu",
                    "kuaishou",
                    "wechat_channels",
                    "tiktok",
                    "youtube",
                ],
            },
            "provider": {
                "type": "string",
                "enum": ["playwright_mcp", "official_api", "manual_assisted"],
                "default": "playwright_mcp",
            },
        },
        "required": ["asset_id", "platform"],
    },
}

READ_PUBLISH_STATE_SCHEMA = {
    "name": "marketing_read_publish_state",
    "description": (
        "Read one publish action, unresolved actions that must be queried before retry, or due "
        "metric checkpoints for the account bound to this conversation. Use this after restart, "
        "timeout or provider disconnect. Unknown is not success and must not be blindly retried."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action_id": {"type": "string"},
            "include_unresolved": {"type": "boolean", "default": True},
            "include_due_metrics": {"type": "boolean", "default": False},
            "as_of": {
                "type": "string",
                "description": "Optional ISO-8601 cutoff for due metrics.",
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
        },
        "required": [],
    },
}

EXECUTE_PUBLISH_SCHEMA = {
    "name": "marketing_effect_publish",
    "description": (
        "Execute one prepared publish action through its trusted native provider. This is an "
        "irreversible external effect and always asks the user for one-shot confirmation. Do not "
        "call it unless marketing_prepare_publish returned the action_id and the user asked to publish."
    ),
    "parameters": {
        "type": "object",
        "properties": {"action_id": {"type": "string"}},
        "required": ["action_id"],
    },
}

QUERY_PUBLISH_SCHEMA = {
    "name": "marketing_publish_query",
    "description": (
        "Query the trusted provider for an executing or unknown publish action. Use this before "
        "any retry. A verified platform ID or stable work URL can recover the action to published."
    ),
    "parameters": {
        "type": "object",
        "properties": {"action_id": {"type": "string"}},
        "required": ["action_id"],
    },
}


def _list_accounts(_args: dict, **kwargs) -> str:
    result = AccountContextRepository().list_accounts()
    scope = read_tool_session_scope(
        task_id=kwargs.get("task_id"), session_id=kwargs.get("session_id")
    )
    if scope and scope.get("entity_id"):
        entity = OperatingEntityRepository().get(
            entity_id=str(scope["entity_id"]), user_id=str(scope["user_id"])
        )
        result["operating_entity"] = {
            "id": entity["id"],
            "label": entity["label"],
            "account_ids": entity.get("account_ids", []),
            "platforms": entity.get("platforms", []),
        }
    return json.dumps(result, ensure_ascii=False)


def _entity_account_ids(scope: dict | None, *, fallback: str) -> list[str]:
    """Resolve the bounded entity read set without changing the action account."""

    if not scope or not scope.get("entity_id"):
        return [fallback]
    entity = OperatingEntityRepository().get(
        entity_id=str(scope["entity_id"]), user_id=str(scope["user_id"])
    )
    values = [str(item) for item in entity.get("account_ids", []) if str(item)]
    return values or [fallback]


def _resolved_plan_platforms(value, *, entity_platforms: list[str]) -> list[str] | None:
    """Expand an all-platform marker to current channels while retaining named targets."""

    if value is None:
        return None
    raw = [value] if isinstance(value, str) else list(value or [])
    all_markers = {"*", "all", "all_platforms", "全平台", "所有平台"}
    has_all = any(str(item or "").strip().lower() in all_markers for item in raw)
    named = [item for item in raw if str(item or "").strip().lower() not in all_markers]
    if not has_all:
        return named
    return list(
        dict.fromkeys(
            str(item).strip()
            for item in [*entity_platforms, *named]
            if str(item).strip()
        )
    )


def _read_account_context(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        args,
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
    )
    scope = read_tool_session_scope(
        task_id=kwargs.get("task_id"), session_id=kwargs.get("session_id")
    )
    if scope and scope.get("entity_id"):
        result = AccountContextRepository().read_operating_entity(
            user_id=user_id,
            entity_id=str(scope["entity_id"]),
            focus_account_id=account_id,
        )
    else:
        result = AccountContextRepository().read(
            user_id=user_id,
            account_id=account_id,
        )
    return json.dumps(result, ensure_ascii=False)


def _update_account_lifecycle(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    repository = AccountLifecycleRepository()
    strategy = AccountStrategyRepository()
    action = str(args.get("action") or "")
    if action == "begin_project":
        result = repository.begin_project(
            user_id=user_id,
            account_id=account_id,
            business_goal=str(args.get("business_goal") or ""),
            constraints=args.get("constraints") or {},
        )
    elif action == "draft_creator_profile":
        result = strategy.draft_creator_profile(
            user_id=user_id,
            account_id=account_id,
            project_id=str(args.get("project_id") or ""),
            profile=args.get("profile") or {},
            source_refs=args.get("source_refs") or [],
        )
    elif action == "confirm_creator_profile":
        result = strategy.confirm_creator_profile(
            user_id=user_id,
            account_id=account_id,
            project_id=str(args.get("project_id") or ""),
            profile_id=str(args.get("profile_id") or ""),
            confirmed_by_user=args.get("confirmed_by_user") is True,
        )
    elif action == "draft_market_route":
        result = strategy.draft_market_route(
            user_id=user_id,
            account_id=account_id,
            project_id=str(args.get("project_id") or ""),
            route=args.get("route") or {},
            evidence_refs=args.get("evidence_refs") or [],
            confidence=float(args.get("confidence") or 0.3),
        )
    elif action == "select_market_route":
        result = strategy.select_market_route(
            user_id=user_id,
            account_id=account_id,
            project_id=str(args.get("project_id") or ""),
            route_id=str(args.get("route_id") or ""),
            confirmed_by_user=args.get("confirmed_by_user") is True,
        )
    elif action == "draft_audience_hypothesis":
        result = repository.draft_audience_hypothesis(
            user_id=user_id,
            account_id=account_id,
            project_id=str(args.get("project_id") or ""),
            segments=args.get("segments"),
            pains=args.get("pains"),
            scenarios=args.get("scenarios"),
            jobs=args.get("jobs"),
            current_alternatives=args.get("current_alternatives"),
            trust_barriers=args.get("trust_barriers"),
            desired_outcomes=args.get("desired_outcomes"),
            behavior_signals=args.get("behavior_signals"),
            existence_strategy_hypotheses=args.get("existence_strategy_hypotheses"),
            need_projection_hypotheses=args.get("need_projection_hypotheses"),
            cognitive_projection_hypotheses=args.get("cognitive_projection_hypotheses"),
            existence_hypotheses=args.get("existence_hypotheses"),
            cognitive_style_hypotheses=args.get("cognitive_style_hypotheses"),
            exclusions=args.get("exclusions"),
            data_gaps=args.get("data_gaps"),
        )
    elif action == "confirm_audience_hypothesis":
        result = repository.confirm_audience_hypothesis(
            user_id=user_id,
            account_id=account_id,
            project_id=str(args.get("project_id") or ""),
            hypothesis_id=str(args.get("hypothesis_id") or ""),
            confirmed_by_user=args.get("confirmed_by_user") is True,
        )
    elif action == "add_benchmark_account":
        result = strategy.add_benchmark_account(
            user_id=user_id,
            account_id=account_id,
            project_id=str(args.get("project_id") or ""),
            platform=str(args.get("platform") or ""),
            account_handle=str(args.get("account_handle") or ""),
            role=str(args.get("role") or ""),
            selection_reason=str(args.get("selection_reason") or ""),
            match_dimensions=args.get("match_dimensions") or {},
            evidence_refs=args.get("evidence_refs") or [],
            account_name=str(args.get("account_name") or ""),
            platform_account_id=str(args.get("platform_account_id") or ""),
            profile_url=str(args.get("profile_url") or ""),
        )
    elif action == "decide_benchmark_account":
        result = strategy.decide_benchmark_account(
            user_id=user_id,
            account_id=account_id,
            project_id=str(args.get("project_id") or ""),
            benchmark_id=str(args.get("benchmark_id") or ""),
            decision=str(args.get("decision") or ""),
            confirmed_by_user=args.get("confirmed_by_user") is True,
        )
    elif action == "add_benchmark_observation":
        result = strategy.add_benchmark_observation(
            user_id=user_id,
            account_id=account_id,
            project_id=str(args.get("project_id") or ""),
            benchmark_id=str(args.get("benchmark_id") or ""),
            dimension=str(args.get("dimension") or ""),
            value=args.get("value") or {},
            evidence_refs=args.get("evidence_refs") or [],
            confidence=float(args.get("confidence") or 0),
        )
    elif action == "draft_positioning":
        result = strategy.draft_positioning(
            user_id=user_id,
            account_id=account_id,
            project_id=str(args.get("project_id") or ""),
            positioning=args.get("positioning") or {},
        )
    elif action == "approve_positioning":
        result = strategy.approve_positioning(
            user_id=user_id,
            account_id=account_id,
            project_id=str(args.get("project_id") or ""),
            positioning_id=str(args.get("positioning_id") or ""),
            confirmed_by_user=args.get("confirmed_by_user") is True,
            accept_data_gaps=args.get("accept_data_gaps") is True,
        )
    elif action == "draft_content_system":
        result = strategy.draft_content_system(
            user_id=user_id,
            account_id=account_id,
            project_id=str(args.get("project_id") or ""),
            system=args.get("content_system") or {},
        )
    elif action == "approve_content_system":
        result = strategy.approve_content_system(
            user_id=user_id,
            account_id=account_id,
            project_id=str(args.get("project_id") or ""),
            system_id=str(args.get("system_id") or ""),
            confirmed_by_user=args.get("confirmed_by_user") is True,
        )
    elif action == "propose_experiment":
        result = strategy.propose_experiment(
            user_id=user_id,
            account_id=account_id,
            project_id=str(args.get("project_id") or ""),
            hypothesis=str(args.get("hypothesis") or ""),
            variable=args.get("variable") or {},
            variants=args.get("variants") or [],
            prediction=args.get("prediction") or {},
            success_criteria=args.get("success_criteria") or {},
        )
    elif action == "approve_experiment":
        result = strategy.approve_experiment(
            user_id=user_id,
            account_id=account_id,
            project_id=str(args.get("project_id") or ""),
            experiment_id=str(args.get("experiment_id") or ""),
            confirmed_by_user=args.get("confirmed_by_user") is True,
        )
    else:
        raise ValueError(f"unsupported lifecycle action: {action}")
    return json.dumps(
        {
            "action": action,
            "result": result,
            "account_context": AccountContextRepository().read(
                user_id=user_id, account_id=account_id
            ),
        },
        ensure_ascii=False,
    )


def _plan_content_production(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    context_repository = AccountContextRepository()
    action_context = context_repository.read(user_id=user_id, account_id=account_id)
    scope = read_tool_session_scope(
        task_id=kwargs.get("task_id"), session_id=kwargs.get("session_id")
    )
    entity_context: dict = {}
    entity_platforms: list[str] = []
    if scope and scope.get("entity_id"):
        entity_context = context_repository.read_operating_entity(
            user_id=user_id,
            entity_id=str(scope["entity_id"]),
            focus_account_id=account_id,
        )
        entity_platforms = list(
            (entity_context.get("operating_entity") or {}).get("platforms") or []
        )
    shared_context = entity_context.get("shared_operating_context") or action_context
    context = {
        **shared_context,
        "account_id": account_id,
        "connected": action_context.get("connected", False),
        "account": action_context.get("account"),
        "entity_id": (scope or {}).get("entity_id"),
    }
    experiment_id = str(args.get("experiment_id") or "").strip()
    if experiment_id:
        project_id = str((context.get("lifecycle") or {}).get("project_id") or "")
        experiment = AccountStrategyRepository().get_experiment(
            user_id=user_id,
            account_id=account_id,
            project_id=project_id,
            experiment_id=experiment_id,
        )
        if experiment["status"] != "running":
            raise ValueError("content production requires a running experiment")
        current_system_id = str(
            (context.get("lifecycle") or {}).get("content_system_id") or ""
        )
        if experiment.get("content_system_id") != current_system_id:
            raise ValueError("experiment does not belong to the current content system")
    evidence_refs = args.get("evidence_refs") or []
    if evidence_refs:
        evidence_refs = [
            item["id"]
            for item in EvidenceRepository().require_verified(
                user_id=user_id,
                account_id=account_id,
                evidence_ids=evidence_refs,
            )
        ]
    objective = str(args.get("objective") or "")
    requested_kind = str(args.get("kind") or "auto")
    requested_platforms = _resolved_plan_platforms(
        args.get("platforms"), entity_platforms=entity_platforms
    )
    asks_for_all_platforms = any(
        marker in objective for marker in ("全平台", "所有平台", "各平台", "每个平台")
    )
    if requested_platforms is None and (
        requested_kind == "cross_platform_campaign" or asks_for_all_platforms
    ):
        requested_platforms = entity_platforms
    result = ContentProductionPolicy().plan(
        objective=objective,
        kind=requested_kind,
        platforms=requested_platforms,
        audience=str(args.get("audience") or ""),
        evidence_refs=evidence_refs,
        constraints=args.get("constraints") or {},
        account_context=context,
        experiment_id=experiment_id,
    )
    checkpoint = ContentAssetRepository().save_production_plan(
        user_id=user_id,
        account_id=account_id,
        plan=result,
    )
    knowledge_context = KnowledgeBaseRepository().retrieve_for_preflight(
        user_id=user_id,
        account_id=account_id,
        platforms=result.get("target_platforms") or [],
        content_kind=result["kind"],
    )
    sound_context: dict = {}
    if result["kind"] == "faceless_video":
        sound_context = {
            "platforms": [
                ShortVideoSignalRepository().rank_sounds(
                    user_id=user_id,
                    account_id=account_id,
                    platform=platform,
                    objective=result["objective"],
                    limit=10,
                )
                for platform in result.get("target_platforms") or []
            ]
        }
        sound_context["candidates"] = [
            candidate
            for platform_result in sound_context["platforms"]
            for candidate in platform_result.get("candidates") or []
        ]
    calibration = AccountStrategyRepository().get_active_influence_calibration(
        user_id=user_id,
        account_id=account_id,
    )
    preflight = create_content_production_preflight(
        OperatingLoopRepository(),
        {
            "user_id": user_id,
            "account_id": account_id,
            "session_id": str(kwargs.get("session_id") or kwargs.get("task_id") or ""),
            "plan_id": checkpoint["plan_id"],
            "plan": checkpoint,
            "evidence_refs": evidence_refs,
            "sound_context": sound_context,
            "knowledge_context": knowledge_context,
            "influence_weights": calibration.get("weights") if calibration else None,
            "influence_calibration_id": calibration.get("id") if calibration else None,
        },
    )
    return json.dumps(
        {
            **checkpoint,
            "preflight": {
                "id": preflight["preflight_id"],
                "formula_version": preflight["formula_version"],
                "scores": preflight["scores"],
                "decision": preflight["preflight_decision"],
                "publish_eligible": preflight["decision"]["publish_eligible"],
                "influence_score": preflight["influence_score"],
                "platform_assessments": preflight["platform_assessments"],
                "recommendation_eligible": preflight["preflight_decision"].get("go")
                is True,
                "recommendation_status": (
                    "recommended"
                    if preflight["preflight_decision"].get("go") is True
                    else "research_only"
                ),
            },
            "operating_entity": entity_context.get("operating_entity"),
        },
        ensure_ascii=False,
    )


def _preflight_daily_topic_recommendations(args: dict, **kwargs) -> str:
    session_id = str(kwargs.get("session_id") or kwargs.get("task_id") or "").strip()
    if not session_id:
        raise ValueError("daily topic preflight requires a durable session")
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    scope = read_tool_session_scope(
        task_id=kwargs.get("task_id"), session_id=kwargs.get("session_id")
    )
    if not scope or not scope.get("entity_id"):
        raise ValueError("daily topic preflight requires an operating-entity scope")
    entity = OperatingEntityRepository().get(
        entity_id=str(scope["entity_id"]), user_id=user_id
    )
    requested = args.get("platforms")
    if requested is None:
        platforms = list(entity.get("platforms") or [])
    else:
        platforms = (
            _resolved_plan_platforms(
                requested, entity_platforms=list(entity.get("platforms") or [])
            )
            or []
        )
    if not platforms:
        raise ValueError(
            "daily topic preflight requires a linked platform or an explicit target platform"
        )
    batch = build_daily_topic_recommendation_batch(
        user_id=user_id,
        entity_id=str(scope["entity_id"]),
        account_id=account_id,
        session_id=session_id,
        as_of_date=datetime.now().astimezone().date().isoformat(),
        candidates=args.get("candidates") or [],
        target_platforms=platforms,
    )
    return json.dumps(
        {
            "contract": "marketing.daily_topic_recommendations.v1",
            "batch_id": batch["id"],
            "status": batch["status"],
            "recommended_count": batch["recommended_count"],
            "research_only_count": batch["research_only_count"],
            "delivery_sha256": batch["delivery_sha256"],
            "delivery_markdown": batch["delivery_text"],
            "candidate_receipts": [
                {
                    "rank": item["rank"],
                    "topic": item["topic"],
                    "plan_id": item["plan_id"],
                    "preflight_id": item["preflight_id"],
                    "decision_status": item["decision_status"],
                    "recommendation_eligible": item["recommendation_eligible"],
                    "recommendation_type": (item.get("candidate") or {}).get(
                        "recommendation_type"
                    ),
                    "recommended_platforms": (item.get("candidate") or {}).get(
                        "recommended_platforms"
                    )
                    or [],
                    "platform_matches": (item.get("candidate") or {}).get(
                        "platform_matches"
                    )
                    or [],
                }
                for item in batch["candidates"]
            ],
            "final_response_contract": (
                "Return delivery_markdown verbatim with no prefix, suffix, explanation, "
                "rewriting, code fence, or extra whitespace."
            ),
        },
        ensure_ascii=False,
    )


def _read_content_assets(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    scope = read_tool_session_scope(
        task_id=kwargs.get("task_id"), session_id=kwargs.get("session_id")
    )
    limit = int(args.get("limit") or 20)
    repository = ContentAssetRepository()
    account_ids = _entity_account_ids(scope, fallback=account_id)
    assets = [
        asset
        for scoped_account_id in account_ids
        for asset in repository.list(
            user_id=user_id,
            account_id=scoped_account_id,
            status=str(args.get("status") or "") or None,
            platform=str(args.get("platform") or "") or None,
            limit=limit,
        ).get("assets", [])
    ]
    assets.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    result = {
        "user_id": user_id,
        "entity_id": (scope or {}).get("entity_id"),
        "action_account_id": account_id,
        "account_ids": account_ids,
        "assets": assets[:limit],
        "total": min(len(assets), limit),
    }
    return json.dumps(result, ensure_ascii=False)


def _read_video_productions(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    result = VideoProductionRepository().list(
        user_id=user_id,
        account_id=account_id,
        status=str(args.get("status") or "") or None,
        limit=int(args.get("limit") or 20),
    )
    return json.dumps(result, ensure_ascii=False)


def _read_evidence_pack(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    scope = read_tool_session_scope(
        task_id=kwargs.get("task_id"), session_id=kwargs.get("session_id")
    )
    limit = int(args.get("limit") or 20)
    repository = EvidenceRepository()
    account_ids = _entity_account_ids(scope, fallback=account_id)
    records = [
        record
        for scoped_account_id in account_ids
        for record in repository.list(
            user_id=user_id,
            account_id=scoped_account_id,
            status=str(args.get("status") or "verified"),
            limit=limit,
        ).get("records", [])
    ]
    records.sort(key=lambda item: str(item.get("captured_at") or ""), reverse=True)
    result = {
        "user_id": user_id,
        "entity_id": (scope or {}).get("entity_id"),
        "action_account_id": account_id,
        "account_ids": account_ids,
        "records": records[:limit],
        "total": min(len(records), limit),
        "verification_semantics": (
            "verified means source integrity is complete; it does not assert every claim is true"
        ),
    }
    return json.dumps(result, ensure_ascii=False)


def _read_sound_trends(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    result = ShortVideoSignalRepository().rank_sounds(
        user_id=user_id,
        account_id=account_id,
        platform=str(args.get("platform") or ""),
        objective=str(args.get("objective") or ""),
        window_hours=int(args.get("window_hours") or 72),
        limit=int(args.get("limit") or 20),
    )
    return json.dumps(result, ensure_ascii=False)


def _read_public_content(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    result = PublicContentObservationRepository().list_cases(
        user_id=user_id,
        account_id=account_id,
        platform=str(args.get("platform") or "") or None,
        limit=int(args.get("limit") or 50),
    )
    return json.dumps(result, ensure_ascii=False)


def _interpret_public_content(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    result = PublicContentObservationRepository().interpret_observation(
        user_id=user_id,
        account_id=account_id,
        observation_id=str(args.get("observation_id") or ""),
        model_observation=args.get("model_observation") or {},
        confidence=float(args.get("confidence") or 0),
        project_id=str(args.get("project_id") or ""),
        benchmark_id=str(args.get("benchmark_id") or ""),
        benchmark_projection=args.get("benchmark_projection"),
        session_id=str(kwargs.get("session_id") or kwargs.get("task_id") or ""),
    )
    return json.dumps(result, ensure_ascii=False)


def _read_account_portfolio(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        args,
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    result = AccountPortfolioRepository().latest(
        user_id=user_id,
        account_id=account_id,
    )
    return json.dumps(result, ensure_ascii=False)


def _read_knowledge(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    base = str(args.get("knowledge_base") or "")
    result = KnowledgeBaseRepository().retrieve(
        knowledge_base=base,
        user_id=user_id,
        account_id=account_id if base == "account" else None,
        platform=str(args.get("platform") or "") or None,
        content_kind=str(args.get("content_kind") or "") or None,
        topics=args.get("topics") or [],
        limit=int(args.get("limit") or 50),
    )
    return json.dumps(result, ensure_ascii=False)


def _require_actionable_preflight(
    *, user_id: str, account_id: str, plan_id: str
) -> tuple[OperatingLoopRepository, dict]:
    loop = OperatingLoopRepository()
    preflight = loop.latest_preflight_for_plan(
        plan_id=plan_id,
        user_id=user_id,
        account_id=account_id,
    )
    decision = preflight.get("decision") or {}
    product_decision = decision.get("preflight_decision") or decision
    if product_decision.get("go") is not True:
        next_action = str(product_decision.get("next_action") or "重新运行预演")
        raise ValueError(f"preflight blocked content production: {next_action}")
    return loop, preflight


def _validate_draft_evidence(
    *, user_id: str, account_id: str, evidence_refs: list[str]
) -> None:
    EvidenceRepository().require_verified(
        user_id=user_id,
        account_id=account_id,
        evidence_ids=evidence_refs,
    )


def _create_content_draft(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    plan_id = str(args.get("plan_id") or "")
    _validate_draft_evidence(
        user_id=user_id,
        account_id=account_id,
        evidence_refs=args.get("evidence_refs") or [],
    )
    loop, preflight = _require_actionable_preflight(
        user_id=user_id, account_id=account_id, plan_id=plan_id
    )
    result = ContentAssetRepository().create_draft(
        user_id=user_id,
        account_id=account_id,
        title=str(args.get("title") or ""),
        plan_id=plan_id,
        asset_type=str(args.get("type") or "script"),
        platform=str(args.get("platform") or ""),
        production_kind=str(args.get("production_kind") or ""),
        content=args.get("content"),
        topic=str(args.get("topic") or ""),
        hook=str(args.get("hook") or ""),
        evidence_refs=args.get("evidence_refs") or [],
        memory_refs=args.get("memory_refs") or [],
        reaction_scenarios=args.get("reaction_scenarios") or [],
        revision_of=str(args.get("revision_of") or ""),
    )
    loop.mark_preflight_used(preflight["id"])
    return json.dumps({**result, "preflight_id": preflight["id"]}, ensure_ascii=False)


def _create_article_draft(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    plan_id = str(args.get("plan_id") or "")
    _validate_draft_evidence(
        user_id=user_id,
        account_id=account_id,
        evidence_refs=args.get("evidence_refs") or [],
    )
    loop, preflight = _require_actionable_preflight(
        user_id=user_id, account_id=account_id, plan_id=plan_id
    )
    result = ContentAssetRepository().create_article_bundle(
        user_id=user_id,
        account_id=account_id,
        title=str(args.get("title") or ""),
        plan_id=plan_id,
        parent_body_markdown=str(args.get("parent_body_markdown") or ""),
        platform_variants=args.get("platform_variants") or {},
        evidence_refs=args.get("evidence_refs") or [],
        topic=str(args.get("topic") or ""),
        hook=str(args.get("hook") or ""),
        revision_of=str(args.get("revision_of") or ""),
        reaction_scenarios=args.get("reaction_scenarios") or [],
    )
    loop.mark_preflight_used(preflight["id"])
    return json.dumps({**result, "preflight_id": preflight["id"]}, ensure_ascii=False)


def _prepare_faceless_render(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    result = VideoProductionRepository().prepare(
        user_id=user_id,
        account_id=account_id,
        source_asset_id=str(args.get("source_asset_id") or ""),
        edl=args.get("edl") if "edl" in args else None,
        video_ir=args.get("video_ir") if "video_ir" in args else None,
        renderer=str(args.get("renderer") or "ffmpeg_timeline_v1"),
    )
    return json.dumps(result, ensure_ascii=False)


def _search_materials(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    result = MaterialSourcingRepository().search(
        user_id=user_id,
        account_id=account_id,
        query=str(args.get("query") or ""),
        role=str(args.get("role") or "broll"),
        orientation=str(args.get("orientation") or ""),
        target_duration=float(args.get("target_duration") or 0),
        limit=int(args.get("limit") or 12),
        locale=str(args.get("locale") or "zh-CN"),
    )
    return json.dumps(result, ensure_ascii=False)


def _materialize_material(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    result = MaterialSourcingRepository().materialize(
        candidate_id=str(args.get("candidate_id") or ""),
        user_id=user_id,
        account_id=account_id,
        rights_reviewed=args.get("rights_reviewed") is True,
    )
    return json.dumps(result, ensure_ascii=False)


def _keep_material(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    if args.get("confirmed") is not True:
        raise ValueError("explicit material retention confirmation is required")
    asset = MediaAssetRepository().get(
        asset_id=str(args.get("asset_id") or ""),
        user_id=user_id,
    )
    if asset.get("account_id") not in {None, account_id}:
        raise KeyError("media asset not found in account scope")
    result = MediaAssetRepository().promote(
        asset_id=asset["id"],
        user_id=user_id,
        target_tier=str(args.get("target_tier") or "library"),
    )
    return json.dumps({"asset": result}, ensure_ascii=False)


def _prepare_video_voice(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    result = ProductionAudioRepository().prepare_voice(
        user_id=user_id,
        account_id=account_id,
        name=str(args.get("name") or ""),
        script_text=str(args.get("script_text") or ""),
    )
    return json.dumps(
        {
            "job": result,
            "effect_executed": False,
            "next_action": "Request one-shot approval for this exact script before TTS generation.",
        },
        ensure_ascii=False,
    )


def _execute_video_voice(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    repository = ProductionAudioRepository()
    repository.approve(
        job_id=str(args.get("job_id") or ""),
        user_id=user_id,
        account_id=account_id,
        approval_ref=str(args.get("approval_ref") or ""),
        confirmed_by_user=args.get("confirmed_by_user") is True,
    )
    result = repository.execute(
        job_id=str(args.get("job_id") or ""),
        user_id=user_id,
        account_id=account_id,
    )
    return json.dumps(result, ensure_ascii=False)


def _execute_faceless_render(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    repository = VideoProductionRepository()
    repository.approve(
        production_id=str(args.get("production_id") or ""),
        user_id=user_id,
        account_id=account_id,
        approval_ref=str(args.get("approval_ref") or ""),
        confirmed_by_user=args.get("confirmed_by_user") is True,
    )
    result = repository.execute(
        production_id=str(args.get("production_id") or ""),
        user_id=user_id,
        account_id=account_id,
        session_id=str(kwargs.get("session_id") or kwargs.get("task_id") or ""),
    )
    return json.dumps(result, ensure_ascii=False)


def _prepare_publish(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    action = PublishingRepository().prepare_action(
        user_id=user_id,
        account_id=account_id,
        asset_id=str(args.get("asset_id") or ""),
        platform=str(args.get("platform") or ""),
        provider=str(args.get("provider") or "playwright_mcp"),
        session_id=str(kwargs.get("session_id") or kwargs.get("task_id") or ""),
        tool_call_id=str(kwargs.get("tool_call_id") or ""),
    )
    return json.dumps(
        {
            "action": action,
            "effect_executed": False,
            "next_action": (
                "Request one-shot user approval, then execute the trusted native publishing provider."
            ),
        },
        ensure_ascii=False,
    )


def _read_publish_state(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    repository = PublishingRepository()
    action_id = str(args.get("action_id") or "").strip()
    result: dict = {"user_id": user_id, "account_id": account_id}
    if action_id:
        action = repository.get_action(action_id)
        if action["user_id"] != user_id or action["account_id"] != account_id:
            raise ValueError("publish action is outside the bound conversation account")
        result["action"] = action
        result["metric_checkpoints"] = repository.list_metric_checkpoints(action_id)
    if args.get("include_unresolved", True):
        result["unresolved_actions"] = repository.list_unresolved_actions(
            user_id=user_id,
            account_id=account_id,
            limit=int(args.get("limit") or 20),
        )
    if args.get("include_due_metrics") is True:
        result["due_metric_checkpoints"] = repository.list_due_metric_checkpoints(
            as_of=str(args.get("as_of") or "") or None,
            user_id=user_id,
            account_id=account_id,
            limit=int(args.get("limit") or 20),
        )
    return json.dumps(result, ensure_ascii=False)


def _publish_action_in_scope(args: dict, **kwargs) -> tuple[PublishingRepository, dict]:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    repository = PublishingRepository()
    action = repository.get_action(str(args.get("action_id") or ""))
    if action["user_id"] != user_id or action["account_id"] != account_id:
        raise ValueError("publish action is outside the bound conversation account")
    return repository, action


def _execute_publish(args: dict, **kwargs) -> str:
    repository, action = _publish_action_in_scope(args, **kwargs)
    if action["status"] != "prepared":
        raise ValueError(f"publish action cannot execute from {action['status']}")
    provider = get_publish_provider(action["provider"])
    from tools.approval import request_elicitation_consent

    consent = request_elicitation_consent(
        message=(
            f"Publish {action['platform']} asset {action['asset_id']} "
            f"version {action['asset_version']}"
        ),
        description=(
            "This will create a public platform post. Approval is valid for this action once only; "
            "silence, timeout or denial will not publish."
        ),
        surface="marketing-publish",
    )
    if consent != "accept":
        return json.dumps(
            {
                "error": "Publishing was not approved by the user.",
                "outcome": "cancel" if consent == "cancel" else "decline",
                "action_id": action["id"],
            },
            ensure_ascii=False,
        )
    approval_ref = (
        f"hermes-once:{kwargs.get('session_id') or kwargs.get('task_id') or 'session'}:"
        f"{kwargs.get('tool_call_id') or action['id']}"
    )
    executing = repository.mark_execution_started(
        action["id"], approval_ref=approval_ref
    )
    try:
        provider_result = provider.publish(executing)
    except Exception as exc:
        provider_result = {
            "outcome": "unknown",
            "failure_code": "provider_exception_after_start",
            "provider_error": f"{type(exc).__name__}: {exc}"[:500],
        }
    if not isinstance(provider_result, dict):
        provider_result = {
            "outcome": "unknown",
            "failure_code": "invalid_provider_result",
        }
    return json.dumps(
        {"marketing_publish_result": {"action_id": action["id"], **provider_result}},
        ensure_ascii=False,
    )


def _query_publish(args: dict, **kwargs) -> str:
    _repository, action = _publish_action_in_scope(args, **kwargs)
    if action["status"] not in {"executing", "unknown"}:
        raise ValueError(
            f"publish action does not require recovery from {action['status']}"
        )
    provider = get_publish_provider(action["provider"])
    try:
        provider_result = provider.query(action)
    except Exception as exc:
        provider_result = {
            "outcome": "unknown",
            "failure_code": "provider_query_failed",
            "provider_error": f"{type(exc).__name__}: {exc}"[:500],
        }
    if not isinstance(provider_result, dict):
        provider_result = {
            "outcome": "unknown",
            "failure_code": "invalid_provider_query_result",
        }
    return json.dumps(
        {"marketing_publish_result": {"action_id": action["id"], **provider_result}},
        ensure_ascii=False,
    )


registry.register(
    name="marketing_read_accounts",
    toolset="marketing",
    schema=LIST_ACCOUNTS_SCHEMA,
    handler=_list_accounts,
    description="List connected Marketing OS accounts without exposing login secrets.",
    emoji="📣",
)

registry.register(
    name="marketing_read_account_context",
    toolset="marketing",
    schema=READ_ACCOUNT_CONTEXT_SCHEMA,
    handler=_read_account_context,
    description="Read verified audience, positioning and lifecycle context for one account.",
    emoji="🧭",
)

registry.register(
    name="marketing_update_account_lifecycle",
    toolset="marketing",
    schema=UPDATE_ACCOUNT_LIFECYCLE_SCHEMA,
    handler=_update_account_lifecycle,
    description="Create and confirm versioned account goals and audience hypotheses.",
    emoji="🧬",
)

registry.register(
    name="marketing_plan_content_production",
    toolset="marketing",
    schema=PLAN_CONTENT_PRODUCTION_SCHEMA,
    handler=_plan_content_production,
    description="Plan one account-scoped content production job with explicit evidence and rights gates.",
    emoji="🗺️",
)

registry.register(
    name="marketing_preflight_daily_topic_recommendations",
    toolset="marketing",
    schema=PREFLIGHT_DAILY_TOPIC_RECOMMENDATIONS_SCHEMA,
    handler=_preflight_daily_topic_recommendations,
    description="Preflight and receipt-bind every candidate in one daily recommendation batch.",
    emoji="🎯",
)

registry.register(
    name="marketing_read_content_assets",
    toolset="marketing",
    schema=READ_CONTENT_ASSETS_SCHEMA,
    handler=_read_content_assets,
    description="Resume durable content work for the current account scope.",
    emoji="🗂️",
)

registry.register(
    name="marketing_read_video_productions",
    toolset="marketing",
    schema=READ_VIDEO_PRODUCTIONS_SCHEMA,
    handler=_read_video_productions,
    description="Recover durable faceless-video render jobs for the current account.",
    emoji="🎞️",
)

registry.register(
    name="marketing_read_evidence_pack",
    toolset="marketing",
    schema=READ_EVIDENCE_PACK_SCHEMA,
    handler=_read_evidence_pack,
    description="Read source-integrity evidence captured by native Hermes collectors.",
    emoji="🔎",
)

registry.register(
    name="marketing_read_sound_trends",
    toolset="marketing",
    schema=READ_SOUND_TRENDS_SCHEMA,
    handler=_read_sound_trends,
    description="Read evidence-backed short-video sound momentum for the current account.",
    emoji="🎵",
)

registry.register(
    name="marketing_read_public_content",
    toolset="marketing",
    schema=READ_PUBLIC_CONTENT_SCHEMA,
    handler=_read_public_content,
    description="Read public creator natural experiments captured from real browser pages.",
    emoji="🔭",
)

registry.register(
    name="marketing_interpret_public_content",
    toolset="marketing",
    schema=INTERPRET_PUBLIC_CONTENT_SCHEMA,
    handler=_interpret_public_content,
    description="Create governed model and benchmark learning candidates from public observations.",
    emoji="🧪",
)

registry.register(
    name="marketing_read_account_portfolio",
    toolset="marketing",
    schema=READ_ACCOUNT_PORTFOLIO_SCHEMA,
    handler=_read_account_portfolio,
    description="Read evidence-backed owned work and the latest account execution baseline.",
    emoji="📝",
)

registry.register(
    name="marketing_read_knowledge",
    toolset="marketing",
    schema=READ_KNOWLEDGE_SCHEMA,
    handler=_read_knowledge,
    description=(
        "Read governed platform, market, account, or content knowledge without allowing model writes."
    ),
    emoji="📚",
)

registry.register(
    name="marketing_draft_content_create",
    toolset="marketing",
    schema=CREATE_CONTENT_DRAFT_SCHEMA,
    handler=_create_content_draft,
    description="Persist a reversible content draft in the current account scope.",
    emoji="✍️",
)

registry.register(
    name="marketing_draft_article_create",
    toolset="marketing",
    schema=CREATE_ARTICLE_DRAFT_SCHEMA,
    handler=_create_article_draft,
    description="Persist a validated parent article and platform-native variants.",
    emoji="📝",
)

registry.register(
    name="marketing_search_materials",
    toolset="marketing",
    schema=SEARCH_MATERIALS_SCHEMA,
    handler=_search_materials,
    description="Search and rank user-owned and licensed visual material candidates.",
    emoji="🔎",
)

registry.register(
    name="marketing_effect_materialize",
    toolset="marketing",
    schema=MATERIALIZE_MATERIAL_SCHEMA,
    handler=_materialize_material,
    description="Materialize one explicitly rights-reviewed provider candidate.",
    emoji="📥",
)

registry.register(
    name="marketing_effect_keep_material",
    toolset="marketing",
    schema=KEEP_MATERIAL_SCHEMA,
    handler=_keep_material,
    description="Keep one explicit temporary material in the local library or connected cloud.",
    emoji="📌",
)

registry.register(
    name="marketing_prepare_video_voice",
    toolset="marketing",
    schema=PREPARE_VIDEO_VOICE_SCHEMA,
    handler=_prepare_video_voice,
    description="Prepare a hash-bound voiceover intent without calling TTS.",
    emoji="🗣️",
)

registry.register(
    name="marketing_effect_video_voice",
    toolset="marketing",
    schema=EXECUTE_VIDEO_VOICE_SCHEMA,
    handler=_execute_video_voice,
    description="Generate one approved voiceover and import its real audio receipt.",
    emoji="🎙️",
)

registry.register(
    name="marketing_prepare_faceless_render",
    toolset="marketing",
    schema=PREPARE_FACELESS_RENDER_SCHEMA,
    handler=_prepare_faceless_render,
    description="Persist and validate an immutable faceless-video edit decision list.",
    emoji="🎬",
)

registry.register(
    name="marketing_effect_faceless_render",
    toolset="marketing",
    schema=EXECUTE_FACELESS_RENDER_SCHEMA,
    handler=_execute_faceless_render,
    description="Render one explicitly approved faceless-video EDL and settle its receipt.",
    emoji="🎥",
)

registry.register(
    name="marketing_prepare_publish",
    toolset="marketing",
    schema=PREPARE_PUBLISH_SCHEMA,
    handler=_prepare_publish,
    description="Prepare an idempotent publish action without executing the external effect.",
    emoji="📤",
)

registry.register(
    name="marketing_read_publish_state",
    toolset="marketing",
    schema=READ_PUBLISH_STATE_SCHEMA,
    handler=_read_publish_state,
    description="Recover unresolved publishing actions and due metric checkpoints.",
    emoji="🧾",
)

registry.register(
    name="marketing_effect_publish",
    toolset="marketing",
    schema=EXECUTE_PUBLISH_SCHEMA,
    handler=_execute_publish,
    check_fn=has_publish_providers,
    description="Execute a one-shot approved external publish effect through a trusted provider.",
    emoji="🚀",
)

registry.register(
    name="marketing_publish_query",
    toolset="marketing",
    schema=QUERY_PUBLISH_SCHEMA,
    handler=_query_publish,
    check_fn=has_publish_providers,
    description="Recover an unknown publish outcome by querying the original provider.",
    emoji="🔍",
)
