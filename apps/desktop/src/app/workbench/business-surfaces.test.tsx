import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { selectMarketingAccount } from '@/store/marketing'

import { AccountCenterView, ContentFactoryView, ManagedView } from './business-surfaces'

describe('Marketing OS business surfaces', () => {
  const requestGateway = async <T,>(method: string): Promise<T> => {
    let result: unknown = {}

    if (method === 'marketing.accounts.list') result = { accounts: [], source: 'hermes_state', total: 0 }
    if (method === 'marketing.accounts.platforms') result = { platforms: [], total: 0 }
    if (method === 'marketing.content.assets.list') result = { assets: [] }
    if (method === 'marketing.learning.candidates.list') result = { candidates: [], total: 0 }

    return result as T
  }

  it('renders the product-owned business destinations without an internal high-end video lane', () => {
    selectMarketingAccount('prospect_default')
    const { rerender } = render(<ContentFactoryView onNewChat={vi.fn()} requestGateway={requestGateway} />)
    expect(screen.getByText('内容工厂')).toBeTruthy()
    expect(screen.getByText('图文创作')).toBeTruthy()
    expect(screen.getByText('素材视频')).toBeTruthy()
    expect(screen.queryByText('高阶视频')).toBeNull()
    expect(screen.queryByText('数字人视频')).toBeNull()

    rerender(<AccountCenterView onNewChat={vi.fn()} requestGateway={requestGateway} />)
    expect(screen.getByText('账号管理')).toBeTruthy()

    rerender(<ManagedView onNewChat={vi.fn()} requestGateway={requestGateway} />)
    expect(screen.getByText('托管')).toBeTruthy()
  })
})
