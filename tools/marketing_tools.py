"""Native tools for the Marketing OS account operating context."""

from __future__ import annotations

import json

from agent.marketing.domains import (
    AccountContextRepository,
    AccountLifecycleRepository,
    ContentAssetRepository,
    ContentProductionPolicy,
    EvidenceRepository,
)
from agent.marketing.session_scope import enforce_tool_account_scope
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
        "Advance the bound account's versioned onboarding lifecycle. Use begin_project after the "
        "user states a real operating goal; draft_audience_hypothesis to save a reviewable hypothesis; "
        "and confirm_audience_hypothesis only after the user explicitly accepts that exact draft. "
        "The account is taken from the current conversation and cannot be overridden."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "begin_project",
                    "draft_audience_hypothesis",
                    "confirm_audience_hypothesis",
                ],
            },
            "business_goal": {"type": "string"},
            "constraints": {"type": "object"},
            "project_id": {"type": "string"},
            "hypothesis_id": {"type": "string"},
            "segments": {"type": "array", "items": {}},
            "pains": {"type": "array", "items": {}},
            "scenarios": {"type": "array", "items": {}},
            "exclusions": {"type": "array", "items": {}},
            "data_gaps": {"type": "array", "items": {}},
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
        "selects a lane and shared capabilities, and exposes audience/evidence/rights/cost gates. "
        "The work order is persisted as a checkpoint and returns a plan_id required for drafting."
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
            "content": {"type": "object"},
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
    action = str(args.get("action") or "")
    if action == "begin_project":
        result = repository.begin_project(
            user_id=user_id,
            account_id=account_id,
            business_goal=str(args.get("business_goal") or ""),
            constraints=args.get("constraints") or {},
        )
    elif action == "draft_audience_hypothesis":
        result = repository.draft_audience_hypothesis(
            user_id=user_id,
            account_id=account_id,
            project_id=str(args.get("project_id") or ""),
            segments=args.get("segments"),
            pains=args.get("pains"),
            scenarios=args.get("scenarios"),
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
    )
    checkpoint = ContentAssetRepository().save_production_plan(
        user_id=user_id,
        account_id=account_id,
        plan=result,
    )
    return json.dumps(checkpoint, ensure_ascii=False)


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


def _create_content_draft(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    result = ContentAssetRepository().create_draft(
        user_id=user_id,
        account_id=account_id,
        title=str(args.get("title") or ""),
        plan_id=str(args.get("plan_id") or ""),
        asset_type=str(args.get("type") or "script"),
        platform=str(args.get("platform") or ""),
        production_kind=str(args.get("production_kind") or ""),
        content=args.get("content"),
        topic=str(args.get("topic") or ""),
        hook=str(args.get("hook") or ""),
        evidence_refs=args.get("evidence_refs") or [],
        memory_refs=args.get("memory_refs") or [],
    )
    return json.dumps(result, ensure_ascii=False)


def _create_article_draft(args: dict, **kwargs) -> str:
    user_id, account_id = enforce_tool_account_scope(
        {},
        task_id=kwargs.get("task_id"),
        session_id=kwargs.get("session_id"),
        require_bound=True,
    )
    result = ContentAssetRepository().create_article_bundle(
        user_id=user_id,
        account_id=account_id,
        title=str(args.get("title") or ""),
        plan_id=str(args.get("plan_id") or ""),
        parent_body_markdown=str(args.get("parent_body_markdown") or ""),
        platform_variants=args.get("platform_variants") or {},
        evidence_refs=args.get("evidence_refs") or [],
        topic=str(args.get("topic") or ""),
        hook=str(args.get("hook") or ""),
        revision_of=str(args.get("revision_of") or ""),
    )
    return json.dumps(result, ensure_ascii=False)


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
