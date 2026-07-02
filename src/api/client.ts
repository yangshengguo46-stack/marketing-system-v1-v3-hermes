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
  addAccount: (data: { account_id: string; platform: string; username: string; label?: string }) =>
    request('POST', `${BASE}/accounts`, data),
  deleteAccount: (id: string) => request('DELETE', `${BASE}/accounts/${id}`),
  updateAccountStatus: (id: string, status: Account['status']) => request('PUT', `${BASE}/accounts/${id}/status`, { status }),
  updateAccountStats: (id: string, data: Record<string, number>) => request('PUT', `${BASE}/accounts/${id}/stats`, data),

  suggestions: () => request('GET', `${BASE}/suggestions`),

  profiles: () => request('GET', `${BASE}/profiles`),
  updateProfile: (id: string, data: unknown) => request('PUT', `${BASE}/profiles/${id}`, data),
  assistantStatus: () => request('GET', `${BASE}/assistant/status`),
  mcpStatus: () => request('GET', `${BASE}/mcp/status`),

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
  deleteContentAsset: (id: string) =>
    request('DELETE', `${BASE}/content/assets/${id}`),
}

export const agent = {
  createSession: (userId?: string) =>
    request('POST', '/agent/sessions', { user_id: userId || 'default' }) as Promise<{ session_id: string; user_id: string }>,
  getSession: (sessionId: string) =>
    request('GET', `/agent/sessions/${sessionId}`) as Promise<{ session_id: string; active_task_id: string | null }>,
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
  douyin: '#FE2C55', weibo: '#E6162D', bilibili: '#FB7299',
  xiaohongshu: '#FE2C55', kuaishou: '#FF4906', zhihu: '#1772F6',
  wechat_channels: '#07C160', tiktok: '#161823', youtube: '#FF0000',
  instagram: '#C13584', facebook: '#1877F2', twitter: '#111111',
}
