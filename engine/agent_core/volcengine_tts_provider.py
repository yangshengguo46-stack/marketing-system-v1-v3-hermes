"""Volcengine TTS provider boundary.

This module is intentionally small and effect-explicit.  It performs one
network request, writes one audio file, and returns an auditable receipt that
can be attached to content assets.  API keys are accepted as function arguments
or environment variables, but are never written into receipts.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib import error, request


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENDPOINT = "https://openspeech.bytedance.com/api/v1/tts"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "runtime" / "tts-cache"
DEFAULT_CLUSTER = "volcano_tts"
DEFAULT_VOICE_TYPE = "zh_female_shuangkuaisisi_moon_bigtts"
DEFAULT_ENCODING = "mp3"
MAX_TEXT_CHARS = 5000


class VolcengineTTSError(RuntimeError):
    """Raised when Volcengine TTS cannot synthesize an audio file."""


Transport = Callable[[request.Request, int], tuple[int, bytes, dict[str, str]]]


def synthesize_volcengine_tts_v1(
    *,
    text: str,
    api_key: str | None = None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    output_path: str | Path | None = None,
    voice_type: str = DEFAULT_VOICE_TYPE,
    cluster: str = DEFAULT_CLUSTER,
    encoding: str = DEFAULT_ENCODING,
    speed_ratio: float = 1.0,
    uid: str = "marketing-os",
    endpoint: str = DEFAULT_ENDPOINT,
    timeout: int = 45,
    transport: Transport | None = None,
) -> dict[str, Any]:
    """Synthesize text using Volcengine's v1 HTTP TTS endpoint.

    The function writes the returned base64 audio to ``output_path`` or a
    deterministic runtime cache path and returns an audit receipt.  The API key
    is read from ``api_key`` first and ``VOLCENGINE_TTS_API_KEY`` second.
    """

    clean_text = _clean_text(text)
    key = (api_key or os.environ.get("VOLCENGINE_TTS_API_KEY") or "").strip()
    if not key:
        raise VolcengineTTSError("VOLCENGINE_TTS_API_KEY is required")
    if not voice_type.strip():
        raise VolcengineTTSError("voice_type is required")

    reqid = str(uuid.uuid4())
    payload = build_volcengine_tts_v1_payload(
        text=clean_text,
        reqid=reqid,
        uid=uid,
        cluster=cluster,
        voice_type=voice_type,
        encoding=encoding,
        speed_ratio=speed_ratio,
    )
    req = request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        headers={"x-api-key": key, "Content-Type": "application/json"},
        method="POST",
    )
    status, body, response_headers = (transport or _urlopen_transport)(req, timeout)
    response = _json_body(body)
    if status != 200 or int(response.get("code") or 0) != 3000 or not response.get("data"):
        message = str(response.get("message") or response.get("error") or "Volcengine TTS failed")
        raise VolcengineTTSError(f"{message} (http={status}, code={response.get('code')})")

    audio = base64.b64decode(str(response["data"]))
    if not audio:
        raise VolcengineTTSError("Volcengine TTS returned empty audio")

    output = Path(output_path) if output_path else _default_output_path(
        Path(output_dir), reqid=reqid, encoding=encoding,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(audio)

    sha256 = hashlib.sha256(audio).hexdigest()
    addition = response.get("addition") if isinstance(response.get("addition"), dict) else {}
    duration_ms = _int_or_none(addition.get("duration"))
    duration_sec = _probe_duration(output) or ((duration_ms / 1000.0) if duration_ms else None)

    return {
        "status": "ok",
        "provider": "volcengine_tts_v1",
        "endpoint": endpoint,
        "cluster": cluster,
        "voice_type": voice_type,
        "encoding": encoding,
        "reqid": str(response.get("reqid") or reqid),
        "operation": response.get("operation"),
        "message": response.get("message"),
        "http_status": status,
        "code": response.get("code"),
        "output_path": str(output),
        "byte_size": len(audio),
        "sha256": sha256,
        "duration_ms": duration_ms,
        "duration_sec": duration_sec,
        "first_pkg_ms": _int_or_none(addition.get("first_pkg")),
        "text_sha256": hashlib.sha256(clean_text.encode("utf-8")).hexdigest(),
        "created_at_unix": int(time.time()),
        "response_log_id": response_headers.get("x-tt-logid") or response_headers.get("X-Tt-Logid") or "",
    }


def build_volcengine_tts_v1_payload(
    *,
    text: str,
    reqid: str,
    uid: str,
    cluster: str,
    voice_type: str,
    encoding: str,
    speed_ratio: float,
) -> dict[str, Any]:
    return {
        "app": {"cluster": cluster},
        "user": {"uid": uid},
        "audio": {
            "voice_type": voice_type,
            "encoding": encoding,
            "speed_ratio": max(0.2, min(3.0, float(speed_ratio or 1.0))),
        },
        "request": {
            "reqid": reqid,
            "text": text,
            "operation": "query",
        },
    }


def _urlopen_transport(req: request.Request, timeout: int) -> tuple[int, bytes, dict[str, str]]:
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read(), dict(resp.headers.items())
    except error.HTTPError as exc:
        return int(exc.code), exc.read(), dict(exc.headers.items())
    except Exception as exc:  # pragma: no cover - exact network errors vary by platform
        raise VolcengineTTSError(f"transport error: {type(exc).__name__}: {exc}") from exc


def _json_body(body: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise VolcengineTTSError(f"non-json response: {body[:200]!r}") from exc
    if not isinstance(parsed, dict):
        raise VolcengineTTSError("unexpected non-object response")
    return parsed


def _clean_text(text: str) -> str:
    clean = " ".join(str(text or "").split())
    if not clean:
        raise VolcengineTTSError("text is required")
    if len(clean) > MAX_TEXT_CHARS:
        raise VolcengineTTSError(f"text is too long: {len(clean)} > {MAX_TEXT_CHARS}")
    return clean


def _default_output_path(output_dir: Path, *, reqid: str, encoding: str) -> Path:
    suffix = (encoding or DEFAULT_ENCODING).lower().lstrip(".")
    safe_suffix = suffix if suffix in {"mp3", "wav", "ogg", "pcm", "aac", "m4a"} else DEFAULT_ENCODING
    return output_dir / f"volcengine_{reqid}.{safe_suffix}"


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _probe_duration(path: Path) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return None
