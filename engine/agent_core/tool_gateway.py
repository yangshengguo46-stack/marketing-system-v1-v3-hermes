"""Tool gateway — registers marketing-desktop tools into Hermes' ToolRegistry,
wrapping every handler with L0-L4 policy enforcement and structured result output.

On import, this module discovers the Hermes tool registry and registers the
full tool manifest.  The ``enabled_toolsets=["marketing-desktop"]`` setting
on AIAgent will then resolve only these tools — no system tools leak through.
"""

from __future__ import annotations

import contextvars
import json
import logging
logger = logging.getLogger("marketing-os.gateway")

from .models import CapabilityLevel
from .policy import CapabilityPolicy, PolicyDecision
from .tool_manifest import READ_TOOLS, DRAFT_TOOLS, CONTROLLED_TOOLS, EFFECT_TOOLS, all_tools

_policy = CapabilityPolicy()

_current_task_ctx: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "gateway_task_ctx", default=None
)


def set_task_context(ctx: dict | None) -> None:
    _current_task_ctx.set(ctx)


def get_task_context() -> dict | None:
    return _current_task_ctx.get()


_RUNTIME_KWARG_KEYS = {
    "task_id",
    "session_id",
    "user_task",
    "enabled_tools",
    "turn_id",
    "api_request_id",
}


def _normalise_invocation_args(config, kwargs: dict) -> dict:
    """Extract tool arguments from Hermes' registry invocation shape.

    Hermes' registry dispatch calls handlers as ``handler(args, task_id=...)``.
    Some direct tests and legacy wrappers call them as ``handler(None, **args)``.
    The marketing gateway must support both shapes; otherwise the model's
    visible function-call arguments are logged correctly while the business
    handler receives an empty parameter dict.
    """
    params: dict = {}
    if isinstance(config, dict):
        params.update(config)
    elif config is not None:
        # Be tolerant of pydantic/dataclass-ish config objects without binding
        # the gateway to any Hermes implementation detail.
        if hasattr(config, "model_dump"):
            try:
                dumped = config.model_dump()
                if isinstance(dumped, dict):
                    params.update(dumped)
            except Exception:
                pass
        elif hasattr(config, "__dict__"):
            params.update({k: v for k, v in vars(config).items() if not k.startswith("_")})

    for key, value in (kwargs or {}).items():
        if key in _RUNTIME_KWARG_KEYS:
            continue
        params[key] = value
    return params


