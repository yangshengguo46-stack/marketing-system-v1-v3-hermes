"""Declarative schema for durable Hermes workflows.

The Harness owns execution facts only. Product and provider repositories keep
owning business facts; workflow artifacts therefore reference canonical domain
objects instead of copying their payloads.
"""

HARNESS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS harness_workflows (
    id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    owner_entity_id TEXT NOT NULL DEFAULT '',
    source_kind TEXT NOT NULL DEFAULT '',
    source_ref TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'queued',
    priority INTEGER NOT NULL DEFAULT 0,
    input_json TEXT NOT NULL DEFAULT '{}',
    policy_json TEXT NOT NULL DEFAULT '{}',
    budget_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    error_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    completed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_harness_workflows_owner
    ON harness_workflows(namespace,owner_user_id,owner_entity_id,updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_harness_workflows_state
    ON harness_workflows(state,priority DESC,updated_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_harness_workflows_source
    ON harness_workflows(namespace,source_kind,source_ref)
    WHERE source_kind<>'' AND source_ref<>'';

CREATE TABLE IF NOT EXISTS harness_steps (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES harness_workflows(id) ON DELETE CASCADE,
    step_key TEXT NOT NULL,
    kind TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'blocked',
    sequence INTEGER NOT NULL DEFAULT 0,
    worker_role TEXT NOT NULL DEFAULT '',
    toolset_json TEXT NOT NULL DEFAULT '[]',
    resource_scope TEXT NOT NULL DEFAULT '',
    input_json TEXT NOT NULL DEFAULT '{}',
    output_json TEXT NOT NULL DEFAULT '{}',
    error_json TEXT NOT NULL DEFAULT '{}',
    retry_policy_json TEXT NOT NULL DEFAULT '{}',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    available_at REAL NOT NULL DEFAULT 0,
    lease_owner TEXT NOT NULL DEFAULT '',
    lease_token_hash TEXT NOT NULL DEFAULT '',
    lease_expires_at REAL,
    heartbeat_at REAL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    started_at REAL,
    completed_at REAL,
    UNIQUE(workflow_id,step_key)
);
CREATE INDEX IF NOT EXISTS idx_harness_steps_claim
    ON harness_steps(state,available_at,sequence,created_at);
CREATE INDEX IF NOT EXISTS idx_harness_steps_workflow
    ON harness_steps(workflow_id,sequence,created_at);
CREATE INDEX IF NOT EXISTS idx_harness_steps_lease
    ON harness_steps(state,lease_expires_at)
    WHERE state IN ('leased','running');

CREATE TABLE IF NOT EXISTS harness_step_dependencies (
    workflow_id TEXT NOT NULL REFERENCES harness_workflows(id) ON DELETE CASCADE,
    step_id TEXT NOT NULL REFERENCES harness_steps(id) ON DELETE CASCADE,
    depends_on_step_id TEXT NOT NULL REFERENCES harness_steps(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    PRIMARY KEY(step_id,depends_on_step_id),
    CHECK(step_id<>depends_on_step_id)
);
CREATE INDEX IF NOT EXISTS idx_harness_step_dependencies_parent
    ON harness_step_dependencies(depends_on_step_id,step_id);

CREATE TABLE IF NOT EXISTS harness_attempts (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES harness_workflows(id) ON DELETE CASCADE,
    step_id TEXT NOT NULL REFERENCES harness_steps(id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL,
    state TEXT NOT NULL,
    worker_id TEXT NOT NULL,
    lease_token_hash TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    runner_json TEXT NOT NULL DEFAULT '{}',
    output_json TEXT NOT NULL DEFAULT '{}',
    error_json TEXT NOT NULL DEFAULT '{}',
    started_at REAL NOT NULL,
    heartbeat_at REAL NOT NULL,
    ended_at REAL,
    UNIQUE(step_id,attempt_number)
);
CREATE INDEX IF NOT EXISTS idx_harness_attempts_active
    ON harness_attempts(step_id,state,started_at DESC);

CREATE TABLE IF NOT EXISTS harness_artifacts (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES harness_workflows(id) ON DELETE CASCADE,
    step_id TEXT REFERENCES harness_steps(id) ON DELETE SET NULL,
    attempt_id TEXT REFERENCES harness_attempts(id) ON DELETE SET NULL,
    kind TEXT NOT NULL,
    object_type TEXT NOT NULL DEFAULT '',
    object_id TEXT NOT NULL DEFAULT '',
    uri TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL,
    media_type TEXT NOT NULL DEFAULT 'application/json',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_harness_artifacts_workflow
    ON harness_artifacts(workflow_id,created_at);

CREATE TABLE IF NOT EXISTS harness_approvals (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES harness_workflows(id) ON DELETE CASCADE,
    step_id TEXT NOT NULL REFERENCES harness_steps(id) ON DELETE CASCADE,
    approval_key TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending',
    request_json TEXT NOT NULL DEFAULT '{}',
    decision_json TEXT NOT NULL DEFAULT '{}',
    requested_by TEXT NOT NULL,
    decided_by TEXT NOT NULL DEFAULT '',
    contract_version TEXT NOT NULL DEFAULT '',
    requested_at REAL NOT NULL,
    expires_at REAL,
    decided_at REAL,
    UNIQUE(workflow_id,approval_key)
);
CREATE INDEX IF NOT EXISTS idx_harness_approvals_pending
    ON harness_approvals(state,requested_at)
    WHERE state='pending';

CREATE TABLE IF NOT EXISTS harness_receipts (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES harness_workflows(id) ON DELETE CASCADE,
    step_id TEXT REFERENCES harness_steps(id) ON DELETE SET NULL,
    attempt_id TEXT REFERENCES harness_attempts(id) ON DELETE SET NULL,
    receipt_kind TEXT NOT NULL,
    idempotency_key TEXT NOT NULL DEFAULT '',
    input_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    output_json TEXT NOT NULL DEFAULT '{}',
    error_json TEXT NOT NULL DEFAULT '{}',
    started_at REAL NOT NULL,
    completed_at REAL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_harness_receipts_idempotency
    ON harness_receipts(receipt_kind,idempotency_key)
    WHERE idempotency_key<>'';

CREATE TABLE IF NOT EXISTS harness_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL REFERENCES harness_workflows(id) ON DELETE CASCADE,
    step_id TEXT REFERENCES harness_steps(id) ON DELETE SET NULL,
    attempt_id TEXT REFERENCES harness_attempts(id) ON DELETE SET NULL,
    event_kind TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_harness_events_workflow
    ON harness_events(workflow_id,id);
"""
