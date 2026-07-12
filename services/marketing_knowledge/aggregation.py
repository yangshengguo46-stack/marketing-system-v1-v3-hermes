"""Privacy-thresholded aggregation for the central Marketing OS knowledge service."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from marketing_knowledge_protocol import (
    CONTRIBUTION_PROTOCOL,
    PACK_PROTOCOL,
    canonical_json,
    pack_checksum,
    unsigned_pack,
)


_FORBIDDEN_FIELD = re.compile(
    r"(?:account.?id|user.?id|username|cookie|token|password|secret|"
    r"(?:^|_)url$|raw.?content|raw.?text|message|email|phone)",
    re.IGNORECASE,
)
_PHONE_LIKE = re.compile(r"(?:\+?\d[\s-]?){7,}")
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")
_CONTRIBUTION_REF = re.compile(r"^contrib_[A-Za-z0-9_-]{4,128}$")


class KnowledgeAggregator:
    """Build signed priors only when a cohort clears privacy thresholds."""

    def __init__(
        self,
        *,
        signing_key: Ed25519PrivateKey,
        key_id: str,
        min_cohort_size: int = 20,
        min_category_size: int = 5,
        half_life_days: float = 30.0,
    ):
        if min_cohort_size < 2 or min_category_size < 2:
            raise ValueError("privacy thresholds are too small")
        self.signing_key = signing_key
        self.key_id = str(key_id or "").strip()
        if not self.key_id:
            raise ValueError("key_id is required")
        self.min_cohort_size = int(min_cohort_size)
        self.min_category_size = int(min_category_size)
        self.half_life_days = max(1.0, float(half_life_days))

    def build_packs(
        self,
        contributions: Iterable[dict[str, Any]],
        *,
        version: str,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        unique: dict[str, dict[str, Any]] = {}
        for raw in contributions:
            contribution = validate_contribution(raw)
            unique[contribution["contribution_ref"]] = contribution
        cohorts: dict[bytes, list[dict[str, Any]]] = defaultdict(list)
        for contribution in unique.values():
            cohort_key = canonical_json(
                {
                    "schema_version": contribution["schema_version"],
                    "cohort": contribution["cohort"],
                }
            )
            cohorts[cohort_key].append(contribution)
        packs: list[dict[str, Any]] = []
        for cohort_key, rows in cohorts.items():
            if len(rows) < self.min_cohort_size:
                continue
            descriptor = json.loads(cohort_key)
            observed = [_parse_time(row["observed_at"]) for row in rows]
            weights = [_time_weight(current, timestamp, self.half_life_days) for timestamp in observed]
            payload = {
                "cohort": descriptor["cohort"],
                "features": _aggregate_object(
                    [row["features"] for row in rows],
                    weights,
                    min_category_size=self.min_category_size,
                ),
                "outcomes": _aggregate_object(
                    [row["outcomes"] for row in rows],
                    weights,
                    min_category_size=self.min_category_size,
                ),
                "decay": {"half_life_days": self.half_life_days},
                "privacy": {
                    "min_cohort_size": self.min_cohort_size,
                    "min_category_size": self.min_category_size,
                    "sparse_values_suppressed": True,
                },
            }
            platform = str(descriptor["cohort"].get("platform") or "unknown")
            region = str(descriptor["cohort"].get("region") or "")
            knowledge_type = str(descriptor["cohort"].get("knowledge_type") or "content_prior")
            fingerprint = hashlib.sha256(cohort_key).hexdigest()[:20]
            pack = {
                "protocol": PACK_PROTOCOL,
                "id": f"knowledge_{fingerprint}_{version}",
                "version": str(version),
                "knowledge_type": knowledge_type,
                "platform": platform,
                "region": region,
                "schema_version": descriptor["schema_version"],
                "window_start": min(observed).isoformat(),
                "window_end": max(observed).isoformat(),
                "sample_size": len(rows),
                "min_cohort_size": self.min_cohort_size,
                "generated_at": current.isoformat(),
                "payload": payload,
            }
            pack["checksum"] = pack_checksum(pack)
            signature = self.signing_key.sign(canonical_json(unsigned_pack(pack)))
            pack["signature"] = f"{self.key_id}:{base64.b64encode(signature).decode('ascii')}"
            packs.append(pack)
        return sorted(packs, key=lambda item: item["id"])


def validate_contribution(value: Any) -> dict[str, Any]:
    """Validate the untrusted anonymous wire envelope at the service edge."""

    if not isinstance(value, dict) or value.get("protocol") != CONTRIBUTION_PROTOCOL:
        raise ValueError("unsupported contribution protocol")
    allowed = {
        "protocol",
        "contribution_ref",
        "schema_version",
        "cohort",
        "features",
        "outcomes",
        "observed_at",
    }
    extra = set(value) - allowed
    if extra:
        raise ValueError("central contribution contains forbidden fields")
    result = {key: value.get(key) for key in allowed}
    if not _CONTRIBUTION_REF.fullmatch(str(result["contribution_ref"] or "")):
        raise ValueError("invalid anonymous contribution reference")
    if not _SAFE_IDENTIFIER.fullmatch(str(result["schema_version"] or "")):
        raise ValueError("invalid anonymous contribution schema version")
    for key in ("cohort", "features", "outcomes"):
        if not isinstance(result[key], dict):
            raise ValueError(f"{key} must be an object")
        result[key] = _validate_aggregate_value(result[key], path=key)
    platform = str(result["cohort"].get("platform") or "")
    if not _SAFE_IDENTIFIER.fullmatch(platform):
        raise ValueError("anonymous contribution cohort requires a safe platform")
    _parse_time(result["observed_at"])
    return result


def _validate_aggregate_value(value: Any, *, path: str, depth: int = 0) -> Any:
    if depth > 6:
        raise ValueError(f"anonymous aggregate at {path} is too deeply nested")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ValueError(f"anonymous aggregate at {path} is not finite")
        return value
    if isinstance(value, str):
        text = value.strip()
        if len(text) > 64:
            raise ValueError(f"anonymous aggregate at {path} is too specific")
        if "://" in text or "@" in text or _PHONE_LIKE.search(text):
            raise ValueError(f"anonymous aggregate at {path} resembles identifying data")
        return text
    if isinstance(value, list):
        if len(value) > 32:
            raise ValueError(f"anonymous aggregate list at {path} is too large")
        return [
            _validate_aggregate_value(item, path=f"{path}[]", depth=depth + 1)
            for item in value
        ]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key or "").strip()
            if not key or len(key) > 64 or _FORBIDDEN_FIELD.search(key):
                raise ValueError(f"anonymous contribution contains forbidden field: {key or '<empty>'}")
            result[key] = _validate_aggregate_value(
                item,
                path=f"{path}.{key}",
                depth=depth + 1,
            )
        return result
    raise ValueError(f"unsupported anonymous aggregate value at {path}")


def _aggregate_object(
    values: list[dict[str, Any]], weights: list[float], *, min_category_size: int
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    keys = sorted(set().union(*(value.keys() for value in values)))
    for key in keys:
        samples = [(value[key], weight) for value, weight in zip(values, weights) if key in value]
        if len(samples) < min_category_size:
            continue
        raw_values = [sample[0] for sample in samples]
        if all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in raw_values):
            total_weight = sum(weight for _, weight in samples)
            result[key] = {
                "kind": "numeric",
                "weighted_mean": round(sum(float(item) * weight for item, weight in samples) / total_weight, 6),
                "min": min(raw_values),
                "max": max(raw_values),
                "sample_size": len(samples),
            }
            continue
        counts: dict[str, tuple[int, float]] = {}
        for item, weight in samples:
            label = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            count, total = counts.get(label, (0, 0.0))
            counts[label] = (count + 1, total + weight)
        visible = {
            label: {"count": count, "weight": round(weight, 6)}
            for label, (count, weight) in counts.items()
            if count >= min_category_size
        }
        if visible:
            result[key] = {"kind": "categorical", "values": visible, "sample_size": len(samples)}
    return result


def _parse_time(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid contribution observed_at") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _time_weight(now: datetime, observed_at: datetime, half_life_days: float) -> float:
    age_days = max(0.0, (now - observed_at).total_seconds() / 86_400)
    return math.exp(-math.log(2) * age_days / half_life_days)
