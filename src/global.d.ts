export {}

declare global {
  type Platform =
    | 'douyin'
    | 'wechat_channels'
    | 'weibo'
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
      api: (method: string, path: string, body?: unknown) => Promise<unknown>
      getHermesStatus: () => Promise<{ running: boolean; port: number }>
      restartHermes: () => Promise<{ status: string }>
      onHermesStatus: (cb: (data: { status: string; port?: number; error?: string }) => void) => () => void
      openLoginBrowser: (platform: string) => Promise<void>
      closeLoginBrowser: (platform: string) => Promise<void>
      getLoginCookies: (platform: string) => Promise<{ platform: string; count: number }>
      scrapeIndustry: (platform: string, keyword: string) => Promise<{ platform: string; keyword: string; items: Array<{ rank: number; title: string; url: string }>; collected_at: string }>
      syncAccountSession: (platform: string, username: string) => Promise<Record<string, number>>
      runIntelligence: () => Promise<IntelligenceReport>
      onIntelligenceProgress: (cb: (report: IntelligenceReport) => void) => () => void
      getChannelStatus: () => Promise<MessagingChannelStatus>
      connectChannel: (platform: MessagingPlatform) => Promise<{ connected: boolean }>
      testChannel: (platform: MessagingPlatform) => Promise<{ success: boolean; detail?: string }>
      retryChannel: (deliveryId: string) => Promise<{ success: boolean; detail?: string }>
      onChannelProgress: (cb: (event: MessagingChannelEvent) => void) => () => void
      onLoginOpened: (cb: (data: { platform: string; url: string }) => void) => () => void
      onLoginClosed: (cb: (data: { platform: string }) => void) => () => void
      onLoginCookies: (cb: (data: { platform: string; count: number; username: string; label: string }) => void) => () => void
    }
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
    event: 'qr' | 'connected' | 'error' | 'status'
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
    source_platform: Platform
  }

  interface Account {
    id: string
    platform: Platform
    username: string
    label: string
    bitwarden_id?: string
    created_at: string
    status: 'active' | 'expired'
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

  interface OverviewData {
    accounts_connected: number
    trending_topics_today: number
    suggestions_generated: number
    videos_published: number
    total_followers: number
    follower_growth_today: number
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
}
