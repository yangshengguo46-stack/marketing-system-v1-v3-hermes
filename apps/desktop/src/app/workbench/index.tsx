import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { BrandMark } from '@/components/brand-mark'
import { Button } from '@/components/ui/button'
import {
  ArrowUpRight,
  BarChart3,
  Brain,
  CheckCircle2,
  ChevronRight,
  Eye,
  FileText,
  Plus,
  RefreshCw,
  Users,
  Zap
} from '@/lib/icons'
import { PRODUCT_NAME } from '@/product'
import {
  $selectedMarketingAccountId,
  type MarketingAccountSummary,
  type MarketingPlatformSummary,
  selectMarketingAccount,
  setMarketingAccounts
} from '@/store/marketing'
import { $gatewayState } from '@/store/session'

import {
  AccountConnectDialog,
  buildOwnedAccountAnalysisPrompt,
  MarketingPlatformAvatar
} from './account-connect-dialog'

interface MarketingAccountsSummary {
  accounts: MarketingAccountSummary[]
  total: number
  source: string
}

interface MarketingPlatformsSummary {
  platforms: MarketingPlatformSummary[]
  total: number
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

interface ContentAssetSummary {
  id: string
  platform?: string
  status?: string
  title?: string
  topic?: string
  type?: string
  updated_at?: string
}

interface WorkbenchViewProps {
  onNewChat: (prefill?: string) => void
  onOpenAccounts: () => void
  onOpenContent: () => void
  requestGateway: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
}

const STAGE_COPY: Record<string, { eyebrow: string; title: string; progress: number }> = {
  not_started: { eyebrow: '等待建立经营模型', title: '先把你的优势变成一个可验证的方向', progress: 12 },
  goal_defined: { eyebrow: '目标已建立', title: '正在寻找最值得进入的赛道', progress: 24 },
  market_routes_ready: { eyebrow: '赛道候选已形成', title: '选择第一条可验证的市场路径', progress: 35 },
  audience_ready: { eyebrow: '受众假设已形成', title: '用对标账号校准目标用户', progress: 48 },
  benchmark_ready: { eyebrow: '对标研究已完成', title: '把优势压缩成清晰的账号定位', progress: 62 },
  positioned: { eyebrow: '账号定位已建立', title: '搭建长期可持续的内容系统', progress: 74 },
  content_system_ready: { eyebrow: '内容系统已建立', title: '启动第一轮内容实验', progress: 86 },
  experiment_running: { eyebrow: '实验正在运行', title: '等待真实回执校准下一步', progress: 94 }
}

export function WorkbenchView({ onNewChat, onOpenAccounts, onOpenContent, requestGateway }: WorkbenchViewProps) {
  const [accounts, setAccounts] = useState<MarketingAccountsSummary | null>(null)
  const [platforms, setPlatforms] = useState<MarketingPlatformSummary[]>([])
  const [context, setContext] = useState<AccountContext | null>(null)
  const [assets, setAssets] = useState<ContentAssetSummary[]>([])
  const [pendingDecisions, setPendingDecisions] = useState(0)
  const [connectOpen, setConnectOpen] = useState(false)
  const [resumeAccount, setResumeAccount] = useState<MarketingAccountSummary | null>(null)
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

    void Promise.all([
      requestGateway<MarketingAccountsSummary>('marketing.accounts.list'),
      requestGateway<MarketingPlatformsSummary>('marketing.accounts.platforms')
    ])
      .then(([accountResult, platformResult]) => {
        if (!active) {
          return
        }

        applyAccounts(accountResult)
        setPlatforms(platformResult.platforms)
      })
      .catch(reason => {
        if (active) {
          setError(reason instanceof Error ? reason.message : String(reason))
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

      setLoadingDetail(false)
    })

    return () => {
      active = false
    }
  }, [requestGateway, selectedAccount?.auth_state, selectedAccount?.id])

  const handleAccountChanged = useCallback(
    (account: MarketingAccountSummary) => {
      setAccounts(current => {
        const previous = current?.accounts || []
        const next = [...previous.filter(item => item.id !== account.id), account]
        setMarketingAccounts(next)

        return { accounts: next, source: current?.source || 'hermes_state', total: next.length }
      })

      if (account.auth_state === 'authenticated') {
        selectMarketingAccount(account.id)
        void refreshAccounts().catch(() => undefined)
      }
    },
    [refreshAccounts]
  )

  const openAccountConnect = (account: MarketingAccountSummary | null = null) => {
    setResumeAccount(account)
    setConnectOpen(true)
  }

