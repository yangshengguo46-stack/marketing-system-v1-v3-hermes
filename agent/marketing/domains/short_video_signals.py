"""Verified short-video and BGM observations owned by Hermes state."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.browser_payloads import decode_schema_payload
from agent.marketing.domains.content_policy import VIDEO_PLATFORMS
from agent.marketing.domains.storage import MarketingDomainRepository


SIGNAL_SCHEMA = "marketing_short_video_signal.v1"
RIGHTS_STATUSES = {"unknown", "platform_library", "licensed", "user_owned", "restricted"}


def decode_browser_signal_result(result: Any) -> dict[str, Any] | None:
    """Find the collector payload inside a Playwright MCP text response."""

    return decode_schema_payload(result, SIGNAL_SCHEMA)


class ShortVideoSignalRepository(MarketingDomainRepository):
    """Capture real browser observations and derive account-scoped sound momentum."""

    def capture_browser_result(
        self,
        *,
        user_id: str,
        account_id: str,
        payload: dict[str, Any],
        session_id: str,
        tool_call_id: str = "",
    ) -> dict[str, Any]:
        if payload.get("schema") != SIGNAL_SCHEMA:
            raise ValueError("unsupported short-video signal schema")
        platform = _platform(payload.get("platform"))
        observed_at = _iso_time(payload.get("observed_at"))
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValueError("short-video signal items must be a list")
        captured: list[dict[str, Any]] = []
        for raw in items[:100]:
            if not isinstance(raw, dict):
                continue
            item = self._capture_item(
                user_id=user_id,
                account_id=account_id,
                platform=platform,
                observed_at=observed_at,
                item=raw,
                session_id=session_id,
                tool_call_id=tool_call_id,
            )
            if item:
                captured.append(item)
        return {
            "schema": SIGNAL_SCHEMA,
            "platform": platform,
            "observed_at": observed_at,
            "captured": captured,
            "total": len(captured),
        }

    def _capture_item(
        self,
        *,
        user_id: str,
        account_id: str,
        platform: str,
        observed_at: str,
        item: dict[str, Any],
        session_id: str,
        tool_call_id: str,
    ) -> dict[str, Any] | None:
        source_item_id = _text(item.get("source_item_id"), 200)
        source_url = _canonical_url(item.get("source_url"))
        if not source_item_id or not source_url:
            return None
        canonical = {
            "platform": platform,
            "source_item_id": source_item_id,
            "source_url": source_url,
            "caption": _text(item.get("caption"), 1_000),
            "creator": _text(item.get("creator"), 200),
            "published_at": _optional_iso_time(item.get("published_at")),
            "rank": _positive_int(item.get("rank")),
            "view_count": _nonnegative_int(item.get("view_count")),
            "like_count": _nonnegative_int(item.get("like_count")),
            "comment_count": _nonnegative_int(item.get("comment_count")),
            "share_count": _nonnegative_int(item.get("share_count")),
            "use_count": _nonnegative_int(item.get("use_count")),
            "sound": _sound_payload(item.get("sound")),
        }
        raw = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        content_hash = hashlib.sha256(raw.encode()).hexdigest()
        evidence_id = "evidence_" + hashlib.sha256(
            f"{user_id}\0{account_id}\0short_video\0{source_url}\0{content_hash}".encode()
        ).hexdigest()[:28]
        observation_id = "svobs_" + hashlib.sha256(
            f"{user_id}\0{account_id}\0{platform}\0{source_item_id}\0{observed_at}".encode()
        ).hexdigest()[:28]
        sound_id = None
        sound = canonical["sound"]
        now = _now()
        with self._transaction() as db:
            db.execute(
                """INSERT INTO evidence_records
                (id,user_id,account_id,source_type,provider,canonical_url,title,excerpt,
                 content_sha256,status,verification_level,captured_at,session_id,
                 tool_call_id,metadata_json,created_at,updated_at)
                VALUES (?,?,?,'short_video',?,?,?,?,?,'verified','browser_observation',?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at""",
                (
                    evidence_id,
                    user_id,
                    account_id,
                    "marketing_browser_short_video",
                    source_url,
                    canonical["caption"][:500],
                    raw[:4_000],
                    content_hash,
                    observed_at,
                    session_id,
                    tool_call_id,
                    json.dumps(
                        {
                            "collector": "marketing_browser_mcp",
                            "signal_schema": SIGNAL_SCHEMA,
                            "claim_truth_verified": False,
                            "verification_note": "Observed in a real account-scoped browser page; platform counters may change.",
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    now,
                    now,
                ),
            )
            if sound:
                sound_id = _sound_id(platform, sound["platform_sound_id"])
                db.execute(
                    """INSERT INTO marketing_sounds
                    (id,platform,platform_sound_id,title,artist,duration_ms,canonical_url,
                     rights_status,metadata_json,first_seen_at,last_seen_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(platform,platform_sound_id) DO UPDATE SET
                        title=CASE WHEN excluded.title!='' THEN excluded.title ELSE marketing_sounds.title END,
                        artist=CASE WHEN excluded.artist!='' THEN excluded.artist ELSE marketing_sounds.artist END,
                        duration_ms=COALESCE(excluded.duration_ms,marketing_sounds.duration_ms),
                        canonical_url=CASE WHEN excluded.canonical_url!='' THEN excluded.canonical_url ELSE marketing_sounds.canonical_url END,
                        rights_status=CASE WHEN excluded.rights_status!='unknown' THEN excluded.rights_status ELSE marketing_sounds.rights_status END,
                        metadata_json=excluded.metadata_json,last_seen_at=excluded.last_seen_at""",
                    (
                        sound_id,
                        platform,
                        sound["platform_sound_id"],
                        sound["title"],
                        sound["artist"],
                        sound["duration_ms"],
                        sound["canonical_url"],
                        sound["rights_status"],
                        json.dumps({"tags": sound["tags"]}, ensure_ascii=False, separators=(",", ":")),
                        observed_at,
                        observed_at,
                    ),
                )
            db.execute(
                """INSERT INTO marketing_short_video_observations
                (id,user_id,account_id,platform,source_item_id,source_url,evidence_id,sound_id,
                 observed_at,published_at,rank,view_count,like_count,comment_count,share_count,
                 use_count,metrics_json,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    evidence_id=excluded.evidence_id,sound_id=excluded.sound_id,
                    rank=excluded.rank,view_count=excluded.view_count,like_count=excluded.like_count,
                    comment_count=excluded.comment_count,share_count=excluded.share_count,
                    use_count=excluded.use_count,metrics_json=excluded.metrics_json""",
                (
                    observation_id,
                    user_id,
                    account_id,
                    platform,
                    source_item_id,
                    source_url,
                    evidence_id,
                    sound_id,
                    observed_at,
                    canonical["published_at"],
                    canonical["rank"],
                    canonical["view_count"],
                    canonical["like_count"],
                    canonical["comment_count"],
                    canonical["share_count"],
                    canonical["use_count"],
                    json.dumps({"caption": canonical["caption"]}, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
        return {
            "observation_id": observation_id,
            "evidence_id": evidence_id,
            "sound_id": sound_id,
            "source_item_id": source_item_id,
        }

    def rank_sounds(
        self,
        *,
        user_id: str,
        account_id: str,
        platform: str,
        objective: str = "",
        window_hours: int = 72,
        limit: int = 20,
    ) -> dict[str, Any]:
        platform_value = _platform(platform)
        hours = max(1, min(int(window_hours), 24 * 30))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        with self._connection() as db:
            rows = db.execute(
                """SELECT o.*,s.platform_sound_id,s.title,s.artist,s.duration_ms,
                          s.canonical_url AS sound_url,s.rights_status,s.metadata_json AS sound_metadata_json
                FROM marketing_short_video_observations o
                JOIN marketing_sounds s ON s.id=o.sound_id
                WHERE o.user_id=? AND o.account_id=? AND o.platform=? AND o.observed_at>=?
                ORDER BY o.observed_at ASC""",
                (user_id, account_id, platform_value, cutoff.isoformat()),
            ).fetchall()
        grouped: dict[str, list[Any]] = {}
        for row in rows:
            grouped.setdefault(row["sound_id"], []).append(row)
        candidates = [
            _ranked_sound(sound_rows, objective=objective, window_hours=hours)
            for sound_rows in grouped.values()
        ]
        candidates.sort(key=lambda item: (-item["selection_score"], item["sound_id"]))
        safe_limit = max(1, min(int(limit), 50))
        return {
            "platform": platform_value,
            "window_hours": hours,
            "objective": _text(objective, 500),
            "candidates": candidates[:safe_limit],
            "observation_count": len(rows),
            "sound_count": len(grouped),
            "semantics": (
                "selection_score combines observed reach, repetition, recency, objective overlap and rights safety; "
                "it is a prior, not proof that the sound caused performance"
            ),
        }

    def require_sound(
        self,
        *,
        user_id: str,
        account_id: str,
        platform: str,
        sound_id: str,
    ) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                """SELECT s.* FROM marketing_sounds s
                WHERE s.id=? AND s.platform=? AND EXISTS (
                    SELECT 1 FROM marketing_short_video_observations o
                    WHERE o.sound_id=s.id AND o.user_id=? AND o.account_id=?
                )""",
                (str(sound_id or "").strip(), _platform(platform), user_id, account_id),
            ).fetchone()
        if row is None:
            raise ValueError("sound_id is not backed by a browser observation in this account scope")
        if row["rights_status"] == "restricted":
            raise ValueError("restricted sound cannot enter a production draft")
        value = dict(row)
        value["metadata"] = json.loads(value.pop("metadata_json") or "{}")
        return value


def _ranked_sound(rows: list[Any], *, objective: str, window_hours: int) -> dict[str, Any]:
    latest = rows[-1]
    views = sum(int(row["view_count"] or 0) for row in rows)
    uses = max((int(row["use_count"] or 0) for row in rows), default=0)
    repetitions = len({row["source_item_id"] for row in rows})
    reach = min(1.0, math.log10(views + 1) / 9.0)
    repeat = min(1.0, repetitions / 8.0)
    use_signal = min(1.0, math.log10(uses + 1) / 7.0)
    try:
        age_hours = max(0.0, (datetime.now(timezone.utc) - datetime.fromisoformat(latest["observed_at"])).total_seconds() / 3600)
    except ValueError:
        age_hours = float(window_hours)
    recency = max(0.0, 1.0 - age_hours / max(1, window_hours))
    metadata = json.loads(latest["sound_metadata_json"] or "{}")
    searchable = " ".join(
        [latest["title"] or "", latest["artist"] or "", *[str(x) for x in metadata.get("tags", [])]]
    ).lower()
    tokens = [part for part in re.split(r"[\s,，。；;、/#]+", objective.lower()) if len(part) >= 2]
    fit = 0.5 if not tokens else min(1.0, sum(token in searchable for token in tokens) / max(1, min(4, len(tokens))))
    rights_status = latest["rights_status"] or "unknown"
    rights = {"platform_library": 1.0, "licensed": 1.0, "user_owned": 1.0, "unknown": 0.45, "restricted": 0.0}[rights_status]
    score = round(0.30 * reach + 0.22 * repeat + 0.18 * use_signal + 0.15 * recency + 0.10 * fit + 0.05 * rights, 4)
    return {
        "sound_id": latest["sound_id"],
        "platform_sound_id": latest["platform_sound_id"],
        "title": latest["title"],
        "artist": latest["artist"],
        "duration_ms": latest["duration_ms"],
        "canonical_url": latest["sound_url"],
        "rights_status": rights_status,
        "selection_score": score,
        "signals": {
            "sampled_posts": repetitions,
            "sampled_views": views,
            "reported_uses": uses,
            "recency": round(recency, 4),
            "objective_fit": round(fit, 4),
        },
        "evidence_ids": list(dict.fromkeys(row["evidence_id"] for row in rows))[:20],
    }


def _sound_payload(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    platform_sound_id = _text(value.get("platform_sound_id"), 240)
    if not platform_sound_id:
        return None
    rights_status = _text(value.get("rights_status"), 40) or "unknown"
    if rights_status not in RIGHTS_STATUSES:
        rights_status = "unknown"
    tags = value.get("tags") if isinstance(value.get("tags"), list) else []
    return {
        "platform_sound_id": platform_sound_id,
        "title": _text(value.get("title"), 300),
        "artist": _text(value.get("artist"), 200),
        "duration_ms": _nonnegative_int(value.get("duration_ms")),
        "canonical_url": _canonical_url(value.get("canonical_url")),
        "rights_status": rights_status,
        "tags": list(dict.fromkeys(_text(item, 80) for item in tags if _text(item, 80)))[:20],
    }


def _sound_id(platform: str, platform_sound_id: str) -> str:
    return "sound_" + hashlib.sha256(f"{platform}\0{platform_sound_id}".encode()).hexdigest()[:28]


def _platform(value: Any) -> str:
    platform = _text(value, 80).lower()
    if platform not in VIDEO_PLATFORMS:
        raise ValueError(f"unsupported short-video platform: {platform}")
    return platform


def _canonical_url(value: Any) -> str:
    text = _text(value, 2_000)
    try:
        parsed = urlsplit(text)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        return ""
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", "", ""))


def _iso_time(value: Any) -> str:
    text = _text(value, 80)
    if not text:
        return _now()
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        epoch = float(text)
        if epoch > 10_000_000_000:
            epoch /= 1_000
        try:
            return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError) as exc:
            raise ValueError("invalid observed_at") from exc
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid observed_at") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _optional_iso_time(value: Any) -> str | None:
    return _iso_time(value) if _text(value, 80) else None


def _nonnegative_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _positive_int(value: Any) -> int | None:
    number = _nonnegative_int(value)
    return number if number and number > 0 else None


def _text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
