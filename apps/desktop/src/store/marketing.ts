import { atom } from 'nanostores'

import { Codecs, persistentAtom } from '@/lib/persisted'

export interface MarketingAccountSummary {
  id: string
  label?: string
  platform?: string
  username?: string
}

export const $marketingAccounts = atom<MarketingAccountSummary[]>([])
export const $selectedMarketingAccountId = persistentAtom('marketing-os.desktop.selected-account', '', Codecs.text)

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
