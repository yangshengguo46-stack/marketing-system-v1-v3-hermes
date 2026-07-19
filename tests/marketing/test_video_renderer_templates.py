from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_advanced_renderers_do_not_leak_internal_direction_or_fake_signals():
    remotion = (ROOT / "video-renderers/remotion/scene.tsx").read_text()
    hyperframes = (ROOT / "video-renderers/render-hyperframes.mjs").read_text()

    assert "props.purpose" not in remotion
    assert "[37, 68, 92]" not in remotion
    assert "SIGNAL" not in remotion
    assert "spec.purpose" not in hyperframes
    assert "DESIGNED MOTION / LIVE" not in hyperframes


def test_advanced_renderers_support_visual_director_presentations():
    remotion = (ROOT / "video-renderers/remotion/scene.tsx").read_text()
    hyperframes = (ROOT / "video-renderers/render-hyperframes.mjs").read_text()

    assert "inset_card" in remotion
    assert "subjectAnchor" in remotion
    assert "inset_card" in hyperframes
    assert "subjectAnchor" in hyperframes
