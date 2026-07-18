import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { $marketingArticleDrafts, $marketingOperationTasks, selectMarketingAccount } from '@/store/marketing'

import { ArticleCreationView } from './article-creation-view'

afterEach(() => {
  cleanup()
  $marketingArticleDrafts.set({})
  $marketingOperationTasks.set([])
})

describe('article creation product flow', () => {
  it('starts from a business brief and keeps the user inside the content asset workspace', async () => {
    selectMarketingAccount('prospect_default')
    const calls = vi.fn()
    const onStartOperation = vi.fn(() => 'article-task-1')

    const requestGateway = async <T,>(method: string, params?: Record<string, unknown>): Promise<T> => {
      calls(method, params)

      if (method === 'marketing.content.assets.list') {
        return { assets: [] } as T
      }

      if (method === 'marketing.account.context') {
        return { lifecycle: { business_goal: '验证 AI 教育方向', data_gaps: ['受众付费证据'] } } as T
      }

      return {} as T
    }

    render(
      <MemoryRouter initialEntries={['/content/article']}>
        <ArticleCreationView onBack={vi.fn()} onStartOperation={onStartOperation} requestGateway={requestGateway} />
      </MemoryRouter>
    )

    fireEvent.change(await screen.findByLabelText('图文创作目标'), {
      target: { value: '解释为什么知识付费应该先验证真实付费问题' }
    })
    fireEvent.click(screen.getByRole('button', { name: '开始创作' }))

    expect(onStartOperation).toHaveBeenCalledWith({
      accountId: 'prospect_default',
      kind: 'content.article.start',
      note: '解释为什么知识付费应该先验证真实付费问题',
      title: '解释为什么知识付费应该先验证真实付费问题'
    })
    expect(screen.getByText(/不会被塞进新对话/)).toBeTruthy()
    await waitFor(() => expect(calls).toHaveBeenCalledWith('marketing.content.assets.list', expect.anything()))
    expect(calls).not.toHaveBeenCalledWith('session.create', expect.anything())
    expect(calls).not.toHaveBeenCalledWith('prompt.submit', expect.anything())
  })
})
