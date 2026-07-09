"""Local TTS provider boundary for IndexTTS2.

The large upstream checkout and model weights live under ``runtime/index-tts``
and are intentionally ignored by git.  Product code talks to this module rather
than importing IndexTTS2 directly, so the desktop app can keep a clean boundary:

- status checks are cheap and do not load model weights;
- synthesis command construction is deterministic and auditable;
- actual audio generation remains an explicit effect step.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_DIR = PROJECT_ROOT / "runtime" / "index-tts"
DEFAULT_MODEL_DIR = DEFAULT_SOURCE_DIR / "checkpoints"

REQUIRED_MODEL_FILES = (
    "config.yaml",
    "bpe.model",
    "gpt.pth",
    "s2mel.pth",
    "wav2vec2bert_stats.pt",
    "feat1.pt",
    "feat2.pt",
    # Official CLI checks the qwen directory, but the actual payload must be
    # present too; keeping this explicit prevents a half-downloaded directory
    # from being reported as usable.
    "qwen0.6bemo4-merge/model.safetensors",
)
REQUIRED_MODEL_DIRS = (
    "qwen0.6bemo4-merge",
)
REQUIRED_AUX_MODEL_FILES = (
    "hf_cache/semantic_codec_model.safetensors",
    "hf_cache/campplus_cn_common.bin",
    "hf_cache/bigvgan/config.json",
    "hf_cache/bigvgan/bigvgan_generator.pt",
)
REQUIRED_AUX_MODEL_DIRS = (
    "hf_cache/w2v-bert-2.0",
)


def index_tts2_status(
    source_dir: str | Path = DEFAULT_SOURCE_DIR,
    model_dir: str | Path = DEFAULT_MODEL_DIR,
) -> dict[str, Any]:
    source = Path(source_dir)
    model = Path(model_dir)
    missing_files = [item for item in REQUIRED_MODEL_FILES if not (model / item).is_file()]
    missing_dirs = [item for item in REQUIRED_MODEL_DIRS if not (model / item).is_dir()]
    missing_aux_files = [item for item in REQUIRED_AUX_MODEL_FILES if not (model / item).is_file()]
    missing_aux_dirs = [item for item in REQUIRED_AUX_MODEL_DIRS if not (model / item).is_dir()]
    missing = missing_files + missing_dirs + missing_aux_files + missing_aux_dirs
    return {
        "provider": "index_tts2",
        "source_dir": str(source),
        "model_dir": str(model),
        "source_available": (source / "indextts" / "infer_v2.py").exists(),
        "cli_available": (source / "indextts" / "cli_v2.py").exists(),
        "model_dir_exists": model.exists(),
        "required_files": list(REQUIRED_MODEL_FILES),
        "required_dirs": list(REQUIRED_MODEL_DIRS),
        "required_aux_files": list(REQUIRED_AUX_MODEL_FILES),
        "required_aux_dirs": list(REQUIRED_AUX_MODEL_DIRS),
        "missing_files": missing,
        "ready": (source / "indextts" / "cli_v2.py").exists() and not missing,
        "license_file": str(source / "LICENSE") if (source / "LICENSE").exists() else "",
        "official_source": _read_source_url(source),
        "run_hint": (
            f"cd {source} && uv run indextts2 check --model-dir {model}"
            if source.exists() else "run scripts/bootstrap-index-tts2.sh first"
        ),
    }


def build_index_tts2_synth_command(
    *,
    text: str,
    voice_path: str | Path,
    output_path: str | Path,
    model_dir: str | Path = DEFAULT_MODEL_DIR,
    source_dir: str | Path = DEFAULT_SOURCE_DIR,
    emotion_text: str = "",
    emotion_audio_path: str | Path | None = None,
    emotion_weight: float = 1.0,
    device: str = "",
    force: bool = True,
) -> list[str]:
    """Build a deterministic IndexTTS2 CLI command without executing it."""

    clean_text = " ".join(str(text or "").split())
    if not clean_text:
        raise ValueError("text is required")
    voice = Path(voice_path)
    if not str(voice):
        raise ValueError("voice_path is required")
    output = Path(output_path)
    command = [
        "uv", "run", "indextts2", "synth",
        "--model-dir", str(Path(model_dir)),
        "--text", clean_text,
        "--voice", str(voice),
        "--output", str(output),
    ]
    if force:
        command.append("--force")
    if device:
        command.extend(["--device", str(device)])
    if emotion_audio_path:
        command.extend(["--emotion-audio", str(Path(emotion_audio_path))])
    elif emotion_text:
        command.extend(["--emotion-text", str(emotion_text)])
    if emotion_audio_path or emotion_text:
        command.extend(["--emotion-weight", _float_text(emotion_weight)])
    return command


def _float_text(value: float) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 1.0
    return f"{max(0.0, min(2.0, number)):.3f}".rstrip("0").rstrip(".")


def _read_source_url(source: Path) -> str:
    marker = source / ".source-url"
    if not marker.exists():
        return "https://github.com/index-tts/index-tts"
    return marker.read_text(encoding="utf-8").strip()
