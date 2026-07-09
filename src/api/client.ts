const BASE = '/api/marketing-os'

const mOS = window.marketingOS

function request(method: string, path: string, body?: unknown) {
  if (!mOS) return Promise.reject(new Error('Marketing OS bridge is unavailable'))
  return mOS.runtimeApi(method, path, body)
}

export const api = {
  overview: () => request('GET', `${BASE}/dashboard/overview`) as Promise<OverviewData>,

  trending: (accountId?: string | null) => request('GET', `${BASE}/trending${accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''}`),
  refreshTrending: () => request('POST', `${BASE}/trending/refresh`),
  importTrending: (data: { platform: string; keyword: string; items: Array<{ rank: number; title: string; url: string }> }) =>
    request('POST', `${BASE}/trending/import`, data),
  importTrendingBatch: (collections: Array<{ platform: string; keyword: string; items: Array<{ rank: number; title: string; url: string }> }>) =>
    request('POST', `${BASE}/trending/import-batch`, { collections }),

  accounts: () => request('GET', `${BASE}/accounts`) as Promise<{ accounts: Account[]; total: number }>,
  addAccount: (data: { account_id: string; platform: string; username: string; label?: string }) =>
    request('POST', `${BASE}/accounts`, data),
  deleteAccount: (id: string) => request('DELETE', `${BASE}/accounts/${id}`),
  updateAccountStatus: (id: string, status: Account['status']) => request('PUT', `${BASE}/accounts/${id}/status`, { status }),
  updateAccountStats: (id: string, data: Record<string, number>) => request('PUT', `${BASE}/accounts/${id}/stats`, data),
  accountLifecycle: (id: string) => request('GET', `${BASE}/accounts/${id}/lifecycle`) as Promise<{
    project_id: string | null
    stage: string
    next_action: string
    data_gaps: string[]
    benchmark_readiness?: { ready?: boolean; missing?: string[] }
  }>,
  prospectLifecycle: () => request('GET', `${BASE}/lifecycle/prospect`) as Promise<{
    project_id: string | null
    stage: string
    next_action: string
    data_gaps: string[]
    benchmark_readiness?: { ready?: boolean; missing?: string[] }
  }>,
  bindProspectStrategy: (id: string, data: { project_id: string; prospect_account_id?: string }) =>
    request('POST', `${BASE}/accounts/${id}/lifecycle/bind-prospect`, data) as Promise<{
      status: 'bound' | 'already_bound'
      project_id: string
      account_id: string
    }>,

  suggestions: (accountId?: string | null) => request('GET', `${BASE}/suggestions${accountId ? `?account_id=${encodeURIComponent(accountId)}` : ''}`),

  profiles: () => request('GET', `${BASE}/profiles`),
  updateProfile: (id: string, data: unknown) => request('PUT', `${BASE}/profiles/${id}`, data),
  assistantStatus: () => request('GET', `${BASE}/assistant/status`),
  mcpStatus: () => request('GET', `${BASE}/mcp/status`),

  publishingTasks: () => request('GET', `${BASE}/publishing/tasks`),
  createPublishingTask: (data: { title: string; platform?: string; status?: string; scheduled_at?: string }) =>
    request('POST', `${BASE}/publishing/tasks`, data),
  deletePublishingTask: (id: string) => request('DELETE', `${BASE}/publishing/tasks/${id}`),
  sqlPublishingTasks: () =>
    request('GET', `${BASE}/publishing/sql-tasks`) as Promise<{ tasks: unknown[]; total: number; source: string }>,
  querySqlPublishingTask: (id: string, refresh = true) =>
    request('POST', `${BASE}/publishing/sql-tasks/${id}/query`, { refresh }),
  collectSqlPublishingMetrics: (id: string, data: {
    metrics: Record<string, number>
    checkpoint_id?: string
    provenance?: Record<string, unknown>
  }) => request('POST', `${BASE}/publishing/sql-tasks/${id}/metrics`, data),

  analyticsSummary: () => request('GET', `${BASE}/analytics/summary`),

  workflowStatus: () => request('GET', `${BASE}/workflow/status`),
  updateWorkflowStatus: (data: { enabled?: boolean; schedule_time?: string }) => request('PUT', `${BASE}/workflow/status`, data),
  runWorkflow: () => request('POST', `${BASE}/workflow/run`),
  completeWorkflow: (data: unknown) => request('POST', `${BASE}/workflow/complete`, data),

  intelligenceConfig: () => request('GET', `${BASE}/intelligence/config`),
  updateIntelligenceConfig: (data: { industries?: string[]; platforms?: string[]; sync_accounts?: boolean }) =>
    request('PUT', `${BASE}/intelligence/config`, data),
  intelligenceReport: () => request('GET', `${BASE}/intelligence/report`),

  memories: (kind?: string) =>
    request('GET', `${BASE}/memories${kind ? `?kind=${kind}` : ''}`),
  deleteMemory: (id: string) =>
    request('DELETE', `${BASE}/memories/${id}`),
  updateMemory: (id: string, data: { status?: string; content?: string }) =>
    request('PUT', `${BASE}/memories/${id}`, data),

  authorizations: () => request('GET', `${BASE}/authorizations`),
  revokeAuthorization: (capability: string) =>
    request('DELETE', `${BASE}/authorizations/${encodeURIComponent(capability)}`),

  contentAssets: (status?: string) =>
    request('GET', `${BASE}/content/assets${status ? `?status=${status}` : ''}`),
  createContentAsset: (data: { title: string; type?: string; platform?: string; account_id?: string; content?: unknown }) =>
    request('POST', `${BASE}/content/assets`, data),
  transitionContentAsset: (id: string, status: string) =>
    request('PUT', `${BASE}/content/assets/${id}/status`, { status }),
  updateContentMetrics: (id: string, data: Record<string, unknown>) =>
    request('POST', `${BASE}/content/assets/${id}/metrics`, data),
  contentAssetAttachment: (id: string, accountId: string) =>
    request('GET', `${BASE}/content/assets/${id}/attachment?account_id=${encodeURIComponent(accountId)}`) as Promise<{
      attachment: null | { id: string; original_name: string; mime_type: string; byte_size: number; sha256: string; position: number }
      attachments: Array<{ id: string; original_name: string; mime_type: string; byte_size: number; sha256: string; position: number }>
    }>,
  stockImageStatus: () => request('GET', `${BASE}/stock-images/status`) as Promise<{
    provider: string; configured: boolean; attribution: string; provider_url: string
  }>,
  searchStockImages: (query: string) => request('POST', `${BASE}/stock-images/search`, {
    query, limit: 12, orientation: 'portrait',
  }) as Promise<{
    provider: string; query: string; attribution: string; provider_url: string
    candidates: Array<{
      provider: string; provider_id: string; preview_url: string; download_url: string
      source_url: string; author: string; author_url: string; alt: string
      width: number; height: number; license: string
    }>
  }>,
  firecrawlStatus: () => request('GET', `${BASE}/firecrawl/status`) as Promise<{
    configured: boolean; mode: 'cloud' | 'self_hosted' | 'invalid'; api_url?: string; error?: string
  }>,
  firecrawlSearch: (query: string, limit = 8) => request('POST', `${BASE}/firecrawl/search`, { query, limit }),
  indexTts2Status: () => request('GET', `${BASE}/tts/index-tts2/status`) as Promise<{
    provider: 'index_tts2'
    source_dir: string
    model_dir: string
    source_available: boolean
    cli_available: boolean
    model_dir_exists: boolean
    required_files: string[]
    missing_files: string[]
    ready: boolean
    license_file: string
    official_source: string
    run_hint: string
  }>,
  synthesizeVolcengineTtsV1: (data: {
    text: string
    api_key?: string
    output_dir?: string
    voice_type?: string
    cluster?: string
    encoding?: 'mp3' | 'wav' | 'ogg' | 'pcm' | 'aac' | 'm4a'
    speed_ratio?: number
    uid?: string
  }) => request('POST', `${BASE}/tts/volcengine/v1/synthesize`, data) as Promise<{
    status: 'ok'
    provider: 'volcengine_tts_v1'
    output_path: string
    byte_size: number
    sha256: string
    duration_ms?: number
    duration_sec?: number
    voice_type: string
    reqid: string
  }>,
  contentProductionPlan: (data: {
    objective: string
    kind?: 'auto' | 'article_soft' | 'faceless_video' | 'premium_human_video'
    platforms?: string[]
    account_id?: string
  }) => request('POST', `${BASE}/content/production/plan`, data),
  contentProductionPreflight: (data: {
    objective: string
    kind?: 'auto' | 'article_soft' | 'faceless_video' | 'premium_human_video'
    platforms?: string[]
    account_id?: string
    audience_context?: Record<string, unknown>
    evidence?: Array<Record<string, unknown>>
    memory_refs?: string[]
    receipt_refs?: string[]
    asset_id?: string
  }) => request('POST', `${BASE}/content/production/preflight`, data),
  influenceScore: (assetId: string) =>
    request('GET', `${BASE}/influence/score?asset_id=${encodeURIComponent(assetId)}`),
  preflightDecision: (data: {
    asset_id?: string
    stage?: 'production_draft' | 'render_prepare' | 'publish_review' | 'launch'
    context?: Record<string, unknown>
    metric_labels?: Record<string, unknown>
    content_score?: Record<string, unknown>
    preflight_scores?: Record<string, unknown>
  }) => request('POST', `${BASE}/preflight/decision`, data),
  learningCandidates: (filters?: {
    account_id?: string
    platform?: string
    candidate_type?: 'memory' | 'strategy' | 'weight'
    status?: 'pending' | 'accepted' | 'rejected' | 'superseded'
    limit?: number
  }) => {
    const query = new URLSearchParams()
    Object.entries(filters || {}).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') query.set(key, String(value))
    })
    return request('GET', `${BASE}/learning/candidates${query.toString() ? `?${query.toString()}` : ''}`)
  },
  weightCandidateReplay: (candidateId: string, options?: { window?: number; min_support?: number }) => {
    const query = new URLSearchParams({ candidate_id: candidateId })
    if (options?.window) query.set('window', String(options.window))
    if (options?.min_support) query.set('min_support', String(options.min_support))
    return request('GET', `${BASE}/learning/weight-replay?${query.toString()}`)
  },
  decideWeightCandidate: (data: {
    candidate_id: string
    decision: 'accepted' | 'rejected'
    reason?: string
    window?: number
    min_support?: number
  }) => request('POST', `${BASE}/learning/weight-decision`, data),
  createSoftArticleAsset: (data: {
    objective: string
    topic?: string
    title?: string
    platforms?: Array<'zhihu' | 'wechat_official'>
    account_id?: string
    audience_context?: Record<string, unknown>
    evidence?: Array<Record<string, unknown>>
  }) => request('POST', `${BASE}/content/production/article-soft`, data),
  createFacelessVideoAsset: (data: {
    objective: string
    topic?: string
    title?: string
    platforms?: Array<'douyin' | 'wechat_channels' | 'bilibili'>
    account_id?: string
    evidence?: Array<Record<string, unknown>>
  }) => request('POST', `${BASE}/content/production/faceless-video`, data),
  createContentFromExperiment: (data: {
    account_id: string
    project_id?: string
    experiment_id: string
    kind?: 'auto' | 'article_soft' | 'faceless_video' | 'premium_human_video'
    platforms?: Array<'zhihu' | 'wechat_official' | 'douyin' | 'wechat_channels' | 'bilibili'>
    objective?: string
    topic?: string
    title?: string
    audience_context?: Record<string, unknown>
    evidence?: Array<Record<string, unknown>>
  }) => request('POST', `${BASE}/content/production/from-experiment`, data),
  prepareFacelessRender: (data: {
    asset_id: string
    project_dir?: string
    output_path?: string
    ffmpeg_path?: string
    ffprobe_path?: string
  }) => request('POST', `${BASE}/content/production/faceless-render/prepare`, data),
  renderFacelessAnimatic: (data: {
    asset_id: string
    project_dir: string
    output_path?: string
    ffmpeg_path?: string
    ffprobe_path?: string
    fontfile?: string
  }) => request('POST', `${BASE}/content/production/faceless-render/animatic`, data),
  fillFacelessImageMaterials: (data: {
    asset_id: string
    project_dir: string
    materials: Array<{
      slot_id?: string
      shot_id?: string
      local_path: string
      provider?: 'pexels' | 'user_supplied'
      source_url?: string
      author?: string
      license?: string
      sha256?: string
      download_hash?: string
    }>
    ffmpeg_path?: string
    ffprobe_path?: string
  }) => request('POST', `${BASE}/content/production/faceless-render/fill-image-materials`, data),
  renderFacelessFinal: (data: {
    asset_id: string
    project_dir: string
    output_path?: string
    subtitle_path?: string
    ffmpeg_path?: string
    ffprobe_path?: string
    burn_subtitles?: boolean
    write_subtitles?: boolean
    voiceover_audio_path?: string
    bgm_audio_path?: string
    voice_volume?: number
    bgm_volume?: number
    voiceover_provenance?: {
      provider?: 'user_supplied' | 'pixabay' | 'pexels' | 'freesound' | 'volcengine_tts_v1'
      source_url?: string
      author?: string
      license?: string
      sha256?: string
      download_hash?: string
    }
    bgm_provenance?: {
      provider?: 'user_supplied' | 'pixabay' | 'pexels' | 'freesound' | 'volcengine_tts_v1'
      source_url?: string
      author?: string
      license?: string
      sha256?: string
      download_hash?: string
    }
  }) => request('POST', `${BASE}/content/production/faceless-render/final`, data),
  deleteContentAsset: (id: string) =>
    request('DELETE', `${BASE}/content/assets/${id}`),
}

