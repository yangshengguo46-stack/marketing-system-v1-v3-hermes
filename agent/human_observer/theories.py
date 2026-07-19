"""Versioned, competing theory lenses for the Human Observation Core.

The registry is a research catalogue, not a diagnosis engine.  A theory being
available means that it may produce a falsifiable interpretation; it does not
make the theory true or permit permanent labels to be attached to a person.
"""

from __future__ import annotations

from typing import Any


BUILTIN_THEORIES: tuple[dict[str, Any], ...] = (
    {
        "theory_id": "maslow_hierarchy",
        "version": "1.0",
        "name": "Maslow hierarchy of needs",
        "family": "motivation",
        "epistemic_status": "historical_framework_contested_ordering",
        "constructs": ["physiological", "safety", "belonging", "esteem", "self_actualization", "transcendence"],
        "assumptions": ["needs may shape attention and action", "ordering is context dependent"],
        "falsification": ["the predicted need-linked behavior fails across matched contexts"],
        "source_refs": ["Maslow, A.H. (1943), A Theory of Human Motivation"],
    },
    {
        "theory_id": "jungian_cognitive_functions",
        "version": "1.0",
        "name": "Jungian cognitive functions",
        "family": "cognition",
        "epistemic_status": "interpretive_framework_not_clinical_typology",
        "constructs": ["Se", "Si", "Ne", "Ni", "Te", "Ti", "Fe", "Fi"],
        "assumptions": ["observable information preferences may be described without permanent typing"],
        "falsification": ["the projected information preference does not predict behavior in the scoped context"],
        "source_refs": ["Jung, C.G. (1921), Psychological Types"],
    },
    {
        "theory_id": "le_bon_crowd_lens",
        "version": "1.0",
        "name": "Le Bon historical crowd lens",
        "family": "collective_behavior",
        "epistemic_status": "historical_and_contested_not_universal_law",
        "constructs": ["suggestibility", "emotional_contagion", "anonymity"],
        "assumptions": ["crowd settings may alter observable behavior"],
        "falsification": ["individual and group behavior do not diverge under comparable conditions"],
        "source_refs": ["Le Bon, G. (1895), The Crowd"],
    },
    {
        "theory_id": "social_identity",
        "version": "1.0",
        "name": "Social identity theory",
        "family": "collective_behavior",
        "epistemic_status": "empirical_competing_lens",
        "constructs": ["in_group", "out_group", "identity_salience"],
        "assumptions": ["salient group membership can shape behavior"],
        "falsification": ["identity salience changes without the predicted behavioral change"],
        "source_refs": ["Tajfel & Turner (1979), An Integrative Theory of Intergroup Conflict"],
    },
    {
        "theory_id": "deindividuation",
        "version": "1.0",
        "name": "Deindividuation",
        "family": "collective_behavior",
        "epistemic_status": "empirical_competing_lens",
        "constructs": ["anonymity", "self_awareness", "accountability"],
        "assumptions": ["reduced identifiability may shift norm adherence"],
        "falsification": ["accountability changes without the predicted behavioral shift"],
        "source_refs": ["Zimbardo (1969), The Human Choice"],
    },
    {
        "theory_id": "emergent_norm",
        "version": "1.0",
        "name": "Emergent norm theory",
        "family": "collective_behavior",
        "epistemic_status": "empirical_competing_lens",
        "constructs": ["novel_norm", "keynoting", "norm_convergence"],
        "assumptions": ["groups can construct situational norms"],
        "falsification": ["behavior converges before any observable norm signal appears"],
        "source_refs": ["Turner & Killian (1957), Collective Behavior"],
    },
    {
        "theory_id": "information_cascade",
        "version": "1.0",
        "name": "Information cascade",
        "family": "collective_behavior",
        "epistemic_status": "formal_empirical_competing_lens",
        "constructs": ["private_signal", "observed_action", "cascade"],
        "assumptions": ["observed prior choices can outweigh private signals"],
        "falsification": ["private evidence remains predictive after controlling for observed prior choices"],
        "source_refs": ["Bikhchandani, Hirshleifer & Welch (1992), A Theory of Fads"],
    },
    {
        "theory_id": "existence_strategy",
        "version": "0.1",
        "name": "Existence strategy research programme",
        "family": "meta_model",
        "epistemic_status": "seed_hypothesis_revisable",
        "constructs": ["preserve", "confirm", "expand", "continue", "unknown"],
        "assumptions": ["behavior may express context-bound strategies for sustaining or changing lived existence"],
        "falsification": ["the strategy projection adds no predictive power over simpler contextual models"],
        "source_refs": ["Marketing OS research seed; not an established psychological law"],
    },
)


COLLECTIVE_MECHANISM_THEORY = {
    "identity_convergence": "social_identity",
    "normative_pressure": "emergent_norm",
    "deindividuation": "deindividuation",
    "rumor_cascade": "information_cascade",
    "imitation": "information_cascade",
    "emotional_contagion": "le_bon_crowd_lens",
    "suggestibility": "le_bon_crowd_lens",
    "authority_transfer": "social_identity",
    "polarization": "social_identity",
    "collective_effervescence": "emergent_norm",
    "unknown": "emergent_norm",
}
