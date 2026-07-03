"""Parameter-level permission policy for Playwright MCP browser tools.

Tool-name allowlist is NOT enough.  This module validates every parameter
before ``registry.dispatch`` is called and enforces type, range, origin,
and context constraints.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from ipaddress import ip_address, ip_network
from typing import Any
from urllib.parse import urlparse

from .models import CapabilityLevel

# ── permanent deny-list ──────────────────────────────────────────────────────

PERMANENTLY_DENIED_TOOLS = frozenset({
    # browser_evaluate is conditionally allowed for marketing_accounts_sync only
    # (see _validate_browser_evaluate). browser_run_code_unsafe stays permanently denied.
    "browser_run_code_unsafe",
    "browser_file_upload", "browser_fill_form", "browser_type",
    "browser_press_key", "browser_take_screenshot",
    "browser_cookie_get", "browser_cookie_list", "browser_cookie_set",
    "browser_cookie_delete", "browser_cookie_clear",
    "browser_storage_state", "browser_set_storage_state",
    "browser_localstorage_get", "browser_localstorage_list", "browser_localstorage_set",
    "browser_localstorage_delete", "browser_localstorage_clear",
    "browser_sessionstorage_get", "browser_sessionstorage_list", "browser_sessionstorage_set",
    "browser_sessionstorage_delete", "browser_sessionstorage_clear",
    "browser_start_tracing", "browser_stop_tracing",
    "browser_start_video", "browser_stop_video", "browser_video_chapter",
    "browser_pdf_save",
    "browser_route", "browser_route_list", "browser_unroute",
    "browser_network_requests", "browser_network_request",
    "browser_console_messages", "browser_resize", "browser_handle_dialog",
    "browser_drag", "browser_drop", "browser_hover",
    "browser_select_option", "browser_navigate_back",
    "browser_mouse_click_xy", "browser_mouse_move_xy",
    "browser_mouse_down", "browser_mouse_up", "browser_mouse_drag_xy",
    "browser_mouse_wheel",
    "browser_annotate", "browser_highlight", "browser_hide_highlight",
    "browser_verify_element_visible", "browser_verify_list_visible",
    "browser_verify_text_visible", "browser_verify_value",
    "browser_generate_locator", "browser_resume",
    "browser_network_state_set", "browser_get_config",
})

# ── origin allowlists ────────────────────────────────────────────────────────

PLATFORM_ORIGINS: dict[str, frozenset[str]] = {
    "douyin": frozenset({
        "https://www.douyin.com",
        "https://douyin.com",
        "https://creator.douyin.com",
    }),
}

_DOUYIN_SUBDOMAIN_RE = re.compile(
    r"^https://([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)*douyin\.com$"
)

_PRIVATE_NETS = [
    ip_network("10.0.0.0/8"), ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"), ip_network("127.0.0.0/8"),
    ip_network("169.254.0.0/16"), ip_network("::1/128"),
    ip_network("fc00::/7"), ip_network("fe80::/10"),
]

_FORBIDDEN_SCHEMES = frozenset({"file", "data", "javascript", "blob", "ftp"})
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# ── dataclasses ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BrowserPolicyDecision:
    allowed: bool
    effective_level: CapabilityLevel
    reason: str
    sanitized_arguments: dict[str, Any] = field(default_factory=dict)
    audit: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrowserActionContext:
    platform: str
    account_id: str
    capability: str
    user_id: str = ""
    task_id: str = ""
    approved: bool = False
    current_origin: str = ""


# ── public entry ─────────────────────────────────────────────────────────────

# Only creator-center discovery tabs and account-sync data controls are clickable.
# Publishing, forms, uploads, arbitrary page controls and login actions remain denied.
_CLICK_ALLOWED_CAPABILITIES: frozenset[str] = frozenset({
    "marketing_trending_search",
    "marketing_accounts_sync",
})
_TREND_CLICK_LABELS = frozenset({"热门话题", "热门挑战", "热点榜单"})

# Creator-center elements that accounts_sync may click: tab navigation and
# official data export.  No form fields, publish buttons, or login controls.
_ACCOUNT_SYNC_CLICK_LABELS = frozenset({
    # Content manage tabs
    "投稿列表", "内容管理", "作品管理",
    # Video detail analysis tabs (per autody research)
    "总览", "流量分析", "观众分析", "评论热词",
    # Official data export
    "导出数据", "导出", "下载",
    # Data center navigation
    "数据中心", "粉丝数据", "作品数据", "直播数据", "互动数据",
    # Dialog dismissal
    "我知道了", "确定",
    # Pagination
    "下一页", "上一页",
})

_READ_BROWSER_CAPABILITIES = frozenset({
    "marketing_trending_search",
    "marketing_session_login",
    "marketing_accounts_sync",
})

# browser_evaluate is only allowed for account data collection, not trending or login
_EVALUATE_CAPABILITIES: frozenset[str] = frozenset({"marketing_accounts_sync"})

_TOOL_CAPABILITIES: dict[str, frozenset[str]] = {
    "browser_close": _READ_BROWSER_CAPABILITIES,
    "browser_navigate": _READ_BROWSER_CAPABILITIES,
    "browser_snapshot": _READ_BROWSER_CAPABILITIES,
    "browser_wait_for": _READ_BROWSER_CAPABILITIES,
    "browser_tabs": _READ_BROWSER_CAPABILITIES,
    "browser_click": _CLICK_ALLOWED_CAPABILITIES,
    "browser_evaluate": _EVALUATE_CAPABILITIES,
}


def validate_browser_call(
    ctx: BrowserActionContext,
    tool_name: str,
    arguments: dict[str, Any] | None,
) -> BrowserPolicyDecision:
    if not isinstance(ctx, BrowserActionContext):
        return _deny("invalid BrowserActionContext")
    if arguments is not None and type(arguments) is not dict:
        return _deny("browser arguments must be an object")
    arguments = dict(arguments or {})
    if any(type(key) is not str for key in arguments):
        return _deny("browser argument names must be strings")

    if tool_name in PERMANENTLY_DENIED_TOOLS:
        return BrowserPolicyDecision(
            allowed=False, effective_level=CapabilityLevel.SYSTEM_FORBIDDEN,
            reason=f"{tool_name} is permanently denied",
            audit={"tool": tool_name},
        )
    if tool_name not in _VALIDATORS:
        return BrowserPolicyDecision(
            allowed=False, effective_level=CapabilityLevel.SYSTEM_FORBIDDEN,
            reason=f"{tool_name} is not registered in browser policy",
            audit={"tool": tool_name},
        )

    # unknown parameter guard
    known = _TOOL_ALLOWED_PARAMS.get(tool_name, frozenset())
    unknown = set(arguments.keys()) - known
    if unknown:
        return BrowserPolicyDecision(
            allowed=False, effective_level=CapabilityLevel.SYSTEM_FORBIDDEN,
            reason=f"unknown parameters: {sorted(unknown)}",
            audit={"tool": tool_name, "unknown_params": sorted(unknown)},
        )

    return _VALIDATORS[tool_name](ctx, tool_name, arguments)


# ── context validation ───────────────────────────────────────────────────────

def _check_context(ctx: BrowserActionContext, tool_name: str, min_level: CapabilityLevel,
                    ) -> BrowserPolicyDecision | None:
    """Return a rejection decision or None if context is acceptable."""
    if type(ctx.platform) is not str or not ctx.platform or ctx.platform not in _VALID_PLATFORMS:
        return BrowserPolicyDecision(
            allowed=False, effective_level=CapabilityLevel.SYSTEM_FORBIDDEN,
            reason=f"invalid or missing platform: {ctx.platform!r}",
        )
    if type(ctx.account_id) is not str or not ctx.account_id or not _ACCT_RE.fullmatch(ctx.account_id):
        return BrowserPolicyDecision(
            allowed=False, effective_level=CapabilityLevel.SYSTEM_FORBIDDEN,
            reason="invalid or missing account_id",
        )
    if type(ctx.capability) is not str or not ctx.capability:
        return BrowserPolicyDecision(
            allowed=False, effective_level=CapabilityLevel.SYSTEM_FORBIDDEN,
            reason="missing capability",
        )
    from .tool_manifest import tool_by_name
    capability = tool_by_name(ctx.capability)
    if capability is None:
        return BrowserPolicyDecision(
            allowed=False, effective_level=CapabilityLevel.SYSTEM_FORBIDDEN,
            reason=f"unknown product capability: {ctx.capability!r}",
        )
    allowed_capabilities = _TOOL_CAPABILITIES.get(tool_name, frozenset())
    if ctx.capability not in allowed_capabilities:
        return BrowserPolicyDecision(
            allowed=False, effective_level=CapabilityLevel.SYSTEM_FORBIDDEN,
            reason=f"capability {ctx.capability!r} is not allowed for {tool_name}",
        )
    if (ctx.user_id and type(ctx.user_id) is not str) or (ctx.task_id and type(ctx.task_id) is not str):
        return BrowserPolicyDecision(
            allowed=False, effective_level=CapabilityLevel.SYSTEM_FORBIDDEN,
            reason="user_id and task_id must be strings",
        )
    if not ctx.user_id and not ctx.task_id:
        return BrowserPolicyDecision(
            allowed=False, effective_level=CapabilityLevel.SYSTEM_FORBIDDEN,
            reason="missing user_id or task_id",
        )
    if type(ctx.approved) is not bool:
        return BrowserPolicyDecision(
            allowed=False, effective_level=CapabilityLevel.SYSTEM_FORBIDDEN,
            reason="approved must be boolean",
        )
    if min_level >= CapabilityLevel.CONTROLLED_RESOURCE and not ctx.approved:
        return BrowserPolicyDecision(
            allowed=False, effective_level=CapabilityLevel.SYSTEM_FORBIDDEN,
            reason=f"{min_level.name} requires approved=True",
        )
    return None


_ACCT_RE = re.compile(r"^acct_[a-f0-9]{6,32}$")
_VALID_PLATFORMS = frozenset({"douyin"})


# ── per-tool validators ──────────────────────────────────────────────────────

def _validate_browser_close(
    ctx: BrowserActionContext, tool: str, args: dict[str, Any],
) -> BrowserPolicyDecision:
    rejection = _check_context(ctx, tool, CapabilityLevel.REVERSIBLE_WRITE)
    if rejection: return rejection
    return BrowserPolicyDecision(
        allowed=True, effective_level=CapabilityLevel.REVERSIBLE_WRITE, reason="ok",
        sanitized_arguments={}, audit={"tool": tool},
    )


def _validate_browser_navigate(
    ctx: BrowserActionContext, tool: str, args: dict[str, Any],
) -> BrowserPolicyDecision:
    rejection = _check_context(ctx, tool, CapabilityLevel.CONTROLLED_RESOURCE)
    if rejection: return rejection

    url = args.get("url")
    if type(url) is not str:
        return _deny("browser_navigate.url must be a string")
    url = url.strip()
    if not url or len(url) > 2048:
        return _deny("browser_navigate.url empty or too long")
    if _CONTROL_RE.search(url):
        return _deny("browser_navigate.url contains control characters")
    if "\n" in url or "\r" in url:
        return _deny("browser_navigate.url contains newline")

    try:
        parsed = urlparse(url)
    except Exception:
        return _deny(f"browser_navigate.url parse error")

    scheme = (parsed.scheme or "").lower()
    if scheme != "https":
        return _deny(f"only https allowed, got {scheme!r}")
    if scheme in _FORBIDDEN_SCHEMES:
        return _deny(f"forbidden scheme: {scheme}")

    # userinfo rejection
    if parsed.username or (parsed.password and parsed.password != ""):
        return _deny("URL must not contain username:password")

    raw_hostname = parsed.hostname or ""
    if raw_hostname.endswith("."):
        return _deny("hostname must not end with trailing dot")
    hostname = raw_hostname.lower()
    if not hostname:
        return _deny("empty hostname")
    if hostname in ("localhost", "127.0.0.1", "::1"):
        return _deny("localhost not allowed")

    # @-in-hostname check (after rstrip)
    if "@" in hostname:
        return _deny("hostname must not contain @")

    # netloc has @ but hostname doesn't → username@host masquerade
    if "@" in (parsed.netloc or ""):
        return _deny("netloc contains @")

    # port
    try:
        port = parsed.port
    except ValueError:
        return _deny("invalid port")
    if port is not None and port != 443:
        return _deny("only default https port (443) allowed")

    # private IP check
    try:
        _check_host_ip(hostname)
    except ValueError as e:
        return _deny(str(e))

    # origin match
    combined = f"{scheme}://{hostname}"
    origins = PLATFORM_ORIGINS.get(ctx.platform, frozenset())
    if combined in origins:
        pass
    elif ctx.platform == "douyin" and _DOUYIN_SUBDOMAIN_RE.match(combined):
        pass
    else:
        return _deny(f"origin {combined} not in {ctx.platform} allowlist")

    return BrowserPolicyDecision(
        allowed=True, effective_level=CapabilityLevel.CONTROLLED_RESOURCE, reason="ok",
        sanitized_arguments={"url": url},
        audit={"url": url, "hostname": hostname},
    )


def _validate_browser_snapshot(
    ctx: BrowserActionContext, tool: str, args: dict[str, Any],
) -> BrowserPolicyDecision:
    rejection = _check_context(ctx, tool, CapabilityLevel.CONTROLLED_RESOURCE)
    if rejection: return rejection

    clean: dict[str, Any] = {}

    if "target" in args:
        v = args["target"]
        if type(v) is not str:
            return _deny("browser_snapshot.target must be a string")
        v = v.strip()
        if not v or len(v) > 500:
            return _deny("browser_snapshot.target empty or too long")
        if _CONTROL_RE.search(v):
            return _deny("browser_snapshot.target contains control characters")
        clean["target"] = v

    if "filename" in args:
        return _deny("browser_snapshot.filename is denied (disk write)")

    if "depth" in args:
        v = args["depth"]
        if type(v) is not int:
            return _deny(f"browser_snapshot.depth must be int, got {type(v).__name__}")
        if isinstance(v, bool):
            return _deny("browser_snapshot.depth must not be bool")
        if v < 1 or v > 20:
            return _deny("browser_snapshot.depth must be 1–20")
        clean["depth"] = v

    if "boxes" in args:
        v = args["boxes"]
        if type(v) is not bool:
            return _deny(f"browser_snapshot.boxes must be bool, got {type(v).__name__}")
        if v:
            return _deny("browser_snapshot.boxes=true is not enabled")
        clean["boxes"] = False

    return BrowserPolicyDecision(
        allowed=True, effective_level=CapabilityLevel.CONTROLLED_RESOURCE, reason="ok",
        sanitized_arguments=clean, audit={"tool": tool},
    )


def _validate_browser_wait_for(
    ctx: BrowserActionContext, tool: str, args: dict[str, Any],
) -> BrowserPolicyDecision:
    rejection = _check_context(ctx, tool, CapabilityLevel.CONTROLLED_RESOURCE)
    if rejection: return rejection

    time_val = args.get("time")
    text_val = args.get("text")
    text_gone = args.get("textGone")

    time_s = None
    text_s = None
    gone_s = None

    if time_val is not None:
        if type(time_val) is bool:
            return _deny("browser_wait_for.time must not be bool")
        if type(time_val) not in (int, float):
            return _deny(f"browser_wait_for.time must be int or float, got {type(time_val).__name__}")
        if math.isnan(time_val) or math.isinf(time_val) or time_val < 0:
            return _deny("browser_wait_for.time must be >= 0 and finite")
        if time_val > 10:
            return _deny("browser_wait_for.time max 10 seconds")
        time_s = float(time_val)

    for label, val in [("text", text_val), ("textGone", text_gone)]:
        if val is not None:
            if type(val) is not str:
                return _deny(f"browser_wait_for.{label} must be a string")
            val = val.strip()
            if not val or len(val) > 500:
                return _deny(f"browser_wait_for.{label} empty or too long")
            if _CONTROL_RE.search(val):
                return _deny(f"browser_wait_for.{label} contains control characters")
            if label == "text":
                text_s = val
            else:
                gone_s = val

    if time_s is None and text_s is None and gone_s is None:
        return _deny("browser_wait_for requires time, text, or textGone")
    if text_s is not None and gone_s is not None:
        return _deny("browser_wait_for cannot use both text and textGone")

    clean: dict[str, Any] = {}
    if time_s is not None: clean["time"] = time_s
    if text_s is not None: clean["text"] = text_s
    if gone_s is not None: clean["textGone"] = gone_s
    return BrowserPolicyDecision(
        allowed=True, effective_level=CapabilityLevel.CONTROLLED_RESOURCE, reason="ok",
        sanitized_arguments=clean,
    )


def _validate_browser_tabs(
    ctx: BrowserActionContext, tool: str, args: dict[str, Any],
) -> BrowserPolicyDecision:
    rejection = _check_context(ctx, tool, CapabilityLevel.CONTROLLED_RESOURCE)
    if rejection: return rejection

    action = args.get("action")
    if type(action) is not str:
        return _deny("browser_tabs.action must be a string")
    action = action.strip()
    if action not in ("list", "select", "close", "new"):
        return _deny(f"browser_tabs.action invalid: {action!r}")

    if action == "new":
        return _deny("browser_tabs.new is denied (use controlled navigate)")

    if "url" in args:
        return _deny("browser_tabs.url is denied")

    clean: dict[str, Any] = {"action": action}
    if "index" in args:
        v = args["index"]
        if type(v) is not int:
            return _deny(f"browser_tabs.index must be int, got {type(v).__name__}")
        if isinstance(v, bool):
            return _deny("browser_tabs.index must not be bool")
        if v < 0:
            return _deny("browser_tabs.index must be >= 0")
        clean["index"] = v
    elif action in ("select", "close"):
        return _deny(f"browser_tabs.{action} requires index")

    if action == "list" and "index" in clean:
        return _deny("browser_tabs.list must not include index")

    return BrowserPolicyDecision(
        allowed=True, effective_level=CapabilityLevel.CONTROLLED_RESOURCE, reason="ok",
        sanitized_arguments=clean,
    )


def _validate_browser_evaluate(
    ctx: BrowserActionContext, tool: str, args: dict[str, Any],
) -> BrowserPolicyDecision:
    # browser_evaluate is the highest-risk tool: it executes arbitrary JS in the
    # page context.  Guardrails:
    #   - only marketing_accounts_sync (not trending/login)
    #   - requires approved=True (L3 controlled resource)
    #   - function must be a string, <= 50KB, no control chars (except newlines/tabs)
    #   - filename is denied (disk write)
    #   - element/target are optional but validated if present
    #   - output still goes through recursive secret sanitizer
    rejection = _check_context(ctx, tool, CapabilityLevel.CONTROLLED_RESOURCE)
    if rejection:
        return rejection

    fn = args.get("function")
    if type(fn) is not str:
        return _deny("browser_evaluate.function must be a string")
    fn = fn.strip()
    if not fn:
        return _deny("browser_evaluate.function must not be empty")
    if len(fn) > 50_000:
        return _deny("browser_evaluate.function must be <= 50000 chars")
    # Allow newlines and tabs but reject other control characters
    _script_ctrl = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    if _script_ctrl.search(fn):
        return _deny("browser_evaluate.function contains control characters")

    # filename is denied (disk write risk)
    if "filename" in args:
        return _deny("browser_evaluate.filename is denied (disk write)")

    clean: dict[str, Any] = {"function": fn}

    # element and target are optional context selectors
    for param in ("element", "target"):
        if param in args:
            v = args[param]
            if type(v) is not str:
                return _deny(f"browser_evaluate.{param} must be a string")
            v = v.strip()
            if not v or len(v) > 1000:
                return _deny(f"browser_evaluate.{param} empty or too long")
            if _CONTROL_RE.search(v):
                return _deny(f"browser_evaluate.{param} contains control characters")
            clean[param] = v

    return BrowserPolicyDecision(
        allowed=True, effective_level=CapabilityLevel.CONTROLLED_RESOURCE, reason="ok",
        sanitized_arguments=clean,
        audit={"tool": tool, "capability": ctx.capability, "function_len": len(fn)},
    )


def _validate_browser_click(
    ctx: BrowserActionContext, tool: str, args: dict[str, Any],
) -> BrowserPolicyDecision:
    rejection = _check_context(ctx, tool, CapabilityLevel.CONTROLLED_RESOURCE)
    if rejection: return rejection

    # capability must be in real allowlist
    if ctx.capability not in _CLICK_ALLOWED_CAPABILITIES:
        return _deny(
            f"browser_click: capability {ctx.capability!r} not in click allowlist; "
            "browser_click is universally denied until MCP-06 registers real capabilities"
        )

    target = args.get("target")
    element = args.get("element")
    if type(target) is not str or not (target := target.strip()) or len(target) > 1000:
        return _deny("browser_click.target must be non-empty string <= 1000 chars")
    if _CONTROL_RE.search(target):
        return _deny("browser_click.target contains control characters")
    if type(element) is not str or not (element := element.strip()) or len(element) > 500:
        return _deny("browser_click.element must be non-empty string <= 500 chars")
    if _CONTROL_RE.search(element):
        return _deny("browser_click.element contains control characters")
    if ctx.capability == "marketing_trending_search":
        if element not in _TREND_CLICK_LABELS:
            return _deny("browser_click element is outside reviewed creator-center trend tabs")
        if not re.fullmatch(r"[a-z0-9]{1,12}", target):
            return _deny("browser_click target must be a current Playwright snapshot ref")
    elif ctx.capability == "marketing_accounts_sync":
        if element not in _ACCOUNT_SYNC_CLICK_LABELS:
            return _deny(
                f"browser_click element {element!r} is outside reviewed "
                "creator-center account-sync controls"
            )
        if not re.fullmatch(r"[a-z0-9]{1,12}", target):
            return _deny("browser_click target must be a current Playwright snapshot ref")

    # button
    if "button" in args:
        v = args["button"]
        if type(v) is not str or v.strip() != "left":
            return _deny(f"browser_click.button={v!r} denied (only 'left' allowed)")

    # doubleClick
    if "doubleClick" in args:
        v = args["doubleClick"]
        if type(v) is not bool:
            return _deny(f"browser_click.doubleClick must be bool, got {type(v).__name__}")
        if v is not False:
            return _deny("browser_click.doubleClick must be false")

    # modifiers — presence at all = deny
    if "modifiers" in args:
        return _deny("browser_click.modifiers denied")

    # Other unknown params handled by centralized unknown-param guard

    return BrowserPolicyDecision(
        allowed=True, effective_level=CapabilityLevel.CONTROLLED_RESOURCE, reason="ok",
        sanitized_arguments={"target": target, "element": element},
        audit={"tool": tool, "capability": ctx.capability},
    )


# ── tool allowed params ──────────────────────────────────────────────────────

_TOOL_ALLOWED_PARAMS: dict[str, frozenset[str]] = {
    "browser_close": frozenset(),
    "browser_navigate": frozenset({"url"}),
    "browser_snapshot": frozenset({"target", "depth", "boxes", "filename"}),
    "browser_wait_for": frozenset({"time", "text", "textGone"}),
    "browser_tabs": frozenset({"action", "index", "url"}),
    "browser_click": frozenset({"target", "element", "doubleClick", "button", "modifiers"}),
    "browser_evaluate": frozenset({"function", "element", "target", "filename"}),
}

_VALIDATORS = {
    "browser_close": _validate_browser_close,
    "browser_navigate": _validate_browser_navigate,
    "browser_snapshot": _validate_browser_snapshot,
    "browser_wait_for": _validate_browser_wait_for,
    "browser_tabs": _validate_browser_tabs,
    "browser_click": _validate_browser_click,
    "browser_evaluate": _validate_browser_evaluate,
}


# ── output sanitizer ─────────────────────────────────────────────────────────

_SECRET_KEY_RE = re.compile(
    r"(?i)\b(cookie|set-cookie|authorization|access_token|refresh_token"
    r"|password|secret|api_key|api-key|x-api-key|token)\b",
)
_SENSITIVE_RE = re.compile(
    r"(eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]+)"
    r"|(sk-[a-zA-Z0-9_-]{16,})|(ghp_[a-zA-Z0-9]{16,})",
)
_MAX_DEPTH = 10
_MAX_OUTPUT_SIZE = 256_000  # 256 KB


def sanitize_output(obj: Any, depth: int = 0) -> Any:
    """Recursively redact secrets with depth, cycle and total-size bounds."""
    budget = [_MAX_OUTPUT_SIZE]
    seen: set[int] = set()

    def walk(value: Any, current_depth: int) -> Any:
        if current_depth > _MAX_DEPTH or budget[0] <= 0:
            return "[TRUNCATED]"
        if isinstance(value, (str, bytes)):
            text = value.decode(errors="replace") if isinstance(value, bytes) else value
            if _SECRET_KEY_RE.search(text) or _SENSITIVE_RE.search(text):
                return "[REDACTED]"
            take = min(len(text), 50_000, max(0, budget[0]))
            budget[0] -= take
            return text[:take] + ("...[TRUNCATED]" if take < len(text) else "")
        if isinstance(value, (dict, list, tuple)):
            identity = id(value)
            if identity in seen:
                return "[CYCLE]"
            seen.add(identity)
            try:
                if isinstance(value, dict):
                    result: dict[str, Any] = {}
                    for key, item in value.items():
                        key_text = str(key)
                        budget[0] -= min(len(key_text), max(0, budget[0]))
                        if _SECRET_KEY_RE.search(key_text):
                            result[key_text] = "[REDACTED]"
                        else:
                            result[key_text] = walk(item, current_depth + 1)
                        if budget[0] <= 0:
                            result["__truncated__"] = True
                            break
                    return result
                sanitized = []
                for item in value:
                    if budget[0] <= 0:
                        sanitized.append("[TRUNCATED]")
                        break
                    sanitized.append(walk(item, current_depth + 1))
                return tuple(sanitized) if isinstance(value, tuple) else sanitized
            finally:
                seen.discard(identity)
        if isinstance(value, (int, float, bool, type(None))):
            budget[0] -= 16
            return value
        text = str(value)
        take = min(len(text), 1000, max(0, budget[0]))
        budget[0] -= take
        return text[:take] + ("...[TRUNCATED]" if take < len(text) else "")

    return walk(obj, depth)


# ── helpers ──────────────────────────────────────────────────────────────────

def _deny(reason: str) -> BrowserPolicyDecision:
    return BrowserPolicyDecision(
        allowed=False, effective_level=CapabilityLevel.SYSTEM_FORBIDDEN,
        reason=reason,
    )


def _check_host_ip(hostname: str) -> None:
    """Raise ValueError if hostname is a loopback/private IP, pass for hostnames."""
    try:
        ip = ip_address(hostname)
    except ValueError:
        return  # not an IP — ok
    for net in _PRIVATE_NETS:
        if ip in net:
            raise ValueError(f"private/loopback IP: {hostname}")


def is_tool_permanently_denied(name: str) -> bool:
    return name in PERMANENTLY_DENIED_TOOLS


def click_capabilities() -> frozenset[str]:
    return _CLICK_ALLOWED_CAPABILITIES
