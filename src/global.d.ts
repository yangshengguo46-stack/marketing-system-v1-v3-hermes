export {}

declare global {
  type Platform =
    | 'douyin'
    | 'wechat_channels'
    | 'wechat_official'
    | 'bilibili'
    | 'xiaohongshu'
    | 'kuaishou'
    | 'zhihu'
    | 'tiktok'
    | 'youtube'
    | 'instagram'
    | 'facebook'
    | 'twitter'

  interface Window {
    marketingOS: {
      runtimeApi: (method: string, path: string, body?: unknown) => Promise<unknown>
      getRuntimeStatus: () => Promise<{ running: boolean; port: number }>
      restartRuntime: () => Promise<{ status: string }>
      setProviderSecret: (name: 'PEXELS_API_KEY' | 'FIRECRAWL_API_KEY', value: string) => Promise<{ saved: boolean; name: string }>
      openAttribution: (url: string) => Promise<{ opened: boolean }>
      onRuntimeStatus: (cb: (data: { status: string; port?: number; error?: string }) => void) => () => void
      openLoginBrowser: (platform: string, accountId?: string) => Promise<{ platform: string; account_id: string }>
      mcpLoginStart: (accountId: string, platform: string) => Promise<MCPLoginAttempt>
      mcpLoginStatus: (accountId: string) => Promise<MCPLoginAttempt>
      mcpLoginCancel: (accountId: string, attemptId?: string) => Promise<MCPLoginAttempt>
      mcpBrowserTakeover: (accountId: string) => Promise<MCPBrowserState>
      mcpBrowserBackground: (accountId: string) => Promise<MCPBrowserState>
      mcpBrowserStop: (accountId: string) => Promise<MCPBrowserState>
      closeLoginBrowser: (platform: string, accountId?: string) => Promise<{ closed: boolean }>
      closeAllLoginBrowsers: () => Promise<{ closed: boolean }>
      navigateLoginBrowser: (platform: string, accountId: string, action: 'back' | 'reload' | 'home' | 'focus') => Promise<{ url: string }>
      getLoginCookies: (platform: string, accountId: string) => Promise<{ platform: string; count: number; account_id: string }>
      runIntelligence: () => Promise<IntelligenceReport>
      onIntelligenceProgress: (cb: (report: IntelligenceReport) => void) => () => void
      onTrendingUpdated: (cb: (result: { status: string; trends_count?: number; error?: string }) => void) => () => void
      getChannelStatus: () => Promise<MessagingChannelStatus>
      connectChannel: (platform: MessagingPlatform) => Promise<{ connected: boolean }>
      cancelChannel: (platform: MessagingPlatform) => Promise<{ cancelled: boolean }>
      testChannel: (platform: MessagingPlatform) => Promise<{ success: boolean; detail?: string }>
      retryChannel: (deliveryId: string) => Promise<{ success: boolean; detail?: string }>
      onChannelProgress: (cb: (event: MessagingChannelEvent) => void) => () => void
      onLoginOpened: (cb: (data: { platform: string; url: string }) => void) => () => void
      onLoginClosed: (cb: (data: { platform: string }) => void) => () => void
      onLoginCookies: (cb: (data: { platform: string; account_id: string; count: number; username: string; label: string }) => void) => () => void
      onLoginQr: (cb: (data: { platform: string; qrImage: string }) => void) => () => void
      onLoginError: (cb: (data: { platform: string; message: string }) => void) => () => void
      onLoginInteraction: (cb: (data: { platform: string; kind: 'qrcode' | 'verification' | 'interactive' }) => void) => () => void
      streamAgentEvents: (taskId: string) => Promise<{ started: boolean; task_id: string }>
      stopAgentEvents: (taskId: string) => Promise<{ stopped: boolean; task_id: string }>
      onAgentEvent: (cb: (event: LiveAgentEvent) => void) => () => void
      checkAccountHealth: (platform: string, username: string, accountId: string) => Promise<{ status: string; detail: string }>
      syncAccountMetrics: (accountId: string) => Promise<Record<string, unknown>>
      clearAccountSession: (platform: string, accountId: string) => Promise<{ cleared: boolean }>
      runNetworkDiagnostic: () => Promise<{ results: Array<{ target: string; status: string; detail: string }>; summary: string }>
      executeApprovedCapability: (approvalId: string, scope: 'once' | 'session' | 'permanent') => Promise<unknown>
      importMediaAttachment: (assetId: string) => Promise<{
        cancelled: boolean; id?: string; asset_id?: string; original_name?: string
        mime_type?: string; byte_size?: number; sha256?: string; position?: number
      }>
      importStockImage: (assetId: string, candidate: {
        provider: string; provider_id: string; download_url: string; source_url: string
        author: string; author_url: string; license: string
      }) => Promise<{ imported: boolean; id: string; position: number }>
      deleteMediaAttachmentForAsset: (assetId: string) => Promise<{ deleted: boolean; id?: string; count?: number; reason?: string }>
    }
  }

  interface MCPLoginAttempt {
    login_attempt_id?: string
    account_id: string
    platform?: string
    status: 'idle' | 'starting' | 'browser_open' | 'authenticated' | 'cancelled' | 'timed_out' | 'error'
    reason?: string
    account?: Account
  }

  interface MCPBrowserState {
    account_id: string
    platform?: string
    status: string
    headless?: boolean | null
    takeover?: boolean
    stopped?: boolean
  }

  type MessagingPlatform = 'weixin' | 'feishu'

  interface MessagingChannelState {
    connected: boolean
    ready_to_push: boolean
    identity?: string
    last_delivery?: MessagingDelivery | null
  }

  interface MessagingDelivery {
    id: string
    platform: MessagingPlatform
    kind: 'test' | 'intelligence' | 'retry'
    success: boolean
    error?: string | null
    created_at: string
  }

  interface MessagingChannelStatus {
    weixin: MessagingChannelState
    feishu: MessagingChannelState
  }

  interface MessagingChannelEvent {
    event: 'starting' | 'qr' | 'connected' | 'error' | 'status' | 'cancelled'
    platform?: MessagingPlatform
    qr_url?: string
    qr_image?: string
    message?: string
    ready_to_push?: boolean
    channels?: MessagingChannelStatus
  }

  interface TrendItem {
    rank: number
    title: string
    heat?: string
    heat_value?: string | number
    source_platform: Platform
    relevance_score?: number
    relevance_label?: string
    match_reasons?: string[]
    fit_mode?: 'exploration' | 'account_positioning' | string
  }

  interface Account {
    id: string
    platform: Platform
    username: string
    label: string
    created_at: string
    status: 'connected' | 'disconnected' | 'expired' | 'error'
    stats: Record<string, unknown>
  }

  interface Suggestion {
    id: string
    trend: string
    trend_source: string
    hot_level: string
    angles: string[]
    target_audience: string
    estimated_traffic: string
  }

  interface CreativeBrief {
    id: string
    kind: 'daily' | 'trend' | 'idea' | 'all_tasks'
    title: string
    source_platform?: Platform | string
    source_label?: string
    heat?: string
    rank?: number
    hot_level?: string
    target_audience?: string
    angles?: string[]
    evidence?: Array<{ label: string; value: string }>
    recommended_action?: string
    created_at?: string
  }

  interface AgentSessionSummary {
    session_id: string
    user_id: string
    workspace?: string | null
    active_task_id?: string | null
    title: string
    last_objective?: string | null
    last_task_id?: string | null
    last_task_status?: string | null
    account_id?: string | null
    task_count: number
    created_at: string
    updated_at: string
  }

  interface AgentChatMessage {
    role: 'user' | 'assistant' | 'system'
    content: string
    task_id?: string
    created_at?: string
  }

  interface OverviewData {
    accounts_connected: number
    trending_topics_today: number
    suggestions_generated: number
    videos_published: number
    total_followers: number
    follower_growth_today: number
    content_pipeline: {
      total_assets: number
      drafts: number
      in_review: number
      approved: number
      published: number
      ready_to_publish: number
      latest_draft?: null | {
        id?: string
        title?: string
        platform?: string | null
        updated_at?: string | null
      }
    }
    publishing_receipts: {
      total: number
      verified: number
      pending_verification: number
      failed: number
      metric_checkpoints: {
        total: number
        scheduled: number
        collected: number
        due: number
      }
      next_metrics_at?: string | null
      latest?: null | {
        id?: string
        asset_id?: string
        platform?: string
        status?: string
        verified?: boolean
        published_at?: string | null
        next_metrics_at?: string | null
      }
    }
    platform_accounts: Array<{
      id: string; platform: Platform; label: string; status: Account['status']
      stats: Record<string, unknown>
      history: Array<{ at: string; followers: number | string; views: number | string }>
    }>
  }

  interface IntelligenceStep {
    id: string
    label: string
    status: 'running' | 'completed' | 'partial' | 'failed' | 'skipped'
    detail: string
    evidence?: Record<string, unknown>
    updated_at?: string
  }

  interface IntelligenceReport {
    status: 'never_run' | 'running' | 'completed' | 'partial' | 'failed'
    started_at?: string | null
    completed_at?: string | null
    steps: IntelligenceStep[]
    errors: Array<{ scope: string; target: string; message: string }>
    summary: Record<string, unknown>
  }

  interface MemoryEntry {
    id: string
    kind: string
    user_id: string
    account_id?: string | null
    platform?: string | null
    content: string
    evidence: Record<string, unknown>[]
    confidence: number
    status: string
    rejection_reason?: string | null
    observed_at: string
    valid_from?: string | null
    valid_to?: string | null
    created_at: string
  }

  interface PlanStep {
    id: string
    description: string
    tool_name?: string | null
    tool_guess?: string | null
    status: 'pending' | 'running' | 'waiting_approval' | 'completed' | 'skipped' | 'failed'
    approval_id?: string | null
    effect_id?: string | null
    result_status?: string | null
  }

  interface LiveAgentEvent {
    type: string
    task_id?: string
    label?: string
    detail?: unknown
    status?: string
    tool?: string
    approval_id?: string
    capability?: string
    risk_summary?: string
    arguments?: Record<string, unknown>
    decision?: string
    reason?: string
    error?: string
    reply?: string
    plan?: PlanStep[]
    plan_step_id?: string
    plan_total?: number
    plan_version?: number
    resume_step?: string
  }
}
