import { beforeEach, describe, expect, it } from 'vitest'

import {
  $marketingAccounts,
  $marketingOperationTasks,
  $selectedMarketingAccountId,
  createMarketingOperationTask,
  restoreMarketingWorkflowTasks,
  selectMarketingAccount,
  setMarketingAccounts,
  workflowTaskState
} from './marketing'

describe('Marketing OS account selection', () => {
  beforeEach(() => {
    $marketingAccounts.set([])
    $marketingOperationTasks.set([])
    $selectedMarketingAccountId.set('')
    window.localStorage.removeItem('marketing-os.desktop.operation-tasks.v1')
  })

  it('selects the first connected account when the previous selection is unavailable', () => {
    setMarketingAccounts([
      { id: 'acct-1', platform: 'douyin' },
      { id: 'acct-2', platform: 'xiaohongshu' }
    ])

    expect($selectedMarketingAccountId.get()).toBe('acct-1')
  })

  it('preserves an onboarding prospect and normalizes an empty selection', () => {
    selectMarketingAccount('prospect_creator')
    setMarketingAccounts([{ id: 'acct-1' }])
    expect($selectedMarketingAccountId.get()).toBe('prospect_creator')

    selectMarketingAccount('  ')
    expect($selectedMarketingAccountId.get()).toBe('prospect_default')
  })

  it('keeps operation progress as an ephemeral projection of backend sessions', () => {
    createMarketingOperationTask({
      accountId: 'acct-1',
      kind: 'account.analyze',
      label: '正在分析',
      title: '账号分析'
    })

    expect($marketingOperationTasks.get()).toHaveLength(1)
    expect(window.localStorage.getItem('marketing-os.desktop.operation-tasks.v1')).toBeNull()
  })

  it('restores active workflow projections from the Python owner without local persistence', () => {
    restoreMarketingWorkflowTasks([
      {
        id: 'workflow-1',
        input: { operation: { account_id: 'acct-1' } },
        kind: 'content.article.start',
        state: 'waiting_approval',
        title: '图文创作',
        updated_at: 1_752_700_000
      }
    ])

    expect($marketingOperationTasks.get()[0]).toMatchObject({
      accountId: 'acct-1',
      state: 'waiting',
      workflowId: 'workflow-1'
    })
    expect(window.localStorage.getItem('marketing-os.desktop.operation-tasks.v1')).toBeNull()
    expect(workflowTaskState('completed')).toBe('complete')
    expect(workflowTaskState('failed')).toBe('error')
  })
})
