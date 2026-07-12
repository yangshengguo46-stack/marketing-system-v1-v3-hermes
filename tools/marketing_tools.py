"""Native tools for the Marketing OS account operating context."""

from __future__ import annotations

import json

from agent.marketing.domains import (
    AccountContextRepository,
    AccountLifecycleRepository,
    AccountStrategyRepository,
    ContentAssetRepository,
    ContentProductionPolicy,
    EvidenceRepository,
    KnowledgeBaseRepository,
    PublishingRepository,
    ShortVideoSignalRepository,
)
from agent.marketing.session_scope import enforce_tool_account_scope
from agent.marketing.providers import get_publish_provider, has_publish_providers
from agent.marketing.intelligence import (
    OperatingLoopRepository,
    create_content_production_preflight,
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
        "Read one account's verified operating context: connected account summary, lifecycle stage, "
        "confirmed audience hypothesis, approved positioning, Account DNA and the latest first-party "
        "audience snapshot. Use it before proposing positioning, topics, content or growth actions. "
        "Missing fields are evidence gaps and must not be invented."
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
        "required": ["account_id"],
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
        "or premium human/digital-human video. It reads the current conversation's account context, "
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
                "enum": ["auto", "article_soft", "faceless_video", "premium_human_video"],
                "default": "auto",
            },
            "platforms": {"type": "array", "items": {"type": "string"}},
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

READ_CONTENT_ASSETS_SCHEMA = {
    "name": "marketing_read_content_assets",
    "description": (
        "List durable content drafts and assets for the account bound to this conversation. "
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

READ_EVIDENCE_PACK_SCHEMA = {
    "name": "marketing_read_evidence_pack",
    "description": (
        "Read evidence records automatically captured from successful native collectors for the "
        "account bound to this conversation. Cite the returned evidence IDs in production tools. "
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
            "platform": {"type": "string", "enum": ["douyin", "bilibili", "xiaohongshu", "kuaishou", "wechat_channels", "tiktok", "youtube"]},
            "objective": {"type": "string"},
            "window_hours": {"type": "integer", "minimum": 1, "maximum": 720, "default": 72},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
        },
        "required": ["platform"],
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

CREATE_CONTENT_DRAFT_SCHEMA = {
    "name": "marketing_draft_content_create",
    "description": (
        "Save a substantive, reversible video/image/caption draft for the account bound to this "
        "conversation. Article drafts must use marketing_draft_article_create so parent/variant and "
        "citation checks cannot be bypassed. At least one verified EvidencePack ID is required. The "
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
                "enum": ["article_soft", "faceless_video", "premium_human_video"],
            },
            "topic": {"type": "string"},
            "hook": {"type": "string"},
            "content": {
                "type": "object",
                "description": (
                    "Draft payload. Video drafts should include sound_plan with mode, mix_role and "
                    "opening_cue_ms; trend_sound additionally requires a verified sound_id returned "
                    "by marketing_read_sound_trends."
                ),
            },
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
            "memory_refs": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "plan_id", "platform", "production_kind", "content"],
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
        "become review_ready. Never invent percentages, time intervals or market prevalence."
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
        },
        "required": [
            "title",
            "plan_id",
            "parent_body_markdown",
            "platform_variants",
            "evidence_refs",
        ],
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
                    "zhihu", "wechat_official", "douyin", "bilibili", "xiaohongshu",
                    "kuaishou", "wechat_channels", "tiktok", "youtube",
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
            "as_of": {"type": "string", "description": "Optional ISO-8601 cutoff for due metrics."},
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


def _list_accounts(_args: dict, **_kwargs) -> str:
    return json.dumps(AccountContextRepository().list_accounts(), ensure_ascii=False)


def _read_account_context(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        args,
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
    )
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
    context = AccountContextRepository().read(user_id=user_id, account_id=account_id)
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
    result = ContentProductionPolicy().plan(
        objective=str(args.get("objective") or ""),
        kind=str(args.get("kind") or "auto"),
        platforms=args.get("platforms"),
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
    if result["kind"] in {"faceless_video", "premium_human_video"}:
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
            },
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
    result = ContentAssetRepository().list(
        user_id=user_id,
        account_id=account_id,
        status=str(args.get("status") or "") or None,
        platform=str(args.get("platform") or "") or None,
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
    result = EvidenceRepository().list(
        user_id=user_id,
        account_id=account_id,
        status=str(args.get("status") or "verified"),
        limit=int(args.get("limit") or 20),
    )
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
    )
    loop.mark_preflight_used(preflight["id"])
    return json.dumps({**result, "preflight_id": preflight["id"]}, ensure_ascii=False)


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
        raise ValueError(f"publish action does not require recovery from {action['status']}")
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
    name="marketing_read_content_assets",
    toolset="marketing",
    schema=READ_CONTENT_ASSETS_SCHEMA,
    handler=_read_content_assets,
    description="Resume durable content work for the current account scope.",
    emoji="🗂️",
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
