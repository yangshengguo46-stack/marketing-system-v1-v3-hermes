import {
  SiBilibili,
  SiKuaishou,
  SiTiktok,
  SiWechat,
  SiXiaohongshu,
  SiYoutube,
  SiZhihu
} from '@icons-pack/react-simple-icons'
import { type ComponentType, type ReactNode, type SVGProps, useCallback, useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { CheckCircle2, Loader2 } from '@/lib/icons'
import type { MarketingAccountSummary, MarketingPlatformSummary } from '@/store/marketing'

interface AccountConnectDialogProps {
  onAnalyzeAccount?: (account: MarketingAccountSummary) => void
  onAccountChanged: (account: MarketingAccountSummary) => void
  onOpenChange: (open: boolean) => void
  open: boolean
  platforms: MarketingPlatformSummary[]
  requestGateway: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
  resumeAccount?: MarketingAccountSummary | null
}

interface AccountEnvelope {
  account: MarketingAccountSummary
}

interface LoginStartEnvelope extends AccountEnvelope {
  browser_owner: string
  login_state: string
}

interface LoginVerifyEnvelope extends AccountEnvelope {
  verified: boolean
  verification?: { reason?: string }
}

type ConnectStage = 'choose' | 'starting' | 'waiting' | 'verified' | 'error'

export function AccountConnectDialog({
  onAnalyzeAccount,
  onAccountChanged,
  onOpenChange,
  open,
  platforms,
  requestGateway,
  resumeAccount
}: AccountConnectDialogProps) {
  const [account, setAccount] = useState<MarketingAccountSummary | null>(null)
  const [error, setError] = useState('')
  const [stage, setStage] = useState<ConnectStage>('choose')
  const verifyInFlight = useRef(false)

  useEffect(() => {
    if (!open) {
      setAccount(null)
      setError('')
      setStage('choose')
      verifyInFlight.current = false

      return
    }

    if (resumeAccount) {
      setAccount(resumeAccount)
    }
  }, [open, resumeAccount])

  const verifyLogin = useCallback(async () => {
    if (!account || verifyInFlight.current || stage !== 'waiting') {
      return
    }

    verifyInFlight.current = true

    try {
      const result = await requestGateway<LoginVerifyEnvelope>('marketing.account.login.verify', {
        account_id: account.id
      })

      if (result.verified) {
        setAccount(result.account)
        onAccountChanged(result.account)
        setStage('verified')
      }
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason)

      if (!/not been verified|cookie_set_not_found/i.test(message)) {
        setError(message)
      }
    } finally {
      verifyInFlight.current = false
    }
  }, [account, onAccountChanged, requestGateway, stage])

  useEffect(() => {
    if (!open || stage !== 'waiting') {
      return
    }

    const first = window.setTimeout(() => void verifyLogin(), 1800)
    const interval = window.setInterval(() => void verifyLogin(), 3000)

    return () => {
      window.clearTimeout(first)
      window.clearInterval(interval)
    }
  }, [open, stage, verifyLogin])

  const startLogin = async (platform?: MarketingPlatformSummary) => {
    setError('')
    setStage('starting')

    try {
      let target = account

      if (!target) {
        if (!platform) {
          throw new Error('请选择平台')
        }

        const created = await requestGateway<AccountEnvelope>('marketing.accounts.register', {
          label: `${platform.label}账号`,
          platform: platform.id
        })

        target = created.account
        setAccount(target)
        onAccountChanged(target)
      }

      const started = await requestGateway<LoginStartEnvelope>('marketing.account.login.start', {
        account_id: target.id
      })

      setAccount(started.account)
      setStage('waiting')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
      setStage('error')
    }
  }

  const selectedPlatform = platforms.find(item => item.id === account?.platform)

  const orderedPlatforms = [...platforms].sort((left, right) => {
    const priority = (id: string) => (id === 'wechat_official' ? 0 : id === 'zhihu' ? 1 : 2)

    return priority(left.id) - priority(right.id)
  })

  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent className="max-w-xl gap-5 p-6">
        <DialogHeader>
          <DialogTitle>{stage === 'verified' ? '账号已连接' : '连接内容平台'}</DialogTitle>
          <DialogDescription>
            登录发生在该账号独立的持久浏览器中。Marketing OS 只保存账号状态，不把 Cookie 交给界面。
          </DialogDescription>
        </DialogHeader>

        {stage === 'choose' && !account ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {orderedPlatforms.map(platform => (
              <button
                className="group flex min-h-24 flex-col items-start justify-between rounded-xl border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) p-4 text-left transition-colors hover:border-(--ui-accent)"
                key={platform.id}
                onClick={() => void startLogin(platform)}
                type="button"
              >
                <MarketingPlatformAvatar platform={platform.id} />
                <span>
                  <strong className="flex items-center gap-2 text-sm font-semibold">
                    {platform.label}
                    {platform.id === 'wechat_official' ? (
                      <em className="not-italic text-[0.62rem] font-medium text-emerald-500">可诊断历史文章</em>
                    ) : null}
                  </strong>
                  <small className="mt-0.5 block text-[0.68rem] text-(--ui-text-tertiary)">
                    {platform.content.includes('article') ? '图文 / 文章' : '短视频'}
                  </small>
                </span>
              </button>
            ))}
          </div>
        ) : null}

        {stage === 'choose' && account ? (
          <div className="flex items-center justify-between rounded-xl border border-(--ui-stroke-tertiary) p-4">
            <div className="flex items-center gap-3">
              <MarketingPlatformAvatar platform={account.platform || ''} />
              <div>
                <strong className="block text-sm">{selectedPlatform?.label || account.platform || '内容平台'}</strong>
                <span className="text-xs text-(--ui-text-tertiary)">继续使用原账号隔离空间登录</span>
              </div>
            </div>
            <Button onClick={() => void startLogin()}>打开登录窗口</Button>
          </div>
        ) : null}

        {stage === 'starting' ? (
          <ConnectStatus
            detail="正在启动这个账号专属的持久浏览器…"
            icon={<Loader2 className="size-5 animate-spin" />}
            title="准备登录环境"
          />
        ) : null}

        {stage === 'waiting' ? (
          <ConnectStatus
            detail="请在刚打开的平台窗口中完成扫码、验证码或密码登录。完成后这里会自动识别，不需要手动复制任何信息。"
            icon={<span className="size-2.5 animate-pulse rounded-full bg-emerald-500" />}
            title={`等待${selectedPlatform?.label || ''}登录`}
          >
            <Button onClick={() => void verifyLogin()} size="sm" variant="outline">
              我已完成，立即检查
            </Button>
          </ConnectStatus>
        ) : null}

        {stage === 'verified' ? (
          <ConnectStatus
            detail={
              account?.platform === 'wechat_official'
                ? '独立账号空间已保存。现在可以同步你已经发布的文章，让 Agent 基于真实作品和可用指标诊断账号。'
                : '独立账号空间已保存。后续采集、分析和经授权发布都会自动使用这个账号，不需要重复扫码。'
            }
            icon={<CheckCircle2 className="size-6 text-emerald-500" />}
            title="登录验证成功"
          >
            <div className="flex flex-wrap gap-2">
              {account?.platform === 'wechat_official' && onAnalyzeAccount ? (
                <Button
                  onClick={() => {
                    onOpenChange(false)
                    onAnalyzeAccount(account)
                  }}
                >
                  同步文章并评分
                </Button>
              ) : null}
              <Button
                onClick={() => onOpenChange(false)}
                variant={account?.platform === 'wechat_official' ? 'outline' : 'default'}
              >
                {account?.platform === 'wechat_official' ? '稍后再说' : '完成'}
              </Button>
            </div>
          </ConnectStatus>
        ) : null}

        {stage === 'error' ? (
          <ConnectStatus
            detail={error || '登录环境启动失败，请重试。'}
            icon={<span className="size-2.5 rounded-full bg-red-500" />}
            title="暂时无法连接"
          >
            <Button onClick={() => void startLogin()} size="sm" variant="outline">
              重试
            </Button>
          </ConnectStatus>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}

export function buildOwnedAccountAnalysisPrompt(account: MarketingAccountSummary): string {
  if (account.platform === 'wechat_official') {
    return (
      '请诊断当前会话绑定的微信公众号。先调用 browser_collect_wechat_official_portfolio 同步最近已发布文章，' +
      '再调用 marketing_read_account_portfolio 读取系统生成的作品档案和执行基线。请按“已证实事实、账号评分、' +
      '每篇文章观察、核心优势、关键问题、下一步实验”输出；每个判断引用对应 evidence_id。没有阅读、点赞、' +
      '分享或评论数据时明确写数据缺口，不得猜测粉丝反馈，也不要把启发式执行分当成内容价值的最终定论。'
    )
  }

  if (account.platform === 'douyin') {
    return (
      '请诊断当前会话绑定的抖音账号。先调用 browser_collect_douyin_portfolio 同步创作者中心的账号和作品数据，' +
      '再读取账号经营上下文。请明确区分公开已发布作品数、包含私密作品的全部作品数，以及每条作品的播放、' +
      '点赞、评论、分享、完播和平均观看指标；不得用“近30天未发布”推断累计作品数。'
    )
  }

  return `请进入账号 ${account.id} 的经营上下文，先汇总账号现状、受众、定位和今天最值得推进的任务。`
}

function ConnectStatus({
  children,
  detail,
  icon,
  title
}: {
  children?: ReactNode
  detail: string
  icon: ReactNode
  title: string
}) {
  return (
    <div className="rounded-2xl border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) p-6">
      <div className="flex items-center gap-3">
        <span className="grid size-10 place-items-center rounded-full bg-(--ui-bg-tertiary)">{icon}</span>
        <strong className="text-base">{title}</strong>
      </div>
      <p className="mt-4 text-sm leading-6 text-(--ui-text-secondary)">{detail}</p>
      {children ? <div className="mt-5">{children}</div> : null}
    </div>
  )
}

const PLATFORM_ICONS: Record<string, { color: string; Icon?: ComponentType<SVGProps<SVGSVGElement>>; text?: string }> =
  {
    bilibili: { color: '#00AEEC', Icon: SiBilibili },
    douyin: { color: '#FE2C55', Icon: SiTiktok },
    kuaishou: { color: '#FF4906', Icon: SiKuaishou },
    tiktok: { color: '#FE2C55', Icon: SiTiktok },
    wechat_channels: { color: '#FA9D3B', text: '∞' },
    wechat_official: { color: '#07C160', Icon: SiWechat },
    xiaohongshu: { color: '#FF2442', Icon: SiXiaohongshu },
    youtube: { color: '#FF0000', Icon: SiYoutube },
    zhihu: { color: '#0084FF', Icon: SiZhihu }
  }

export function MarketingPlatformAvatar({ platform }: { platform: string }) {
  const spec = PLATFORM_ICONS[platform] || { color: '#64748B', text: '?' }
  const Icon = spec.Icon

  return (
    <span
      aria-hidden="true"
      className="grid size-9 place-items-center rounded-xl text-base font-semibold"
      style={{ backgroundColor: `color-mix(in srgb, ${spec.color} 13%, transparent)`, color: spec.color }}
    >
      {Icon ? <Icon className="size-5" /> : spec.text}
    </span>
  )
}