  const stats = selectedAccount?.stats || {}
  const lifecycle = context?.lifecycle || {}
  const stage = lifecycle.stage || 'not_started'
  const stageCopy = STAGE_COPY[stage] || STAGE_COPY.not_started
  const accountName = selectedAccount?.label || selectedAccount?.username || '你的账号'
  const greeting = timeGreeting()

  const metrics = selectedAccount?.platform === 'wechat_official'
    ? [
        { icon: Eye, label: '已同步阅读', value: metric(stats, ['read_users']), accent: '#54b99a' },
        { icon: ArrowUpRight, label: '已同步分享', value: metric(stats, ['share_users']), accent: '#ef625c' },
        { icon: Zap, label: '点赞', value: metric(stats, ['like_count']), accent: '#d6a84a' },
        { icon: FileText, label: '文章', value: metric(stats, ['articles_count']), accent: '#7894d8' }
      ]
    : selectedAccount?.platform === 'douyin'
      ? [
          { icon: Users, label: '粉丝', value: metric(stats, ['followers']), accent: '#54b99a' },
          { icon: Eye, label: '公开播放', value: metric(stats, ['total_views']), accent: '#ef625c' },
          { icon: Zap, label: '累计获赞', value: metric(stats, ['total_likes']), accent: '#d6a84a' },
          { icon: FileText, label: '公开作品', value: metric(stats, ['videos_count']), accent: '#7894d8' }
        ]
      : [
          { icon: Users, label: '粉丝', value: metric(stats, ['followers', 'fan_count', 'fans']), accent: '#54b99a' },
          { icon: Eye, label: '浏览', value: metric(stats, ['views', 'play_count', 'total_views']), accent: '#ef625c' },
          {
            icon: Zap,
            label: '互动',
            value: metric(stats, ['likes', 'total_likes', 'digg_count', 'engagement', 'interaction']),
            accent: '#d6a84a'
          },
          {
            icon: FileText,
            label: '作品',
            value: metric(stats, ['works', 'video_count', 'videos_count', 'content_count']),
            accent: '#7894d8'
          }
        ]

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

        <section className="mt-7 flex items-center gap-2 overflow-x-auto pb-1">
          {accounts?.accounts.map(account => (
            <button
              className={`flex shrink-0 items-center gap-2 rounded-full border px-3 py-2 text-left transition-all ${
                selectedAccount?.id === account.id
                  ? 'border-(--ui-accent)/35 bg-(--ui-accent)/8 shadow-[0_6px_20px_rgba(0,0,0,0.04)]'
                  : 'border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) text-(--ui-text-secondary) hover:text-foreground'
              }`}
              key={account.id}
              onClick={() =>
                account.auth_state === 'authenticated'
                  ? selectMarketingAccount(account.id)
                  : openAccountConnect(account)
              }
              type="button"
            >
              <MarketingPlatformAvatar platform={account.platform || ''} />
              <span className="max-w-32 truncate text-xs font-medium">
                {account.label || account.username || account.id}
              </span>
              <span
                className={`size-1.5 rounded-full ${account.auth_state === 'authenticated' ? 'bg-emerald-500' : 'bg-amber-400'}`}
              />
            </button>
          ))}
          <button
            className="grid size-9 shrink-0 place-items-center rounded-full border border-dashed border-(--ui-stroke-secondary) text-(--ui-text-tertiary) hover:border-(--ui-accent) hover:text-(--ui-accent)"
            onClick={() => openAccountConnect()}
            title="连接新账号"
            type="button"
          >
            <Plus className="size-4" />
          </button>
        </section>

        <section className="mt-5 overflow-hidden rounded-[28px] border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) shadow-[0_18px_55px_rgba(34,30,26,0.055)]">
          <div className="grid min-h-[280px] lg:grid-cols-[1.03fr_1.6fr]">
            <div className="relative flex flex-col justify-between overflow-hidden border-b border-(--ui-stroke-tertiary) p-8 lg:border-b-0 lg:border-r">
              <div className="absolute -left-24 -top-32 size-72 rounded-full bg-(--ui-accent)/9 blur-3xl" />
              <div className="relative">
                <div className="flex items-center gap-2 text-[0.68rem] font-semibold uppercase tracking-[0.2em] text-(--ui-text-tertiary)">
                  <span className="size-1.5 rounded-full bg-(--ui-accent)" />
                  经营进度
                </div>
                <p className="mt-8 text-sm text-(--ui-text-secondary)">{stageCopy.eyebrow}</p>
                <h2 className="mt-2 max-w-md text-[1.8rem] font-semibold leading-[1.2] tracking-[-0.045em]">
                  {stageCopy.title}
                </h2>
                {lifecycle.business_goal ? (
                  <p className="mt-3 line-clamp-2 text-sm leading-6 text-(--ui-text-secondary)">
                    {lifecycle.business_goal}
                  </p>
                ) : null}
              </div>
              <div className="relative mt-8">
                <div className="h-1.5 overflow-hidden rounded-full bg-(--ui-fill-tertiary)">
                  <div className="h-full rounded-full bg-(--ui-accent)" style={{ width: `${stageCopy.progress}%` }} />
                </div>
                <div className="mt-4 flex items-center justify-between">
                  <span className="text-xs text-(--ui-text-tertiary)">{stageCopy.progress}% 已建立</span>
                  <button
                    className="flex items-center gap-1.5 text-sm font-medium hover:text-(--ui-accent)"
                    onClick={() =>
                      onNewChat('请读取当前账号经营进度，从下一步开始继续推进；先说明你读取到的账号状态。')
                    }
                  >
                    让 Agent 继续 <ArrowUpRight className="size-4" />
                  </button>
                </div>
              </div>
            </div>

