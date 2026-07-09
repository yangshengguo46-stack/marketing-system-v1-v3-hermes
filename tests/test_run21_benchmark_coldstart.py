"""RUN-21: Benchmark account cold-start tests.

Tests the benchmark import flow:
  add account → add samples → derive rubric anchor
"""

import pytest
from engine.agent_core.store import AgentCoreStore
from engine.agent_core.content_rubric import OPINION_VIDEO_RUBRIC


@pytest.fixture
def store(tmp_path):
    return AgentCoreStore(tmp_path / "test_run21.db")


SAMPLE_SCORES_1 = {d.key: 8 for d in OPINION_VIDEO_RUBRIC}
SAMPLE_SCORES_2 = {d.key: 6 for d in OPINION_VIDEO_RUBRIC}
SAMPLE_SCORES_3 = {d.key: 7 for d in OPINION_VIDEO_RUBRIC}


class TestBenchmarkAccount:
    def test_add_and_get(self, store):
        account = store.add_benchmark_account(
            user_id="user1",
            platform="douyin",
            account_handle="@creator1",
            account_name="Creator One",
            metadata={"followers": 100000},
        )
        assert account["platform"] == "douyin"
        assert account["account_handle"] == "@creator1"
        assert account["account_name"] == "Creator One"
        assert account["metadata"]["followers"] == 100000

        fetched = store.get_benchmark_account(account["id"])
        assert fetched["account_handle"] == "@creator1"

    def test_get_nonexistent_raises(self, store):
        with pytest.raises(KeyError, match="benchmark account not found"):
            store.get_benchmark_account("bench_nonexistent")

    def test_list_by_user(self, store):
        store.add_benchmark_account(user_id="user1", platform="douyin", account_handle="@c1")
        store.add_benchmark_account(user_id="user1", platform="douyin", account_handle="@c2")
        store.add_benchmark_account(user_id="user2", platform="douyin", account_handle="@c3")
        user1_accounts = store.list_benchmark_accounts("user1")
        user2_accounts = store.list_benchmark_accounts("user2")
        assert len(user1_accounts) == 2
        assert len(user2_accounts) == 1


class TestBenchmarkSamples:
    def test_add_and_get(self, store):
        account = store.add_benchmark_account(
            user_id="user1", platform="douyin", account_handle="@c1",
        )
        sample = store.add_benchmark_sample(
            benchmark_account_id=account["id"],
            video_id="v001",
            title="Why AI matters",
            transcript="Today let's talk about...",
            metrics={"views": 50000, "likes": 1200},
            scores=SAMPLE_SCORES_1,
        )
        assert sample["video_id"] == "v001"
        assert sample["title"] == "Why AI matters"
        assert sample["metrics"]["views"] == 50000
        assert sample["scores"]["hook"] == 8

    def test_get_nonexistent_raises(self, store):
        with pytest.raises(KeyError, match="benchmark sample not found"):
            store.get_benchmark_sample("sample_nonexistent")

    def test_list_by_account(self, store):
        account = store.add_benchmark_account(
            user_id="user1", platform="douyin", account_handle="@c1",
        )
        store.add_benchmark_sample(benchmark_account_id=account["id"], title="v1")
        store.add_benchmark_sample(benchmark_account_id=account["id"], title="v2")
        store.add_benchmark_sample(benchmark_account_id=account["id"], title="v3")
        samples = store.list_benchmark_samples(account["id"])
        assert len(samples) == 3

    def test_sample_without_scores(self, store):
        account = store.add_benchmark_account(
            user_id="user1", platform="douyin", account_handle="@c1",
        )
        sample = store.add_benchmark_sample(
            benchmark_account_id=account["id"],
            title="no scores",
            metrics={"views": 1000},
        )
        assert sample["scores"] is None
        assert sample["metrics"]["views"] == 1000


class TestDeriveRubricAnchor:
    def test_derive_with_samples(self, store):
        account = store.add_benchmark_account(
            user_id="user1", platform="douyin", account_handle="@c1",
        )
        store.add_benchmark_sample(benchmark_account_id=account["id"], scores=SAMPLE_SCORES_1)
        store.add_benchmark_sample(benchmark_account_id=account["id"], scores=SAMPLE_SCORES_2)
        store.add_benchmark_sample(benchmark_account_id=account["id"], scores=SAMPLE_SCORES_3)

        anchor = store.derive_rubric_anchor(account["id"])
        assert anchor["sample_count"] == 3
        # Average of 8, 6, 7 = 7.0
        for key in anchor["anchor_scores"]:
            assert anchor["anchor_scores"][key] == 7.0

    def test_derive_with_no_samples(self, store):
        account = store.add_benchmark_account(
            user_id="user1", platform="douyin", account_handle="@c1",
        )
        anchor = store.derive_rubric_anchor(account["id"])
        assert anchor["sample_count"] == 0
        # Default to 5.0 when no data
        for key in anchor["anchor_scores"]:
            assert anchor["anchor_scores"][key] == 5.0

    def test_derive_with_partial_scores(self, store):
        account = store.add_benchmark_account(
            user_id="user1", platform="douyin", account_handle="@c1",
        )
        # Only one sample with scores, others without
        store.add_benchmark_sample(benchmark_account_id=account["id"], scores=SAMPLE_SCORES_1)
        store.add_benchmark_sample(benchmark_account_id=account["id"], title="no scores")
        anchor = store.derive_rubric_anchor(account["id"])
        assert anchor["sample_count"] == 2
        # Only 1 sample with scores → all 8.0
        for key in anchor["anchor_scores"]:
            assert anchor["anchor_scores"][key] == 8.0

    def test_derive_all_seven_dimensions(self, store):
        account = store.add_benchmark_account(
            user_id="user1", platform="douyin", account_handle="@c1",
        )
        store.add_benchmark_sample(benchmark_account_id=account["id"], scores=SAMPLE_SCORES_1)
        anchor = store.derive_rubric_anchor(account["id"])
        expected_keys = {d.key for d in OPINION_VIDEO_RUBRIC}
        assert set(anchor["anchor_scores"].keys()) == expected_keys
