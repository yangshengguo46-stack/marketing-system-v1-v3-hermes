"""Read-only projection and draft lifecycle for durable video results.

Video execution is owned exclusively by the official Hermes Kanban pipeline in
``video_kanban.py``.  This module intentionally contains no planning, material
selection, TTS, renderer routing, approval, or render execution path.  It only
keeps historical and official-Kanban results readable by the Desktop, Draft Box
and publishing boundary.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.content_assets import ContentAssetRepository
from agent.marketing.domains.media_assets import MediaAssetRepository
from agent.marketing.domains.storage import MarketingDomainRepository


PRODUCTION_STATUSES = {
    "prepared",
    "approved",
    "running",
    "completed",
    "failed",
    "archived",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        decoded = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _record(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    value["edl"] = _object(value.pop("edl_json", "{}"))
    value["video_ir"] = _object(value.pop("video_ir_json", "{}"))
    value["render_plan"] = _object(value.pop("render_plan_json", "{}"))
    value["receipt"] = _object(value.pop("receipt_json", "{}"))
    return value


def _execution_record(row: sqlite3.Row) -> dict[str, Any]:
    value = dict(row)
    value["model"] = _object(value.pop("model_json", "{}"))
    value["budget"] = _object(value.pop("budget_json", "{}"))
    value["execution"] = _object(value.pop("execution_json", "{}"))
    value["receipt"] = _object(value.pop("receipt_json", "{}"))
    return value


class VideoProductionRepository(MarketingDomainRepository):
    """Project official video results without owning video execution."""

    def __init__(self, paths: MarketingDataPaths | None = None):
        super().__init__(paths)
        self.content = ContentAssetRepository(self.paths)
        self.media = MediaAssetRepository(self.paths)

    def get(
        self, *, production_id: str, user_id: str, account_id: str
    ) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                """SELECT * FROM marketing_video_productions
                WHERE id=? AND user_id=? AND account_id=?""",
                (production_id, user_id, account_id),
            ).fetchone()
        if row is None:
            raise KeyError("video production not found in account scope")
        return _record(row)

    def list(
        self,
        *,
        user_id: str,
        account_id: str,
        status: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        if status and status not in PRODUCTION_STATUSES:
            raise ValueError("unsupported video production status")
        safe_limit = max(1, min(int(limit), 50))
        query = (
            "SELECT * FROM marketing_video_productions "
            "WHERE user_id=? AND account_id=?"
        )
        params: list[Any] = [user_id, account_id]
        if status:
            query += " AND status=?"
            params.append(status)
        else:
            query += " AND status!='archived'"
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(safe_limit)
        with self._connection() as db:
            rows = db.execute(query, params).fetchall()
        return {
            "user_id": user_id,
            "account_id": account_id,
            "productions": [_record(row) for row in rows],
            "total": len(rows),
        }

    def render_readiness(
        self, *, production_id: str, user_id: str, account_id: str
    ) -> dict[str, Any]:
        production = self.get(
            production_id=production_id,
            user_id=user_id,
            account_id=account_id,
        )
        blockers: list[dict[str, str]] = []
        if production["status"] != "completed":
            blockers.append({
                "code": "official_pipeline_incomplete",
                "message": "官方 Hermes 视频任务尚未形成通过审查的成片",
            })
        if not production.get("final_video_asset_id"):
            blockers.append({
                "code": "final_video_missing",
                "message": "尚未登记官方 Reviewer 验收的成片文件",
            })
        if not production.get("output_asset_id"):
            blockers.append({
                "code": "draft_revision_missing",
                "message": "成片尚未进入草稿箱的人审版本",
            })
        final_asset = None
        if production.get("final_video_asset_id"):
            try:
                final_asset = self.media.get(
                    asset_id=str(production["final_video_asset_id"]),
                    user_id=user_id,
                )
            except KeyError:
                blockers.append({
                    "code": "final_video_unavailable",
                    "message": "登记的成片文件已不可用",
                })
            else:
                if final_asset.get("account_id") not in {None, account_id}:
                    blockers.append({
                        "code": "final_video_scope_mismatch",
                        "message": "成片不属于当前账号作用域",
                    })
                elif not self.media.resolve_local_path(
                    asset_id=final_asset["id"], user_id=user_id
                ):
                    blockers.append({
                        "code": "final_video_file_missing",
                        "message": "成片文件不在本地受管素材库中",
                    })
        return {
            "version": "marketing.video.readiness.v2",
            "owner": "hermes.official.kanban-video-orchestrator",
            "ready": not blockers,
            "render_required": False,
            "voice_required": False,
            "blockers": blockers,
        }

    def list_review_summaries(
        self,
        *,
        user_id: str,
        account_id: str,
        status: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 50))
        execution_statuses = {"preparing", "queued", "blocked", "archived"}
        production_status = status if status not in execution_statuses else None
        productions = (
            self.list(
                user_id=user_id,
                account_id=account_id,
                status=production_status,
                limit=safe_limit,
            )["productions"]
            if status not in execution_statuses
            else []
        )
        summaries = [
            self._production_summary(item, user_id=user_id, account_id=account_id)
            for item in productions
        ]
        from agent.marketing.domains.video_kanban import VideoKanbanExecutionRepository

        VideoKanbanExecutionRepository(self.paths).reconcile_scope(
            user_id=user_id, account_id=account_id
        )
        if not status or status in execution_statuses:
            execution_filter = (
                "AND status=?" if status in execution_statuses else
                "AND status IN ('preparing','queued','blocked')"
            )
            execution_params: list[Any] = [user_id, account_id]
            if status in execution_statuses:
                execution_params.append(status)
            execution_params.append(safe_limit)
            with self._connection() as db:
                rows = db.execute(
                    f"""SELECT * FROM marketing_video_executions
                    WHERE user_id=? AND account_id=?
                      {execution_filter}
                      AND (production_id IS NULL OR production_id='')
                    ORDER BY updated_at DESC LIMIT ?""",
                    execution_params,
                ).fetchall()
            summaries.extend(self._execution_summary(_execution_record(row)) for row in rows)
        summaries.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        summaries = summaries[:safe_limit]
        return {
            "user_id": user_id,
            "account_id": account_id,
            "productions": summaries,
            "total": len(summaries),
        }

    def get_review_projection(
        self,
        *,
        production_id: str,
        user_id: str,
        account_id: str,
    ) -> dict[str, Any]:
        try:
            production = self.get(
                production_id=production_id,
                user_id=user_id,
                account_id=account_id,
            )
        except KeyError:
            return self._execution_projection(
                execution_id=production_id,
                user_id=user_id,
                account_id=account_id,
            )
        try:
            source = self.content.get(
                asset_id=production["source_asset_id"],
                user_id=user_id,
                account_id=account_id,
            )
        except KeyError:
            source = {}
        output = None
        if production.get("output_asset_id"):
            try:
                output = self.content.get(
                    asset_id=production["output_asset_id"],
                    user_id=user_id,
                    account_id=account_id,
                )
            except KeyError:
                output = None
        media_assets = self._media_projection(
            production=production,
            user_id=user_id,
            account_id=account_id,
        )
        readiness = self.render_readiness(
            production_id=production_id,
            user_id=user_id,
            account_id=account_id,
        )
        return {
            "summary": self._review_summary(
                production, source, output or {}, readiness=readiness
            ),
            "production": {
                key: value
                for key, value in production.items()
                if key not in {"idempotency_key", "user_id", "account_id"}
            },
            "source_asset": source,
            "output_asset": output,
            "media_assets": media_assets,
            "material_searches": [],
            "voice_job": None,
            "readiness": readiness,
        }

    def archive(
        self,
        *,
        production_id: str,
        user_id: str,
        account_id: str,
        confirmed: bool,
    ) -> dict[str, Any]:
        if confirmed is not True:
            raise ValueError("explicit archive confirmation is required")
        now = _now()
        with self._transaction() as db:
            row = db.execute(
                """SELECT * FROM marketing_video_productions
                WHERE id=? AND user_id=? AND account_id=?""",
                (production_id, user_id, account_id),
            ).fetchone()
            if row is None:
                raise KeyError("video production not found in account scope")
            if row["status"] == "archived":
                return _record(row)
            if row["status"] == "running":
                raise ValueError("a running video production cannot be archived")
            if row["status"] == "completed" and row["output_asset_id"]:
                output = db.execute(
                    """SELECT human_review_status FROM content_assets
                    WHERE id=? AND user_id=? AND account_id=?""",
                    (row["output_asset_id"], user_id, account_id),
                ).fetchone()
                if output is not None and output["human_review_status"] == "accepted":
                    raise ValueError("an accepted video production is not a draft")
            db.execute(
                """UPDATE marketing_video_productions
                SET status='archived',archived_from_status=?,archived_at=?,updated_at=?
                WHERE id=? AND user_id=? AND account_id=?""",
                (row["status"], now, now, production_id, user_id, account_id),
            )
            _archive_related_content(
                db,
                asset_ids=(row["source_asset_id"], row["output_asset_id"]),
                user_id=user_id,
                account_id=account_id,
                now=now,
            )
        return self.get(
            production_id=production_id, user_id=user_id, account_id=account_id
        )

    def restore_archived(
        self,
        *,
        production_id: str,
        user_id: str,
        account_id: str,
    ) -> dict[str, Any]:
        now = _now()
        with self._transaction() as db:
            row = db.execute(
                """SELECT * FROM marketing_video_productions
                WHERE id=? AND user_id=? AND account_id=?""",
                (production_id, user_id, account_id),
            ).fetchone()
            if row is None:
                raise KeyError("video production not found in account scope")
            if row["status"] != "archived":
                raise ValueError("only an archived video production can be restored")
            restored = str(row["archived_from_status"] or "completed")
            if restored not in PRODUCTION_STATUSES - {"archived"}:
                restored = "completed"
            db.execute(
                """UPDATE marketing_video_productions
                SET status=?,archived_from_status='',archived_at=NULL,updated_at=?
                WHERE id=? AND user_id=? AND account_id=?""",
                (restored, now, production_id, user_id, account_id),
            )
            _restore_related_content(
                db,
                asset_ids=(row["source_asset_id"], row["output_asset_id"]),
                user_id=user_id,
                account_id=account_id,
                now=now,
            )
        return self.get(
            production_id=production_id, user_id=user_id, account_id=account_id
        )

    def _production_summary(
        self, production: dict[str, Any], *, user_id: str, account_id: str
    ) -> dict[str, Any]:
        try:
            source = self.content.get(
                asset_id=production["source_asset_id"],
                user_id=user_id,
                account_id=account_id,
            )
        except KeyError:
            source = {}
        output = {}
        if production.get("output_asset_id"):
            try:
                output = self.content.get(
                    asset_id=production["output_asset_id"],
                    user_id=user_id,
                    account_id=account_id,
                )
            except KeyError:
                output = {}
        readiness = self.render_readiness(
            production_id=production["id"],
            user_id=user_id,
            account_id=account_id,
        )
        return self._review_summary(production, source, output, readiness=readiness)

    def _media_projection(
        self,
        *,
        production: dict[str, Any],
        user_id: str,
        account_id: str,
    ) -> list[dict[str, Any]]:
        asset_ids: list[str] = []
        final_id = str(production.get("final_video_asset_id") or "").strip()
        if final_id:
            asset_ids.append(final_id)
        for scene in (production.get("video_ir") or {}).get("scenes") or []:
            if not isinstance(scene, dict):
                continue
            for visual in scene.get("visuals") or []:
                if isinstance(visual, dict) and visual.get("media_asset_id"):
                    asset_ids.append(str(visual["media_asset_id"]))
        results = []
        for asset_id in dict.fromkeys(asset_ids):
            try:
                asset = self.media.get(asset_id=asset_id, user_id=user_id)
            except KeyError:
                continue
            if asset.get("account_id") not in {None, account_id}:
                continue
            results.append({
                "id": asset["id"],
                "name": asset["name"],
                "media_type": asset["media_type"],
                "role": asset["role"],
                "mime_type": asset["mime_type"],
                "rights_status": asset["rights_status"],
                "source_type": asset["source_type"],
                "provider": asset["provider"],
                "size_bytes": asset["size_bytes"],
                "playback_path": self.media.resolve_local_path(
                    asset_id=asset_id, user_id=user_id
                ),
            })
        return results

    def _execution_projection(
        self, *, execution_id: str, user_id: str, account_id: str
    ) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                """SELECT * FROM marketing_video_executions
                WHERE id=? AND user_id=? AND account_id=?""",
                (execution_id, user_id, account_id),
            ).fetchone()
        if row is None:
            raise KeyError("video production not found in account scope")
        execution = _execution_record(row)
        summary = self._execution_summary(execution)
        return {
            "summary": summary,
            "production": {
                "id": execution["id"],
                "status": execution["status"],
                "video_ir": {
                    "version": "marketing.video.ir.v2",
                    "canvas": summary["canvas"],
                    "scenes": [],
                    "captions": [],
                    "audio": {},
                },
                "render_plan": {
                    "version": "marketing.video.render_plan.v2",
                    "owner": "hermes.official.kanban-video-orchestrator",
                    "executable": False,
                    "scenes": [],
                },
                "failure_code": execution.get("failure_code"),
            },
            "source_asset": {},
            "output_asset": None,
            "media_assets": [],
            "material_searches": [],
            "voice_job": None,
            "readiness": summary["readiness"],
            "execution": execution,
        }

    @staticmethod
    def _execution_summary(execution: dict[str, Any]) -> dict[str, Any]:
        context = execution.get("execution") or {}
        width, height = _resolution(context.get("resolution"))
        status = "failed" if execution.get("status") == "blocked" else "running"
        blocker = (
            str(execution.get("failure_code") or "官方 Hermes 视频任务已阻断")
            if execution.get("status") == "blocked"
            else "官方 Hermes 视频团队正在编导、找素材、配音、剪辑和审片"
        )
        return {
            "id": execution["id"],
            "source_asset_id": "",
            "output_asset_id": None,
            "final_video_asset_id": execution.get("final_video_asset_id"),
            "title": str(context.get("topic") or "视频制作任务"),
            "status": status,
            "failure_code": execution.get("failure_code"),
            "canvas": {"width": width, "height": height, "fps": 30},
            "duration": 0,
            "scene_count": 0,
            "renderers": ["Hermes Official Kanban"],
            "readiness": {
                "version": "marketing.video.readiness.v2",
                "owner": "hermes.official.kanban-video-orchestrator",
                "ready": False,
                "render_required": False,
                "voice_required": False,
                "blockers": [{"code": execution["status"], "message": blocker}],
            },
            "human_review_status": "pending",
            "created_at": execution["created_at"],
            "updated_at": execution["updated_at"],
            "settled_at": execution.get("settled_at"),
        }

    @staticmethod
    def _review_summary(
        production: dict[str, Any],
        source: dict[str, Any],
        output: dict[str, Any],
        *,
        readiness: dict[str, Any],
    ) -> dict[str, Any]:
        video_ir = production.get("video_ir") or {}
        canvas = video_ir.get("canvas") or {}
        scenes = [item for item in video_ir.get("scenes") or [] if isinstance(item, dict)]
        duration = max(
            [float(item.get("end_seconds") or 0) for item in scenes]
            + [sum(float(item.get("duration") or 0) for item in scenes)]
        )
        render_plan = production.get("render_plan") or {}
        renderers = list(dict.fromkeys(
            [
                str(item.get("renderer") or "")
                for item in render_plan.get("scenes") or []
                if isinstance(item, dict) and item.get("renderer")
            ]
            + ([str(render_plan.get("owner"))] if render_plan.get("owner") else [])
        ))
        return {
            "id": production["id"],
            "source_asset_id": production["source_asset_id"],
            "output_asset_id": production.get("output_asset_id"),
            "final_video_asset_id": production.get("final_video_asset_id"),
            "title": source.get("title") or source.get("topic") or "未命名素材视频",
            "status": production["status"],
            "failure_code": production.get("failure_code"),
            "canvas": {
                "width": int(canvas.get("width") or 1080),
                "height": int(canvas.get("height") or 1920),
                "fps": int(canvas.get("fps") or 30),
            },
            "duration": round(duration, 3),
            "scene_count": len(scenes),
            "renderers": renderers,
            "readiness": readiness,
            "human_review_status": output.get("human_review_status") or "pending",
            "created_at": production["created_at"],
            "updated_at": production["updated_at"],
            "settled_at": production.get("settled_at"),
        }


def _resolution(value: Any) -> tuple[int, int]:
    try:
        width, height = str(value or "").lower().split("x", 1)
        return int(width), int(height)
    except (TypeError, ValueError):
        return 1080, 1920


def _content_plan_id(content_json: str) -> str:
    return str(_object(content_json).get("_production_plan_id") or "").strip()


def _archive_related_content(
    db: sqlite3.Connection,
    *,
    asset_ids: Iterable[str | None],
    user_id: str,
    account_id: str,
    now: str,
) -> None:
    for asset_id in dict.fromkeys(item for item in asset_ids if item):
        row = db.execute(
            """SELECT status,content_json FROM content_assets
            WHERE id=? AND user_id=? AND account_id=?""",
            (asset_id, user_id, account_id),
        ).fetchone()
        if row is None or row["status"] not in {"draft", "review_ready"}:
            continue
        db.execute(
            """UPDATE content_assets
            SET status='archived',archived_from_status=?,archived_at=?,updated_at=?
            WHERE id=? AND user_id=? AND account_id=?""",
            (row["status"], now, now, asset_id, user_id, account_id),
        )
        plan_id = _content_plan_id(row["content_json"])
        if plan_id:
            db.execute(
                """UPDATE content_production_plans SET status='archived',updated_at=?
                WHERE id=? AND user_id=? AND account_id=?""",
                (now, plan_id, user_id, account_id),
            )


def _restore_related_content(
    db: sqlite3.Connection,
    *,
    asset_ids: Iterable[str | None],
    user_id: str,
    account_id: str,
    now: str,
) -> None:
    for asset_id in dict.fromkeys(item for item in asset_ids if item):
        row = db.execute(
            """SELECT status,archived_from_status,content_json FROM content_assets
            WHERE id=? AND user_id=? AND account_id=?""",
            (asset_id, user_id, account_id),
        ).fetchone()
        if row is None or row["status"] != "archived":
            continue
        restored = str(row["archived_from_status"] or "draft")
        if restored not in {"draft", "review_ready"}:
            restored = "draft"
        db.execute(
            """UPDATE content_assets
            SET status=?,archived_from_status='',archived_at=NULL,updated_at=?
            WHERE id=? AND user_id=? AND account_id=?""",
            (restored, now, asset_id, user_id, account_id),
        )
        plan_id = _content_plan_id(row["content_json"])
        if plan_id:
            db.execute(
                """UPDATE content_production_plans SET status=?,updated_at=?
                WHERE id=? AND user_id=? AND account_id=?""",
                (
                    "review_ready" if restored == "review_ready" else "draft_created",
                    now,
                    plan_id,
                    user_id,
                    account_id,
                ),
            )
