import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { $marketingJourneyGoalDraft, $marketingOperationTasks } from '@/store/marketing'

import { FirstRunJourney } from './first-run-journey'

afterEach(() => {
  cleanup()
  $marketingJourneyGoalDraft.set('')
  $marketingOperationTasks.set([])
})

describe('first run journey', () => {
  it('allows a prospect to start real research with one explicit action', () => {
    const onStartOperation = vi.fn(() => 'bootstrap-task-1')

    render(
      <FirstRunJourney
        accounts={[]}
        hasFirstAsset={false}
        hasFirstDecision={false}
        onOpenAccounts={vi.fn()}
        onReviewFirstAsset={vi.fn()}
        onSelectAccount={vi.fn()}
        onStartOperation={onStartOperation}
        selectedAccountId="prospect_default"
      />
    )

    fireEvent.change(screen.getByLabelText('2. 说出你真正想实现的经营目标'), {
      target: { value: '未来三十天验证 AI 教育方向并找到第一批付费用户' }
    })
    fireEvent.click(screen.getByRole('button', { name: '开始经营' }))

    expect(onStartOperation).toHaveBeenCalledWith({
      accountId: 'prospect_default',
      businessGoal: '未来三十天验证 AI 教育方向并找到第一批付费用户',
      kind: 'account.bootstrap',
      title: '首次经营研究'
    })
    expect(screen.getByText(/不会再让你确认或发送预设提示词/)).toBeTruthy()
  })

  it('can resume a persisted goal when the first visible object is still missing', () => {
    const onStartOperation = vi.fn(() => 'bootstrap-retry-task')

    render(
      <FirstRunJourney
        accounts={[]}
        businessGoal="验证 AI 教育方向"
        hasFirstAsset={false}
        hasFirstDecision={false}
        onOpenAccounts={vi.fn()}
        onReviewFirstAsset={vi.fn()}
        onSelectAccount={vi.fn()}
        onStartOperation={onStartOperation}
        selectedAccountId="prospect_default"
      />
    )

    fireEvent.click(screen.getByRole('button', { name: '继续形成首个经营对象' }))
    expect(onStartOperation).toHaveBeenCalledWith({
      accountId: 'prospect_default',
      businessGoal: '验证 AI 教育方向',
      kind: 'account.bootstrap',
      title: '首次经营研究'
    })
  })
})
