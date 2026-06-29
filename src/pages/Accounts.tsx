import { useEffect, useRef, useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { api, PLATFORM_NAMES, PLATFORM_COLORS } from '@/api/client'
import { BellRing, Check, ChevronRight, Globe2, Loader2, MessageCircle, RefreshCw, Send, ShieldCheck, Trash2 } from 'lucide-react'

const DOMESTIC_PLATFORMS: Platform[] = [
  'douyin', 'wechat_channels', 'xiaohongshu', 'kuaishou', 'bilibili', 'weibo', 'zhihu',
]

const GLOBAL_PLATFORMS: Platform[] = [
  'tiktok', 'youtube', 'instagram', 'facebook', 'twitter',
]

const mOS = window.marketingOS

export default function Accounts() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loading, setLoading] = useState(true)
  const [loggingIn, setLoggingIn] = useState<string | null>(null)
  const [syncing, setSyncing] = useState<string | null>(null)
  const [notice, setNotice] = useState<{ tone: 'error' | 'warning'; message: string } | null>(null)
  const savedPlatforms = useRef(new Set<string>())

  const load = () => {
    api.accounts()
      .then((data) => { setAccounts(data.accounts || []); setLoading(false) })
      .catch(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  useEffect(() => {
    if (!mOS) return
    const unsubscribe = mOS.onLoginCookies((data) => {
      if (data.count === 0) {
        setNotice({ tone: 'error', message: `没有读取到 ${PLATFORM_NAMES[data.platform]} 的登录凭据，请确认登录完成后再试。` })
        return
      }
      if (savedPlatforms.current.has(data.platform)) return
      savedPlatforms.current.add(data.platform)
      api.addAccount({
        platform: data.platform,
        username: data.username || `${data.platform}_session`,
        label: data.label || `${PLATFORM_NAMES[data.platform]}账号`,
      }).then((result) => {
        const payload = result as { warning?: string }
        if (payload.warning) setNotice({ tone: 'warning', message: payload.warning })
        setLoggingIn(null)
        load()
      }).catch((reason) => {
        savedPlatforms.current.delete(data.platform)
        setNotice({ tone: 'error', message: String(reason?.message || reason || '账号保存失败') })
      })
    })
    return unsubscribe
  }, [])

  const startLogin = (platform: string) => {
    if (!mOS) return
    savedPlatforms.current.delete(platform)
    setNotice(null)
    setLoggingIn(platform)
    mOS.openLoginBrowser(platform)
  }

  const finishLogin = () => {
    if (loggingIn && mOS) mOS.closeLoginBrowser(loggingIn)
  }

  const remove = (id: string) => api.deleteAccount(id).then(load).catch((reason) => {
    setNotice({ tone: 'error', message: String(reason?.message || reason || '账号删除失败') })
  })

  const sync = async (id: string) => {
    setSyncing(id)
    setNotice(null)
    try {
      const account = accounts.find((item) => item.id === id)
      if (!account || !mOS) throw new Error('账号会话不可用')
      const stats = await mOS.syncAccountSession(account.platform, account.username)
      await api.updateAccountStats(id, stats)
      await load()
    } catch (reason) {
      setNotice({ tone: 'error', message: String((reason as Error)?.message || reason || '账号指标同步失败') })
    } finally {
      setSyncing(null)
    }
  }

  if (loading) {
    return <div className="flex justify-center py-24">{['','',''].map((_, index) => <div key={index} className="w-2 h-2 rounded-full bg-muted-foreground/20 animate-bounce mx-0.5" style={{ animationDelay: `${index * .1}s` }} />)}</div>
  }

  return (
    <div className="accounts-page animate-fade-up">
      <div className="standard-page-header">
        <div>
          <span className="page-kicker">ACCOUNT HUB</span>
          <h1>账号管理</h1>
          <p>统一管理国内与海外内容平台。</p>
        </div>
        <div className="account-summary"><Globe2 size={15} /><strong>{accounts.length}</strong><span>个账号已连接</span></div>
      </div>

      {notice && (
        <Card className={notice.tone === 'error' ? 'border-destructive/30' : 'border-amber-500/30'}>
          <CardContent className="px-5 py-4 text-sm">{notice.message}</CardContent>
        </Card>
      )}

      {loggingIn && (
        <Card className="border-primary/30 bg-primary/5">
          <CardContent className="flex items-center gap-4 px-5 py-4">
            <Loader2 className="h-5 w-5 text-primary animate-spin" />
            <div className="flex-1">
              <div className="text-sm font-semibold">正在登录 {PLATFORM_NAMES[loggingIn]}...</div>
              <div className="text-xs text-muted-foreground">请在登录窗口中完成授权</div>
            </div>
            <Button variant="outline" size="sm" onClick={finishLogin}><Check className="h-4 w-4 mr-1.5" />完成登录</Button>
          </CardContent>
        </Card>
      )}

      <MessagingChannels />

      {accounts.length > 0 && (
        <section className="connected-accounts">
          <div className="account-section-heading"><div><span className="page-kicker">CONNECTED</span><h2>已连接账号</h2></div><span>{accounts.length} 个在线</span></div>
          <div className="connected-list">
            {accounts.map((account) => (
              <div className="connected-row" key={account.id}>
                <PlatformMark platform={account.platform} />
                <div className="connected-identity"><strong>{account.label || PLATFORM_NAMES[account.platform]}</strong><span>@{account.username}</span></div>
                <div className="account-stat"><strong>{formatMetric(account.stats?.followers)}</strong><span>粉丝</span></div>
                <div className="account-stat"><strong>{formatMetric(account.stats?.total_views)}</strong><span>累计播放</span></div>
                <Badge variant="outline" className="border-emerald-500/30 text-emerald-500 gap-1.5"><i className="w-1.5 h-1.5 rounded-full bg-emerald-500" />在线</Badge>
                <Button variant="ghost" size="icon" className="h-8 w-8" title="同步账号指标" disabled={syncing === account.id} onClick={() => sync(account.id)}><RefreshCw className={`h-4 w-4 text-muted-foreground ${syncing === account.id ? 'animate-spin' : ''}`} /></Button>
                <Button variant="ghost" size="icon" className="h-8 w-8" title="移除账号" onClick={() => remove(account.id)}><Trash2 className="h-4 w-4 text-muted-foreground" /></Button>
              </div>
            ))}
          </div>
        </section>
      )}

      <PlatformGroup
        eyebrow="CHINA"
        title="国内平台"
        description="覆盖主流短视频、内容社区与视频号生态"
        platforms={DOMESTIC_PLATFORMS}
        accounts={accounts}
        disabled={loggingIn !== null}
        onConnect={startLogin}
      />

      <PlatformGroup
        eyebrow="GLOBAL"
        title="海外平台"
        description="面向全球短视频、社交媒体与长视频渠道"
        platforms={GLOBAL_PLATFORMS}
        accounts={accounts}
        disabled={loggingIn !== null}
        onConnect={startLogin}
      />
    </div>
  )
}

function MessagingChannels() {
  const [channels, setChannels] = useState<MessagingChannelStatus | null>(null)
  const [connecting, setConnecting] = useState<MessagingPlatform | null>(null)
  const [testing, setTesting] = useState<MessagingPlatform | null>(null)
  const [qr, setQr] = useState<{ platform: MessagingPlatform; image: string; url: string } | null>(null)
  const [message, setMessage] = useState('')

  const load = () => mOS?.getChannelStatus().then(setChannels).catch((reason) => setMessage(String(reason?.message || reason)))

  useEffect(() => {
    load()
    if (!mOS) return
    return mOS.onChannelProgress((event) => {
      if (event.event === 'qr' && event.platform && event.qr_image) {
        setQr({ platform: event.platform, image: event.qr_image, url: event.qr_url || '' })
        setMessage(`请用${event.platform === 'weixin' ? '微信' : '飞书'}扫描二维码并确认授权`)
      }
      if (event.event === 'connected') {
        setQr(null)
        setMessage(event.platform === 'feishu' ? '连接成功。打开飞书机器人随便发一句话，当前对话会自动成为通知窗口。' : '连接成功，微信已成为你的随身营销助手。')
        load()
      }
      if (event.event === 'error') setMessage(event.message || '连接失败')
    })
  }, [])

  const connect = async (platform: MessagingPlatform) => {
    if (!mOS) return
    setConnecting(platform)
    setQr(null)
    setMessage('正在生成安全二维码…')
    try {
      await mOS.connectChannel(platform)
      await load()
    } catch (reason) {
      setMessage(String((reason as Error)?.message || reason || '连接失败'))
    } finally {
      setConnecting(null)
    }
  }

  const test = async (platform: MessagingPlatform, retryId?: string) => {
    if (!mOS) return
    setTesting(platform)
    try {
      if (retryId) await mOS.retryChannel(retryId)
      else await mOS.testChannel(platform)
      setMessage(retryId ? '消息重试成功，已经送达。' : '测试消息已送达。之后的行业简报会自动推送到这个会话。')
      await load()
    } catch (reason) {
      setMessage(String((reason as Error)?.message || reason || '测试发送失败'))
    } finally {
      setTesting(null)
    }
  }

  return (
    <section className="messaging-section">
      <div className="account-section-heading">
        <div><span className="page-kicker">MOBILE ASSISTANT</span><h2>随身助手</h2><p>离开电脑也能接收行业简报、异常提醒，并继续聊营销方案</p></div>
        <span><ShieldCheck size={12} /> 扫码人自动授权</span>
      </div>
      <div className="messaging-grid">
        <ChannelCard
          platform="weixin"
          name="微信"
          description="个人微信扫码，热点与方案随时聊"
          state={channels?.weixin}
          busy={connecting === 'weixin'}
          testing={testing === 'weixin'}
          onConnect={connect}
          onTest={test}
        />
        <ChannelCard
          platform="feishu"
          name="飞书"
          description="扫码自动创建机器人，无需公网地址"
          state={channels?.feishu}
          busy={connecting === 'feishu'}
          testing={testing === 'feishu'}
          onConnect={connect}
          onTest={test}
        />
      </div>
      {(qr || message) && (
        <div className="channel-onboarding">
          {qr && <img src={qr.image} alt={`${qr.platform === 'weixin' ? '微信' : '飞书'}连接二维码`} />}
          <div>
            <strong>{qr ? '扫码连接随身助手' : '连接提示'}</strong>
            <p>{message}</p>
            {qr?.url && <span>二维码有效期有限，过期后重新点击连接即可。</span>}
          </div>
        </div>
      )}
    </section>
  )
}

function ChannelCard({ platform, name, description, state, busy, testing, onConnect, onTest }: {
  platform: MessagingPlatform
  name: string
  description: string
  state?: MessagingChannelState
  busy: boolean
  testing: boolean
  onConnect: (platform: MessagingPlatform) => void
  onTest: (platform: MessagingPlatform, retryId?: string) => void
}) {
  return (
    <div className={`messaging-card ${state?.connected ? 'connected' : ''}`}>
      <span className={`channel-logo ${platform}`}><MessageCircle size={18} /></span>
      <div className="channel-copy">
        <strong>{name}</strong>
        <p>{description}</p>
        <span>{state?.last_delivery ? `${state.last_delivery.success ? '最近消息已送达' : '最近消息发送失败'} · ${new Date(state.last_delivery.created_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}` : state?.ready_to_push ? '聊天与自动推送已就绪' : state?.connected ? '给机器人发一句话即可开启推送' : '尚未连接'}</span>
      </div>
      {state?.connected ? (
        <Button size="sm" variant="outline" disabled={testing} onClick={() => onTest(platform, state.last_delivery?.success === false ? state.last_delivery.id : undefined)}>
          {testing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : state.ready_to_push ? <Send className="h-3.5 w-3.5" /> : <BellRing className="h-3.5 w-3.5" />}
          {state.last_delivery?.success === false ? '重试' : state.ready_to_push ? '发测试消息' : '检查通知'}
        </Button>
      ) : (
        <Button size="sm" disabled={busy} onClick={() => onConnect(platform)}>
          {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}{busy ? '等待扫码' : '扫码连接'}
        </Button>
      )}
    </div>
  )
}

function PlatformGroup({ eyebrow, title, description, platforms, accounts, disabled, onConnect }: {
  eyebrow: string
  title: string
  description: string
  platforms: Platform[]
  accounts: Account[]
  disabled: boolean
  onConnect: (platform: string) => void
}) {
  return (
    <section className="platform-group">
      <div className="account-section-heading">
        <div><span className="page-kicker">{eyebrow}</span><h2>{title}</h2><p>{description}</p></div>
      </div>
      <div className="platform-grid">
        {platforms.map((platform) => {
          const connected = accounts.some((account) => account.platform === platform)
          return (
            <button className="platform-connect-card" key={platform} disabled={disabled || connected} onClick={() => onConnect(platform)}>
              <PlatformMark platform={platform} />
              <span className="platform-name"><strong>{PLATFORM_NAMES[platform]}</strong><small>{connected ? '已连接' : '连接账号'}</small></span>
              {connected ? <Check size={15} className="platform-connected" /> : <ChevronRight size={15} />}
            </button>
          )
        })}
      </div>
    </section>
  )
}

function PlatformMark({ platform }: { platform: Platform }) {
  return (
    <span className="platform-mark" style={{ backgroundColor: PLATFORM_COLORS[platform] }}>
      {PLATFORM_NAMES[platform]?.slice(0, 1)}
    </span>
  )
}

function formatMetric(value: unknown) {
  const number = Number(value || 0)
  return number ? new Intl.NumberFormat('zh-CN', { notation: number >= 10000 ? 'compact' : 'standard', maximumFractionDigits: 1 }).format(number) : '--'
}
