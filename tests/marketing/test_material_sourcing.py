import json
from pathlib import Path

import pytest

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import MaterialSourcingRepository, MediaAssetRepository
from agent.marketing.providers import (
    clear_material_providers,
    register_material_provider,
)
from agent.marketing.providers.materials import (
    PexelsMaterialProvider,
    WikimediaCommonsMaterialProvider,
)
from hermes_state import SessionDB


class FakeMaterialProvider:
    name = "stock_test"

    def __init__(self):
        self.download_calls = 0

    def search(self, request):
        return [
            {
                "provider": self.name,
                "provider_asset_id": "video-1",
                "media_type": "video",
                "source_url": "https://stock.test/videos/1",
                "preview_url": "https://stock.test/previews/1.jpg",
                "download_url": "https://stock.test/files/1.mp4",
                "creator": "Creator",
                "creator_url": "https://stock.test/creator",
                "license_name": "Stock Test License",
                "license_url": "https://stock.test/license",
                "provider_home_url": "https://stock.test/",
                "width": 1920,
                "height": 1080,
                "duration": 8,
                "metadata": {"query": request["query"]},
            }
        ]

    def download(self, candidate):
        self.download_calls += 1
        assert candidate["provider_asset_id"] == "video-1"
        return b"video-content", "video-1.mp4", "video/mp4"


@pytest.fixture(autouse=True)
def reset_providers():
    clear_material_providers()
    yield
    clear_material_providers()


def _paths(tmp_path):
    state_path = tmp_path / "state.db"
    SessionDB(db_path=state_path).close()
    return MarketingDataPaths(tmp_path, tmp_path / "config", state_path)


def test_search_ranks_user_assets_before_provider_and_hides_download_url(tmp_path):
    paths = _paths(tmp_path)
    media = MediaAssetRepository(paths)
    local = media.import_bytes(
        user_id="u1",
        account_id="acct-1",
        name="办公室工作空镜",
        media_type="video",
        role="broll",
        source_type="user_upload",
        rights_status="user_confirmed",
        payload=b"local-video",
        filename="office.mp4",
        mime_type="video/mp4",
    )
    provider = FakeMaterialProvider()
    register_material_provider(provider)

    result = MaterialSourcingRepository(paths).search(
        user_id="u1",
        account_id="acct-1",
        query="办公室 工作",
        role="broll",
        orientation="landscape",
        target_duration=5,
    )

    assert result["status"] == "completed"
    assert result["candidates"][0]["provider"] == "user_library"
    assert result["candidates"][0]["provider_asset_id"] == local["id"]
    assert "download_url" not in json.dumps(result, ensure_ascii=False)
    assert result["candidates"][1]["license_url"] == "https://stock.test/license"


def test_search_does_not_treat_unrelated_library_media_as_a_match(tmp_path):
    paths = _paths(tmp_path)
    MediaAssetRepository(paths).import_bytes(
        user_id="u1",
        account_id="acct-1",
        name="股票市场行情",
        media_type="video",
        role="broll",
        source_type="user_upload",
        rights_status="user_confirmed",
        payload=b"local-video",
        filename="market.mp4",
        mime_type="video/mp4",
    )

    result = MaterialSourcingRepository(paths).search(
        user_id="u1",
        account_id="acct-1",
        query="data center server",
        role="broll",
    )

    assert result["status"] == "unavailable"
    assert result["candidates"] == []


def test_material_search_request_ref_is_idempotent(tmp_path):
    paths = _paths(tmp_path)
    provider = FakeMaterialProvider()
    register_material_provider(provider)
    repository = MaterialSourcingRepository(paths)

    first = repository.search(
        user_id="u1",
        account_id="acct-1",
        query="city office",
        role="broll",
        request_ref="video-setup:fingerprint:scene-001",
    )
    repeated = repository.search(
        user_id="u1",
        account_id="acct-1",
        query="a changed query is ignored for the same owner ref",
        role="scene",
        request_ref="video-setup:fingerprint:scene-001",
    )

    assert repeated["id"] == first["id"]
    assert repeated["query"]["query"] == "city office"
    assert len(repeated["candidates"]) == len(first["candidates"])


