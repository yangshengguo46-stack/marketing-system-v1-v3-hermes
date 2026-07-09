"""RUN-22: Cadence buffer alert tests.

Tests the publish cadence monitoring:
  get_or_create → increment (shot) → decrement (published) → alert levels
"""

import pytest
from engine.agent_core.store import AgentCoreStore


@pytest.fixture
def store(tmp_path):
    return AgentCoreStore(tmp_path / "test_run22.db")


class TestCadenceState:
    def test_create_default(self, store):
        cadence = store.get_or_create_cadence(user_id="user1")
        assert cadence["buffer"] == 0
        assert cadence["target_frequency"] == "daily"
        assert cadence["user_id"] == "user1"

    def test_idempotent_create(self, store):
        c1 = store.get_or_create_cadence(user_id="user1")
        c2 = store.get_or_create_cadence(user_id="user1")
        assert c1["id"] == c2["id"]

    def test_with_account(self, store):
        c = store.get_or_create_cadence(
            user_id="user1", account_id="acc1", platform="douyin",
        )
        assert c["account_id"] == "acc1"
        assert c["platform"] == "douyin"

    def test_different_accounts_separate(self, store):
        c1 = store.get_or_create_cadence(user_id="user1", account_id="acc1")
        c2 = store.get_or_create_cadence(user_id="user1", account_id="acc2")
        assert c1["id"] != c2["id"]


class TestBufferOperations:
    def test_increment(self, store):
        store.get_or_create_cadence(user_id="user1")
        result = store.increment_buffer("user1")
        assert result["buffer"] == 1

    def test_increment_multiple(self, store):
        store.get_or_create_cadence(user_id="user1")
        store.increment_buffer("user1")
        store.increment_buffer("user1")
        store.increment_buffer("user1")
        result = store.increment_buffer("user1")
        assert result["buffer"] == 4

    def test_decrement(self, store):
        store.get_or_create_cadence(user_id="user1")
        store.increment_buffer("user1")
        store.increment_buffer("user1")
        result = store.decrement_buffer("user1")
        assert result["buffer"] == 1
        assert result["last_published_at"] is not None

    def test_decrement_floor_at_zero(self, store):
        store.get_or_create_cadence(user_id="user1")
        result = store.decrement_buffer("user1")
        assert result["buffer"] == 0  # doesn't go negative

    def test_increment_nonexistent_raises(self, store):
        with pytest.raises(KeyError, match="cadence state not found"):
            store.increment_buffer("nonexistent_user")

    def test_decrement_nonexistent_raises(self, store):
        with pytest.raises(KeyError, match="cadence state not found"):
            store.decrement_buffer("nonexistent_user")


class TestAlertLevels:
    def test_green_daily(self, store):
        store.get_or_create_cadence(user_id="user1", target_frequency="daily")
        store.increment_buffer("user1")
        store.increment_buffer("user1")
        store.increment_buffer("user1")
        status = store.get_cadence_status("user1")
        assert status["alert"] == "green"
        assert status["buffer"] == 3

    def test_yellow_daily(self, store):
        store.get_or_create_cadence(user_id="user1", target_frequency="daily")
        store.increment_buffer("user1")
        status = store.get_cadence_status("user1")
        assert status["alert"] == "yellow"

    def test_red_daily(self, store):
        store.get_or_create_cadence(user_id="user1", target_frequency="daily")
        status = store.get_cadence_status("user1")
        assert status["alert"] == "red"
        assert status["buffer"] == 0

    def test_green_weekly(self, store):
        store.get_or_create_cadence(user_id="user1", target_frequency="weekly")
        store.increment_buffer("user1")
        store.increment_buffer("user1")
        status = store.get_cadence_status("user1")
        assert status["alert"] == "green"

    def test_yellow_weekly(self, store):
        store.get_or_create_cadence(user_id="user1", target_frequency="weekly")
        store.increment_buffer("user1")
        status = store.get_cadence_status("user1")
        assert status["alert"] == "yellow"

    def test_red_weekly(self, store):
        store.get_or_create_cadence(user_id="user1", target_frequency="weekly")
        status = store.get_cadence_status("user1")
        assert status["alert"] == "red"

    def test_thresholds_in_status(self, store):
        store.get_or_create_cadence(user_id="user1", target_frequency="daily")
        status = store.get_cadence_status("user1")
        assert "thresholds" in status
        assert "green" in status["thresholds"]
        assert "yellow" in status["thresholds"]
        assert "red" in status["thresholds"]


class TestFullCadenceLifecycle:
    def test_shot_publish_cycle(self, store):
        """Simulate: shoot 3 videos, publish 1, check buffer."""
        store.get_or_create_cadence(user_id="user1", target_frequency="daily")

        # Shoot 3
        store.increment_buffer("user1")
        store.increment_buffer("user1")
        store.increment_buffer("user1")
        assert store.get_cadence_status("user1")["buffer"] == 3
        assert store.get_cadence_status("user1")["alert"] == "green"

        # Publish 1
        store.decrement_buffer("user1")
        assert store.get_cadence_status("user1")["buffer"] == 2
        assert store.get_cadence_status("user1")["alert"] == "yellow"

        # Publish another
        store.decrement_buffer("user1")
        assert store.get_cadence_status("user1")["buffer"] == 1
        assert store.get_cadence_status("user1")["alert"] == "yellow"

        # Publish last
        store.decrement_buffer("user1")
        assert store.get_cadence_status("user1")["buffer"] == 0
        assert store.get_cadence_status("user1")["alert"] == "red"
