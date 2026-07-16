"""Deterministic technical QA for rendered Marketing OS videos."""

from __future__ import annotations

import json
import math
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


QUALITY_REPORT_VERSION = "marketing.media_quality.v1"
_CommandRunner = Callable[[list[str], int], subprocess.CompletedProcess[str]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_runner(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class VideoQualityAnalyzer:
    """Probe one final video and return a receipt-safe QA report."""

    def __init__(
        self,
        *,
        ffmpeg_path: str,
        ffprobe_path: str,
        runner: _CommandRunner | None = None,
    ) -> None:
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.runner = runner or _default_runner

    def analyze(
        self,
        path: Path,
        *,
        expected_duration: float,
        expected_width: int,
        expected_height: int,
        audio_expected: bool,
    ) -> dict[str, Any]:
        probe = self._probe(path)
        scan = self._scan(path)
        checks = [
            self._technical_check(
                probe,
                expected_duration=expected_duration,
                expected_width=expected_width,
                expected_height=expected_height,
            ),
            self._black_check(scan["black_events"], expected_duration),
            self._freeze_check(scan["freeze_events"], expected_duration),
            self._audio_check(
                probe,
                loudness=scan["loudness"],
                audio_expected=audio_expected,
            ),
        ]
        failed = [check for check in checks if check["status"] == "fail"]
        if any(check["severity"] == "critical" for check in failed):
            disposition = "reject"
        elif failed:
            disposition = "hold"
        else:
            disposition = "ready"
        return {
            "version": QUALITY_REPORT_VERSION,
            "disposition": disposition,
            "analyzed_at": _now(),
            "checks": checks,
            "probe": probe,
        }

    def _probe(self, path: Path) -> dict[str, Any]:
        result = self.runner(
            [
                self.ffprobe_path,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ],
            30,
        )
        payload = json.loads(result.stdout)
        streams = payload.get("streams") or []
        video = next(
            (stream for stream in streams if stream.get("codec_type") == "video"),
            {},
        )
        audio = next(
            (stream for stream in streams if stream.get("codec_type") == "audio"),
            {},
        )
        format_info = payload.get("format") or {}
        return {
            "duration_seconds": _float_or_none(format_info.get("duration")),
            "video": {
                "present": bool(video),
                "codec": video.get("codec_name"),
                "width": int(video.get("width") or 0),
                "height": int(video.get("height") or 0),
                "frame_rate": video.get("avg_frame_rate")
                or video.get("r_frame_rate"),
                "pixel_format": video.get("pix_fmt"),
            },
            "audio": {
                "present": bool(audio),
                "codec": audio.get("codec_name"),
                "sample_rate": int(audio.get("sample_rate") or 0),
                "channels": int(audio.get("channels") or 0),
            },
        }

    def _scan(self, path: Path) -> dict[str, Any]:
        result = self.runner(
            [
                self.ffmpeg_path,
                "-hide_banner",
                "-nostats",
                "-i",
                str(path),
                "-vf",
                "blackdetect=d=0.5:pix_th=0.10,freezedetect=n=-50dB:d=1.0",
                "-af",
                "loudnorm=I=-14:TP=-1:LRA=11:print_format=json",
                "-f",
                "null",
                "-",
            ],
            180,
        )
        output = f"{result.stdout}\n{result.stderr}"
        return {
            "black_events": _black_events(output),
            "freeze_events": _freeze_events(output),
            "loudness": _loudness_metrics(output),
        }

    @staticmethod
    def _technical_check(
        probe: dict[str, Any],
        *,
        expected_duration: float,
        expected_width: int,
        expected_height: int,
    ) -> dict[str, Any]:
        video = probe["video"]
        duration = probe.get("duration_seconds")
        failures = []
        if not video["present"]:
            failures.append("missing video stream")
        if video["width"] != expected_width or video["height"] != expected_height:
            failures.append("dimensions do not match approved canvas")
        if duration is None or abs(duration - expected_duration) > 0.12:
            failures.append("duration does not match approved timeline")
        return _check(
            check_id="technical_delivery",
            label="技术规格",
            failed=bool(failures),
            severity="critical",
            evidence={
                "failures": failures,
                "actual": {
                    "duration_seconds": duration,
                    "width": video["width"],
                    "height": video["height"],
                    "codec": video["codec"],
                    "pixel_format": video["pixel_format"],
                },
                "expected": {
                    "duration_seconds": expected_duration,
                    "width": expected_width,
                    "height": expected_height,
                },
            },
        )

    @staticmethod
    def _black_check(events: list[dict[str, float]], duration: float) -> dict[str, Any]:
        total = round(sum(event["duration"] for event in events), 3)
        longest = round(max((event["duration"] for event in events), default=0), 3)
        limit = round(max(1.5, duration * 0.2), 3)
        failed = longest > limit or total > duration * 0.35
        return _check(
            check_id="black_frames",
            label="异常黑场",
            failed=failed,
            severity="major",
            evidence={
                "events": events[:20],
                "event_count": len(events),
                "total_seconds": total,
                "longest_seconds": longest,
                "longest_allowed_seconds": limit,
            },
        )

    @staticmethod
    def _freeze_check(events: list[dict[str, float]], duration: float) -> dict[str, Any]:
        total = round(sum(event["duration"] for event in events), 3)
        longest = round(max((event["duration"] for event in events), default=0), 3)
        limit = round(max(2.0, duration * 0.35), 3)
        failed = longest > limit or total > duration * 0.5
        return _check(
            check_id="frozen_frames",
            label="异常冻结",
            failed=failed,
            severity="major",
            evidence={
                "events": events[:20],
                "event_count": len(events),
                "total_seconds": total,
                "longest_seconds": longest,
                "longest_allowed_seconds": limit,
            },
        )

    @staticmethod
    def _audio_check(
        probe: dict[str, Any],
        *,
        loudness: dict[str, float | None],
        audio_expected: bool,
    ) -> dict[str, Any]:
        audio = probe["audio"]
        if not audio_expected:
            return {
                "id": "audio_loudness",
                "label": "声音响度",
                "status": "not_applicable",
                "severity": "observation",
                "evidence": {
                    "reason": "approved Video IR does not require voice or music",
                    "stream_present": audio["present"],
                },
            }
        integrated = loudness.get("integrated_lufs")
        true_peak = loudness.get("true_peak_dbfs")
        failures = []
        if not audio["present"]:
            failures.append("missing expected audio stream")
        if integrated is None:
            failures.append("integrated loudness is unavailable")
        elif integrated < -24 or integrated > -8:
            failures.append("integrated loudness is outside -24 to -8 LUFS")
        if true_peak is not None and true_peak > -0.5:
            failures.append("true peak exceeds -0.5 dBFS")
        return _check(
            check_id="audio_loudness",
            label="声音响度",
            failed=bool(failures),
            severity="critical" if not audio["present"] else "major",
            evidence={
                "failures": failures,
                "integrated_lufs": integrated,
                "true_peak_dbfs": true_peak,
                "accepted_integrated_lufs": {"minimum": -24, "maximum": -8},
                "maximum_true_peak_dbfs": -0.5,
                "codec": audio["codec"],
                "sample_rate": audio["sample_rate"],
                "channels": audio["channels"],
            },
        )


def _check(
    *,
    check_id: str,
    label: str,
    failed: bool,
    severity: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": check_id,
        "label": label,
        "status": "fail" if failed else "pass",
        "severity": severity if failed else "observation",
        "evidence": evidence,
    }


def _float_or_none(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _black_events(output: str) -> list[dict[str, float]]:
    pattern = re.compile(
        r"black_start:(?P<start>-?[\d.]+)\s+black_end:(?P<end>-?[\d.]+)"
        r"\s+black_duration:(?P<duration>[\d.]+)"
    )
    return [
        {
            "start": round(float(match.group("start")), 3),
            "end": round(float(match.group("end")), 3),
            "duration": round(float(match.group("duration")), 3),
        }
        for match in pattern.finditer(output)
    ]


def _freeze_events(output: str) -> list[dict[str, float]]:
    starts: list[float] = []
    events: list[dict[str, float]] = []
    for line in output.splitlines():
        start = re.search(r"freeze_start:\s*(-?[\d.]+)", line)
        if start:
            starts.append(float(start.group(1)))
        end = re.search(
            r"freeze_end:\s*(-?[\d.]+)\s*\|\s*freeze_duration:\s*([\d.]+)",
            line,
        )
        if end:
            finish = float(end.group(1))
            duration = float(end.group(2))
            beginning = starts.pop(0) if starts else finish - duration
            events.append({
                "start": round(beginning, 3),
                "end": round(finish, 3),
                "duration": round(duration, 3),
            })
    return events


def _loudness_metrics(output: str) -> dict[str, float | None]:
    blocks = re.findall(r"\{\s*\"input_i\".*?\}", output, flags=re.DOTALL)
    if not blocks:
        return {"integrated_lufs": None, "true_peak_dbfs": None}
    try:
        payload = json.loads(blocks[-1])
    except json.JSONDecodeError:
        return {"integrated_lufs": None, "true_peak_dbfs": None}
    return {
        "integrated_lufs": _float_or_none(payload.get("input_i")),
        "true_peak_dbfs": _float_or_none(payload.get("input_tp")),
    }
