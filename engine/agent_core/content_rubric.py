"""RUN-17: Content scoring protocol — 9-dimension rubric for short-form video.

Inspired by Cheat on Content's calibrated scoring loop:
  Score → Blind-predict → Publish → T+3d retro → Evolve rubric

The rubric is a working bench, not a museum. Dimensions and weights can evolve
as real performance data accumulates. The initial rubric is fitted for
opinion-type short videos and can be extended for other content types.

UPGRADE-01 (Q12): Added negative signal dimensions inspired by X's algorithm:
  - title_bait_risk: 标题党/封面党风险
  - controversy_overload_risk: 争议过度风险
Negative dimensions subtract from the weighted total (is_negative=True).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RubricDimension:
    """A single scoring dimension in the rubric."""

    key: str
    label: str
    description: str
    weight: float  # 0.0–1.0, relative importance within the rubric
    scale: int = 10  # max score for this dimension
    is_negative: bool = False  # if True, higher score = worse content (subtracts)


# ── Starter rubric: opinion-type short video ──────────────────────────
# Fitted from reference creator's 25+ published samples.
# 7 positive dimensions (weight sum 0.90) + 2 negative dimensions (weight sum 0.10).
# Weights sum to 1.0 and can be evolved via RUN-20 bump protocol.

OPINION_VIDEO_RUBRIC: tuple[RubricDimension, ...] = (
    # ── Positive dimensions (higher = better) ──
    RubricDimension(
        key="hook",
        label="开头钩子",
        description="前 3 秒能否抓住注意力：悬念、冲突、反常识、痛点直击",
        weight=0.18,
    ),
    RubricDimension(
        key="topic",
        label="话题热度",
        description="选题是否踩中热点/痛点/争议，受众覆盖面大小",
        weight=0.13,
    ),
    RubricDimension(
        key="emotion",
        label="情绪共鸣",
        description="内容引发的情绪强度（愤怒/认同/好奇/感动/焦虑）",
        weight=0.13,
    ),
    RubricDimension(
        key="density",
        label="信息密度",
        description="单位时间内的有效信息量，无废话、无注水",
        weight=0.13,
    ),
    RubricDimension(
        key="pacing",
        label="节奏感",
        description="内容推进的快慢交替，高潮与缓冲的分布",
        weight=0.09,
    ),
    RubricDimension(
        key="viewpoint",
        label="观点清晰度",
        description="核心观点是否明确、有立场、不模糊",
        weight=0.13,
    ),
    RubricDimension(
        key="cta",
        label="引导互动",
        description="结尾是否有效引导点赞/评论/转发/关注",
        weight=0.11,
    ),
    # ── Negative dimensions (higher = worse, inspired by X algorithm) ──
    RubricDimension(
        key="title_bait_risk",
        label="标题党风险",
        description="标题/封面是否过度夸张、误导，与正文内容落差大；"
                    "高分意味着用户点开后会感到被骗，类似 X 的 not_interested 信号",
        weight=0.05,
        is_negative=True,
    ),
    RubricDimension(
        key="controversy_overload_risk",
        label="争议过度风险",
        description="内容是否为了流量故意制造对立、极端化表达，"
                    "可能引发举报/拉黑；类似 X 的 block/report 信号",
        weight=0.05,
        is_negative=True,
    ),
)

assert abs(sum(d.weight for d in OPINION_VIDEO_RUBRIC) - 1.0) < 1e-6, "weights must sum to 1.0"


# ── Scoring logic ─────────────────────────────────────────────────────


@dataclass
class ContentScore:
    """A single content scoring result."""

    rubric_type: str
    dimensions: dict[str, int]  # key → score (0–scale)
    weighted_total: float
    notes: str = ""
    scored_by: str = "agent"  # "agent" | "blind_agent" | "user"
    metadata: dict[str, Any] = field(default_factory=dict)
    risk_adjusted_total: float | None = None  # weighted_total minus negative dim penalties
    risk_flags: list[str] = field(default_factory=list)  # triggered risk dimension keys


def get_rubric(rubric_type: str = "opinion_video") -> tuple[RubricDimension, ...]:
    """Get the rubric dimensions for a given content type."""
    rubrics = {
        "opinion_video": OPINION_VIDEO_RUBRIC,
    }
    if rubric_type not in rubrics:
        raise ValueError(f"unknown rubric type: {rubric_type}; available: {list(rubrics)}")
    return rubrics[rubric_type]


def validate_scores(
    scores: dict[str, int],
    rubric_type: str = "opinion_video",
) -> None:
    """Validate that scores cover all dimensions and are in range."""
    rubric = get_rubric(rubric_type)
    expected_keys = {d.key for d in rubric}
    provided_keys = set(scores.keys())

    missing = expected_keys - provided_keys
    if missing:
        raise ValueError(f"missing dimension scores: {missing}")

    extra = provided_keys - expected_keys
    if extra:
        raise ValueError(f"unknown dimension keys: {extra}")

    for dim in rubric:
        val = scores[dim.key]
        if not isinstance(val, int) or val < 0 or val > dim.scale:
            raise ValueError(
                f"score for '{dim.key}' must be int 0–{dim.scale}, got {val}"
            )


def compute_weighted_total(
    scores: dict[str, int],
    rubric_type: str = "opinion_video",
) -> float:
    """Compute weighted total score (0.0–10.0).

    Positive dimensions add to the total; negative dimensions subtract.
    The formula: sum(normalized * weight * 10) for all dims, where negative
    dims have their contribution inverted (higher score → more subtraction).
    """
    rubric = get_rubric(rubric_type)
    validate_scores(scores, rubric_type)
    total = 0.0
    for dim in rubric:
        normalized = scores[dim.key] / dim.scale  # 0.0–1.0
        contribution = normalized * dim.weight * 10.0
        if dim.is_negative:
            total -= contribution
        else:
            total += contribution
    return round(max(total, 0.0), 2)  # floor at 0


def score_content(
    scores: dict[str, int],
    *,
    rubric_type: str = "opinion_video",
    notes: str = "",
    scored_by: str = "agent",
    metadata: dict[str, Any] | None = None,
) -> ContentScore:
    """Score a piece of content and return a ContentScore object.

    Also computes risk_adjusted_total and risk_flags for negative dimensions
    that score above the RISK_THRESHOLD (7/10).
    """
    validate_scores(scores, rubric_type)
    weighted = compute_weighted_total(scores, rubric_type)

    rubric = get_rubric(rubric_type)
    risk_flags: list[str] = []
    risk_penalty = 0.0
    for dim in rubric:
        if dim.is_negative and scores[dim.key] >= 7:
            risk_flags.append(dim.key)
            risk_penalty += (scores[dim.key] / dim.scale) * dim.weight * 10.0

    risk_adjusted = round(max(weighted - risk_penalty * 0.5, 0.0), 2) if risk_flags else None

    return ContentScore(
        rubric_type=rubric_type,
        dimensions=dict(scores),
        weighted_total=weighted,
        notes=notes,
        scored_by=scored_by,
        metadata=metadata or {},
        risk_adjusted_total=risk_adjusted,
        risk_flags=risk_flags,
    )


def rubric_to_dict(rubric_type: str = "opinion_video") -> list[dict[str, Any]]:
    """Serialize rubric dimensions to a list of dicts for storage/display."""
    rubric = get_rubric(rubric_type)
    return [
        {
            "key": d.key,
            "label": d.label,
            "description": d.description,
            "weight": d.weight,
            "scale": d.scale,
            "is_negative": d.is_negative,
        }
        for d in rubric
    ]
