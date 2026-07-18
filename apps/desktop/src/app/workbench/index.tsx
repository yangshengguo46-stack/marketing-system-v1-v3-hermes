import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { BrandMark } from '@/components/brand-mark'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ArrowUpRight, ChevronRight, FileText, Globe, Layers3, RefreshCw } from '@/lib/icons'
import { PRODUCT_NAME } from '@/product'
import {
  $marketingOperationTasks,
  $selectedMarketingAccountId,
  createMarketingOperationTask,
  type MarketingAccountSummary,
  type MarketingWorkflowProjection,
  selectMarketingAccount,
  setMarketingAccounts,
  updateMarketingOperationTask,
  workflowTaskState
} from '@/store/marketing'
import { $gatewayState } from '@/store/session'

import { type ContentAssetSummary, ContentReviewSheet } from './content-review-sheet'
import { GrowthDashboard } from './growth-dashboard'
import type { StartMarketingOperation } from './operations'
import { userFacingError } from './user-facing-copy'

interface MarketingAccountsSummary {
  accounts: MarketingAccountSummary[]
  total: number
  source: string
}

interface AccountContext {
  account_dna?: {
    audience?: string
    content_pillars?: string[]
    persona?: string
    tone?: string
  }
  lifecycle?: {
    benchmark_count?: number
    business_goal?: string
    data_gaps?: string[]
    experiment_count?: number
    next_action?: string
    positioning?: Record<string, unknown> | null
    stage?: string
  }
}

interface PublishActionSummary {
  id: string
  platform: string
  status: string
  title: string
  updated_at: string
  receipt?: {
    summary?: {
      platform_post_id?: string | null
      published_url?: string | null
    }
  } | null
}

interface PublishActionDetail {
  action?: {
    request?: {
      prediction?: Record<string, unknown> | null
    }
    [key: string]: unknown
  }
  metric_checkpoints?: Array<Record<string, unknown>>
  receipt?: {
    summary?: Record<string, unknown>
  } | null
  summary?: PublishActionSummary
}

interface TopicPlatformBlueprint {
  cta_contract?: string
  guidance_status?: string
  opening_contract?: string
  recommended_formats?: string[]
  structure_contract?: string
  visual_contract?: string
}

interface TopicRecommendation {
  angle?: string
  audience?: string
  decision_status?: string
  id: string
  influence_score?: number
  plan_id: string
  platform_matches: Array<{
    basis?: string
    guidance_status?: string
    match_score: number
    platform: string
    rationale?: string
    strong_match?: boolean
  }>
  platform_blueprints: Record<string, TopicPlatformBlueprint>
  preflight?: {
    primary_reason?: string
    warnings?: string[]
  }
  preflight_id: string
  rank: number
  recommendation_type: 'general' | 'platform_specific'
  recommended_platforms: string[]
  target_platforms: string[]
  topic: string
  why_now?: string
}

interface TopicRecommendationBatch {
  as_of_date: string
  completed_at?: string
  id: string
  recommendations: TopicRecommendation[]
  recommended_count: number
  research_only_count: number
  target_platforms: string[]
}

interface WorkbenchViewProps {
  onOpenAccounts: () => void
  onOpenContent: () => void
  onStartOperation: StartMarketingOperation
  requestGateway: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
}

