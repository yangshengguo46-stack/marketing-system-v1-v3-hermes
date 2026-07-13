"""Volcengine Speech V3 provider protocol and registration."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from agent.tts_registry import _reset_for_tests, get_provider
from plugins.tts.volcengine import (
    VolcengineSpeechError,
    VolcengineSpeechProvider,
    register,
)


def _response_events(audio: bytes = b"mp3-bytes") -> str:
    return "\n".join([
        json.dumps({"code": 0, "data": base64.b64encode(audio).decode()}),
        json.dumps({"code": 20000000, "message": "OK", "usage": {"text_words": 4}}),
    ])


def test_provider_sends_new_console_key_and_writes_audio_atomically(tmp_path):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            text=_response_events(),
            headers={"X-Tt-Logid": "log-1"},
        )

    provider = VolcengineSpeechProvider(
        "speech-key",
        base_url="https://speech.test",
        transport=httpx.MockTransport(handler),
    )
    result = provider.synthesize(
        "你好世界",
        str(tmp_path / "voice.wav"),
        speed=1.2,
        format="wav",
    )

    assert result.endswith("voice.mp3")
    assert (tmp_path / "voice.mp3").read_bytes() == b"mp3-bytes"
    assert captured["headers"]["x-api-key"] == "speech-key"
    assert "x-api-app-key" not in captured["headers"]
    assert captured["headers"]["x-api-resource-id"] == "seed-tts-2.0"
    params = captured["body"]["req_params"]
    assert params["speaker"] == "zh_female_vv_uranus_bigtts"
    assert params["speed_ratio"] == 1.2
    assert provider.last_receipt["usage"] == {"text_words": 4}
    assert "speech-key" not in json.dumps(provider.last_receipt)


def test_provider_rejects_terminal_error_without_writing_file(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=json.dumps({
            "code": 45000001,
            "message": "speaker unavailable",
        }))

    provider = VolcengineSpeechProvider(
        "speech-key",
        base_url="https://speech.test",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(VolcengineSpeechError, match="speaker unavailable"):
        provider.synthesize("测试", str(tmp_path / "voice.mp3"))
    assert not (tmp_path / "voice.mp3").exists()


def test_plugin_registers_native_tts_provider():
    class Context:
        def register_tts_provider(self, provider):
            from agent.tts_registry import register_provider

            register_provider(provider)

    _reset_for_tests()
    try:
        register(Context())
        assert isinstance(get_provider("volcengine-speech"), VolcengineSpeechProvider)
    finally:
        _reset_for_tests()
