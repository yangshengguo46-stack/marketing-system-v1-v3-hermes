"""Volcengine Doubao Speech V3 TTS provider.

The new Speech console issues an API Key that is sent only as ``X-Api-Key``.
It is intentionally separate from Ark image/video credentials.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx

from agent.tts_provider import DEFAULT_OUTPUT_FORMAT, TTSProvider

DEFAULT_BASE_URL = "https://openspeech.bytedance.com"
DEFAULT_RESOURCE_ID = "seed-tts-2.0"
DEFAULT_MODEL = "seed-tts-2.0"
DEFAULT_VOICE = "zh_female_vv_uranus_bigtts"
DEFAULT_SAMPLE_RATE = 24000

_FORMAT_MAP = {
    "mp3": ("mp3", ".mp3"),
    "ogg": ("ogg_opus", ".ogg"),
    "opus": ("ogg_opus", ".ogg"),
}


class VolcengineSpeechError(RuntimeError):
    """A provider response ended without valid synthesized audio."""


class VolcengineSpeechProvider(TTSProvider):
    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        resource_id: str = DEFAULT_RESOURCE_ID,
        default_voice: str = DEFAULT_VOICE,
        timeout_sec: float = 60.0,
        trust_env: bool = False,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._resource_id = resource_id
        self._default_voice = default_voice
        self._timeout_sec = timeout_sec
        self._trust_env = trust_env
        self._transport = transport
        self.last_receipt: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "volcengine-speech"

    @property
    def display_name(self) -> str:
        return "Volcengine Doubao Speech 2.0"

    @property
    def voice_compatible(self) -> bool:
        return True

    def _resolved_api_key(self) -> str:
        if self._api_key is not None:
            return self._api_key.strip()
        try:
            # Dynamic lookup preserves Hermes profile-scoped secret isolation.
            from hermes_cli.config import get_env_value

            key = get_env_value("VOLCENGINE_SPEECH_API_KEY") or ""
        except ImportError:
            key = os.getenv("VOLCENGINE_SPEECH_API_KEY", "")
        return key.strip()

    def is_available(self) -> bool:
        return bool(self._resolved_api_key())

    def list_models(self) -> list[dict[str, Any]]:
        return [{
            "id": DEFAULT_MODEL,
            "display": "Doubao Speech Synthesis 2.0",
            "languages": ["zh", "en"],
            "max_text_length": 5000,
        }]

    def list_voices(self) -> list[dict[str, Any]]:
        # Keep this catalog evidence-based. More voices can be added after a
        # console/API calibration rather than copying a stale public list.
        return [{
            "id": DEFAULT_VOICE,
            "display": "Vivi - Chinese female",
            "language": "zh-CN",
            "gender": "female",
        }]

    def default_model(self) -> str:
        return DEFAULT_MODEL

    def default_voice(self) -> str:
        return self._default_voice

    def get_setup_schema(self) -> dict[str, Any]:
        return {
            "name": self.display_name,
            "badge": "paid",
            "tag": "Seed TTS 2.0; new-console API Key",
            "env_vars": [{
                "key": "VOLCENGINE_SPEECH_API_KEY",
                "prompt": "Volcengine Speech API Key",
                "url": "https://console.volcengine.com/speech",
            }],
        }

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout_sec,
            trust_env=self._trust_env,
            transport=self._transport,
        )

    def _synthesize_bytes(
        self,
        text: str,
        *,
        voice: str,
        model: str,
        speed: float | None,
        api_format: str,
        emotion: str = "",
    ) -> bytes:
        key = self._resolved_api_key()
        if not key:
            raise VolcengineSpeechError("VOLCENGINE_SPEECH_API_KEY is not configured")
        if model != DEFAULT_MODEL:
            raise ValueError(f"unsupported Volcengine speech model: {model}")

        request_id = str(uuid.uuid4())
        headers = {
            "X-Api-Key": key,
            "X-Api-Resource-Id": self._resource_id,
            "X-Api-Request-Id": request_id,
            "X-Control-Require-Usage-Tokens-Return": "*",
            "Content-Type": "application/json",
        }
        req_params: dict[str, Any] = {
            "text": text,
            "speaker": voice,
            "audio_params": {
                "format": api_format,
                "sample_rate": DEFAULT_SAMPLE_RATE,
            },
        }
        if speed is not None:
            req_params["speed_ratio"] = max(0.2, min(3.0, float(speed)))
        if emotion:
            req_params["emotion"] = emotion

        with self._client() as client:
            response = client.post(
                "/api/v3/tts/unidirectional",
                headers=headers,
                json={
                    "user": {"uid": "hermes-tts"},
                    "req_params": req_params,
                },
            )
        response.raise_for_status()

        audio = bytearray()
        terminal: dict[str, Any] = {}
        for raw_line in response.text.splitlines():
            if not raw_line.strip():
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise VolcengineSpeechError("invalid JSON event from speech provider") from exc
            code = int(event.get("code", -1))
            if event.get("data"):
                try:
                    audio.extend(base64.b64decode(event["data"], validate=True))
                except (ValueError, TypeError) as exc:
                    raise VolcengineSpeechError("invalid audio payload from speech provider") from exc
            if code == 20000000:
                terminal = event
            elif code not in {0, 20000000}:
                message = str(event.get("message") or f"provider code {code}")
                raise VolcengineSpeechError(message[:500])

        if not terminal or not audio:
            raise VolcengineSpeechError("speech provider returned no completed audio")
        self.last_receipt = {
            "provider": "volcengine_speech",
            "model": model,
            "voice": voice,
            "request_id": request_id,
            "log_id": response.headers.get("X-Tt-Logid", ""),
            "usage": terminal.get("usage") or {},
            "audio_bytes": len(audio),
        }
        return bytes(audio)

    def synthesize(
        self,
        text: str,
        output_path: str,
        *,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        speed: Optional[float] = None,
        format: str = DEFAULT_OUTPUT_FORMAT,
        **extra: Any,
    ) -> str:
        text = text.strip()
        if not text:
            raise ValueError("speech text is required")
        api_format, suffix = _FORMAT_MAP.get(format.lower(), _FORMAT_MAP["mp3"])
        requested = Path(output_path).expanduser().resolve()
        destination = requested.with_suffix(suffix)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = self._synthesize_bytes(
            text,
            voice=voice or self.default_voice(),
            model=model or self.default_model(),
            speed=speed,
            api_format=api_format,
            emotion=str(extra.get("emotion") or "").strip(),
        )

        fd, temporary = tempfile.mkstemp(dir=destination.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return str(destination)


def register(ctx) -> None:
    ctx.register_tts_provider(VolcengineSpeechProvider())
