import pytest

from agent_core import AgentCoreStore


SHA_A = "a" * 64
SHA_B = "b" * 64


def _video(store, *, user_id="u", account_id="acct_a"):
    return store.create_content_asset(
        user_id=user_id, account_id=account_id, platform="douyin",
        title="待发布视频", type="video",
    )


def _image(store, *, user_id="u", account_id="acct_a"):
    return store.create_content_asset(
        user_id=user_id, account_id=account_id, platform="douyin",
        title="待发布图文", type="image",
    )


def test_register_attachment_is_scoped_and_hides_storage_key_by_default(tmp_path):
    store = AgentCoreStore(tmp_path / "media.db")
    asset = _video(store)
    attachment = store.register_media_attachment(
        user_id="u", account_id="acct_a", asset_id=asset["id"],
        original_name="video.mp4", mime_type="video/mp4", byte_size=1024,
        sha256=SHA_A, storage_key=f"{'1' * 32}/video.mp4",
    )
    assert attachment["storage_key"].endswith("/video.mp4")
    public = store.get_media_attachment(
        attachment["id"], user_id="u", account_id="acct_a",
    )
    assert "storage_key" not in public
    with pytest.raises(KeyError):
        store.get_media_attachment(
            attachment["id"], user_id="u", account_id="acct_b",
        )


def test_reimport_supersedes_old_attachment_without_deleting_history(tmp_path):
    store = AgentCoreStore(tmp_path / "media.db")
    asset = _video(store)
    first = store.register_media_attachment(
        user_id="u", account_id="acct_a", asset_id=asset["id"],
        original_name="v1.mp4", mime_type="video/mp4", byte_size=100,
        sha256=SHA_A, storage_key=f"{'1' * 32}/v1.mp4",
    )
    second = store.register_media_attachment(
        user_id="u", account_id="acct_a", asset_id=asset["id"],
        original_name="v2.mp4", mime_type="video/mp4", byte_size=200,
        sha256=SHA_B, storage_key=f"{'2' * 32}/v2.mp4",
    )
    assert store.get_media_attachment(
        first["id"], user_id="u", account_id="acct_a",
    )["status"] == "superseded"
    assert store.get_active_media_attachment(
        asset_id=asset["id"], user_id="u", account_id="acct_a",
    )["id"] == second["id"]


@pytest.mark.parametrize("field,value,error", [
    ("mime_type", "application/pdf", "unsupported media type"),
    ("sha256", "not-a-hash", "invalid media sha256"),
    ("storage_key", "../secret.mp4", "invalid media storage_key"),
    ("byte_size", 0, "between 1 byte"),
])
def test_attachment_rejects_untrusted_metadata(tmp_path, field, value, error):
    store = AgentCoreStore(tmp_path / f"media-{field}.db")
    asset = _video(store)
    params = {
        "user_id": "u", "account_id": "acct_a", "asset_id": asset["id"],
        "original_name": "video.mp4", "mime_type": "video/mp4", "byte_size": 100,
        "sha256": SHA_A, "storage_key": f"{'1' * 32}/video.mp4",
    }
    params[field] = value
    with pytest.raises(ValueError, match=error):
        store.register_media_attachment(**params)


def test_attachment_rejects_cross_account_asset_and_non_media_asset(tmp_path):
    store = AgentCoreStore(tmp_path / "media-scope.db")
    video = _video(store)
    with pytest.raises(ValueError, match="outside content asset scope"):
        store.register_media_attachment(
            user_id="u", account_id="acct_b", asset_id=video["id"],
            original_name="video.mp4", mime_type="video/mp4", byte_size=100,
            sha256=SHA_A, storage_key=f"{'1' * 32}/video.mp4",
        )
    script = store.create_content_asset(
        user_id="u", account_id="acct_a", platform="douyin",
        title="脚本", type="script",
    )
    with pytest.raises(ValueError, match="video or image"):
        store.register_media_attachment(
            user_id="u", account_id="acct_a", asset_id=script["id"],
            original_name="video.mp4", mime_type="video/mp4", byte_size=100,
            sha256=SHA_A, storage_key=f"{'2' * 32}/video.mp4",
        )


def test_image_asset_keeps_ordered_multi_image_attachments(tmp_path):
    store = AgentCoreStore(tmp_path / "multi-image.db")
    asset = _image(store)
    first = store.register_media_attachment(
        user_id="u", account_id="acct_a", asset_id=asset["id"],
        original_name="one.jpg", mime_type="image/jpeg", byte_size=100,
        sha256=SHA_A, storage_key=f"{'1' * 32}/one.jpg",
    )
    second = store.register_media_attachment(
        user_id="u", account_id="acct_a", asset_id=asset["id"],
        original_name="two.png", mime_type="image/png", byte_size=200,
        sha256=SHA_B, storage_key=f"{'2' * 32}/two.png",
    )
    active = store.list_active_media_attachments(
        asset_id=asset["id"], user_id="u", account_id="acct_a",
    )
    assert [item["id"] for item in active] == [first["id"], second["id"]]
    assert [item["position"] for item in active] == [0, 1]


def test_replacing_one_image_position_preserves_other_images(tmp_path):
    store = AgentCoreStore(tmp_path / "replace-image.db")
    asset = _image(store)
    old = store.register_media_attachment(
        user_id="u", account_id="acct_a", asset_id=asset["id"],
        original_name="old.jpg", mime_type="image/jpeg", byte_size=100,
        sha256=SHA_A, storage_key=f"{'1' * 32}/old.jpg", position=0,
    )
    store.register_media_attachment(
        user_id="u", account_id="acct_a", asset_id=asset["id"],
        original_name="keep.jpg", mime_type="image/jpeg", byte_size=100,
        sha256=SHA_A, storage_key=f"{'2' * 32}/keep.jpg", position=1,
    )
    replacement = store.register_media_attachment(
        user_id="u", account_id="acct_a", asset_id=asset["id"],
        original_name="new.jpg", mime_type="image/jpeg", byte_size=100,
        sha256=SHA_B, storage_key=f"{'3' * 32}/new.jpg", position=0,
    )
    assert store.get_media_attachment(old["id"], user_id="u", account_id="acct_a")["status"] == "superseded"
    active = store.list_active_media_attachments(asset_id=asset["id"], user_id="u", account_id="acct_a")
    assert [(item["position"], item["id"]) for item in active] == [(0, replacement["id"]), (1, active[1]["id"])]


def test_stock_image_provenance_is_preserved_and_validated(tmp_path):
    store = AgentCoreStore(tmp_path / "provenance.db")
    asset = _image(store)
    provenance = {
        "provider": "pexels", "provider_id": "42",
        "source_url": "https://www.pexels.com/photo/example-42/",
        "author": "Alice", "author_url": "https://www.pexels.com/@alice",
        "license": "Pexels License",
    }
    attachment = store.register_media_attachment(
        user_id="u", account_id="acct_a", asset_id=asset["id"],
        original_name="pexels-42.jpg", mime_type="image/jpeg", byte_size=100,
        sha256=SHA_A, storage_key=f"{'4' * 32}/media.jpg", provenance=provenance,
    )
    assert attachment["provenance"] == provenance
    with pytest.raises(ValueError, match="source_url"):
        store.register_media_attachment(
            user_id="u", account_id="acct_a", asset_id=asset["id"],
            original_name="bad.jpg", mime_type="image/jpeg", byte_size=100,
            sha256=SHA_B, storage_key=f"{'5' * 32}/media.jpg",
            provenance={**provenance, "source_url": "https://evil.example/image"},
        )
