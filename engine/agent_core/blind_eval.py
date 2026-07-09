"""UPGRADE-02 (Q13): blind_agent blind evaluation protocol.

Inspired by ViMax's best-of-k + VLM judge pattern:
  1. Multiple candidates are scored independently by blind_agent
     (no knowledge of which candidate is "preferred" or prior scores)
  2. If scores diverge beyond SPREAD_THRESHOLD, an arbitrator resolves
  3. The winner is selected by risk-adjusted total (negative dims considered)

This module is deterministic and does not call any LLM directly.
The caller (agent loop) is responsible for:
  - Generating k candidates
  - Calling blind_agent to score each (scored_by="blind_agent")
  - Passing the scores here for arbitration

Design principles:
  - Blind scoring: each candidate scored in isolation, no cross-referencing
  - Spread detection: if max-min > threshold, flag for arbitration
  - Risk-aware: risk_adjusted_total takes priority over raw weighted_total
  - Auditable: full scoring matrix preserved in BlindEvalResult
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .content_rubric import (
    ContentScore,
    score_content,
    get_rubric,
)


# If the spread (max - min) of weighted totals exceeds this, trigger arbitration
SPREAD_THRESHOLD = 1.5

# If any candidate has risk_flags, apply a risk penalty to its effective score
RISK_PENALTY_WEIGHT = 0.5  # subtract 50% of risk penalty from effective score


@dataclass
class CandidateScore:
    """A single candidate's blind evaluation result."""

    candidate_id: str
    content_score: ContentScore
    effective_score: float  # risk_adjusted_total if available, else weighted_total


@dataclass
class BlindEvalResult:
    """Result of a blind evaluation across multiple candidates."""

    candidates: list[CandidateScore]
    winner_id: str
    spread: float  # max - min of effective scores
    arbitration_triggered: bool
    arbitration_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def winner(self) -> CandidateScore:
        return next(c for c in self.candidates if c.candidate_id == self.winner_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "winner_id": self.winner_id,
            "spread": self.spread,
            "arbitration_triggered": self.arbitration_triggered,
            "arbitration_reason": self.arbitration_reason,
            "candidates": [
                {
                    "candidate_id": c.candidate_id,
                    "weighted_total": c.content_score.weighted_total,
                    "effective_score": c.effective_score,
                    "risk_flags": c.content_score.risk_flags,
                    "risk_adjusted_total": c.content_score.risk_adjusted_total,
                    "dimensions": c.content_score.dimensions,
                }
                for c in self.candidates
            ],
            "metadata": self.metadata,
        }


def _effective_score(cs: ContentScore) -> float:
    """Compute the effective score, preferring risk_adjusted_total when available."""
    if cs.risk_adjusted_total is not None:
        return cs.risk_adjusted_total
    return cs.weighted_total


def evaluate_candidates(
    candidates: dict[str, dict[str, int]],
    *,
    rubric_type: str = "opinion_video",
    notes: str = "",
    metadata: dict[str, Any] | None = None,
) -> BlindEvalResult:
    """Blind-evaluate multiple content candidates and select a winner.

    Args:
        candidates: mapping of candidate_id → dimension scores
        rubric_type: rubric to use for scoring
        notes: optional notes to attach to each score
        metadata: optional metadata for the result

    Returns:
        BlindEvalResult with all candidate scores and the winner.
    """
    if not candidates:
        raise ValueError("at least one candidate required")
    if len(candidates) == 1:
        raise ValueError("blind evaluation requires at least 2 candidates")

    scored: list[CandidateScore] = []
    for cid, scores in candidates.items():
        cs = score_content(
            scores,
            rubric_type=rubric_type,
            notes=notes,
            scored_by="blind_agent",
        )
        scored.append(CandidateScore(
            candidate_id=cid,
            content_score=cs,
            effective_score=_effective_score(cs),
        ))

    # Sort by effective score descending
    scored.sort(key=lambda c: c.effective_score, reverse=True)

    effective_scores = [c.effective_score for c in scored]
    spread = round(max(effective_scores) - min(effective_scores), 2)
    arbitration_triggered = spread > SPREAD_THRESHOLD

    # Winner selection: highest effective score
    # If tie (within 0.01), prefer the one with fewer risk_flags
    top = scored[0]
    runner_up = scored[1]
    if abs(top.effective_score - runner_up.effective_score) < 0.01:
        if len(runner_up.content_score.risk_flags) < len(top.content_score.risk_flags):
            top = runner_up

    arbitration_reason = ""
    if arbitration_triggered:
        arbitration_reason = (
            f"score spread {spread} exceeds threshold {SPREAD_THRESHOLD}; "
            f"winner '{top.candidate_id}' selected with effective_score={top.effective_score}"
        )

    return BlindEvalResult(
        candidates=scored,
        winner_id=top.candidate_id,
        spread=spread,
        arbitration_triggered=arbitration_triggered,
        arbitration_reason=arbitration_reason,
        metadata=metadata or {},
    )


def detect_score_anomaly(
    scores: dict[str, int],
    *,
    rubric_type: str = "opinion_video",
) -> list[str]:
    """Detect anomalous scoring patterns that may indicate evaluator bias.

    Returns a list of anomaly descriptions (empty if none found).
    """
    rubric = get_rubric(rubric_type)
    anomalies: list[str] = []

    # Check for all-max scores (potential sycophancy)
    all_max = all(scores.get(d.key, 0) >= d.scale - 1 for d in rubric if not d.is_negative)
    if all_max:
        anomalies.append("all positive dimensions near max — possible sycophancy")

    # Check for all-min scores (potential overly harsh evaluation)
    all_min = all(scores.get(d.key, 0) <= 1 for d in rubric if not d.is_negative)
    if all_min:
        anomalies.append("all positive dimensions near min — possible overly harsh evaluation")

    # Check for negative dims scored 0 while positives are high (ignoring risk)
    high_pos = any(scores.get(d.key, 0) >= 8 for d in rubric if not d.is_negative)
    zero_neg = all(scores.get(d.key, 0) == 0 for d in rubric if d.is_negative)
    if high_pos and zero_neg:
        anomalies.append("high positive scores with zero negative risk — risk dimensions may be under-evaluated")

    # Check for extreme negative scores (flagging everything)
    all_neg_max = all(scores.get(d.key, 0) >= 8 for d in rubric if d.is_negative)
    if all_neg_max:
        anomalies.append("all negative dimensions near max — content may be flagged as high-risk")

    return anomalies
