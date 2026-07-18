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
from agent.marketing.intelligence.audience_reaction_simulation import (
    build_social_reaction_simulation,
)
from agent.marketing.intelligence.content_prediction import attach_prediction_dimensions
from agent.marketing.intelligence.social_system_simulation import (
    build_social_system_simulation,
)
from agent.marketing.intelligence.store import OperatingLoopRepository
from agent.marketing.platform_catalog import (
    normalize_platform_id,
    normalize_platforms,
    platform_content_blueprints,
)


ASSET_TYPES = {"script", "video", "image", "caption"}
CONTENT_ASSET_PLATFORMS = VALID_PLATFORMS | {"multi_article", "multi_platform"}


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
        platforms = normalize_platforms(platforms)
        if not platforms:
            raise ValueError("production plan requires target platforms")
        experiment_id = str(plan.get("experiment_id") or "").strip() or None
        fingerprint = json.dumps(
            {
                "user_id": user_id,
                "account_id": account_id,
                "kind": kind,
                "objective": objective,
                "platforms": platforms,
                "constraints": plan.get("constraints") or {},
                "audience_model": plan.get("audience_model") or {},
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
        payload["target_platforms"] = platforms
        payload["platform_blueprints"] = platform_content_blueprints(platforms)
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
        reaction_scenarios: list[dict[str, Any]] | None = None,
        revision_of: str = "",
    ) -> dict[str, Any]:
        if production_kind == "article_soft":
            raise ValueError(
                "article_soft drafts must use the validated article bundle path"
            )
        parent_id, asset_version = self._content_revision_parent(
            revision_of=revision_of,
            user_id=user_id,
            account_id=account_id,
            plan_id=plan_id,
            platform=platform,
            production_kind=production_kind,
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
            reaction_scenarios=reaction_scenarios,
            parent_id=parent_id,
            asset_version=asset_version,
        )

    def create_faceless_render_revision(
        self,
        *,
        parent_asset_id: str,
        user_id: str,
        account_id: str,
        production: dict[str, Any],
    ) -> dict[str, Any]:
        """Create the immutable, reviewable version produced by a render job."""

        production_id = str(production.get("production_id") or "").strip()
        if not production_id or len(production_id) > 200:
            raise ValueError("render production_id is required")
        with self._connection() as db:
            prior_rows = db.execute(
                """SELECT * FROM content_assets
                WHERE user_id=? AND account_id=? AND type='video'
                ORDER BY created_at ASC""",
                (user_id, account_id),
            ).fetchall()
        for row in prior_rows:
            prior_content = json.loads(row["content_json"] or "{}")
            prior_production = prior_content.get("production") or {}
            if prior_production.get("production_id") == production_id:
                return _record(row)

        parent = self.get(
            asset_id=parent_asset_id,
            user_id=user_id,
            account_id=account_id,
        )
        previous = parent.get("content") if isinstance(parent.get("content"), dict) else {}
        if previous.get("_production_kind") != "faceless_video":
            raise ValueError("render revision parent is not a faceless video asset")
        plan_id = str(previous.get("_production_plan_id") or "").strip()
        if not plan_id:
            raise ValueError("render revision parent has no production plan")
        parent_id, asset_version = self._content_revision_parent(
            revision_of=parent_asset_id,
            user_id=user_id,
            account_id=account_id,
            plan_id=plan_id,
            platform=str(parent.get("platform") or ""),
            production_kind="faceless_video",
        )
        payload = {
            key: value
            for key, value in previous.items()
            if not str(key).startswith("_") and key != "feature_snapshot"
        }
        payload["schema"] = "marketing.faceless_video.v1"
        payload["production"] = production
        payload["review_status"] = "ready_for_human_review"
        validation = (
            dict(payload.get("validation"))
            if isinstance(payload.get("validation"), dict)
            else {}
        )
        validation.update(
            {
                "version": "marketing.faceless_video_validation.v1",
                "ready": True,
                "issues": [],
                "pending_human_checks": [
                    "pacing and account fit",
                    "caption timing and readability",
                    "visual rights and final preview",
                    "voice and background sound balance",
                ],
            }
        )
        payload["validation"] = validation
        prediction = previous.get("prediction")
        reaction = (
            prediction.get("social_reaction_simulation")
            if isinstance(prediction, dict)
            and isinstance(prediction.get("social_reaction_simulation"), dict)
            else {}
        )
        return self._save_draft(
            user_id=user_id,
            account_id=account_id,
            title=str(parent.get("title") or "不露脸视频"),
            plan_id=plan_id,
            asset_type="video",
            platform=str(parent.get("platform") or ""),
            production_kind="faceless_video",
            content=payload,
            topic=str(parent.get("topic") or ""),
            hook=str(parent.get("hook") or ""),
            evidence_refs=list(previous.get("_provenance_evidence_refs") or []),
            memory_refs=list(previous.get("_provenance_memory_refs") or []),
            reaction_scenarios=list(reaction.get("scenarios") or []),
            asset_status="review_ready",
            plan_checkpoint_status="review_ready",
            parent_id=parent_id,
            asset_version=asset_version,
        )

    def _content_revision_parent(
        self,
        *,
        revision_of: str,
        user_id: str,
        account_id: str,
        plan_id: str,
        platform: str,
        production_kind: str,
    ) -> tuple[str | None, int]:
        revision_value = str(revision_of or "").strip()
        if not revision_value:
            return None, 1
        parent = self.get(
            asset_id=revision_value,
            user_id=user_id,
            account_id=account_id,
        )
        content = parent.get("content") if isinstance(parent.get("content"), dict) else {}
        if content.get("_production_kind") != production_kind:
            raise ValueError("content revision parent has the wrong production kind")
        if content.get("_production_plan_id") != str(plan_id or "").strip():
            raise ValueError("content revision must keep the same production plan")
        if parent.get("platform") != platform or parent.get("type") not in {"script", "video"}:
            raise ValueError("content revision must keep the same platform and asset lane")
        if parent.get("status") in {"superseded", "approved", "published", "archived"}:
            raise ValueError(f"content revision cannot branch from {parent.get('status')}")
        return str(parent["id"]), int(parent.get("version") or 1) + 1

    def get_production_plan(
        self, *, plan_id: str, user_id: str, account_id: str
    ) -> dict[str, Any]:
        """Read one durable production plan inside its account boundary."""

        with self._connection() as db:
            row = db.execute(
                """SELECT * FROM content_production_plans
                WHERE id=? AND user_id=? AND account_id=?""",
                (plan_id, user_id, account_id),
            ).fetchone()
        if row is None:
            raise KeyError("production plan not found in account scope")
        return _plan_record(row)

    def list_production_plans(
        self,
        *,
        user_id: str,
        account_id: str,
        limit: int = 50,
    ) -> dict[str, Any]:
        """List bounded durable plans, including their preflight identity."""

        safe_limit = max(1, min(int(limit), 100))
        with self._connection() as db:
            rows = db.execute(
                """SELECT p.*,
                          (SELECT id FROM marketing_preflight_records f
                           WHERE f.plan_id=p.id AND f.user_id=p.user_id
                             AND f.account_id=p.account_id
                           ORDER BY f.created_at DESC,f.id DESC LIMIT 1) AS preflight_id,
                          (SELECT decision_json FROM marketing_preflight_records f
                           WHERE f.plan_id=p.id AND f.user_id=p.user_id
                             AND f.account_id=p.account_id
                           ORDER BY f.created_at DESC,f.id DESC LIMIT 1) AS preflight_decision_json
                FROM content_production_plans p
                WHERE p.user_id=? AND p.account_id=? AND p.status!='archived'
                ORDER BY p.updated_at DESC,p.id DESC LIMIT ?""",
                (user_id, account_id, safe_limit),
            ).fetchall()
        plans = []
        for row in rows:
            value = _plan_record(row)
            value["preflight_id"] = row["preflight_id"]
            decision = json.loads(row["preflight_decision_json"] or "{}")
            preflight_decision = decision.get("preflight_decision") or {}
            value["preflight_status"] = preflight_decision.get("status")
            value["recommendation_eligible"] = preflight_decision.get("go") is True
            plans.append(value)
        return {"plans": plans, "total": len(plans)}

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
        reaction_scenarios: list[dict[str, Any]] | None = None,
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
            if parent_row["status"] == "archived":
                raise ValueError("an archived article must be restored before revision")
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
            reaction_scenarios=reaction_scenarios,
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
        reaction_scenarios: list[dict[str, Any]] | None = None,
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
        if platform not in {"multi_article", "multi_platform"}:
            platform = normalize_platform_id(platform)
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
        try:
            persisted_preflight = OperatingLoopRepository(self.paths).latest_preflight_for_plan(
                plan_id=plan_id_value,
                user_id=user_id,
                account_id=account_id,
            )
        except ValueError:
            persisted_preflight = None
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
            elif platform == "multi_platform":
                if production_kind != "cross_platform_campaign":
                    raise ValueError("multi_platform is reserved for cross-platform campaigns")
                payload["platform_variants"] = _validate_cross_platform_variants(
                    payload,
                    target_platforms=plan_platforms,
                )
                payload["platform_blueprints"] = platform_content_blueprints(plan_platforms)
            elif platform not in plan_platforms:
                raise ValueError("draft platform is outside its production plan")
            payload["_production_plan_id"] = plan_id_value
            experiment_id = str(plan_row["experiment_id"] or "").strip() or None
            payload["_experiment_id"] = experiment_id
            plan_payload = json.loads(plan_row["plan_json"])
            audience_context = plan_payload.get("audience_model") or {}
            social_reaction_simulation = build_social_reaction_simulation(
                scenarios=reaction_scenarios,
                audience_context=audience_context,
                content_context={
                    "title": title_value,
                    "topic": topic,
                    "hook": hook,
                    "objective": plan_row["objective"],
                },
                platforms=plan_platforms,
                evidence_refs=[item["id"] for item in verified_evidence],
            )
            prediction = payload.get("prediction")
            if not isinstance(prediction, dict):
                prediction = {}
            prediction = dict(prediction)
            if persisted_preflight is not None:
                preflight_scores = persisted_preflight.get("scores") or {}
                normalized_scores = {
                    "topic": float(preflight_scores.get("audience_fit") or 0) * 10,
                    "hook": float(preflight_scores.get("platform_fit") or 0) * 10,
                    "pacing": float(preflight_scores.get("production_feasibility") or 0) * 10,
                    "density": float(preflight_scores.get("evidence_strength") or 0) * 10,
                    "viewpoint": float(preflight_scores.get("strategy_fit") or 0) * 10,
                    "cta": float(preflight_scores.get("audience_fit") or 0) * 10,
                    "sound_fit": float(preflight_scores.get("sound_fit") or 0) * 10,
                }
                prediction["confidence"] = str(prediction.get("confidence") or "low")
                prediction["platforms"] = list(
                    prediction.get("platforms") or plan_platforms
                )
                prediction["basis"] = list(
                    dict.fromkeys(
                        [
                            *(prediction.get("basis") or []),
                            f"preflight:{persisted_preflight['id']}",
                            str(persisted_preflight.get("formula_version") or ""),
                        ]
                    )
                )
                prediction = attach_prediction_dimensions(
                    prediction,
                    kind=production_kind,
                    scores=normalized_scores,
                    evidence_ready=bool(verified_evidence),
                )
            prediction["social_reaction_simulation"] = social_reaction_simulation
            prediction["social_system_simulation"] = build_social_system_simulation(
                prediction=prediction,
                reaction=social_reaction_simulation,
                plan=plan_payload,
            )
            payload["prediction"] = prediction
            sound_plan = payload.get("sound_plan")
            if production_kind == "faceless_video":
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
                audience_context=audience_context,
                evidence=verified_evidence,
                structure={
                    "content_schema": payload.get("schema") or asset_type,
                    "platform_variant_keys": sorted(platform_variants.keys()),
                },
                material_context=payload.get("material_manifest") or {},
                sound_context=sound_plan if isinstance(sound_plan, dict) else None,
                prediction=prediction,
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

    def record_human_review(
        self,
        *,
        asset_id: str,
        user_id: str,
        account_id: str,
        decision: str,
        note: str = "",
        confirmed: bool,
    ) -> dict[str, Any]:
        """Persist the user's decision for this immutable asset version."""

        if confirmed is not True:
            raise ValueError("explicit human review confirmation is required")
        decision_value = str(decision or "").strip().lower()
        if decision_value not in {"accepted", "changes_requested"}:
            raise ValueError("human review decision must be accepted or changes_requested")
        note_value = str(note or "").strip()[:2_000]
        if decision_value == "changes_requested" and not note_value:
            raise ValueError("changes_requested requires a review note")
        with self._transaction() as db:
            row = db.execute(
                """SELECT status,human_review_status,human_review_note FROM content_assets
                WHERE id=? AND user_id=? AND account_id=?""",
                (asset_id, user_id, account_id),
            ).fetchone()
            if row is None:
                raise KeyError("content asset not found in account scope")
            if row["status"] in {"superseded", "approved", "published", "archived"}:
                raise ValueError(f"content asset cannot be reviewed from {row['status']}")
            if decision_value == "accepted" and row["status"] != "review_ready":
                raise ValueError("only a review_ready asset can be accepted by the user")
            if (
                row["human_review_status"] != decision_value
                or row["human_review_note"] != note_value
            ):
                reviewed_at = _now()
                db.execute(
                    """UPDATE content_assets
                    SET human_review_status=?,human_review_note=?,human_reviewed_at=?,updated_at=?
                    WHERE id=? AND user_id=? AND account_id=?""",
                    (
                        decision_value,
                        note_value,
                        reviewed_at,
                        reviewed_at,
                        asset_id,
                        user_id,
                        account_id,
                    ),
                )
        return self.get(asset_id=asset_id, user_id=user_id, account_id=account_id)

    def archive(
        self,
        *,
        asset_id: str,
        user_id: str,
        account_id: str,
        confirmed: bool,
    ) -> dict[str, Any]:
        """Soft-archive an unfinished content asset without deleting its history."""

        if confirmed is not True:
            raise ValueError("explicit archive confirmation is required")
        now = _now()
        with self._transaction() as db:
            row = db.execute(
                """SELECT status,human_review_status,content_json FROM content_assets
                WHERE id=? AND user_id=? AND account_id=?""",
                (asset_id, user_id, account_id),
            ).fetchone()
            if row is None:
                raise KeyError("content asset not found in account scope")
            if row["status"] == "archived":
                return self.get(
                    asset_id=asset_id,
                    user_id=user_id,
                    account_id=account_id,
                )
            if row["status"] not in {"draft", "review_ready"}:
                raise ValueError(
                    f"content asset cannot be archived from {row['status']}"
                )
            if row["human_review_status"] == "accepted":
                raise ValueError("an accepted content asset is not a draft")
            db.execute(
                """UPDATE content_assets
                SET status='archived',archived_from_status=?,archived_at=?,updated_at=?
                WHERE id=? AND user_id=? AND account_id=?""",
                (row["status"], now, now, asset_id, user_id, account_id),
            )
            _archive_plan(
                db,
                row["content_json"],
                user_id=user_id,
                account_id=account_id,
                now=now,
            )
        return self.get(asset_id=asset_id, user_id=user_id, account_id=account_id)

    def restore_archived(
        self,
        *,
        asset_id: str,
        user_id: str,
        account_id: str,
    ) -> dict[str, Any]:
        """Restore a soft-archived draft to its exact pre-archive status."""

        now = _now()
        with self._transaction() as db:
            row = db.execute(
                """SELECT status,archived_from_status,content_json FROM content_assets
                WHERE id=? AND user_id=? AND account_id=?""",
                (asset_id, user_id, account_id),
            ).fetchone()
            if row is None:
                raise KeyError("content asset not found in account scope")
            if row["status"] != "archived":
                raise ValueError("only an archived content asset can be restored")
            restored_status = str(row["archived_from_status"] or "draft")
            if restored_status not in {"draft", "review_ready"}:
                restored_status = "draft"
            db.execute(
                """UPDATE content_assets
                SET status=?,archived_from_status='',archived_at=NULL,updated_at=?
                WHERE id=? AND user_id=? AND account_id=?""",
                (restored_status, now, asset_id, user_id, account_id),
            )
            _restore_plan(
                db,
                row["content_json"],
                user_id=user_id,
                account_id=account_id,
                asset_status=restored_status,
                now=now,
            )
        return self.get(asset_id=asset_id, user_id=user_id, account_id=account_id)

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
            query += " AND status NOT IN ('superseded','archived')"
        if platform:
            if platform not in {"multi_article", "multi_platform"}:
                platform = normalize_platform_id(platform)
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

    def list_summaries(
        self,
        *,
        user_id: str,
        account_id: str,
        status: str | None = None,
        platform: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Return bounded review metadata without loading full draft bodies into UI."""

        result = self.list(
            user_id=user_id,
            account_id=account_id,
            status=status,
            platform=platform,
            limit=limit,
        )
        summaries = []
        for asset in result["assets"]:
            content = asset.get("content") if isinstance(asset.get("content"), dict) else {}
            validation = (
                content.get("validation")
                if isinstance(content.get("validation"), dict)
                else {}
            )
            variants = (
                content.get("platform_variants")
                if isinstance(content.get("platform_variants"), dict)
                else {}
            )
            summaries.append(
                {
                    key: asset.get(key)
                    for key in (
                        "id",
                        "account_id",
                        "platform",
                        "title",
                        "type",
                        "status",
                        "parent_id",
                        "experiment_id",
                        "topic",
                        "hook",
                        "version",
                        "human_review_status",
                        "human_review_note",
                        "human_reviewed_at",
                        "created_at",
                        "updated_at",
                    )
                }
                | {
                    "production_kind": content.get("_production_kind")
                    or content.get("production_kind"),
                    "review_status": content.get("review_status"),
                    "validation_ready": validation.get("ready"),
                    "validation_issue_count": len(validation.get("issues") or []),
                    "target_platforms": list(variants),
                }
            )
        return {**result, "assets": summaries}

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
                    human_review_status TEXT NOT NULL DEFAULT 'pending',
                    human_review_note TEXT NOT NULL DEFAULT '',
                    human_reviewed_at TEXT,
                    archived_from_status TEXT NOT NULL DEFAULT '',
                    archived_at TEXT,
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
            migrated_status = (
                row["status"]
                if row["status"] in {"archived", "superseded", "approved", "published"}
                else "review_ready"
                if ready
                else "draft"
            )
            db.execute(
                """UPDATE content_assets
                SET content_json=?, status=?, version=version+1, updated_at=?
                WHERE id=?""",
                (encoded, migrated_status, now, row["id"]),
            )
            plan_id = previous.get("_production_plan_id")
            if plan_id and migrated_status in {"draft", "review_ready"}:
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


def _production_plan_id(content_json: str) -> str:
    try:
        content = json.loads(content_json or "{}")
    except (TypeError, ValueError):
        return ""
    if not isinstance(content, dict):
        return ""
    return str(content.get("_production_plan_id") or "").strip()


def _validate_cross_platform_variants(
    content: dict[str, Any], *, target_platforms: list[str]
) -> dict[str, dict[str, Any]]:
    """Require one substantive, platform-native variant per campaign target."""

    raw_variants = content.get("platform_variants")
    if not isinstance(raw_variants, dict):
        raise ValueError("cross-platform campaign requires platform_variants")
    expected = normalize_platforms(target_platforms)
    supplied = {normalize_platform_id(key) for key in raw_variants}
    if supplied != set(expected):
        missing = sorted(set(expected) - supplied)
        extra = sorted(supplied - set(expected))
        raise ValueError(
            "cross-platform campaign variants must exactly match its plan"
            f"; missing={missing}; extra={extra}"
        )
    normalized: dict[str, dict[str, Any]] = {}
    fingerprints: dict[str, str] = {}
    content_fields = {
        "body_markdown",
        "caption",
        "carousel_cards",
        "outline",
        "script",
        "short_text",
        "thread",
        "title",
        "voiceover",
    }
    for platform in expected:
        raw = raw_variants.get(platform)
        if not isinstance(raw, dict):
            raise ValueError(f"platform variant must be an object: {platform}")
        format_value = str(raw.get("format") or "").strip()
        if not format_value:
            raise ValueError(f"platform variant requires format: {platform}")
        if not any(raw.get(field) for field in content_fields):
            raise ValueError(f"platform variant has no substantive content: {platform}")
        adaptation = raw.get("adaptation_basis")
        if not isinstance(adaptation, dict) or not all(
            str(adaptation.get(field) or "").strip()
            for field in ("audience_intent", "opening", "structure", "cta")
        ):
            raise ValueError(
                f"platform variant requires audience/opening/structure/cta adaptation basis: {platform}"
            )
        value = dict(raw)
        value["platform"] = platform
        value["format"] = format_value[:80]
        normalized[platform] = value
        fingerprints[platform] = json.dumps(
            {
                key: value.get(key)
                for key in sorted(content_fields)
                if value.get(key)
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    if len(set(fingerprints.values())) != len(fingerprints):
        raise ValueError("cross-platform campaign variants must be platform-distinct")
    return normalized


def _archive_plan(
    db: sqlite3.Connection,
    content_json: str,
    *,
    user_id: str,
    account_id: str,
    now: str,
) -> None:
    plan_id = _production_plan_id(content_json)
    if plan_id:
        db.execute(
            """UPDATE content_production_plans
            SET status='archived',updated_at=?
            WHERE id=? AND user_id=? AND account_id=?""",
            (now, plan_id, user_id, account_id),
        )


def _restore_plan(
    db: sqlite3.Connection,
    content_json: str,
    *,
    user_id: str,
    account_id: str,
    asset_status: str,
    now: str,
) -> None:
    plan_id = _production_plan_id(content_json)
    if plan_id:
        db.execute(
            """UPDATE content_production_plans
            SET status=?,updated_at=?
            WHERE id=? AND user_id=? AND account_id=?""",
            (
                "review_ready" if asset_status == "review_ready" else "draft_created",
                now,
                plan_id,
                user_id,
                account_id,
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
    elif mode in {"custom_licensed", "original_music"}:
        music_asset_id = str(value.get("music_asset_id") or "").strip()
        if music_asset_id:
            result["music_asset_id"] = music_asset_id[:160]
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
