import io
import json
from unittest.mock import patch

import pytest

from marketing_tools.firecrawl_provider import FirecrawlError, FirecrawlProvider


class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *args): return None


def test_cloud_requires_key_and_self_host_requires_loopback():
    assert not FirecrawlProvider(api_key="").configured
    with pytest.raises(FirecrawlError, match="not configured"):
        FirecrawlProvider(api_key="").search("AI 教育")
    assert FirecrawlProvider(api_url="http://127.0.0.1:3002", api_key="").configured
    with pytest.raises(ValueError, match="loopback"):
        FirecrawlProvider(api_url="http://192.168.1.2:3002")


def test_search_normalizes_cloud_response_and_sends_bearer_key():
    payload = {"success": True, "data": {"web": [{
        "title": "AI education", "url": "https://example.com/article",
        "description": "Summary", "markdown": "# Evidence",
    }]}}
    with patch("marketing_tools.firecrawl_provider.urlopen", return_value=Response(json.dumps(payload).encode())) as call:
        result = FirecrawlProvider(api_key="fc-test-key").search("AI 教育", limit=3)
    request = call.call_args.args[0]
    assert request.headers["Authorization"] == "Bearer fc-test-key"
    assert result["results"][0]["url"] == "https://example.com/article"
    assert result["results"][0]["markdown"] == "# Evidence"


def test_search_rejects_invalid_limit():
    with pytest.raises(ValueError, match="limit"):
        FirecrawlProvider(api_key="x").search("x", limit=0)