export function WorkbenchView({
  onOpenAccounts,
  onOpenContent,
  onStartOperation,
  requestGateway
}: WorkbenchViewProps) {
  const [accounts, setAccounts] = useState<MarketingAccountsSummary | null>(null)
  const [context, setContext] = useState<AccountContext | null>(null)
  const [assets, setAssets] = useState<ContentAssetSummary[]>([])
  const [selectedReviewAsset, setSelectedReviewAsset] = useState<ContentAssetSummary | null>(null)
  const [publishActionDetails, setPublishActionDetails] = useState<PublishActionDetail[]>([])
  const [topicBatch, setTopicBatch] = useState<TopicRecommendationBatch | null>(null)
  const [expandedTopicId, setExpandedTopicId] = useState('')
  const [refreshingTopics, setRefreshingTopics] = useState(false)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [error, setError] = useState('')
  const [businessGoalDraft, setBusinessGoalDraft] = useState('')
  const [businessGoalError, setBusinessGoalError] = useState('')
  const selectedAccountId = useStore($selectedMarketingAccountId)
  const operationTasks = useStore($marketingOperationTasks)
  const gatewayState = useStore($gatewayState)

  const selectedAccount = useMemo(() => {
    if (selectedAccountId.startsWith('prospect_')) {
      return null
    }

    return accounts?.accounts.find(account => account.id === selectedAccountId) || accounts?.accounts[0] || null
  }, [accounts, selectedAccountId])

  const scopeAccountId =
    selectedAccount?.id || (selectedAccountId.startsWith('prospect_') ? selectedAccountId : 'prospect_default')

  const applyAccounts = useCallback((result: MarketingAccountsSummary) => {
    setAccounts(result)
    setMarketingAccounts(result.accounts)
  }, [])

  const refreshAccounts = useCallback(async () => {
    const result = await requestGateway<MarketingAccountsSummary>('marketing.accounts.list')
    applyAccounts(result)
  }, [applyAccounts, requestGateway])

  const refreshTopics = useCallback(async () => {
    if (gatewayState !== 'open') {
      return
    }

    setRefreshingTopics(true)

    try {
      const result = await requestGateway<{ batch: TopicRecommendationBatch | null }>(
        'marketing.topic_recommendations.latest',
        { account_id: scopeAccountId }
      )

      setTopicBatch(result.batch || null)
    } catch (reason) {
      setError(userFacingError(reason, '今日选题暂时无法读取，请稍后重试。'))
    } finally {
      setRefreshingTopics(false)
    }
  }, [gatewayState, requestGateway, scopeAccountId])

  useEffect(() => {
    if (gatewayState !== 'open') {
      setError('')

      return
    }

    let active = true

    void requestGateway<MarketingAccountsSummary>('marketing.accounts.list')
      .then(accountResult => {
        if (!active) {
          return
        }

        applyAccounts(accountResult)
      })
      .catch(reason => {
        if (active) {
          setError(userFacingError(reason, '账号数据暂时无法读取，请稍后重试。'))
        }
      })

    return () => {
      active = false
    }
  }, [applyAccounts, gatewayState, requestGateway])

  const refreshDetail = useCallback(() => {
    let active = true
    setLoadingDetail(true)

    void Promise.allSettled([
      requestGateway<AccountContext>('marketing.account.context', { account_id: scopeAccountId }),
      requestGateway<{ assets: ContentAssetSummary[] }>('marketing.content.assets.list', {
        account_id: scopeAccountId,
        limit: 8
      }),
      requestGateway<{ actions: PublishActionSummary[] }>('marketing.publish.actions.list', {
        account_id: scopeAccountId,
        limit: 20
      }),
      requestGateway<{ batch: TopicRecommendationBatch | null }>('marketing.topic_recommendations.latest', {
        account_id: scopeAccountId
      })
    ]).then(results => {
      if (!active) {
        return
      }

      if (results[0].status === 'fulfilled') {
        setContext(results[0].value)
      }

      if (results[1].status === 'fulfilled') {
        setAssets(results[1].value.assets || [])
      }

      if (results[2].status === 'fulfilled') {
        const actions = results[2].value.actions || []
        void Promise.allSettled(
          actions.slice(0, 8).map(action =>
            requestGateway<PublishActionDetail>('marketing.publish.action.get', {
              account_id: scopeAccountId,
              action_id: action.id
            })
          )
        ).then(detailResults => {
          if (!active) {
            return
          }

          setPublishActionDetails(
            detailResults.flatMap(result => (result.status === 'fulfilled' ? [result.value] : []))
          )
        })
      } else {
        setPublishActionDetails([])
      }

      if (results[3].status === 'fulfilled') {
        setTopicBatch(results[3].value.batch || null)
      }

      setLoadingDetail(false)
    })

    return () => {
      active = false
    }
  }, [requestGateway, scopeAccountId])

  useEffect(() => refreshDetail(), [refreshDetail])

  useEffect(() => {
    if (gatewayState !== 'open') {
      return
    }

    const timer = window.setInterval(() => void refreshTopics(), 60_000)

    return () => window.clearInterval(timer)
  }, [gatewayState, refreshTopics])

  const operationRefreshSignature = operationTasks
    .filter(task => task.accountId === scopeAccountId && (task.operationId || task.state === 'complete'))
    .map(task => `${task.id}:${task.state}:${task.operationId || ''}`)
    .join('|')

  useEffect(() => {
    if (operationRefreshSignature) {
      return refreshDetail()
    }
  }, [operationRefreshSignature, refreshDetail])

  const accountName = selectedAccount?.label || selectedAccount?.username || '你的经营项目'
  const greeting = timeGreeting()

  const generalTopics = (topicBatch?.recommendations || []).filter(
    topic => topic.recommendation_type !== 'platform_specific'
  )

  const platformTopics = (topicBatch?.recommendations || []).filter(
    topic => topic.recommendation_type === 'platform_specific'
  )

  const startFirstResearch = () => {
    const businessGoal = businessGoalDraft.trim()

    if (businessGoal.length < 4) {
      setBusinessGoalError('用一句话说清楚你希望这个账号取得什么结果。')

      return
    }

    setBusinessGoalError('')
    onStartOperation({
      accountId: scopeAccountId,
      businessGoal,
      kind: 'account.bootstrap'
    })
  }

  const startTopicProduction = (topic: TopicRecommendation) => {
    const taskId = createMarketingOperationTask({
      accountId: scopeAccountId,
      kind: 'topic.production',
      label: '正在固化 TopicBrief，并行启动图文 Director 与视频 Director。',
      title: topic.topic
    })

    void requestGateway<MarketingWorkflowProjection>('marketing.topic_production.start', {
      account_id: scopeAccountId,
      candidate_id: topic.id,
      user_id: 'default'
    })
      .then(workflow => {
        updateMarketingOperationTask(taskId, {
          label: '图文与视频正在按平台独立制作；可随时恢复、停止或重试。',
          results: workflow.result?.results || [],
          state: workflowTaskState(workflow.state),
          workflowId: workflow.id
        })
      })
      .catch(reason => {
        updateMarketingOperationTask(taskId, {
          error: userFacingError(reason, '选题制作管线启动失败，请重试。'),
          state: 'error'
        })
      })

    return taskId
  }

  return (
    <main className="marketing-workbench h-full overflow-y-auto bg-(--ui-background) text-foreground">
      <div className="mx-auto w-full max-w-[1380px] px-8 pb-16 pt-[calc(var(--titlebar-height)+2rem)] lg:px-12">
        <header className="flex items-center justify-between gap-8 border-b border-(--ui-stroke-tertiary) pb-7">
          <div className="flex min-w-0 items-center gap-3.5">
            <BrandMark className="size-10 text-[2rem] shadow-[0_9px_24px_rgba(239,91,85,0.2)]" />
            <div>
              <p className="text-[0.67rem] font-semibold uppercase tracking-[0.24em] text-(--ui-text-tertiary)">
                {PRODUCT_NAME}
              </p>
              <h1 className="mt-0.5 text-[1.45rem] font-semibold tracking-[-0.035em]">
                {greeting}，{accountName}
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-2.5">
            <Button className="rounded-full px-4" onClick={onOpenAccounts} variant="outline">
              管理账号
            </Button>
            <Button className="rounded-full px-5 shadow-[0_8px_24px_rgba(239,91,85,0.2)]" onClick={onOpenContent}>
              <FileText className="mr-1.5 size-4" />
              创建内容
            </Button>
          </div>
        </header>

        {!loadingDetail && context && !context.lifecycle?.business_goal ? (
          <section
            aria-label="设置首次经营目标"
            className="mt-5 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) px-5 py-4"
          >
            <div className="min-w-52">
              <strong className="text-sm font-medium">先给 Agent 一个经营目标</strong>
              <p className="mt-1 text-xs text-(--ui-text-tertiary)">
                一行就够；目标会由原生账号 owner 保存并启动首次研究。
              </p>
            </div>
            <div className="min-w-72 flex-1 lg:max-w-2xl">
              <div className="flex gap-2">
                <Input
                  aria-label="经营目标"
                  autoCapitalize="sentences"
                  maxLength={500}
                  onChange={event => setBusinessGoalDraft(event.target.value)}
                  onKeyDown={event => {
                    if (event.key === 'Enter') {
                      startFirstResearch()
                    }
                  }}
                  placeholder="例如：未来 30 天验证 AI 教育方向并找到第一批付费用户"
                  value={businessGoalDraft}
                />
                <Button className="shrink-0" onClick={startFirstResearch}>
                  开始研究
                </Button>
              </div>
              {businessGoalError ? <p className="mt-1.5 text-xs text-red-500">{businessGoalError}</p> : null}
            </div>
          </section>
        ) : null}

        <GrowthDashboard
          accounts={accounts?.accounts || []}
          actionDetails={publishActionDetails}
          onRefresh={() => void refreshAccounts()}
          onSelectAccount={selectMarketingAccount}
          refreshing={loadingDetail}
          selectedAccountId={selectedAccount?.id || ''}
        />

        <section className="mt-5 overflow-hidden rounded-[26px] border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) shadow-[0_16px_48px_rgba(42,34,27,0.045)]">
          <header className="flex flex-wrap items-end justify-between gap-3 border-b border-(--ui-stroke-tertiary) px-7 py-5">
            <div>
              <p className="text-xs text-(--ui-text-tertiary)">每天 09:00 · 全平台数据、经营模型与预演引擎</p>
              <h2 className="mt-1 text-xl font-semibold tracking-[-0.035em]">今日选题</h2>
            </div>
            <button
              className="flex items-center gap-1.5 text-sm font-medium text-(--ui-text-secondary) hover:text-foreground disabled:opacity-50"
              disabled={refreshingTopics}
              onClick={() => void refreshTopics()}
              type="button"
            >
              <RefreshCw className={`size-4 ${refreshingTopics ? 'animate-spin' : ''}`} />
              刷新选题
            </button>
          </header>

          <div className="grid xl:grid-cols-[1.35fr_0.65fr]">
            <WorkbenchLane
              action="刷新"
              count={topicBatch?.recommendations.length || 0}
              icon={<Globe className="size-4" />}
              onAction={() => void refreshTopics()}
              title="预演通过"
            >
              {topicBatch?.recommendations.length ? (
                <div className="space-y-6">
                  {[
                    {
                      detail: '至少两个平台达到强匹配，同一个内容内核值得做平台化改编。',
                      key: 'general',
                      title: '通用选题',
                      topics: generalTopics
                    },
                    {
                      detail: '只在少数平台明显成立，优先按推荐平台的内容机制制作。',
                      key: 'platform',
                      title: '平台推荐',
                      topics: platformTopics
                    }
                  ].map(group =>
                    group.topics.length ? (
                      <section aria-label={group.title} key={group.key}>
                        <header className="mb-2.5 flex flex-wrap items-baseline gap-x-2 gap-y-1 px-1">
                          <h4 className="text-xs font-semibold">{group.title}</h4>
                          <span className="text-[0.68rem] tabular-nums text-(--ui-text-tertiary)">
                            {group.topics.length}
                          </span>
                          <p className="text-[0.68rem] text-(--ui-text-tertiary)">{group.detail}</p>
                        </header>
                        <div className="space-y-3">
                          {group.topics.map(topic => (
                            <TopicRecommendationCard
                              expanded={expandedTopicId === topic.id}
                              key={topic.id}
                              onStart={() => startTopicProduction(topic)}
                              onToggle={() => setExpandedTopicId(current => (current === topic.id ? '' : topic.id))}
                              topic={topic}
                            />
                          ))}
                        </div>
                      </section>
                    ) : null
                  )}
                  {topicBatch.research_only_count ? (
                    <p className="px-1 text-[0.7rem] leading-5 text-(--ui-text-tertiary)">
                      另有 {topicBatch.research_only_count} 条候选未通过预演，已留在研究池，不会推送给你。
                    </p>
                  ) : null}
                </div>
              ) : (
                <EmptySignal
                  detail={
                    topicBatch
                      ? `${topicBatch.as_of_date} 的候选没有通过预演，系统会继续收集证据，不会为了凑数推荐。`
                      : '每日 Agent 会先汇总全平台信号，再结合你的经营模型逐条预演；通过的选题会自动出现在这里。'
                  }
                  title={topicBatch ? '今天没有合格选题' : '下一批选题将在 09:00 到达'}
                />
              )}
            </WorkbenchLane>

            <WorkbenchLane
              action="进入内容工厂"
              count={assets.length}
              icon={<FileText className="size-4" />}
              onAction={onOpenContent}
              title="正在推进"
            >
              {assets.length ? (
                <div className="divide-y divide-(--ui-stroke-tertiary)">
                  {assets.slice(0, 4).map((asset, index) => (
                    <button
                      className="group flex w-full items-center gap-4 py-4 text-left"
                      key={asset.id}
                      onClick={() => setSelectedReviewAsset(asset)}
                      type="button"
                    >
                      <span className="w-5 text-[0.66rem] font-semibold tabular-nums text-(--ui-text-quaternary)">
                        {String(index + 1).padStart(2, '0')}
                      </span>
                      <span className="min-w-0 flex-1">
                        <strong className="block truncate text-sm font-medium">
                          {asset.title || asset.topic || '未命名内容'}
                        </strong>
                        <small className="mt-1 block text-xs text-(--ui-text-tertiary)">
                          {contentTypeLabel(asset.type)} · {statusLabel(asset.status)}
                        </small>
                      </span>
                      <ChevronRight className="size-4 text-(--ui-text-quaternary) transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" />
                    </button>
                  ))}
                </div>
              ) : (
                <EmptySignal detail="选题进入内容工厂后，会在这里持续推进。" title="还没有正在制作的内容" />
              )}
            </WorkbenchLane>
          </div>
        </section>

        {error ? (
          <p className="mt-5 rounded-xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-xs text-red-500">
            数据连接暂未就绪：{error}
          </p>
        ) : null}
      </div>
      <ContentReviewSheet
        accountId={scopeAccountId}
        asset={selectedReviewAsset}
        onOpenChange={open => {
          if (!open) {
            setSelectedReviewAsset(null)
          }
        }}
        onReviewed={reviewed => {
          setAssets(current => current.map(asset => (asset.id === reviewed.id ? { ...asset, ...reviewed } : asset)))
          setSelectedReviewAsset(reviewed)
        }}
        onStartOperation={onStartOperation}
        requestGateway={requestGateway}
      />
    </main>
  )
}

