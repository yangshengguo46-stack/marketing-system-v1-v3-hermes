import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  ArrowUpRight,
  ChevronLeft,
  Clock,
  FileText,
  Lock,
  MonitorPlay,
  Plus,
  RefreshCw,
  Trash2,
  Zap
} from '@/lib/icons'
import {
  $marketingAccounts,
  $selectedMarketingAccountId,
  type MarketingAccountSummary,
  type MarketingPlatformSummary,
  selectMarketingAccount,
  setMarketingAccounts
} from '@/store/marketing'

import { AccountConnectDialog, MarketingPlatformAvatar } from './account-connect-dialog'
import type { StartMarketingOperation } from './operations'
import { VideoProductionWorkbench } from './video-production-workbench'

interface GatewaySurfaceProps {
  requestGateway: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
}

interface OperationSurfaceProps extends GatewaySurfaceProps {
  onStartOperation: StartMarketingOperation
}

interface AccountCenterViewProps extends OperationSurfaceProps {
  onOpenWorkbench?: () => void
}

interface VideoCreationViewProps extends GatewaySurfaceProps {
  initialProductionId?: string
  onBack?: () => void
  onStartOperation: StartMarketingOperation
}

interface AccountsEnvelope {
  accounts: MarketingAccountSummary[]
  source: string
  total: number
}

interface PlatformsEnvelope {
  platforms: MarketingPlatformSummary[]
  total: number
}

export function ContentFactoryView({
  onOpenArticle,
  onOpenVideo
}: {
  onOpenArticle: () => void
  onOpenVideo: () => void
}) {
  return (
    <ProductPage
      action={null}
      description="选择生产类型后，后续研究、草稿、审核和结果都留在同一个内容对象里。"
      title="内容工厂"
    >
      <section className="grid min-h-[calc(100vh-var(--titlebar-height)-12rem)] place-items-center px-4 py-12">
        <div className="flex flex-col items-center gap-8 sm:flex-row sm:gap-20">
          <CreationEntry icon={<FileText className="size-4" />} onClick={onOpenArticle} title="图文创作" />
          <CreationEntry icon={<MonitorPlay className="size-4" />} onClick={onOpenVideo} title="视频创作" />
        </div>
      </section>
    </ProductPage>
  )
}

export function VideoCreationView({
  initialProductionId,
  onBack,
  onStartOperation,
  requestGateway
}: VideoCreationViewProps) {
  const accountId = useStore($selectedMarketingAccountId)

  return (
    <main className="flex h-full min-h-0 flex-col overflow-hidden bg-(--ui-chat-surface-background) text-foreground">
      <VideoProductionWorkbench
        accountId={accountId || 'prospect_default'}
        initialProductionId={initialProductionId}
        key={accountId || 'prospect_default'}
        onBack={onBack}
        onStartOperation={onStartOperation}
        requestGateway={requestGateway}
      />
    </main>
  )
}

