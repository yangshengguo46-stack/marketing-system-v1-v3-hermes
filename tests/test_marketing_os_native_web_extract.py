import json

import hermes_state
import httpx
import pytest
from hermes_state import SessionDB
from marketing_os.data_paths import MarketingDataPaths
from marketing_os.domains import EvidenceRepository
from model_tools import get_tool_definitions, handle_function_call
from tools import web_tools


def _force_native_provider(monkeypatch):
    import agent.web_search_registry as provider_registry

    monkeypatch.setattr(web_tools, "_ensure_web_plugins_loaded", lambda: None)
    monkeypatch.setattr(web_tools, "_get_extract_backend", lambda: "")
    monkeypatch.setattr(provider_registry, "get_provider", lambda _name: None)
    monkeypatch.setattr(provider_registry, "get_active_extract_provider", lambda: None)
    monkeypatch.setattr(web_tools, "check_auxiliary_model", lambda: False)


def _mock_http(monkeypatch, handler):
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def client_factory(**kwargs):
        return original_client(transport=transport, **kwargs)

    monkeypatch.setattr(web_tools.httpx, "AsyncClient", client_factory)


def _bind_product_session(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "accounts.json").write_text(
        json.dumps(
            {
                "accounts": [
                    {
                        "id": "acct-native",
                        "platform": "zhihu",
                        "label": "文章账号",
                        "status": "active",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    paths = MarketingDataPaths(
        user_data=tmp_path,
        config_dir=config_dir,
        agent_db=tmp_path / "agent-runtime" / "agent_core.db",
    )
    monkeypatch.setenv("MARKETING_OS_USER_DATA", str(paths.user_data))
    monkeypatch.setenv("MARKETING_OS_CONFIG_DIR", str(paths.config_dir))
    monkeypatch.setenv("MARKETING_OS_AGENT_DB", str(paths.agent_db))
    state_path = tmp_path / "state.db"
    monkeypatch.setattr(hermes_state, "DEFAULT_DB_PATH", state_path)
    db = SessionDB(db_path=state_path)
    db.create_session(
        "native-session",
        "tui",
        marketing_user_id="default",
        marketing_account_id="acct-native",
    )
    db.close()
    return paths


@pytest.mark.asyncio
async def test_native_extract_reads_public_html_without_api_key(monkeypatch):
    _force_native_provider(monkeypatch)

    async def safe_url(_url):
        return True

    monkeypatch.setattr(web_tools, "async_is_safe_url", safe_url)
    _mock_http(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=(
                "<html><head><title>公开研究</title><script>secretNoise()</script></head>"
                "<body><nav>菜单噪音</nav><main><h1>核心结论</h1>"
                "<p>这是无需第三方 API 即可读取的公开正文。</p></main></body></html>"
            ).encode("utf-8"),
            request=request,
        ),
    )

    payload = json.loads(
        await web_tools.web_extract_tool(
            ["https://example.com/report"], use_llm_processing=False
        )
    )
    record = payload["results"][0]

    assert record["title"] == "公开研究"
    assert "核心结论" in record["content"]
    assert "secretNoise" not in record["content"]
    assert record["content_origin"] == "extracted_source"
    assert len(record["source_content_sha256"]) == 64
    assert record["error"] is None


@pytest.mark.asyncio
async def test_native_extract_rechecks_redirect_for_ssrf(monkeypatch):
    _force_native_provider(monkeypatch)

    async def safe_url(url):
        return not url.startswith("http://127.0.0.1")

    monkeypatch.setattr(web_tools, "async_is_safe_url", safe_url)
    _mock_http(
        monkeypatch,
        lambda request: httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/private"},
            request=request,
        ),
    )

    payload = json.loads(
        await web_tools.web_extract_tool(
            ["https://example.com/redirect"], use_llm_processing=False
        )
    )

    assert "private or internal" in payload["results"][0]["error"]
    assert payload["results"][0]["content"] == ""


def test_native_extract_is_visible_without_search_provider_and_captures_evidence(
    tmp_path, monkeypatch
):
    paths = _bind_product_session(tmp_path, monkeypatch)
    _force_native_provider(monkeypatch)

    async def safe_url(_url):
        return True

    monkeypatch.setattr(web_tools, "async_is_safe_url", safe_url)
    _mock_http(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=(
                "<html><head><title>本地抽取证据</title></head><body>"
                "<article><h1>真实来源</h1><p>这段正文会进入账号级 EvidencePack。</p>"
                "</article></body></html>"
            ).encode("utf-8"),
            request=request,
        ),
    )

    definitions = get_tool_definitions(enabled_toolsets=["web"], quiet_mode=True)
    names = {item["function"]["name"] for item in definitions}
    assert "web_extract" in names

    payload = json.loads(
        handle_function_call(
            "web_extract",
            {"urls": ["https://example.com/evidence"]},
            task_id="native-session",
            session_id="native-session",
            tool_call_id="native-http-call",
            enabled_toolsets=["web", "marketing"],
        )
    )
    evidence_id = payload["marketing_evidence"]["records"][0]["evidence_id"]
    stored = EvidenceRepository(paths).require_verified(
        user_id="default",
        account_id="acct-native",
        evidence_ids=[evidence_id],
    )[0]

    assert stored["tool_call_id"] == "native-http-call"
    assert stored["canonical_url"] == "https://example.com/evidence"
    assert stored["metadata"]["excerpt_origin"] == "extracted_source"
