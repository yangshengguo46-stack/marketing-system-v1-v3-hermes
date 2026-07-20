"""Account-scoped draft-box projection over native content and video owners."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.content_assets import ContentAssetRepository
from agent.marketing.domains.storage import MarketingDomainRepository
from agent.marketing.domains.video_production import VideoProductionRepository
from agent.marketing.domains.video_kanban import VideoKanbanExecutionRepository


_ACTIVE_CONTENT_STATUSES = {"draft", "review_ready", "approved"}
_ACTIVE_VIDEO_STATUSES = {"prepared", "approved", "running", "completed", "failed"}


class DraftBoxRepository(MarketingDomainRepository):
    """Project unfinished work without creating a second lifecycle store."""

    def __init__(self, paths: MarketingDataPaths | None = None):
        super().__init__(paths)
        self.content = ContentAssetRepository(self.paths)
        self.video = VideoProductionRepository(self.paths)
        self.video_execution = VideoKanbanExecutionRepository(self.paths)

    def list(
        self,
        *,
        user_id: str,
        account_id: str,
        archived: bool = False,
        limit: int = 100,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 200))
        self.video_execution.reconcile_scope(
            user_id=user_id, account_id=account_id
        )
        with self._connection() as db:
            represented_asset_ids = {
                str(value)
                for row in db.execute(
                    """SELECT source_asset_id,output_asset_id
                    FROM marketing_video_productions
                    WHERE user_id=? AND account_id=?""",
                    (user_id, account_id),
                ).fetchall()
                for value in (row["source_asset_id"], row["output_asset_id"])
                if value
            }
            content_rows = db.execute(
                """SELECT * FROM content_assets
                WHERE user_id=? AND account_id=? AND status IN (?,?,?,?)
                ORDER BY updated_at DESC LIMIT 500""",
                (
                    user_id,
                    account_id,
                    "draft",
                    "review_ready",
                    "approved",
                    "archived",
                ),
            ).fetchall()
            video_rows = db.execute(
                """SELECT p.*,s.title AS source_title,
                    o.title AS output_title,o.status AS output_status,
                    o.human_review_status AS output_review_status
                FROM marketing_video_productions p
                LEFT JOIN content_assets s ON s.id=p.source_asset_id
                LEFT JOIN content_assets o ON o.id=p.output_asset_id
                WHERE p.user_id=? AND p.account_id=?
                ORDER BY p.updated_at DESC LIMIT 500""",
                (user_id, account_id),
            ).fetchall()
            execution_rows = db.execute(
                """SELECT * FROM marketing_video_executions
                WHERE user_id=? AND account_id=?
                  AND (production_id IS NULL OR production_id='')
                ORDER BY updated_at DESC LIMIT 500""",
                (user_id, account_id),
            ).fetchall()
            publish_action_rows = db.execute(
                """SELECT id,asset_id,platform,status,failure_code,updated_at
                FROM marketing_publish_actions
                WHERE user_id=? AND account_id=?
                ORDER BY updated_at DESC""",
                (user_id, account_id),
            ).fetchall()

        publish_actions_by_asset: dict[str, list[dict[str, Any]]] = {}
        for row in publish_action_rows:
            publish_actions_by_asset.setdefault(str(row["asset_id"]), []).append(
                {
                    "id": row["id"],
                    "platform": row["platform"],
                    "status": row["status"],
                    "failure_code": row["failure_code"] or "",
                    "updated_at": row["updated_at"],
                }
            )

        items: list[dict[str, Any]] = []
        for row in content_rows:
            if row["id"] in represented_asset_ids:
                continue
            if archived:
                if row["status"] != "archived":
                    continue
            elif row["status"] not in _ACTIVE_CONTENT_STATUSES:
                continue
            items.append(
                _content_item(
                    row,
                    publish_actions=publish_actions_by_asset.get(str(row["id"]), []),
                )
            )

        for row in video_rows:
            if archived:
                if row["status"] != "archived":
                    continue
            else:
                if row["status"] not in _ACTIVE_VIDEO_STATUSES:
                    continue
                if row["output_status"] == "published":
                    continue
            try:
                readiness = self.video.render_readiness(
                    production_id=str(row["id"]),
                    user_id=user_id,
                    account_id=account_id,
                )
            except (KeyError, ValueError):
                readiness = {
                    "ready": False,
                    "blockers": [{
                        "code": "readiness_unavailable",
                        "message": "视频生产就绪状态无法核验",
                    }],
                }
            items.append(
                _video_item(
                    row,
                    readiness=readiness,
                    publish_actions=publish_actions_by_asset.get(
                        str(row["output_asset_id"] or ""), []
                    ),
                )
            )

        for row in execution_rows:
            if archived:
                if row["status"] != "archived":
                    continue
            elif row["status"] not in {"preparing", "queued", "blocked"}:
                continue
            items.append(_video_execution_item(row))

        items.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        bounded = items[:safe_limit]
        return {
            "user_id": user_id,
            "account_id": account_id,
            "archived": archived,
            "items": bounded,
            "total": len(bounded),
        }

    def archive(
        self,
        *,
        object_type: str,
        object_id: str,
        user_id: str,
        account_id: str,
        confirmed: bool,
    ) -> dict[str, Any]:
        if object_type == "content_asset":
            self._require_standalone_content(
                object_id=object_id,
                user_id=user_id,
                account_id=account_id,
            )
            item = self.content.archive(
                asset_id=object_id,
                user_id=user_id,
                account_id=account_id,
                confirmed=confirmed,
            )
        elif object_type == "video_production":
            item = self.video.archive(
                production_id=object_id,
                user_id=user_id,
                account_id=account_id,
                confirmed=confirmed,
            )
        elif object_type == "video_execution":
            item = self.video_execution.archive_blocked(
                execution_id=object_id,
                user_id=user_id,
                account_id=account_id,
                confirmed=confirmed,
            )
        else:
            raise ValueError("unsupported draft object type")
        return {"operation": "archived", "object_type": object_type, "item": item}

    def restore(
        self,
        *,
        object_type: str,
        object_id: str,
        user_id: str,
        account_id: str,
    ) -> dict[str, Any]:
        if object_type == "content_asset":
            self._require_standalone_content(
                object_id=object_id,
                user_id=user_id,
                account_id=account_id,
            )
            item = self.content.restore_archived(
                asset_id=object_id,
                user_id=user_id,
                account_id=account_id,
            )
        elif object_type == "video_production":
            item = self.video.restore_archived(
                production_id=object_id,
                user_id=user_id,
                account_id=account_id,
            )
        elif object_type == "video_execution":
            item = self.video_execution.restore_archived(
                execution_id=object_id,
                user_id=user_id,
                account_id=account_id,
            )
        else:
            raise ValueError("unsupported draft object type")
        return {"operation": "restored", "object_type": object_type, "item": item}

    def _require_standalone_content(
        self,
        *,
        object_id: str,
        user_id: str,
        account_id: str,
    ) -> None:
        with self._connection() as db:
            represented = db.execute(
                """SELECT 1 FROM marketing_video_productions
                WHERE user_id=? AND account_id=?
                  AND (source_asset_id=? OR output_asset_id=?)
                LIMIT 1""",
                (user_id, account_id, object_id, object_id),
            ).fetchone()
        if represented is not None:
            raise ValueError("video-owned content must be managed through its production")


def _content_item(
    row: sqlite3.Row, *, publish_actions: list[dict[str, Any]]
) -> dict[str, Any]:
    try:
        content = json.loads(row["content_json"] or "{}")
    except (TypeError, ValueError):
        content = {}
    production_kind = str(content.get("_production_kind") or "article_soft")
    content_kind = "video_source" if production_kind == "faceless_video" else "article"
    archived = row["status"] == "archived"
    accepted = row["human_review_status"] == "accepted"
    action_statuses = {str(action["status"]) for action in publish_actions}
    return {
        "id": row["id"],
        "object_type": "content_asset",
        "content_kind": content_kind,
        "title": row["title"],
        "status": row["status"],
        "previous_status": row["archived_from_status"] if archived else "",
        "version": row["version"],
        "human_review_status": row["human_review_status"],
        "failure_code": "",
        "workflow_stage": _workflow_stage(
            archived=archived,
            accepted=accepted,
            native_status=str(row["status"]),
            publish_action_statuses=action_statuses,
        ),
        "publish_asset_id": row["id"] if accepted and not archived else "",
        "publish_actions": publish_actions,
        "source_asset_id": row["id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "can_resume": not archived,
        "can_archive": not archived and not accepted and row["status"] != "approved",
        "can_prepare_publish": accepted
        and not archived
        and not action_statuses.intersection({"executing", "unknown", "published"}),
    }


def _video_item(
    row: sqlite3.Row,
    *,
    readiness: dict[str, Any],
    publish_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    archived = row["status"] == "archived"
    accepted = row["output_review_status"] == "accepted"
    action_statuses = {str(action["status"]) for action in publish_actions}
    publish_failure = next(
        (
            str(action.get("failure_code") or "")
            for action in publish_actions
            if action.get("failure_code")
        ),
        "",
    )
    readiness_blocker = next(iter(readiness.get("blockers") or []), {})
    publish_ready = readiness.get("ready") is True
    workflow_stage = (
        "production_blocked"
        if accepted and not publish_ready
        else _workflow_stage(
            archived=archived,
            accepted=accepted,
            native_status=str(row["status"]),
            publish_action_statuses=action_statuses,
        )
    )
    return {
        "id": row["id"],
        "object_type": "video_production",
        "content_kind": "video",
        "title": row["output_title"] or row["source_title"] or "未命名视频",
        "status": row["status"],
        "previous_status": row["archived_from_status"] if archived else "",
        "version": row["source_asset_version"],
        "human_review_status": row["output_review_status"] or "pending",
        "failure_code": (
            row["failure_code"]
            or publish_failure
            or str(readiness_blocker.get("code") or "")
        ),
        "workflow_stage": workflow_stage,
        "readiness": readiness,
        "publish_asset_id": (
            row["output_asset_id"] if accepted and publish_ready and not archived else ""
        ),
        "publish_actions": publish_actions,
        "source_asset_id": row["source_asset_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "can_resume": not archived,
        "can_archive": not archived and row["status"] != "running" and not accepted,
        "can_prepare_publish": accepted
        and publish_ready
        and not archived
        and row["output_status"] != "published"
        and not action_statuses.intersection({"executing", "unknown", "published"}),
    }


def _video_execution_item(row: sqlite3.Row) -> dict[str, Any]:
    try:
        context = json.loads(row["execution_json"] or "{}")
    except (TypeError, ValueError):
        context = {}
    archived = row["status"] == "archived"
    blocked = row["status"] == "blocked"
    return {
        "id": row["id"],
        "object_type": "video_execution",
        "content_kind": "video",
        "title": str(context.get("topic") or "视频制作任务"),
        "status": row["status"],
        "previous_status": row["archived_from_status"] if archived else "",
        "version": 1,
        "human_review_status": "pending",
        "failure_code": str(row["failure_code"] or ""),
        "workflow_stage": "archived" if archived else ("production_blocked" if blocked else "production"),
        "readiness": {
            "version": "marketing.video.readiness.v2",
            "owner": "hermes.official.kanban-video-orchestrator",
            "ready": False,
            "render_required": False,
            "voice_required": False,
            "blockers": ([{
                "code": "official_pipeline_blocked",
                "message": str(row["failure_code"] or "官方视频管线已阻断"),
            }] if blocked else []),
        },
        "publish_asset_id": "",
        "publish_actions": [],
        "source_asset_id": "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "can_resume": blocked and not archived,
        "can_archive": blocked and not archived,
        "can_prepare_publish": False,
    }


def _workflow_stage(
    *,
    archived: bool,
    accepted: bool,
    native_status: str,
    publish_action_statuses: set[str],
) -> str:
    if archived:
        return "archived"
    if publish_action_statuses.intersection({"executing", "unknown"}):
        return "publishing"
    if publish_action_statuses.intersection({"failed", "cancelled"}):
        return "publish_blocked"
    if accepted:
        return "publish_pending"
    if native_status == "review_ready" or native_status == "completed":
        return "review"
    if native_status in {"prepared", "approved", "running", "failed"}:
        return "production"
    return "drafting"