            <div className="p-7 lg:p-8">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[0.68rem] font-semibold uppercase tracking-[0.2em] text-(--ui-text-tertiary)">
                    Data pulse
                  </p>
                  <h2 className="mt-1.5 text-lg font-semibold tracking-[-0.025em]">账号实时脉搏</h2>
                </div>
                <button
                  className="grid size-8 place-items-center rounded-full text-(--ui-text-tertiary) hover:bg-(--ui-control-hover-background) hover:text-foreground"
                  onClick={() => void refreshAccounts()}
                  title="刷新数据"
                  type="button"
                >
                  <RefreshCw className={`size-4 ${loadingDetail ? 'animate-spin' : ''}`} />
                </button>
              </div>
              <div className="mt-7 grid grid-cols-2 gap-4 sm:grid-cols-4">
                {metrics.map(item => (
                  <MetricDial key={item.label} {...item} />
                ))}
              </div>
              <div className="mt-7 flex items-center justify-between border-t border-(--ui-stroke-tertiary) pt-5 text-xs text-(--ui-text-tertiary)">
                <span>{selectedAccount ? '数据来自已登录平台与发布回执' : '连接账号后开始建立真实数据曲线'}</span>
                <span className="flex items-center gap-1.5">
                  <span className="size-1.5 rounded-full bg-emerald-500" />
                  {selectedAccount ? '持续更新' : '等待连接'}
                </span>
              </div>
            </div>
          </div>
        </section>

