"""Marketing domain schema owned by Hermes ``state.db``."""

MARKETING_DOMAIN_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS marketing_account_adoptions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    prospect_account_id TEXT NOT NULL,
    target_account_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'complete',
    moved_counts_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    completed_at REAL NOT NULL,
    UNIQUE(user_id,prospect_account_id,target_account_id)
);

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
    jobs_json TEXT NOT NULL DEFAULT '[]',
    current_alternatives_json TEXT NOT NULL DEFAULT '[]',
    trust_barriers_json TEXT NOT NULL DEFAULT '[]',
    desired_outcomes_json TEXT NOT NULL DEFAULT '[]',
    behavior_signals_json TEXT NOT NULL DEFAULT '[]',
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

CREATE TABLE IF NOT EXISTS creator_operating_profiles (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES account_strategy_projects(id),
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    profile_json TEXT NOT NULL DEFAULT '{}',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    confirmed_at TEXT,
    UNIQUE(project_id, version)
);

CREATE TABLE IF NOT EXISTS market_route_hypotheses (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES account_strategy_projects(id),
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    route_json TEXT NOT NULL DEFAULT '{}',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    selected_at TEXT,
    UNIQUE(project_id, version)
);

CREATE TABLE IF NOT EXISTS benchmark_accounts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL,
    target_account_id TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL DEFAULT '',
    platform_account_id TEXT NOT NULL DEFAULT '',
    account_handle TEXT NOT NULL DEFAULT '',
    account_name TEXT,
    profile_url TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'direct',
    selection_reason TEXT NOT NULL DEFAULT '',
    match_dimensions_json TEXT NOT NULL DEFAULT '{}',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    selection_status TEXT NOT NULL DEFAULT 'candidate',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    observed_at TEXT,
    valid_until TEXT,
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS benchmark_observations (
    id TEXT PRIMARY KEY,
    benchmark_account_id TEXT NOT NULL REFERENCES benchmark_accounts(id),
    project_id TEXT NOT NULL REFERENCES account_strategy_projects(id),
    user_id TEXT NOT NULL,
    target_account_id TEXT NOT NULL,
    dimension TEXT NOT NULL,
    value_json TEXT NOT NULL DEFAULT '{}',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    provenance_json TEXT NOT NULL DEFAULT '{}',
    confidence REAL NOT NULL DEFAULT 0,
    observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positioning_versions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES account_strategy_projects(id),
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    positioning_json TEXT NOT NULL DEFAULT '{}',
    basis_refs_json TEXT NOT NULL DEFAULT '[]',
    data_gaps_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    approved_at TEXT,
    UNIQUE(project_id, version)
);

CREATE TABLE IF NOT EXISTS content_system_versions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES account_strategy_projects(id),
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    positioning_id TEXT NOT NULL REFERENCES positioning_versions(id),
    version INTEGER NOT NULL,
    system_json TEXT NOT NULL DEFAULT '{}',
    basis_refs_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    approved_at TEXT,
    UNIQUE(project_id, version)
);

CREATE TABLE IF NOT EXISTS account_experiments (
    id TEXT PRIMARY KEY,
    source_key TEXT,
    project_id TEXT NOT NULL REFERENCES account_strategy_projects(id),
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    content_system_id TEXT REFERENCES content_system_versions(id),
    hypothesis TEXT NOT NULL,
    variable_json TEXT NOT NULL DEFAULT '{}',
    variants_json TEXT NOT NULL DEFAULT '[]',
    asset_ids_json TEXT NOT NULL DEFAULT '[]',
    prediction_json TEXT NOT NULL DEFAULT '{}',
    success_criteria_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    approved_at TEXT,
    updated_at TEXT NOT NULL
);

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
    experiment_id TEXT REFERENCES account_experiments(id),
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
    experiment_id TEXT REFERENCES account_experiments(id),
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
    source_key TEXT,
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
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    claimed_at TEXT,
    last_error TEXT,
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
    submitted_at TEXT,
    upload_claimed_at TEXT,
    deletion_ref TEXT,
    withdrawal_requested_at TEXT,
    deleted_at TEXT,
    last_sync_error TEXT
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

