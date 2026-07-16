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
  sessionId?: string
  state: MarketingOperationTaskState
  storedSessionId?: string
  title: string
  updatedAt: number
}

export const $marketingAccounts = atom<MarketingAccountSummary[]>([])
export const $selectedMarketingAccountId = persistentAtom('marketing-os.desktop.selected-account', '', Codecs.text)
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
    $marketingOperationTasks.get().map(task =>
      task.id === id ? { ...task, ...patch, id: task.id, updatedAt: Date.now() } : task
    )
  )
}

export function dismissMarketingOperationTask(id: string) {
  $marketingOperationTasks.set($marketingOperationTasks.get().filter(task => task.id !== id))
}
