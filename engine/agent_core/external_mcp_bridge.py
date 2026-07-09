"""External MCP Bridge — integrates open-source MCP servers as downstream tools.

Wraps external MCP servers (huimei, douyin-upload-mcp-skill) into our
marketing_* capability system, enforcing our approval/effect chain before
any external tool is called.

Architecture:
    Agent → tool_gateway (policy/approval) → external_mcp_bridge → external MCP server

External servers:
- huimei: Chinese social platforms (douyin/xhs/bilibili/ks/zhihu/...)
- douyin-upload-mcp-skill: douyin CDP automation (video/imagetext publish)

Key principle: external tools are NEVER exposed directly to the agent.
They are mapped to our marketing_* capabilities and go through the same
approval/effect chain as our native tools.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("marketing-os.external_mcp")

# ── External MCP server definitions ──────────────────────────────────

@dataclass(frozen=True)
class ExternalMcpServer:
    """Configuration for an external MCP server."""
    name: str
    command: str
    args: list[str]
    env: dict[str, str] = field(default_factory=dict)
    description: str = ""
    platforms: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    call_timeout_seconds: float = 30.0


# huimei: multi-platform social media publishing
HUIMEI_SERVER = ExternalMcpServer(
    name="huimei",
    command="huimei-mcp-server",
    args=[],
    description="中文社媒多平台发布 MCP Server",
    platforms=["douyin", "xhs", "bilibili", "ks", "tencent",
               "tk", "toutiao", "baijiahao", "weixingongzhonghao", "zhihu"],
    tools=["huimei_login", "huimei_status", "huimei_logout",
           "huimei_platforms", "huimei_accounts", "huimei_publish"],
)

# douyin-upload-mcp-skill: douyin CDP automation
DOUYIN_UPLOAD_SERVER = ExternalMcpServer(
    name="douyin-upload",
    command="node",
    args=["mcp-server.js"],
    env={"BROWSER_HEADLESS": "false"},
    description="抖音创作者平台 CDP 自动化上传 (视频/图文)",
    platforms=["douyin"],
    tools=["douyin_publish_video", "douyin_publish_imagetext",
           "douyin_check_login", "douyin_probe", "douyin_screenshot",
           "douyin_navigate_to", "douyin_reload_page", "douyin_browser_info"],
)

# mcp-voice-clone: TTS + voice cloning (Fish Audio for Chinese, ElevenLabs for English)
VOICE_CLONE_SERVER = ExternalMcpServer(
    name="voice-clone",
    command="python",
    args=["-m", "mcp_voice_clone"],
    env={"FISH_AUDIO_API_KEY": "", "ELEVENLABS_API_KEY": ""},
    description="语音克隆 + TTS (Fish Audio 中文最佳 / ElevenLabs 英文)",
    platforms=[],
    tools=["clone_voice", "speak", "list_voices", "generate_sfx"],
)

# mcp-image: AI image generation (Gemini + GPT Image)
IMAGE_GEN_SERVER = ExternalMcpServer(
    name="image-gen",
    command="npx",
    args=["@anthropic/mcp-image"],
    description="AI 图片生成 (Gemini Nano Banana / GPT Image)",
    platforms=[],
    tools=["generate_image", "edit_image", "optimize_prompt"],
)

# reap.video: video clipping + captioning
VIDEO_CLIP_SERVER = ExternalMcpServer(
    name="video-clip",
    command="npx",
    args=["@reap/mcp-server"],
    description="视频剪辑 + 字幕 + 配音 (YouTube 链接→短视频)",
    platforms=[],
    tools=["clip_video", "add_captions", "dub_video"],
)

ALL_EXTERNAL_SERVERS: list[ExternalMcpServer] = [
    HUIMEI_SERVER, DOUYIN_UPLOAD_SERVER,
    VOICE_CLONE_SERVER, IMAGE_GEN_SERVER, VIDEO_CLIP_SERVER,
]


# ── Tool mapping: external → our capability system ───────────────────

@dataclass(frozen=True)
class ToolMapping:
    """Maps an external MCP tool to our marketing_* capability."""
    our_name: str
    external_server: str
    external_tool: str
    capability_level: str  # read / controlled / effect
    requires_approval: bool
    platform_param: str | None = None  # which param carries the platform
    description: str = ""


TOOL_MAPPINGS: list[ToolMapping] = [
    # ── Voice clone: TTS + voice cloning ──
    ToolMapping(
        our_name="marketing_external_tts",
        external_server="voice-clone",
        external_tool="speak",
        capability_level="effect",
        requires_approval=True,
        description="生成语音 (TTS)，支持克隆声音",
    ),
    ToolMapping(
        our_name="marketing_external_voice_clone",
        external_server="voice-clone",
        external_tool="clone_voice",
        capability_level="effect",
        requires_approval=True,
        description="从音频样本克隆声音",
    ),
    ToolMapping(
        our_name="marketing_external_list_voices",
        external_server="voice-clone",
        external_tool="list_voices",
        capability_level="read",
        requires_approval=False,
        description="列出可用声音",
    ),
    ToolMapping(
        our_name="marketing_external_sfx",
        external_server="voice-clone",
        external_tool="generate_sfx",
        capability_level="effect",
        requires_approval=True,
        description="生成音效",
    ),
    # ── Image generation ──
    ToolMapping(
        our_name="marketing_external_image_gen",
        external_server="image-gen",
        external_tool="generate_image",
        capability_level="effect",
        requires_approval=True,
        description="AI 生成图片 (封面/缩略图/插画)",
    ),
    ToolMapping(
        our_name="marketing_external_image_edit",
        external_server="image-gen",
        external_tool="edit_image",
        capability_level="effect",
        requires_approval=True,
        description="AI 编辑图片",
    ),
    # ── Video clipping ──
    ToolMapping(
        our_name="marketing_external_video_clip",
        external_server="video-clip",
        external_tool="clip_video",
        capability_level="effect",
        requires_approval=True,
        description="从长视频剪辑短视频片段",
    ),
    ToolMapping(
        our_name="marketing_external_add_captions",
        external_server="video-clip",
        external_tool="add_captions",
        capability_level="controlled",
        requires_approval=True,
        description="为视频添加字幕",
    ),
    ToolMapping(
        our_name="marketing_external_dub_video",
        external_server="video-clip",
        external_tool="dub_video",
        capability_level="effect",
        requires_approval=True,
        description="为视频配音",
    ),
    # ── huimei: social media publishing ──
    ToolMapping(
        our_name="marketing_external_login",
        external_server="huimei",
        external_tool="huimei_login",
        capability_level="controlled",
        requires_approval=True,
        platform_param="platform",
        description="通过 huimei 打开平台登录流程",
    ),
    # huimei: status → read
    ToolMapping(
        our_name="marketing_external_status",
        external_server="huimei",
        external_tool="huimei_status",
        capability_level="read",
        requires_approval=False,
        description="查询 huimei 后端连接状态",
    ),
    # huimei: platforms → read
    ToolMapping(
        our_name="marketing_external_platforms",
        external_server="huimei",
        external_tool="huimei_platforms",
        capability_level="read",
        requires_approval=False,
        description="列出 huimei 支持的平台",
    ),
    # huimei: accounts → read
    ToolMapping(
        our_name="marketing_external_accounts",
        external_server="huimei",
        external_tool="huimei_accounts",
        capability_level="read",
        requires_approval=False,
        description="列出 huimei 已绑定的社媒账号",
    ),
    # huimei: publish → effect (highest level, always requires approval)
    ToolMapping(
        our_name="marketing_external_publish",
        external_server="huimei",
        external_tool="huimei_publish",
        capability_level="effect",
        requires_approval=True,
        platform_param="platforms",
        description="通过 huimei 发布内容到指定平台",
    ),
    # douyin-upload: publish_video → effect
    ToolMapping(
        our_name="marketing_douyin_publish_video",
        external_server="douyin-upload",
        external_tool="douyin_publish_video",
        capability_level="effect",
        requires_approval=True,
        platform_param=None,  # douyin only
        description="通过 CDP 自动化发布抖音视频",
    ),
    # douyin-upload: publish_imagetext → effect
    ToolMapping(
        our_name="marketing_douyin_publish_imagetext",
        external_server="douyin-upload",
        external_tool="douyin_publish_imagetext",
        capability_level="effect",
        requires_approval=True,
        platform_param=None,
        description="通过 CDP 自动化发布抖音图文",
    ),
    # douyin-upload: check_login → controlled
    ToolMapping(
        our_name="marketing_douyin_check_login",
        external_server="douyin-upload",
        external_tool="douyin_check_login",
        capability_level="controlled",
        requires_approval=True,
        platform_param=None,
        description="检查抖音登录状态并推进登录流程",
    ),
]


def get_mappings_for_server(server_name: str) -> list[ToolMapping]:
    """Get all tool mappings for a specific external server."""
    return [m for m in TOOL_MAPPINGS if m.external_server == server_name]


def get_mapping(our_name: str) -> ToolMapping | None:
    """Get tool mapping by our capability name."""
    return next((m for m in TOOL_MAPPINGS if m.our_name == our_name), None)


def get_external_server(name: str) -> ExternalMcpServer | None:
    """Get external server config by name."""
    return next((s for s in ALL_EXTERNAL_SERVERS if s.name == name), None)


# ── Server availability checks ───────────────────────────────────────

def check_server_available(server: ExternalMcpServer) -> dict[str, Any]:
    """Check if an external MCP server is available (command exists)."""
    cmd = shutil.which(server.command)
    return {
        "server": server.name,
        "command": server.command,
        "available": cmd is not None,
        "path": cmd,
        "platforms": server.platforms,
        "tools": server.tools,
    }


def check_all_servers() -> list[dict[str, Any]]:
    """Check availability of all configured external servers."""
    return [check_server_available(s) for s in ALL_EXTERNAL_SERVERS]


# ── MCP stdio client ─────────────────────────────────────────────────

class McpStdioClient:
    """Minimal MCP stdio client for calling external MCP servers.

    This is a simplified client that:
    1. Spawns the external MCP server as a subprocess
    2. Sends JSON-RPC tool calls via stdin
    3. Reads responses from stdout
    4. Handles process lifecycle

    In production, this would use the official MCP Python SDK client.
    For now, we implement a minimal protocol for testing and integration.
    """

    def __init__(self, server: ExternalMcpServer):
        self.server = server
        self._process: subprocess.Popen | None = None

    def start(self) -> None:
        """Start the external MCP server subprocess."""
        if self._process is not None and self._process.poll() is None:
            return
        env = {**os.environ, **self.server.env}
        self._process = subprocess.Popen(
            [self.server.command, *self.server.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )
        logger.info("Started external MCP server: %s (pid=%d)",
                     self.server.name, self._process.pid)

    def stop(self) -> None:
        """Stop the external MCP server subprocess."""
        if self._process is None:
            return
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
        self._process = None
        logger.info("Stopped external MCP server: %s", self.server.name)

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool on the external MCP server.

        Returns the tool result as a dict.
        Raises RuntimeError if the server is not available or the call fails.
        """
        if self._process is None or self._process.poll() is not None:
            raise RuntimeError(f"External MCP server {self.server.name} is not running")

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }

        self._process.stdin.write(json.dumps(request) + "\n")
        self._process.stdin.flush()

        responses: queue.Queue[str | BaseException] = queue.Queue(maxsize=1)

        def _read_response() -> None:
            try:
                responses.put(self._process.stdout.readline())
            except BaseException as exc:  # propagate pipe/decoder failures
                responses.put(exc)

        threading.Thread(target=_read_response, daemon=True).start()
        try:
            response_line = responses.get(timeout=self.server.call_timeout_seconds)
        except queue.Empty as exc:
            raise TimeoutError(
                f"MCP tool call timed out after {self.server.call_timeout_seconds:g}s: "
                f"{self.server.name}/{tool_name}"
            ) from exc
        if isinstance(response_line, BaseException):
            raise RuntimeError(f"Failed reading response from {self.server.name}") from response_line
        if not response_line:
            raise RuntimeError(f"No response from {self.server.name}")

        response = json.loads(response_line)
        if "error" in response:
            raise RuntimeError(f"MCP error from {self.server.name}: {response['error']}")

        return response.get("result", {})

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


