"""编排管线测试 — 七工具协作"""

import json
import pytest
from unittest.mock import patch
from tools.orchestration import (
    ingest_hot_topics, deep_research_notebooklm,
    create_content_pipeline, generate_media,
    publish_content, pipeline_status,
)
from tools.monitor import get_marketing_context


class TestPhase1Ingest:
    def test_default_platforms(self):
        with patch("tools.scraping._fetch_with_backend", return_value={"success": True, "backend_used": "mock", "data": []}):
            result = json.loads(ingest_hot_topics({}))
        assert result["phase"] == "ingest"
        assert len(result["platforms"]) == 3

    def test_selected_platforms(self):
        with patch("tools.scraping._fetch_with_backend", return_value={"success": True, "backend_used": "mock", "data": []}):
            result = json.loads(ingest_hot_topics({"platforms": ["weibo"]}))
        assert result["platforms"] == ["weibo"]
        assert "weibo" in result["results"]

    def test_output_schema(self):
        with patch("tools.scraping._fetch_with_backend", return_value={"success": True, "backend_used": "mock", "data": []}):
            result = json.loads(ingest_hot_topics({}))
        for p in result["platforms"]:
            assert p in result["results"]
            r = result["results"][p]
            assert isinstance(r, dict)
            # 每种后端输出都有特征字段
            has_key = "backend" in r or "error" in r
            assert has_key, f"{p} 缺少 backend/error 字段"


class TestPhase2Research:
    def test_no_topics(self):
        result = json.loads(deep_research_notebooklm({}))
        assert result["phase"] == "research"

    def test_with_topics(self):
        topics = [{"title": "AI大模型新突破"}, {"title": "苹果发布iOS 20"}]
        result = json.loads(deep_research_notebooklm({"topics": topics}))
        assert result["phase"] == "research"
        assert "topics_count" in result or "results" in result

    def test_string_topics(self):
        result = json.loads(deep_research_notebooklm({"topics": json.dumps([{"title": "test"}])}))
        assert result["phase"] == "research"


class TestPhase3Creation:
    def test_minimal_params(self):
        result = json.loads(create_content_pipeline({"script": "test content"}))
        assert result["phase"] == "creation"
        assert len(result["steps"]) >= 2

    def test_skip_humanize(self):
        result = json.loads(create_content_pipeline({"script": "test", "humanize": False}))
        steps = [s["step"] for s in result["steps"]]
        assert "humanize" not in steps

    def test_skip_illustrate(self):
        result = json.loads(create_content_pipeline({"script": "test", "illustrate": False}))
        steps = [s["step"] for s in result["steps"]]
        assert "illustrate" not in steps
        assert "cover_image" not in steps


class TestPhase4Media:
    def test_podcast_type(self):
        result = json.loads(generate_media({"type": "podcast", "content": "AI的未来"}))
        assert result["tool"] == "listenhub"

    def test_tts_type(self):
        result = json.loads(generate_media({"type": "tts", "content": "test"}))
        assert result["tool"] == "listenhub"

    def test_remotion_type(self):
        result = json.loads(generate_media({"type": "video_remotion", "content": "test"}))
        assert result["tool"] == "remotion"

    def test_short_video_apaas(self):
        result = json.loads(generate_media({"type": "video_short", "content": "test"}))
        assert result["tool"] == "apaas"
        assert result["protocol"] == "ACP"

    def test_unknown_type(self):
        result = json.loads(generate_media({"type": "unknown", "content": "test"}))
        assert "error" in result


class TestPhase5Publish:
    def test_wechat_weibo(self):
        result = json.loads(publish_content({
            "platforms": ["wechat", "weibo"],
            "content": "test content"
        }))
        assert result["phase"] == "publish"
        assert len(result["plan"]) == 2
        platforms = [p["platform"] for p in result["plan"]]
        assert "wechat" in platforms
        assert "weibo" in platforms

    def test_video_platforms_manual(self):
        result = json.loads(publish_content({
            "platforms": ["douyin", "bilibili"],
            "content": "test"
        }))
        assert len(result["plan"]) == 2
        for p in result["plan"]:
            assert p["tool"] == "manual"


class TestPipelineStatus:
    def test_status_schema(self):
        result = json.loads(pipeline_status())
        phases = ["phase1_ingest", "phase2_research", "phase3_creation",
                   "phase4_media", "phase5_publish"]
        for phase in phases:
            assert phase in result, f"缺少 {phase}"
            assert isinstance(result[phase], dict)

    def test_status_values_are_boolean_or_string(self):
        result = json.loads(pipeline_status())
        for phase_name, tools in result.items():
            if phase_name == "checked_at":
                continue
            for tool, status in tools.items():
                assert isinstance(status, (bool, str)), \
                    f"{phase_name}.{tool} = {status} ({type(status)})"


class TestEndToEndPipelineOrchestration:
    """五阶段管线数据流兼容性"""

    def test_full_pipeline_flow(self):
        # Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5
        with patch("tools.scraping._fetch_with_backend", return_value={"success": True, "backend_used": "mock", "data": []}):
            p1 = json.loads(ingest_hot_topics({}))
        assert p1["phase"] == "ingest"

        topics = [{"title": "AI"}, {"title": "科技"}]
        p2 = json.loads(deep_research_notebooklm({"topics": topics}))
        assert p2["phase"] == "research"

        p3 = json.loads(create_content_pipeline({"script": "AI发展趋势分析"}))
        assert p3["phase"] == "creation"

        p4 = json.loads(generate_media({"type": "podcast", "content": "AI趋势播客"}))
        assert p4["tool"] in ("listenhub", "remotion", "apaas")

        p5 = json.loads(publish_content({"platforms": ["weibo"], "content": "test"}))
        assert p5["phase"] == "publish"


def test_marketing_context_reads_persisted_desktop_data(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(tmp_path))
    (tmp_path / "trending-cache.json").write_text(json.dumps({"cached_at": "2026-06-28T10:00:00", "top_trends": [{"title": "行业热点"}]}))
    (tmp_path / "suggestions-cache.json").write_text(json.dumps({"suggestions": [{"trend": "行业热点", "angles": ["角度一"]}]}))
    (tmp_path / "intelligence-report.json").write_text(json.dumps({"status": "completed", "summary": {"trends_count": 1}}))
    (tmp_path / "intelligence-config.json").write_text(json.dumps({"industries": ["餐饮"]}))
    (tmp_path / "accounts.json").write_text(json.dumps({"accounts": [{"platform": "douyin", "label": "主账号", "status": "active", "stats": {"followers": 100}}]}))

    result = json.loads(get_marketing_context({"limit": 5}))
    assert result["source"] == "marketing-os-desktop"
    assert result["industries"] == ["餐饮"]
    assert result["trends"][0]["title"] == "行业热点"
    assert result["accounts"][0]["stats"]["followers"] == 100
