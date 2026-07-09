"""Parameter-level MCP browser policy tests — type, context, URL, sanitize."""

from __future__ import annotations

import math, pytest
from agent_core.mcp_browser_policy import (
    PERMANENTLY_DENIED_TOOLS,
    BrowserActionContext,
    validate_browser_call,
    sanitize_output,
    is_tool_permanently_denied,
    click_capabilities,
)
from agent_core.models import CapabilityLevel


def ctx(**kw):
    d = {"platform": "douyin", "account_id": "acct_000000000001",
         "capability": "marketing_trending_search",
         "user_id": "u1", "approved": True}
    d.update(kw)
    return BrowserActionContext(**d)

def _neg(reason_fragment="", **kw):
    """Shorthand: context that should definitely fail."""
    c = ctx(**kw)
    c = BrowserActionContext(
        platform=c.platform, account_id=c.account_id,
        capability=c.capability, user_id=c.user_id,
        task_id=c.task_id, approved=c.approved,
    )
    return c


# ── permanent deny ───────────────────────────────────────────────────────────

class TestPermanentDeny:
    def test_evaluate(self):
        d = validate_browser_call(ctx(), "browser_evaluate", {})
        assert not d.allowed
        assert d.effective_level == CapabilityLevel.SYSTEM_FORBIDDEN

    def test_cookie(self):
        for t in ["browser_cookie_get", "browser_storage_state"]:
            assert not validate_browser_call(ctx(), t, {}).allowed

    def test_unregistered(self):
        d = validate_browser_call(ctx(), "browser_unknown_tool", {})
        assert not d.allowed


# ── context fail-closed ──────────────────────────────────────────────────────

class TestContextFailClosed:
    def test_empty_platform(self):
        d = validate_browser_call(ctx(platform=""), "browser_close", {})
        assert not d.allowed

    def test_unknown_platform(self):
        d = validate_browser_call(ctx(platform="weibo"), "browser_snapshot", {})
        assert not d.allowed

    def test_no_account(self):
        d = validate_browser_call(ctx(account_id=""), "browser_snapshot", {})
        assert not d.allowed

    def test_no_capability(self):
        d = validate_browser_call(ctx(capability=""), "browser_snapshot", {})
        assert not d.allowed

    def test_unknown_capability(self):
        d = validate_browser_call(ctx(capability="totally_fake"), "browser_snapshot", {})
        assert not d.allowed
        assert "unknown product capability" in d.reason

    def test_no_user_or_task(self):
        c = ctx(user_id="", task_id="")
        d = validate_browser_call(c, "browser_navigate", {"url": "https://www.douyin.com"})
        assert not d.allowed

    def test_not_approved_l2(self):
        c = ctx(approved=False)
        d = validate_browser_call(c, "browser_navigate", {"url": "https://www.douyin.com"})
        assert not d.allowed

    def test_close_no_approval_ok(self):
        c = ctx(approved=False)
        d = validate_browser_call(c, "browser_close", {})
        assert d.allowed


# ── browser_close ────────────────────────────────────────────────────────────

class TestClose:
    def test_ok(self):
        d = validate_browser_call(ctx(), "browser_close", {})
        assert d.allowed
        assert d.effective_level == CapabilityLevel.REVERSIBLE_WRITE
    def test_extra_rejected(self):
        d = validate_browser_call(ctx(), "browser_close", {"x": 1})
        assert not d.allowed


# ── browser_navigate ─────────────────────────────────────────────────────────

