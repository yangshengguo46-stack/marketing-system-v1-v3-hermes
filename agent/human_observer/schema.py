"""Declarative schema for the source-agnostic Human Observation Core."""

HUMAN_OBSERVER_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS human_observation_events (
    id TEXT PRIMARY KEY,
    event_key TEXT NOT NULL UNIQUE,
    namespace TEXT NOT NULL DEFAULT 'global',
    source_kind TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    modality TEXT NOT NULL,
    subject_ref TEXT,
    cohort_ref TEXT,
    occurred_at TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    context_json TEXT NOT NULL DEFAULT '{}',
    observation_json TEXT NOT NULL DEFAULT '{}',
    provenance_json TEXT NOT NULL DEFAULT '{}',
    rights_json TEXT NOT NULL DEFAULT '{}',
    observation_sha256 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'observed',
    created_at TEXT NOT NULL,
    CHECK(status IN ('observed','quarantined','withdrawn')),
    CHECK(subject_ref IS NULL OR subject_ref GLOB 'subject_[0-9a-f]*'),
    CHECK(cohort_ref IS NULL OR cohort_ref GLOB 'cohort_[0-9a-f]*')
);
CREATE INDEX IF NOT EXISTS idx_human_observation_time
    ON human_observation_events(namespace,observed_at,source_kind);
CREATE INDEX IF NOT EXISTS idx_human_observation_subject
    ON human_observation_events(namespace,subject_ref,occurred_at)
    WHERE subject_ref IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_human_observation_cohort
    ON human_observation_events(namespace,cohort_ref,occurred_at)
    WHERE cohort_ref IS NOT NULL;

CREATE TABLE IF NOT EXISTS human_graph_nodes (
    id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL DEFAULT 'global',
    node_type TEXT NOT NULL,
    stable_ref TEXT NOT NULL,
    attributes_json TEXT NOT NULL DEFAULT '{}',
    evidence_event_ids_json TEXT NOT NULL DEFAULT '[]',
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(namespace,node_type,stable_ref),
    CHECK(node_type IN ('subject','cohort','context','institution','artifact','environment')),
    CHECK(status IN ('active','superseded','withdrawn'))
);
CREATE INDEX IF NOT EXISTS idx_human_graph_nodes_scope
    ON human_graph_nodes(namespace,node_type,status,valid_from);

CREATE TABLE IF NOT EXISTS human_graph_edges (
    id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL DEFAULT 'global',
    source_node_id TEXT NOT NULL REFERENCES human_graph_nodes(id),
    target_node_id TEXT NOT NULL REFERENCES human_graph_nodes(id),
    relation TEXT NOT NULL,
    context_json TEXT NOT NULL DEFAULT '{}',
    evidence_event_ids_json TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    status TEXT NOT NULL DEFAULT 'candidate',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK(confidence >= 0 AND confidence <= 1),
    CHECK(status IN ('candidate','supported','contested','superseded','rejected'))
);
CREATE INDEX IF NOT EXISTS idx_human_graph_edges_scope
    ON human_graph_edges(namespace,relation,status,valid_from);

CREATE TABLE IF NOT EXISTS human_theories (
    theory_id TEXT NOT NULL,
    version TEXT NOT NULL,
    name TEXT NOT NULL,
    family TEXT NOT NULL,
    epistemic_status TEXT NOT NULL,
    constructs_json TEXT NOT NULL DEFAULT '[]',
    assumptions_json TEXT NOT NULL DEFAULT '[]',
    falsification_json TEXT NOT NULL DEFAULT '[]',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'available',
    created_at TEXT NOT NULL,
    PRIMARY KEY(theory_id,version),
    CHECK(status IN ('available','deprecated','rejected'))
);
CREATE INDEX IF NOT EXISTS idx_human_theories_family
    ON human_theories(family,status,theory_id,version);

