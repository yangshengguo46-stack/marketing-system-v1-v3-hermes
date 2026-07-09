"""项目目录布局 + 画布持久化 —— ADR v2 决策 3 / 决策 8。

目录布局（文件即项目，可拷走/备份/迁移）：

    <root>/<project_id>/
        project.json     画布本体（schema.Project 序列化）
        script.md        剧本全文
        frames/          资产图 / 分镜图
        videos/          Seedance 片段（含替身试拍）
        audio/           配音 / 音效 / BGM
        final/           v0 样片、v1+ 成片

写入原则：原子写（tmp + rename），画布是唯一真相源，不做数据库镜像
（SQLite 任务索引由 poller 自己维护，仅存 task_id -> project/shot 映射）。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from engine.video_core.schema import Project

SUBDIRS = ("frames", "videos", "audio", "final")


class ProjectStore:
    """画布持久化。已写实，有测试。"""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def project_dir(self, project_id: str) -> Path:
        return self.root / project_id

    def create(self, project: Project) -> Path:
        pdir = self.project_dir(project.id)
        if pdir.exists():
            raise FileExistsError(f"project already exists: {project.id}")
        for sub in SUBDIRS:
            (pdir / sub).mkdir(parents=True, exist_ok=True)
        self.save(project)
        return pdir

    def save(self, project: Project) -> None:
        pdir = self.project_dir(project.id)
        pdir.mkdir(parents=True, exist_ok=True)
        data = project.model_dump_json(indent=2)
        # 原子写：崩溃不留半截 JSON
        fd, tmp = tempfile.mkstemp(dir=pdir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.replace(tmp, pdir / "project.json")
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def load(self, project_id: str) -> Project:
        path = self.project_dir(project_id) / "project.json"
        with open(path, encoding="utf-8") as f:
            return Project.model_validate(json.load(f))

    def exists(self, project_id: str) -> bool:
        return (self.project_dir(project_id) / "project.json").exists()

    def list_projects(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(
            p.name for p in self.root.iterdir()
            if (p / "project.json").exists()
        )

    def save_script(self, project_id: str, script_md: str) -> Path:
        path = self.project_dir(project_id) / "script.md"
        path.write_text(script_md, encoding="utf-8")
        return path

    def load_script(self, project_id: str) -> Optional[str]:
        path = self.project_dir(project_id) / "script.md"
        return path.read_text(encoding="utf-8") if path.exists() else None
