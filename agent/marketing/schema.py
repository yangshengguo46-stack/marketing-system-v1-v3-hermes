"""Marketing domain schema owned by Hermes ``state.db``."""

MARKETING_DOMAIN_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS account_strategy_projects (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    business_goal TEXT NOT NULL,
    constraints_json TEXT NOT NULL DEFAULT '{}',
    stage TEXT NOT NULL DEFAULT 'goal_defined',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_strategy_projects_one_active
    ON account_strategy_projects(user_id, account_id) WHERE status='active';
CREATE INDEX IF NOT EXISTS idx_strategy_projects_scope
    ON account_strategy_projects(user_id, account_id, status);

CREATE TABLE IF NOT EXISTS audience_hypotheses (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES account_strategy_projects(id),
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    segments_json TEXT NOT NULL DEFAULT '[]',
    pains_json TEXT NOT NULL DEFAULT '[]',
    scenarios_json TEXT NOT NULL DEFAULT '[]',
    exclusions_json TEXT NOT NULL DEFAULT '[]',
    data_gaps_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    confirmed_at TEXT,
    UNIQUE(project_id, version)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_audience_one_confirmed
    ON audience_hypotheses(project_id) WHERE status='confirmed';
CREATE INDEX IF NOT EXISTS idx_audience_scope
    ON audience_hypotheses(user_id, account_id, project_id);

CREATE TABLE IF NOT EXISTS evidence_records (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    provider TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    excerpt TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    verification_level TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    session_id TEXT NOT NULL,
    tool_call_id TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_scope_content
    ON evidence_records(user_id, account_id,provider,canonical_url,content_sha256);
CREATE INDEX IF NOT EXISTS idx_evidence_scope_status
    ON evidence_records(user_id, account_id,status,captured_at);

CREATE TABLE IF NOT EXISTS content_production_plans (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    objective TEXT NOT NULL,
    platforms_json TEXT NOT NULL,
    plan_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_content_production_plan_scope
    ON content_production_plans(user_id, account_id, updated_at);

CREATE TABLE IF NOT EXISTS content_assets (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'default',
    account_id TEXT,
    platform TEXT,
    title TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'script',
    status TEXT NOT NULL DEFAULT 'draft',
    parent_id TEXT,
    experiment_id TEXT,
    topic TEXT,
    hook TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    content_json TEXT NOT NULL DEFAULT '{}',
    metrics_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_content_assets_status ON content_assets(status);
CREATE INDEX IF NOT EXISTS idx_content_assets_account ON content_assets(account_id);
CREATE INDEX IF NOT EXISTS idx_content_assets_scope
    ON content_assets(user_id, account_id, updated_at);

CREATE TABLE IF NOT EXISTS marketing_preflight_records (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    platform TEXT,
    plan_id TEXT NOT NULL REFERENCES content_production_plans(id),
    session_id TEXT NOT NULL DEFAULT '',
    formula_version TEXT NOT NULL,
    input_json TEXT NOT NULL,
    scores_json TEXT NOT NULL,
    decision_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_marketing_preflight_scope
    ON marketing_preflight_records(account_id,platform,created_at);

CREATE TABLE IF NOT EXISTS marketing_receipt_refs (
    id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    receipt_type TEXT NOT NULL,
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    platform TEXT,
    plan_id TEXT,
    preflight_id TEXT REFERENCES marketing_preflight_records(id),
    session_id TEXT NOT NULL DEFAULT '',
    summary_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(source_kind,source_id,receipt_type)
);
CREATE INDEX IF NOT EXISTS idx_marketing_receipt_scope
    ON marketing_receipt_refs(account_id,platform,created_at);

CREATE TABLE IF NOT EXISTS marketing_learning_candidates (
    id TEXT PRIMARY KEY,
    candidate_type TEXT NOT NULL,
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    platform TEXT,
    preflight_id TEXT REFERENCES marketing_preflight_records(id),
    prediction_id TEXT,
    receipt_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    proposal_json TEXT NOT NULL DEFAULT '{}',
    confidence REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    decision_reason TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_marketing_learning_scope
    ON marketing_learning_candidates(account_id,platform,status,created_at);

CREATE TABLE IF NOT EXISTS marketing_publish_actions (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    asset_id TEXT NOT NULL REFERENCES content_assets(id),
    asset_version INTEGER NOT NULL,
    plan_id TEXT NOT NULL REFERENCES content_production_plans(id),
    preflight_id TEXT NOT NULL REFERENCES marketing_preflight_records(id),
    platform TEXT NOT NULL,
    provider TEXT NOT NULL,
    session_id TEXT NOT NULL DEFAULT '',
    tool_call_id TEXT NOT NULL DEFAULT '',
    approval_ref TEXT,
    status TEXT NOT NULL,
    request_json TEXT NOT NULL,
    receipt_id TEXT,
    failure_code TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    settled_at TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_marketing_publish_scope
    ON marketing_publish_actions(account_id,platform,status,updated_at);

CREATE TABLE IF NOT EXISTS marketing_metric_checkpoints (
    id TEXT PRIMARY KEY,
    publish_action_id TEXT NOT NULL REFERENCES marketing_publish_actions(id),
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    label TEXT NOT NULL,
    due_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    metric_receipt_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(publish_action_id,label)
);
CREATE INDEX IF NOT EXISTS idx_marketing_metric_due
    ON marketing_metric_checkpoints(status,due_at);

CREATE TABLE IF NOT EXISTS marketing_knowledge_contributions (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    source_candidate_id TEXT NOT NULL REFERENCES marketing_learning_candidates(id),
    consent_ref TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    cohort_json TEXT NOT NULL,
    features_json TEXT NOT NULL,
    outcomes_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    submitted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_marketing_contribution_status
    ON marketing_knowledge_contributions(status,created_at);

CREATE TABLE IF NOT EXISTS marketing_knowledge_packs (
    id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    knowledge_type TEXT NOT NULL,
    platform TEXT NOT NULL,
    region TEXT NOT NULL DEFAULT '',
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    sample_size INTEGER NOT NULL,
    min_cohort_size INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    checksum TEXT NOT NULL,
    signature TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'verified',
    verified_at TEXT NOT NULL,
    UNIQUE(knowledge_type,platform,region,version)
);
CREATE INDEX IF NOT EXISTS idx_marketing_knowledge_pack_active
    ON marketing_knowledge_packs(knowledge_type,platform,region,status,verified_at);
"""

LEGACY_MARKETING_TABLES = (
    "account_strategy_projects",
    "audience_hypotheses",
    "evidence_records",
    "content_production_plans",
    "content_assets",
    "marketing_preflight_records",
    "marketing_receipt_refs",
    "marketing_learning_candidates",
    "marketing_publish_actions",
    "marketing_metric_checkpoints",
)
