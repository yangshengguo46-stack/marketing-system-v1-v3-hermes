import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useState } from 'react'

import { BrandMark } from '@/components/brand-mark'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import {
  ArrowUpRight,
  Brain,
  ChevronRight,
  Clock,
  FileImage,
  FileText,
  Lock,
  Plus,
  RefreshCw,
  Trash2,
  Zap
} from '@/lib/icons'
import {
  $selectedMarketingAccountId,
  type MarketingAccountSummary,
  type MarketingPlatformSummary,
  selectMarketingAccount,
  setMarketingAccounts
} from '@/store/marketing'

import {
  AccountConnectDialog,
  buildOwnedAccountAnalysisPrompt,
  MarketingPlatformAvatar
} from './account-connect-dialog'

interface SurfaceProps {
  onNewChat: (prefill?: string) => void
  requestGateway: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
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

interface AssetSummary {
  id: string
  platform?: string
  production_kind?: string
  status?: string
  title?: string
  topic?: string
  type?: string
  updated_at?: string
}

export function ContentFactoryView({ onNewChat, requestGateway }: SurfaceProps) {
  const accountId = useStore($selectedMarketingAccountId)
  const [assets, setAssets] = useState<AssetSummary[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!accountId || accountId.startsWith('prospect_')) {
      setAssets([])
      setLoading(false)

      return
    }

    setLoading(true)
    void requestGateway<{ assets: AssetSummary[] }>('marketing.content.assets.list', {
      account_id: accountId,
      limit: 40
    })
      .then(result => setAssets(result.assets || []))
      .catch(() => setAssets([]))
      .finally(() => setLoading(false))
  }, [accountId, requestGateway])

  return (
    <ProductPage
      action={
        <Button
          onClick={() =>
            onNewChat('我想开始创作内容。请先结合当前账号定位和最近真实数据，帮我选择最值得做的内容形态与选题。')
          }
        >
          <Plus className="mr-1.5 size-4" />
          开始创作
        </Button>
      }
      eyebrow="CONTENT STUDIO"
      subtitle="图文与素材视频共享选题、证据、素材、预演与发布回执。"
      title="内容工厂"
    >
      <section className="grid gap-4 lg:grid-cols-2">
        <PipelineCard
          accent="coral"
          count={assets.filter(asset => contentLane(asset) === 'article').length}
          detail="知乎、公众号与长图文；自动适配平台表达、配图与排版。"
          icon={<FileText className="size-5" />}
          onClick={() =>
            onNewChat(
              '我要创作一篇知乎或微信公众号图文。请先读取当前账号定位、目标受众和可用证据，再和我确定平台、选题和文章目标。'
            )
          }
          title="图文创作"
        />
        <PipelineCard
          accent="gold"
          count={assets.filter(asset => contentLane(asset) === 'faceless').length}
          detail="搜索与生成素材协同，完成不露脸视频的编排、配音与剪辑。"
          icon={<FileImage className="size-5" />}
          onClick={() =>
            onNewChat(
              '我要制作一条不露脸素材视频。请先读取当前账号定位和目标平台，再给出选题、素材方案、配音与剪辑计划。'
            )
          }
          title="素材视频"
        />
      </section>

      <section className="mt-5 rounded-[24px] border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) p-7">
        <div className="flex items-center justify-between border-b border-(--ui-stroke-tertiary) pb-5">
          <div>
            <p className="text-[0.66rem] font-semibold tracking-[0.18em] text-(--ui-text-tertiary)">PRODUCTION FLOW</p>
            <h2 className="mt-2 text-lg font-semibold">最近内容</h2>
          </div>
          <span className="text-xs text-(--ui-text-tertiary)">{loading ? '正在同步' : `${assets.length} 项资产`}</span>
        </div>
        {assets.length ? (
          <div className="divide-y divide-(--ui-stroke-tertiary)">
            {assets.slice(0, 12).map((asset, index) => (
              <button
                className="group flex w-full items-center gap-5 py-4 text-left"
                key={asset.id}
                onClick={() =>
                  onNewChat(
                    `请继续推进内容资产 ${asset.id}（${asset.title || asset.topic || '未命名内容'}）。先读取当前版本、证据和审核状态，再告诉我下一步。`
                  )
                }
                type="button"
              >
                <span className="w-6 text-[0.66rem] font-semibold text-(--ui-text-quaternary)">
                  {String(index + 1).padStart(2, '0')}
                </span>
                <span className="min-w-0 flex-1">
                  <strong className="block truncate text-sm font-medium">
                    {asset.title || asset.topic || '未命名内容'}
                  </strong>
                  <small className="mt-1 block text-xs text-(--ui-text-tertiary)">
                    {formatAssetKind(asset)} · {formatAssetStatus(asset.status)}
                  </small>
                </span>
                <ChevronRight className="size-4 text-(--ui-text-quaternary) group-hover:text-foreground" />
              </button>
            ))}
          </div>
        ) : (
          <SurfaceEmpty
            detail="直接告诉 Agent 你要写什么，或者从工作台的选题进入。第一条内容会自动出现在这里。"
            title="草稿箱还是空的"
          />
        )}
      </section>
    </ProductPage>
  )
}

