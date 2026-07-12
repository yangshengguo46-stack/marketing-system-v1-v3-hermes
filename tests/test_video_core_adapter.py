"""VolcengineAdapter 单元测试（VIDEO-03）：httpx.MockTransport，无真实网络。

响应形状全部按 2026-07-11 真实校准记录构造（见 adapter.py docstring / 台账）。
"""

import asyncio
import json

import httpx
import pytest

from engine.video_core.adapter import (
    AdapterError,
    ModelTier,
    QuotaError,
    ReferenceAssets,
    VideoTaskStatus,
    VolcengineAdapter,
)

BASE = "https://ark.test/api/v3"


def _adapter(handler, **kwargs):
    return VolcengineAdapter(
        "test-key", BASE, transport=httpx.MockTransport(handler), max_retries=1, **kwargs
    )


# ------------------------------------------------------------------ 图片


def test_generate_image_downloads_bytes():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/images/generations"):
            captured["body"] = json.loads(request.content)
            captured["auth"] = request.headers["Authorization"]
            return httpx.Response(200, json={
                "model": "doubao-seedream-5-0-260128",
                "data": [{"url": f"{BASE}/fake.jpeg", "size": "1920x1920"}],
                "usage": {"generated_images": 1, "output_tokens": 14400},
            })
        return httpx.Response(200, content=b"jpeg-bytes", headers={"content-type": "image/jpeg"})

    results = asyncio.run(_adapter(handler).generate_image("小猫", seed=42, n=1))
    assert captured["auth"] == "Bearer test-key"
    assert captured["body"]["size"] == "1920x1920"        # 校准的默认下限
    assert captured["body"]["seed"] == 42
    assert results[0].file_bytes == b"jpeg-bytes"
    assert results[0].mime == "image/jpeg"
    assert results[0].raw["usage"]["output_tokens"] == 14400


# ------------------------------------------------------------------ 视频提交


def test_submit_builds_content_with_suffix_and_first_frame(tmp_path):
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"png")
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "cgt-123"})

    handle = asyncio.run(_adapter(handler).submit_video_task(
        "小猫奔跑", tier=ModelTier.AUDITION, first_frame_path=str(frame),
        duration_sec=4.2, resolution="720p",
    ))
    body = captured["body"]
    assert handle.task_id == "cgt-123"
    assert body["model"] == "doubao-seedance-2-0-fast-260128"   # 替身档映射
    assert body["content"][0]["text"] == "小猫奔跑 --resolution 720p --duration 4"
    frame_item = body["content"][1]
    assert frame_item["role"] == "first_frame"
    assert frame_item["image_url"]["url"].startswith("data:image/png;base64,")


def test_submit_with_references_appends_items():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "cgt-9"})

    refs = ReferenceAssets(image_paths=["https://cdn/img1.png", "https://cdn/img2.png"])
    asyncio.run(_adapter(handler).submit_video_task("镜头", references=refs))
    items = captured["body"]["content"]
    assert captured["body"]["model"] == "doubao-seedance-2-0-260128"  # 正片档默认
    assert [i.get("role") for i in items[1:]] == ["reference_image", "reference_image"]
    assert items[1]["image_url"]["url"] == "https://cdn/img1.png"     # URL 透传


# ------------------------------------------------------------------ 轮询


def test_query_maps_succeeded_shape():
    def handler(request):
        return httpx.Response(200, json={
            "id": "cgt-1", "status": "succeeded",
            "content": {"video_url": "https://tos/video.mp4"},
            "usage": {"completion_tokens": 87300},
            "seed": 99061, "resolution": "720p", "duration": 4,
        })

    result = asyncio.run(_adapter(handler).query_video_task("cgt-1"))
    assert result.status == VideoTaskStatus.SUCCEEDED
    assert result.video_url == "https://tos/video.mp4"
    assert result.duration_sec == 4.0
    assert result.raw["seed"] == 99061
    assert "content" not in result.raw


def test_query_maps_running_and_failed():
    responses = iter([
        {"id": "t", "status": "running"},
        {"id": "t", "status": "failed", "error": {"message": "content policy"}},
    ])

    def handler(request):
        return httpx.Response(200, json=next(responses))

    adapter = _adapter(handler)
    first = asyncio.run(adapter.query_video_task("t"))
    second = asyncio.run(adapter.query_video_task("t"))
    assert first.status == VideoTaskStatus.RUNNING and first.video_url == ""
    assert second.status == VideoTaskStatus.FAILED
    assert second.error_message == "content policy"


# ------------------------------------------------------------------ 取消


def test_cancel_treats_409_as_noop():
    def handler(request):
        assert request.method == "DELETE"
        return httpx.Response(409, json={"error": {
            "code": "InvalidAction.RunningTaskDeletion", "message": "cannot delete"}})

    asyncio.run(_adapter(handler).cancel_video_task("cgt-1"))   # 不应抛异常


# ------------------------------------------------------------------ 错误与重试


def test_429_raises_quota_error_after_retries():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    with pytest.raises(QuotaError):
        asyncio.run(_adapter(handler).query_video_task("t"))
    assert calls["n"] == 2      # max_retries=1 → 初次 + 1 重试


def test_5xx_retries_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(502, text="bad gateway")
        return httpx.Response(200, json={"id": "t", "status": "running"})

    result = asyncio.run(_adapter(handler).query_video_task("t"))
    assert result.status == VideoTaskStatus.RUNNING
    assert calls["n"] == 2


def test_4xx_fails_fast_without_retry():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, json={"error": {
            "code": "InvalidParameter", "message": "image size must be at least 3686400 pixels"}})

    with pytest.raises(AdapterError, match="InvalidParameter"):
        asyncio.run(_adapter(handler).generate_image("x", size="1024x1024"))
    assert calls["n"] == 1
