"""RUN-06: Error classification and retry strategies."""

import pytest
from agent_core.models import ErrorCategory, classify_error


class TestClassifyError:
    def test_rate_limit(self):
        for msg in ["429 Too Many Requests", "rate limit exceeded",
                     "too many requests, retry after 60s", "quota exceeded"]:
            assert classify_error(msg) == ErrorCategory.RATE_LIMIT, msg

    def test_auth(self):
        for msg in ["401 Unauthorized", "403 Forbidden",
                     "permission denied at platform", "authentication failed"]:
            assert classify_error(msg) == ErrorCategory.AUTH, msg

    def test_network(self):
        for msg in ["connection refused", "connection reset by peer",
                     "ECONNREFUSED", "dns lookup failed", "proxy error",
                     "tunnel connection failed"]:
            assert classify_error(msg) == ErrorCategory.NETWORK, msg

    def test_retryable(self):
        for msg in ["503 Service Unavailable", "502 Bad Gateway",
                     "504 Gateway Timeout", "timeout waiting for response",
                     "request timed out", "temporarily unavailable"]:
            assert classify_error(msg) == ErrorCategory.RETRYABLE, msg

    def test_approval(self):
        for msg in ["pending_approval", "approval expired",
                     "approval rejected by user", "user rejected"]:
            assert classify_error(msg) == ErrorCategory.APPROVAL, msg

    def test_schema_change(self):
        for msg in ["missing required field 'url'",
                     "unknown parameter 'xyz'",
                     "unexpected tool schema from MCP"]:
            assert classify_error(msg) == ErrorCategory.SCHEMA_CHANGE, msg

    def test_permanent(self):
        for msg in ["not found", "400 Bad Request",
                     "invalid argument: x must be int"]:
            assert classify_error(msg) == ErrorCategory.PERMANENT, msg

    def test_unknown(self):
        for msg in ["something completely unexpected happened",
                     "this error has no matching pattern", ""]:
            assert classify_error(msg) == ErrorCategory.UNKNOWN, msg

    def test_case_insensitive(self):
        assert classify_error("Rate Limit Exceeded") == ErrorCategory.RATE_LIMIT
        assert classify_error("Connection Refused") == ErrorCategory.NETWORK


class TestRetryProperties:
    def test_retryable_categories(self):
        assert ErrorCategory.RETRYABLE.retryable is True
        assert ErrorCategory.RATE_LIMIT.retryable is True
        assert ErrorCategory.NETWORK.retryable is True

    def test_non_retryable_categories(self):
        assert ErrorCategory.PERMANENT.retryable is False
        assert ErrorCategory.AUTH.retryable is False
        assert ErrorCategory.APPROVAL.retryable is False
        assert ErrorCategory.SCHEMA_CHANGE.retryable is False
        assert ErrorCategory.UNKNOWN.retryable is False

    def test_retry_delays(self):
        assert ErrorCategory.RETRYABLE.default_retry_delay == 1.0
        assert ErrorCategory.RATE_LIMIT.default_retry_delay == 30.0
        assert ErrorCategory.NETWORK.default_retry_delay == 2.0
        assert ErrorCategory.PERMANENT.default_retry_delay == 0.0


class TestRetryDecision:
    def test_retry_503(self):
        from agent_core.models import decide_retry
        d = decide_retry("503 Service Unavailable")
        assert d.should_retry is True
        assert d.delay_seconds == 1.0

    def test_retry_rate_limit_with_backoff(self):
        from agent_core.models import decide_retry
        d = decide_retry("429 rate limit", attempt=2)
        assert d.should_retry is True
        assert d.delay_seconds == 60.0  # 30 * 2^(2-1)

    def test_no_retry_permanent(self):
        from agent_core.models import decide_retry
        d = decide_retry("400 Bad Request")
        assert d.should_retry is False

    def test_no_retry_auth(self):
        from agent_core.models import decide_retry
        d = decide_retry("401 Unauthorized")
        assert d.should_retry is False

    def test_no_retry_approval(self):
        from agent_core.models import decide_retry
        d = decide_retry("approval rejected")
        assert d.should_retry is False

    def test_side_effect_blocks_retry(self):
        from agent_core.models import decide_retry
        d = decide_retry("503 timeout", has_side_effects=True)
        assert d.should_retry is False
        assert "side-effect" in d.reason

    def test_side_effect_allows_429(self):
        from agent_core.models import decide_retry
        d = decide_retry("429 rate limited", has_side_effects=True)
        assert d.should_retry is True
        assert d.delay_seconds == 30.0

    def test_max_attempts_exhausted(self):
        from agent_core.models import decide_retry
        d = decide_retry("503", attempt=3, max_attempts=3)
        assert d.should_retry is False
        assert "exhausted" in d.reason

    def test_backoff_capped_at_120(self):
        from agent_core.models import decide_retry
        d = decide_retry("503", attempt=10, max_attempts=20)
        assert d.should_retry is True
        assert d.delay_seconds <= 120.0

    def test_retry_decision_to_dict(self):
        from agent_core.models import decide_retry
        d = decide_retry("503", attempt=1)
        j = d.to_dict()
        assert j["should_retry"] is True
        assert j["delay_seconds"] > 0