export function AccountCenterView({ onNewChat, requestGateway }: SurfaceProps) {
  const selectedId = useStore($selectedMarketingAccountId)
  const [accounts, setAccounts] = useState<MarketingAccountSummary[]>([])
  const [platforms, setPlatforms] = useState<MarketingPlatformSummary[]>([])
  const [connectOpen, setConnectOpen] = useState(false)
  const [resumeAccount, setResumeAccount] = useState<MarketingAccountSummary | null>(null)

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
      eyebrow="ACCOUNT HUB"
      subtitle="每个账号拥有独立登录环境、经营模型、内容资产和学习记录。"
      title="账号管理"
    >
      <section className="rounded-[24px] border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) p-7">
        <div className="flex items-center justify-between border-b border-(--ui-stroke-tertiary) pb-5">
          <h2 className="text-lg font-semibold">已连接账号</h2>
          <span className="text-xs text-(--ui-text-tertiary)">
            {accounts.filter(item => item.auth_state === 'authenticated').length} 个在线
          </span>
        </div>
        {accounts.length ? (
          <div className="space-y-4 pt-5">
            {accounts.map(account => (
              <article className="rounded-[20px] border border-(--ui-stroke-tertiary) p-5" key={account.id}>
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
                        onNewChat(buildOwnedAccountAnalysisPrompt(account))
                      } else {
                        setResumeAccount(account)
                        setConnectOpen(true)
                      }
                    }}
                    variant={selectedId === account.id ? 'default' : 'outline'}
                  >
                    {account.auth_state === 'authenticated'
                      ? account.platform === 'wechat_official'
                        ? selectedId === account.id
                          ? '同步文章并评分'
                          : '诊断公众号'
                        : selectedId === account.id
                          ? '进入当前账号'
                          : '进入经营'
                      : '继续登录'}
                  </Button>
                </div>
                <div className="mt-5 grid grid-cols-2 gap-3 border-y border-(--ui-stroke-tertiary) py-4 sm:grid-cols-4">
                  <AccountMetric
                    label="粉丝"
                    value={accountMetric(account.stats, ['followers', 'fan_count', 'fans'])}
                  />
                  <AccountMetric
                    label="浏览"
                    value={accountMetric(account.stats, ['views', 'play_count', 'total_views'])}
                  />
                  <AccountMetric
                    label="互动"
                    value={accountMetric(account.stats, [
                      'likes',
                      'total_likes',
                      'digg_count',
                      'engagement',
                      'interaction'
                    ])}
                  />
                  <AccountMetric
                    label="作品"
                    value={accountMetric(account.stats, ['works', 'video_count', 'videos_count', 'content_count'])}
                  />
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
                      <Button
                        onClick={() => setAccountAction({ account, kind: 'disconnect' })}
                        size="sm"
                        variant="ghost"
                      >
                        退出登录
                      </Button>
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
            detail="也可以不登录账号，先通过自然对话完成个人能力、赛道和目标受众建模。"
            title="还没有连接内容平台"
          />
        )}
      </section>
      <AccountConnectDialog
        onAccountChanged={handleChanged}
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
      <ConfirmDialog
        confirmLabel={accountAction?.kind === 'delete' ? '删除账号' : '退出登录'}
        description={
          accountAction?.kind === 'delete'
            ? '将删除账号记录并清理该账号独立浏览器环境。已有内容资产和经营记录不会被悄悄迁移到其他账号。'
            : '将结束当前登录状态并释放浏览器会话。之后可以重新扫码登录，经营数据仍保留。'
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

export function ManagedView({ onNewChat, requestGateway }: SurfaceProps) {
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
        <Button onClick={() => onNewChat('请为当前账号配置托管目标、授权边界、运行频率和需要人工确认的动作。')}>
          和 Agent 配置托管
        </Button>
      }
      eyebrow="AUTOPILOT"
      subtitle="让 Agent 持续采集、判断和推进；涉及身份、发布与策略改变时仍由你决定。"
      title="托管"
    >
      <section className="grid gap-4 lg:grid-cols-3">
        <AutopilotSignal
          detail="热点、平台规则和账号回执会按经营目标持续更新。"
          icon={<Zap className="size-5" />}
          title="主动监测"
        />
        <AutopilotSignal
          detail="长任务与内容管线在切换页面后继续运行，不依赖当前窗口。"
          icon={<Clock className="size-5" />}
          title="后台推进"
        />
        <AutopilotSignal
          detail={`${pending} 条策略变化等待确认；真实结果不会直接污染长期模型。`}
          icon={<Lock className="size-5" />}
          title="策略守门"
        />
      </section>
      <section className="mt-5 rounded-[24px] border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) p-8">
        <div className="max-w-2xl">
          <p className="text-[0.66rem] font-semibold tracking-[0.18em] text-(--ui-text-tertiary)">OPERATING MODE</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-[-0.035em]">托管不是“一键乱跑”</h2>
          <p className="mt-3 text-sm leading-7 text-(--ui-text-secondary)">
            Agent 会自行补证据、预演方案和恢复失败任务；发布、账号身份变更和长期策略学习仍遵循你的授权边界。
          </p>
          <Button
            className="mt-6"
            onClick={() => onNewChat('请通过自然对话帮我设置当前账号的长期经营目标和托管边界。')}
            variant="outline"
          >
            通过自然对话设置目标 <ArrowUpRight className="ml-1.5 size-4" />
          </Button>
        </div>
      </section>
    </ProductPage>
  )
}

