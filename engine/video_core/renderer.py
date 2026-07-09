"""确定性渲染器：EDL → mp4 —— ADR v2 决策 4 / 台账 VIDEO-05。

纯函数原则：同一 EDL + 同一批素材文件 = 同一输出（不含编码器时间戳级差异）。
智能全部在剪辑师 Agent 的 EDL 里；本模块只做确定性转换，可写确定性测试。

两条渲染路径共用一套管线：
- render_final(): 正片渲染（视频片段 + 字幕 + 三音轨 + 转场）
- render_animatic(): 样片渲染（分镜静图 + Ken Burns 缩放 + TTS 配音）——
  ADR v2 倒置 B 的 Phase 1 草稿，成本≈0

设计约束（填代码的模型必读）：
- FFmpeg CLI（subprocess），不用 MoviePy；ffmpeg 路径由构造函数注入
  （桌面打包时随包分发，DESK-08 模式），默认 "ffmpeg" 走 PATH
- EDL → ffmpeg filtergraph 的生成必须是独立纯函数（build_*_command），
  测试只测命令生成，不实际跑 ffmpeg（真跑放集成测试）
- 字幕用 drawtext 或烧录 ass（样式表 SUBTITLE_STYLES 参数化）
- 音轨混合：voice 为主，volume_curve 转 ffmpeg volume 表达式实现 BGM ducking
- 禁止 import agent_core / marketing_tools
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from engine.video_core.edl import EDL, ClipEntry, SubtitleEntry, TimelineSlot

# 参数化字幕样式表（剪辑师 Agent 通过 SubtitleEntry.style 引用）
SUBTITLE_STYLES: dict[str, dict] = {
    "default": {"fontsize": 48, "fontcolor": "white", "bordercolor": "black", "borderw": 3, "y_ratio": 0.82},
    "title": {"fontsize": 72, "fontcolor": "white", "bordercolor": "black", "borderw": 4, "y_ratio": 0.40},
    "caption_small": {"fontsize": 36, "fontcolor": "#EEEEEE", "bordercolor": "black", "borderw": 2, "y_ratio": 0.88},
}


@dataclass
class RenderResult:
    output_path: Path
    duration_sec: float
    command: list[str]      # 实际执行的 ffmpeg 命令（审计/复现用）


class RenderError(Exception):
    """ffmpeg 非零退出。message 携带 stderr 尾部 50 行。"""


class Renderer:
    """EDL 渲染器。

    This first implementation intentionally supports the conservative subset
    needed by Marketing OS faceless videos:

    - final: concatenate accepted shot videos from ``project_dir/videos``;
    - animatic: concatenate still storyboard frames from ``project_dir/frames``;
    - subtitles: burn simple drawtext subtitles from the EDL when available;
    - audio: optionally mix a voice track and looping BGM into AAC.

    It remains deterministic and contains no business imports.
    """

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe") -> None:
        self._ffmpeg = ffmpeg_path
        self._ffprobe = ffprobe_path

    # ---- 纯函数：命令生成（可确定性测试） ----

    def build_final_command(
        self,
        edl: EDL,
        project_dir: Path,
        output: Path,
        *,
        voice_path: Path | None = None,
        bgm_path: Path | None = None,
        voice_volume: float = 1.0,
        bgm_volume: float = 0.18,
    ) -> list[str]:
        _validate_edl(edl)
        slots = _slots_by_id(edl)
        clips = sorted(edl.clips, key=lambda clip: slots.get(clip.slot_id, TimelineSlot(id=clip.slot_id, order=999, duration_sec=1)).order)
        if not clips:
            raise ValueError("final render requires at least one clip")

        command = [self._ffmpeg, "-y"]
        for clip in clips:
            command.extend(["-i", str(_shot_video_path(project_dir, clip))])
        if voice_path is not None:
            command.extend(["-i", str(voice_path)])
        if bgm_path is not None:
            command.extend(["-stream_loop", "-1", "-i", str(bgm_path)])

        filter_complex, output_label = _video_filter(
            input_count=len(clips),
            resolution=edl.resolution,
            fps=edl.fps,
            subtitles=edl.subtitles,
            durations=[_clip_duration(clip, slots.get(clip.slot_id)) for clip in clips],
            clips=clips,
        )
        audio_filter, audio_label = _audio_filter(
            video_input_count=len(clips),
            duration_sec=sum(_clip_duration(clip, slots.get(clip.slot_id)) for clip in clips),
            voice_enabled=voice_path is not None,
            bgm_enabled=bgm_path is not None,
            voice_volume=voice_volume,
            bgm_volume=bgm_volume,
        )
        if audio_filter:
            filter_complex = f"{filter_complex};{audio_filter}"
        command.extend([
            "-filter_complex", filter_complex,
            "-map", output_label,
            "-r", str(edl.fps),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
        ])
        if audio_label:
            command.extend([
                "-map", audio_label,
                "-c:a", "aac",
                "-b:a", "128k",
            ])
        else:
            command.append("-an")
        command.append(str(output))
        return command

    def build_animatic_command(self, edl: EDL, project_dir: Path, output: Path) -> list[str]:
        _validate_edl(edl)
        if not edl.slots:
            raise ValueError("animatic render requires at least one timeline slot")

        command = [self._ffmpeg, "-y"]
        for slot in sorted(edl.slots, key=lambda item: item.order):
            command.extend(["-loop", "1", "-t", _duration_arg(slot.duration_sec), "-i", str(_frame_path(project_dir, slot))])

        durations = [slot.duration_sec for slot in sorted(edl.slots, key=lambda item: item.order)]
        filter_complex, output_label = _video_filter(
            input_count=len(edl.slots),
            resolution=edl.resolution,
            fps=edl.fps,
            subtitles=edl.subtitles,
            durations=durations,
            still_inputs=True,
        )
        command.extend([
            "-filter_complex", filter_complex,
            "-map", output_label,
            "-r", str(edl.fps),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-an",
            str(output),
        ])
        return command

    # ---- 执行 ----

    def render_final(
        self,
        edl: EDL,
        project_dir: Path,
        output: Path,
        *,
        voice_path: Path | None = None,
        bgm_path: Path | None = None,
        voice_volume: float = 1.0,
        bgm_volume: float = 0.18,
    ) -> RenderResult:
        command = self.build_final_command(
            edl,
            project_dir,
            output,
            voice_path=voice_path,
            bgm_path=bgm_path,
            voice_volume=voice_volume,
            bgm_volume=bgm_volume,
        )
        _ensure_inputs_exist(command)
        duration = _run_and_probe(command, output, self)
        return RenderResult(output_path=output, duration_sec=duration, command=command)

    def render_animatic(self, edl: EDL, project_dir: Path, output: Path) -> RenderResult:
        command = self.build_animatic_command(edl, project_dir, output)
        _ensure_inputs_exist(command)
        duration = _run_and_probe(command, output, self)
        return RenderResult(output_path=output, duration_sec=duration, command=command)

    def probe_duration(self, path: Path) -> float:
        result = subprocess.run(
            [
                self._ffprobe,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RenderError(_stderr_tail(result.stderr))
        try:
            payload = json.loads(result.stdout or "{}")
            return float(payload["format"]["duration"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RenderError(f"ffprobe duration parse failed: {result.stdout[:500]}") from exc


def _validate_edl(edl: EDL) -> None:
    problems = edl.validate_skeleton()
    if problems:
        raise ValueError("; ".join(problems))


def _slots_by_id(edl: EDL) -> dict[str, TimelineSlot]:
    return {slot.id: slot for slot in edl.slots}


def _parse_resolution(value: str) -> tuple[int, int]:
    try:
        width, height = str(value).lower().split("x", 1)
        parsed = int(width), int(height)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"invalid EDL resolution: {value}") from exc
    if parsed[0] <= 0 or parsed[1] <= 0:
        raise ValueError(f"invalid EDL resolution: {value}")
    return parsed


def _duration_arg(value: float) -> str:
    return f"{float(value):.3f}".rstrip("0").rstrip(".")


def _shot_video_path(project_dir: Path, clip: ClipEntry) -> Path:
    return project_dir / "videos" / f"{clip.shot_id}.mp4"


def _frame_path(project_dir: Path, slot: TimelineSlot) -> Path:
    stem = slot.shot_id or slot.id
    return project_dir / "frames" / f"{stem}.png"


def _clip_duration(clip: ClipEntry, slot: TimelineSlot | None) -> float:
    if clip.source_out_sec > clip.source_in_sec:
        return clip.source_out_sec - clip.source_in_sec
    if slot is not None:
        return slot.duration_sec
    return 1.0


def _video_filter(
    *,
    input_count: int,
    resolution: str,
    fps: int,
    subtitles: list[SubtitleEntry],
    durations: list[float],
    clips: list[ClipEntry] | None = None,
    still_inputs: bool = False,
) -> tuple[str, str]:
    width, height = _parse_resolution(resolution)
    parts: list[str] = []
    labels: list[str] = []
    clips = clips or []

    for index in range(input_count):
        duration = durations[index]
        label = f"v{index}"
        if still_inputs:
            chain = (
                f"[{index}:v]fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
                f"trim=duration={_duration_arg(duration)},setpts=PTS-STARTPTS[{label}]"
            )
        else:
            clip = clips[index]
            trim = f"trim=start={_duration_arg(clip.source_in_sec)}"
            if clip.source_out_sec > clip.source_in_sec:
                trim += f":end={_duration_arg(clip.source_out_sec)}"
            else:
                trim += f":duration={_duration_arg(duration)}"
            chain = (
                f"[{index}:v]{trim},setpts=PTS-STARTPTS,"
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}[{label}]"
            )
        parts.append(chain)
        labels.append(f"[{label}]")

    base_label = "vcat"
    parts.append("".join(labels) + f"concat=n={input_count}:v=1:a=0[{base_label}]")
    current = base_label
    for index, subtitle in enumerate(subtitles):
        next_label = f"sub{index}"
        parts.append(f"[{current}]{_drawtext(subtitle)}[{next_label}]")
        current = next_label
    return ";".join(parts), f"[{current}]"


def _audio_filter(
    *,
    video_input_count: int,
    duration_sec: float,
    voice_enabled: bool,
    bgm_enabled: bool,
    voice_volume: float,
    bgm_volume: float,
) -> tuple[str, str | None]:
    parts: list[str] = []
    labels: list[str] = []
    duration = max(0.1, float(duration_sec))
    next_input = video_input_count
    if voice_enabled:
        parts.append(
            f"[{next_input}:a]volume={_volume_arg(voice_volume)},"
            f"apad,atrim=0:{_duration_arg(duration)},asetpts=PTS-STARTPTS[voicea]"
        )
        labels.append("[voicea]")
        next_input += 1
    if bgm_enabled:
        parts.append(
            f"[{next_input}:a]volume={_volume_arg(bgm_volume)},"
            f"atrim=0:{_duration_arg(duration)},asetpts=PTS-STARTPTS[bgma]"
        )
        labels.append("[bgma]")
    if len(labels) == 1:
        parts.append(f"{labels[0]}anull[aout]")
    elif len(labels) > 1:
        parts.append("".join(labels) + f"amix=inputs={len(labels)}:duration=longest:normalize=0,atrim=0:{_duration_arg(duration)}[aout]")
    return ";".join(parts), "[aout]" if labels else None


def _volume_arg(value: float) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 1.0
    number = min(2.0, max(0.0, number))
    return f"{number:.3f}".rstrip("0").rstrip(".")


def _drawtext(subtitle: SubtitleEntry) -> str:
    style = SUBTITLE_STYLES.get(subtitle.style, SUBTITLE_STYLES["default"])
    y_ratio = float(style.get("y_ratio", 0.82))
    return (
        "drawtext="
        f"text='{_escape_drawtext(subtitle.text)}':"
        f"fontsize={int(style.get('fontsize', 48))}:"
        f"fontcolor={style.get('fontcolor', 'white')}:"
        f"bordercolor={style.get('bordercolor', 'black')}:"
        f"borderw={int(style.get('borderw', 3))}:"
        "x=(w-text_w)/2:"
        f"y=h*{y_ratio}:"
        f"enable='between(t,{_duration_arg(subtitle.start_sec)},{_duration_arg(subtitle.end_sec)})'"
    )


def _escape_drawtext(value: str) -> str:
    text = str(value or "").replace("\n", " ")
    return (
        text.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace("%", "\\%")
    )


def _ensure_inputs_exist(command: list[str]) -> None:
    for index, part in enumerate(command[:-1]):
        if part == "-i":
            path = Path(command[index + 1])
            if not path.exists():
                raise FileNotFoundError(f"render input missing: {path}")


def _run_and_probe(command: list[str], output: Path, renderer: Renderer) -> float:
    output.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RenderError(_stderr_tail(result.stderr))
    if not output.exists() or output.stat().st_size <= 0:
        raise RenderError(f"render output missing or empty: {output}")
    return renderer.probe_duration(output)


def _stderr_tail(stderr: str) -> str:
    lines = str(stderr or "").splitlines()
    return "\n".join(lines[-50:]) or "ffmpeg failed"
