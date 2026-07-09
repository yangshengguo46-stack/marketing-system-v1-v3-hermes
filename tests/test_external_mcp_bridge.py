"""Tests for external MCP bridge integration.

Verifies:
1. External server configs are well-defined
2. Tool mappings cover our capability levels correctly
3. Parameter translation works for each external tool
4. Platform coverage is comprehensive
5. Publish capability matrix is correct
6. Bridge gracefully handles unavailable servers
7. Our approval chain is enforced before external calls
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ENGINE_ROOT = Path(__file__).parent.parent / "engine"
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from agent_core.external_mcp_bridge import (
    HUIMEI_SERVER,
    DOUYIN_UPLOAD_SERVER,
    ALL_EXTERNAL_SERVERS,
    TOOL_MAPPINGS,
    ExternalMcpServer,
    ToolMapping,
    get_mappings_for_server,
    get_mapping,
    get_external_server,
    check_server_available,
    check_all_servers,
    McpStdioClient,
    bridge_call,
    _translate_params,
    get_platform_coverage,
    get_publish_capability_matrix,
)


class TestExternalServerConfigs:
    def test_huimei_server_config(self):
        assert HUIMEI_SERVER.name == "huimei"
        assert HUIMEI_SERVER.command == "huimei-mcp-server"
        assert len(HUIMEI_SERVER.platforms) == 10
        assert "douyin" in HUIMEI_SERVER.platforms
        assert "xhs" in HUIMEI_SERVER.platforms
        assert "bilibili" in HUIMEI_SERVER.platforms
        assert "weibo" not in HUIMEI_SERVER.platforms
        assert len(HUIMEI_SERVER.tools) == 6

    def test_douyin_upload_server_config(self):
        assert DOUYIN_UPLOAD_SERVER.name == "douyin-upload"
        assert DOUYIN_UPLOAD_SERVER.command == "node"
        assert DOUYIN_UPLOAD_SERVER.platforms == ["douyin"]
        assert "douyin_publish_video" in DOUYIN_UPLOAD_SERVER.tools
        assert "douyin_publish_imagetext" in DOUYIN_UPLOAD_SERVER.tools

    def test_all_servers_registered(self):
        assert len(ALL_EXTERNAL_SERVERS) == 5  # huimei, douyin-upload, voice-clone, image-gen, video-clip

    def test_server_names_unique(self):
        names = [s.name for s in ALL_EXTERNAL_SERVERS]
        assert len(names) == len(set(names))


class TestToolMappings:
    def test_all_mappings_have_our_name_prefix(self):
        for m in TOOL_MAPPINGS:
            assert m.our_name.startswith("marketing_"), f"{m.our_name} missing prefix"

    def test_effect_tools_require_approval(self):
        for m in TOOL_MAPPINGS:
            if m.capability_level == "effect":
                assert m.requires_approval, f"{m.our_name} is effect but no approval"

    def test_read_tools_dont_require_approval(self):
        for m in TOOL_MAPPINGS:
            if m.capability_level == "read":
                assert not m.requires_approval, f"{m.our_name} is read but requires approval"

    def test_huimei_mappings(self):
        mappings = get_mappings_for_server("huimei")
        assert len(mappings) == 5
        our_names = [m.our_name for m in mappings]
        assert "marketing_external_publish" in our_names
        assert "marketing_external_login" in our_names

    def test_douyin_upload_mappings(self):
        mappings = get_mappings_for_server("douyin-upload")
        assert len(mappings) == 3
        our_names = [m.our_name for m in mappings]
        assert "marketing_douyin_publish_video" in our_names
        assert "marketing_douyin_publish_imagetext" in our_names

    def test_voice_clone_mappings(self):
        mappings = get_mappings_for_server("voice-clone")
        assert len(mappings) == 4
        our_names = [m.our_name for m in mappings]
        assert "marketing_external_tts" in our_names
        assert "marketing_external_voice_clone" in our_names

    def test_image_gen_mappings(self):
        mappings = get_mappings_for_server("image-gen")
        assert len(mappings) == 2
        our_names = [m.our_name for m in mappings]
        assert "marketing_external_image_gen" in our_names

    def test_video_clip_mappings(self):
        mappings = get_mappings_for_server("video-clip")
        assert len(mappings) == 3
        our_names = [m.our_name for m in mappings]
        assert "marketing_external_video_clip" in our_names

    def test_get_mapping_returns_none_for_unknown(self):
        assert get_mapping("nonexistent") is None

    def test_get_mapping_returns_correct_mapping(self):
        m = get_mapping("marketing_external_publish")
        assert m is not None
        assert m.external_server == "huimei"
        assert m.external_tool == "huimei_publish"
        assert m.capability_level == "effect"


class TestParameterTranslation:
    def test_huimei_login_translation(self):
        params = _translate_params(
            ToolMapping("test", "huimei", "huimei_login", "controlled", True, "platform"),
            {"platform": "xhs"},
        )
        assert params == {"platform": "xhs"}

    def test_huimei_publish_translation(self):
        params = _translate_params(
            get_mapping("marketing_external_publish"),
            {
                "platforms": ["douyin", "xhs"],
                "media_type": "video",
                "file_path": "/tmp/video.mp4",
                "title": "测试标题",
                "description": "测试描述",
            },
        )
        assert params["platforms"] == ["douyin", "xhs"]
        assert params["media_type"] == "video"
        assert params["file_path"] == "/tmp/video.mp4"
        assert params["title"] == "测试标题"

    def test_douyin_publish_video_translation(self):
        params = _translate_params(
            get_mapping("marketing_douyin_publish_video"),
            {
                "file_path": "/tmp/video.mp4",
                "title": "抖音视频",
                "description": "描述",
                "timeout": 60000,
            },
        )
        assert params["filePath"] == "/tmp/video.mp4"
        assert params["title"] == "抖音视频"
        assert params["timeout"] == 60000

    def test_douyin_publish_imagetext_translation(self):
        params = _translate_params(
            get_mapping("marketing_douyin_publish_imagetext"),
            {
                "file_paths": ["/tmp/1.jpg", "/tmp/2.jpg"],
                "title": "图文",
                "description": "描述",
            },
        )
        assert params["filePaths"] == ["/tmp/1.jpg", "/tmp/2.jpg"]
        assert params["title"] == "图文"

    def test_douyin_check_login_translation(self):
        params = _translate_params(
            get_mapping("marketing_douyin_check_login"),
            {"sms_code": "123456"},
        )
        assert params["smsCode"] == "123456"


class TestPlatformCoverage:
    def test_douyin_covered_by_both_servers(self):
        coverage = get_platform_coverage()
        assert "douyin" in coverage
        assert "huimei" in coverage["douyin"]
        assert "douyin-upload" in coverage["douyin"]

    def test_xhs_covered_by_huimei(self):
        coverage = get_platform_coverage()
        assert "xhs" in coverage
        assert "huimei" in coverage["xhs"]

    def test_all_huimei_platforms_covered(self):
        coverage = get_platform_coverage()
        for platform in HUIMEI_SERVER.platforms:
            assert platform in coverage, f"{platform} not in coverage"
            assert "huimei" in coverage[platform]


class TestPublishCapabilityMatrix:
    def test_matrix_has_publish_tools(self):
        matrix = get_publish_capability_matrix()
        assert len(matrix) >= 6  # huimei publish + douyin video + douyin imagetext + tts + voice_clone + image_gen + video_clip + dub

    def test_all_publish_tools_require_approval(self):
        matrix = get_publish_capability_matrix()
        for entry in matrix:
            assert entry["requires_approval"] is True

    def test_matrix_includes_platforms(self):
        matrix = get_publish_capability_matrix()
        for entry in matrix:
            assert "platforms" in entry  # may be empty for non-platform tools


class TestServerAvailability:
    def test_check_huimei_available(self):
        with patch("shutil.which", return_value="/usr/local/bin/huimei-mcp-server"):
            result = check_server_available(HUIMEI_SERVER)
        assert result["available"] is True
        assert result["server"] == "huimei"

    def test_check_huimei_unavailable(self):
        with patch("shutil.which", return_value=None):
            result = check_server_available(HUIMEI_SERVER)
        assert result["available"] is False

    def test_check_all_servers(self):
        results = check_all_servers()
        assert len(results) == 5
        for r in results:
            assert "server" in r
            assert "available" in r


class TestBridgeCall:
    def test_bridge_returns_unavailable_when_not_installed(self):
        with patch("shutil.which", return_value=None):
            result = bridge_call("marketing_external_status", {})
        assert result["status"] == "unavailable"
        assert "huimei" in result["error"]

    def test_bridge_returns_error_for_unknown_tool(self):
        with pytest.raises(ValueError, match="No external mapping"):
            bridge_call("nonexistent_tool", {})

    def test_bridge_calls_external_tool(self):
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout.readline.return_value = (
            '{"jsonrpc":"2.0","id":1,"result":{"status":"ok","platforms":["douyin"]}}'
        )

        with patch("shutil.which", return_value="/usr/local/bin/huimei-mcp-server"):
            with patch("subprocess.Popen", return_value=mock_process):
                result = bridge_call("marketing_external_platforms", {})

        assert result["status"] == "ok"
        assert result["server"] == "huimei"
        assert result["tool"] == "huimei_platforms"

    def test_bridge_handles_external_error(self):
        mock_process = MagicMock()
        mock_process.poll.return_value = None
        mock_process.stdout.readline.return_value = (
            '{"jsonrpc":"2.0","id":1,"error":{"code":-1,"message":"login required"}}'
        )

        with patch("shutil.which", return_value="/usr/local/bin/huimei-mcp-server"):
            with patch("subprocess.Popen", return_value=mock_process):
                result = bridge_call("marketing_external_platforms", {})

        assert result["status"] == "error"
        assert "login required" in result["error"]


class TestMcpStdioClient:
    def test_start_and_stop(self):
        server = ExternalMcpServer("test", "echo", [])
        client = McpStdioClient(server)
        client.start()
        assert client._process is not None
        client.stop()
        assert client._process is None

    def test_call_tool_raises_when_not_running(self):
        server = ExternalMcpServer("test", "echo", [])
        client = McpStdioClient(server)
        with pytest.raises(RuntimeError, match="not running"):
            client.call_tool("test_tool", {})

    def test_context_manager(self):
        server = ExternalMcpServer("test", "echo", [])
        with McpStdioClient(server) as client:
            assert client._process is not None
        assert client._process is None

    def test_call_tool_times_out_instead_of_hanging(self):
        server = ExternalMcpServer("test", "unused", [], call_timeout_seconds=0.01)
        client = McpStdioClient(server)
        release = threading.Event()
        process = MagicMock()
        process.poll.return_value = None
        process.stdout.readline.side_effect = lambda: release.wait(1) or ""
        client._process = process

        try:
            with pytest.raises(TimeoutError, match="timed out"):
                client.call_tool("slow_tool", {})
        finally:
            release.set()


class TestApprovalChainEnforcement:
    """Verify that external tools go through our approval chain."""

    def test_all_effect_mappings_require_approval(self):
        effects = [m for m in TOOL_MAPPINGS if m.capability_level == "effect"]
        for m in effects:
            assert m.requires_approval is True

    def test_all_controlled_mappings_require_approval(self):
        controlled = [m for m in TOOL_MAPPINGS if m.capability_level == "controlled"]
        for m in controlled:
            assert m.requires_approval is True

    def test_no_external_tool_bypasses_approval(self):
        """No mapping should have effect level without approval."""
        for m in TOOL_MAPPINGS:
            if m.capability_level in ("effect", "controlled"):
                assert m.requires_approval, f"{m.our_name} bypasses approval!"