export const agent = {
  createSession: (userId?: string, workspace?: string) =>
    request('POST', '/agent/sessions', { user_id: userId || 'default', workspace }) as Promise<{ session_id: string; user_id: string }>,
  listSessions: () =>
    request('GET', '/agent/sessions') as Promise<{ sessions: AgentSessionSummary[]; total: number }>,
  getSession: (sessionId: string) =>
    request('GET', `/agent/sessions/${sessionId}`) as Promise<{ session_id: string; active_task_id: string | null }>,
  getSessionMessages: (sessionId: string) =>
    request('GET', `/agent/sessions/${sessionId}/messages`) as Promise<{ session_id: string; messages: AgentChatMessage[] }>,
  sendMessage: (sessionId: string, message: string, accountId?: string) =>
    request('POST', '/agent/messages', { session_id: sessionId, message, account_id: accountId }) as Promise<{ task_id: string; session_id: string; status: string }>,
  getTaskStatus: (taskId: string) =>
    request('GET', `/agent/runs/${taskId}`) as Promise<{
      task_id: string; status: string; objective: string; current_step?: string
      plan?: PlanStep[]; plan_version?: number; event_count?: number
      retry_count?: number; last_error?: string
    }>,
  cancelTask: (taskId: string) =>
    request('POST', `/agent/tasks/${taskId}/cancel`),
  pauseTask: (taskId: string) =>
    request('POST', `/agent/tasks/${taskId}/pause`),
  resumeTask: (taskId: string) =>
    request('POST', `/agent/tasks/${taskId}/resume`),
  replanTask: (taskId: string, message: string) =>
    request('POST', `/agent/tasks/${taskId}/replan`, { message }) as Promise<{ task_id: string; status: string; objective: string }>,
  rejectAction: (approvalId: string, reason?: string) =>
    request('POST', `/agent/approvals/${approvalId}/reject`, { reason }),
  submitEffectResult: (approvalId: string, result: unknown, idempotencyKey?: string) =>
    request('POST', '/agent/effects/submit', {
      approval_id: approvalId, receipt: result,
      idempotency_key: idempotencyKey || `effect_${approvalId}`,
    }),
  executeCapability: (approvalId: string, scope: 'once' | 'session' | 'permanent') =>
    mOS.executeApprovedCapability(approvalId, scope),
  startEventStream: (taskId: string) => mOS.streamAgentEvents(taskId),
  stopEventStream: (taskId: string) => mOS.stopAgentEvents(taskId),
  onEvent: (cb: (event: LiveAgentEvent) => void) => mOS.onAgentEvent(cb),
}

export const runtime = {
  status: () => mOS.getRuntimeStatus(),
  restart: () => mOS.restartRuntime(),
  onStatus: (cb: (data: { status: string }) => void) =>
    mOS.onRuntimeStatus(cb),
}

export const hermes = runtime

export const PLATFORM_NAMES: Record<string, string> = {
  douyin: '抖音', bilibili: 'B站',
  xiaohongshu: '小红书', kuaishou: '快手', zhihu: '知乎',
  wechat_channels: '视频号', wechat_official: '公众号',
  tiktok: 'TikTok', youtube: 'YouTube',
  instagram: 'Instagram', facebook: 'Facebook', twitter: 'X',
}

export const PLATFORM_COLORS: Record<string, string> = {
  douyin: '#FE2C55', bilibili: '#FB7299',
  xiaohongshu: '#FE2C55', kuaishou: '#FF4906', zhihu: '#1772F6',
  wechat_channels: '#07C160', wechat_official: '#07C160',
  tiktok: '#161823', youtube: '#FF0000',
  instagram: '#C13584', facebook: '#1877F2', twitter: '#111111',
}
