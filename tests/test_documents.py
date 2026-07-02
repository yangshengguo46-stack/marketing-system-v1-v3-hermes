"""MEM-10: Document library tests."""

import pytest
from marketing_tools.documents import create_document, can_read, can_modify


def test_create_user_doc():
    d = create_document("AI行业分析", "content...", user_id="u1", tags=["AI", "行业"])
    assert d["scope"] == "user"
    assert d["user_id"] == "u1"
    assert d["tags"] == ["AI", "行业"]

def test_public_doc():
    d = create_document("公开资料", "public", scope="public")
    assert d["scope"] == "public"

def test_user_can_read_own():
    d = create_document("t", "c", user_id="u1")
    assert can_read(d, "u1") is True

def test_other_cannot_read_user():
    d = create_document("t", "c", user_id="u1")
    assert can_read(d, "u2") is False

def test_anyone_can_read_public():
    d = create_document("t", "c", scope="public")
    assert can_read(d, "anyone") is True

def test_only_owner_can_modify():
    d = create_document("t", "c", user_id="u1")
    assert can_modify(d, "u1") is True
    assert can_modify(d, "u2") is False

def test_invalid_scope():
    with pytest.raises(ValueError):
        create_document("t", "c", scope="admin")
