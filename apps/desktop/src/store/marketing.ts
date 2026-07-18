import { atom } from 'nanostores'

import { Codecs, persistentAtom } from '@/lib/persisted'

export interface MarketingAccountSummary {
  id: string
  auth_state?: string
  label?: string
  last_verified_at?: number | string
  platform?: string
  platform_user_id?: string
  status?: string
  stats?: Record<string, unknown>
  username?: string
}

export interface MarketingPlatformSummary {
  content: string[]
  id: string
  label: string
  region: 'china' | 'global' | string
}

export type MarketingOperationTaskState = 'complete' | 'error' | 'starting' | 'waiting' | 'working'

export interface MarketingOperationTask {
  accountId: string
  createdAt: number
  error?: string
  id: string
  kind: string
  label: string
  operationId?: string
  workflowId?: string
  results?: MarketingOperationTaskResult[]
  state: MarketingOperationTaskState
  title: string
  updatedAt: number
}

export interface MarketingOperationTaskResult {
  object_id: string
  object_type: string
  title: string
}

export interface MarketingWorkbenchViewState {
  drillPlatform: string
  lineMode: 'index' | 'raw'
  lineScope: string
  range: 'live' | '7d' | '30d' | 'all'
}

export interface MarketingMaterialViewState {
  filter: 'all' | 'audio' | 'image' | 'video'
  query: string
  tab: 'cloud' | 'library' | 'temporary'
}

export const $marketingAccounts = atom<MarketingAccountSummary[]>([])
export const $selectedMarketingAccountId = persistentAtom('marketing-os.desktop.selected-account', '', Codecs.text)
export const $marketingArticleDrafts = persistentAtom<Record<string, string>>(
  'marketing-os.desktop.article-drafts',
  {},
  Codecs.stringRecord
)
export const $marketingWorkbenchViewState = persistentAtom<MarketingWorkbenchViewState>(
  'marketing-os.desktop.workbench-view',
  { drillPlatform: '', lineMode: 'index', lineScope: 'all', range: 'all' },
  Codecs.json(value => sanitizeWorkbenchViewState(value))
)
export const $marketingMaterialViewState = persistentAtom<MarketingMaterialViewState>(
  'marketing-os.desktop.material-view',
  { filter: 'all', query: '', tab: 'temporary' },
  Codecs.json(value => sanitizeMaterialViewState(value))
)
// Presentation-only projections of backend-owned sessions. Keeping this
// ephemeral prevents the renderer from becoming a second durable task owner.
export const $marketingOperationTasks = atom<MarketingOperationTask[]>([])

export function setMarketingAccounts(accounts: MarketingAccountSummary[]) {
  $marketingAccounts.set(accounts)
  const selected = $selectedMarketingAccountId.get()

  if (selected.startsWith('prospect_') || accounts.some(account => account.id === selected)) {
    return
  }

  $selectedMarketingAccountId.set(accounts[0]?.id ?? 'prospect_default')
}

export function selectMarketingAccount(accountId: string) {
  $selectedMarketingAccountId.set(accountId.trim() || 'prospect_default')
}

export function createMarketingOperationTask(
  task: Pick<MarketingOperationTask, 'accountId' | 'kind' | 'label' | 'title'>
): string {
  const now = Date.now()
  const id = `marketing-task-${now}-${Math.random().toString(36).slice(2, 8)}`

  $marketingOperationTasks.set(
    [
      {
        ...task,
        createdAt: now,
        id,
        state: 'starting' as const,
        updatedAt: now
      },
      ...$marketingOperationTasks.get()
    ].slice(0, 12)
  )

  return id
}

export function updateMarketingOperationTask(id: string, patch: Partial<MarketingOperationTask>) {
  $marketingOperationTasks.set(
    $marketingOperationTasks
      .get()
      .map(task => (task.id === id ? { ...task, ...patch, id: task.id, updatedAt: Date.now() } : task))
  )
}

export interface MarketingWorkflowProjection {
  error?: { code?: string; message?: string }
  id: string
  input?: {
    account_id?: string
    operation?: { account_id?: string }
  }
  kind: string
  result?: { results?: MarketingOperationTaskResult[] }
  state: string
  title: string
  updated_at: number
}

export function restoreMarketingWorkflowTasks(workflows: MarketingWorkflowProjection[]) {
  const existing = $marketingOperationTasks.get()
  const known = new Set(existing.flatMap(task => (task.workflowId ? [task.workflowId] : [])))

  const restored = workflows
    .filter(workflow => !known.has(workflow.id))
    .map(workflow => ({
      accountId: workflow.input?.account_id || workflow.input?.operation?.account_id || 'prospect_default',
      createdAt: workflow.updated_at * 1000,
      error: workflow.error?.message,
      id: `marketing-workflow-${workflow.id}`,
      kind: workflow.kind,
      label: '已从 Hermes 恢复持久任务。',
      results: workflow.result?.results || [],
      state: workflowTaskState(workflow.state),
      title: workflow.title,
      updatedAt: workflow.updated_at * 1000,
      workflowId: workflow.id
    }))

  if (restored.length) {
    $marketingOperationTasks.set([...restored, ...existing].slice(0, 12))
  }
}

export function workflowTaskState(state: string): MarketingOperationTaskState {
  if (state === 'completed') {
    return 'complete'
  }

  if (state === 'failed' || state === 'cancelled') {
    return 'error'
  }

  if (state === 'waiting_approval' || state === 'paused') {
    return 'waiting'
  }

  return 'working'
}

export function dismissMarketingOperationTask(id: string) {
  $marketingOperationTasks.set($marketingOperationTasks.get().filter(task => task.id !== id))
}

export function setMarketingArticleDraft(accountId: string, value: string) {
  const key = accountId.trim() || 'prospect_default'
  const drafts = { ...$marketingArticleDrafts.get() }

  if (value.trim()) {
    drafts[key] = value
  } else {
    delete drafts[key]
  }

  $marketingArticleDrafts.set(drafts)
}

function sanitizeWorkbenchViewState(value: unknown): MarketingWorkbenchViewState {
  const row = value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}

  const range = ['live', '7d', '30d', 'all'].includes(String(row.range))
    ? (String(row.range) as MarketingWorkbenchViewState['range'])
    : 'all'

  return {
    drillPlatform: typeof row.drillPlatform === 'string' ? row.drillPlatform : '',
    lineMode: row.lineMode === 'raw' ? 'raw' : 'index',
    lineScope: typeof row.lineScope === 'string' && row.lineScope ? row.lineScope : 'all',
    range
  }
}

function sanitizeMaterialViewState(value: unknown): MarketingMaterialViewState {
  const row = value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}

  const filter = ['all', 'audio', 'image', 'video'].includes(String(row.filter))
    ? (String(row.filter) as MarketingMaterialViewState['filter'])
    : 'all'

  const tab = ['cloud', 'library', 'temporary'].includes(String(row.tab))
    ? (String(row.tab) as MarketingMaterialViewState['tab'])
    : 'temporary'

  return {
    filter,
    query: typeof row.query === 'string' ? row.query : '',
    tab
  }
}
