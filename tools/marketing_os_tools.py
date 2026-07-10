"""Native read tools for the Marketing OS account operating context."""

from __future__ import annotations

import json

from marketing_os.domains import AccountContextRepository
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


def _list_accounts(_args: dict, **_kwargs) -> str:
    return json.dumps(AccountContextRepository().list_accounts(), ensure_ascii=False)


def _read_account_context(args: dict, **_kwargs) -> str:
    result = AccountContextRepository().read(
        user_id=str(args.get("user_id") or "default"),
        account_id=str(args.get("account_id") or ""),
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