export function AccountCenterView({ onOpenWorkbench, onStartOperation, requestGateway }: AccountCenterViewProps) {
  const selectedId = useStore($selectedMarketingAccountId)
  const [accounts, setAccounts] = useState<MarketingAccountSummary[]>([])
  const [platforms, setPlatforms] = useState<MarketingPlatformSummary[]>([])
  const [connectOpen, setConnectOpen] = useState(false)
  const [resumeAccount, setResumeAccount] = useState<MarketingAccountSummary | null>(null)
  const [syncingAccountId, setSyncingAccountId] = useState<string | null>(null)

  const [accountAction, setAccountAction] = useState<{
    account: MarketingAccountSummary
    kind: 'delete' | 'disconnect'
  } | null>(null)

  const refresh = useCallback(async () => {
    const [accountResult, platformResult] = await Promise.all([
      requestGateway<AccountsEnvelope>('marketing.accounts.list'),
      requestGateway<PlatformsEnvelope>('marketing.accounts.platforms')
    ])

    setAccounts(accountResult.accounts)
    setMarketingAccounts(accountResult.accounts)
    setPlatforms(platformResult.platforms)
  }, [requestGateway])

  useEffect(() => {
    void refresh().catch(() => undefined)
  }, [refresh])

  const handleChanged = (account: MarketingAccountSummary) => {
    setAccounts(current => [...current.filter(item => item.id !== account.id), account])

    if (account.auth_state === 'authenticated') {
      selectMarketingAccount(account.id)
    }

    void refresh().catch(() => undefined)
  }

  const runAccountAction = async () => {
    if (!accountAction) {
      return
    }

    await requestGateway(
      accountAction.kind === 'delete' ? 'marketing.account.delete' : 'marketing.account.disconnect',
      { account_id: accountAction.account.id }
    )
    await refresh()
  }

  const syncAccount = async (account: MarketingAccountSummary) => {
    setSyncingAccountId(account.id)

    try {
      const result = await requestGateway<{ account: MarketingAccountSummary }>('marketing.account.sync', {
        account_id: account.id
      })

      handleChanged(result.account)
    } finally {
      setSyncingAccountId(null)
    }
  }

  return (
    <ProductPage
      action={
        <Button
          onClick={() => {
            setResumeAccount(null)
            setConnectOpen(true)
          }}
        >
          <Plus className="mr-1.5 size-4" />
          连接平台
        </Button>
      }
      description="账号是经营上下文，不是开始使用的门槛；你也可以暂不登录，从目标开始。"
      title="账号管理"
    >
      <section>
        <div className="flex items-center justify-between border-b border-(--ui-stroke-tertiary) pb-4">
          <h2 className="text-base font-semibold tracking-[-0.02em]">已连接账号</h2>
          <span className="text-xs text-(--ui-text-tertiary)">
            {accounts.filter(item => item.auth_state === 'authenticated').length} 个在线
          </span>
        </div>
        {accounts.length ? (
          <div className="divide-y divide-(--ui-stroke-tertiary)">
            {accounts.map(account => (
              <article className="py-5" key={account.id}>
                <div className="flex items-center gap-4">
                  <MarketingPlatformAvatar platform={account.platform || ''} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <strong className="truncate text-base font-semibold">
                        {account.label || account.username || account.id}
                      </strong>
                      <span
                        className={`size-1.5 rounded-full ${account.auth_state === 'authenticated' ? 'bg-emerald-500' : 'bg-amber-400'}`}
                      />
                    </div>
                    <p className="mt-1 text-xs text-(--ui-text-tertiary)">
                      {platformLabel(account.platform)} · {authStateLabel(account.auth_state)}
                    </p>
                  </div>
                  <Button
                    onClick={() => {
                      if (account.auth_state === 'authenticated') {
                        selectMarketingAccount(account.id)
                        onOpenWorkbench?.()
                      } else {
                        setResumeAccount(account)
                        setConnectOpen(true)
                      }
                    }}
                    variant={selectedId === account.id ? 'default' : 'outline'}
                  >
                    {account.auth_state === 'authenticated'
                      ? selectedId === account.id
                        ? '回到经营台'
                        : '进入经营'
                      : '继续登录'}
                  </Button>
                </div>
                <div className="mt-5 grid grid-cols-2 gap-3 rounded-[14px] bg-(--ui-bg-quaternary) px-4 py-4 sm:grid-cols-4">
                  {accountMetricSpecs(account).map(metric => (
                    <AccountMetric key={metric.label} label={metric.label} value={metric.value} />
                  ))}
                </div>
                <footer className="mt-4 flex flex-wrap items-center justify-between gap-3">
                  <span className="text-xs text-(--ui-text-tertiary)">
                    {accountUpdateTime(account)
                      ? `最近同步 ${formatAccountTime(accountUpdateTime(account)!)}`
                      : '等待首次账号验证'}
                  </span>
                  <div className="flex items-center gap-1">
                    {account.auth_state !== 'authenticated' ? (
                      <Button
                        onClick={() => {
                          setResumeAccount(account)
                          setConnectOpen(true)
                        }}
                        size="sm"
                        variant="ghost"
                      >
                        <RefreshCw className="mr-1.5 size-3.5" />
                        继续验证
                      </Button>
                    ) : (
                      <>
                        {['douyin', 'wechat_official'].includes(account.platform || '') ? (
                          <Button
                            disabled={syncingAccountId === account.id}
                            onClick={() => void syncAccount(account)}
                            size="sm"
                            variant="ghost"
                          >
                            <RefreshCw className="mr-1.5 size-3.5" />
                            {syncingAccountId === account.id ? '同步中' : '同步数据'}
                          </Button>
                        ) : null}
                        <Button
                          onClick={() => setAccountAction({ account, kind: 'disconnect' })}
                          size="sm"
                          variant="ghost"
                        >
                          退出登录
                        </Button>
                      </>
                    )}
                    <Button
                      className="text-(--ui-text-tertiary) hover:text-destructive"
                      onClick={() => setAccountAction({ account, kind: 'delete' })}
                      size="icon-sm"
                      title="删除账号"
                      variant="ghost"
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                </footer>
              </article>
            ))}
          </div>
        ) : (
          <SurfaceEmpty
            action={
              onOpenWorkbench ? (
                <Button onClick={onOpenWorkbench} variant="outline">
                  暂不登录，回到工作台
                </Button>
              ) : null
            }
            detail="不登录也可以先设置经营目标，Agent 会从公开研究和明确标注的假设开始建立经营模型。"
            title="还没有连接内容平台"
          />
        )}
      </section>
      <AccountConnectDialog
        onAccountChanged={handleChanged}
        onAnalyzeAccount={account => {
          selectMarketingAccount(account.id)
          onStartOperation({
            accountId: account.id,
            kind: 'account.analyze',
            title: account.label || account.username || account.id
          })
        }}
        onOpenChange={setConnectOpen}
        open={connectOpen}
        platforms={platforms}
        requestGateway={requestGateway}
        resumeAccount={resumeAccount}
      />
      <ConfirmDialog
        confirmLabel={accountAction?.kind === 'delete' ? '删除账号' : '退出登录'}
        description={
          accountAction?.kind === 'delete'
            ? '将删除这个账号及其本地登录信息，已有作品和经营记录不会受影响。'
            : '将退出当前账号，之后可以重新登录，经营数据仍会保留。'
        }
        destructive
        onClose={() => setAccountAction(null)}
        onConfirm={runAccountAction}
        open={Boolean(accountAction)}
        title={accountAction?.kind === 'delete' ? '确定删除这个账号？' : '确定退出这个账号？'}
      />
    </ProductPage>
  )
}

