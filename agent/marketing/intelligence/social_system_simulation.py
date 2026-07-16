"""Pre-publish social-system simulation and post-publish causal reflection."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from agent.marketing.domains.human_model import existence_ontology_contract

SOCIAL_SYSTEM_SIMULATION_VERSION = "social-system-simulation-v0.2"
CAUSAL_REFLECTION_VERSION = "causal-reflection-v0.2"


def build_social_system_simulation(
    *, prediction: dict[str, Any], reaction: dict[str, Any], plan: dict[str, Any]
) -> dict[str, Any]:
    dimensions_root = prediction.get("prediction_dimensions") or {}
    dimensions = dimensions_root.get("dimensions") or {}
    scenarios = [item for item in reaction.get("scenarios") or [] if isinstance(item, dict)]
    need_projections = sorted(
        {str(item.get("need_projection") or "unknown") for item in scenarios}
    )
    cognitive_projections = sorted(
        {str(item.get("cognitive_projection") or "unknown") for item in scenarios}
    )
    existence_strategies = sorted(
        {
            str(
                item.get("existence_strategy")
                or item.get("existence_direction")
                or "unknown"
            )
            for item in scenarios
        }
    )
    body = {
        "version": SOCIAL_SYSTEM_SIMULATION_VERSION,
        "scope": "content_enters_social_attention_field",
        "existence_ontology": existence_ontology_contract(),
        "mechanism_chain": [
            "environment_and_embodied_constraints",
            "need_projection",
            "cognitive_projection",
            "existence_strategy",
            "observable_behavior",
            "group_propagation",
            "platform_distribution",
            "business_action",
        ],
        "stages": {
            "individual_attention": {
                "attention": dimensions.get("attention"),
                "retention": dimensions.get("retention"),
                "trust": dimensions.get("trust"),
                "need_projections": need_projections,
                "cognitive_projections": cognitive_projections,
                "existence_strategies": existence_strategies,
                "projection_notice": "latent_hypotheses_not_directly_observed_inner_states",
            },
            "group_propagation": {
                "scenario_ids": list(reaction.get("scenario_ids") or []),
                "cohort_relations": sorted(
                    {str(item.get("cohort_relation") or "unknown") for item in scenarios}
                ),
                "stances": sorted({str(item.get("stance") or "unknown") for item in scenarios}),
                "trust_or_share_hypothesis": dimensions.get("trust"),
            },
            "platform_distribution": {
                "platforms": list(plan.get("target_platforms") or []),
                "reach_hypothesis": dimensions.get("attention"),
                "account_fit": dimensions.get("account_fit"),
                "sound": dimensions.get("sound"),
            },
            "business_action": {
                "action": dimensions.get("action"),
                "risk": dimensions.get("risk"),
            },
        },
        "intervention": {
            "experiment_id": plan.get("experiment_id"),
            "status": (
                "designed_experiment" if plan.get("experiment_id") else "observational_content_action"
            ),
        },
        "data_gaps": list(
            dict.fromkeys(
                [
                    *(reaction.get("data_gaps") or []),
                    "platform_competition_and_allocation_are_not_fully_observed",
                    "paid_traffic_and_timing_may_confound_outcomes",
                ]
            )
        ),
        "causal_contract": {
            "prediction_is_not_causal_proof": True,
            "existence_is_not_a_measured_variable": True,
            "projection_match_is_not_motive_observation": True,
            "single_post_identifies_counterfactual": False,
            "required_for_causal_upgrade": [
                "pre_registered_variants",
                "stable_platform_receipts",
                "comparable_time_windows",
                "repeated_or_matched_observations",
            ],
        },
    }
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        **body,
        "simulation_id": "socialsim_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:28],
        "mutable": False,
    }


def build_causal_reflection(
    *,
    action: dict[str, Any],
    checkpoint: dict[str, Any],
    metric_labels: dict[str, Any],
    metric_retro: dict[str, Any],
    reaction_retro: dict[str, Any],
) -> dict[str, Any]:
    experiment_id = action.get("experiment_id") or (action.get("request") or {}).get(
        "experiment_id"
    )
    prediction_errors = [
        {
            "metric": item.get("metric"),
            "direction": item.get("direction"),
            "bucket": item.get("bucket"),
        }
        for item in metric_retro.get("accuracies") or []
        if item.get("direction") in {"over", "under"}
    ]
    reaction_surprises = {
        "missed_scenario_ids": list(reaction_retro.get("missed_scenario_ids") or []),
        "unexpected_clusters": list(reaction_retro.get("unexpected_clusters") or []),
        "projection_chain_retro": reaction_retro.get("projection_chain_retro"),
    }
    has_prediction = metric_retro.get("status") == "compared"
    has_reaction = reaction_retro.get("status") == "compared"
    return {
        "version": CAUSAL_REFLECTION_VERSION,
        "status": "reflected" if has_prediction or has_reaction else "observation_only",
        "observation": {
            "checkpoint_id": checkpoint.get("id"),
            "checkpoint_label": checkpoint.get("label"),
            "metric_labels": metric_labels,
            "reaction_status": reaction_retro.get("status"),
        },
        "prediction_error": {
            "metric_errors": prediction_errors,
            "reaction_surprises": reaction_surprises,
        },
        "intervention": {
            "experiment_id": experiment_id,
            "status": (
                "designed_but_not_identified_from_one_action"
                if experiment_id
                else "not_pre_registered"
            ),
        },
        "counterfactual": {
            "status": "unavailable",
            "reason": (
                "One observed post does not reveal what would have happened under an unchosen "
                "variant. Matched or randomized variant receipts are required."
            ),
        },
        "alternative_explanations": [
            "platform_distribution_or_policy_change",
            "creator_history_and_follower_base",
            "publication_timing_and_competing_content",
            "paid_or_unobserved_traffic",
            "measurement_delay_or_partial_visibility",
        ],
        "causal_claim_allowed": False,
        "next_evidence": (
            "Collect comparable variant receipts and repeat across time windows before upgrading "
            "an association to an intervention claim."
        ),
    }
