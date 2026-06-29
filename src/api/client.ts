const BASE = '/api/plugins/marketing-os'

const mOS = window.marketingOS

function request(method: string, path: string, body?: unknown) {
  if (!mOS) return Promise.reject(new Error('Marketing OS bridge is unavailable'))
  return mOS.api(method, path, body)
}

export const api = {
  overview: () => request('GET', `${BASE}/dashboard/overview`) as Promise<OverviewData>,

  trending: () => request('GET', `${BASE}/trending`),
  refreshTrending: () => request('POST', `${BASE}/trending/refresh`),
  importTrending: (data: { platform: string; keyword: string; items: Array<{ rank: number; title: string; url: string }> }) =>
    request('POST', `${BASE}/trending/import`, data),
  importTrendingBatch: (collections: Array<{ platform: string; keyword: string; items: Array<{ rank: number; title: string; url: string }> }>) =>
    request('POST', `${BASE}/trending/import-batch`, { collections }),

  accounts: () => request('GET', `${BASE}/accounts`) as Promise<{ accounts: Account[]; total: number }>,
  addAccount: (data: { platform: string; username: string; password?: string; label?: string; cookie?: string }) =>
    request('POST', `${BASE}/accounts`, data),
  deleteAccount: (id: string) => request('DELETE', `${BASE}/accounts/${id}`),
  updateAccountStats: (id: string, data: Record<string, number>) => request('PUT', `${BASE}/accounts/${id}/stats`, data),
  syncAccount: (id: string) => request('POST', `${BASE}/accounts/${id}/sync`),

  suggestions: () => request('GET', `${BASE}/suggestions`),

  profiles: () => request('GET', `${BASE}/profiles`),
  updateProfile: (id: string, data: unknown) => request('PUT', `${BASE}/profiles/${id}`, data),
  assistantStatus: () => request('GET', `${BASE}/assistant/status`),
  assistantMessage: (message: string, history: Array<{ role: 'user' | 'assistant'; content: string }> = []) =>
    request('POST', `${BASE}/assistant/message`, { message, history }),

  publishingTasks: () => request('GET', `${BASE}/publishing/tasks`),
  createPublishingTask: (data: { title: string; platform?: string; status?: string; scheduled_at?: string }) =>
    request('POST', `${BASE}/publishing/tasks`, data),
  deletePublishingTask: (id: string) => request('DELETE', `${BASE}/publishing/tasks/${id}`),

  analyticsSummary: () => request('GET', `${BASE}/analytics/summary`),

  workflowStatus: () => request('GET', `${BASE}/workflow/status`),
  updateWorkflowStatus: (data: { enabled?: boolean; schedule_time?: string }) => request('PUT', `${BASE}/workflow/status`, data),
  runWorkflow: () => request('POST', `${BASE}/workflow/run`),
  completeWorkflow: (data: unknown) => request('POST', `${BASE}/workflow/complete`, data),

  intelligenceConfig: () => request('GET', `${BASE}/intelligence/config`),
  updateIntelligenceConfig: (data: { industries?: string[]; platforms?: string[]; sync_accounts?: boolean }) =>
    request('PUT', `${BASE}/intelligence/config`, data),
  intelligenceReport: () => request('GET', `${BASE}/intelligence/report`),
}

export const hermes = {
  status: () => mOS.getHermesStatus(),
  restart: () => mOS.restartHermes(),
  onStatus: (cb: (data: { status: string }) => void) => mOS.onHermesStatus(cb),
}

export const PLATFORM_NAMES: Record<string, string> = {
  douyin: '抖音', weibo: '微博', bilibili: 'B站',
  xiaohongshu: '小红书', kuaishou: '快手', zhihu: '知乎',
  wechat_channels: '视频号', tiktok: 'TikTok', youtube: 'YouTube',
  instagram: 'Instagram', facebook: 'Facebook', twitter: 'X',
}

export const PLATFORM_COLORS: Record<string, string> = {
  douyin: '#161823', weibo: '#E6162D', bilibili: '#FB7299',
  xiaohongshu: '#FE2C55', kuaishou: '#FF4906', zhihu: '#1772F6',
  wechat_channels: '#07C160', tiktok: '#161823', youtube: '#FF0000',
  instagram: '#C13584', facebook: '#1877F2', twitter: '#111111',
}
