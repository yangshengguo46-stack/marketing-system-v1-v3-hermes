import importlib.util
from pathlib import Path


def test_channel_bridge_emit_bypasses_print_monkeypatch(monkeypatch, capsys):
    """Weixin QR login monkey-patches builtins.print; bridge events must survive."""
    bridge_path = Path(__file__).resolve().parents[1] / "electron" / "channel_bridge.py"
    spec = importlib.util.spec_from_file_location("channel_bridge_under_test", bridge_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    monkeypatch.setattr("builtins.print", lambda *_args, **_kwargs: None)
    module.emit("qr", platform="weixin", qr_url="https://example.com/qr")

    captured = capsys.readouterr().out
    assert '"event": "qr"' in captured
    assert '"platform": "weixin"' in captured