function WorkbenchLane({
  action,
  children,
  count,
  icon,
  onAction,
  title
}: {
  action: string
  children: React.ReactNode
  count: number
  icon: React.ReactNode
  onAction: () => void
  title: string
}) {
  return (
    <article className="min-w-0 p-7 xl:border-r xl:border-(--ui-stroke-tertiary) xl:last:border-r-0">
      <header className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <span className="grid size-8 place-items-center rounded-xl bg-(--ui-fill-secondary) text-(--ui-text-secondary)">
            {icon}
          </span>
          <h3 className="text-base font-semibold tracking-[-0.02em]">{title}</h3>
          <span className="text-xs tabular-nums text-(--ui-text-tertiary)">{count}</span>
        </div>
        <button
          className="flex items-center gap-1 text-xs font-medium text-(--ui-text-secondary) hover:text-foreground"
          onClick={onAction}
          type="button"
        >
          {action}
          <ArrowUpRight className="size-3.5" />
        </button>
      </header>
      <div className="mt-4 min-h-[180px]">{children}</div>
    </article>
  )
}

function EmptySignal({ detail, title }: { detail: string; title: string }) {
  return (
    <div className="flex min-h-[180px] items-center justify-center text-center">
      <div className="max-w-sm">
        <div className="mx-auto grid size-10 place-items-center rounded-full bg-(--ui-fill-secondary) text-(--ui-text-secondary)">
          <FileText className="size-4" />
        </div>
        <strong className="mt-4 block text-sm font-medium">{title}</strong>
        <p className="mt-2 text-xs leading-5 text-(--ui-text-tertiary)">{detail}</p>
      </div>
    </div>
  )
}

