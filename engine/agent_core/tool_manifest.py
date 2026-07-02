"""Minimal marketing-desktop tool manifest.

Only capabilities that are both implemented and safe are registered.  Product
writes and Electron-owned actions stay absent until the durable approval/effect
bridge can execute them without bypassing the capability boundary.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Callable

from .models import CapabilityLevel


@dataclass(frozen=True)
class ToolSpec:
    name: str
    level: CapabilityLevel
    description: str
    schema: dict[str, Any]
    handler: Callable[[dict], str]
    requires_approval: bool = False


def _schema(properties: dict | None = None) -> dict:
    return {"type": "object", "properties": properties or {}, "additionalProperties": False}


def _ensure_marketing_path() -> None:
    path = Path(__file__).resolve().parents[1] / "marketing-os"
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _server_read(function_name: str, *, pass_params: bool = False):
    def handler(params: dict) -> str:
        _ensure_marketing_path()
        server = import_module("server")
        function = getattr(server, function_name)
        result = function(params) if pass_params else function()
        return json.dumps(result, ensure_ascii=False, default=str)
    return handler


def _tool_read(module_name: str, function_name: str):
    def handler(params: dict) -> str:
        _ensure_marketing_path()
        module = import_module(f"marketing_tools.{module_name}")
        result = getattr(module, function_name)(params)
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    return handler


def _server_action(function_name: str):
    def handler(params: dict) -> str:
        _ensure_marketing_path()
        server = import_module("server")
        result = getattr(server, function_name)(params)
        return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    return handler


READ_TOOLS: list[ToolSpec] = [
    ToolSpec("marketing_read_context", CapabilityLevel.READ_ONLY,
             "读取最新行业目标、热点、选题、巡检报告和脱敏账号指标；数据缺失时保留真实状态",
             _schema({"limit": {"type": "integer", "minimum": 1, "maximum": 20}}),
             _tool_read("monitor", "get_marketing_context")),
    ToolSpec("marketing_read_trends", CapabilityLevel.READ_ONLY,
             "搜索已缓存热点趋势，按关键词、平台筛选本地缓存（非实时网络抓取）；"
             "结果保留来源、采集时间、URL 等完整证据",
             _schema({
                 "query": {"type": "string",
                           "description": "搜索关键词（匹配标题和分类，如 AI/教育/财经），留空返回全部"},
                 "platform": {"type": "string",
                              "description": "平台筛选：douyin / weibo / bilibili / zhihu"},
                 "limit": {"type": "integer", "minimum": 1, "maximum": 30, "default": 30},
             }),
             _server_read("query_trending_cache", pass_params=True)),
    ToolSpec("marketing_read_accounts", CapabilityLevel.READ_ONLY,
             "读取账号脱敏元信息和最近指标快照，不读取 Cookie",
             _schema(), _server_read("get_accounts_for_tool", pass_params=True)),
    ToolSpec("marketing_read_suggestions", CapabilityLevel.READ_ONLY,
             "读取已有选题建议及其依据和置信度",
             _schema(), _server_read("get_suggestions")),
    ToolSpec("marketing_read_dashboard", CapabilityLevel.READ_ONLY,
             "读取营销概览的真实持久数据",
             _schema(), _server_read("dashboard_overview")),
    ToolSpec("marketing_read_profiles", CapabilityLevel.READ_ONLY,
             "读取用户画像配置",
             _schema(), _server_read("get_profiles")),
    ToolSpec("marketing_read_intelligence_report", CapabilityLevel.READ_ONLY,
             "读取最近巡检步骤、错误、降级和证据",
             _schema(), _server_read("intelligence_report")),
    ToolSpec("marketing_read_analytics", CapabilityLevel.READ_ONLY,
             "读取发布分析汇总；无真实数据时返回空状态",
             _schema(), _server_read("analytics_summary")),
    ToolSpec("marketing_read_publishing_tasks", CapabilityLevel.READ_ONLY,
             "读取发布任务及状态，不执行发布或删除",
             _schema(), _server_read("publishing_tasks")),
    ToolSpec("marketing_read_workflow_status", CapabilityLevel.READ_ONLY,
             "读取巡检计划与最近运行状态",
             _schema(), _server_read("workflow_status")),
    ToolSpec("marketing_read_intelligence_config", CapabilityLevel.READ_ONLY,
             "读取巡检行业、平台和账号同步配置",
             _schema(), _server_read("intelligence_config")),
    ToolSpec("marketing_read_memory_list", CapabilityLevel.READ_ONLY,
             "读取已有记忆（用户画像、账号DNA、项目上下文、结果记录），支持按类型和账号筛选",
             _schema({
                 "kind": {"type": "string", "description": "记忆类型：user/account/episodic/semantic/procedural"},
                 "account_id": {"type": "string", "description": "按账号ID筛选"},
                 "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
             }),
             _server_read("get_memories", pass_params=True)),
    ToolSpec("marketing_read_content_list", CapabilityLevel.READ_ONLY,
             "列出内容资产（选题、脚本、视频、封面），支持按状态、类型、账号筛选",
             _schema({
                 "status": {"type": "string", "description": "状态：draft/review/approved/published"},
                 "type": {"type": "string", "description": "类型：script/video/image/caption"},
                 "account_id": {"type": "string", "description": "按账号ID筛选"},
             }),
             _server_read("get_content_assets", pass_params=True)),
]

def _noop(params: dict) -> str:
    return json.dumps({"status": "ok", "note": "handler intercepted by gateway"}, ensure_ascii=False)


CONTROLLED_TOOLS: list[ToolSpec] = [
    ToolSpec("marketing_trending_search", CapabilityLevel.CONTROLLED_RESOURCE,
             "使用平台登录会话搜索行业关键词内容，需要用户授权",
             _schema({
                 "platform": {"type": "string", "description": "平台标识", "enum": ["douyin"]},
                 "keyword": {"type": "string", "description": "搜索关键词"},
             }),
             _noop,
             requires_approval=True),
    ToolSpec("marketing_session_login", CapabilityLevel.CONTROLLED_RESOURCE,
             "打开平台登录窗口完成认证，需要用户授权",
             _schema({
                 "platform": {"type": "string", "description": "平台标识",
                              "enum": ["douyin", "weibo", "bilibili", "xiaohongshu",
                                       "kuaishou", "zhihu", "wechat_channels"]},
             }),
             _noop,
             requires_approval=True),
    ToolSpec("marketing_accounts_sync", CapabilityLevel.CONTROLLED_RESOURCE,
             "同步指定账号的最新指标（粉丝、点赞、播放），需要用户授权",
             _schema({
                 "platform": {"type": "string", "description": "平台", "enum": ["douyin", "bilibili"]},
                 "username": {"type": "string", "description": "账号 ID"},
             }),
             _noop,
             requires_approval=True),
]

DRAFT_TOOLS: list[ToolSpec] = [
    ToolSpec("marketing_draft_memory_add", CapabilityLevel.REVERSIBLE_WRITE,
             "写入一条结构化记忆（用户画像、账号DNA、项目上下文、结果记录），自动过滤秘密信息",
             _schema({
                 "kind": {"type": "string", "enum": ["user", "account", "episodic", "semantic", "procedural"]},
                 "content": {"type": "string", "description": "记忆内容"},
                 "account_id": {"type": "string", "description": "关联的账号ID"},
                 "platform": {"type": "string", "description": "关联的平台"},
                 "confidence": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.8},
             }),
             _server_action("add_memory"),
             ),
    ToolSpec("marketing_draft_content_create", CapabilityLevel.REVERSIBLE_WRITE,
             "创建内容草稿（选题/脚本/视频/封面），可指定平台和账号",
             _schema({
                 "title": {"type": "string", "description": "内容标题"},
                 "type": {"type": "string", "enum": ["script", "video", "image", "caption"], "default": "script"},
                 "platform": {"type": "string", "description": "目标平台"},
                 "account_id": {"type": "string", "description": "关联的账号ID"},
                 "content": {"type": "object", "description": "内容正文/URL等"},
             }),
             _server_action("create_content_asset"),
             ),
]

EFFECT_TOOLS: list[ToolSpec] = [
    ToolSpec("marketing_effect_publish", CapabilityLevel.EXTERNAL_EFFECT,
             "将内容资产正式发布到目标平台；"
             "每次都需要用户逐次确认，不可被 session/永久授权跳过",
             _schema({
                 "asset_id": {"type": "string", "description": "发布的内容资产ID"},
                 "platform": {"type": "string", "description": "目标平台",
                              "enum": ["douyin", "bilibili", "weibo", "xiaohongshu"]},
             }),
             _noop,
             requires_approval=True),
]


def all_tools() -> list[ToolSpec]:
    return [*READ_TOOLS, *DRAFT_TOOLS, *CONTROLLED_TOOLS, *EFFECT_TOOLS]


def tool_by_name(name: str) -> ToolSpec | None:
    return next((tool for tool in all_tools() if tool.name == name), None)
