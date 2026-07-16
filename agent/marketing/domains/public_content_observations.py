"""Evidence-backed public content natural experiments owned by Hermes."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.account_strategy import (
    BENCHMARK_DIMENSIONS,
    BENCHMARK_ROLES,
    MATCH_DIMENSIONS,
)
from agent.marketing.domains.browser_payloads import decode_schema_payload
from agent.marketing.domains.human_model import existence_ontology_contract
from agent.marketing.domains.storage import MarketingDomainRepository
from agent.marketing.intelligence.store import OperatingLoopRepository


PUBLIC_CONTENT_SCHEMA = "marketing_public_content_observation.v1"
PUBLIC_CONTENT_MODEL_VERSION = "public-content-natural-experiment-v0.2"
PUBLIC_PLATFORMS = {
    "bilibili",
    "douyin",
    "kuaishou",
    "tiktok",
    "wechat_channels",
    "wechat_official",
    "weibo",
    "xiaohongshu",
    "zhihu",
}
CONTENT_TYPES = {"article", "image_text", "text", "video", "unknown"}
STANCES = {
    "action_seeking",
    "experience_sharing",
    "off_target",
    "oppositional",
    "questioning",
    "skeptical",
    "supportive",
}
EXISTENCE_STRATEGIES = {"confirm", "continue", "expand", "preserve", "unknown"}
NEED_PROJECTIONS = {
    "physiological",
    "safety",
    "belonging",
    "esteem",
    "self_actualization",
    "transcendence",
    "unknown",
}
COGNITIVE_PROJECTIONS = {"Se", "Si", "Ne", "Ni", "Te", "Ti", "Fe", "Fi", "unknown"}
METRIC_KEYS = {
    "comments",
    "danmaku",
    "favorites",
    "likes",
    "reposts",
    "shares",
    "views",
}
_FORBIDDEN_REACTION_KEYS = {
    "comment_texts",
    "comments",
    "handles",
    "nicknames",
    "profiles",
    "raw_comments",
    "user_ids",
    "users",
}
_IDENTITY_PATTERN = re.compile(
    r"(?:https?://|www\.|@[A-Za-z0-9_.-]{2,}|(?:微信|wechat|vx|v信|邮箱|email|电话|手机)\s*[:：]?\s*[A-Za-z0-9_.@+-]{5,})",
    re.IGNORECASE,
)


def decode_browser_public_content_result(result: Any) -> dict[str, Any] | None:
    return decode_schema_payload(result, PUBLIC_CONTENT_SCHEMA)


class PublicContentObservationRepository(MarketingDomainRepository):
    """Persist public posts and delayed feedback as account-scoped time series."""

    def capture_browser_result(
        self,
        *,
        user_id: str,
        account_id: str,
        payload: dict[str, Any],
        session_id: str,
        tool_call_id: str = "",
    ) -> dict[str, Any]:
        if payload.get("schema") != PUBLIC_CONTENT_SCHEMA:
            raise ValueError("unsupported public content observation schema")
        platform = _platform(payload.get("platform"))
        observed_at = _iso_time(payload.get("observed_at"))
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValueError("public content items must be a list")
        captured = []
        for raw in items[:100]:
            if isinstance(raw, dict):
                item = self._capture_item(
                    user_id=user_id,
                    account_id=account_id,
                    platform=platform,
                    observed_at=observed_at,
                    raw=raw,
                    session_id=session_id,
                    tool_call_id=tool_call_id,
                )
                if item:
                    captured.append(item)
        return {
            "schema": PUBLIC_CONTENT_SCHEMA,
            "platform": platform,
            "observed_at": observed_at,
            "captured": captured,
            "total": len(captured),
            "semantics": (
                "Each row is a time-bounded public observation, not proof that a content "
                "feature caused the observed feedback."
            ),
        }

    def _capture_item(
        self,
        *,
        user_id: str,
        account_id: str,
        platform: str,
        observed_at: str,
        raw: dict[str, Any],
        session_id: str,
        tool_call_id: str,
    ) -> dict[str, Any] | None:
        source_item_id = _text(raw.get("source_item_id"), limit=300)
        source_url = _canonical_url(raw.get("source_url"))
        if not source_item_id or not source_url:
            return None
        feedback = raw.get("feedback") or {}
        if not isinstance(feedback, dict):
            raise ValueError("public content feedback must be an object")
        leaked = sorted(_FORBIDDEN_REACTION_KEYS & set(feedback))
        if leaked:
            raise ValueError("public capture cannot persist raw commenter data: " + ", ".join(leaked))
        creator = _creator(raw.get("creator"))
        content = _content(raw.get("content"))
        published_at = _optional_iso_time(raw.get("published_at") or content.get("published_at"))
        metrics = _metrics(feedback.get("metrics") or feedback)
        rank = _nonnegative_int(raw.get("rank"))
        canonical = {
            "platform": platform,
            "source_item_id": source_item_id,
            "source_url": source_url,
            "creator": creator,
            "content": content,
            "published_at": published_at,
            "feedback": {
                "metrics": metrics,
                "visible_comment_count": _nonnegative_int(
                    feedback.get("visible_comment_count")
                ),
            },
            "rank": rank,
            "observed_at": observed_at,
        }
        encoded = _json(canonical)
        content_hash = hashlib.sha256(encoded.encode()).hexdigest()
        case_id = "publiccase_" + hashlib.sha256(
            f"{user_id}\0{account_id}\0{platform}\0{source_item_id}".encode()
        ).hexdigest()[:28]
        evidence_id = "evidence_" + hashlib.sha256(
            f"{user_id}\0{account_id}\0public_content\0{source_url}\0{content_hash}".encode()
        ).hexdigest()[:28]
        observation_id = "publicobs_" + hashlib.sha256(
            f"{case_id}\0{observed_at}".encode()
        ).hexdigest()[:28]
        now = _now()
        with self._transaction() as db:
            db.execute(
                """INSERT INTO evidence_records
                (id,user_id,account_id,source_type,provider,canonical_url,title,excerpt,
                 content_sha256,status,verification_level,captured_at,session_id,
                 tool_call_id,metadata_json,created_at,updated_at)
                VALUES (?,?,?,'public_content',?,?,?,?,?,'verified','browser_observation',?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at""",
                (
                    evidence_id,
                    user_id,
                    account_id,
                    "marketing_browser_public_content",
                    source_url,
                    content.get("title") or content.get("caption") or "",
                    encoded[:12_000],
                    content_hash,
                    observed_at,
                    session_id,
                    tool_call_id,
                    _json(
                        {
                            "collector": "marketing_browser_mcp",
                            "schema": PUBLIC_CONTENT_SCHEMA,
                            "claim_truth_verified": False,
                            "counter_note": "Public counters can change and may be incomplete.",
                        }
                    ),
                    now,
                    now,
                ),
            )
            db.execute(
                """INSERT INTO marketing_public_content_cases
                (id,user_id,account_id,platform,source_item_id,source_url,creator_json,
                 first_content_json,latest_content_json,published_at,first_seen_at,last_seen_at,
                 created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(user_id,account_id,platform,source_item_id) DO UPDATE SET
                    source_url=excluded.source_url,creator_json=excluded.creator_json,
                    latest_content_json=excluded.latest_content_json,
                    published_at=COALESCE(marketing_public_content_cases.published_at,excluded.published_at),
                    last_seen_at=MAX(marketing_public_content_cases.last_seen_at,excluded.last_seen_at),
                    updated_at=excluded.updated_at""",
                (
                    case_id,
                    user_id,
                    account_id,
                    platform,
                    source_item_id,
                    source_url,
                    _json(creator),
                    _json(content),
                    _json(content),
                    published_at,
                    observed_at,
                    observed_at,
                    now,
                    now,
                ),
            )
            db.execute(
                """INSERT INTO marketing_public_feedback_observations
                (id,case_id,user_id,account_id,platform,evidence_id,observed_at,
                 content_json,metrics_json,rank,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(case_id,observed_at) DO UPDATE SET
                    evidence_id=excluded.evidence_id,content_json=excluded.content_json,
                    metrics_json=excluded.metrics_json,rank=excluded.rank""",
                (
                    observation_id,
                    case_id,
                    user_id,
                    account_id,
                    platform,
                    evidence_id,
                    observed_at,
                    _json(content),
                    _json(metrics),
                    rank,
                    now,
                ),
            )
        return {
            "case_id": case_id,
            "observation_id": observation_id,
            "evidence_id": evidence_id,
            "source_item_id": source_item_id,
        }

    def list_cases(
        self,
        *,
        user_id: str,
        account_id: str,
        platform: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        query = """SELECT c.*,COUNT(o.id) AS observation_count
                   FROM marketing_public_content_cases c
                   LEFT JOIN marketing_public_feedback_observations o ON o.case_id=c.id
                   WHERE c.user_id=? AND c.account_id=?"""
        params: list[Any] = [user_id, account_id]
        if platform:
            query += " AND c.platform=?"
            params.append(_platform(platform))
        query += " GROUP BY c.id ORDER BY c.last_seen_at DESC,c.id DESC LIMIT ?"
        params.append(max(1, min(int(limit), 200)))
        with self._connection() as db:
            rows = db.execute(query, params).fetchall()
        return [_case_record(row) for row in rows]

    def get_observation(
        self, *, user_id: str, account_id: str, observation_id: str
    ) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                """SELECT o.*,c.source_item_id,c.source_url,c.creator_json,c.published_at
                FROM marketing_public_feedback_observations o
                JOIN marketing_public_content_cases c ON c.id=o.case_id
                WHERE o.id=? AND o.user_id=? AND o.account_id=?""",
                (observation_id, user_id, account_id),
            ).fetchone()
        if row is None:
            raise KeyError("public content observation not found in account scope")
        return _observation_record(row)

    def interpret_observation(
        self,
        *,
        user_id: str,
        account_id: str,
        observation_id: str,
        model_observation: dict[str, Any],
        confidence: float,
        project_id: str = "",
        benchmark_id: str = "",
        benchmark_projection: dict[str, Any] | None = None,
        session_id: str = "",
    ) -> dict[str, Any]:
        observation = self.get_observation(
            user_id=user_id, account_id=account_id, observation_id=observation_id
        )
        model = _model_observation(model_observation)
        bounded_confidence = _confidence(confidence, maximum=0.7)
        projection = None
        if project_id or benchmark_id or benchmark_projection:
            if not project_id or not benchmark_projection:
                raise ValueError(
                    "project_id and benchmark_projection are required for benchmark learning"
                )
            projection = _benchmark_projection(benchmark_projection)
        delta = self._metric_delta(
            user_id=user_id,
            account_id=account_id,
            case_id=observation["case_id"],
            observation_id=observation_id,
            observed_at=observation["observed_at"],
            metrics=observation["metrics"],
        )
        loop = OperatingLoopRepository(self.paths)
        receipt = loop.create_receipt(
            source_kind=f"public_content:{observation['platform']}",
            source_id=observation_id,
            receipt_type="public_content_natural_experiment",
            user_id=user_id,
            account_id=account_id,
            platform=observation["platform"],
            session_id=session_id,
            summary={
                "version": PUBLIC_CONTENT_MODEL_VERSION,
                "case_id": observation["case_id"],
                "observation_id": observation_id,
                "content": observation["content"],
                "metrics": observation["metrics"],
                "metric_delta": delta,
                "model_observation": model,
                "causal_warning": (
                    "Observed association only. Distribution, creator history, paid traffic, "
                    "timing and platform allocation remain possible confounders."
                ),
            },
        )
        common_proposal = {
            "kind": "public_content_natural_experiment",
            "version": PUBLIC_CONTENT_MODEL_VERSION,
            "case_id": observation["case_id"],
            "observation_id": observation_id,
            "public_creator": observation["creator"],
            "content": observation["content"],
            "observed_outcome": {
                "metrics": observation["metrics"],
                "metric_delta": delta,
            },
            "model_observation": model,
            "guardrail": (
                "Correlation only; compare repeated posts and delayed snapshots before generalizing."
            ),
        }
        model_candidate = loop.create_learning_candidate(
            source_key=f"public-content-model:{observation_id}:{_digest(model)}",
            candidate_type="memory",
            user_id=user_id,
            account_id=account_id,
            platform=observation["platform"],
            receipt_refs=[receipt["id"]],
            evidence_refs=[observation["evidence_id"]],
            proposal=common_proposal,
            confidence=bounded_confidence,
        )
        strategy_candidate = None
        if projection is not None:
            proposal = {
                **common_proposal,
                "kind": (
                    "public_benchmark_observation"
                    if benchmark_id
                    else "public_benchmark_account_candidate"
                ),
                "project_id": project_id,
                "benchmark_id": benchmark_id,
                "benchmark_projection": projection,
                "public_source": {
                    "platform": observation["platform"],
                    "source_item_id": observation["source_item_id"],
                    "source_url": observation["source_url"],
                    "creator": observation["creator"],
                },
            }
            strategy_candidate = loop.create_learning_candidate(
                source_key=f"public-benchmark:{project_id}:{benchmark_id}:{observation_id}:{_digest(projection)}",
                candidate_type="strategy",
                user_id=user_id,
                account_id=account_id,
                platform=observation["platform"],
                receipt_refs=[receipt["id"]],
                evidence_refs=[observation["evidence_id"]],
                proposal=proposal,
                confidence=bounded_confidence,
            )
        return {
            "receipt": receipt,
            "model_candidate": model_candidate,
            "strategy_candidate": strategy_candidate,
        }

    def _metric_delta(
        self,
        *,
        user_id: str,
        account_id: str,
        case_id: str,
        observation_id: str,
        observed_at: str,
        metrics: dict[str, int | float],
    ) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                """SELECT id,observed_at,metrics_json
                FROM marketing_public_feedback_observations
                WHERE case_id=? AND user_id=? AND account_id=? AND id!=? AND observed_at<?
                ORDER BY observed_at DESC,id DESC LIMIT 1""",
                (case_id, user_id, account_id, observation_id, observed_at),
            ).fetchone()
        if row is None:
            return {"status": "baseline_only", "previous_observation_id": None, "metrics": {}}
        previous = json.loads(row["metrics_json"] or "{}")
        deltas = {
            key: value - previous[key]
            for key, value in metrics.items()
            if key in previous
        }
        elapsed_hours = max(
            0.0,
            (
                datetime.fromisoformat(observed_at)
                - datetime.fromisoformat(row["observed_at"])
            ).total_seconds()
            / 3600,
        )
        return {
            "status": "compared",
            "previous_observation_id": row["id"],
            "elapsed_hours": round(elapsed_hours, 3),
            "metrics": deltas,
            "counter_decreases": sorted(key for key, value in deltas.items() if value < 0),
            "counter_note": (
                "Negative deltas are retained as platform corrections or scope changes, not hidden."
            ),
        }


def _model_observation(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("model_observation must be an object")
    leaked = sorted(_FORBIDDEN_REACTION_KEYS & set(value))
    if leaked:
        raise ValueError("model observation cannot contain raw commenter data: " + ", ".join(leaked))
    features = _bounded_structure(value.get("content_features") or {}, field="content_features")
    if not features:
        raise ValueError("content_features requires at least one observed feature")
    audience = _bounded_structure(value.get("audience") or {}, field="audience")
    reaction = _reaction(value.get("reaction") or {})
    disconfirming = _strings(
        value.get("disconfirming_signals"),
        field="disconfirming_signals",
        maximum=12,
        required=True,
    )
    data_gaps = _strings(
        value.get("data_gaps"), field="data_gaps", maximum=20, required=True
    )
    _reject_identity([*disconfirming, *data_gaps], field="model_observation")
    return {
        "existence_ontology": existence_ontology_contract(),
        "mechanism_chain": [
            "need_projection",
            "cognitive_projection",
            "existence_strategy",
            "observable_reaction",
        ],
        "content_features": features,
        "audience": audience,
        "reaction": reaction,
        "disconfirming_signals": disconfirming,
        "data_gaps": data_gaps,
    }


def _reaction(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("reaction must be an object")
    leaked = sorted(_FORBIDDEN_REACTION_KEYS & set(value))
    if leaked:
        raise ValueError("reaction must contain anonymous clusters only: " + ", ".join(leaked))
    sample_size = value.get("sample_size")
    if isinstance(sample_size, bool) or not isinstance(sample_size, int) or sample_size < 0:
        raise ValueError("reaction.sample_size must be a non-negative integer")
    clusters = []
    for raw in value.get("clusters") or []:
        if not isinstance(raw, dict):
            raise ValueError("reaction clusters must be objects")
        stance = _enum(raw.get("stance"), STANCES, field="stance")
        need_projection = _enum(
            raw.get("need_projection") or "unknown",
            NEED_PROJECTIONS,
            field="need_projection",
        )
        cognitive_projection = _cognitive_projection(raw.get("cognitive_projection"))
        existence_strategy = _enum(
            raw.get("existence_strategy") or raw.get("existence_direction") or "unknown",
            EXISTENCE_STRATEGIES,
            field="existence_strategy",
        )
        cohort = _text(raw.get("cohort"), field="cohort", limit=200, required=True)
        themes = _strings(raw.get("themes"), field="themes", maximum=8, required=True)
        count = raw.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("reaction cluster count must be a non-negative integer")
        _reject_identity([cohort, *themes], field="reaction cluster")
        clusters.append(
            {
                "cohort": cohort,
                "stance": stance,
                "need_projection": need_projection,
                "cognitive_projection": cognitive_projection,
                "existence_strategy": existence_strategy,
                "themes": themes,
                "count": count,
            }
        )
    if len(clusters) > 12:
        raise ValueError("reaction clusters exceed 12 items")
    questions = _strings(value.get("question_patterns"), field="question_patterns", maximum=12)
    objections = _strings(value.get("objection_patterns"), field="objection_patterns", maximum=12)
    _reject_identity([*questions, *objections], field="reaction patterns")
    return {
        "aggregation": "anonymous_clusters_only",
        "sample_size": sample_size,
        "clusters": clusters,
        "question_patterns": questions,
        "objection_patterns": objections,
    }


def _benchmark_projection(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("benchmark_projection must be an object")
    role = _enum(value.get("suggested_role"), BENCHMARK_ROLES, field="suggested_role")
    dimensions = value.get("match_dimensions")
    if not isinstance(dimensions, dict) or len(dimensions) < 3:
        raise ValueError("benchmark projection requires at least three match dimensions")
    normalized_dimensions = {
        key: _confidence(raw)
        for key, raw in dimensions.items()
        if key in MATCH_DIMENSIONS
    }
    if len(normalized_dimensions) < 3 or len(normalized_dimensions) != len(dimensions):
        raise ValueError("benchmark projection contains unsupported match dimensions")
    observations = value.get("observation_dimensions")
    if not isinstance(observations, dict) or not observations:
        raise ValueError("benchmark projection requires observation_dimensions")
    normalized_observations = {}
    for key, raw in observations.items():
        if key not in BENCHMARK_DIMENSIONS:
            raise ValueError(f"unsupported benchmark observation dimension: {key}")
        normalized_observations[key] = _bounded_structure(raw, field=f"observation.{key}")
    reason = _text(
        value.get("selection_reason"), field="selection_reason", limit=1_000, required=True
    )
    disconfirming = _strings(
        value.get("disconfirming_signals"),
        field="benchmark.disconfirming_signals",
        maximum=12,
        required=True,
    )
    return {
        "suggested_role": role,
        "selection_reason": reason,
        "match_dimensions": normalized_dimensions,
        "observation_dimensions": normalized_observations,
        "disconfirming_signals": disconfirming,
    }


def _creator(value: Any) -> dict[str, str]:
    raw = value if isinstance(value, dict) else {}
    return {
        "platform_account_id": _text(raw.get("platform_account_id"), limit=300),
        "handle": _text(raw.get("handle"), limit=200),
        "name": _text(raw.get("name"), limit=300),
        "profile_url": _canonical_url(raw.get("profile_url")),
    }


def _content(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    content_type = str(raw.get("content_type") or "unknown").strip().lower()
    if content_type not in CONTENT_TYPES:
        content_type = "unknown"
    return {
        "content_type": content_type,
        "title": _text(raw.get("title"), limit=1_000),
        "caption": _text(raw.get("caption"), limit=4_000),
        "body_excerpt": _text(raw.get("body_excerpt"), limit=8_000),
        "duration_ms": _nonnegative_int(raw.get("duration_ms")),
        "hashtags": _strings(raw.get("hashtags"), field="hashtags", maximum=30),
        "sound_id": _text(raw.get("sound_id"), limit=300),
    }


def _metrics(value: Any) -> dict[str, int | float]:
    if not isinstance(value, dict):
        return {}
    result = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key or "").strip().lower().removesuffix("_count")
        if key not in METRIC_KEYS:
            continue
        number = _number(raw_value)
        if number is not None and number >= 0:
            result[key] = number
    return result


def _bounded_structure(value: Any, *, field: str, depth: int = 0) -> Any:
    if depth > 4:
        raise ValueError(f"{field} exceeds maximum depth")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ValueError(f"{field} contains a non-finite number")
        return value
    if isinstance(value, str):
        text = " ".join(value.split())[:1_000]
        _reject_identity([text], field=field)
        return text
    if isinstance(value, list):
        if len(value) > 30:
            raise ValueError(f"{field} contains too many items")
        return [
            _bounded_structure(item, field=f"{field}[]", depth=depth + 1)
            for item in value
        ]
    if isinstance(value, dict):
        if len(value) > 40:
            raise ValueError(f"{field} contains too many fields")
        leaked = sorted(_FORBIDDEN_REACTION_KEYS & set(value))
        if leaked:
            raise ValueError(f"{field} contains raw commenter data: {', '.join(leaked)}")
        return {
            str(key)[:80]: _bounded_structure(
                item, field=f"{field}.{key}", depth=depth + 1
            )
            for key, item in value.items()
        }
    raise ValueError(f"{field} contains an unsupported value")


def _case_record(row) -> dict[str, Any]:
    value = dict(row)
    value["creator"] = json.loads(value.pop("creator_json") or "{}")
    value["first_content"] = json.loads(value.pop("first_content_json") or "{}")
    value["latest_content"] = json.loads(value.pop("latest_content_json") or "{}")
    return value


def _observation_record(row) -> dict[str, Any]:
    value = dict(row)
    value["content"] = json.loads(value.pop("content_json") or "{}")
    value["metrics"] = json.loads(value.pop("metrics_json") or "{}")
    value["creator"] = json.loads(value.pop("creator_json") or "{}")
    return value


def _platform(value: Any) -> str:
    platform = str(value or "").strip().lower()
    if platform not in PUBLIC_PLATFORMS:
        raise ValueError(f"unsupported public content platform: {platform or '<empty>'}")
    return platform


def _canonical_url(value: Any) -> str:
    text = _text(value, limit=2_000)
    try:
        parsed = urlsplit(text)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    if parsed.username or parsed.password:
        return ""
    query = ""
    if parsed.hostname.lower() == "mp.weixin.qq.com":
        identity_keys = {"__biz", "mid", "idx", "sn"}
        query = urlencode(
            [(key, item) for key, item in parse_qsl(parsed.query) if key in identity_keys]
        )
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", query, "")
    )


def _text(value: Any, *, field: str = "value", limit: int, required: bool = False) -> str:
    text = " ".join(str(value or "").split())[:limit]
    if required and not text:
        raise ValueError(f"{field} is required")
    return text


def _strings(
    value: Any, *, field: str, maximum: int, required: bool = False
) -> list[str]:
    if value is None:
        items = []
    elif isinstance(value, list):
        items = list(dict.fromkeys(_text(item, limit=500) for item in value if _text(item, limit=500)))
    else:
        raise ValueError(f"{field} must be a list")
    if required and not items:
        raise ValueError(f"{field} is required")
    if len(items) > maximum:
        raise ValueError(f"{field} exceeds {maximum} items")
    return items


def _enum(value: Any, allowed: set[str], *, field: str) -> str:
    text = str(value or "").strip().lower()
    if text not in allowed:
        raise ValueError(f"unsupported {field}: {text or '<empty>'}")
    return text


def _cognitive_projection(value: Any) -> str:
    text = str(value or "unknown").strip()
    canonical = {item.lower(): item for item in COGNITIVE_PROJECTIONS}.get(text.lower())
    if canonical is None:
        raise ValueError(f"unsupported cognitive_projection: {text or '<empty>'}")
    return canonical


def _confidence(value: Any, *, maximum: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence must be a number") from exc
    if not math.isfinite(number) or not 0 <= number <= maximum:
        raise ValueError(f"confidence must be between 0 and {maximum}")
    return number


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.replace(",", "").strip())
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def _nonnegative_int(value: Any) -> int | None:
    number = _number(value)
    if number is None or number < 0:
        return None
    return int(number)


def _iso_time(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return _now()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid observed_at") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _optional_iso_time(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        epoch = float(text)
        if epoch > 10_000_000_000:
            epoch /= 1_000
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
    return _iso_time(text)


def _reject_identity(values: list[str], *, field: str) -> None:
    if any(_IDENTITY_PATTERN.search(value) for value in values):
        raise ValueError(f"{field} cannot contain handles, contact details, or URLs")


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()[:16]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
