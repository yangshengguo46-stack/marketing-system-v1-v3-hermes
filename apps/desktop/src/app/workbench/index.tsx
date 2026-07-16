import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { BrandMark } from '@/components/brand-mark'
import { Button } from '@/components/ui/button'
import { ArrowUpRight, BarChart3, Brain, CheckCircle2, ChevronRight, FileText, Plus, Zap } from '@/lib/icons'
import { PRODUCT_NAME } from '@/product'
import {
  $selectedMarketingAccountId,
  type MarketingAccountSummary,
  selectMarketingAccount,
  setMarketingAccounts
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

interface WorkbenchViewProps {
  onNewChat: () => void
  onOpenAccounts: () => void
  onOpenContent: () => void
  onStartOperation: StartMarketingOperation
  requestGateway: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
}

export function WorkbenchView({
  onNewChat,
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
  const [pendingDecisions, setPendingDecisions] = useState(0)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [error, setError] = useState('')
  const selectedAccountId = useStore($selectedMarketingAccountId)
  const gatewayState = useStore($gatewayState)

  const selectedAccount = useMemo(
    () => accounts?.accounts.find(account => account.id === selectedAccountId) || accounts?.accounts[0] || null,
    [accounts, selectedAccountId]
  )

  const applyAccounts = useCallback((result: MarketingAccountsSummary) => {
    setAccounts(result)
    setMarketingAccounts(result.accounts)
  }, [])

  const refreshAccounts = useCallback(async () => {
    const result = await requestGateway<MarketingAccountsSummary>('marketing.accounts.list')
    applyAccounts(result)
  }, [applyAccounts, requestGateway])

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

  useEffect(() => {
    if (!selectedAccount?.id || selectedAccount.auth_state !== 'authenticated') {
      setContext(null)
      setAssets([])
      setSelectedReviewAsset(null)
      setPublishActionDetails([])
      setPendingDecisions(0)

      return
    }

    let active = true
    setLoadingDetail(true)

    void Promise.allSettled([
      requestGateway<AccountContext>('marketing.account.context', { account_id: selectedAccount.id }),
      requestGateway<{ assets: ContentAssetSummary[] }>('marketing.content.assets.list', {
        account_id: selectedAccount.id,
        limit: 8
      }),
      requestGateway<{ total: number }>('marketing.learning.candidates.list', {
        account_id: selectedAccount.id,
        limit: 20,
        status: 'pending'
      }),
      requestGateway<{ actions: PublishActionSummary[] }>('marketing.publish.actions.list', {
        account_id: selectedAccount.id,
        limit: 20
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
        setPendingDecisions(results[2].value.total || 0)
      }

      if (results[3].status === 'fulfilled') {
        const actions = results[3].value.actions || []
        void Promise.allSettled(
          actions.slice(0, 8).map(action =>
            requestGateway<PublishActionDetail>('marketing.publish.action.get', {
              account_id: selectedAccount.id,
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

      setLoadingDetail(false)
    })

    return () => {
      active = false
    }
  }, [requestGateway, selectedAccount?.auth_state, selectedAccount?.id])

  const accountName = selectedAccount?.label || selectedAccount?.username || '你的账号'
  const greeting = timeGreeting()

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
            <Button className="rounded-full px-5 shadow-[0_8px_24px_rgba(239,91,85,0.2)]" onClick={() => onNewChat()}>
              <Plus className="mr-1.5 size-4" />
              新对话
            </Button>
          </div>
        </header>

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
              <p className="text-xs text-(--ui-text-tertiary)">此刻最值得处理的事情</p>
              <h2 className="mt-1 text-xl font-semibold tracking-[-0.035em]">今天的经营面</h2>
            </div>
            <button
              className="flex items-center gap-1.5 text-sm font-medium text-(--ui-text-secondary) hover:text-foreground"
              onClick={() =>
                onStartOperation({
                  accountId: selectedAccount?.id || 'prospect_default',
                  kind: 'account.prioritize'
                })
              }
              type="button"
            >
              排出今天的优先级 <ArrowUpRight className="size-4" />
            </button>
          </header>

          <div className="grid xl:grid-cols-[1.08fr_0.92fr]">
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
                <EmptySignal detail="从一个想法开始，内容会在这里持续推进。" title="还没有正在制作的内容" />
              )}
            </WorkbenchLane>

            <WorkbenchLane
              action={pendingDecisions ? '一起判断' : '查看经营模型'}
              count={pendingDecisions}
              icon={<Brain className="size-4" />}
              onAction={() =>
                onStartOperation({
                  accountId: selectedAccount?.id || 'prospect_default',
                  kind: pendingDecisions ? 'learning.review' : 'account.model.review'
                })
              }
              title="今日判断"
            >
              <div className="space-y-1">
                <InsightRow
                  detail={
                    pendingDecisions
                      ? `${pendingDecisions} 条策略学习需要确认，未经同意不会改变账号长期方向。`
                      : '目前没有需要你审批的策略变化，会继续观察真实结果。'
                  }
                  icon={pendingDecisions ? <Zap className="size-4" /> : <CheckCircle2 className="size-4" />}
                  title={pendingDecisions ? '有新的策略判断等待决定' : '经营策略保持稳定'}
                  tone={pendingDecisions ? 'warm' : 'green'}
                />
                <InsightRow
                  detail={radarDetail(context, selectedAccount)}
                  icon={<BarChart3 className="size-4" />}
                  title={radarTitle(context, selectedAccount)}
                  tone="blue"
                />
              </div>
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
        accountId={selectedAccount?.id || ''}
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

function InsightRow({
  detail,
  icon,
  title,
  tone
}: {
  detail: string
  icon: React.ReactNode
  title: string
  tone: 'blue' | 'green' | 'warm'
}) {
  const toneClass = {
    blue: 'bg-blue-500/10 text-blue-500',
    green: 'bg-emerald-500/10 text-emerald-500',
    warm: 'bg-(--ui-accent)/10 text-(--ui-accent)'
  }[tone]

  return (
    <div className="flex gap-3.5 rounded-2xl px-1 py-4">
      <span className={`grid size-9 shrink-0 place-items-center rounded-xl ${toneClass}`}>{icon}</span>
      <div>
        <strong className="text-sm font-medium">{title}</strong>
        <p className="mt-1.5 text-xs leading-5 text-(--ui-text-tertiary)">{detail}</p>
      </div>
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

function radarTitle(context: AccountContext | null, account: MarketingAccountSummary | null): string {
  if (!account) {
    return '连接第一个账号，建立真实经营基线'
  }

  if (!context?.lifecycle?.positioning) {
    return '账号定位仍需要更多用户与赛道证据'
  }

  return '账号定位、内容生产与真实结果正在形成闭环'
}

function radarDetail(context: AccountContext | null, account: MarketingAccountSummary | null): string {
  if (!account) {
    return '也可以不登录账号，直接通过自然对话从零寻找方向。'
  }

  const lifecycle = context?.lifecycle
  const gaps = lifecycle?.data_gaps?.length || 0

  if (gaps) {
    return `还有 ${gaps} 个关键数据缺口，会先补充证据再给出判断。`
  }

  return `已纳入 ${lifecycle?.benchmark_count || 0} 个对标对象和 ${lifecycle?.experiment_count || 0} 轮真实实验。`
}
