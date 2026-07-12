from __future__ import annotations

from agent.product import bundled_browser_mcp_config


def test_product_browser_mcp_uses_schema_discovery_and_scoped_execution(tmp_path):
    config = bundled_browser_mcp_config(
        {
            "HERMES_NODE_EXECUTABLE": "/usr/local/bin/node",
            "HERMES_HOME": str(tmp_path),
        }
    )
    assert config is not None
    assert config["session_scope"] == "marketing_account"
    assert config["args"][-1] == "--schema-only"
    assert config["scoped_args"][-1].endswith("server.js")
    assert config["env"]["HERMES_BROWSER_PROFILE_ROOT"] == str(tmp_path / "browser-profiles")
    assert config["env"]["HERMES_BROWSER_OUTPUT_ROOT"] == str(tmp_path / "browser-output")
    assert "ELECTRON" not in str(config).upper()


def test_packaged_browser_mcp_reuses_electron_as_node_and_bundled_chromium(tmp_path):
    browsers = tmp_path / "playwright-browsers"
    config = bundled_browser_mcp_config(
        {
            "HERMES_NODE_EXECUTABLE": "/Applications/Marketing OS.app/Marketing OS",
            "HERMES_NODE_IS_ELECTRON": "1",
            "HERMES_BROWSER_EXECUTABLE": str(browsers / "chromium" / "chrome"),
            "HERMES_HOME": str(tmp_path / "hermes"),
            "PLAYWRIGHT_BROWSERS_PATH": str(browsers),
        }
    )
    assert config is not None
    assert config["command"].endswith("Marketing OS")
    assert config["env"]["ELECTRON_RUN_AS_NODE"] == "1"
    assert config["env"]["PLAYWRIGHT_BROWSERS_PATH"] == str(browsers)
    assert config["env"]["HERMES_BROWSER_EXECUTABLE"].endswith("chromium/chrome")
