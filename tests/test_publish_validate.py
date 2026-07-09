from marketing_tools.publish_validate import validate_publish_request


def _asset():
    return {
        "id": "asset_" + "1" * 32, "account_id": "acct_a",
        "platform": "douyin", "title": "测试视频", "type": "video",
        "status": "approved", "content": {"duration": 15},
    }


def _attachment():
    return {
        "id": "media_" + "2" * 32, "asset_id": "asset_" + "1" * 32,
        "account_id": "acct_a", "status": "active", "sha256": "a" * 64,
    }


def test_video_publish_requires_managed_attachment():
    result = validate_publish_request(_asset())
    assert result["valid"] is False
    assert "missing active media attachment" in result["errors"]


def test_video_publish_rejects_agent_supplied_raw_path_even_with_attachment():
    asset = _asset()
    asset["content"]["file_path"] = "/Users/example/private.mp4"
    result = validate_publish_request(asset, attachment=_attachment())
    assert result["valid"] is False
    assert any("raw local media paths" in item for item in result["errors"])


def test_video_publish_accepts_scoped_hashed_attachment():
    result = validate_publish_request(_asset(), attachment=_attachment())
    assert result == {"valid": True, "errors": []}


def test_video_publish_rejects_cross_account_attachment():
    attachment = _attachment()
    attachment["account_id"] = "acct_b"
    result = validate_publish_request(_asset(), attachment=attachment)
    assert "media attachment account mismatch" in result["errors"]


def test_image_publish_accepts_ordered_scoped_attachments():
    asset = _asset()
    asset["type"] = "image"
    attachments = [
        {**_attachment(), "mime_type": "image/jpeg", "position": position}
        for position in range(3)
    ]
    assert validate_publish_request(asset, attachments=attachments) == {"valid": True, "errors": []}


def test_image_publish_requires_images_and_rejects_cross_account():
    asset = _asset()
    asset["type"] = "image"
    assert "image posts require 1 to 9 active media attachments" in validate_publish_request(asset)["errors"]
    bad = {**_attachment(), "mime_type": "image/png", "account_id": "acct_b"}
    assert "media attachment account mismatch" in validate_publish_request(asset, attachments=[bad])["errors"]
