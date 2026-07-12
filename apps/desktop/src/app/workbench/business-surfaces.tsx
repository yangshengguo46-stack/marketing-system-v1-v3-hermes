import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useState } from 'react'

import { BrandMark } from '@/components/brand-mark'
import { Button } from '@/components/ui/button'
import {
  ArrowUpRight,
  Brain,
  ChevronRight,
  Clock,
  FileImage,
  FileText,
  Lock,
  MonitorPlay,
  Plus,
  Zap
} from '@/lib/icons'
import {
  $selectedMarketingAccountId,
  type MarketingAccountSummary,
  type MarketingPlatformSummary,
  selectMarketingAccount,
  setMarketingAccounts
} from '@/store/marketing'

import { AccountConnectDialog, MarketingPlatformAvatar } from './account-connect-dialog'

interface SurfaceProps {
  onNewChat: () => void
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
        <Button onClick={onNewChat}>
          <Plus className="mr-1.5 size-4" />
          开始创作
        </Button>
      }
      eyebrow="CONTENT STUDIO"
      subtitle="三条内容管道共享选题、证据、素材、预演与发布回执。"
      title="内容工厂"
    >
      <section className="grid gap-4 lg:grid-cols-3">
        <PipelineCard
          accent="coral"
          count={assets.filter(asset => asset.type === 'article_soft').length}
          detail="知乎、公众号与长图文；自动适配平台表达、配图与排版。"
          icon={<FileText className="size-5" />}
          onClick={onNewChat}
          title="图文创作"
        />
        <PipelineCard
          accent="gold"
          count={assets.filter(asset => asset.type === 'faceless_video').length}
          detail="搜索与生成素材协同，完成不露脸视频的编排、配音与剪辑。"
          icon={<FileImage className="size-5" />}
          onClick={onNewChat}
          title="素材视频"
        />
        <PipelineCard
          accent="blue"
          count={assets.filter(asset => asset.type === 'premium_video').length}
          detail="真人、数字人和 AI 影像由独立片场 Agent 预演后生产。"
          icon={<MonitorPlay className="size-5" />}
          onClick={onNewChat}
          title="高阶视频"
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
                onClick={onNewChat}
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
                    {asset.platform || '跨平台'} · {asset.status || 'draft'}
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
          <div className="divide-y divide-(--ui-stroke-tertiary)">
            {accounts.map(account => (
              <div className="flex items-center gap-4 py-5" key={account.id}>
                <MarketingPlatformAvatar platform={account.platform || ''} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <strong className="truncate text-sm font-medium">
                      {account.label || account.username || account.id}
                    </strong>
                    <span
                      className={`size-1.5 rounded-full ${account.auth_state === 'authenticated' ? 'bg-emerald-500' : 'bg-amber-400'}`}
                    />
                  </div>
                  <p className="mt-1 text-xs text-(--ui-text-tertiary)">
                    {account.platform || '内容平台'} · 独立账号空间
                  </p>
                </div>
                <Button
                  onClick={() => {
                    if (account.auth_state === 'authenticated') {
                      selectMarketingAccount(account.id)
                      onNewChat()
                    } else {
                      setResumeAccount(account)
                      setConnectOpen(true)
                    }
                  }}
                  variant={selectedId === account.id ? 'default' : 'outline'}
                >
                  {account.auth_state === 'authenticated'
                    ? selectedId === account.id
                      ? '当前账号'
                      : '进入经营'
                    : '继续登录'}
                </Button>
              </div>
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
        onOpenChange={setConnectOpen}
        open={connectOpen}
        platforms={platforms}
        requestGateway={requestGateway}
        resumeAccount={resumeAccount}
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
      action={<Button onClick={onNewChat}>和 Agent 配置托管</Button>}
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
          <Button className="mt-6" onClick={onNewChat} variant="outline">
            通过自然对话设置目标 <ArrowUpRight className="ml-1.5 size-4" />
          </Button>
        </div>
      </section>
    </ProductPage>
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
