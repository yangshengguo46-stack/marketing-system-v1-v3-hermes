"""Durable publishing action and receipt contracts for the native Agent loop.

This module owns marketing business facts only.  It does not execute a browser,
run an Agent, or implement a second approval system.  A real Hermes provider
prepares an action, records the native approval reference before execution,
and settles the action from the provider's observed result.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit

from agent.marketing.domains.content_policy import VALID_PLATFORMS
from agent.marketing.domains.storage import MarketingDomainRepository
from agent.marketing.intelligence.store import OperatingLoopRepository


ACTION_STATUSES = {
    "prepared",
    "executing",
    "unknown",
    "failed",
    "cancelled",
    "published",
}
FINAL_ACTION_STATUSES = {"failed", "cancelled", "published"}
METRIC_CHECKPOINTS = (
    ("1h", timedelta(hours=1)),
    ("6h", timedelta(hours=6)),
    ("24h", timedelta(hours=24)),
    ("3d", timedelta(days=3)),
    ("7d", timedelta(days=7)),
)

_PLATFORM_HOSTS = {
    "douyin": ("douyin.com",),
    "bilibili": ("bilibili.com", "b23.tv"),
    "xiaohongshu": ("xiaohongshu.com", "xhslink.com"),
    "kuaishou": ("kuaishou.com",),
    "wechat_channels": ("channels.weixin.qq.com", "weixin.qq.com"),
    "zhihu": ("zhihu.com",),
    "wechat_official": ("mp.weixin.qq.com",),
    "tiktok": ("tiktok.com",),
    "youtube": ("youtube.com", "youtu.be"),
}
_SENSITIVE_TEXT = re.compile(
    r"(?i)(api[_-]?key|authorization|cookie|password|secret|token)\s*[:=]\s*[^\s,;]+"
)


class PublishingRepository(MarketingDomainRepository):
    """Append-oriented publish intent, outcome and metric checkpoint store."""

    def __init__(self, paths=None):
        super().__init__(paths)
        self._ensure_schema()

    def prepare_action(
        self,
        *,
        user_id: str,
        account_id: str,
        asset_id: str,
        platform: str,
        provider: str,
        session_id: str = "",
        tool_call_id: str = "",
    ) -> dict[str, Any]:
        """Pre-log one idempotent action before any external side effect."""

        platform_value = _platform(platform)
        provider_value = _required(provider, "provider", 120)
        with self._transaction() as db:
            asset = db.execute(
                """SELECT * FROM content_assets
                WHERE id=? AND user_id=? AND account_id=?""",
                (asset_id, user_id, account_id),
            ).fetchone()
            if asset is None:
                raise KeyError("content asset not found in account scope")
            if asset["status"] != "review_ready":
                raise ValueError("only a review_ready asset can enter publishing approval")
            content = _object(asset["content_json"], "content asset")
            plan_id = str(content.get("_production_plan_id") or "").strip()
            if not plan_id:
                raise ValueError("content asset has no production plan")
            preflight = OperatingLoopRepository(self.paths).latest_preflight_for_plan(
                plan_id=plan_id,
                user_id=user_id,
                account_id=account_id,
            )
            decision = preflight.get("decision") or {}
            if decision.get("publish_eligible") is not True:
                raise ValueError(
                    "latest preflight is exploratory only; current positioning, content system "
                    "and a connected account are required before publishing review"
                )
            product_decision = decision.get("preflight_decision") or decision
            if product_decision.get("go") is not True:
                raise ValueError("latest preflight does not allow publishing review")
            _validate_asset_platform(asset_platform=str(asset["platform"] or ""), platform=platform_value, content=content)
            idempotency_key = _idempotency_key(
                account_id=account_id,
                asset_id=asset_id,
                version=int(asset["version"] or 1),
                platform=platform_value,
            )
            existing = db.execute(
                "SELECT id FROM marketing_publish_actions WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                return self.get_action(existing["id"])
            action_id = f"publish_{uuid.uuid4().hex}"
            request = {
                "title": str(asset["title"] or ""),
                "asset_type": str(asset["type"] or ""),
                "asset_version": int(asset["version"] or 1),
                "content_sha256": hashlib.sha256(
                    str(asset["content_json"]).encode("utf-8")
                ).hexdigest(),
                "sound_plan": content.get("sound_plan")
                if isinstance(content.get("sound_plan"), dict)
                else None,
                "content_kind": str(content.get("production_kind") or ""),
                "experiment_id": str(asset["experiment_id"] or "") or None,
                "prediction": content.get("prediction")
                if isinstance(content.get("prediction"), dict)
                else None,
            }
            now = _now()
            db.execute(
                """INSERT INTO marketing_publish_actions
                (id,idempotency_key,user_id,account_id,asset_id,asset_version,plan_id,
                 preflight_id,platform,provider,session_id,tool_call_id,status,
                 request_json,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'prepared',?,?,?)""",
                (
                    action_id,
                    idempotency_key,
                    user_id,
                    account_id,
                    asset_id,
                    int(asset["version"] or 1),
                    plan_id,
                    preflight["id"],
                    platform_value,
                    provider_value,
                    str(session_id or "")[:200],
                    str(tool_call_id or "")[:200],
                    json.dumps(request, ensure_ascii=False, separators=(",", ":")),
                    now,
                    now,
                ),
            )
        return self.get_action(action_id)

    def mark_execution_started(
        self,
        action_id: str,
        *,
        approval_ref: str,
    ) -> dict[str, Any]:
        """Bind a one-shot native approval immediately before provider execution."""

        approval_value = _required(approval_ref, "approval_ref", 300)
        now = _now()
        with self._transaction() as db:
            row = db.execute(
                "SELECT * FROM marketing_publish_actions WHERE id=?", (action_id,)
            ).fetchone()
            if row is None:
                raise KeyError("publish action not found")
            if row["status"] == "executing":
                return self.get_action(action_id)
            if row["status"] != "prepared":
                raise ValueError(f"publish action cannot execute from {row['status']}")
            updated = db.execute(
                """UPDATE content_assets SET status='approved',updated_at=?
                WHERE id=? AND user_id=? AND account_id=? AND status='review_ready'""",
                (now, row["asset_id"], row["user_id"], row["account_id"]),
            ).rowcount
            if updated != 1:
                raise ValueError("content asset is no longer ready for approval")
            db.execute(
                """UPDATE marketing_publish_actions
                SET status='executing',approval_ref=?,started_at=?,updated_at=?
                WHERE id=?""",
                (approval_value, now, now, action_id),
            )
        return self.get_action(action_id)

    def settle_action(
        self,
        action_id: str,
        *,
        outcome: str,
        provider_result: dict[str, Any] | None = None,
        verification_source: str = "",
        failure_code: str = "",
    ) -> dict[str, Any]:
        """Settle a provider-observed result without turning unknown into success."""

        outcome_value = str(outcome or "").strip().lower()
        if outcome_value not in {"published", "unknown", "failed", "cancelled"}:
            raise ValueError("unsupported publish outcome")
        result = provider_result or {}
        if not isinstance(result, dict):
            raise ValueError("provider_result must be an object")
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM marketing_publish_actions WHERE id=?", (action_id,)
            ).fetchone()
            if row is None:
                raise KeyError("publish action not found")
            if row["status"] in FINAL_ACTION_STATUSES:
                if row["status"] == outcome_value:
                    return self.get_action(action_id)
                raise ValueError(f"settled publish action is immutable: {row['status']}")
            if row["status"] not in {"executing", "unknown"}:
                raise ValueError(f"publish action cannot settle from {row['status']}")

            post_id = _platform_post_id(
                result.get("platform_post_id") or result.get("post_id")
            )
            published_url = _published_url(result.get("published_url") or result.get("url"), row["platform"])
            verification = str(verification_source or result.get("verification_source") or "").strip()
            if outcome_value == "published":
                if not post_id and not published_url:
                    raise ValueError("published outcome requires platform_post_id or stable platform URL")
                if not verification:
                    raise ValueError("published outcome requires a verification source")

        row = dict(row)
        request_payload = _object(row["request_json"], "publish request")
        sound_plan = request_payload.get("sound_plan") if isinstance(request_payload.get("sound_plan"), dict) else {}
        summary = {
            "outcome": outcome_value,
            "provider": row["provider"],
            "platform_post_id": post_id or None,
            "published_url": published_url or None,
            "verification_source": verification or None,
            "failure_code": str(failure_code or result.get("failure_code") or "")[:120] or None,
            "observed_at": str(result.get("observed_at") or _now()),
            "sound_id": sound_plan.get("sound_id"),
            "sound_mode": sound_plan.get("mode"),
            "experiment_id": request_payload.get("experiment_id"),
        }
        source_id = post_id or published_url or action_id
        # ReceiptRef is created first through its single owner.  If the process
        # dies before the action row is updated, retrying settle_action reuses
        # the same idempotent receipt and finishes the interrupted settlement.
        receipt = OperatingLoopRepository(self.paths).create_receipt(
            source_kind=f"publish:{row['platform']}:{row['provider']}",
            source_id=source_id,
            receipt_type=f"publish_{outcome_value}",
            user_id=row["user_id"],
            account_id=row["account_id"],
            platform=row["platform"],
            plan_id=row["plan_id"],
            preflight_id=row["preflight_id"],
            session_id=row["session_id"],
            summary=summary,
        )
        with self._transaction() as db:
            current = db.execute(
                "SELECT * FROM marketing_publish_actions WHERE id=?", (action_id,)
            ).fetchone()
            if current is None:
                raise KeyError("publish action not found")
            if current["status"] in FINAL_ACTION_STATUSES:
                if current["status"] == outcome_value:
                    return self.get_action(action_id)
                raise ValueError(f"settled publish action is immutable: {current['status']}")
            if current["status"] not in {"executing", "unknown"}:
                raise ValueError(f"publish action cannot settle from {current['status']}")
            now = _now()
            db.execute(
                """UPDATE marketing_publish_actions
                SET status=?,receipt_id=?,failure_code=?,settled_at=?,updated_at=?
                WHERE id=?""",
                (
                    outcome_value,
                    receipt["id"],
                    str(failure_code or result.get("failure_code") or "")[:120],
                    now,
                    now,
                    action_id,
                ),
            )
            if outcome_value == "published":
                db.execute(
                    """UPDATE content_assets SET status='published',updated_at=?
                    WHERE id=? AND user_id=? AND account_id=? AND status='approved'""",
                    (now, current["asset_id"], current["user_id"], current["account_id"]),
                )
                db.execute(
                    "UPDATE marketing_preflight_records SET status='settled' WHERE id=?",
                    (current["preflight_id"],),
                )
                db.execute(
                    "UPDATE content_production_plans SET status='published',updated_at=? WHERE id=?",
                    (now, current["plan_id"]),
                )
                self._create_metric_checkpoints(db, current, published_at=_parse_time(now))
        return self.get_action(action_id)

    def get_action(self, action_id: str) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM marketing_publish_actions WHERE id=?", (action_id,)
            ).fetchone()
        if row is None:
            raise KeyError("publish action not found")
        value = dict(row)
        value["request"] = json.loads(value.pop("request_json"))
        return value

    def list_unresolved_actions(
        self,
        *,
        user_id: str | None = None,
        account_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return actions that must be queried before any retry after restart."""

        query = "SELECT id FROM marketing_publish_actions WHERE status IN ('executing','unknown')"
        params: list[Any] = []
        if user_id is not None:
            query += " AND user_id=?"
            params.append(user_id)
        if account_id is not None:
            query += " AND account_id=?"
            params.append(account_id)
        query += " ORDER BY updated_at,id LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._connection() as db:
            rows = db.execute(query, params).fetchall()
        return [self.get_action(row["id"]) for row in rows]

    def list_verified_recoveries(
        self,
        *,
        user_id: str,
        account_id: str,
        platform: str | None = None,
        provider: str | None = None,
        content_kind: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return publish actions proven to recover from ``unknown`` to success.

        This is the evidence owner for procedural learning.  It joins the
        immutable unknown receipt to the later verified published receipt;
        callers cannot turn a final success row alone into recovery evidence.
        """

        account_value = _required(account_id, "account_id", 200)
        query = """SELECT action.*, unknown.id AS unknown_receipt_id,
            unknown.summary_json AS unknown_summary_json,
            published.id AS published_receipt_id,
            published.summary_json AS published_summary_json
        FROM marketing_publish_actions AS action
        JOIN marketing_receipt_refs AS unknown
          ON unknown.source_id=action.id
         AND unknown.receipt_type='publish_unknown'
         AND unknown.source_kind=('publish:' || action.platform || ':' || action.provider)
        JOIN marketing_receipt_refs AS published
          ON published.id=action.receipt_id
         AND published.receipt_type='publish_published'
        WHERE action.user_id=? AND action.account_id=? AND action.status='published'"""
        params: list[Any] = [str(user_id or "default"), account_value]
        if platform:
            query += " AND action.platform=?"
            params.append(_platform(platform))
        if provider:
            query += " AND action.provider=?"
            params.append(_required(provider, "provider", 120))
        query += " ORDER BY action.settled_at DESC,action.id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._connection() as db:
            rows = db.execute(query, params).fetchall()
        recoveries: list[dict[str, Any]] = []
        for row in rows:
            request = _object(row["request_json"], "publish request")
            kind = str(request.get("content_kind") or request.get("asset_type") or "").strip()
            if content_kind and kind != str(content_kind).strip():
                continue
            unknown = _object(row["unknown_summary_json"], "unknown receipt")
            published = _object(row["published_summary_json"], "published receipt")
            if not published.get("verification_source"):
                continue
            recoveries.append(
                {
                    "action_id": row["id"],
                    "platform": row["platform"],
                    "provider": row["provider"],
                    "content_kind": kind,
                    "unknown_receipt_id": row["unknown_receipt_id"],
                    "published_receipt_id": row["published_receipt_id"],
                    "failure_code": unknown.get("failure_code"),
                    "verification_source": published.get("verification_source"),
                    "settled_at": row["settled_at"],
                }
            )
        return recoveries[: max(1, min(int(limit), 500))]

    def list_metric_checkpoints(self, action_id: str) -> list[dict[str, Any]]:
        with self._connection() as db:
            rows = db.execute(
                """SELECT * FROM marketing_metric_checkpoints
                WHERE publish_action_id=? ORDER BY due_at,id""",
                (action_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_due_metric_checkpoints(
        self,
        *,
        as_of: str | None = None,
        user_id: str | None = None,
        account_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return pending checkpoints for the native Hermes scheduler."""

        cutoff = _parse_time(as_of or _now()).isoformat()
        query = (
            "SELECT * FROM marketing_metric_checkpoints "
            "WHERE status='pending' AND due_at<=? "
            "AND COALESCE(next_attempt_at,due_at)<=?"
        )
        params: list[Any] = [cutoff, cutoff]
        if user_id is not None:
            query += " AND user_id=?"
            params.append(user_id)
        if account_id is not None:
            query += " AND account_id=?"
            params.append(account_id)
        query += " ORDER BY due_at,id LIMIT ?"
        params.append(max(1, min(int(limit), 500)))
        with self._connection() as db:
            rows = db.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def claim_metric_checkpoint(
        self, checkpoint_id: str, *, as_of: str | None = None
    ) -> dict[str, Any] | None:
        """Atomically claim one due checkpoint for a platform Provider."""

        now = _now()
        cutoff = _parse_time(as_of or now).isoformat()
        with self._transaction() as db:
            updated = db.execute(
                """UPDATE marketing_metric_checkpoints
                SET status='collecting',claimed_at=?,attempt_count=attempt_count+1,
                    last_error=NULL,updated_at=?
                WHERE id=? AND status='pending'
                  AND due_at<=? AND COALESCE(next_attempt_at,due_at)<=?""",
                (now, now, checkpoint_id, cutoff, cutoff),
            ).rowcount
            if updated != 1:
                return None
            row = db.execute(
                "SELECT * FROM marketing_metric_checkpoints WHERE id=?",
                (checkpoint_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def defer_metric_checkpoint(
        self,
        checkpoint_id: str,
        *,
        retry_at: str,
        error: str,
    ) -> dict[str, Any]:
        """Release a failed/not-ready claim without inventing metric values."""

        retry = _parse_time(retry_at).isoformat()
        with self._transaction() as db:
            updated = db.execute(
                """UPDATE marketing_metric_checkpoints
                SET status='pending',next_attempt_at=?,claimed_at=NULL,last_error=?,updated_at=?
                WHERE id=? AND status='collecting'""",
                (retry, _safe_status_text(error), _now(), checkpoint_id),
            ).rowcount
            if updated != 1:
                raise ValueError("metric checkpoint is not collecting")
        return self.get_metric_checkpoint(checkpoint_id)

    def mark_metric_observed(
        self, checkpoint_id: str, *, metric_receipt_id: str
    ) -> dict[str, Any]:
        """Bind an immutable observed receipt before interpretation starts."""

        receipt_value = _required(metric_receipt_id, "metric_receipt_id", 200)
        with self._transaction() as db:
            updated = db.execute(
                """UPDATE marketing_metric_checkpoints
                SET status='observed',metric_receipt_id=?,claimed_at=NULL,
                    next_attempt_at=NULL,last_error=NULL,updated_at=?
                WHERE id=? AND status='collecting'""",
                (receipt_value, _now(), checkpoint_id),
            ).rowcount
            if updated != 1:
                current = db.execute(
                    "SELECT metric_receipt_id,status FROM marketing_metric_checkpoints WHERE id=?",
                    (checkpoint_id,),
                ).fetchone()
                if current is None:
                    raise KeyError("metric checkpoint not found")
                if current["status"] in {"observed", "settled"} and current["metric_receipt_id"] == receipt_value:
                    return self.get_metric_checkpoint(checkpoint_id)
                raise ValueError("metric checkpoint is not collecting")
        return self.get_metric_checkpoint(checkpoint_id)

    def mark_metric_unavailable(
        self, checkpoint_id: str, *, metric_receipt_id: str
    ) -> dict[str, Any]:
        with self._transaction() as db:
            updated = db.execute(
                """UPDATE marketing_metric_checkpoints
                SET status='unavailable',metric_receipt_id=?,claimed_at=NULL,
                    next_attempt_at=NULL,updated_at=?
                WHERE id=? AND status='collecting'""",
                (metric_receipt_id, _now(), checkpoint_id),
            ).rowcount
            if updated != 1:
                raise ValueError("metric checkpoint is not collecting")
        return self.get_metric_checkpoint(checkpoint_id)

    def list_observed_metric_checkpoints(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._connection() as db:
            rows = db.execute(
                """SELECT * FROM marketing_metric_checkpoints
                WHERE status='observed' ORDER BY updated_at,id LIMIT ?""",
                (max(1, min(int(limit), 500)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_metric_reconciled(self, checkpoint_id: str) -> dict[str, Any]:
        with self._transaction() as db:
            updated = db.execute(
                """UPDATE marketing_metric_checkpoints SET status='settled',updated_at=?
                WHERE id=? AND status='observed' AND metric_receipt_id IS NOT NULL""",
                (_now(), checkpoint_id),
            ).rowcount
            if updated != 1:
                current = db.execute(
                    "SELECT status FROM marketing_metric_checkpoints WHERE id=?",
                    (checkpoint_id,),
                ).fetchone()
                if current is None:
                    raise KeyError("metric checkpoint not found")
                if current["status"] != "settled":
                    raise ValueError("metric checkpoint is not ready for reconciliation")
        return self.get_metric_checkpoint(checkpoint_id)

    def get_metric_checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM marketing_metric_checkpoints WHERE id=?",
                (checkpoint_id,),
            ).fetchone()
        if row is None:
            raise KeyError("metric checkpoint not found")
        return dict(row)

    def recover_stale_metric_claims(
        self, *, stale_before: str, retry_at: str | None = None
    ) -> int:
        """Return process-crash claims to pending for the next Cron tick."""

        cutoff = _parse_time(stale_before).isoformat()
        retry = _parse_time(retry_at or _now()).isoformat()
        with self._transaction() as db:
            return db.execute(
                """UPDATE marketing_metric_checkpoints
                SET status='pending',next_attempt_at=?,claimed_at=NULL,
                    last_error='stale_collection_claim_recovered',updated_at=?
                WHERE status='collecting' AND claimed_at<?""",
                (retry, _now(), cutoff),
            ).rowcount

    def _create_metric_checkpoints(self, db, action, *, published_at: datetime) -> None:
        now = _now()
        for label, delta in METRIC_CHECKPOINTS:
            checkpoint_id = f"metric_{uuid.uuid4().hex}"
            db.execute(
                """INSERT OR IGNORE INTO marketing_metric_checkpoints
                (id,publish_action_id,user_id,account_id,platform,label,due_at,status,
                 created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,'pending',?,?)""",
                (
                    checkpoint_id,
                    action["id"],
                    action["user_id"],
                    action["account_id"],
                    action["platform"],
                    label,
                    (published_at + delta).isoformat(),
                    now,
                    now,
                ),
            )

    def _ensure_schema(self) -> None:
        with self._connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS marketing_publish_actions (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL REFERENCES content_assets(id),
                    asset_version INTEGER NOT NULL,
                    plan_id TEXT NOT NULL REFERENCES content_production_plans(id),
                    preflight_id TEXT NOT NULL REFERENCES marketing_preflight_records(id),
                    platform TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    session_id TEXT NOT NULL DEFAULT '',
                    tool_call_id TEXT NOT NULL DEFAULT '',
                    approval_ref TEXT,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    receipt_id TEXT,
                    failure_code TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    settled_at TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_marketing_publish_scope
                    ON marketing_publish_actions(account_id,platform,status,updated_at);
                CREATE TABLE IF NOT EXISTS marketing_metric_checkpoints (
                    id TEXT PRIMARY KEY,
                    publish_action_id TEXT NOT NULL REFERENCES marketing_publish_actions(id),
                    user_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    label TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    metric_receipt_id TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT,
                    claimed_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(publish_action_id,label)
                );
                CREATE INDEX IF NOT EXISTS idx_marketing_metric_due
                    ON marketing_metric_checkpoints(status,due_at);
                """
            )
            columns = {
                row["name"]
                for row in db.execute("PRAGMA table_info(marketing_metric_checkpoints)")
            }
            additions = {
                "attempt_count": "INTEGER NOT NULL DEFAULT 0",
                "next_attempt_at": "TEXT",
                "claimed_at": "TEXT",
                "last_error": "TEXT",
            }
            for column, declaration in additions.items():
                if column not in columns:
                    db.execute(
                        f"ALTER TABLE marketing_metric_checkpoints ADD COLUMN {column} {declaration}"
                    )


def _validate_asset_platform(*, asset_platform: str, platform: str, content: dict[str, Any]) -> None:
    if asset_platform == "multi_article":
        variants = content.get("platform_variants") or {}
        if platform not in variants:
            raise ValueError("article bundle has no variant for the target platform")
        return
    if asset_platform != platform:
        raise ValueError("content asset platform does not match publish platform")


def _safe_status_text(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return _SENSITIVE_TEXT.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)[:500]


def _idempotency_key(*, account_id: str, asset_id: str, version: int, platform: str) -> str:
    raw = f"{account_id}\0{asset_id}\0{version}\0{platform}".encode("utf-8")
    return "publish:" + hashlib.sha256(raw).hexdigest()


def _published_url(value: Any, platform: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError as exc:
        raise ValueError("published_url is invalid") from exc
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or not host or parsed.username or parsed.password:
        raise ValueError("published_url must be a public HTTPS platform URL")
    allowed = _PLATFORM_HOSTS[platform]
    if not any(host == item or host.endswith("." + item) for item in allowed):
        raise ValueError("published_url host does not match target platform")
    if parsed.path in {"", "/"}:
        raise ValueError("published_url must identify a concrete work")
    return text


def _platform_post_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > 500 or any(character.isspace() for character in text):
        raise ValueError("platform_post_id is invalid")
    if any(ord(character) < 32 for character in text):
        raise ValueError("platform_post_id is invalid")
    return text


def _platform(value: Any) -> str:
    platform = str(value or "").strip().lower()
    if platform not in VALID_PLATFORMS:
        raise ValueError("unsupported publish platform")
    return platform


def _required(value: Any, field: str, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    if len(text) > limit:
        raise ValueError(f"{field} exceeds {limit} characters")
    return text


def _object(value: Any, field: str) -> dict[str, Any]:
    try:
        decoded = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} is invalid") from exc
    if not isinstance(decoded, dict):
        raise ValueError(f"{field} is invalid")
    return decoded


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