function TopicRecommendationCard({
  expanded,
  onStart,
  onToggle,
  topic
}: {
  expanded: boolean
  onStart: () => void
  onToggle: () => void
  topic: TopicRecommendation
}) {
  return (
    <article className="rounded-2xl border border-(--ui-stroke-tertiary) bg-(--ui-background) p-4">
      <div className="flex gap-3">
        <span className="grid size-8 shrink-0 place-items-center rounded-xl bg-(--ui-accent)/10 text-xs font-semibold text-(--ui-accent)">
          {String(topic.rank).padStart(2, '0')}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <h4 className="text-sm font-semibold leading-6">{topic.topic}</h4>
              {topic.angle ? <p className="mt-1 text-xs leading-5 text-(--ui-text-secondary)">{topic.angle}</p> : null}
              {topic.recommendation_type === 'platform_specific' && topic.platform_matches.length ? (
                <p className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-[0.68rem] leading-5 text-(--ui-text-tertiary)">
                  {topic.platform_matches.map(match => (
                    <span className={match.strong_match ? 'font-medium text-(--ui-accent)' : ''} key={match.platform}>
                      {platformLabel(match.platform)}匹配度 {Math.round(match.match_score)}%
                    </span>
                  ))}
                </p>
              ) : null}
            </div>
            <span className="shrink-0 rounded-full bg-emerald-500/10 px-2.5 py-1 text-[0.68rem] font-medium text-emerald-600">
              预演 {Math.round(topic.influence_score || 0)}
            </span>
          </div>
          {topic.why_now ? (
            <p className="mt-2 text-[0.7rem] leading-5 text-(--ui-text-tertiary)">为什么是现在：{topic.why_now}</p>
          ) : null}
          <div className="mt-3 flex flex-wrap gap-1.5">
            {topic.target_platforms.map(platform => (
              <span
                className="rounded-full border border-(--ui-stroke-tertiary) px-2 py-1 text-[0.66rem] text-(--ui-text-secondary)"
                key={platform}
              >
                {platformLabel(platform)}
              </span>
            ))}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button className="h-8 rounded-full px-3 text-xs" onClick={onToggle} variant="outline">
              <Layers3 className="mr-1.5 size-3.5" />
              {expanded ? '收起方案' : '查看各平台方案'}
            </Button>
            <Button className="h-8 rounded-full px-3 text-xs" onClick={onStart}>
              交给内容工厂 <ArrowUpRight className="ml-1.5 size-3.5" />
            </Button>
          </div>
        </div>
      </div>

      {expanded ? (
        <div className="mt-4 grid gap-2 border-t border-(--ui-stroke-tertiary) pt-4 md:grid-cols-2">
          {topic.target_platforms.map(platform => {
            const blueprint = topic.platform_blueprints[platform]

            return (
              <div className="rounded-xl bg-(--ui-fill-secondary) p-3" key={platform}>
                <div className="flex items-center justify-between gap-2">
                  <strong className="text-xs font-semibold">{platformLabel(platform)}</strong>
                  <span className="text-[0.62rem] text-(--ui-text-tertiary)">
                    {(blueprint?.recommended_formats || []).join(' / ') || '待研究载体'}
                  </span>
                </div>
                <dl className="mt-2 space-y-1.5 text-[0.68rem] leading-5">
                  <BlueprintLine label="开头" value={blueprint?.opening_contract} />
                  <BlueprintLine label="结构" value={blueprint?.structure_contract} />
                  <BlueprintLine label="视觉" value={blueprint?.visual_contract} />
                  <BlueprintLine label="CTA" value={blueprint?.cta_contract} />
                </dl>
              </div>
            )
          })}
        </div>
      ) : null}
    </article>
  )
}