CREATE TABLE IF NOT EXISTS marketing_sounds (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    platform_sound_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    artist TEXT NOT NULL DEFAULT '',
    duration_ms INTEGER,
    canonical_url TEXT NOT NULL DEFAULT '',
    rights_status TEXT NOT NULL DEFAULT 'unknown',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE(platform,platform_sound_id)
);
CREATE INDEX IF NOT EXISTS idx_marketing_sounds_platform_seen
    ON marketing_sounds(platform,last_seen_at DESC);

CREATE TABLE IF NOT EXISTS marketing_short_video_observations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    source_item_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    evidence_id TEXT NOT NULL REFERENCES evidence_records(id),
    sound_id TEXT REFERENCES marketing_sounds(id),
    observed_at TEXT NOT NULL,
    published_at TEXT,
    rank INTEGER,
    view_count INTEGER,
    like_count INTEGER,
    comment_count INTEGER,
    share_count INTEGER,
    use_count INTEGER,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(user_id,account_id,platform,source_item_id,observed_at)
);
CREATE INDEX IF NOT EXISTS idx_short_video_observation_scope
    ON marketing_short_video_observations(user_id,account_id,platform,observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_short_video_observation_sound
    ON marketing_short_video_observations(sound_id,platform,observed_at DESC);

CREATE TABLE IF NOT EXISTS marketing_knowledge_entries (
    id TEXT PRIMARY KEY,
    knowledge_base TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT 'default',
    account_id TEXT,
    platform TEXT,
    region TEXT NOT NULL DEFAULT '',
    content_kind TEXT NOT NULL DEFAULT '',
    topic TEXT NOT NULL,
    statement_json TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0.5,
    version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    supersedes_id TEXT REFERENCES marketing_knowledge_entries(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_marketing_knowledge_retrieval
    ON marketing_knowledge_entries(knowledge_base,user_id,account_id,platform,topic,status,valid_from);
CREATE UNIQUE INDEX IF NOT EXISTS idx_marketing_knowledge_identity
    ON marketing_knowledge_entries(knowledge_base,user_id,IFNULL(account_id,''),IFNULL(platform,''),
                                   region,content_kind,topic,version,source_kind,source_ref);
"""


# AccountRegistry authorizes adoption; SessionDB applies this declarative map
# atomically. Sessions are intentionally absent: an existing conversation keeps
# its immutable prospect scope, while the successor conversation starts bound
# to the authenticated account.
PROSPECT_SCOPE_COLUMNS = {
    "account_strategy_projects": "account_id",
    "audience_hypotheses": "account_id",
    "creator_operating_profiles": "account_id",
    "market_route_hypotheses": "account_id",
    "benchmark_accounts": "target_account_id",
    "benchmark_observations": "target_account_id",
    "positioning_versions": "account_id",
    "content_system_versions": "account_id",
    "account_experiments": "account_id",
    "evidence_records": "account_id",
    "content_production_plans": "account_id",
    "content_assets": "account_id",
    "marketing_preflight_records": "account_id",
    "marketing_receipt_refs": "account_id",
    "marketing_learning_candidates": "account_id",
    "marketing_publish_actions": "account_id",
    "marketing_metric_checkpoints": "account_id",
    "marketing_knowledge_contributions": "account_id",
    "marketing_knowledge_entries": "account_id",
    "marketing_short_video_observations": "account_id",
    # Optional compatibility tables may exist in upgraded product databases.
    "audience_snapshots": "account_id",
    "memory_candidates": "account_id",
}

LEGACY_MARKETING_TABLES = (
    "account_strategy_projects",
    "audience_hypotheses",
    "creator_operating_profiles",
    "market_route_hypotheses",
    "benchmark_accounts",
    "benchmark_observations",
    "positioning_versions",
    "content_system_versions",
    "account_experiments",
    "evidence_records",
    "content_production_plans",
    "content_assets",
    "marketing_preflight_records",
    "marketing_receipt_refs",
    "marketing_learning_candidates",
    "marketing_publish_actions",
    "marketing_metric_checkpoints",
    "marketing_sounds",
    "marketing_short_video_observations",
    "marketing_knowledge_entries",
)