function accountMetricSpecs(account: MarketingAccountSummary): { label: string; value: number | null }[] {
  if (account.platform === 'wechat_official') {
    return [
      { label: '已同步阅读', value: accountMetric(account.stats, ['read_users']) },
      { label: '已同步分享', value: accountMetric(account.stats, ['share_users']) },
      { label: '点赞', value: accountMetric(account.stats, ['like_count']) },
      { label: '文章', value: accountMetric(account.stats, ['articles_count']) }
    ]
  }

  if (account.platform === 'douyin') {
    return [
      { label: '粉丝', value: accountMetric(account.stats, ['followers']) },
      { label: '公开播放', value: accountMetric(account.stats, ['total_views']) },
      { label: '累计获赞', value: accountMetric(account.stats, ['total_likes']) },
      { label: '公开作品', value: accountMetric(account.stats, ['videos_count']) }
    ]
  }

  return [
    { label: '粉丝', value: accountMetric(account.stats, ['followers', 'fan_count', 'fans']) },
    { label: '浏览', value: accountMetric(account.stats, ['views', 'play_count', 'total_views']) },
    {
      label: '互动',
      value: accountMetric(account.stats, ['likes', 'total_likes', 'digg_count', 'engagement', 'interaction'])
    },
    { label: '作品', value: accountMetric(account.stats, ['works', 'video_count', 'videos_count', 'content_count']) }
  ]
}

