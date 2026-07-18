"""Licensed material discovery and selection owned by Hermes state."""

from __future__ import annotations

import json
import math
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.media_assets import MediaAssetRepository
from agent.marketing.domains.storage import MarketingDomainRepository
from agent.marketing.providers.materials import (
    ensure_default_material_providers,
    get_material_provider,
    list_material_providers,
)


_ROLES = {"scene", "broll", "prop", "storyboard", "other"}
_ORIENTATIONS = {"", "landscape", "portrait", "square"}
_MEDIA_TYPES = {"either", "image", "video"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _candidate_record(row) -> dict[str, Any]:
    value = dict(row)
    value["score_breakdown"] = json.loads(value.pop("score_json") or "{}")
    value["metadata"] = json.loads(value.pop("metadata_json") or "{}")
    # Download URLs are provider execution details, not presentation data.
    value.pop("download_url", None)
    return value


class MaterialSourcingRepository(MarketingDomainRepository):
    """Normalize provider results and materialize only rights-reviewed binaries."""

    def __init__(self, paths: MarketingDataPaths | None = None) -> None:
        super().__init__(paths)
        self.media = MediaAssetRepository(self.paths)

    def search(
        self,
        *,
        user_id: str,
        account_id: str,
        query: str,
        role: str = "broll",
        orientation: str = "",
        media_type: str = "either",
        target_duration: float = 0,
        limit: int = 12,
        locale: str = "zh-CN",
        request_ref: str = "",
    ) -> dict[str, Any]:
        user_id = self._required(user_id, "user_id")
        account_id = self._required(account_id, "account_id")
        query = self._required(query, "query", limit=300)
        role = str(role or "broll").strip().lower()
        if role not in _ROLES:
            raise ValueError("unsupported material role")
        orientation = str(orientation or "").strip().lower()
        if orientation not in _ORIENTATIONS:
            raise ValueError("unsupported material orientation")
        media_type = str(media_type or "either").strip().lower()
        if media_type not in _MEDIA_TYPES:
            raise ValueError("unsupported material media type")
        safe_limit = max(1, min(int(limit), 40))
        duration = max(0.0, min(float(target_duration or 0), 600.0))
        request_ref = str(request_ref or "").strip()
        if len(request_ref) > 240:
            raise ValueError("request_ref must not exceed 240 characters")
        search_id = f"material_search_{uuid.uuid4().hex}"
        request = {
            "query": query,
            "role": role,
            "orientation": orientation,
            "media_type": media_type,
            "target_duration": round(duration, 3),
            "limit": safe_limit,
            "locale": str(locale or "zh-CN")[:20],
            "request_ref": request_ref or None,
        }
        if request_ref:
            with self._connection() as db:
                existing = db.execute(
                    """SELECT id FROM material_searches
                    WHERE user_id=? AND account_id=?
                      AND json_extract(query_json,'$.request_ref')=?
                    ORDER BY created_at ASC LIMIT 1""",
                    (user_id, account_id, request_ref),
                ).fetchone()
            if existing is not None:
                return self.get_search(
                    search_id=existing["id"],
                    user_id=user_id,
                    account_id=account_id,
                )
        now = _now()
        with self._transaction() as db:
            db.execute(
                """INSERT INTO material_searches
                (id,user_id,account_id,query_json,status,provider_errors_json,created_at,updated_at)
                VALUES (?,?,?,?,?,'{}',?,?)""",
                (search_id, user_id, account_id, _json(request), "running", now, now),
            )

        candidates = self._local_candidates(
            user_id=user_id,
            account_id=account_id,
            request=request,
        )
        provider_errors: dict[str, str] = {}
        ensure_default_material_providers()
        for provider in list_material_providers():
            try:
                results = provider.search(request)
            except Exception as exc:
                provider_errors[provider.name] = f"{type(exc).__name__}: {exc}"[:500]
                continue
            for candidate in results:
                try:
                    normalized = self._normalize_provider_candidate(
                        candidate, role=role
                    )
                except ValueError as exc:
                    provider_errors[provider.name] = f"invalid candidate: {exc}"[:500]
                    continue
                if media_type != "either" and normalized["media_type"] != media_type:
                    continue
                normalized["score_breakdown"] = self._score(normalized, request)
                normalized["score"] = round(
                    sum(normalized["score_breakdown"].values()), 4
                )
                candidates.append(normalized)

        candidates.sort(key=lambda item: (-float(item["score"]), item["provider"]))
        candidates = candidates[:safe_limit]
        with self._transaction() as db:
            for candidate in candidates:
                candidate_id = f"material_candidate_{uuid.uuid4().hex}"
                candidate["id"] = candidate_id
                db.execute(
                    """INSERT INTO material_candidates
                    (id,search_id,user_id,account_id,provider,provider_asset_id,
                     media_type,role,source_url,preview_url,download_url,creator,
                     creator_url,license_name,license_url,provider_home_url,width,
                     height,duration,score,score_json,metadata_json,status,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'candidate',?,?)""",
                    (
                        candidate_id,
                        search_id,
                        user_id,
                        account_id,
                        candidate["provider"],
                        candidate["provider_asset_id"],
                        candidate["media_type"],
                        candidate["role"],
                        candidate.get("source_url", ""),
                        candidate.get("preview_url", ""),
                        candidate.get("download_url", ""),
                        candidate.get("creator", ""),
                        candidate.get("creator_url", ""),
                        candidate.get("license_name", ""),
                        candidate.get("license_url", ""),
                        candidate.get("provider_home_url", ""),
                        int(candidate.get("width") or 0),
                        int(candidate.get("height") or 0),
                        float(candidate.get("duration") or 0),
                        float(candidate["score"]),
                        _json(candidate["score_breakdown"]),
                        _json(candidate.get("metadata") or {}),
                        now,
                        now,
                    ),
                )
            status = "completed" if candidates else "unavailable"
            db.execute(
                """UPDATE material_searches
                SET status=?,provider_errors_json=?,updated_at=? WHERE id=?""",
                (status, _json(provider_errors), _now(), search_id),
            )
        return self.get_search(
            search_id=search_id,
            user_id=user_id,
            account_id=account_id,
        )

    def get_search(
        self, *, search_id: str, user_id: str, account_id: str
    ) -> dict[str, Any]:
        with self._connection() as db:
            search = db.execute(
                """SELECT * FROM material_searches
                WHERE id=? AND user_id=? AND account_id=?""",
                (search_id, user_id, account_id),
            ).fetchone()
            rows = db.execute(
                """SELECT * FROM material_candidates
                WHERE search_id=? AND user_id=? AND account_id=?
                ORDER BY score DESC,created_at ASC""",
                (search_id, user_id, account_id),
            ).fetchall()
        if search is None:
            raise KeyError("material search not found in account scope")
        value = dict(search)
        value["query"] = json.loads(value.pop("query_json") or "{}")
        value["provider_errors"] = json.loads(value.pop("provider_errors_json") or "{}")
        value["candidates"] = [_candidate_record(row) for row in rows]
        return value

    def materialize(
        self,
        *,
        candidate_id: str,
        user_id: str,
        account_id: str,
        rights_reviewed: bool,
    ) -> dict[str, Any]:
        if not rights_reviewed:
            raise ValueError("explicit source and license review is required")
        self.media.cleanup_expired(user_id=user_id)
        with self._connection() as db:
            row = db.execute(
                """SELECT * FROM material_candidates
                WHERE id=? AND user_id=? AND account_id=?""",
                (candidate_id, user_id, account_id),
            ).fetchone()
        if row is None:
            raise KeyError("material candidate not found in account scope")
        candidate = dict(row)
        if candidate.get("selected_media_asset_id"):
            try:
                return {
                    "candidate": _candidate_record(row),
                    "asset": self.media.get(
                        asset_id=candidate["selected_media_asset_id"], user_id=user_id
                    ),
                }
            except KeyError:
                # An unreferenced temporary binary may have expired since selection.
                # Keep the durable candidate and materialize it again below.
                candidate["selected_media_asset_id"] = None
        if candidate["provider"] == "user_library":
            asset = self.media.get(
                asset_id=candidate["provider_asset_id"], user_id=user_id
            )
        else:
            if not candidate["license_name"] or not candidate["license_url"]:
                raise ValueError("provider candidate has no durable license evidence")
            asset = self.media.find_provider_asset(
                user_id=user_id,
                account_id=account_id,
                provider=candidate["provider"],
                provider_asset_id=candidate["provider_asset_id"],
            )
            if asset is None:
                provider = get_material_provider(candidate["provider"])
                payload, filename, mime_type = provider.download(candidate)
                asset = self.media.import_provider_bytes(
                    user_id=user_id,
                    account_id=account_id,
                    name=f"{candidate['provider']} {candidate['provider_asset_id']}",
                    media_type=candidate["media_type"],
                    role=candidate["role"],
                    payload=payload,
                    filename=filename,
                    mime_type=mime_type,
                    provider=candidate["provider"],
                    provider_asset_id=candidate["provider_asset_id"],
                    metadata={
                        "source_url": candidate["source_url"],
                        "creator": candidate["creator"],
                        "creator_url": candidate["creator_url"],
                        "license_name": candidate["license_name"],
                        "license_url": candidate["license_url"],
                        "provider_home_url": candidate["provider_home_url"],
                        "rights_caveat": (
                            "Check people, property, trademarks and context-specific releases before publication."
                        ),
                    },
                    receipt={
                        "version": "marketing.material.receipt.v1",
                        "candidate_id": candidate_id,
                        "search_id": candidate["search_id"],
                        "provider": candidate["provider"],
                        "provider_asset_id": candidate["provider_asset_id"],
                        "source_url": candidate["source_url"],
                        "license_name": candidate["license_name"],
                        "license_url": candidate["license_url"],
                        "rights_reviewed": True,
                        "materialized_at": _now(),
                    },
                    storage_tier="temporary",
                )
        with self._transaction() as db:
            db.execute(
                """UPDATE material_candidates
                SET status='selected',selected_media_asset_id=?,updated_at=?
                WHERE id=? AND user_id=? AND account_id=?""",
                (asset["id"], _now(), candidate_id, user_id, account_id),
            )
            selected = db.execute(
                "SELECT * FROM material_candidates WHERE id=?", (candidate_id,)
            ).fetchone()
        return {"candidate": _candidate_record(selected), "asset": asset}

    def _local_candidates(
        self, *, user_id: str, account_id: str, request: dict[str, Any]
    ) -> list[dict[str, Any]]:
        query_terms = _semantic_query_terms(str(request["query"]))
        results = []
        for asset in self.media.list(user_id=user_id, account_id=account_id)["assets"]:
            if (
                asset["media_type"] not in {"image", "video"}
                or (
                    request.get("media_type") != "either"
                    and asset["media_type"] != request.get("media_type")
                )
                or asset["role"] not in _ROLES
                or not asset.get("local_path")
            ):
                continue
            haystack = f"{asset['name']} {_json(asset.get('metadata') or {})}".lower()
            if not any(term in haystack for term in query_terms):
                continue
            semantic = 1.0
            breakdown = {
                "source_priority": 0.32,
                "semantic_fit": round(0.28 * semantic, 4),
                "rights_confidence": 0.2,
                "quality_fit": 0.08,
                "continuity_fit": 0.04,
            }
            results.append({
                "provider": "user_library",
                "provider_asset_id": asset["id"],
                "media_type": asset["media_type"],
                "role": request["role"],
                "source_url": "",
                "preview_url": "",
                "download_url": "",
                "creator": "",
                "creator_url": "",
                "license_name": "User-confirmed rights",
                "license_url": "",
                "provider_home_url": "",
                "width": int((asset.get("metadata") or {}).get("width") or 0),
                "height": int((asset.get("metadata") or {}).get("height") or 0),
                "duration": float((asset.get("metadata") or {}).get("duration") or 0),
                "score_breakdown": breakdown,
                "score": round(sum(breakdown.values()), 4),
                "metadata": {"asset_name": asset["name"]},
            })
        return results

    @staticmethod
    def _normalize_provider_candidate(
        candidate: dict[str, Any], *, role: str
    ) -> dict[str, Any]:
        if not isinstance(candidate, dict):
            raise ValueError("material provider returned a non-object candidate")
        required = (
            "provider",
            "provider_asset_id",
            "media_type",
            "source_url",
            "download_url",
            "license_name",
            "license_url",
        )
        if any(not str(candidate.get(field) or "").strip() for field in required):
            raise ValueError(
                "material provider candidate is missing required provenance"
            )
        if candidate["media_type"] not in {"image", "video"}:
            raise ValueError("material provider returned an unsupported media type")
        value = dict(candidate)
        value["role"] = role
        value["metadata"] = (
            value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
        )
        return value

    @staticmethod
    def _score(candidate: dict[str, Any], request: dict[str, Any]) -> dict[str, float]:
        width = max(0, int(candidate.get("width") or 0))
        height = max(0, int(candidate.get("height") or 0))
        long_edge = max(width, height)
        quality = min(1.0, long_edge / 1920) if long_edge else 0.35
        orientation = request.get("orientation")
        orientation_fit = 1.0
        if orientation == "portrait":
            orientation_fit = 1.0 if height >= width else 0.3
        elif orientation == "landscape":
            orientation_fit = 1.0 if width >= height else 0.3
        elif orientation == "square" and width and height:
            orientation_fit = max(0.3, 1 - abs(math.log(width / height)))
        duration_fit = 0.7
        target_duration = float(request.get("target_duration") or 0)
        actual_duration = float(candidate.get("duration") or 0)
        if target_duration and actual_duration:
            duration_fit = max(0.2, min(1.0, actual_duration / target_duration))
        return {
            "source_priority": 0.1,
            "semantic_fit": 0.2,
            "rights_confidence": 0.14,
            "quality_fit": round(0.18 * quality, 4),
            "orientation_fit": round(0.12 * orientation_fit, 4),
            "duration_fit": round(0.08 * duration_fit, 4),
            "novelty": 0.02,
        }

    @staticmethod
    def _required(value: Any, field: str, *, limit: int = 256) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{field} is required")
        if len(text) > limit:
            raise ValueError(f"{field} must be at most {limit} characters")
        return text


def _semantic_query_terms(query: str) -> set[str]:
    """Tokenize Latin words and CJK bigrams for conservative library matching."""

    terms = {term.lower() for term in re.findall(r"[a-zA-Z0-9]+", query)}
    for run in re.findall(r"[\u3400-\u9fff]+", query):
        if len(run) == 1:
            terms.add(run)
        else:
            terms.update(run[index : index + 2] for index in range(len(run) - 1))
    return terms
