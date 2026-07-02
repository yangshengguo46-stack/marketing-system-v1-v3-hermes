"""DATA-12: Rate limiter tests."""

import time
from marketing_tools.rate_limiter import RateLimiter


def test_allow_one():
    rl = RateLimiter("douyin")
    ok, _ = rl.allow()
    assert ok is True


def test_allow_multiple_with_pacing():
    rl = RateLimiter("douyin")
    for i in range(3):
        ok, _ = rl.allow()
        assert ok is True, f"call {i}"
        time.sleep(1.1)


def test_block_second_limit():
    rl = RateLimiter("douyin")  # max 1/sec
    rl.allow()
    ok, wait = rl.allow()
    assert ok is False or wait > 0


def test_remaining():
    rl = RateLimiter("douyin")
    before = rl.remaining()["per_day"]
    rl.allow()
    after = rl.remaining()["per_day"]
    assert after == before - 1


def test_default_limits():
    rl = RateLimiter("unknown")
    assert rl.limits["max_per_second"] == 1