# ── Bridge: our capability → external MCP tool ───────────────────────

def bridge_call(
    our_tool_name: str,
    params: dict[str, Any],
    *,
    server_override: str | None = None,
) -> dict[str, Any]:
    """Bridge a marketing_* capability call to an external MCP server.

    This function is called AFTER our tool_gateway has enforced policy
    and approval. It translates our parameters to the external tool's
    format and dispatches the call.

    Returns the external tool's result as a dict.
    """
    mapping = get_mapping(our_tool_name)
    if mapping is None:
        raise ValueError(f"No external mapping for tool: {our_tool_name}")

    server_name = server_override or mapping.external_server
    server = get_external_server(server_name)
    if server is None:
        raise ValueError(f"Unknown external server: {server_name}")

    # Check availability
    avail = check_server_available(server)
    if not avail["available"]:
        return {
            "status": "unavailable",
            "error": f"External MCP server '{server_name}' is not installed",
            "command": server.command,
        }

    # Translate parameters
    external_params = _translate_params(mapping, params)

    # Call external server
    client = McpStdioClient(server)
    try:
        client.start()
        result = client.call_tool(mapping.external_tool, external_params)
        return {
            "status": "ok",
            "server": server_name,
            "tool": mapping.external_tool,
            "result": result,
        }
    except Exception as e:
        return {
            "status": "error",
            "server": server_name,
            "tool": mapping.external_tool,
            "error": str(e),
        }
    finally:
        client.stop()


