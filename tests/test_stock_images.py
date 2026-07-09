import io
import json
from unittest.mock import patch

import pytest

from marketing_tools.stock_images import PexelsProvider, StockImageError


class Response(io.BytesIO):
    headers = {"X-Ratelimit-Remaining": "199", "X-Ratelimit-Reset": "2000000000"}
    def __enter__(self): return self
    def __exit__(self, *args): return None


def test_pexels_search_normalizes_attribution_and_portrait_url():
    payload = {"total_results": 1, "photos": [{
        "id": 7, "width": 3000, "height": 4000,
        "url": "https://www.pexels.com/photo/example-7/",
        "photographer": "Alice", "photographer_url": "https://www.pexels.com/@alice",
        "alt": "Office team", "src": {
            "portrait": "https://images.pexels.com/photos/7/p.jpg",
            "medium": "https://images.pexels.com/photos/7/m.jpg",
        },
    }]}
    with patch("marketing_tools.stock_images.urlopen", return_value=Response(json.dumps(payload).encode())):
        result = PexelsProvider("secret").search("AI 教育", limit=3)
    assert result["attribution"] == "Photos provided by Pexels"
    assert result["rate_limit_remaining"] == 199
    assert result["candidates"][0] == {
        "provider": "pexels", "provider_id": "7",
        "preview_url": "https://images.pexels.com/photos/7/m.jpg",
        "download_url": "https://images.pexels.com/photos/7/p.jpg",
        "source_url": "https://www.pexels.com/photo/example-7/",
        "author": "Alice", "author_url": "https://www.pexels.com/@alice",
        "alt": "Office team", "width": 3000, "height": 4000,
        "license": "Pexels License", "attribution_required_in_search": True,
    }


def test_pexels_requires_key_and_validates_query():
    with pytest.raises(StockImageError, match="not configured"):
        PexelsProvider("").search("office")
    with pytest.raises(ValueError, match="query required"):
        PexelsProvider("x").search("")


def test_pexels_drops_untrusted_download_hosts():
    payload = {"photos": [{
        "id": 1, "url": "https://evil.example/photo/1", "src": {"portrait": "https://evil.example/a.jpg"},
    }]}
    with patch("marketing_tools.stock_images.urlopen", return_value=Response(json.dumps(payload).encode())):
        assert PexelsProvider("secret").search("x")["candidates"] == []