def _wrap_handler(tool_name: str, handler_callable):
    """Return a handler that enforces policy and normalises output.

    Hermes passes the actual tool parameters as the first positional argument
    and runtime metadata as **kwargs.  Legacy direct calls may still pass the
    tool parameters as **kwargs, so both shapes are normalised here.
    """
    decision = _policy.evaluate(tool_name)

    def wrapped(_config=None, **kwargs) -> str:
        ctx = get_task_context()
        kwargs = _normalise_invocation_args(_config, dict(kwargs))
        # The selected account belongs to the durable task context, not to the
        # model.  Inject it before policy evaluation and approval persistence so
        # every controlled Electron action is bound to the same account.
        if ctx and ctx.get("account_id") and not kwargs.get("account_id"):
            kwargs["account_id"] = ctx["account_id"]
        user_id = ctx.get("user_id") if ctx else None
        session_auths = ctx.get("session_auths") if ctx else None

        session_constraints = session_auths.get(tool_name) if isinstance(session_auths, dict) else None
        session_allowed = session_constraints is not None and all(
            kwargs.get(key) == value for key, value in session_constraints.items()
        )
        if session_allowed:
            active_decision = PolicyDecision(
                allowed=True, approval_required=False,
                level=decision.level, reason="本次对话已授权 — 跳过审批",
            )
        elif user_id:
            active_decision = _policy.evaluate(tool_name, user_id=user_id, arguments=kwargs)
        else:
            active_decision = decision

        if not active_decision.allowed:
            return json.dumps({
                "status": "blocked",
                "error": active_decision.reason,
                "capability_level": active_decision.level.value,
            }, ensure_ascii=False)
        if active_decision.approval_required:
            ctx2 = get_task_context()
            if ctx2 is None:
                return json.dumps({
                    "status": "blocked",
                    "error": "任务上下文不可用，无法创建审批",
                    "capability_level": active_decision.level.value,
                }, ensure_ascii=False)
            store = ctx2.get("store")
            task_id = ctx2.get("task_id")
            if not store or not task_id:
                return json.dumps({
                    "status": "blocked",
                    "error": "任务存储或 ID 缺失",
                    "capability_level": active_decision.level.value,
                }, ensure_ascii=False)
            try:
                approval = store.create_approval(
                    task_id=task_id,
                    capability=tool_name,
                    arguments=kwargs,
                    risk_summary=active_decision.reason,
                )
                return json.dumps({
                    "status": "pending_approval",
                    "approval_id": approval["id"],
                    "capability": tool_name,
                    "arguments": kwargs,
                    "risk_summary": active_decision.reason,
                    "message": "该操作需要用户确认，请在界面中审批",
                }, ensure_ascii=False)
            except Exception as exc:
                logger.exception("approval creation failed for %s", tool_name)
                return json.dumps({
                    "status": "error",
                    "error": f"审批创建失败：{exc}",
                    "retryable": False,
                }, ensure_ascii=False)

        try:
            handler_params = dict(kwargs)
            if user_id:
                handler_params["__user_id"] = user_id
            if ctx and ctx.get("task_id"):
                handler_params["__task_id"] = ctx["task_id"]
            raw = handler_callable(handler_params)
            if isinstance(raw, str):
                try:
                    parsed = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    parsed = {"data": raw}
            elif isinstance(raw, dict):
                parsed = raw
            else:
                parsed = {"data": str(raw)}

            return json.dumps({
                "status": "ok",
                "data": parsed,
                "evidence": {
                    "tool": tool_name,
                    "capability_level": decision.level.value,
                    "approval_required": decision.approval_required,
                    "policy_reason": decision.reason,
                },
            }, ensure_ascii=False, default=str)
        except Exception as exc:
            logger.exception("tool %s failed", tool_name)
            from .models import classify_error
            category = classify_error(str(exc))
            return json.dumps({
                "status": "error",
                "error": str(exc),
                "error_category": category.value,
                "retryable": category.retryable,
                "retry_delay": category.default_retry_delay,
            }, ensure_ascii=False)

    wrapped.__name__ = tool_name
    return wrapped


def _register_all() -> int:
    """Register every tool from the manifest into Hermes' global registry.

    Returns the count of successfully registered tools.
    """
    try:
        from tools.registry import registry
    except ImportError:
        logger.warning("Hermes tool registry unavailable — tools not registered")
        return 0

    try:
        from toolsets import create_custom_toolset
    except ImportError:
        logger.warning("Hermes toolsets module unavailable")
        return 0

    tool_names: list[str] = []
    registered = 0

    for spec in all_tools():
        wrapped = _wrap_handler(spec.name, spec.handler)
        try:
            registry.register(
                name=spec.name,
                toolset="marketing-desktop",
                schema={
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": spec.schema,
                    },
                },
                handler=wrapped,
                description=spec.description,
                override=False,
            )
            tool_names.append(spec.name)
            registered += 1
        except Exception as exc:
            logger.warning("failed to register tool %s: %s", spec.name, exc)

    create_custom_toolset(
        name="marketing-desktop",
        description="智能营销桌面只读业务能力（受 L0-L4 确定性策略约束）",
        tools=tool_names,
    )

    return registered


_registered_count: int | None = None


def ensure_registered() -> int:
    """Register tools into Hermes registry. Idempotent — safe to call multiple times."""
    global _registered_count
    if _registered_count is not None:
        return _registered_count
    _registered_count = _register_all()
    logger.info("marketing-desktop toolset: %d tools registered", _registered_count)
    return _registered_count


def get_tool_count() -> int:
    return _registered_count or 0


def get_tool_names_by_level() -> dict[str, list[str]]:
    return {
        "L0_read_only": [t.name for t in READ_TOOLS],
        "L1_reversible_write": [t.name for t in DRAFT_TOOLS],
        "L2_controlled_resource": [t.name for t in CONTROLLED_TOOLS],
        "L3_external_effect": [t.name for t in EFFECT_TOOLS],
    }