export function ManagedView({ onStartOperation, requestGateway }: OperationSurfaceProps) {
  const accountId = useStore($selectedMarketingAccountId)
  const [pending, setPending] = useState(0)

  useEffect(() => {
    if (!accountId || accountId.startsWith('prospect_')) {
      return
    }

    void requestGateway<{ total: number }>('marketing.learning.candidates.list', {
      account_id: accountId,
      limit: 100,
      status: 'pending'
    })
      .then(result => setPending(result.total || 0))
      .catch(() => setPending(0))
  }, [accountId, requestGateway])

  return (
    <ProductPage
      action={
        <Button
          onClick={() =>
            onStartOperation({
              accountId: accountId || 'prospect_default',
              kind: 'autopilot.configure'
            })
          }
        >
          设置托管
        </Button>
      }
      title="托管"
    >
      <section className="divide-y divide-(--ui-stroke-tertiary) border-y border-(--ui-stroke-tertiary)">
        <AutopilotSignal
          detail="持续关注热点、平台变化和账号表现。"
          icon={<Zap className="size-5" />}
          title="主动监测"
        />
        <AutopilotSignal
          detail="切换页面后，正在进行的工作也会继续。"
          icon={<Clock className="size-5" />}
          title="后台推进"
        />
        <AutopilotSignal
          detail={`${pending} 条策略变化等待确认，重要决定仍由你完成。`}
          icon={<Lock className="size-5" />}
          title="策略守门"
        />
      </section>
      <section className="mt-10">
        <div className="max-w-2xl">
          <h2 className="text-xl font-semibold tracking-[-0.03em]">你决定边界，它负责推进</h2>
          <p className="mt-3 text-sm leading-7 text-(--ui-text-secondary)">
            日常采集、分析和内容推进可以自动完成；发布、账号变更和长期策略调整仍会先征得你的同意。
          </p>
          <Button
            className="mt-6"
            onClick={() =>
              onStartOperation({
                accountId: accountId || 'prospect_default',
                kind: 'autopilot.configure'
              })
            }
            variant="outline"
          >
            通过自然对话设置目标 <ArrowUpRight className="ml-1.5 size-4" />
          </Button>
        </div>
      </section>
    </ProductPage>
  )
}

function platformLabel(platform?: string): string {
  return (
    {
      bilibili: 'B站',
      douyin: '抖音',
      kuaishou: '快手',
      tiktok: 'TikTok',
      wechat_channels: '视频号',
      wechat_official: '微信公众号',
      xiaohongshu: '小红书',
      youtube: 'YouTube',
      zhihu: '知乎'
    }[platform || ''] ||
    platform ||
    '内容平台'
  )
}

function authStateLabel(state?: string): string {
  return (
    {
      authenticated: '登录有效',
      unauthenticated: '尚未登录',
      verification_required: '需要重新验证'
    }[state || ''] || '状态待确认'
  )
}

function accountMetric(stats: Record<string, unknown> | undefined, keys: string[]): number | null {
  for (const key of keys) {
    const value = Number(stats?.[key])

    if (Number.isFinite(value) && value >= 0) {
      return value
    }
  }

  return null
}

function compactAccountMetric(value: number): string {
  if (value >= 100_000_000) {
    return `${(value / 100_000_000).toFixed(value >= 1_000_000_000 ? 0 : 1)}亿`
  }

  if (value >= 10_000) {
    return `${(value / 10_000).toFixed(value >= 100_000 ? 0 : 1)}万`
  }

  return new Intl.NumberFormat('zh-CN').format(value)
}

function accountUpdateTime(account: MarketingAccountSummary): number | string | null {
  if (account.last_verified_at) {
    return account.last_verified_at
  }

  const updatedAt = account.stats?.updated_at

  return typeof updatedAt === 'number' || typeof updatedAt === 'string' ? updatedAt : null
}

function formatAccountTime(value: number | string): string {
  const numeric = typeof value === 'number' ? value * (value < 10_000_000_000 ? 1000 : 1) : value
  const date = new Date(numeric)

  if (Number.isNaN(date.getTime())) {
    return '时间待同步'
  }

  return new Intl.DateTimeFormat('zh-CN', {
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    month: 'short'
  }).format(date)
}

function AccountMetric({ label, value }: { label: string; value: number | null }) {
  return (
    <div>
      <strong className="block text-lg font-semibold tabular-nums tracking-[-0.03em]">
        {value === null ? '—' : compactAccountMetric(value)}
      </strong>
      <span className="mt-1 block text-xs text-(--ui-text-tertiary)">{label}</span>
    </div>
  )
}

