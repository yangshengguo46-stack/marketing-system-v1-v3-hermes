import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { $selectedMarketingAccountId } from '@/store/marketing'

import { type DraftBoxItem, DraftBoxView } from './draft-box-view'

const activeArticle: DraftBoxItem = {
  can_archive: true,
  can_resume: true,
  content_kind: 'article',
  created_at: '2026-07-10T08:00:00+00:00',
  failure_code: '',
  human_review_status: 'pending',
  id: 'asset-ai-education',
  object_type: 'content_asset',
  previous_status: '',
  source_asset_id: 'asset-ai-education',
  status: 'review_ready',
  title: 'AI 教育',
  updated_at: '2026-07-10T08:00:00+00:00',
  version: 4
}

afterEach(() => {
  cleanup()
  $selectedMarketingAccountId.set('')
})

describe('DraftBoxView', () => {
  it('opens the original article pipeline and sends an explicitly confirmed archive request', async () => {
    $selectedMarketingAccountId.set('acct-1')
    const onOpenArticle = vi.fn()
    const calls = vi.fn()

    const requestGateway = async <T,>(method: string, params?: Record<string, unknown>): Promise<T> => {
      calls(method, params)

      if (method === 'marketing.drafts.list') {
        return { items: [activeArticle] } as T
      }

      return {} as T
    }

    render(
      <DraftBoxView
        onOpenArticle={onOpenArticle}
        onOpenVideo={vi.fn()}
        onStartOperation={vi.fn()}
        requestGateway={requestGateway}
      />
    )

    expect(await screen.findByText('AI 教育')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '继续' }))
    expect(onOpenArticle).toHaveBeenCalledWith('asset-ai-education')

    fireEvent.click(screen.getByRole('button', { name: '归档 AI 教育' }))
    fireEvent.click(await screen.findByRole('button', { name: '移入归档' }))

    await waitFor(() =>
      expect(calls).toHaveBeenCalledWith('marketing.draft.archive', {
        account_id: 'acct-1',
        confirmed: true,
        object_id: 'asset-ai-education',
        object_type: 'content_asset'
      })
    )
  })

  it('loads the archived projection and restores through the native owner', async () => {
    $selectedMarketingAccountId.set('acct-1')

    const archivedArticle = {
      ...activeArticle,
      can_archive: false,
      can_resume: false,
      previous_status: 'review_ready',
      status: 'archived'
    }

    const calls = vi.fn()

    const requestGateway = async <T,>(method: string, params?: Record<string, unknown>): Promise<T> => {
      calls(method, params)

      if (method === 'marketing.drafts.list') {
        return { items: params?.archived ? [archivedArticle] : [] } as T
      }

      return {} as T
    }

    render(
      <DraftBoxView
        onOpenArticle={vi.fn()}
        onOpenVideo={vi.fn()}
        onStartOperation={vi.fn()}
        requestGateway={requestGateway}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: '已归档' }))
    expect(await screen.findByText('AI 教育')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '恢复' }))

    await waitFor(() =>
      expect(calls).toHaveBeenCalledWith('marketing.draft.restore', {
        account_id: 'acct-1',
        object_id: 'asset-ai-education',
        object_type: 'content_asset'
      })
    )
  })
})
