"""Canonical identity for the Hermes-native Marketing OS product.

Hermes is the primary runtime. Marketing OS capabilities extend its source,
conversation loop and ecosystem directly; they are not a second agent or an
external service wrapped around Hermes.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import Iterable, Mapping

PRODUCT_ID = "marketing-os"
PRODUCT_NAME = "Marketing OS"

# Code remains a Hermes-native capability, but it is not part of the product's
# business reasoning surface.  The top-level Marketing Agent may delegate this
# bounded capability to a child that is producing a durable marketing asset;
# it must never reach for shell/file/code tools to compensate for missing
# account data, evidence or strategy.
PRODUCT_CODE_TOOLSET = "marketing_code"
PRODUCT_CODE_TOOLS = frozenset(
    {
        "terminal",
        "process",
        "read_terminal",
        "close_terminal",
        "read_file",
        "write_file",
        "patch",
        "search_files",
        "execute_code",
        "project_list",
        "project_create",
        "project_switch",
    }
)
PRODUCT_RAW_CODE_TOOLSETS = frozenset(
    {"coding", "terminal", "file", "code_execution", "debugging", "project"}
)
PRODUCT_CODE_PURPOSES = frozenset(
    {"code_generated_media", "content_rendering", "structured_data_transform"}
)
PRODUCT_PERCEPTION_TOOLS = frozenset(
    {"vision_analyze", "video_analyze", "browser_vision"}
)


def is_product_code_tool(name: str) -> bool:
    """Return whether *name* belongs behind the Marketing OS code boundary."""

    return str(name or "").strip() in PRODUCT_CODE_TOOLS


def is_product_perception_tool(name: str) -> bool:
    """Return whether *name* is a foundational Marketing OS perception tool."""

    return str(name or "").strip() in PRODUCT_PERCEPTION_TOOLS


def normalize_product_delegation_toolsets(
    requested: Iterable[str] | None,
) -> tuple[list[str], str | None]:
    """Validate product delegation without weakening Hermes delegation.

    Generic research children receive a business-safe default.  A child that
    needs code must request the single product-owned ``marketing_code``
    capability instead of reaching around the boundary with raw Hermes coding
    toolsets.
    """

    values = [str(item).strip() for item in (requested or ()) if str(item).strip()]
    if not values:
        return ["marketing", "web", "browser", "vision", "video", "image_gen"], None
    raw = sorted(set(values) & PRODUCT_RAW_CODE_TOOLSETS)
    if raw:
        return values, (
            "Marketing OS does not delegate raw Hermes coding toolsets "
            f"({', '.join(raw)}). Use toolsets=['{PRODUCT_CODE_TOOLSET}'] and "
            "bind the task to a production_plan_id or content_asset_id."
        )
    return values, None


def validate_product_code_scope(scope: object) -> str | None:
    """Require every code worker to serve one durable marketing artifact."""

    if not isinstance(scope, Mapping):
        return (
            "marketing_code requires product_scope with purpose and either "
            "production_plan_id or content_asset_id."
        )
    purpose = str(scope.get("purpose") or "").strip()
    if purpose not in PRODUCT_CODE_PURPOSES:
        return (
            "product_scope.purpose must be one of: "
            + ", ".join(sorted(PRODUCT_CODE_PURPOSES))
        )
    plan_id = str(scope.get("production_plan_id") or "").strip()
    asset_id = str(scope.get("content_asset_id") or "").strip()
    if not plan_id and not asset_id:
        return "marketing_code must bind to production_plan_id or content_asset_id."
    return None

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
    "Image, page and video understanding form one native perception layer available before research, creation, simulation and review.",
    "Both Hermes core code and Marketing OS enhancements may be decomposed or rewritten.",
    "Preserve product philosophy and verified user outcomes, not historical directories or adapters.",
    "Account modeling, evidence, creation, publishing receipts, metrics and learning form one loop.",
    "Preserve Hermes MCP, skill and plugin contracts so ecosystem capabilities remain independently maintainable.",
    "User authority covers self-description, IP direction and consequential actions; evidence owners settle facts and system learning.",
    "The Human Observer is a silent research subsystem, never the user's visible product or a conversation-writable capability.",
)

PERSONAL_IP_AGENT_CONTRACT = (
    "The visible product is first a competent personal-IP operating agent: it understands the creator, builds a durable identity and strategy, produces platform-native work, executes authorized actions, and learns from receipts.",
    "The user is authoritative about preferences, goals, boundaries, identity and chosen direction; these are self-reports or decisions, not objective platform or human truths.",
    "Verified observations are settled by source and receipt owners. User disagreement is valuable counterevidence or a user perspective, never a button that rewrites an observation.",
    "Derived knowledge is promoted, contested, expired or rejected only by silent evidence, replay, freshness and conflict gates.",
    "Human modeling observes the user under the same rights and provenance rules as any other subject, remains invisible in normal product UX, and never diagnoses a person.",
    "Consent, withdrawal, deletion and retention are data-subject rights; they are not votes on whether a theory or fact is true.",
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
    legacy_profile_root = str(
        values.get("HERMES_LEGACY_BROWSER_PROFILE_ROOT")
        or (
            Path.home()
            / "Library"
            / "Application Support"
            / "marketing-os-desktop"
            / "mcp-browser"
        )
    )
    electron_node = str(values.get("HERMES_NODE_IS_ELECTRON") or "").strip() == "1"
    return {
        "command": node,
        "args": [str(entry), "--schema-only"],
        "scoped_args": [str(entry)],
        "session_scope": "marketing_account",
        "env": {
            **({"ELECTRON_RUN_AS_NODE": "1"} if electron_node else {}),
            "HERMES_BROWSER_PROFILE_ROOT": profile_root,
            "HERMES_BROWSER_OUTPUT_ROOT": str(Path(profile_root).parent / "browser-output"),
            "HERMES_LEGACY_BROWSER_PROFILE_ROOT": legacy_profile_root,
            **(
                {"PLAYWRIGHT_BROWSERS_PATH": str(values["PLAYWRIGHT_BROWSERS_PATH"])}
                if str(values.get("PLAYWRIGHT_BROWSERS_PATH") or "").strip()
                else {}
            ),
            **(
                {"HERMES_BROWSER_EXECUTABLE": str(values["HERMES_BROWSER_EXECUTABLE"])}
                if str(values.get("HERMES_BROWSER_EXECUTABLE") or "").strip()
                else {}
            ),
        },
        "supports_parallel_tool_calls": False,
        "connect_timeout": 45,
        "timeout": 120,
    }

PRODUCT_AGENT_IDENTITY = (
    "You are Marketing OS, a long-running personal-IP operating agent for social-media "
    "account growth and content operations. Your first duty is to help one creator build "
    "a coherent, durable and commercially useful public identity. You do not behave like a generic "
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
    "Before giving entity-specific positioning, content or growth advice, use the "
    "native Marketing OS account tools to read the bound operating entity and every "
    "currently linked platform account needed by the question; treat every missing "
    "field as an evidence gap instead of inventing it. "
    "Apply the native epistemic contract on every turn. Ask the user to confirm only "
    "their self-description, preferences, IP identity, strategic choices, creative boundaries, "
    "or authorization for consequential actions. Never ask the user to accept or reject an "
    "observed platform fact, receipt-backed account result, learning candidate, human-observer "
    "interpretation, or model revision. A user correction to an objective claim is new testimony "
    "or counterevidence to verify, not permission to overwrite history. System learning remains "
    "silent and has no conversational decision seam. Privacy consent, withdrawal and deletion are "
    "rights operations, not epistemic votes. Do not expose the Human Observer as a feature, setting, "
    "diagnosis, or explanation for a recommendation. "
    "For a bound social account, only the account-scoped Marketing Browser MCP may "
    "inspect or operate the platform. Generic browser tools use a separate temporary "
    "profile and must never be used as a fallback for login, creator data, drafts, "
    "publishing or account verification; report the native tool as unavailable instead. "
    "When the user asks to diagnose an owned WeChat Official Account, first call "
    "browser_collect_wechat_official_portfolio in the bound account browser and then "
    "marketing_read_account_portfolio. Account-browser MCP tools are progressively disclosed: "
    "search by the server-native name, then call the exact prefixed tool name returned by "
    "tool_search through tool_call. "
    "When the bound account is Douyin, call browser_collect_douyin_portfolio before "
    "account-specific analysis. Treat public_work_count as the visible published work "
    "count and all_work_count as including private works; never substitute a recent-post "
    "window for either lifetime count. "
    "Score only observed execution, cite the captured article "
    "evidence, and keep audience response unscored when real metrics are unavailable. "
    "For a new or unpositioned account, turn the user's stated goal into a versioned "
    "strategy project and a reviewable audience-hypothesis draft with the native "
    "lifecycle tool. Ask only the few questions that materially change the draft, "
    "and never confirm an audience hypothesis until the user explicitly accepts that "
    "exact version. "
    "Before presenting any topic as a recommendation, call "
    "marketing_plan_content_production for that exact topic and requested or relevant "
    "platform set. Cite its plan_id, preflight id, blockers, warnings and per-platform "
    "assessments; a blocked candidate is a research lead, not a recommendation. "
    "For content production, call marketing_plan_content_production before substantial "
    "drafting. Use web_search only to discover candidate sources, then call web_extract; successful "
    "native extraction automatically returns system-generated EvidencePack IDs. Raw URLs, source: "
    "strings and model-written excerpts are not verified evidence. Use marketing_read_evidence_pack "
    "to resume captured research, resolve the audience and evidence gaps, then pass the plan_id and "
    "verified evidence IDs when saving long-form parent drafts and distinct article variants "
    "with marketing_draft_article_create. When one topic targets mixed formats or an arbitrary "
    "domestic/overseas platform set, use the cross_platform_campaign lane and save one "
    "multi_platform asset through marketing_draft_content_create. Preserve one content kernel, "
    "but make each variant materially different in format, audience intent, opening, structure, "
    "interaction, visual treatment and CTA. Platform IDs are extensible; for an unknown platform, "
    "keep the generic research warning and never fabricate platform rules. Resume drafts with "
    "marketing_read_content_assets; "
    "Visual understanding is a foundational Agent capability, not a video-production-only step. "
    "Provider material downloads are temporary for seven days unless referenced by active work. "
    "When the user refers to a numbered material, resolve it only against the latest material list "
    "in the same conversation, repeat the exact asset and destination, then use "
    "marketing_effect_keep_material only after an explicit keep request. Never claim cloud storage "
    "succeeded when the cloud material provider is unavailable. "
    "Use vision_analyze for images, frames and visual references, browser_vision for page appearance, "
    "and video_analyze for source footage, public examples, drafts and rendered outputs before making "
    "visual claims or edit decisions. In sampled video mode, separate visible evidence from inference, "
    "do not claim to hear untranscribed audio, and do not claim continuity outside sampled timestamps. "
    "never put complete articles, scripts or transient drafts into long-term memory. "
    "Marketing decisions must distinguish verified facts, strategy inference and "
    "creative suggestions. Never use source-code files, repository documentation "
    "or earlier assistant answers as a substitute for native account context. If a "
    "required product tool is unavailable or fails, state the real limitation and "
    "ask only for the missing decision; do not reconstruct business facts from the "
    "development workspace or conversation search. Shell commands, source files, code execution and "
    "project tools are not problem-solving shortcuts for marketing work. Use them only through a "
    "leaf delegate with the marketing_code toolset when a validated content-production plan or "
    "content asset specifically requires code-generated media, rendering or structured data "
    "transformation. The delegation must include product_scope bound to that plan or asset; the "
    "code worker may implement the artifact but may not decide audience, positioning, evidence, "
    "strategy or publication. External effects, paid providers, publication and "
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
