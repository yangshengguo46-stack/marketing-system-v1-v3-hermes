"""Skill routing registry for the content production factory.

Hermes already ships many useful skills.  Marketing OS should not let the
agent randomly browse all of them at runtime.  This registry is an auditable
allowlist: each content lane gets a focused set of skills and a reason.

The registry is data-only.  Actual loading remains the Hermes/runtime layer's
job; content plans simply expose which skills should be preloaded or suggested.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

ContentLane = Literal["article_soft", "faceless_video", "premium_human_video"]


@dataclass(frozen=True)
class ContentSkill:
    id: str
    path: str
    role: str
    purpose: str
    lanes: tuple[ContentLane, ...]
    load_policy: Literal["preload", "on_demand"] = "on_demand"
    maturity: Literal["ready", "reference", "experimental"] = "reference"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"lanes": list(self.lanes)}


CONTENT_PRODUCTION_SKILLS: tuple[ContentSkill, ...] = (
    ContentSkill(
        id="content.short_video_script",
        path="runtime/hermes-agent/skills/content-creation/short-video-script/SKILL.md",
        role="screenwriter",
        purpose="短视频脚本结构、开头钩子、旁白拆段。",
        lanes=("faceless_video", "premium_human_video"),
        load_policy="preload",
        maturity="ready",
    ),
    ContentSkill(
        id="content.platform_adapter",
        path="runtime/hermes-agent/skills/content-creation/platform-content-adapter/SKILL.md",
        role="platform_adapter",
        purpose="把父稿改成知乎、公众号、抖音、B站等平台语气和结构。",
        lanes=("article_soft", "faceless_video", "premium_human_video"),
        load_policy="preload",
        maturity="ready",
    ),
    ContentSkill(
        id="content.viral_title",
        path="runtime/hermes-agent/skills/content-creation/viral-title-writer/SKILL.md",
        role="title_writer",
        purpose="生成标题候选，但必须过证据守门和账号调性守门。",
        lanes=("article_soft", "faceless_video"),
        maturity="ready",
    ),
    ContentSkill(
        id="content.analysis",
        path="runtime/hermes-agent/skills/content-creation/content-analysis/SKILL.md",
        role="blind_reviewer",
        purpose="分析内容质量、受众匹配和发布前风险。",
        lanes=("article_soft", "faceless_video", "premium_human_video"),
        load_policy="preload",
        maturity="ready",
    ),
    ContentSkill(
        id="creative.humanizer",
        path="runtime/hermes-agent/skills/creative/humanizer/SKILL.md",
        role="copy_polish",
        purpose="去 AI 味、口语化、压缩啰嗦表达；只改表达不改事实。",
        lanes=("article_soft", "faceless_video"),
        maturity="ready",
    ),
    ContentSkill(
        id="creative.baoyu_infographic",
        path="runtime/hermes-agent/skills/creative/baoyu-infographic/SKILL.md",
        role="code_visual",
        purpose="把框架、数据、流程变成信息图/视觉解释素材，作为代码生成视觉源。",
        lanes=("article_soft", "faceless_video", "premium_human_video"),
        maturity="reference",
    ),
    ContentSkill(
        id="video.director_pipeline",
        path="runtime/hermes-agent/skills/video-production/director-pipeline/SKILL.md",
        role="director",
        purpose="视频项目从 brief 到脚本、素材、剪辑、审片的导演管线。",
        lanes=("faceless_video", "premium_human_video"),
        load_policy="preload",
        maturity="reference",
    ),
    ContentSkill(
        id="video.storyboard_creator",
        path="runtime/hermes-agent/skills/video-production/storyboard-creator/SKILL.md",
        role="storyboard",
        purpose="把脚本拆成分镜和镜头意图，供素材引擎和剪辑引擎使用。",
        lanes=("faceless_video", "premium_human_video"),
        maturity="reference",
    ),
    ContentSkill(
        id="video.voiceover_planner",
        path="runtime/hermes-agent/skills/video-production/voiceover-planner/SKILL.md",
        role="sound",
        purpose="旁白节奏、音色、分段和 TTS 时长反推。",
        lanes=("faceless_video", "premium_human_video"),
        maturity="reference",
    ),
    ContentSkill(
        id="video.shot_design",
        path="runtime/hermes-agent/skills/video-production/shot-design/SKILL.md",
        role="shot_designer",
        purpose="将脚本段落转成镜头规格、画面动作和素材检索意图。",
        lanes=("faceless_video", "premium_human_video"),
        maturity="reference",
    ),
    ContentSkill(
        id="screenwriting.story_router",
        path="runtime/hermes-agent/skills/screenwriting/story-structure-router/SKILL.md",
        role="screenwriter",
        purpose="为软文/视频选择叙事结构，避免只堆信息点。",
        lanes=("article_soft", "faceless_video", "premium_human_video"),
        maturity="reference",
    ),
    ContentSkill(
        id="screenwriting.save_the_cat",
        path="runtime/hermes-agent/skills/screenwriting/save-the-cat-beats/SKILL.md",
        role="screenwriter",
        purpose="把视频脚本拆成更强的节奏 beat，可作为高级视频参考。",
        lanes=("faceless_video", "premium_human_video"),
        maturity="reference",
    ),
    ContentSkill(
        id="creative.manim_video",
        path="runtime/hermes-agent/skills/creative/manim-video/SKILL.md",
        role="code_visual",
        purpose="生成数学、流程、结构解释类动效；作为 Remotion/HyperFrames 之外的代码视觉参考。",
        lanes=("faceless_video", "premium_human_video"),
        maturity="experimental",
    ),
    ContentSkill(
        id="creative.p5js",
        path="runtime/hermes-agent/skills/creative/p5js/SKILL.md",
        role="code_visual",
        purpose="生成抽象动效、图形化背景和可复现视觉素材。",
        lanes=("faceless_video", "premium_human_video"),
        maturity="experimental",
    ),
)


def recommended_skills_for_lane(lane: ContentLane) -> list[dict[str, Any]]:
    return [skill.to_dict() for skill in CONTENT_PRODUCTION_SKILLS if lane in skill.lanes]


def verify_skill_mounts(project_root: Path) -> dict[str, Any]:
    """Return missing/present skill paths without mutating the runtime."""

    present: list[str] = []
    missing: list[str] = []
    for skill in CONTENT_PRODUCTION_SKILLS:
        target = project_root / skill.path
        (present if target.exists() else missing).append(skill.id)
    return {
        "status": "ok" if not missing else "missing_skills",
        "present": present,
        "missing": missing,
        "total": len(CONTENT_PRODUCTION_SKILLS),
    }
