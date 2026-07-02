"""MEM-05: Time-to-live and decay for memory kinds."""

import pytest
from agent_core import MemoryKind
from agent_core.models import memory_is_expired


class TestMemoryKindTTL:
    def test_user_has_ttl(self):
        assert MemoryKind.USER.default_ttl_days == 90

    def test_account_is_permanent(self):
        assert MemoryKind.ACCOUNT.default_ttl_days is None

    def test_episodic_has_ttl(self):
        assert MemoryKind.EPISODIC.default_ttl_days == 180

    def test_semantic_has_ttl(self):
        assert MemoryKind.SEMANTIC.default_ttl_days == 365

    def test_procedural_is_permanent(self):
        assert MemoryKind.PROCEDURAL.default_ttl_days is None


class TestMemoryIsExpired:
    def test_locked_never_expires(self):
        m = {"kind": "user", "status": "locked", "observed_at": "2020-01-01T00:00:00"}
        assert memory_is_expired(m) is False

    def test_permanent_kind_never_expires(self):
        m = {"kind": "account", "status": "verified", "observed_at": "2020-01-01T00:00:00"}
        assert memory_is_expired(m) is False

    def test_expired_user_memory(self):
        m = {"kind": "user", "status": "verified", "observed_at": "2020-01-01T00:00:00"}
        assert memory_is_expired(m, now="2026-07-02T00:00:00") is True

    def test_recent_user_memory_not_expired(self):
        m = {"kind": "user", "status": "verified", "observed_at": "2026-06-01T00:00:00"}
        assert memory_is_expired(m, now="2026-07-02T00:00:00") is False

    def test_expired_episodic(self):
        m = {"kind": "episodic", "status": "verified", "observed_at": "2020-01-01T00:00:00"}
        assert memory_is_expired(m, now="2026-07-02T00:00:00") is True

    def test_recent_semantic_not_expired(self):
        m = {"kind": "semantic", "status": "verified", "observed_at": "2026-06-01T00:00:00"}
        assert memory_is_expired(m, now="2026-07-02T00:00:00") is False

    def test_unknown_kind_returns_false(self):
        m = {"kind": "nonexistent", "status": "verified", "observed_at": "2020-01-01T00:00:00"}
        assert memory_is_expired(m) is False

    def test_no_observed_at_returns_false(self):
        m = {"kind": "user", "status": "verified"}
        assert memory_is_expired(m) is False

    def test_uses_created_at_fallback(self):
        m = {"kind": "user", "status": "verified", "created_at": "2020-01-01T00:00:00"}
        assert memory_is_expired(m, now="2026-07-02T00:00:00") is True
