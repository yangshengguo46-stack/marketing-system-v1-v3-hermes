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
        return { lifecycle: { stage: 'active' } } as T
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
    expect(screen.queryByText('首次经营闭环正在形成')).toBeNull()
    expect(await screen.findByLabelText('经营目标')).toBeTruthy()
    expect(await screen.findByText('经营罗盘')).toBeTruthy()
    expect(await screen.findByText('今日选题')).toBeTruthy()
    expect(screen.queryByText('今日判断')).toBeNull()
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

  it('starts first research from a compact business-goal input', async () => {
    selectMarketingAccount('prospect_default')
    $gatewayState.set('open')
    const onStartOperation = vi.fn(() => 'bootstrap-task')

    const requestGateway = async <T,>(method: string): Promise<T> => {
      if (method === 'marketing.accounts.list') {
        return { accounts: [], source: 'hermes_state', total: 0 } as T
      }

      if (method === 'marketing.account.context') {
        return { lifecycle: { stage: 'prospect' } } as T
      }

      if (method === 'marketing.content.assets.list') {
        return { assets: [] } as T
      }

      if (method === 'marketing.publish.actions.list') {
        return { actions: [] } as T
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

    fireEvent.change(await screen.findByLabelText('经营目标'), {
      target: { value: '未来三十天验证 AI 教育方向并找到第一批付费用户' }
    })
    fireEvent.click(screen.getByRole('button', { name: '开始研究' }))

    expect(onStartOperation).toHaveBeenCalledWith({
      accountId: 'prospect_default',
      businessGoal: '未来三十天验证 AI 教育方向并找到第一批付费用户',
      kind: 'account.bootstrap'
    })
    expect(screen.queryByText('首次经营闭环正在形成')).toBeNull()
  })

  it('shows preflight-approved daily topics and starts the bound production plan', async () => {
    selectMarketingAccount('acct-1')
    $gatewayState.set('open')
    const onStartOperation = vi.fn(() => 'topic-task')
    const calls = vi.fn()

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
        return { lifecycle: { business_goal: '验证 AI 产业判断', stage: 'active' } } as T
      }

      if (method === 'marketing.content.assets.list') {
        return { assets: [] } as T
      }

      if (method === 'marketing.publish.actions.list') {
        return { actions: [] } as T
      }

      if (method === 'marketing.topic_recommendations.latest') {
        return {
          batch: {
            as_of_date: '2026-07-17',
            id: 'topic-batch-1',
            recommendations: [
              {
                angle: '区分估值、需求与生产率',
                id: 'topic-candidate-1',
                influence_score: 72.5,
                plan_id: 'plan-1',
                platform_matches: [
                  { match_score: 88, platform: 'douyin', strong_match: true },
                  { match_score: 82, platform: 'wechat_official', strong_match: true }
                ],
                platform_blueprints: {
                  douyin: {
                    cta_contract: '邀请观众站队并说明理由',
                    opening_contract: '前三秒直接给反常识结论',
                    recommended_formats: ['口播视频'],
                    structure_contract: '结论—三层证据—反方观点',
                    visual_contract: '数据卡与人物口播交替'
                  },
                  wechat_official: {
                    cta_contract: '引导读者收藏并留言讨论',
                    opening_contract: '从泡沫争议的定义切入',
                    recommended_formats: ['深度图文'],
                    structure_contract: '问题定义—证据拆解—条件化结论',
                    visual_contract: '关键数据图表与小标题'
                  }
                },
                preflight_id: 'preflight-1',
                rank: 1,
                recommendation_type: 'general',
                recommended_platforms: ['douyin', 'wechat_official'],
                target_platforms: ['douyin', 'wechat_official'],
                topic: '当前的 AI 是泡沫吗？',
                why_now: '基础设施投入和收入兑现同时进入争议期'
              },
              {
                angle: '从工具采用转向个人商业模式',
                id: 'topic-candidate-2',
                influence_score: 68,
                plan_id: 'plan-2',
                platform_blueprints: {
                  douyin: {
                    opening_contract: '用一天的真实工作流程开场',
                    recommended_formats: ['口播视频']
                  },
                  xiaohongshu: {
                    opening_contract: '用清单展示工具链',
                    recommended_formats: ['卡片图文']
                  }
                },
                platform_matches: [
                  { match_score: 91, platform: 'douyin', strong_match: true },
                  { match_score: 60, platform: 'xiaohongshu', strong_match: false }
                ],
                preflight_id: 'preflight-2',
                rank: 2,
                recommendation_type: 'platform_specific',
                recommended_platforms: ['douyin'],
                target_platforms: ['douyin', 'xiaohongshu'],
                topic: 'AI 工具把打工人变成一人公司',
                why_now: '工具链已经能完成小型业务闭环'
              }
            ],
            recommended_count: 2,
            research_only_count: 2,
            target_platforms: ['douyin', 'wechat_official', 'xiaohongshu']
          }
        } as T
      }

      if (method === 'marketing.topic_production.start') {
        return {
          id: 'workflow-topic-1',
          kind: 'topic.production',
          state: 'running',
          title: '当前的 AI 是泡沫吗？',
          updated_at: 1
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

    expect(await screen.findByText('当前的 AI 是泡沫吗？')).toBeTruthy()
    expect(screen.getByText('通用选题')).toBeTruthy()
    expect(screen.getByText('平台推荐')).toBeTruthy()
    expect(screen.getByText('AI 工具把打工人变成一人公司')).toBeTruthy()
    expect(screen.getByText('抖音匹配度 91%')).toBeTruthy()
    expect(screen.getByText('小红书匹配度 60%')).toBeTruthy()
    expect(screen.getAllByText('抖音').length).toBeGreaterThan(0)
    expect(screen.getAllByText('微信公众号').length).toBeGreaterThan(0)
    expect(screen.getByText('另有 2 条候选未通过预演，已留在研究池，不会推送给你。')).toBeTruthy()

    fireEvent.click(screen.getAllByRole('button', { name: '查看各平台方案' })[0])
    expect(await screen.findByText('前三秒直接给反常识结论')).toBeTruthy()
    expect(screen.getByText('从泡沫争议的定义切入')).toBeTruthy()

    fireEvent.click(screen.getAllByRole('button', { name: /交给内容工厂/ })[0])
    await waitFor(() =>
      expect(calls).toHaveBeenCalledWith('marketing.topic_production.start', {
        account_id: 'acct-1',
        candidate_id: 'topic-candidate-1',
        user_id: 'default'
      })
    )
    expect(onStartOperation).not.toHaveBeenCalled()
  })
})
