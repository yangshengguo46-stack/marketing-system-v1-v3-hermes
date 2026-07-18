"""Marketing domain schema owned by Hermes ``state.db``."""

MARKETING_DOMAIN_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS marketing_operating_entities (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    label TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(user_id,label)
);
CREATE INDEX IF NOT EXISTS idx_marketing_operating_entities_user
    ON marketing_operating_entities(user_id,status,updated_at DESC);

CREATE TABLE IF NOT EXISTS marketing_operating_entity_accounts (
    entity_id TEXT NOT NULL REFERENCES marketing_operating_entities(id),
    user_id TEXT NOT NULL,
    account_id TEXT NOT NULL REFERENCES marketing_accounts(id),
    role TEXT NOT NULL DEFAULT 'channel',
    status TEXT NOT NULL DEFAULT 'active',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY(entity_id,account_id),
    UNIQUE(user_id,account_id)
);
CREATE INDEX IF NOT EXISTS idx_marketing_operating_entity_accounts_scope
    ON marketing_operating_entity_accounts(user_id,entity_id,status,updated_at DESC);

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

CREATE TABLE IF NOT EXISTS marketing_operations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
    account_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'working',
    live_session_id TEXT NOT NULL DEFAULT '',
    stored_session_id TEXT NOT NULL DEFAULT '',
    project_id TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    visible_text TEXT NOT NULL,
    operation_json TEXT NOT NULL DEFAULT '{}',
    baseline_json TEXT NOT NULL DEFAULT '{}',
    results_json TEXT NOT NULL DEFAULT '[]',
    workflow_id TEXT NOT NULL DEFAULT '',
    workflow_step_id TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    completed_at REAL
);
CREATE INDEX IF NOT EXISTS idx_marketing_operations_scope
    ON marketing_operations(user_id, account_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_marketing_operations_state
    ON marketing_operations(state, updated_at DESC);

CREATE TABLE IF NOT EXISTS account_strategy_projects (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
    account_id TEXT NOT NULL,
    business_goal TEXT NOT NULL,
    constraints_json TEXT NOT NULL DEFAULT '{}',
    stage TEXT NOT NULL DEFAULT 'goal_defined',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_strategy_projects_scope
    ON account_strategy_projects(user_id, account_id, status);

CREATE TABLE IF NOT EXISTS audience_hypotheses (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES account_strategy_projects(id),
    user_id TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
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
    existence_hypotheses_json TEXT NOT NULL DEFAULT '[]',
    cognitive_style_hypotheses_json TEXT NOT NULL DEFAULT '[]',
    existence_strategy_hypotheses_json TEXT NOT NULL DEFAULT '[]',
    need_projection_hypotheses_json TEXT NOT NULL DEFAULT '[]',
    cognitive_projection_hypotheses_json TEXT NOT NULL DEFAULT '[]',
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
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
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
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
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
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
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
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
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
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
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
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
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

CREATE TABLE IF NOT EXISTS account_influence_calibrations (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES account_strategy_projects(id),
    user_id TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
    account_id TEXT NOT NULL,
    source_candidate_id TEXT NOT NULL REFERENCES marketing_learning_candidates(id),
    version INTEGER NOT NULL,
    formula_version TEXT NOT NULL,
    weights_json TEXT NOT NULL DEFAULT '{}',
    adjustment_json TEXT NOT NULL DEFAULT '{}',
    review_reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    UNIQUE(project_id, version),
    UNIQUE(source_candidate_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_influence_calibration_one_active
    ON account_influence_calibrations(project_id) WHERE status='active';
CREATE INDEX IF NOT EXISTS idx_influence_calibration_scope
    ON account_influence_calibrations(user_id, account_id, project_id, status);

CREATE TABLE IF NOT EXISTS account_experiments (
    id TEXT PRIMARY KEY,
    source_key TEXT,
    project_id TEXT NOT NULL REFERENCES account_strategy_projects(id),
    user_id TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
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
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
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
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
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
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
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
    human_review_status TEXT NOT NULL DEFAULT 'pending',
    human_review_note TEXT NOT NULL DEFAULT '',
    human_reviewed_at TEXT,
    archived_from_status TEXT NOT NULL DEFAULT '',
    archived_at TEXT,
    content_json TEXT NOT NULL DEFAULT '{}',
    metrics_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_content_assets_status ON content_assets(status);
CREATE INDEX IF NOT EXISTS idx_content_assets_account ON content_assets(account_id);
CREATE INDEX IF NOT EXISTS idx_content_assets_scope
    ON content_assets(user_id, account_id, updated_at);

CREATE TABLE IF NOT EXISTS media_asset_library (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
    account_id TEXT,
    name TEXT NOT NULL,
    media_type TEXT NOT NULL,
    role TEXT NOT NULL,
    source_type TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT '',
    provider_asset_id TEXT NOT NULL DEFAULT '',
    local_path TEXT NOT NULL DEFAULT '',
    mime_type TEXT NOT NULL DEFAULT '',
    sha256 TEXT NOT NULL DEFAULT '',
    size_bytes INTEGER NOT NULL DEFAULT 0,
    rights_status TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    receipt_json TEXT NOT NULL DEFAULT '{}',
    storage_tier TEXT NOT NULL DEFAULT 'library',
    expires_at TEXT,
    last_used_at TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_media_asset_library_scope
    ON media_asset_library(user_id, account_id, status, updated_at);

CREATE TABLE IF NOT EXISTS media_asset_references (
    id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES media_asset_library(id),
    owner_kind TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(asset_id, owner_kind, owner_id, relation)
);
CREATE INDEX IF NOT EXISTS idx_media_asset_references_asset
    ON media_asset_references(asset_id, created_at);

CREATE TABLE IF NOT EXISTS material_searches (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
    account_id TEXT NOT NULL,
    query_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    provider_errors_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_material_search_scope
    ON material_searches(user_id, account_id, created_at);

CREATE TABLE IF NOT EXISTS material_candidates (
    id TEXT PRIMARY KEY,
    search_id TEXT NOT NULL REFERENCES material_searches(id),
    user_id TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
    account_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_asset_id TEXT NOT NULL,
    media_type TEXT NOT NULL,
    role TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    preview_url TEXT NOT NULL DEFAULT '',
    download_url TEXT NOT NULL DEFAULT '',
    creator TEXT NOT NULL DEFAULT '',
    creator_url TEXT NOT NULL DEFAULT '',
    license_name TEXT NOT NULL DEFAULT '',
    license_url TEXT NOT NULL DEFAULT '',
    provider_home_url TEXT NOT NULL DEFAULT '',
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    duration REAL NOT NULL DEFAULT 0,
    score REAL NOT NULL DEFAULT 0,
    score_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'candidate',
    selected_media_asset_id TEXT REFERENCES media_asset_library(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(search_id, provider, provider_asset_id)
);
CREATE INDEX IF NOT EXISTS idx_material_candidate_scope
    ON material_candidates(user_id, account_id, search_id, score DESC);

CREATE TABLE IF NOT EXISTS marketing_audio_jobs (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
    account_id TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'voiceover',
    name TEXT NOT NULL,
    script_text TEXT NOT NULL,
    script_sha256 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'prepared',
    approval_ref TEXT,
    provider TEXT NOT NULL DEFAULT '',
    output_asset_id TEXT REFERENCES media_asset_library(id),
    receipt_json TEXT NOT NULL DEFAULT '{}',
    failure_code TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    settled_at TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_marketing_audio_job_scope
    ON marketing_audio_jobs(user_id, account_id, status, updated_at);

CREATE TABLE IF NOT EXISTS marketing_video_productions (
    id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
    account_id TEXT NOT NULL,
    source_asset_id TEXT NOT NULL REFERENCES content_assets(id),
    source_asset_version INTEGER NOT NULL,
    provider TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'prepared',
    edl_json TEXT NOT NULL,
    approval_ref TEXT,
    voice_asset_id TEXT REFERENCES media_asset_library(id),
    final_video_asset_id TEXT REFERENCES media_asset_library(id),
    output_asset_id TEXT REFERENCES content_assets(id),
    receipt_json TEXT NOT NULL DEFAULT '{}',
    failure_code TEXT,
    archived_from_status TEXT NOT NULL DEFAULT '',
    archived_at TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    settled_at TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_video_production_scope
    ON marketing_video_productions(user_id,account_id,status,updated_at);

CREATE TABLE IF NOT EXISTS marketing_preflight_records (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
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

CREATE TABLE IF NOT EXISTS marketing_topic_recommendation_batches (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
    account_id TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    source_session_id TEXT NOT NULL DEFAULT '',
    target_platforms_json TEXT NOT NULL DEFAULT '[]',
    input_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'building',
    delivery_text TEXT NOT NULL DEFAULT '',
    delivery_sha256 TEXT NOT NULL DEFAULT '',
    recommended_count INTEGER NOT NULL DEFAULT 0,
    research_only_count INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id,entity_id,as_of_date)
);
CREATE INDEX IF NOT EXISTS idx_marketing_topic_batch_scope
    ON marketing_topic_recommendation_batches(entity_id,as_of_date,status,updated_at);
CREATE INDEX IF NOT EXISTS idx_marketing_topic_batch_session
    ON marketing_topic_recommendation_batches(source_session_id,status,updated_at);

CREATE TABLE IF NOT EXISTS marketing_topic_recommendation_candidates (
    id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES marketing_topic_recommendation_batches(id),
    user_id TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
    account_id TEXT NOT NULL,
    rank INTEGER NOT NULL,
    topic TEXT NOT NULL,
    angle TEXT NOT NULL DEFAULT '',
    plan_id TEXT NOT NULL REFERENCES content_production_plans(id),
    preflight_id TEXT NOT NULL REFERENCES marketing_preflight_records(id),
    target_platforms_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    signal_refs_json TEXT NOT NULL DEFAULT '[]',
    decision_status TEXT NOT NULL,
    recommendation_eligible INTEGER NOT NULL DEFAULT 0,
    influence_score REAL NOT NULL DEFAULT 0,
    candidate_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(batch_id,rank)
);
CREATE INDEX IF NOT EXISTS idx_marketing_topic_candidate_batch
    ON marketing_topic_recommendation_candidates(batch_id,recommendation_eligible,rank);

CREATE TABLE IF NOT EXISTS marketing_topic_recommendation_delivery_receipts (
    source_session_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES marketing_topic_recommendation_batches(id),
    delivery_sha256 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'prepared',
    created_at TEXT NOT NULL,
    validated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_marketing_topic_delivery_batch
    ON marketing_topic_recommendation_delivery_receipts(batch_id,status,created_at);

CREATE TABLE IF NOT EXISTS marketing_receipt_refs (
    id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    receipt_type TEXT NOT NULL,
    user_id TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
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
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
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
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
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
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
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
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
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
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
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

CREATE TABLE IF NOT EXISTS marketing_public_content_cases (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
    account_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    source_item_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    creator_json TEXT NOT NULL DEFAULT '{}',
    first_content_json TEXT NOT NULL DEFAULT '{}',
    latest_content_json TEXT NOT NULL DEFAULT '{}',
    published_at TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id,account_id,platform,source_item_id)
);
CREATE INDEX IF NOT EXISTS idx_public_content_case_scope
    ON marketing_public_content_cases(user_id,account_id,platform,last_seen_at);

CREATE TABLE IF NOT EXISTS marketing_public_feedback_observations (
    id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES marketing_public_content_cases(id),
    user_id TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
    account_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    evidence_id TEXT NOT NULL REFERENCES evidence_records(id),
    observed_at TEXT NOT NULL,
    content_json TEXT NOT NULL DEFAULT '{}',
    metrics_json TEXT NOT NULL DEFAULT '{}',
    rank INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE(case_id,observed_at)
);
CREATE INDEX IF NOT EXISTS idx_public_feedback_case_time
    ON marketing_public_feedback_observations(case_id,observed_at);
CREATE INDEX IF NOT EXISTS idx_short_video_observation_scope
    ON marketing_short_video_observations(user_id,account_id,platform,observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_short_video_observation_sound
    ON marketing_short_video_observations(sound_id,platform,observed_at DESC);

CREATE TABLE IF NOT EXISTS marketing_account_portfolio_snapshots (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
    account_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    account_name TEXT NOT NULL DEFAULT '',
    source_count INTEGER NOT NULL DEFAULT 0,
    portfolio_json TEXT NOT NULL DEFAULT '{}',
    score_json TEXT NOT NULL DEFAULT '{}',
    session_id TEXT NOT NULL DEFAULT '',
    tool_call_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(user_id,account_id,platform,observed_at)
);
CREATE INDEX IF NOT EXISTS idx_account_portfolio_latest
    ON marketing_account_portfolio_snapshots(user_id,account_id,platform,observed_at DESC);

CREATE TABLE IF NOT EXISTS marketing_owned_content_observations (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES marketing_account_portfolio_snapshots(id),
    user_id TEXT NOT NULL,
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
    account_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    source_item_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    evidence_id TEXT NOT NULL REFERENCES evidence_records(id),
    title TEXT NOT NULL DEFAULT '',
    digest TEXT NOT NULL DEFAULT '',
    content_excerpt TEXT NOT NULL DEFAULT '',
    published_at TEXT,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    features_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(snapshot_id,source_item_id)
);
CREATE INDEX IF NOT EXISTS idx_owned_content_scope
    ON marketing_owned_content_observations(user_id,account_id,platform,published_at DESC);

CREATE TABLE IF NOT EXISTS marketing_knowledge_entries (
    id TEXT PRIMARY KEY,
    knowledge_base TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT 'default',
    entity_id TEXT NOT NULL DEFAULT '' REFERENCES marketing_operating_entities(id),
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
ENTITY_OWNED_SCOPE_COLUMNS = {
    "marketing_operations": "account_id",
    "account_strategy_projects": "account_id",
    "audience_hypotheses": "account_id",
    "creator_operating_profiles": "account_id",
    "market_route_hypotheses": "account_id",
    "benchmark_accounts": "target_account_id",
    "benchmark_observations": "target_account_id",
    "positioning_versions": "account_id",
    "content_system_versions": "account_id",
    "account_influence_calibrations": "account_id",
    "account_experiments": "account_id",
    "evidence_records": "account_id",
    "content_production_plans": "account_id",
    "content_assets": "account_id",
    "media_asset_library": "account_id",
    "material_searches": "account_id",
    "material_candidates": "account_id",
    "marketing_audio_jobs": "account_id",
    "marketing_video_productions": "account_id",
    "marketing_preflight_records": "account_id",
    "marketing_topic_recommendation_batches": "account_id",
    "marketing_topic_recommendation_candidates": "account_id",
    "marketing_receipt_refs": "account_id",
    "marketing_learning_candidates": "account_id",
    "marketing_publish_actions": "account_id",
    "marketing_metric_checkpoints": "account_id",
    "marketing_knowledge_contributions": "account_id",
    "marketing_knowledge_entries": "account_id",
    "marketing_short_video_observations": "account_id",
    "marketing_public_content_cases": "account_id",
    "marketing_public_feedback_observations": "account_id",
    "marketing_account_portfolio_snapshots": "account_id",
    "marketing_owned_content_observations": "account_id",
    # Optional compatibility tables may exist in upgraded product databases.
    "audience_snapshots": "account_id",
    "memory_candidates": "account_id",
}

# Account adoption uses the same inventory, but changes only the channel
# provenance column.  ``entity_id`` remains stable across the adoption.
PROSPECT_SCOPE_COLUMNS = ENTITY_OWNED_SCOPE_COLUMNS

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
    "marketing_video_productions",
    "marketing_preflight_records",
    "marketing_topic_recommendation_batches",
    "marketing_topic_recommendation_candidates",
    "marketing_topic_recommendation_delivery_receipts",
    "marketing_receipt_refs",
    "marketing_learning_candidates",
    "account_influence_calibrations",
    "marketing_publish_actions",
    "marketing_metric_checkpoints",
    "marketing_sounds",
    "marketing_short_video_observations",
    "marketing_public_content_cases",
    "marketing_public_feedback_observations",
    "marketing_account_portfolio_snapshots",
    "marketing_owned_content_observations",
    "marketing_knowledge_entries",
)