        <section className="mt-5 grid gap-5 xl:grid-cols-[1.08fr_0.92fr]">
          <DashboardPanel
            action="进入内容工厂"
            count={assets.length}
            eyebrow="CONTENT FLOW"
            icon={<FileText className="size-4" />}
            onAction={onOpenContent}
            title="正在推进的内容"
          >
            {assets.length ? (
              <div className="divide-y divide-(--ui-stroke-tertiary)">
                {assets.slice(0, 4).map((asset, index) => (
                  <button
                    className="group flex w-full items-center gap-4 py-4 text-left"
                    key={asset.id}
                    onClick={() =>
                      onNewChat(
                        `请继续推进内容资产 ${asset.id}（${asset.title || asset.topic || '未命名内容'}）。先读取资产、校验状态与证据，再和我确认下一步。`
                      )
                    }
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
              <EmptySignal
                detail="从选题、素材到发布版本，Agent 会把每一步沉淀为可继续推进的内容资产。"
                title="还没有进入生产的内容"
              />
            )}
          </DashboardPanel>

          <DashboardPanel
            action={pendingDecisions ? '和 Agent 一起判断' : '查看经营模型'}
            count={pendingDecisions}
            eyebrow="AGENT JUDGEMENT"
            icon={<Brain className="size-4" />}
            onAction={() =>
              onNewChat(
                pendingDecisions
                  ? '请打开当前账号待确认的策略学习，逐条说明证据、风险和建议，由我决定是否接受。'
                  : '请基于当前账号经营模型，告诉我今天最值得推进的一件事；先说明依据，再开始执行。'
              )
            }
            title="今天值得你关注"
          >
            <div className="space-y-3 pt-1">
              <InsightRow
                detail={
                  pendingDecisions
                    ? `${pendingDecisions} 条策略学习需要确认，未经同意不会改变账号长期方向。`
                    : '目前没有需要你审批的策略变化，Agent 会继续收集证据。'
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
          </DashboardPanel>
        </section>

        {error ? (
          <p className="mt-5 rounded-xl border border-red-500/20 bg-red-500/5 px-4 py-3 text-xs text-red-500">
            数据连接暂未就绪：{error}
          </p>
        ) : null}
      </div>

      <AccountConnectDialog
        onAccountChanged={handleAccountChanged}
        onAnalyzeAccount={account => {
          selectMarketingAccount(account.id)
          onNewChat(buildOwnedAccountAnalysisPrompt(account))
        }}
        onOpenChange={setConnectOpen}
        open={connectOpen}
        platforms={platforms}
        requestGateway={requestGateway}
        resumeAccount={resumeAccount}
      />
    </main>
  )
}

function MetricDial({
  accent,
  icon: Icon,
  label,
  value
}: {
  accent: string
  icon: typeof Users
  label: string
  value: number | null
}) {
  const progress = value === null ? 4 : Math.max(8, Math.min(88, Math.log10(value + 1) * 18))

  return (
    <div className="flex flex-col items-center">
      <div
        className="grid aspect-square w-full max-w-[118px] place-items-center rounded-full p-[7px]"
        style={{ background: `conic-gradient(${accent} ${progress}%, var(--ui-fill-tertiary) 0)` }}
      >
        <div className="grid size-full place-items-center rounded-full bg-(--ui-sidebar-surface-background)">
          <div className="text-center">
            <Icon className="mx-auto size-4 text-(--ui-text-tertiary)" />
            <strong className="mt-1.5 block text-lg font-semibold tabular-nums tracking-[-0.03em]">
              {value === null ? '—' : compactNumber(value)}
            </strong>
            <span className="mt-0.5 block text-[0.66rem] text-(--ui-text-tertiary)">{label}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

function DashboardPanel({
  action,
  children,
  count,
  eyebrow,
  icon,
  onAction,
  title
}: {
  action: string
  children: React.ReactNode
  count: number
  eyebrow: string
  icon: React.ReactNode
  onAction: () => void
  title: string
}) {
  return (
    <article className="rounded-[24px] border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) p-7 shadow-[0_14px_42px_rgba(34,30,26,0.04)]">
      <header className="flex items-start justify-between border-b border-(--ui-stroke-tertiary) pb-5">
        <div>
          <p className="flex items-center gap-2 text-[0.66rem] font-semibold tracking-[0.18em] text-(--ui-text-tertiary)">
            {icon}
            {eyebrow}
          </p>
          <h2 className="mt-2 text-lg font-semibold tracking-[-0.025em]">{title}</h2>
        </div>
        <span className="rounded-full bg-(--ui-accent)/10 px-2.5 py-1 text-xs font-semibold text-(--ui-accent)">
          {count}
        </span>
      </header>
      <div className="min-h-[190px]">{children}</div>
      <button
        className="mt-4 flex items-center gap-1.5 text-sm text-(--ui-text-secondary) hover:text-foreground"
        onClick={onAction}
      >
        {action}
        <ArrowUpRight className="size-4" />
      </button>
    </article>
  )
}

function EmptySignal({ detail, title }: { detail: string; title: string }) {
  return (
    <div className="flex min-h-[190px] items-center justify-center text-center">
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
    <div className="flex gap-3.5 rounded-2xl border border-(--ui-stroke-tertiary) p-4">
      <span className={`grid size-9 shrink-0 place-items-center rounded-xl ${toneClass}`}>{icon}</span>
      <div>
        <strong className="text-sm font-medium">{title}</strong>
        <p className="mt-1.5 text-xs leading-5 text-(--ui-text-tertiary)">{detail}</p>
      </div>
    </div>
  )
}

function metric(stats: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const value = Number(stats[key])

    if (Number.isFinite(value) && value >= 0) {
      return value
    }
  }

  return null
}

function compactNumber(value: number): string {
  if (value >= 100_000_000) {
    return `${(value / 100_000_000).toFixed(value >= 1_000_000_000 ? 0 : 1)}亿`
  }

  if (value >= 10_000) {
    return `${(value / 10_000).toFixed(value >= 100_000 ? 0 : 1)}万`
  }

  return new Intl.NumberFormat('zh-CN').format(value)
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

  return labels[type || ''] || '内容资产'
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

  return '账号定位、内容系统与真实回执正在形成闭环'
}

function radarDetail(context: AccountContext | null, account: MarketingAccountSummary | null): string {
  if (!account) {
    return '也可以不登录账号，直接通过自然对话从零寻找方向。'
  }

  const lifecycle = context?.lifecycle
  const gaps = lifecycle?.data_gaps?.length || 0

  if (gaps) {
    return `还有 ${gaps} 个关键数据缺口；Agent 会优先补证据，不会凭空给出确定结论。`
  }

  return `已纳入 ${lifecycle?.benchmark_count || 0} 个对标对象和 ${lifecycle?.experiment_count || 0} 轮真实实验。`
}
