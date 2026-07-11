"""Canonical identity for the Hermes-native Marketing OS product.

Hermes is the primary runtime. Marketing OS capabilities extend its source,
conversation loop and ecosystem directly; they are not a second agent or an
external service wrapped around Hermes.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Mapping

PRODUCT_ID = "marketing-os"
PRODUCT_NAME = "Marketing OS"

PRODUCT_ECOSYSTEM_COMPATIBILITY = {
    "mcp": {
        "compatibility": "hermes-native",
        "install_and_discovery": "preserved",
        "update_channel": "mcp-server-or-product-release",
    },
    "skills": {
        "compatibility": "hermes-native",
        "hub_install_update": "preserved",
        "user_skills": "preserved",
    },
    "plugins": {
        "compatibility": "hermes-native",
        "install_update": "preserved",
    },
    "core": {
        "upstream": "NousResearch/hermes-agent",
        "update_channel": "marketing-os-product-release",
        "raw_upstream_apply": "blocked-in-product-runtime",
    },
}

PRODUCT_CORE_UPDATE_MESSAGE = (
    "Marketing OS directly extends the Hermes source tree. Core Hermes updates "
    "must be integrated and regression-tested in a Marketing OS release; applying "
    "raw upstream in place could remove the native marketing enhancements. MCP "
    "servers, Hub skills, user skills and plugins keep their independent update paths."
)

PRODUCT_ARCHITECTURE_PRINCIPLES = (
    "Modify the native capability owner first; never add an outer adapter merely to avoid changing upstream source.",
    "Electron is presentation and interaction only; it never owns product state, automation, accounts, browsers or tasks.",
    "One Hermes-native runtime owns conversation, tasks, memory, skills and marketing workflows.",
    "Account operations, audience modeling, evidence, content and learning are native Agent capabilities, never external attachments.",
    "Both Hermes core code and Marketing OS enhancements may be decomposed or rewritten.",
    "Preserve product philosophy and verified user outcomes, not historical directories or adapters.",
    "Account modeling, evidence, creation, publishing receipts, metrics and learning form one loop.",
    "Preserve Hermes MCP, skill and plugin contracts so ecosystem capabilities remain independently maintainable.",
)


def bundled_browser_mcp_config(
    env: Mapping[str, str] | None = None,
) -> dict[str, object] | None:
    """Return the Hermes-owned scoped Playwright MCP configuration."""

    values = os.environ if env is None else env
    root = Path(__file__).resolve().parents[1]
    entry = root / "mcp" / "marketing-browser" / "src" / "server.js"
    node = str(values.get("HERMES_NODE_EXECUTABLE") or "").strip() or shutil.which("node")
    if not node or not entry.is_file():
        return None
    profile_root = str(
        values.get("HERMES_BROWSER_PROFILE_ROOT")
        or (Path(values.get("HERMES_HOME") or Path.home() / ".hermes") / "browser-profiles")
    )
    return {
        "command": node,
        "args": [str(entry), "--schema-only"],
        "scoped_args": [str(entry)],
        "session_scope": "marketing_account",
        "env": {
            "HERMES_BROWSER_PROFILE_ROOT": profile_root,
            "HERMES_BROWSER_OUTPUT_ROOT": str(Path(profile_root).parent / "browser-output"),
        },
        "supports_parallel_tool_calls": False,
        "connect_timeout": 45,
        "timeout": 120,
    }

PRODUCT_AGENT_IDENTITY = (
    "You are Marketing OS, a long-running AI operating system for social-media "
    "account growth and content operations. You do not behave like a generic "
    "chatbot or a collection of disconnected marketing buttons. You learn the "
    "user's preferences, model each account and audience, gather traceable "
    "evidence, create platform-native content, coordinate approved actions, "
    "collect real publishing receipts and metrics, and use governed retrospectives "
    "to improve the next cycle. Be natural in conversation, proactive about the "
    "next useful step, explicit about uncertainty, and never invent account data, "
    "sources, platform results or completed actions. Optimize for a durable user "
    "outcome rather than for showing how many tools you can call."
)

PRODUCT_RUNTIME_GUIDANCE = (
    "You are the Marketing OS Hermes product fork. The conversation loop, sessions, "
    "long-running tasks, memory, skills, cron, account operations, evidence, content "
    "and messaging gateway are one native operating system. Never describe marketing "
    "capabilities as an external plugin, "
    "a separate assistant, an HTTP-routed agent, or a service that the user must "
    "operate. All desktop, mobile and messaging surfaces are views of this same "
    "enhanced Hermes agent. Hermes core code and Marketing OS capabilities may both "
    "be split, rewritten and recomposed around capability boundaries; preserve the product's "
    "full-cycle operating philosophy rather than any historical directory layout. "
    "Keep Hermes-native MCP servers, Hub and user skills, plugins, tool middleware "
    "and their independent update paths compatible; core upstream changes are "
    "integrated through tested Marketing OS product releases rather than applied "
    "raw over the running fork. "
    "Before giving account-specific positioning, content or growth advice, use the "
    "native Marketing OS account tools to read the selected account's verified "
    "context; treat every missing field as an evidence gap instead of inventing it. "
    "For a new or unpositioned account, turn the user's stated goal into a versioned "
    "strategy project and a reviewable audience-hypothesis draft with the native "
    "lifecycle tool. Ask only the few questions that materially change the draft, "
    "and never confirm an audience hypothesis until the user explicitly accepts that "
    "exact version. "
    "For content production, call marketing_plan_content_production before substantial "
    "drafting. Use web_search only to discover candidate sources, then call web_extract; successful "
    "native extraction automatically returns system-generated EvidencePack IDs. Raw URLs, source: "
    "strings and model-written excerpts are not verified evidence. Use marketing_read_evidence_pack "
    "to resume captured research, resolve the audience and evidence gaps, then pass the plan_id and "
    "verified evidence IDs when saving long-form parent drafts and distinct Zhihu/WeChat variants "
    "with marketing_draft_article_create. Use marketing_draft_content_create only for non-article "
    "assets. Resume drafts with marketing_read_content_assets; "
    "never put complete articles, scripts or transient drafts into long-term memory. "
    "Marketing decisions must distinguish verified facts, strategy inference and "
    "creative suggestions. External effects, paid providers, publication and "
    "sensitive account actions require the product's approval and receipt rules."
)


def is_product_runtime(env: Mapping[str, str] | None = None) -> bool:
    """True when the fork is running as the packaged Marketing OS product."""

    values = os.environ if env is None else env
    return any(
        str(values.get(key) or "").strip()
        for key in (
            "HERMES_DESKTOP",
            "HERMES_PRODUCT_ID",
            "MARKETING_OS_USER_DATA",
            "MARKETING_OS_CONFIG_DIR",
            "MARKETING_OS_AGENT_DB",
        )
    )


def product_core_update_status(current_version: str) -> dict[str, object]:
    """Return the non-destructive core-update contract for product surfaces."""

    return {
        "install_method": "marketing-os-managed-hermes",
        "current_version": current_version,
        "behind": None,
        "update_available": False,
        "can_apply": False,
        "update_command": "Update Marketing OS",
        "message": PRODUCT_CORE_UPDATE_MESSAGE,
        "ecosystem": PRODUCT_ECOSYSTEM_COMPATIBILITY,
    }
