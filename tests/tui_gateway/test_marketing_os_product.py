from tui_gateway import server


def test_product_status_comes_from_native_gateway():
    response = server.handle_request({
        "jsonrpc": "2.0",
        "id": "marketing-os-status",
        "method": "marketing.product.status",
        "params": {},
    })

    assert response["result"] == {
        "product_id": "marketing-os",
        "product_name": "Marketing OS",
        "runtime": "hermes-product-fork",
        "agent_owner": "native",
        "desktop_owner": "apps/desktop",
        "surfaces": ["desktop", "messaging", "cron"],
        "ecosystem": {
            "mcp": {
                "compatibility": "hermes-native",
                "install_and_discovery": "preserved",
                "update_channel": "mcp-server-or-product-release",
            },
            "skills": {
                "compatibility": "hermes-native",
                "hub_install_update": "preserved",
                "user_skills": "preserved",
            },
            "plugins": {
                "compatibility": "hermes-native",
                "install_update": "preserved",
            },
            "core": {
                "upstream": "NousResearch/hermes-agent",
                "update_channel": "marketing-os-product-release",
                "raw_upstream_apply": "blocked-in-product-runtime",
            },
        },
    }