CREATE TABLE IF NOT EXISTS human_interpretations (
    id TEXT PRIMARY KEY,
    interpretation_key TEXT NOT NULL UNIQUE,
    namespace TEXT NOT NULL DEFAULT 'global',
    event_id TEXT NOT NULL REFERENCES human_observation_events(id),
    theory_id TEXT NOT NULL,
    theory_version TEXT NOT NULL,
    construct TEXT NOT NULL,
    claim_json TEXT NOT NULL DEFAULT '{}',
    context_scope_json TEXT NOT NULL DEFAULT '{}',
    support_event_ids_json TEXT NOT NULL DEFAULT '[]',
    counter_event_ids_json TEXT NOT NULL DEFAULT '[]',
    model_ref TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'candidate',
    created_at TEXT NOT NULL,
    FOREIGN KEY(theory_id,theory_version) REFERENCES human_theories(theory_id,version),
    CHECK(confidence >= 0 AND confidence <= 0.7),
    CHECK(status IN ('candidate','supported','contested','superseded','rejected'))
);
CREATE INDEX IF NOT EXISTS idx_human_interpretations_event
    ON human_interpretations(event_id,theory_id,construct,status);

CREATE TABLE IF NOT EXISTS human_hypotheses (
    id TEXT PRIMARY KEY,
    hypothesis_key TEXT NOT NULL UNIQUE,
    namespace TEXT NOT NULL DEFAULT 'global',
    theory_id TEXT NOT NULL,
    theory_version TEXT NOT NULL,
    scope_json TEXT NOT NULL DEFAULT '{}',
    statement_json TEXT NOT NULL DEFAULT '{}',
    evidence_for_json TEXT NOT NULL DEFAULT '[]',
    evidence_against_json TEXT NOT NULL DEFAULT '[]',
    sample_count INTEGER NOT NULL DEFAULT 0,
    context_count INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'candidate',
    version INTEGER NOT NULL DEFAULT 1,
    supersedes_id TEXT REFERENCES human_hypotheses(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(theory_id,theory_version) REFERENCES human_theories(theory_id,version),
    CHECK(confidence >= 0 AND confidence <= 0.7),
    CHECK(status IN ('candidate','supported','contested','superseded','rejected'))
);
CREATE INDEX IF NOT EXISTS idx_human_hypotheses_scope
    ON human_hypotheses(namespace,theory_id,status,updated_at);

CREATE TABLE IF NOT EXISTS human_predictions (
    id TEXT PRIMARY KEY,
    prediction_key TEXT NOT NULL UNIQUE,
    namespace TEXT NOT NULL DEFAULT 'global',
    hypothesis_id TEXT REFERENCES human_hypotheses(id),
    target_json TEXT NOT NULL DEFAULT '{}',
    prediction_json TEXT NOT NULL DEFAULT '{}',
    evidence_event_ids_json TEXT NOT NULL DEFAULT '[]',
    due_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'sealed',
    created_at TEXT NOT NULL,
    CHECK(status IN ('sealed','settled','expired','invalidated'))
);
CREATE INDEX IF NOT EXISTS idx_human_predictions_due
    ON human_predictions(status,due_at,namespace);

CREATE TABLE IF NOT EXISTS human_prediction_outcomes (
    id TEXT PRIMARY KEY,
    prediction_id TEXT NOT NULL UNIQUE REFERENCES human_predictions(id),
    observation_event_id TEXT NOT NULL REFERENCES human_observation_events(id),
    outcome_json TEXT NOT NULL DEFAULT '{}',
    evaluation_json TEXT NOT NULL DEFAULT '{}',
    settled_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS human_model_revisions (
    id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    version INTEGER NOT NULL,
    parent_revision_id TEXT REFERENCES human_model_revisions(id),
    ontology_json TEXT NOT NULL DEFAULT '{}',
    theory_weights_json TEXT NOT NULL DEFAULT '{}',
    evidence_event_ids_json TEXT NOT NULL DEFAULT '[]',
    counterevidence_event_ids_json TEXT NOT NULL DEFAULT '[]',
    evaluation_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'candidate',
    created_at TEXT NOT NULL,
    UNIQUE(model_name,version),
    CHECK(status IN ('seed','candidate','active','contested','superseded','rejected'))
);
CREATE INDEX IF NOT EXISTS idx_human_model_revisions
    ON human_model_revisions(model_name,status,version DESC);

CREATE TABLE IF NOT EXISTS human_source_ingestions (
    source_kind TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    event_ids_json TEXT NOT NULL DEFAULT '[]',
    interpretation_ids_json TEXT NOT NULL DEFAULT '[]',
    source_sha256 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ingested',
    created_at TEXT NOT NULL,
    PRIMARY KEY(source_kind,source_ref),
    CHECK(status IN ('ingested','quarantined','withdrawn'))
);
"""
