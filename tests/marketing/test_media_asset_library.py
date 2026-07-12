import pytest

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains import MediaAssetRepository
from hermes_state import SessionDB


def _repo(tmp_path):
    state_path = tmp_path / "state.db"
    SessionDB(db_path=state_path).close()
    return MediaAssetRepository(
        MarketingDataPaths(tmp_path, tmp_path / "config", state_path)
    )


def test_user_upload_is_hashed_listed_and_physically_deleted(tmp_path):
    repo = _repo(tmp_path)
    asset = repo.import_bytes(
        user_id="u1", account_id=None, name="我的形象", media_type="image",
        role="character", source_type="user_upload", rights_status="user_confirmed",
        payload=b"image-bytes", filename="portrait.png", mime_type="image/png",
    )
    assert asset["sha256"]
    assert (repo.root / asset["local_path"]).read_bytes() == b"image-bytes"
    assert repo.list(user_id="u1", account_id="acct-1")["total"] == 1

    result = repo.delete(asset_id=asset["id"], user_id="u1", confirmed=True)
    assert result["deleted"] is True
    assert not (repo.root / asset["local_path"]).exists()
    assert repo.list(user_id="u1")["total"] == 0


def test_referenced_asset_cannot_be_deleted_until_detached(tmp_path):
    repo = _repo(tmp_path)
    asset = repo.import_bytes(
        user_id="u1", account_id="acct-1", name="办公室", media_type="image",
        role="scene", source_type="ai_generated", rights_status="generated",
        payload=b"scene", filename="scene.jpg", mime_type="image/jpeg",
    )
    repo.add_reference(
        asset_id=asset["id"], user_id="u1", owner_kind="video_project",
        owner_id="project-1", relation="scene_reference",
    )
    blocked = repo.delete(asset_id=asset["id"], user_id="u1", confirmed=True)
    assert blocked["deleted"] is False
    assert blocked["blocked_by"][0]["owner_id"] == "project-1"

    repo.remove_reference(
        asset_id=asset["id"], user_id="u1", owner_kind="video_project",
        owner_id="project-1", relation="scene_reference",
    )
    assert repo.delete(asset_id=asset["id"], user_id="u1", confirmed=True)["deleted"] is True


def test_volcengine_trusted_asset_keeps_provider_uri_without_local_file(tmp_path):
    repo = _repo(tmp_path)
    asset = repo.register_volcengine_trusted_asset(
        user_id="u1", account_id=None, name="已授权演员",
        provider_asset_id="asset://asset-example", media_type="video",
        metadata={"authorization_status": "accepted"},
    )
    assert asset["source_type"] == "volcengine_trusted"
    assert asset["provider"] == "volcengine_ark"
    assert asset["provider_asset_id"] == "asset://asset-example"
    assert asset["rights_status"] == "provider_verified"
    assert asset["local_path"] == ""


def test_trusted_asset_registration_is_idempotent_and_redacts_secrets(tmp_path):
    repo = _repo(tmp_path)
    first = repo.register_volcengine_trusted_asset(
        user_id="u1", account_id=None, name="已授权演员",
        provider_asset_id="asset://asset-example", media_type="video",
        metadata={"api_key": "must-not-persist", "nested": {"token": "secret"}},
    )
    second = repo.register_volcengine_trusted_asset(
        user_id="u1", account_id="acct-2", name="重复注册",
        provider_asset_id="asset://asset-example", media_type="video",
    )
    assert second["id"] == first["id"]
    assert first["metadata"] == {
        "api_key": "[REDACTED]",
        "nested": {"token": "[REDACTED]"},
    }


def test_upload_scope_cannot_escape_library_and_metadata_is_redacted(tmp_path):
    repo = _repo(tmp_path)
    asset = repo.import_bytes(
        user_id="../../escape", account_id=None, name="安全路径", media_type="image",
        role="scene", source_type="user_upload", rights_status="user_confirmed",
        payload=b"image", filename="../../portrait.png", mime_type="image/png",
        metadata={"authorization": "Bearer private", "caption": "kept"},
    )
    target = (repo.root / asset["local_path"]).resolve()
    assert repo.root.resolve() in target.parents
    assert ".." not in asset["local_path"]
    assert "escape" not in asset["local_path"]
    assert asset["metadata"] == {
        "authorization": "[REDACTED]",
        "caption": "kept",
    }


def test_upload_rejects_mime_and_rights_mismatches(tmp_path):
    repo = _repo(tmp_path)
    common = {
        "user_id": "u1", "account_id": None, "name": "素材",
        "role": "scene", "source_type": "user_upload", "payload": b"content",
        "filename": "asset.png",
    }
    with pytest.raises(ValueError, match="mime_type"):
        repo.import_bytes(
            **common, media_type="image", rights_status="user_confirmed",
            mime_type="video/mp4",
        )
    with pytest.raises(ValueError, match="rights status"):
        repo.import_bytes(
            **common, media_type="image", rights_status="licensed",
            mime_type="image/png",
        )


def test_gateway_rejects_oversized_inline_upload_before_decoding(monkeypatch):
    import agent.marketing.domains.media_assets as media_assets
    from tui_gateway import server

    monkeypatch.setattr(media_assets, "MAX_INLINE_UPLOAD_BYTES", 4)
    response = server._methods["marketing.assets.upload"](
        "request-1",
        {
            "rights_confirmed": True,
            "data_url": "data:image/png;base64," + ("A" * 2048),
            "media_type": "image",
        },
    )
    assert response["error"]["code"] == 4130


def test_delete_requires_explicit_confirmation_and_user_scope(tmp_path):
    repo = _repo(tmp_path)
    asset = repo.import_bytes(
        user_id="u1", account_id=None, name="声音", media_type="audio",
        role="voice", source_type="user_upload", rights_status="user_confirmed",
        payload=b"voice", filename="voice.wav", mime_type="audio/wav",
    )
    try:
        repo.delete(asset_id=asset["id"], user_id="u1", confirmed=False)
        assert False, "expected confirmation error"
    except ValueError:
        pass
    try:
        repo.get(asset_id=asset["id"], user_id="u2")
        assert False, "expected scope error"
    except KeyError:
        pass
