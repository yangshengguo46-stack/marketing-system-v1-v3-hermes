import pytest

from agent_core.local_tts_provider import (
    REQUIRED_AUX_MODEL_DIRS,
    REQUIRED_AUX_MODEL_FILES,
    REQUIRED_MODEL_FILES,
    build_index_tts2_synth_command,
    index_tts2_status,
)


def test_index_tts2_status_reports_missing_resources(tmp_path):
    source = tmp_path / "index-tts"
    (source / "indextts").mkdir(parents=True)
    (source / "indextts" / "cli_v2.py").write_text("# cli")
    model_dir = source / "checkpoints"
    model_dir.mkdir()
    (model_dir / "config.yaml").write_text("model: test")

    status = index_tts2_status(source, model_dir)

    assert status["provider"] == "index_tts2"
    assert status["source_available"] is False
    assert status["cli_available"] is True
    assert status["ready"] is False
    assert "gpt.pth" in status["missing_files"]


def test_index_tts2_status_ready_when_required_files_exist(tmp_path):
    source = tmp_path / "index-tts"
    (source / "indextts").mkdir(parents=True)
    (source / "indextts" / "cli_v2.py").write_text("# cli")
    (source / "indextts" / "infer_v2.py").write_text("# infer")
    model_dir = source / "checkpoints"
    for item in (*REQUIRED_MODEL_FILES, *REQUIRED_AUX_MODEL_FILES):
        path = model_dir / item
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    for item in REQUIRED_AUX_MODEL_DIRS:
        (model_dir / item).mkdir(parents=True, exist_ok=True)

    status = index_tts2_status(source, model_dir)

    assert status["source_available"] is True
    assert status["missing_files"] == []
    assert status["ready"] is True


def test_build_index_tts2_synth_command_is_auditable(tmp_path):
    command = build_index_tts2_synth_command(
        text="  你好，   IndexTTS2。 ",
        voice_path=tmp_path / "voice.wav",
        output_path=tmp_path / "out.wav",
        model_dir=tmp_path / "models",
        emotion_text="warm and calm",
        emotion_weight=0.6,
        device="cpu",
    )

    joined = " ".join(command)
    assert command[:3] == ["uv", "run", "indextts2"]
    assert "--model-dir" in command
    assert "你好， IndexTTS2。" in command
    assert "--voice" in command
    assert "--emotion-text warm and calm" in joined
    assert "--emotion-weight 0.6" in joined
    assert "--device cpu" in joined


def test_build_index_tts2_synth_command_requires_text(tmp_path):
    with pytest.raises(ValueError, match="text is required"):
        build_index_tts2_synth_command(
            text=" ",
            voice_path=tmp_path / "voice.wav",
            output_path=tmp_path / "out.wav",
        )
