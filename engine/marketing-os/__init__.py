"""marketing-os: 基于 Hermes 的智能营销系统"""

import json
import logging

logger = logging.getLogger("marketing-os")

PLUGIN_VERSION = "0.1.0"


def register(ctx):
    """插件注册入口 — Hermes 加载插件时调用"""
    logger.info(f"[marketing-os v{PLUGIN_VERSION}] 注册中...")

    # ---- 注册工具集 ----
    _register_scraping_tools(ctx)
    _register_account_tools(ctx)
    _register_content_tools(ctx)
    _register_orchestration_tools(ctx)
    _register_monitor_tools(ctx)

    # ---- 注册生命周期钩子 ----
    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("on_session_end", _on_session_end)
    from .tools.channel_context import pre_gateway_dispatch
    ctx.register_hook("pre_gateway_dispatch", pre_gateway_dispatch)

    logger.info("[marketing-os] 注册完成")


def _on_session_start(session_id, **kwargs):
    logger.info(f"[marketing-os] 会话开始: {session_id}")


def _on_session_end(session_id, **kwargs):
    logger.info(f"[marketing-os] 会话结束: {session_id}")


# ---- 内部: 注册各模块工具 ----

def _register_scraping_tools(ctx):
    from .tools.scraping import TOOLS
    for t in TOOLS:
        ctx.register_tool(
            name=t["name"],
            toolset="marketing-os",
            schema=t["schema"],
            handler=t["handler"],
            description=t["description"],
        )


def _register_account_tools(ctx):
    from .tools.account import TOOLS
    for t in TOOLS:
        ctx.register_tool(
            name=t["name"],
            toolset="marketing-os",
            schema=t["schema"],
            handler=t["handler"],
            description=t["description"],
        )


def _register_content_tools(ctx):
    from .tools.content import TOOLS
    for t in TOOLS:
        ctx.register_tool(
            name=t["name"],
            toolset="marketing-os",
            schema=t["schema"],
            handler=t["handler"],
            description=t["description"],
        )


def _register_orchestration_tools(ctx):
    from .tools.orchestration import TOOLS
    for t in TOOLS:
        ctx.register_tool(
            name=t["name"],
            toolset="marketing-os",
            schema=t["schema"],
            handler=t["handler"],
            description=t["description"],
        )


def _register_monitor_tools(ctx):
    from .tools.monitor import TOOLS
    for t in TOOLS:
        ctx.register_tool(
            name=t["name"],
            toolset="marketing-os",
            schema=t["schema"],
            handler=t["handler"],
            description=t["description"],
        )
