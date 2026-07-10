import { beforeEach, describe, expect, it } from 'vitest'

import {
  $marketingAccounts,
  $selectedMarketingAccountId,
  selectMarketingAccount,
  setMarketingAccounts
} from './marketing'

describe('Marketing OS account selection', () => {
  beforeEach(() => {
    $marketingAccounts.set([])
    $selectedMarketingAccountId.set('')
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
})
