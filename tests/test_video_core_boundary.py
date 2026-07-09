"""架构回归：video_core / video_agents 解耦边界（ADR v2 决策 7）。

规则：
1. engine/video_core 与 engine/video_agents 内禁止 import
   agent_core / marketing_tools / backend / electron
2. video_agents 是纯资产包：不允许出现 .py 文件
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIDEO_CORE = ROOT / "engine" / "video_core"
VIDEO_AGENTS = ROOT / "engine" / "video_agents"

FORBIDDEN = ("agent_core", "marketing_tools", "backend", "electron")
IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([\w.]+)", re.MULTILINE)


def test_video_core_has_no_business_imports():
    violations = []
    for py in VIDEO_CORE.rglob("*.py"):
        for match in IMPORT_RE.finditer(py.read_text(encoding="utf-8")):
            module = match.group(1)
            for bad in FORBIDDEN:
                if module == bad or module.startswith(f"{bad}.") or f".{bad}" in module:
                    violations.append(f"{py.name}: {module}")
    assert not violations, f"video_core 违反解耦边界: {violations}"


def test_video_agents_is_pure_asset_package():
    py_files = list(VIDEO_AGENTS.rglob("*.py"))
    assert not py_files, f"video_agents 必须是纯资产包，发现代码文件: {[p.name for p in py_files]}"


def test_video_agents_roles_complete():
    expected = {"director", "producer", "screenwriter", "editor",
                "art", "cinematographer", "continuity", "sound"}
    dirs = {p.name for p in VIDEO_AGENTS.iterdir() if p.is_dir()}
    assert expected <= dirs, f"缺少角色目录: {expected - dirs}"
    missing_skills = [d for d in expected if not (VIDEO_AGENTS / d / "SKILL.md").exists()]
    assert not missing_skills, f"缺少 SKILL.md: {missing_skills}"
