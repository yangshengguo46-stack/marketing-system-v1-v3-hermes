import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { MarketingAccountSummary } from '@/store/marketing'

import { GrowthDashboard } from './growth-dashboard'

const accounts: MarketingAccountSummary[] = [
  {
    auth_state: 'authenticated',
    id: 'douyin-main',
    label: '抖音主号',
    platform: 'douyin',
    stats: {
      followers_gained: 120,
      observed_at: '2026-07-16T06:00:00Z',
      public_video_likes: 900,
      total_views: 10_000
    }
  },
  {
    auth_state: 'authenticated',
    id: 'wechat-main',
    label: '公众号主号',
    platform: 'wechat_official',
    stats: {
      followers_gained: 30,
      like_count: 80,
      observed_at: '2026-07-16T06:10:00Z',
      read_users: 5_000,
      share_users: 20
    }
  }
]

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

describe('GrowthDashboard', () => {
  it('uses verified account fields for the three compasses and drills from platform to account', () => {
    vi.useFakeTimers()
    const onSelectAccount = vi.fn()

    render(
      <GrowthDashboard
        accounts={accounts}
        actionDetails={[]}
        onRefresh={vi.fn()}
        onSelectAccount={onSelectAccount}
        refreshing={false}
        selectedAccountId="douyin-main"
      />
    )

    expect(screen.getByRole('img', { name: '总浏览量 1.5万' })).toBeTruthy()
    expect(screen.getByRole('img', { name: '总新增粉丝量 +150' })).toBeTruthy()
    expect(screen.getByRole('img', { name: '总互动率 6.7%' })).toBeTruthy()
    expect(screen.getByText('还差一次可比快照')).toBeTruthy()

    fireEvent.click(screen.getAllByRole('button', { name: '抖音' })[0])
    act(() => vi.advanceTimersByTime(420))

    expect(screen.getAllByRole('button', { name: '抖音主号' }).length).toBeGreaterThan(0)
    fireEvent.click(screen.getAllByRole('button', { name: '抖音主号' })[0])
    expect(onSelectAccount).toHaveBeenCalledWith('douyin-main')

    fireEvent.click(screen.getByText('经营罗盘'))
    act(() => vi.advanceTimersByTime(420))

    expect(screen.queryByRole('button', { name: '抖音主号' })).toBeNull()
    expect(screen.getByText('全部平台 · 悬停查看贡献，点击色块进入账号层')).toBeTruthy()
  })

  it('shows calibration dimensions only when a publish prediction is available', () => {
    render(
      <GrowthDashboard
        accounts={accounts}
        actionDetails={[
          {
            action: {
              request: {
                prediction: {
                  prediction_dimensions: {
                    dimensions: {
                      attention: {
                        expected_metric: 'views',
                        range: { high: 12_000, low: 8_000, mid: 10_000 }
                      },
                      trust: {
                        expected_metric: 'engagement_rate',
                        range: { high: 0.12, low: 0.08, mid: 0.1 }
                      }
                    }
                  }
                }
              }
            },
            receipt: {
              summary: {
                metrics: { engagement_rate: 0.11, sample_size: 9_000, views: 11_500 }
              }
            },
            summary: { platform: 'douyin', title: '测试作品' }
          }
        ]}
        onRefresh={vi.fn()}
        onSelectAccount={vi.fn()}
        refreshing={false}
        selectedAccountId="douyin-main"
      />
    )

    expect(screen.getByText('预测中位值 = 100')).toBeTruthy()
    expect(screen.queryByText('还没有可校准的作品')).toBeNull()
    expect(screen.getByRole('img', { name: '预测与实际校准' })).toBeTruthy()
    expect(screen.getByText('浏览')).toBeTruthy()
    expect(screen.getByText('互动')).toBeTruthy()
  })
})