def test_materialize_requires_review_and_persists_provenance(tmp_path):
    paths = _paths(tmp_path)
    provider = FakeMaterialProvider()
    register_material_provider(provider)
    repo = MaterialSourcingRepository(paths)
    search = repo.search(user_id="u1", account_id="acct-1", query="city", role="scene")
    candidate_id = search["candidates"][0]["id"]

    with pytest.raises(ValueError, match="license review"):
        repo.materialize(
            candidate_id=candidate_id,
            user_id="u1",
            account_id="acct-1",
            rights_reviewed=False,
        )
    result = repo.materialize(
        candidate_id=candidate_id,
        user_id="u1",
        account_id="acct-1",
        rights_reviewed=True,
    )

    assert provider.download_calls == 1
    assert result["asset"]["rights_status"] == "licensed"
    assert result["asset"]["storage_tier"] == "temporary"
    assert result["asset"]["expires_at"]
    assert result["asset"]["metadata"]["source_url"] == "https://stock.test/videos/1"
    assert result["asset"]["receipt"]["rights_reviewed"] is True
    assert (
        MediaAssetRepository(paths).root / result["asset"]["local_path"]
    ).read_bytes() == b"video-content"
    repeated = repo.materialize(
        candidate_id=candidate_id,
        user_id="u1",
        account_id="acct-1",
        rights_reviewed=True,
    )
    assert repeated["asset"]["id"] == result["asset"]["id"]
    assert provider.download_calls == 1


def test_expired_temporary_candidate_is_downloaded_again(tmp_path):
    paths = _paths(tmp_path)
    provider = FakeMaterialProvider()
    register_material_provider(provider)
    repo = MaterialSourcingRepository(paths)
    search = repo.search(user_id="u1", account_id="acct-1", query="city", role="scene")
    candidate_id = search["candidates"][0]["id"]
    first = repo.materialize(
        candidate_id=candidate_id,
        user_id="u1",
        account_id="acct-1",
        rights_reviewed=True,
    )
    with repo.media._transaction() as db:
        db.execute(
            "UPDATE media_asset_library SET expires_at=? WHERE id=?",
            ("2000-01-01T00:00:00+00:00", first["asset"]["id"]),
        )

    second = repo.materialize(
        candidate_id=candidate_id,
        user_id="u1",
        account_id="acct-1",
        rights_reviewed=True,
    )

    assert second["asset"]["id"] != first["asset"]["id"]
    assert second["asset"]["storage_tier"] == "temporary"
    assert provider.download_calls == 2


def test_material_candidate_is_account_scoped(tmp_path):
    paths = _paths(tmp_path)
    register_material_provider(FakeMaterialProvider())
    repo = MaterialSourcingRepository(paths)
    search = repo.search(user_id="u1", account_id="acct-1", query="city", role="scene")
    with pytest.raises(KeyError):
        repo.materialize(
            candidate_id=search["candidates"][0]["id"],
            user_id="u1",
            account_id="acct-2",
            rights_reviewed=True,
        )


def test_same_provider_asset_is_reused_across_searches(tmp_path):
    paths = _paths(tmp_path)
    provider = FakeMaterialProvider()
    register_material_provider(provider)
    repo = MaterialSourcingRepository(paths)
    first_search = repo.search(
        user_id="u1", account_id="acct-1", query="city", role="scene"
    )
    second_search = repo.search(
        user_id="u1", account_id="acct-1", query="city office", role="scene"
    )
    first = repo.materialize(
        candidate_id=first_search["candidates"][0]["id"],
        user_id="u1",
        account_id="acct-1",
        rights_reviewed=True,
    )
    second = repo.materialize(
        candidate_id=second_search["candidates"][0]["id"],
        user_id="u1",
        account_id="acct-1",
        rights_reviewed=True,
    )
    assert second["asset"]["id"] == first["asset"]["id"]
    assert provider.download_calls == 1