function contentLane(asset: AssetSummary): 'article' | 'faceless' | 'unknown' {
  const values = [asset.production_kind, asset.type, asset.platform]
    .map(value => (value || '').toLowerCase())
    .filter(Boolean)

  if (
    values.some(value =>
      ['article', 'article_soft', 'multi_article', 'wechat_article', 'zhihu_article'].includes(value)
    )
  ) {
    return 'article'
  }

  if (values.some(value => ['faceless_video', 'material_video', 'remix_video'].includes(value))) {
    return 'faceless'
  }

  return 'unknown'
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

function formatAssetKind(asset: AssetSummary): string {
  const lane = contentLane(asset)

  return { article: '图文', faceless: '素材视频', unknown: '内容资产' }[lane]
}

function formatAssetStatus(status?: string): string {
  return (
    {
      draft: '草稿',
      needs_revision: '需要修改',
      ready_for_human_review: '等待确认',
      review_ready: '等待确认',
      approved: '已确认',
      published: '已发布'
    }[status || ''] || '推进中'
  )
}

function ProductPage({
  action,
  children,
  eyebrow,
  subtitle,
  title
}: {
  action: React.ReactNode
  children: React.ReactNode
  eyebrow: string
  subtitle: string
  title: string
}) {
  return (
    <main className="h-full overflow-y-auto bg-(--ui-background) text-foreground">
      <div className="mx-auto w-full max-w-[1280px] px-8 pb-16 pt-[calc(var(--titlebar-height)+2.5rem)] lg:px-12">
        <header className="flex items-start justify-between gap-8 border-b border-(--ui-stroke-tertiary) pb-7">
          <div className="flex items-start gap-4">
            <BrandMark className="mt-0.5 size-9 text-[1.8rem]" />
            <div>
              <p className="text-[0.66rem] font-semibold tracking-[0.22em] text-(--ui-text-tertiary)">{eyebrow}</p>
              <h1 className="mt-1 text-[1.8rem] font-semibold tracking-[-0.04em]">{title}</h1>
              <p className="mt-2 text-sm text-(--ui-text-secondary)">{subtitle}</p>
            </div>
          </div>
          {action}
        </header>
        <div className="mt-7">{children}</div>
      </div>
    </main>
  )
}

function PipelineCard({
  accent,
  count,
  detail,
  icon,
  onClick,
  title
}: {
  accent: 'blue' | 'coral' | 'gold'
  count: number
  detail: string
  icon: React.ReactNode
  onClick: () => void
  title: string
}) {
  const accents = {
    blue: 'bg-blue-500/10 text-blue-500',
    coral: 'bg-(--ui-accent)/10 text-(--ui-accent)',
    gold: 'bg-amber-500/10 text-amber-600'
  }

  return (
    <button
      className="group min-h-56 rounded-[24px] border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) p-6 text-left shadow-[0_14px_42px_rgba(34,30,26,0.04)] transition-transform hover:-translate-y-0.5"
      onClick={onClick}
      type="button"
    >
      <div className="flex items-start justify-between">
        <span className={`grid size-10 place-items-center rounded-2xl ${accents[accent]}`}>{icon}</span>
        <span className="text-xs text-(--ui-text-tertiary)">{count} 项</span>
      </div>
      <h2 className="mt-9 text-xl font-semibold tracking-[-0.03em]">{title}</h2>
      <p className="mt-3 text-sm leading-6 text-(--ui-text-secondary)">{detail}</p>
      <span className="mt-5 flex items-center gap-1 text-xs font-medium text-(--ui-text-tertiary) group-hover:text-foreground">
        开始创作 <ArrowUpRight className="size-3.5" />
      </span>
    </button>
  )
}

function AutopilotSignal({ detail, icon, title }: { detail: string; icon: React.ReactNode; title: string }) {
  return (
    <article className="rounded-[24px] border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) p-6">
      <span className="grid size-10 place-items-center rounded-2xl bg-(--ui-accent)/10 text-(--ui-accent)">{icon}</span>
      <h2 className="mt-7 text-lg font-semibold">{title}</h2>
      <p className="mt-2 text-sm leading-6 text-(--ui-text-secondary)">{detail}</p>
    </article>
  )
}

function SurfaceEmpty({ detail, title }: { detail: string; title: string }) {
  return (
    <div className="grid min-h-64 place-items-center text-center">
      <div className="max-w-sm">
        <span className="mx-auto grid size-11 place-items-center rounded-full bg-(--ui-fill-secondary) text-(--ui-text-secondary)">
          <Brain className="size-4" />
        </span>
        <strong className="mt-4 block text-sm">{title}</strong>
        <p className="mt-2 text-xs leading-5 text-(--ui-text-tertiary)">{detail}</p>
      </div>
    </div>
  )
}
