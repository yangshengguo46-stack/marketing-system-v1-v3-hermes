import base64
import json
from pathlib import Path

import pytest

from agent_core.volcengine_tts_provider import (
    VolcengineTTSError,
    build_volcengine_tts_v1_payload,
    synthesize_volcengine_tts_v1,
)


def test_volcengine_tts_payload_uses_expected_v1_shape():
    payload = build_volcengine_tts_v1_payload(
        text="你好",
        reqid="r1",
        uid="u1",
        cluster="volcano_tts",
        voice_type="zh_female_test",
        encoding="mp3",
        speed_ratio=1.25,
    )

    assert payload["app"]["cluster"] == "volcano_tts"
    assert payload["audio"]["voice_type"] == "zh_female_test"
    assert payload["audio"]["encoding"] == "mp3"
    assert payload["audio"]["speed_ratio"] == 1.25
    assert payload["request"]["operation"] == "query"
    assert payload["request"]["text"] == "你好"


def test_volcengine_tts_writes_audio_and_redacts_secret_from_receipt(tmp_path):
    api_key = "secret-key-not-in-receipt"
    audio = b"\xff\xf3fake-mp3"

    def fake_transport(req, timeout):
        assert req.headers["X-api-key"] == api_key
        assert timeout == 45
        body = json.loads(req.data.decode("utf-8"))
        assert body["request"]["text"] == "你好 Marketing OS"
        return 200, json.dumps({
            "reqid": body["request"]["reqid"],
            "code": 3000,
            "operation": "query",
            "message": "Success",
            "data": base64.b64encode(audio).decode("ascii"),
            "addition": {"duration": "1234", "first_pkg": "88"},
        }).encode("utf-8"), {"x-tt-logid": "log-1"}

    receipt = synthesize_volcengine_tts_v1(
        text="  你好   Marketing OS ",
        api_key=api_key,
        output_dir=tmp_path,
        transport=fake_transport,
    )

    assert receipt["status"] == "ok"
    assert receipt["provider"] == "volcengine_tts_v1"
    assert receipt["duration_ms"] == 1234
    assert receipt["first_pkg_ms"] == 88
    assert receipt["byte_size"] == len(audio)
    assert receipt["response_log_id"] == "log-1"
    assert receipt["output_path"].endswith(".mp3")
    assert Path(receipt["output_path"]).read_bytes() == audio
    assert "secret" not in json.dumps(receipt, ensure_ascii=False)


def test_volcengine_tts_raises_clean_error_on_provider_failure(tmp_path):
    def fake_transport(_req, _timeout):
        return 401, b'{"code": 4001, "message": "Invalid API Key"}', {}

    with pytest.raises(VolcengineTTSError, match="Invalid API Key"):
        synthesize_volcengine_tts_v1(
            text="hello",
            api_key="bad-key",
            output_dir=tmp_path,
            transport=fake_transport,
        )


def test_volcengine_tts_requires_text(tmp_path):
    with pytest.raises(VolcengineTTSError, match="text is required"):
        synthesize_volcengine_tts_v1(text=" ", api_key="key", output_dir=tmp_path)
