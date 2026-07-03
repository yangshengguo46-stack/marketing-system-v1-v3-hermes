"""Product-owned MCP broker.

External MCP tools are never exposed directly to the marketing agent.  The
product capability layer approves an action first, then calls this broker with
the exact server/tool pair and canonical arguments.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import CapabilityLevel


class MCPConfigError(ValueError):
    pass


ROLE_LEVELS = {
    "browser": CapabilityLevel.CONTROLLED_RESOURCE,
    "fetch": CapabilityLevel.READ_ONLY,
    "filesystem": CapabilityLevel.REVERSIBLE_WRITE,
    "sqlite_readonly": CapabilityLevel.READ_ONLY,
    "transcription": CapabilityLevel.REVERSIBLE_WRITE,
}

PLAYWRIGHT_MINIMAL_TOOLS = frozenset({
    "browser_navigate",
    "browser_snapshot",
    "browser_click",
    "browser_wait_for",
    "browser_tabs",
    "browser_close",
    "browser_evaluate",
})

PLAYWRIGHT_FORBIDDEN_TOOLS = frozenset({
    "browser_run_code_unsafe",
    "browser_file_upload",
    "browser_fill_form",
    "browser_type",
    "browser_press_key",
    "browser_take_screenshot",
})

_SAFE_NAME = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_SHELL_META = re.compile(r"[;&|`$<>\n\r]")


@dataclass(frozen=True)
class MCPServerSpec:
    name: str
    role: str
    enabled: bool
    transport: str
    command: str | None
    args: tuple[str, ...]
    url: str | None
    include_tools: tuple[str, ...]
    timeout: float
    connect_timeout: float
    source: dict[str, Any]
    blocked_reason: str | None = None

    @property
    def level(self) -> CapabilityLevel:
        return ROLE_LEVELS[self.role]

    @property
    def toolset(self) -> str:
        return f"mcp-{self.name}"

    def hermes_config(self) -> dict[str, Any]:
        config: dict[str, Any] = {
            "enabled": self.enabled,
            "timeout": self.timeout,
            "connect_timeout": self.connect_timeout,
            "supports_parallel_tool_calls": False,
            "tools": {
                "include": list(self.include_tools),
                "resources": False,
                "prompts": False,
            },
        }
        if self.transport == "stdio":
            config.update({"command": self.command, "args": list(self.args), "env": {}})
        else:
            config.update({"url": self.url, "ssl_verify": True})
        return config


def _validate_stdio(command: str | None, args: tuple[str, ...], *, enabled: bool) -> None:
    if not command:
        if enabled:
            raise MCPConfigError("enabled stdio MCP server requires command")
        return
    if _SHELL_META.search(command) or any(_SHELL_META.search(arg) for arg in args):
        raise MCPConfigError("MCP stdio command must not contain shell syntax")
    if command in {"sh", "bash", "zsh", "cmd", "powershell", "powershell.exe"}:
        raise MCPConfigError("shell interpreters are forbidden as MCP commands")
    if command in {"npx", "npm", "pnpm", "yarn", "uvx", "pipx"}:
        joined = " ".join(args).lower()
        if "latest" in joined or "-y" in args or "--yes" in args:
            raise MCPConfigError("MCP package execution must use a reviewed pinned version")


def load_mcp_manifest(path: str | Path) -> dict[str, MCPServerSpec]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("version") != 1 or not isinstance(raw.get("servers"), dict):
        raise MCPConfigError("unsupported MCP manifest")
    result: dict[str, MCPServerSpec] = {}
    for name, item in raw["servers"].items():
        if not _SAFE_NAME.fullmatch(name):
            raise MCPConfigError(f"invalid MCP server name: {name}")
        if not isinstance(item, dict) or item.get("role") not in ROLE_LEVELS:
            raise MCPConfigError(f"invalid MCP role for {name}")
        enabled = bool(item.get("enabled", False))
        transport = str(item.get("transport", "stdio"))
        if transport not in {"stdio", "http"}:
            raise MCPConfigError(f"unsupported MCP transport for {name}")
        command = item.get("command")
        args = tuple(str(value) for value in item.get("args", []))
        url = item.get("url")
        tools = item.get("tools") or {}
        include = tuple(str(value) for value in tools.get("include", []))
        if enabled and not include:
            raise MCPConfigError(f"enabled MCP server {name} requires a non-empty tool allowlist")
        if transport == "stdio":
            _validate_stdio(command, args, enabled=enabled)
        elif enabled and (not isinstance(url, str) or not url.startswith("https://")):
            raise MCPConfigError(f"enabled HTTP MCP server {name} requires HTTPS")
        result[name] = MCPServerSpec(
            name=name,
            role=item["role"],
            enabled=enabled,
            transport=transport,
            command=str(command) if command else None,
            args=args,
            url=str(url) if url else None,
            include_tools=include,
            timeout=min(max(float(item.get("timeout", 120)), 5), 300),
            connect_timeout=min(max(float(item.get("connect_timeout", 30)), 5), 60),
            source=dict(item.get("source") or {}),
            blocked_reason=str(item.get("blocked_reason")) if item.get("blocked_reason") else None,
        )
    return result


def _sanitized(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", value)


def validate_tool_discovery(
    spec: MCPServerSpec, discovered: list[str] | tuple[str, ...] | set[str],
) -> dict[str, Any]:
    """Compare runtime discovery with the reviewed product allowlist.

    Extra server tools are reported for audit but never become product tools.
    Missing reviewed tools make the server unusable. Discovery does not mutate
    the manifest or registry.
    """
    found = {str(name) for name in discovered}
    allowed = set(spec.include_tools)
    missing = sorted(allowed - found)
    extra = sorted(found - allowed)
    return {
        "valid": not missing,
        "allowed": sorted(allowed),
        "missing": missing,
        "extra_hidden": extra,
    }


class ProductMCPBroker:
    def __init__(self, specs: dict[str, MCPServerSpec]):
        self.specs = specs
        self._registered = False

    def status(self) -> dict[str, Any]:
        servers = []
        for spec in self.specs.values():
            executable = bool(spec.command and (Path(spec.command).is_file() or shutil.which(spec.command)))
            servers.append({
                "name": spec.name,
                "role": spec.role,
                "level": int(spec.level),
                "enabled": spec.enabled,
                "configured": bool(spec.url or spec.command),
                "executable_available": executable if spec.transport == "stdio" else None,
                "tools": list(spec.include_tools),
                "blocked_reason": spec.blocked_reason,
                "source": spec.source,
            })
        return {"ready": any(item["enabled"] for item in servers), "servers": servers}

    def register(self) -> list[str]:
        configs = {
            spec.name: spec.hermes_config()
            for spec in self.specs.values()
            if spec.enabled
        }
        if not configs:
            self._registered = True
            return []
        from tools.mcp_tool import register_mcp_servers
        names = register_mcp_servers(configs)
        self._registered = True
        return names

    def call(
        self, server_name: str, tool_name: str, arguments: dict[str, Any],
        *, approved: bool = False,
        browser_ctx: Any = None,
    ) -> dict[str, Any]:
        spec = self.specs.get(server_name)
        if spec is None or not spec.enabled:
            raise PermissionError("MCP server is not enabled")
        if tool_name not in spec.include_tools:
            raise PermissionError("MCP tool is outside the product allowlist")

        from .mcp_browser_policy import (
            PERMANENTLY_DENIED_TOOLS, validate_browser_call, sanitize_output,
        )
        if tool_name in PERMANENTLY_DENIED_TOOLS:
            raise PermissionError(f"MCP tool {tool_name} is permanently denied")

        # Browser tools MUST have a valid BrowserActionContext
        sanitized_args = dict(arguments or {})
        effective_level = spec.level
        policy_meta: dict[str, Any] = {}
        if spec.role == "browser":
            if browser_ctx is None:
                raise PermissionError(
                    "browser MCP tools require BrowserActionContext"
                )
            if type(approved) is not bool:
                raise PermissionError("approved must be boolean")
            if browser_ctx.approved != approved:
                raise PermissionError(
                    "browser_ctx.approved must agree with call(approved=...)"
                )
            decision = validate_browser_call(browser_ctx, tool_name, arguments)
            if not decision.allowed:
                raise PermissionError(f"{tool_name}: {decision.reason}")
            sanitized_args = decision.sanitized_arguments
            effective_level = decision.effective_level
            policy_meta = {
                "effective_level": effective_level.name,
                "policy_reason": decision.reason,
                "audit": decision.audit,
            }

        if effective_level >= CapabilityLevel.CONTROLLED_RESOURCE and not approved:
            raise PermissionError("MCP action requires product approval")

        if not self._registered:
            self.register()
        prefixed = f"mcp_{_sanitized(server_name)}_{_sanitized(tool_name)}"
        from tools.registry import registry
        entry = registry.get_entry(prefixed)
        if entry is None or entry.toolset != spec.toolset:
            raise RuntimeError("MCP tool was not registered by the expected server")
        raw = registry.dispatch(prefixed, dict(sanitized_args))
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            parsed = {"data": str(raw)}
        return {
            "status": "ok",
            "server": server_name,
            "tool": tool_name,
            "capability_level": int(effective_level),
            "data": sanitize_output(parsed),
            **policy_meta,
        }

    async def call_account_scoped_browser(
        self, manager: Any, server_name: str, platform: str, account_id: str,
        tool_name: str, arguments: dict[str, Any], *, browser_ctx: Any,
        approved: bool,
    ) -> dict[str, Any]:
        """Validate a product browser action, then use its account MCP session.

        Account-scoped Playwright is intentionally not globally enabled in the
        Hermes registry.  The explicit login action owns the process lifetime.
        """
        spec = self.specs.get(server_name)
        if spec is None or spec.role != "browser":
            raise PermissionError("reviewed browser MCP server is unavailable")
        if tool_name not in spec.include_tools:
            raise PermissionError("MCP tool is outside the product allowlist")
        from .mcp_browser_policy import (
            PERMANENTLY_DENIED_TOOLS, sanitize_output, validate_browser_call,
        )
        if tool_name in PERMANENTLY_DENIED_TOOLS:
            raise PermissionError(f"MCP tool {tool_name} is permanently denied")
        if type(approved) is not bool or browser_ctx.approved != approved:
            raise PermissionError("browser approval context mismatch")
        decision = validate_browser_call(browser_ctx, tool_name, arguments)
        if not decision.allowed:
            raise PermissionError(f"{tool_name}: {decision.reason}")
        if decision.effective_level >= CapabilityLevel.CONTROLLED_RESOURCE and not approved:
            raise PermissionError("MCP action requires product approval")
        raw = await manager.call_tool(
            platform, account_id, tool_name, decision.sanitized_arguments,
            timeout=spec.timeout,
        )
        if raw.get("status") != "ok":
            return raw
        return {
            **raw,
            "server": server_name,
            "capability_level": int(decision.effective_level),
            "content": sanitize_output(raw.get("content", [])),
            "policy_reason": decision.reason,
            "audit": decision.audit,
        }