function BlueprintLine({ label, value }: { label: string; value?: string }) {
  return (
    <div className="grid grid-cols-[2rem_1fr] gap-2">
      <dt className="text-(--ui-text-tertiary)">{label}</dt>
      <dd className="text-(--ui-text-secondary)">{value || '平台规则待研究，生产前不会盲猜。'}</dd>
    </div>
  )
}

function timeGreeting(): string {
  const hour = new Date().getHours()

  if (hour < 6) {
    return '夜深了'
  }

  if (hour < 11) {
    return '早上好'
  }

  if (hour < 14) {
    return '中午好'
  }

  if (hour < 18) {
    return '下午好'
  }

  return '晚上好'
}

function contentTypeLabel(type?: string): string {
  const labels: Record<string, string> = {
    article_soft: '图文软文',
    faceless_video: '素材视频',
    video: '视频'
  }

  return labels[type || ''] || '其他内容'
}

function statusLabel(status?: string): string {
  const labels: Record<string, string> = {
    draft: '正在打磨',
    review_ready: '等待确认',
    approved: '已确认',
    published: '已发布'
  }

  return labels[status || ''] || '正在推进'
}

function platformLabel(platform: string): string {
  const labels: Record<string, string> = {
    bilibili: 'B站',
    douyin: '抖音',
    instagram: 'Instagram',
    linkedin: 'LinkedIn',
    mastodon: 'Mastodon',
    wechat_official: '微信公众号',
    weibo: '微博',
    xiaohongshu: '小红书',
    youtube: 'YouTube'
  }

  return labels[platform] || platform
}
