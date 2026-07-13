"""Evidence-backed owned-content portfolio and execution baseline."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from statistics import mean, median, pstdev
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.browser_payloads import decode_schema_payload
from agent.marketing.domains.storage import MarketingDomainRepository


PORTFOLIO_SCHEMA = "marketing_wechat_official_portfolio.v1"


def decode_browser_portfolio_result(result: Any) -> dict[str, Any] | None:
    return decode_schema_payload(result, PORTFOLIO_SCHEMA)


class AccountPortfolioRepository(MarketingDomainRepository):
    """Persist first-party account work and expose a non-causal scorecard."""

    def __init__(self, paths: MarketingDataPaths | None = None):
        super().__init__(paths)

    def capture_browser_result(
        self,
        *,
        user_id: str,
        account_id: str,
        payload: dict[str, Any],
        session_id: str,
        tool_call_id: str = "",
    ) -> dict[str, Any]:
        if payload.get("schema") != PORTFOLIO_SCHEMA:
            raise ValueError("unsupported account portfolio schema")
        if str(payload.get("platform") or "") != "wechat_official":
            raise ValueError("account portfolio platform must be wechat_official")
        observed_at = _iso_time(payload.get("observed_at"))
        articles = [_article(item) for item in (payload.get("articles") or []) if isinstance(item, dict)]
        articles = [item for item in articles if item is not None][:50]
        scorecard = _score_portfolio(articles, payload.get("data_gaps") or [])
        account_name = _text((payload.get("account") or {}).get("name"), 300)
        snapshot_id = "portfolio_" + hashlib.sha256(
            f"{user_id}\0{account_id}\0wechat_official\0{observed_at}".encode()
        ).hexdigest()[:28]
        now = _now()
        safe_portfolio = {
            "schema": PORTFOLIO_SCHEMA,
            "platform": "wechat_official",
            "account": {"name": account_name},
            "articles": [
                {
                    **{key: value for key, value in article.items() if key != "body_text"},
                    "body_excerpt": article["body_text"][:4_000],
                }
                for article in articles
            ],
            "collection": payload.get("collection") if isinstance(payload.get("collection"), dict) else {},
            "data_gaps": scorecard["data_gaps"],
        }
        with self._transaction() as db:
            db.execute(
                """INSERT INTO marketing_account_portfolio_snapshots
                (id,user_id,account_id,platform,observed_at,account_name,source_count,
                 portfolio_json,score_json,session_id,tool_call_id,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    account_name=excluded.account_name,source_count=excluded.source_count,
                    portfolio_json=excluded.portfolio_json,score_json=excluded.score_json,
                    session_id=excluded.session_id,tool_call_id=excluded.tool_call_id""",
                (
                    snapshot_id,
                    user_id,
                    account_id,
                    "wechat_official",
                    observed_at,
                    account_name,
                    len(articles),
                    json.dumps(safe_portfolio, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(scorecard, ensure_ascii=False, separators=(",", ":")),
                    session_id,
                    tool_call_id,
                    now,
                ),
            )
            evidence_ids = []
            for article in articles:
                evidence_id = self._capture_article(
                    db=db,
                    user_id=user_id,
                    account_id=account_id,
                    snapshot_id=snapshot_id,
                    observed_at=observed_at,
                    article=article,
                    session_id=session_id,
                    tool_call_id=tool_call_id,
                    now=now,
                )
                evidence_ids.append(evidence_id)
        return {
            "schema": PORTFOLIO_SCHEMA,
            "snapshot_id": snapshot_id,
            "account_id": account_id,
            "article_count": len(articles),
            "evidence_ids": evidence_ids,
            "scorecard": scorecard,
        }

    def _capture_article(
        self,
        *,
        db,
        user_id: str,
        account_id: str,
        snapshot_id: str,
        observed_at: str,
        article: dict[str, Any],
        session_id: str,
        tool_call_id: str,
        now: str,
    ) -> str:
        content = json.dumps(
            {
                "title": article["title"],
                "digest": article["digest"],
                "body_text": article["body_text"],
                "published_at": article["published_at"],
                "metrics": article["metrics"],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        evidence_id = "evidence_" + hashlib.sha256(
            f"{user_id}\0{account_id}\0owned_wechat_article\0{article['source_url']}\0{content_hash}".encode()
        ).hexdigest()[:28]
        observation_id = "owned_" + hashlib.sha256(
            f"{snapshot_id}\0{article['source_item_id']}".encode()
        ).hexdigest()[:28]
        db.execute(
            """INSERT INTO evidence_records
            (id,user_id,account_id,source_type,provider,canonical_url,title,excerpt,
             content_sha256,status,verification_level,captured_at,session_id,
             tool_call_id,metadata_json,created_at,updated_at)
            VALUES (?,?,?,'owned_content','marketing_browser_wechat_official',?,?,?,?,
                    'verified','account_browser_observation',?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,excerpt=excluded.excerpt,session_id=excluded.session_id,
                tool_call_id=excluded.tool_call_id,metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at""",
            (
                evidence_id,
                user_id,
                account_id,
                article["source_url"],
                article["title"],
                (article["body_text"] or article["digest"])[:4_000],
                content_hash,
                observed_at,
                session_id,
                tool_call_id,
                json.dumps(
                    {
                        "collector": "marketing_browser_mcp",
                        "portfolio_schema": PORTFOLIO_SCHEMA,
                        "owned_account_content": True,
                        "claim_truth_verified": False,
                        "verification_note": (
                            "Publication ownership and source integrity were observed in the authenticated "
                            "account browser; content quality and causal performance are not asserted."
                        ),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                now,
                now,
            ),
        )
        db.execute(
            """INSERT INTO marketing_owned_content_observations
            (id,snapshot_id,user_id,account_id,platform,source_item_id,source_url,evidence_id,
             title,digest,content_excerpt,published_at,metrics_json,features_json,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                evidence_id=excluded.evidence_id,title=excluded.title,digest=excluded.digest,
                content_excerpt=excluded.content_excerpt,published_at=excluded.published_at,
                metrics_json=excluded.metrics_json,features_json=excluded.features_json""",
            (
                observation_id,
                snapshot_id,
                user_id,
                account_id,
                "wechat_official",
                article["source_item_id"],
                article["source_url"],
                evidence_id,
                article["title"],
                article["digest"],
                article["body_text"][:8_000],
                article["published_at"],
                json.dumps(article["metrics"], ensure_ascii=False, separators=(",", ":")),
                json.dumps(
                    {
                        "character_count": article["character_count"],
                        "paragraph_count": article["paragraph_count"],
                        "image_count": article["image_count"],
                        "cover_available": bool(article["cover_url"]),
                        "metrics_provenance": article["metrics_provenance"],
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                now,
            ),
        )
        return evidence_id

    def latest(self, *, user_id: str, account_id: str) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                """SELECT * FROM marketing_account_portfolio_snapshots
                WHERE user_id=? AND account_id=?
                ORDER BY observed_at DESC,id DESC LIMIT 1""",
                (user_id, account_id),
            ).fetchone()
            if not row:
                return {
                    "account_id": account_id,
                    "status": "not_collected",
                    "next_action": "Call browser_collect_wechat_official_portfolio in this account session.",
                }
            observations = db.execute(
                """SELECT source_item_id,source_url,evidence_id,title,digest,content_excerpt,
                          published_at,metrics_json,features_json
                FROM marketing_owned_content_observations
                WHERE snapshot_id=? ORDER BY COALESCE(published_at,'') DESC,id""",
                (row["id"],),
            ).fetchall()
        return {
            "status": "ready",
            "snapshot_id": row["id"],
            "account_id": account_id,
            "platform": row["platform"],
            "observed_at": row["observed_at"],
            "account_name": row["account_name"],
            "source_count": row["source_count"],
            "scorecard": json.loads(row["score_json"] or "{}"),
            "articles": [
                {
                    "source_item_id": item["source_item_id"],
                    "source_url": item["source_url"],
                    "evidence_id": item["evidence_id"],
                    "title": item["title"],
                    "digest": item["digest"],
                    "content_excerpt": item["content_excerpt"],
                    "published_at": item["published_at"],
                    "metrics": json.loads(item["metrics_json"] or "{}"),
                    "features": json.loads(item["features_json"] or "{}"),
                }
                for item in observations
            ],
            "assessment_contract": (
                "Score verified execution only from observed articles. Separate observed facts, "
                "qualitative interpretation and recommendations; do not infer audience response when metrics are absent."
            ),
        }


def _article(raw: dict[str, Any]) -> dict[str, Any] | None:
    source_url = _canonical_wechat_url(raw.get("source_url"))
    source_item_id = _text(raw.get("source_item_id"), 300)
    if not source_url or not source_item_id:
        return None
    integer_metrics = {
        key: value
        for key in (
            "read_users",
            "share_users",
            "like_count",
            "recommend_count",
            "comment_count",
            "collection_users",
            "followers_gained",
            "avg_read_seconds",
            "listen_users",
            "listen_count",
        )
        if (value := _nonnegative_int((raw.get("metrics") or {}).get(key))) is not None
    }
    metrics = {
        **integer_metrics,
        **(
            {"completion_rate": completion_rate}
            if (
                completion_rate := _nonnegative_number(
                    (raw.get("metrics") or {}).get("completion_rate")
                )
            ) is not None
            and completion_rate <= 1
            else {}
        ),
    }
    provenance = raw.get("metrics_provenance") or {}
    body = _text(raw.get("body_text"), 20_000)
    return {
        "source_item_id": source_item_id,
        "source_url": source_url,
        "title": _text(raw.get("title"), 500),
        "digest": _text(raw.get("digest"), 2_000),
        "cover_url": _canonical_wechat_url(raw.get("cover_url")),
        "body_text": body,
        "published_at": _optional_iso_time(raw.get("published_at")),
        "metrics": metrics,
        "character_count": _nonnegative_int(raw.get("character_count")) or len(body),
        "paragraph_count": _nonnegative_int(raw.get("paragraph_count")) or 0,
        "image_count": _nonnegative_int(raw.get("image_count")) or 0,
        "metrics_provenance": {
            key: value
            for key, value in {
                "source": _text(provenance.get("source"), 100),
                "window": _text(provenance.get("window"), 100),
                "read_unit": _text(provenance.get("read_unit"), 100),
                "share_unit": _text(provenance.get("share_unit"), 100),
                "is_new_data": bool(provenance.get("is_new_data")),
            }.items()
            if value not in ("", None)
        },
    }


def _score_portfolio(articles: list[dict[str, Any]], inherited_gaps: list[Any]) -> dict[str, Any]:
    dimensions: dict[str, dict[str, Any]] = {}
    titles = [item["title"] for item in articles if item["title"]]
    if titles:
        title_scores = [100 if 10 <= len(title) <= 32 else 72 if 6 <= len(title) <= 45 else 45 for title in titles]
        uniqueness = len(set(titles)) / len(titles)
        dimensions["headline_execution"] = {
            "score": round(mean(title_scores) * (0.85 + 0.15 * uniqueness), 1),
            "basis": f"{len(titles)} observed titles; length and exact-title uniqueness only",
        }
    else:
        dimensions["headline_execution"] = {"score": None, "basis": "no observed titles"}
    bodies = [item for item in articles if item["body_text"]]
    if bodies:
        body_scores = []
        for item in bodies:
            characters = item["character_count"]
            length_score = 95 if 800 <= characters <= 5_000 else 78 if characters >= 400 else 50
            structure_bonus = min(5, item["image_count"] * 1.5 + item["paragraph_count"] * 0.1)
            body_scores.append(min(100, length_score + structure_bonus))
        dimensions["article_execution"] = {
            "score": round(mean(body_scores), 1),
            "basis": f"{len(bodies)} public bodies; length, paragraph and image structure only",
        }
    else:
        dimensions["article_execution"] = {"score": None, "basis": "public article bodies unavailable"}
    times = sorted(
        datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
        for item in articles
        if item["published_at"]
    )
    if len(times) >= 3:
        intervals = [(right - left).total_seconds() / 86_400 for left, right in zip(times, times[1:])]
        average = mean(intervals)
        variability = pstdev(intervals) / average if average else 1.0
        score = max(25.0, min(100.0, 100.0 - variability * 45.0 - max(0.0, median(intervals) - 21) * 1.2))
        dimensions["publishing_consistency"] = {
            "score": round(score, 1),
            "basis": f"{len(times)} timestamps; median interval {median(intervals):.1f} days",
        }
    else:
        dimensions["publishing_consistency"] = {
            "score": None,
            "basis": "at least 3 publication timestamps required",
        }
    metric_articles = [item for item in articles if item["metrics"]]
    dimensions["audience_response"] = {
        "score": None,
        "basis": (
            f"30-day content-analysis metrics observed for {len(metric_articles)} articles; "
            "read/share values are unique-user counts"
            if metric_articles
            else "30-day article content-analysis metrics unavailable"
        ),
    }
    available = [float(item["score"]) for item in dimensions.values() if item["score"] is not None]
    confidence = min(0.9, len(articles) / 10 * 0.65 + len(metric_articles) / max(1, len(articles)) * 0.2)
    gaps = {_text(value, 200) for value in inherited_gaps if _text(value, 200)}
    if len(articles) < 5:
        gaps.add("small_owned_content_sample")
    if len(times) < 3:
        gaps.add("publishing_cadence_sample_insufficient")
    if not metric_articles:
        gaps.add("audience_response_metrics_unavailable")
    return {
        "formula_version": "owned-account-execution-baseline-v1",
        "observed_execution_score": round(mean(available), 1) if available else None,
        "confidence": round(confidence, 2),
        "dimensions": dimensions,
        "data_gaps": sorted(gaps),
        "semantics": (
            "This is a transparent execution baseline from owned published work, not a universal content-quality "
            "score and not proof of what caused audience response. Agent interpretation must cite article evidence."
        ),
    }


def _canonical_wechat_url(value: Any) -> str:
    raw = _text(value, 4_000).replace("&amp;", "&")
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    if parts.scheme != "https" or parts.hostname != "mp.weixin.qq.com":
        return ""
    return urlunsplit(("https", "mp.weixin.qq.com", parts.path, parts.query, ""))


def _optional_iso_time(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or str(value).strip().isdigit():
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        return None


def _iso_time(value: Any) -> str:
    return _optional_iso_time(value) or _now()


def _nonnegative_int(value: Any) -> int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return int(number)


def _nonnegative_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _text(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
