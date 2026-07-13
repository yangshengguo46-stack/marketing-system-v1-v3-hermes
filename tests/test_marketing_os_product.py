from pathlib import Path
from types import SimpleNamespace

from agent.prompt_builder import DEFAULT_AGENT_IDENTITY, HERMES_AGENT_HELP_GUIDANCE
from agent.product import (
    PRODUCT_AGENT_IDENTITY,
    PRODUCT_ARCHITECTURE_PRINCIPLES,
    PRODUCT_CORE_UPDATE_MESSAGE,
    PRODUCT_ECOSYSTEM_COMPATIBILITY,
    PRODUCT_NAME,
    PRODUCT_RUNTIME_GUIDANCE,
    is_product_code_tool,
    is_product_runtime,
    normalize_product_delegation_toolsets,
    product_core_update_status,
    validate_product_code_scope,
)
from toolsets import resolve_toolset


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_product_source_is_owned_by_the_main_repository():
    assert (PROJECT_ROOT / "agent" / "marketing").is_dir()
    assert (PROJECT_ROOT / "gateway" / "product_messaging.py").is_file()
    assert (PROJECT_ROOT / "tools" / "marketing_tools.py").is_file()
    assert not (PROJECT_ROOT / "marketing_os").exists()
    assert (PROJECT_ROOT / "hermes_cli" / "main.py").is_file()
    assert (PROJECT_ROOT / "apps" / "desktop" / "package.json").is_file()
    assert not (PROJECT_ROOT / "runtime" / "hermes-agent").exists()
    assert not (PROJECT_ROOT / "runtime" / "hermes-patches").exists()


def test_marketing_os_is_the_native_agent_identity():
    assert PRODUCT_NAME == "Marketing OS"
    assert DEFAULT_AGENT_IDENTITY == PRODUCT_AGENT_IDENTITY
    assert DEFAULT_AGENT_IDENTITY.startswith("You are Marketing OS")
    assert "generic chatbot" in DEFAULT_AGENT_IDENTITY
    assert "real publishing receipts" in DEFAULT_AGENT_IDENTITY


def test_runtime_guidance_keeps_hermes_primary_without_a_second_agent():
    assert HERMES_AGENT_HELP_GUIDANCE.startswith(PRODUCT_RUNTIME_GUIDANCE)
    assert "one native operating system" in HERMES_AGENT_HELP_GUIDANCE
    assert "external plugin" in HERMES_AGENT_HELP_GUIDANCE
    assert "HTTP-routed agent" in HERMES_AGENT_HELP_GUIDANCE
    assert "enhanced Hermes agent" in HERMES_AGENT_HELP_GUIDANCE
    assert "Marketing OS capabilities may both" in HERMES_AGENT_HELP_GUIDANCE
    assert any("never external attachments" in principle for principle in PRODUCT_ARCHITECTURE_PRINCIPLES)
    assert any("not historical directories" in principle for principle in PRODUCT_ARCHITECTURE_PRINCIPLES)
    assert "marketing_plan_content_production" in HERMES_AGENT_HELP_GUIDANCE
    assert "marketing_draft_content_create" in HERMES_AGENT_HELP_GUIDANCE
    assert "never put complete articles" in HERMES_AGENT_HELP_GUIDANCE


def test_hermes_ecosystem_contracts_remain_product_capabilities():
    from hermes_cli.mcp_picker import install_by_name
    from hermes_cli.skills_hub import do_update

    tools = set(resolve_toolset("hermes-cli"))

    assert callable(install_by_name)
    assert callable(do_update)
    assert {"skills_list", "skill_view", "skill_manage"} <= tools
    assert PRODUCT_ECOSYSTEM_COMPATIBILITY["mcp"]["install_and_discovery"] == "preserved"
    assert PRODUCT_ECOSYSTEM_COMPATIBILITY["skills"]["hub_install_update"] == "preserved"
    assert PRODUCT_ECOSYSTEM_COMPATIBILITY["core"]["raw_upstream_apply"] == "blocked-in-product-runtime"


def test_product_runtime_is_explicit_and_not_inferred_from_import(monkeypatch):
    monkeypatch.delenv("HERMES_DESKTOP", raising=False)
    monkeypatch.delenv("HERMES_PRODUCT_ID", raising=False)
    monkeypatch.delenv("MARKETING_OS_USER_DATA", raising=False)
    monkeypatch.delenv("MARKETING_OS_CONFIG_DIR", raising=False)
    monkeypatch.delenv("MARKETING_OS_AGENT_DB", raising=False)
    assert is_product_runtime() is False

    monkeypatch.setenv("MARKETING_OS_USER_DATA", "/tmp/marketing-os")
    assert is_product_runtime() is True

    monkeypatch.delenv("MARKETING_OS_USER_DATA", raising=False)
    monkeypatch.setenv("HERMES_DESKTOP", "1")
    assert is_product_runtime() is True


def test_code_capability_is_product_scoped_instead_of_business_default():
    assert is_product_code_tool("terminal") is True
    assert is_product_code_tool("read_file") is True
    assert is_product_code_tool("marketing_read_account_context") is False
    assert "terminal" in resolve_toolset("marketing_code")
    assert "marketing_read_content_assets" in resolve_toolset("marketing_code")

    safe, error = normalize_product_delegation_toolsets(None)
    assert error is None
    assert "marketing" in safe
    assert "marketing_code" not in safe

    _, error = normalize_product_delegation_toolsets(["terminal", "file"])
    assert "raw Hermes coding toolsets" in str(error)
    assert validate_product_code_scope(None) is not None
    assert (
        validate_product_code_scope(
            {
                "purpose": "code_generated_media",
                "content_asset_id": "asset_123",
            }
        )
        is None
    )


def test_top_level_product_agent_cannot_execute_code_tools(monkeypatch):
    from agent.tool_executor import _product_code_block_message

    monkeypatch.setenv("HERMES_DESKTOP", "1")
    top_level = SimpleNamespace(_delegate_depth=0)
    code_worker = SimpleNamespace(_delegate_depth=1)

    assert "isolated" in _product_code_block_message(top_level, "terminal")
    assert _product_code_block_message(top_level, "marketing_read_accounts") is None
    assert _product_code_block_message(code_worker, "terminal") is None


def test_electron_does_not_choose_marketing_business_storage():
    source = (PROJECT_ROOT / "apps" / "desktop" / "electron" / "main.cjs").read_text()

    assert "process.env.MARKETING_OS_USER_DATA" not in source
    assert "process.env.MARKETING_OS_CONFIG_DIR" not in source
    assert "process.env.MARKETING_OS_AGENT_DB" not in source


def test_raw_core_update_is_blocked_but_ecosystem_updates_stay_available(
    monkeypatch, capsys, tmp_path
):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    monkeypatch.setenv("MARKETING_OS_USER_DATA", str(tmp_path / "marketing-os"))

    import hermes_cli.main as cli_main

    monkeypatch.setattr(
        cli_main,
        "_cmd_update_impl",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("raw upstream apply must not run")
        ),
    )
    cli_main.cmd_update(SimpleNamespace(check=False, gateway=False))
    check = product_core_update_status("test-version")

    assert PRODUCT_CORE_UPDATE_MESSAGE in capsys.readouterr().out
    assert check["install_method"] == "marketing-os-managed-hermes"
    assert check["can_apply"] is False
    assert check["ecosystem"]["skills"]["hub_install_update"] == "preserved"
