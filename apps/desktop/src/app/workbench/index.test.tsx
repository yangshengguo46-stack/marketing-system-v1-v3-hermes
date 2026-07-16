import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { selectMarketingAccount } from '@/store/marketing'
import { $gatewayState } from '@/store/session'

import { WorkbenchView } from './index'

afterEach(() => cleanup())

describe('Marketing OS workbench flow', () => {
  it('opens a content asset in place instead of starting a new conversation', async () => {
    selectMarketingAccount('acct-1')
    $gatewayState.set('open')
    const calls = vi.fn()
    const onStartOperation = vi.fn()

    const requestGateway = async <T,>(method: string, params?: Record<string, unknown>): Promise<T> => {
      calls(method, params)

      if (method === 'marketing.accounts.list') {
        return {
          accounts: [{ auth_state: 'authenticated', id: 'acct-1', label: '杨炎昭', platform: 'douyin' }],
          source: 'hermes_state',
          total: 1
        } as T
      }

      if (method === 'marketing.account.context') {
        return { lifecycle: { business_goal: '持续经营 AI 教育账号', stage: 'active' } } as T
      }

      if (method === 'marketing.content.assets.list') {
        return {
          assets: [
            {
              human_review_status: 'pending',
              id: 'asset-1',
              status: 'review_ready',
              title: 'AI教育：比提示词更重要的三件事',
              type: 'article',
              version: 1
            }
          ]
        } as T
      }

      if (method === 'marketing.learning.candidates.list') {
        return { total: 0 } as T
      }

      if (method === 'marketing.publish.actions.list') {
        return { actions: [] } as T
      }

      if (method === 'marketing.content.asset.get') {
        return {
          asset: {
            content: { parent_draft: { body_markdown: '这是需要用户确认的真实内容正文。' } },
            human_review_status: 'pending',
            id: 'asset-1',
            status: 'review_ready',
            title: 'AI教育：比提示词更重要的三件事',
            version: 1
          }
        } as T
      }

      return {} as T
    }

    render(
      <WorkbenchView
        onOpenAccounts={vi.fn()}
        onOpenContent={vi.fn()}
        onStartOperation={onStartOperation}
        requestGateway={requestGateway}
      />
    )

    await waitFor(() =>
      expect(calls).toHaveBeenCalledWith('marketing.content.assets.list', {
        account_id: 'acct-1',
        limit: 8
      })
    )
    fireEvent.click(await screen.findByRole('button', { name: /AI教育：比提示词更重要的三件事/ }))

    expect(await screen.findByText('这是需要用户确认的真实内容正文。')).toBeTruthy()
    expect(onStartOperation).not.toHaveBeenCalled()
    await waitFor(() =>
      expect(calls).toHaveBeenCalledWith('marketing.content.asset.get', {
        account_id: 'acct-1',
        asset_id: 'asset-1'
      })
    )
  })
})