class TestNavigate:
    def test_ok(self):
        d = validate_browser_call(ctx(), "browser_navigate",
                                   {"url": "https://www.douyin.com/search"})
        assert d.allowed
        assert d.effective_level == CapabilityLevel.CONTROLLED_RESOURCE

    def test_http(self):
        d = validate_browser_call(ctx(), "browser_navigate", {"url": "http://douyin.com"})
        assert not d.allowed
    def test_file(self):
        d = validate_browser_call(ctx(), "browser_navigate", {"url": "file:///etc"})
        assert not d.allowed
    def test_localhost(self):
        for u in ["https://localhost/", "https://127.0.0.1/", "https://[::1]/"]:
            d = validate_browser_call(ctx(), "browser_navigate", {"url": u})
            assert not d.allowed, u

    def test_private(self):
        for u in ["https://192.168.1.1/", "https://10.0.0.1/"]:
            assert not validate_browser_call(ctx(), "browser_navigate", {"url": u}).allowed

    def test_custom_port(self):
        d = validate_browser_call(ctx(), "browser_navigate",
                                   {"url": "https://www.douyin.com:8443/"})
        assert not d.allowed

    # URL bypass samples
    def test_evil_domain(self):
        for u in ["https://douyin.com.evil.test/",
                   "https://evil-douyin.com/",
                   "https://www.douyin.com./"]:
            d = validate_browser_call(ctx(), "browser_navigate", {"url": u})
            assert not d.allowed, u

    def test_at_masquerade(self):
        d = validate_browser_call(ctx(), "browser_navigate",
                                   {"url": "https://douyin.com@evil.test/"})
        assert not d.allowed

    def test_double_at(self):
        d = validate_browser_call(ctx(), "browser_navigate",
                                   {"url": "https://user@douyin.com@evil.test/"})
        assert not d.allowed

    def test_backslash(self):
        d = validate_browser_call(ctx(), "browser_navigate",
                                   {"url": "https://douyin.com\\\\@evil.test"})
        assert not d.allowed

    def test_percent_encoded_hostname(self):
        d = validate_browser_call(ctx(), "browser_navigate",
                                   {"url": "https://douyin.com%2eevil.test/"})
        assert not d.allowed

    def test_invalid_port(self):
        d = validate_browser_call(ctx(), "browser_navigate",
                                   {"url": "https://www.douyin.com:abc"})
        assert not d.allowed

    def test_broken_ipv6(self):
        d = validate_browser_call(ctx(), "browser_navigate", {"url": "https://[::1"})
        assert not d.allowed

    def test_embedded_newline(self):
        d = validate_browser_call(ctx(), "browser_navigate",
                                   {"url": "https://www.douyin.com/\njavascript:..."})
        assert not d.allowed

    def test_unicode_homoglyph(self):
        d = validate_browser_call(ctx(), "browser_navigate",
                                   {"url": "https://ｗｗｗ.douyin.com/"})
        assert not d.allowed

    def test_username_password(self):
        d = validate_browser_call(ctx(), "browser_navigate",
                                   {"url": "https://user:pass@www.douyin.com/"})
        assert not d.allowed

    def test_subdomain_allowed(self):
        d = validate_browser_call(ctx(), "browser_navigate",
                                   {"url": "https://live.douyin.com/123"})
        assert d.allowed

    def test_url_string_only(self):
        for v in [123, True, None, ["a"], {"x": 1}]:
            d = validate_browser_call(ctx(), "browser_navigate", {"url": v})
            assert not d.allowed, f"type {type(v).__name__} should be rejected"

    def test_url_too_long(self):
        d = validate_browser_call(ctx(), "browser_navigate",
                                   {"url": "https://www.douyin.com/" + "x" * 3000})
        assert not d.allowed

    def test_url_control_chars(self):
        d = validate_browser_call(ctx(), "browser_navigate",
                                   {"url": "https://www.douyin.com/\x00test"})
        assert not d.allowed


# ── browser_snapshot ─────────────────────────────────────────────────────────

class TestSnapshot:
    def test_minimal(self):
        d = validate_browser_call(ctx(), "browser_snapshot", {})
        assert d.allowed

    def test_filename_rejected(self):
        assert not validate_browser_call(ctx(), "browser_snapshot", {"filename": "x"}).allowed

    def test_depth_ok(self):
        d = validate_browser_call(ctx(), "browser_snapshot", {"depth": 5})
        assert d.allowed

    # type strictness
    def test_depth_rejects_bool(self):
        for v in [True, False]:
            d = validate_browser_call(ctx(), "browser_snapshot", {"depth": v})
            assert not d.allowed, v

    def test_depth_rejects_float(self):
        for v in [1.0, 1.5]:
            d = validate_browser_call(ctx(), "browser_snapshot", {"depth": v})
            assert not d.allowed, v

    def test_depth_rejects_string(self):
        d = validate_browser_call(ctx(), "browser_snapshot", {"depth": "1"})
        assert not d.allowed

    def test_depth_nan_inf(self):
        for v in [float("nan"), float("inf")]:
            d = validate_browser_call(ctx(), "browser_snapshot", {"depth": v})
            assert not d.allowed

    def test_depth_range(self):
        for v in [0, 21, -1]:
            d = validate_browser_call(ctx(), "browser_snapshot", {"depth": v})
            assert not d.allowed, v

    def test_boxes_bool_only(self):
        for v in [1, "true", [], None]:
            d = validate_browser_call(ctx(), "browser_snapshot", {"boxes": v})
            assert not d.allowed, v
        assert not validate_browser_call(ctx(), "browser_snapshot", {"boxes": True}).allowed
        assert validate_browser_call(ctx(), "browser_snapshot", {"boxes": False}).allowed