export function ProductPage({
  action,
  children,
  description,
  maxWidth = 'var(--mos-page-max-width)',
  onBack,
  parentLabel,
  showHeader = true,
  title
}: {
  action: React.ReactNode
  children: React.ReactNode
  description?: string
  maxWidth?: string
  onBack?: () => void
  parentLabel?: string
  showHeader?: boolean
  title: string
}) {
  const accountId = useStore($selectedMarketingAccountId)
  const accounts = useStore($marketingAccounts)
  const account = accounts.find(item => item.id === accountId)

  const accountLabel =
    account?.label || account?.username || (accountId.startsWith('prospect_') ? '未连接账号' : '当前经营对象')

  return (
    <main className="h-full overflow-y-auto bg-(--ui-chat-surface-background) text-foreground">
      <div
        className="mx-auto w-full px-7 pb-16 pt-[calc(var(--titlebar-height)+1.5rem)] sm:px-9 lg:px-12"
        style={{ maxWidth }}
      >
        {showHeader ? (
          <header className="flex min-h-10 flex-wrap items-end justify-between gap-5 border-b border-(--ui-stroke-quaternary) pb-4">
            <div className="min-w-0">
              {onBack && parentLabel ? (
                <button
                  className="mb-2 flex items-center gap-1 text-xs text-(--ui-text-tertiary) hover:text-foreground"
                  onClick={onBack}
                  type="button"
                >
                  <ChevronLeft className="size-3.5" /> {parentLabel}
                </button>
              ) : null}
              <h1 className="text-lg font-semibold tracking-[-0.035em]">{title}</h1>
              {description ? <p className="mt-1 text-xs text-(--ui-text-tertiary)">{description}</p> : null}
            </div>
            <div className="flex items-center gap-2">
              <span className="max-w-56 truncate rounded-full bg-(--ui-fill-secondary) px-3 py-1.5 text-xs text-(--ui-text-secondary)">
                {accountLabel}
              </span>
              {action}
            </div>
          </header>
        ) : null}
        <div className={`mos-page-enter ${showHeader ? 'mt-7' : ''}`}>{children}</div>
      </div>
    </main>
  )
}

function CreationEntry({ icon, onClick, title }: { icon: React.ReactNode; onClick: () => void; title: string }) {
  return (
    <button
      className="group relative flex flex-col items-center gap-3 px-1 py-2 text-xl font-semibold tracking-[-0.04em] text-(--ui-text-secondary) transition-colors duration-[var(--mos-motion-standard)] after:absolute after:inset-x-1 after:bottom-0 after:h-px after:origin-left after:scale-x-0 after:bg-(--ui-accent) after:transition-transform after:duration-[var(--mos-motion-standard)] hover:text-foreground hover:after:scale-x-100"
      onClick={onClick}
      type="button"
    >
      <span className="grid size-9 place-items-center rounded-[10px] bg-(--ui-bg-tertiary) text-(--ui-text-tertiary) transition-colors duration-[var(--mos-motion-fast)] group-hover:text-(--ui-accent)">
        {icon}
      </span>
      <span>{title}</span>
    </button>
  )
}

function AutopilotSignal({ detail, icon, title }: { detail: string; icon: React.ReactNode; title: string }) {
  return (
    <article className="grid gap-4 py-5 sm:grid-cols-[2.5rem_minmax(0,1fr)] sm:items-start">
      <span className="grid size-9 place-items-center rounded-[10px] bg-(--ui-bg-tertiary) text-(--ui-accent)">
        {icon}
      </span>
      <div>
        <h2 className="text-sm font-semibold">{title}</h2>
        <p className="mt-1 text-sm leading-6 text-(--ui-text-secondary)">{detail}</p>
      </div>
    </article>
  )
}

function SurfaceEmpty({ action, detail, title }: { action?: React.ReactNode; detail: string; title: string }) {
  return (
    <div className="grid min-h-64 place-items-center text-center">
      <div className="max-w-sm">
        <strong className="block text-sm">{title}</strong>
        <p className="mt-2 text-xs leading-5 text-(--ui-text-tertiary)">{detail}</p>
        {action ? <div className="mt-5">{action}</div> : null}
      </div>
    </div>
  )
}
