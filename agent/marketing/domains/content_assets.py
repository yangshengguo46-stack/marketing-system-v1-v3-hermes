"""Account-scoped content assets owned by the native Hermes runtime."""

from __future__ import annotations

import json
import hashlib
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.article_drafts import ArticleDraftValidator
from agent.marketing.domains.content_policy import CONTENT_KINDS, VALID_PLATFORMS
from agent.marketing.domains.evidence import EvidenceRepository
from agent.marketing.domains.storage import MarketingDomainRepository
from agent.marketing.domains.short_video_signals import ShortVideoSignalRepository
from agent.marketing.intelligence.content_feature_snapshot import (
    build_content_feature_snapshot,
)


ASSET_TYPES = {"script", "video", "image", "caption"}
CONTENT_ASSET_PLATFORMS = VALID_PLATFORMS | {"multi_article"}


class ContentAssetRepository(MarketingDomainRepository):
    def __init__(self, paths: MarketingDataPaths | None = None):
        super().__init__(paths)
        self._ensure_schema()

    def save_production_plan(
        self,
        *,
        user_id: str,
        account_id: str,
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(plan, dict) or plan.get("status") != "planned":
            raise ValueError("a valid production plan is required")
        kind = str(plan.get("kind") or "")
        if kind not in CONTENT_KINDS:
            raise ValueError("production plan kind is invalid")
        objective = _bounded_text(plan.get("objective"), "objective", 2_000)
        platforms = plan.get("target_platforms")
        if not isinstance(platforms, list) or not platforms:
            raise ValueError("production plan requires target platforms")
        if any(platform not in VALID_PLATFORMS for platform in platforms):
            raise ValueError("production plan contains unsupported platform")
        experiment_id = str(plan.get("experiment_id") or "").strip() or None
        fingerprint = json.dumps(
            {
                "user_id": user_id,
                "account_id": account_id,
                "kind": kind,
                "objective": objective,
                "platforms": platforms,
                "constraints": plan.get("constraints") or {},
                "experiment_id": experiment_id,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:24]
        plan_id = f"production_plan_{digest}"
        payload = dict(plan)
        payload["plan_id"] = plan_id
        encoded = _bounded_json(payload, "production_plan", 500_000)
        now = _now()
        with self._transaction() as db:
            if experiment_id:
                experiment = db.execute(
                    """SELECT content_system_id,status FROM account_experiments
                    WHERE id=? AND user_id=? AND account_id=?""",
                    (experiment_id, user_id, account_id),
                ).fetchone()
                if experiment is None:
                    raise KeyError("experiment not found in account scope")
                if experiment["status"] != "running":
                    raise ValueError("production plan requires a running experiment")
                current_system_id = str(
                    (plan.get("account_scope") or {}).get("content_system_id") or ""
                )
                if current_system_id and experiment["content_system_id"] != current_system_id:
                    raise ValueError("experiment does not belong to the current content system")
            db.execute(
                """INSERT INTO content_production_plans
                (id,user_id,account_id,experiment_id,kind,objective,platforms_json,plan_json,
                 status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,'planned',?,?)
                ON CONFLICT(id) DO UPDATE SET
                    plan_json=excluded.plan_json,
                    updated_at=excluded.updated_at""",
                (
                    plan_id,
                    user_id,
                    account_id,
                    experiment_id,
                    kind,
                    objective,
                    json.dumps(platforms, ensure_ascii=False),
                    encoded,
                    now,
                    now,
                ),
            )
            row = db.execute(
                "SELECT * FROM content_production_plans WHERE id=?",
                (plan_id,),
            ).fetchone()
        return _plan_record(row)

    def create_draft(
        self,
        *,
        user_id: str,
        account_id: str,
        title: str,
        plan_id: str,
        asset_type: str,
        platform: str,
        production_kind: str,
        content: dict[str, Any],
        topic: str = "",
        hook: str = "",
        evidence_refs: list[str] | None = None,
        memory_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        if production_kind == "article_soft":
            raise ValueError(
                "article_soft drafts must use the validated article bundle path"
            )
        return self._save_draft(
            user_id=user_id,
            account_id=account_id,
            title=title,
            plan_id=plan_id,
            asset_type=asset_type,
            platform=platform,
            production_kind=production_kind,
            content=content,
            topic=topic,
            hook=hook,
            evidence_refs=evidence_refs,
            memory_refs=memory_refs,
        )

    def create_article_bundle(
        self,
        *,
        user_id: str,
        account_id: str,
        title: str,
        plan_id: str,
        parent_body_markdown: str,
        platform_variants: dict[str, Any],
        evidence_refs: list[str],
        topic: str = "",
        hook: str = "",
        revision_of: str = "",
    ) -> dict[str, Any]:
        plan_id_value = _bounded_text(plan_id, "plan_id", 120)
        with self._connection() as db:
            plan_row = db.execute(
                """SELECT * FROM content_production_plans
                WHERE id=? AND user_id=? AND account_id=?""",
                (plan_id_value, user_id, account_id),
            ).fetchone()
        if plan_row is None:
            raise KeyError("production plan not found in account scope")
        if plan_row["kind"] != "article_soft":
            raise ValueError("article bundle requires an article_soft production plan")
        parent_asset_id: str | None = None
        next_version = 1
        revision_of_value = str(revision_of or "").strip()
        if revision_of_value:
            with self._connection() as db:
                parent_row = db.execute(
                    """SELECT * FROM content_assets
                    WHERE id=? AND user_id=? AND account_id=?""",
                    (revision_of_value, user_id, account_id),
                ).fetchone()
            if parent_row is None:
                raise KeyError("article revision parent not found in account scope")
            if parent_row["platform"] != "multi_article" or parent_row["type"] != "script":
                raise ValueError("article revision parent is not an ArticleBundle")
            try:
                parent_content = json.loads(parent_row["content_json"])
            except (TypeError, ValueError) as exc:
                raise ValueError("article revision parent content is invalid") from exc
            if parent_content.get("_production_plan_id") != plan_id_value:
                raise ValueError("article revision must keep the same production plan")
            parent_asset_id = parent_row["id"]
            next_version = int(parent_row["version"] or 1) + 1
        target_platforms = json.loads(plan_row["platforms_json"])
        verified_evidence = EvidenceRepository(self.paths).require_verified(
            user_id=user_id,
            account_id=account_id,
            evidence_ids=evidence_refs,
            require_any=True,
        )
        bundle = ArticleDraftValidator().build_bundle(
            title=title,
            parent_body_markdown=parent_body_markdown,
            target_platforms=target_platforms,
            variants=platform_variants,
            evidence_records=verified_evidence,
            topic=topic,
            hook=hook,
        )
        ready = bundle["review_status"] == "ready_for_human_review"
        return self._save_draft(
            user_id=user_id,
            account_id=account_id,
            title=title,
            plan_id=plan_id_value,
            asset_type="script",
            platform="multi_article",
            production_kind="article_soft",
            content=bundle,
            topic=topic,
            hook=hook,
            evidence_refs=evidence_refs,
            memory_refs=[],
            allow_multi_article=True,
            asset_status="review_ready" if ready else "draft",
            plan_checkpoint_status="review_ready" if ready else "draft_created",
            parent_id=parent_asset_id,
            asset_version=next_version,
        )

    def _save_draft(
        self,
        *,
        user_id: str,
        account_id: str,
        title: str,
        plan_id: str,
        asset_type: str,
        platform: str,
        production_kind: str,
        content: dict[str, Any],
        topic: str = "",
        hook: str = "",
        evidence_refs: list[str] | None = None,
        memory_refs: list[str] | None = None,
        allow_multi_article: bool = False,
        asset_status: str = "draft",
        plan_checkpoint_status: str = "draft_created",
        parent_id: str | None = None,
        asset_version: int = 1,
    ) -> dict[str, Any]:
        title_value = _bounded_text(title, "title", 300)
        plan_id_value = _bounded_text(plan_id, "plan_id", 120)
        if asset_type not in ASSET_TYPES:
            raise ValueError(f"unsupported asset type: {asset_type}")
        if platform not in CONTENT_ASSET_PLATFORMS:
            raise ValueError(f"unsupported content platform: {platform}")
        if platform == "multi_article" and not allow_multi_article:
            raise ValueError("multi_article is reserved for validated article bundles")
        if production_kind not in CONTENT_KINDS:
            raise ValueError(f"unsupported production kind: {production_kind}")
        if asset_status not in {"draft", "review_ready"}:
            raise ValueError("unsupported content asset status")
        if int(asset_version) < 1:
            raise ValueError("content asset version must be positive")
        if not isinstance(content, dict) or not content:
            raise ValueError("content must be a non-empty object")
        if any(str(key).startswith("_") for key in content):
            raise ValueError("content keys beginning with '_' are reserved")
        if "feature_snapshot" in content:
            raise ValueError("feature_snapshot is system-generated")
        verified_evidence = EvidenceRepository(self.paths).require_verified(
            user_id=user_id,
            account_id=account_id,
            evidence_ids=evidence_refs or [],
            require_any=True,
        )
        payload = dict(content)
        payload["_production_kind"] = production_kind
        payload["_provenance_evidence_refs"] = [item["id"] for item in verified_evidence]
        payload["_evidence_verification_level"] = "source_integrity"
        payload["_provenance_memory_refs"] = _bounded_refs(memory_refs or [], "memory_refs")
        payload["_created_by"] = "hermes-native-marketing"
        encoded = _bounded_json(payload, "content", 500_000)
        now = _now()
        asset_id = f"asset_{uuid.uuid4().hex}"
        with self._transaction() as db:
            plan_row = db.execute(
                """SELECT * FROM content_production_plans
                WHERE id=? AND user_id=? AND account_id=?""",
                (plan_id_value, user_id, account_id),
            ).fetchone()
            if plan_row is None:
                raise KeyError("production plan not found in account scope")
            plan_platforms = json.loads(plan_row["platforms_json"])
            if plan_row["kind"] != production_kind:
                raise ValueError("draft production kind does not match its plan")
            if platform == "multi_article":
                if production_kind != "article_soft" or any(
                    item not in {"zhihu", "wechat_official"} for item in plan_platforms
                ):
                    raise ValueError("article bundle platforms do not match its plan")
            elif platform not in plan_platforms:
                raise ValueError("draft platform is outside its production plan")
            payload["_production_plan_id"] = plan_id_value
            experiment_id = str(plan_row["experiment_id"] or "").strip() or None
            payload["_experiment_id"] = experiment_id
            plan_payload = json.loads(plan_row["plan_json"])
            sound_plan = payload.get("sound_plan")
            if production_kind in {"faceless_video", "premium_human_video"}:
                sound_plan = _validated_sound_plan(
                    sound_plan,
                    repository=ShortVideoSignalRepository(self.paths),
                    user_id=user_id,
                    account_id=account_id,
                    platform=platform,
                )
                payload["sound_plan"] = sound_plan
            platform_variants = payload.get("platform_variants")
            if not isinstance(platform_variants, dict):
                platform_variants = {}
            payload["feature_snapshot"] = build_content_feature_snapshot(
                kind=production_kind,
                objective=plan_row["objective"],
                title=title_value,
                topic=topic,
                hook=hook,
                account_id=account_id,
                platforms=plan_platforms,
                audience_context=plan_payload.get("account_scope") or {},
                evidence=verified_evidence,
                structure={
                    "content_schema": payload.get("schema") or asset_type,
                    "platform_variant_keys": sorted(platform_variants.keys()),
                },
                material_context=payload.get("material_manifest") or {},
                sound_context=sound_plan if isinstance(sound_plan, dict) else None,
                risks=(payload.get("validation") or {}).get("issues") or [],
            )
            encoded = _bounded_json(payload, "content", 500_000)
            db.execute(
                """INSERT INTO content_assets
                (id,user_id,account_id,platform,title,type,status,parent_id,experiment_id,
                 topic,hook,version,content_json,metrics_json,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'{}',?,?)""",
                (
                    asset_id,
                    user_id,
                    account_id,
                    platform,
                    title_value,
                    asset_type,
                    asset_status,
                    parent_id,
                    experiment_id,
                    _optional_text(topic, 200),
                    _optional_text(hook, 200),
                    int(asset_version),
                    encoded,
                    now,
                    now,
                ),
            )
            if experiment_id:
                experiment = db.execute(
                    """SELECT asset_ids_json FROM account_experiments
                    WHERE id=? AND user_id=? AND account_id=? AND status='running'""",
                    (experiment_id, user_id, account_id),
                ).fetchone()
                if experiment is None:
                    raise ValueError("running experiment disappeared from account scope")
                asset_ids = json.loads(experiment["asset_ids_json"] or "[]")
                if asset_id not in asset_ids:
                    asset_ids.append(asset_id)
                    db.execute(
                        """UPDATE account_experiments SET asset_ids_json=?,updated_at=?
                        WHERE id=?""",
                        (json.dumps(asset_ids, ensure_ascii=False), now, experiment_id),
                    )
            if parent_id:
                updated = db.execute(
                    """UPDATE content_assets SET status='superseded', updated_at=?
                    WHERE id=? AND user_id=? AND account_id=?""",
                    (now, parent_id, user_id, account_id),
                ).rowcount
                if updated != 1:
                    raise KeyError("article revision parent disappeared from account scope")
            db.execute(
                """UPDATE content_production_plans
                SET status=?, updated_at=? WHERE id=?""",
                (plan_checkpoint_status, now, plan_id_value),
            )
        return self.get(asset_id=asset_id, user_id=user_id, account_id=account_id)

    def get(self, *, asset_id: str, user_id: str, account_id: str) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM content_assets WHERE id=? AND user_id=? AND account_id=?",
                (asset_id, user_id, account_id),
            ).fetchone()
        if row is None:
            raise KeyError("content asset not found in account scope")
        return _record(row)

    def list(
        self,
        *,
        user_id: str,
        account_id: str,
        status: str | None = None,
        platform: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 50))
        query = "SELECT * FROM content_assets WHERE user_id=? AND account_id=?"
        params: list[Any] = [user_id, account_id]
        if status:
            query += " AND status=?"
            params.append(status)
        else:
            query += " AND status!='superseded'"
        if platform:
            if platform not in CONTENT_ASSET_PLATFORMS:
                raise ValueError(f"unsupported content platform: {platform}")
            query += " AND platform=?"
            params.append(platform)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(safe_limit)
        with self._connection() as db:
            rows = db.execute(query, params).fetchall()
        return {
            "user_id": user_id,
            "account_id": account_id,
            "assets": [_record(row) for row in rows],
            "total": len(rows),
        }

    def _ensure_schema(self) -> None:
        with self._connection() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS content_assets (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    account_id TEXT,
                    platform TEXT,
                    title TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'script',
                    status TEXT NOT NULL DEFAULT 'draft',
                    parent_id TEXT,
                    experiment_id TEXT,
                    topic TEXT,
                    hook TEXT,
                    version INTEGER NOT NULL DEFAULT 1,
                    content_json TEXT NOT NULL DEFAULT '{}',
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_content_assets_status ON content_assets(status);
                CREATE INDEX IF NOT EXISTS idx_content_assets_account ON content_assets(account_id);
                CREATE INDEX IF NOT EXISTS idx_content_assets_scope
                    ON content_assets(user_id, account_id, updated_at);
                CREATE TABLE IF NOT EXISTS content_production_plans (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    platforms_json TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'planned',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_content_production_plan_scope
                    ON content_production_plans(user_id, account_id, updated_at);
                """
            )
            self._migrate_article_validation_v2(db)

    def _migrate_article_validation_v2(self, db: sqlite3.Connection) -> None:
        evidence_table = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='evidence_records'"
        ).fetchone()
        if evidence_table is None:
            return
        rows = db.execute(
            """SELECT * FROM content_assets
            WHERE platform='multi_article' AND type='script'"""
        ).fetchall()
        for row in rows:
            try:
                previous = json.loads(row["content_json"])
            except (TypeError, ValueError):
                continue
            if previous.get("schema") != "marketing.article_bundle.v1":
                continue
            previous_validation = previous.get("validation") or {}
            if previous_validation.get("version") == "marketing.article_validation.v2":
                continue
            evidence_ids = previous.get("_provenance_evidence_refs") or [
                item.get("evidence_id")
                for item in previous.get("evidence_pack") or []
                if isinstance(item, dict) and item.get("evidence_id")
            ]
            evidence_records: list[dict[str, Any]] = []
            if evidence_ids:
                placeholders = ",".join("?" for _ in evidence_ids)
                evidence_records = [
                    dict(item)
                    for item in db.execute(
                        f"""SELECT * FROM evidence_records
                        WHERE user_id=? AND account_id=? AND id IN ({placeholders})""",
                        [row["user_id"], row["account_id"], *evidence_ids],
                    ).fetchall()
                ]
            try:
                bundle = ArticleDraftValidator().build_bundle(
                    title=str(
                        (previous.get("parent_draft") or {}).get("title")
                        or row["title"]
                    ),
                    parent_body_markdown=str(
                        (previous.get("parent_draft") or {}).get("body_markdown")
                        or ""
                    ),
                    target_platforms=list(
                        (previous.get("platform_variants") or {}).keys()
                    ),
                    variants=previous.get("platform_variants") or {},
                    evidence_records=evidence_records,
                    topic=str(previous.get("topic") or row["topic"] or ""),
                    hook=str(previous.get("hook") or row["hook"] or ""),
                )
                for key, value in previous.items():
                    if str(key).startswith("_"):
                        bundle[key] = value
                ready = bundle["review_status"] == "ready_for_human_review"
                encoded = _bounded_json(bundle, "content", 500_000)
            except (KeyError, TypeError, ValueError) as exc:
                failed = dict(previous)
                failed["review_status"] = "needs_revision"
                failed["validation"] = {
                    "version": "marketing.article_validation.v2",
                    "ready": False,
                    "issues": ["article_validation_migration_failed"],
                    "migration_error": str(exc)[:300],
                }
                ready = False
                encoded = _bounded_json(failed, "content", 500_000)
            now = _now()
            db.execute(
                """UPDATE content_assets
                SET content_json=?, status=?, version=version+1, updated_at=?
                WHERE id=?""",
                (encoded, "review_ready" if ready else "draft", now, row["id"]),
            )
            plan_id = previous.get("_production_plan_id")
            if plan_id:
                db.execute(
                    """UPDATE content_production_plans
                    SET status=?, updated_at=? WHERE id=? AND user_id=? AND account_id=?""",
                    (
                        "review_ready" if ready else "draft_created",
                        now,
                        plan_id,
                        row["user_id"],
                        row["account_id"],
                    ),
                )

def _validated_sound_plan(
    value: Any,
    *,
    repository: ShortVideoSignalRepository,
    user_id: str,
    account_id: str,
    platform: str,
) -> dict[str, Any]:
    if value is None:
        return {
            "status": "needs_selection",
            "mode": "undecided",
            "reason": "BGM is a first-class distribution variable for short video",
        }
    if not isinstance(value, dict):
        raise ValueError("sound_plan must be an object")
    mode = str(value.get("mode") or "").strip()
    if mode not in {"trend_sound", "original_voice_only", "custom_licensed", "original_music"}:
        raise ValueError("unsupported sound_plan mode")
    result = {
        "status": "selected",
        "mode": mode,
        "mix_role": str(value.get("mix_role") or "support").strip()[:80],
        "opening_cue_ms": max(0, int(value.get("opening_cue_ms") or 0)),
    }
    if mode == "trend_sound":
        sound = repository.require_sound(
            user_id=user_id,
            account_id=account_id,
            platform=platform,
            sound_id=str(value.get("sound_id") or ""),
        )
        result.update(
            {
                "sound_id": sound["id"],
                "title": sound["title"],
                "artist": sound["artist"],
                "rights_status": sound["rights_status"],
            }
        )
    return result


def _record(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    value["content"] = json.loads(value.pop("content_json"))
    value["metrics"] = json.loads(value.pop("metrics_json"))
    return value


def _plan_record(row: sqlite3.Row) -> dict[str, Any]:
    value = json.loads(row["plan_json"])
    value["plan_id"] = row["id"]
    value["checkpoint_status"] = row["status"]
    value["created_at"] = row["created_at"]
    value["updated_at"] = row["updated_at"]
    return value


def _bounded_text(value: Any, field: str, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    if len(text) > limit:
        raise ValueError(f"{field} exceeds {limit} characters")
    return text


def _optional_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _bounded_refs(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    result = [str(item).strip() for item in value if str(item).strip()]
    if len(result) > 100 or any(len(item) > 500 for item in result):
        raise ValueError(f"{field} exceeds limits")
    return result


def _bounded_json(value: Any, field: str, limit: int) -> str:
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be JSON serializable") from exc
    if len(encoded.encode("utf-8")) > limit:
        raise ValueError(f"{field} exceeds {limit} bytes")
    return encoded


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