# ── browser_wait_for ─────────────────────────────────────────────────────────

class TestWaitFor:
    def test_time_ok(self):
        d = validate_browser_call(ctx(), "browser_wait_for", {"time": 3})
        assert d.allowed

    def test_time_rejects_bool(self):
        d = validate_browser_call(ctx(), "browser_wait_for", {"time": True})
        assert not d.allowed

    def test_time_rejects_string(self):
        d = validate_browser_call(ctx(), "browser_wait_for", {"time": "3"})
        assert not d.allowed

    def test_time_nan(self):
        d = validate_browser_call(ctx(), "browser_wait_for", {"time": float("nan")})
        assert not d.allowed

    def test_time_range(self):
        for v in [-1, 11, float("inf")]:
            d = validate_browser_call(ctx(), "browser_wait_for", {"time": v})
            assert not d.allowed, v

    def test_text_only_ok(self):
        d = validate_browser_call(ctx(), "browser_wait_for", {"text": "done"})
        assert d.allowed

    def test_text_and_textgone_rejected(self):
        d = validate_browser_call(ctx(), "browser_wait_for",
                                   {"text": "a", "textGone": "b"})
        assert not d.allowed


# ── browser_tabs ─────────────────────────────────────────────────────────────

class TestTabs:
    def test_list(self):
        d = validate_browser_call(ctx(), "browser_tabs", {"action": "list"})
        assert d.allowed
    def test_select(self):
        d = validate_browser_call(ctx(), "browser_tabs", {"action": "select", "index": 0})
        assert d.allowed
    def test_close(self):
        d = validate_browser_call(ctx(), "browser_tabs", {"action": "close", "index": 1})
        assert d.allowed
    def test_new_rejected(self):
        d = validate_browser_call(ctx(), "browser_tabs", {"action": "new"})
        assert not d.allowed
    def test_url_rejected(self):
        d = validate_browser_call(ctx(), "browser_tabs", {"action": "select", "index": 0, "url": "x"})
        assert not d.allowed

    # type strictness
    def test_index_rejects_bool(self):
        d = validate_browser_call(ctx(), "browser_tabs", {"action": "select", "index": True})
        assert not d.allowed
    def test_index_rejects_float(self):
        for v in [1.0, 1.5]:
            d = validate_browser_call(ctx(), "browser_tabs", {"action": "select", "index": v})
            assert not d.allowed, v
    def test_index_rejects_string(self):
        d = validate_browser_call(ctx(), "browser_tabs", {"action": "select", "index": "1"})
        assert not d.allowed


# ── browser_click ────────────────────────────────────────────────────────────

class TestClick:
    def test_capability_not_in_allowlist(self):
        """Arbitrary click remains denied even for a click-capable product action."""
        d = validate_browser_call(ctx(), "browser_click",
                                   {"target": "#btn", "element": "btn"})
        assert not d.allowed
        assert "outside reviewed" in d.reason

    def test_trending_tab_click_is_narrowly_allowed(self):
        c = ctx(capability="marketing_trending_search")
        d = validate_browser_call(c, "browser_click",
                                   {"target": "e369", "element": "热门话题"})
        assert d.allowed

    def test_trending_arbitrary_click_is_denied(self):
        c = ctx(capability="marketing_trending_search")
        for args in [
            {"target": "e369", "element": "发布视频"},
            {"target": "#btn", "element": "热门话题"},
        ]:
            assert not validate_browser_call(c, "browser_click", args).allowed

    def test_publish_prepare_allows_only_publish_video_navigation(self):
        c = ctx(capability="marketing_publish_prepare")
        assert validate_browser_call(
            c, "browser_click", {"target": "e369", "element": "发布视频"},
        ).allowed
        assert validate_browser_call(
            c, "browser_click", {"target": "e370", "element": "发布图文"},
        ).allowed
        for element in ("发布", "确认发布", "上传视频", "选择文件", "添加图片"):
            assert not validate_browser_call(
                c, "browser_click", {"target": "e369", "element": element},
            ).allowed

    def test_doubleclick_rejects_all_types(self):
        for v in [True, 1, "true", []]:
            d = validate_browser_call(ctx(), "browser_click",
                                       {"target": "#b", "element": "b",
                                        "doubleClick": v})
            assert not d.allowed, type(v)

    def test_modifiers_empty_array_rejected(self):
        d = validate_browser_call(ctx(), "browser_click",
                                   {"target": "#b", "element": "b",
                                    "modifiers": []})
        assert not d.allowed

    def test_button_anything_not_left(self):
        for v in ["right", "middle", True, 1, None]:
            d = validate_browser_call(ctx(), "browser_click",
                                       {"target": "#b", "element": "b",
                                        "button": v})
            assert not d.allowed, v


