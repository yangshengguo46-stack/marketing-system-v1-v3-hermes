"""Account-scoped draft-box projection over native content and video owners."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from agent.marketing.data_paths import MarketingDataPaths
from agent.marketing.domains.content_assets import ContentAssetRepository
from agent.marketing.domains.storage import MarketingDomainRepository
from agent.marketing.domains.video_production import VideoProductionRepository


_ACTIVE_CONTENT_STATUSES = {"draft", "review_ready"}
_ACTIVE_VIDEO_STATUSES = {"prepared", "approved", "running", "completed", "failed"}


class DraftBoxRepository(MarketingDomainRepository):
    """Project unfinished work without creating a second lifecycle store."""

    def __init__(self, paths: MarketingDataPaths | None = None):
        super().__init__(paths)
        self.content = ContentAssetRepository(self.paths)
        self.video = VideoProductionRepository(self.paths)

    def list(
        self,
        *,
        user_id: str,
        account_id: str,
        archived: bool = False,
        limit: int = 100,
    ) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 200))
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
                WHERE user_id=? AND account_id=? AND status IN (?,?,?)
                ORDER BY updated_at DESC LIMIT 500""",
                (user_id, account_id, "draft", "review_ready", "archived"),
            ).fetchall()
            video_rows = db.execute(
                """SELECT p.*,s.title AS source_title,
                    o.title AS output_title,o.human_review_status AS output_review_status
                FROM marketing_video_productions p
                LEFT JOIN content_assets s ON s.id=p.source_asset_id
                LEFT JOIN content_assets o ON o.id=p.output_asset_id
                WHERE p.user_id=? AND p.account_id=?
                ORDER BY p.updated_at DESC LIMIT 500""",
                (user_id, account_id),
            ).fetchall()

        items: list[dict[str, Any]] = []
        for row in content_rows:
            if row["id"] in represented_asset_ids:
                continue
            if archived:
                if row["status"] != "archived":
                    continue
            elif row["status"] not in _ACTIVE_CONTENT_STATUSES:
                continue
            if not archived and row["human_review_status"] == "accepted":
                continue
            items.append(_content_item(row))

        for row in video_rows:
            if archived:
                if row["status"] != "archived":
                    continue
            else:
                if row["status"] not in _ACTIVE_VIDEO_STATUSES:
                    continue
                if (
                    row["status"] == "completed"
                    and row["output_review_status"] == "accepted"
                ):
                    continue
            items.append(_video_item(row))

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


def _content_item(row: sqlite3.Row) -> dict[str, Any]:
    try:
        content = json.loads(row["content_json"] or "{}")
    except (TypeError, ValueError):
        content = {}
    production_kind = str(content.get("_production_kind") or "article_soft")
    content_kind = "video_source" if production_kind == "faceless_video" else "article"
    archived = row["status"] == "archived"
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
        "source_asset_id": row["id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "can_resume": not archived,
        "can_archive": not archived,
    }


def _video_item(row: sqlite3.Row) -> dict[str, Any]:
    archived = row["status"] == "archived"
    return {
        "id": row["id"],
        "object_type": "video_production",
        "content_kind": "video",
        "title": row["output_title"] or row["source_title"] or "未命名视频",
        "status": row["status"],
        "previous_status": row["archived_from_status"] if archived else "",
        "version": row["source_asset_version"],
        "human_review_status": row["output_review_status"] or "pending",
        "failure_code": row["failure_code"] or "",
        "source_asset_id": row["source_asset_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "can_resume": not archived,
        "can_archive": not archived and row["status"] != "running",
    }