def _translate_params(mapping: ToolMapping, our_params: dict[str, Any]) -> dict[str, Any]:
    """Translate our marketing_* parameters to external tool's format.

    Each external tool has its own parameter schema. This function
    maps our normalized parameters to the external format.
    """
    if mapping.external_server == "huimei":
        if mapping.external_tool == "huimei_login":
            return {"platform": our_params.get("platform", "douyin")}
        if mapping.external_tool == "huimei_publish":
            return {
                "platforms": our_params.get("platforms", []),
                "media_type": our_params.get("media_type", "video"),
                "file_path": our_params.get("file_path", ""),
                "title": our_params.get("title", ""),
                "description": our_params.get("description", ""),
            }
        return our_params

    if mapping.external_server == "douyin-upload":
        if mapping.external_tool == "douyin_publish_video":
            return {
                "filePath": our_params.get("file_path", ""),
                "title": our_params.get("title", ""),
                "description": our_params.get("description", ""),
                "timeout": our_params.get("timeout", 120000),
            }
        if mapping.external_tool == "douyin_publish_imagetext":
            return {
                "filePaths": our_params.get("file_paths", []),
                "title": our_params.get("title", ""),
                "description": our_params.get("description", ""),
            }
        if mapping.external_tool == "douyin_check_login":
            return {"smsCode": our_params.get("sms_code", "")}
        return our_params

    return our_params


# ── Platform coverage summary ────────────────────────────────────────

def get_platform_coverage() -> dict[str, list[str]]:
    """Get which external servers cover which platforms."""
    coverage: dict[str, list[str]] = {}
    for server in ALL_EXTERNAL_SERVERS:
        for platform in server.platforms:
            if platform not in coverage:
                coverage[platform] = []
            coverage[platform].append(server.name)
    return coverage


def get_publish_capability_matrix() -> list[dict[str, Any]]:
    """Get the full publish capability matrix across external servers."""
    matrix = []
    for server in ALL_EXTERNAL_SERVERS:
        publish_tools = [
            m for m in TOOL_MAPPINGS
            if m.external_server == server.name and m.capability_level == "effect"
        ]
        for tool in publish_tools:
            matrix.append({
                "our_tool": tool.our_name,
                "external_server": server.name,
                "external_tool": tool.external_tool,
                "platforms": server.platforms,
                "requires_approval": tool.requires_approval,
            })
    return matrix
