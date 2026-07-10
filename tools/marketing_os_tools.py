"""Native tools for the Marketing OS account operating context."""

from __future__ import annotations

import json

from marketing_os.domains import AccountContextRepository, AccountLifecycleRepository
from marketing_os.session_scope import enforce_tool_account_scope
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