def test_pexels_adapter_uses_official_endpoint_and_never_exposes_api_key(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return json.dumps({
                "videos": [
                    {
                        "id": 42,
                        "url": "https://www.pexels.com/video/example-42/",
                        "width": 1920,
                        "height": 1080,
                        "duration": 7,
                        "user": {"name": "A", "url": "https://www.pexels.com/@a"},
                        "video_files": [
                            {
                                "file_type": "video/mp4",
                                "width": 1920,
                                "height": 1080,
                                "quality": "hd",
                                "link": "https://videos.pexels.com/video.mp4",
                            }
                        ],
                        "video_pictures": [
                            {"picture": "https://images.pexels.com/p.jpg"}
                        ],
                    }
                ]
            }).encode()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.headers["Authorization"]
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = PexelsMaterialProvider(api_key="private-key")
    result = provider.search({
        "query": "office",
        "orientation": "landscape",
        "limit": 1,
        "locale": "zh-CN",
    })

    assert captured["url"].startswith("https://api.pexels.com/v1/videos/search?")
    assert captured["authorization"] == "private-key"
    assert "private-key" not in json.dumps(result)
    assert result[0]["license_name"] == "Pexels License"


def test_wikimedia_adapter_finds_open_licensed_video_without_credentials(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return json.dumps({
                "query": {
                    "pages": [
                        {
                            "pageid": 42,
                            "title": "File:Open data center.webm",
                            "imageinfo": [
                                {
                                    "url": "https://upload.wikimedia.org/open-data-center.webm",
                                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:Open_data_center.webm",
                                    "mime": "video/webm",
                                    "width": 1920,
                                    "height": 1080,
                                    "size": 1024,
                                    "sha1": "abc123",
                                    "extmetadata": {
                                        "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                        "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"},
                                        "Artist": {"value": "<b>Open Creator</b>"},
                                        "Credit": {"value": "Credit the creator"},
                                        "UsageTerms": {"value": "Creative Commons Attribution-Share Alike 4.0"},
                                    },
                                }
                            ],
                        }
                    ]
                }
            }).encode()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.headers.get("Authorization")
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = WikimediaCommonsMaterialProvider().search({
        "query": "data center",
        "limit": 3,
        "media_type": "video",
    })

    assert "commons.wikimedia.org/w/api.php?" in captured["url"]
    assert "filetype%3Avideo" in captured["url"]
    assert captured["authorization"] is None
    assert result[0]["provider"] == "wikimedia_commons"
    assert result[0]["creator"] == "Open Creator"
    assert result[0]["license_name"] == "CC BY-SA 4.0"
    assert result[0]["download_url"].startswith("https://upload.wikimedia.org/")


def test_wikimedia_adapter_can_request_open_licensed_images(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return json.dumps({
                "query": {
                    "pages": [{
                        "pageid": 84,
                        "title": "File:Data center.jpg",
                        "imageinfo": [{
                            "url": "https://upload.wikimedia.org/data-center.jpg",
                            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Data_center.jpg",
                            "mime": "image/jpeg",
                            "width": 2400,
                            "height": 1600,
                            "size": 2048,
                            "sha1": "image123",
                            "extmetadata": {
                                "LicenseShortName": {"value": "CC BY 4.0"},
                                "LicenseUrl": {"value": "https://creativecommons.org/licenses/by/4.0/"},
                                "Artist": {"value": "Open Photographer"},
                            },
                        }],
                    }]
                }
            }).encode()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = WikimediaCommonsMaterialProvider().search({
        "query": "data center",
        "limit": 3,
        "media_type": "image",
    })

    assert "filetype%3Abitmap" in captured["url"]
    assert result[0]["media_type"] == "image"
    assert result[0]["license_name"] == "CC BY 4.0"