# ── unknown args ─────────────────────────────────────────────────────────────

class TestUnknownArgs:
    def test_navigate_extra(self):
        d = validate_browser_call(ctx(), "browser_navigate",
                                   {"url": "https://www.douyin.com", "x": 1})
        assert not d.allowed

    def test_wait_extra(self):
        d = validate_browser_call(ctx(), "browser_wait_for", {"time": 1, "z": 0})
        assert not d.allowed

    def test_non_string_argument_name(self):
        assert not validate_browser_call(ctx(), "browser_snapshot", {1: "bad"}).allowed

    def test_arguments_must_be_dict(self):
        assert not validate_browser_call(ctx(), "browser_snapshot", [("depth", 1)]).allowed


# ── sanitize output ──────────────────────────────────────────────────────────

class TestSanitize:
    def test_cookie_redacted(self):
        assert sanitize_output({"Cookie": "x"}) == {"Cookie": "[REDACTED]"}

    def test_nested_token(self):
        assert sanitize_output({"a": {"b": {"access_token": "s"}}}) == \
               {"a": {"b": {"access_token": "[REDACTED]"}}}

    def test_jwt_redacted(self):
        r = sanitize_output({"body": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgN"[:80]})
        assert r["body"] == "[REDACTED]"

    def test_list_with_cookie(self):
        r = sanitize_output([{"a": 1}, {"Cookie": "x"}])
        assert r[1]["Cookie"] == "[REDACTED]"

    def test_tuple(self):
        r = sanitize_output(({"Cookie": "x"}, "ok"))
        assert r[0]["Cookie"] == "[REDACTED]"

    def test_deep_truncated(self):
        deep = {}
        cur = deep
        for _ in range(20):
            cur["next"] = {}
            cur = cur["next"]
        cur["Cookie"] = "secret"
        r = sanitize_output(deep)
        assert r == "[TRUNCATED]" or "Cookie" not in str(r)

    def test_cycle_is_bounded(self):
        raw = {}
        raw["self"] = raw
        assert sanitize_output(raw)["self"] == "[CYCLE]"

    def test_total_output_budget(self):
        clean = sanitize_output(["x" * 50_000 for _ in range(20)])
        assert len(str(clean)) < 300_000

    def test_pass_through_normal(self):
        assert sanitize_output({"title": "hello"}) == {"title": "hello"}


# ── effective level consistency ──────────────────────────────────────────────

class TestEffectiveLevel:
    def test_close_is_l1(self):
        d = validate_browser_call(ctx(), "browser_close", {})
        assert d.allowed and d.effective_level == CapabilityLevel.REVERSIBLE_WRITE

    def test_navigate_is_l2(self):
        d = validate_browser_call(ctx(), "browser_navigate",
                                   {"url": "https://www.douyin.com"})
        assert d.allowed and d.effective_level == CapabilityLevel.CONTROLLED_RESOURCE

    def test_deny_is_l4(self):
        d = validate_browser_call(ctx(), "browser_evaluate", {})
        assert not d.allowed
        assert d.effective_level == CapabilityLevel.SYSTEM_FORBIDDEN


# ── click capabilities ───────────────────────────────────────────────────────

class TestClickCapabilities:
    def test_only_reviewed_capabilities_allowed(self):
        assert click_capabilities() == frozenset({
            "marketing_trending_search", "marketing_accounts_sync",
            "marketing_publish_prepare",
        })
