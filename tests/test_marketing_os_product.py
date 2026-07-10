from agent.prompt_builder import DEFAULT_AGENT_IDENTITY, HERMES_AGENT_HELP_GUIDANCE
from marketing_os.product import (
    PRODUCT_AGENT_IDENTITY,
    PRODUCT_ARCHITECTURE_PRINCIPLES,
    PRODUCT_NAME,
    PRODUCT_RUNTIME_GUIDANCE,
)


def test_marketing_os_is_the_native_agent_identity():
    assert PRODUCT_NAME == "Marketing OS"
    assert DEFAULT_AGENT_IDENTITY == PRODUCT_AGENT_IDENTITY
    assert DEFAULT_AGENT_IDENTITY.startswith("You are Marketing OS")
    assert "generic chatbot" in DEFAULT_AGENT_IDENTITY
    assert "real publishing receipts" in DEFAULT_AGENT_IDENTITY


def test_runtime_guidance_forbids_external_plugin_identity():
    assert HERMES_AGENT_HELP_GUIDANCE.startswith(PRODUCT_RUNTIME_GUIDANCE)
    assert "Never describe Hermes as an external plugin" in HERMES_AGENT_HELP_GUIDANCE
    assert "same Marketing OS agent" in HERMES_AGENT_HELP_GUIDANCE
    assert "earlier Marketing OS modules may both be split" in HERMES_AGENT_HELP_GUIDANCE
    assert any("not historical directories" in principle for principle in PRODUCT_ARCHITECTURE_PRINCIPLES)
