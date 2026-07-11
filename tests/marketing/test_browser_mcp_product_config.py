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
