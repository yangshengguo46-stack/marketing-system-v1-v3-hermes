"""Stable domain enums shared by the runtime, API, and tests."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum, IntEnum
from typing import Any


class CapabilityLevel(IntEnum):
    READ_ONLY = 0
    REVERSIBLE_WRITE = 1
    CONTROLLED_RESOURCE = 2
    EXTERNAL_EFFECT = 3
    SYSTEM_FORBIDDEN = 4


class ErrorCategory(str, Enum):
    """Classify every tool/runtime error for deterministic retry behaviour."""
    RETRYABLE = "retryable"            # transient infra: timeout, 503, connection reset
    PERMANENT = "permanent"            # bad input, schema mismatch, not found
    AUTH = "auth"                      # 401, expired token, permission denied at platform
    APPROVAL = "approval"              # user rejected, approval expired
    NETWORK = "network"                # DNS, proxy, connection refused, ECONNREFUSED
    RATE_LIMIT = "rate_limit"          # 429, platform quota, retry-after
    SCHEMA_CHANGE = "schema_change"    # tool schema changed, missing required field
    UNKNOWN = "unknown"                # unclassified — default fail-closed

    @property
    def retryable(self) -> bool:
        return self in {ErrorCategory.RETRYABLE, ErrorCategory.RATE_LIMIT, ErrorCategory.NETWORK}

    @property
    def default_retry_delay(self) -> float:
        return {
            ErrorCategory.RETRYABLE: 1.0,
            ErrorCategory.RATE_LIMIT: 30.0,
            ErrorCategory.NETWORK: 2.0,
        }.get(self, 0.0)


# Error classification patterns — checked in order, first match wins
_ERROR_CLASSIFIERS: list[tuple[str, ErrorCategory]] = [
    # rate_limit first (429 trumps generic 5xx)
    ("429", ErrorCategory.RATE_LIMIT),
    ("rate limit", ErrorCategory.RATE_LIMIT),
    ("too many requests", ErrorCategory.RATE_LIMIT),
    ("quota exceeded", ErrorCategory.RATE_LIMIT),
    # auth
    ("401", ErrorCategory.AUTH),
    ("403", ErrorCategory.AUTH),
    ("unauthorized", ErrorCategory.AUTH),
    ("permission denied", ErrorCategory.AUTH),
    ("authentication", ErrorCategory.AUTH),
    # approval
    ("pending_approval", ErrorCategory.APPROVAL),
    ("approval expired", ErrorCategory.APPROVAL),
    ("approval rejected", ErrorCategory.APPROVAL),
    ("user rejected", ErrorCategory.APPROVAL),
    # schema_change
    ("missing required", ErrorCategory.SCHEMA_CHANGE),
    ("unknown parameter", ErrorCategory.SCHEMA_CHANGE),
    ("unexpected tool schema", ErrorCategory.SCHEMA_CHANGE),
    # network
    ("connection refused", ErrorCategory.NETWORK),
    ("connection reset", ErrorCategory.NETWORK),
    ("econnrefused", ErrorCategory.NETWORK),
    ("dns", ErrorCategory.NETWORK),
    ("proxy", ErrorCategory.NETWORK),
    ("tunnel connection", ErrorCategory.NETWORK),
    # retryable
    ("503", ErrorCategory.RETRYABLE),
    ("502", ErrorCategory.RETRYABLE),
    ("504", ErrorCategory.RETRYABLE),
    ("timeout", ErrorCategory.RETRYABLE),
    ("timed out", ErrorCategory.RETRYABLE),
    ("temporarily unavailable", ErrorCategory.RETRYABLE),
    # permanent
    ("not found", ErrorCategory.PERMANENT),
    ("400", ErrorCategory.PERMANENT),
    ("invalid", ErrorCategory.PERMANENT),
]


def classify_error(message: str) -> ErrorCategory:
    """Return error category for a human-readable or machine error string."""
    lowered = str(message).strip().lower()
    for pattern, category in _ERROR_CLASSIFIERS:
        if pattern in lowered:
            return category
    return ErrorCategory.UNKNOWN


# ── Retry policy ─────────────────────────────────────────────────────────────

@dataclass
class RetryDecision:
    should_retry: bool
    delay_seconds: float
    reason: str
    attempt: int = 0
    max_attempts: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "should_retry": self.should_retry, "delay_seconds": self.delay_seconds,
            "reason": self.reason, "attempt": self.attempt, "max_attempts": self.max_attempts,
        }


def decide_retry(
    error_message: str,
    tool_name: str = "",
    attempt: int = 1,
    max_attempts: int = 3,
    has_side_effects: bool = False,
) -> RetryDecision:
    """Determine if a tool error should be retried.

    Rules:
    - RETRYABLE / NETWORK / RATE_LIMIT → retry with backoff (if not side-effectful)
    - Side-effect tools (L2+) never auto-retry without receipt check
    - PERMANENT / AUTH / APPROVAL / SCHEMA_CHANGE / UNKNOWN → no retry
    - Exceeding max_attempts → no retry
    """
    category = classify_error(error_message)

    # Never retry these
    if category in (ErrorCategory.PERMANENT, ErrorCategory.AUTH,
                     ErrorCategory.APPROVAL, ErrorCategory.SCHEMA_CHANGE,
                     ErrorCategory.UNKNOWN):
        return RetryDecision(should_retry=False, delay_seconds=0,
                              reason=f"{category.value}: {error_message[:120]}")

    # Side-effect guard
    if has_side_effects and category != ErrorCategory.RATE_LIMIT:
        return RetryDecision(should_retry=False, delay_seconds=0,
                              reason=f"side-effect tool, retry blocked for {category.value}")

    if attempt >= max_attempts:
        return RetryDecision(should_retry=False, delay_seconds=0,
                              reason=f"max retries ({max_attempts}) exhausted")

    delay = min(category.default_retry_delay * (2 ** (attempt - 1)), 120.0)
    return RetryDecision(should_retry=True, delay_seconds=delay,
                          reason=f"{category.value}: retry {attempt}/{max_attempts}",
                          attempt=attempt, max_attempts=max_attempts)


class TaskStatus(str, Enum):
    QUEUED = "queued"
    PLANNING = "planning"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    RETRYING = "retrying"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class MemoryKind(str, Enum):
    USER = "user"
    ACCOUNT = "account"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"

    @property
    def default_ttl_days(self) -> int | None:
        """Return the default TTL in days for this memory kind.

        None means "no automatic expiry" (locked facts are never expired).
        """
        return {
            MemoryKind.USER: 90,         # preferences can drift
            MemoryKind.ACCOUNT: None,     # account DNA is semi-permanent
            MemoryKind.EPISODIC: 180,     # project events age slowly
            MemoryKind.SEMANTIC: 365,     # knowledge can be long-lived
            MemoryKind.PROCEDURAL: None,  # skills/processes need explicit deprecation
        }.get(self)


def memory_is_expired(memory: dict[str, Any], *, now: str | None = None) -> bool:
    """Check if a memory entry has exceeded its TTL.

    Locked memories never expire.  Memories without a kind TTL never expire.
    """
    if memory.get("status") == "locked":
        return False
    kind_str = memory.get("kind", "")
    try:
        kind = MemoryKind(kind_str)
    except ValueError:
        return False
    ttl = kind.default_ttl_days
    if ttl is None:
        return False
    observed = memory.get("observed_at") or memory.get("created_at")
    if not observed:
        return False
    from datetime import datetime, timezone, timedelta
    try:
        observed_dt = datetime.fromisoformat(observed)
        ref = datetime.fromisoformat(now) if now else datetime.now(timezone.utc)
        return (ref - observed_dt) > timedelta(days=ttl)
    except (ValueError, TypeError):
        return False


class PlanStepStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    WAITING_APPROVAL = "waiting_approval"

    NOT_STARTED = {PENDING}
    ACTIVE = {RUNNING, WAITING_APPROVAL}
    FINISHED = {COMPLETED, SKIPPED}


@dataclass
class PlanStep:
    """Single step in an agent task plan.

    Stored as a JSON dict inside plan_json. This dataclass provides
    type-safe access without changing the SQL schema.
    """
    id: str
    description: str
    tool_name: str | None = None
    status: str = PlanStepStatus.PENDING
    effect_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return {k: v for k, v in d.items() if v is not None}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PlanStep":
        return cls(
            id=str(d.get("id", "")),
            description=str(d.get("description", "")),
            tool_name=d.get("tool_name") or d.get("tool_guess"),
            status=str(d.get("status", PlanStepStatus.PENDING)),
            effect_id=d.get("effect_id"),
        )

    @classmethod
    def from_legacy(cls, d: dict[str, Any]) -> "PlanStep":
        """Convert from old dict format (id, description, tool_guess, status)."""
        return cls.from_dict(d)


# ── Unified source contract ──────────────────────────────────────────────────

@dataclass
class SourceContract:
    """Every data item ingested into the system must satisfy this shape.

    Required: source, platform, url, title, collected_at.
    Optional fields document richer provenance when available.
    """
    source: str              # backend name: hot_topics_api | bilibili_public | playwright_mcp_creator_center | electron_session
    platform: str            # douyin | bilibili | xiaohongshu | zhihu | ...
    url: str                 # canonical URL
    title: str               # display title, max 500 chars
    collected_at: str        # ISO-8601 timestamp when the item was fetched
    rank: int | None = None
    author: str | None = None
    published_at: str | None = None
    metrics: dict[str, Any] | None = None          # views, likes, comments, shares, ...
    query: str | None = None                        # search term that produced this item
    account_scope: str | None = None                # account_id if session-scoped
    raw_ref: str | None = None                      # pointer to raw fixture/file (not URL)
    additional: dict[str, Any] | None = None        # source-specific extra fields (preserved but not indexed)

    _REQUIRED = frozenset({"source", "platform", "url", "title", "collected_at"})
    _ALL_FIELDS = frozenset({
        "source", "platform", "url", "title", "collected_at",
        "rank", "author", "published_at", "metrics", "query",
        "account_scope", "raw_ref", "additional",
    })

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SourceContract":
        """Normalize and validate an incoming item dict.

        Unknown keys are preserved in ``additional``.  Missing required
        keys are rejected.  Types are coerced where safe (int→str), rejected
        where unsafe (non-string for url/title).
        """
        missing = cls._REQUIRED - set(raw.keys())
        if missing:
            raise ValueError(f"SourceContract missing required fields: {sorted(missing)}")

        extra = {}
        for k, v in list(raw.items()):
            if k not in cls._ALL_FIELDS:
                extra[k] = raw.pop(k)
        if extra:
            raw["additional"] = {**(raw.get("additional") or {}), **extra}

        # type coercion
        url_val = str(raw["url"]).strip()
        if not url_val or len(url_val) > 2048:
            raise ValueError(f"invalid url: {url_val[:100]!r}")
        if url_val.lower().startswith(("javascript:", "data:", "file:")):
            raise ValueError(f"forbidden url scheme: {url_val[:50]!r}")

        title_val = str(raw["title"]).strip()[:500]
        if not title_val:
            raise ValueError("title must not be empty")

        return cls(
            source=str(raw["source"]).strip().lower(),
            platform=str(raw["platform"]).strip().lower(),
            url=url_val,
            title=title_val,
            collected_at=str(raw["collected_at"]),
            rank=int(raw["rank"]) if raw.get("rank") is not None else None,
            author=str(raw["author"])[:200] if raw.get("author") else None,
            published_at=str(raw["published_at"]) if raw.get("published_at") else None,
            metrics=raw.get("metrics") if isinstance(raw.get("metrics"), dict) else None,
            query=str(raw["query"])[:200] if raw.get("query") else None,
            account_scope=str(raw["account_scope"])[:100] if raw.get("account_scope") else None,
            raw_ref=str(raw["raw_ref"])[:500] if raw.get("raw_ref") else None,
            additional=raw.get("additional"),
        )

    def to_evidence_dict(self) -> dict[str, Any]:
        """Minimal evidence dict suitable for Hermes context injection."""
        d: dict[str, Any] = {
            "source": self.source, "platform": self.platform,
            "url": self.url, "title": self.title, "collected_at": self.collected_at,
        }
        if self.rank is not None:
            d["rank"] = self.rank
        if self.author:
            d["author"] = self.author
        if self.published_at:
            d["published_at"] = self.published_at
        if self.query:
            d["query"] = self.query
        return d

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "source": self.source, "platform": self.platform,
            "url": self.url, "title": self.title, "collected_at": self.collected_at,
        }
        for k in ("rank", "author", "published_at", "metrics", "query",
                   "account_scope", "raw_ref", "additional"):
            v = getattr(self, k)
            if v is not None:
                d[k] = v
        return d


class SourceValidationError(ValueError):
    pass


def validate_source_batch(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize a batch of source items; keep the good, log the bad.

    Returns a list of validated ``SourceContract.to_dict()`` dicts.
    Invalid items are silently dropped (empty title / forbidden URL).
    """
    result: list[dict[str, Any]] = []
    for item in items:
        try:
            sc = SourceContract.from_dict(item)
            result.append(sc.to_dict())
        except (ValueError, TypeError):
            continue
    return result


ACCOUNT_DNA_FIELDS = [
    "persona",
    "tone",
    "audience",
    "content_pillars",
    "taboos",
    "goals",
]

ACCOUNT_DNA_LABELS = {
    "persona": "人设定位",
    "tone": "内容风格",
    "audience": "目标受众",
    "content_pillars": "内容支柱",
    "taboos": "禁区",
    "goals": "账号目标",
}
