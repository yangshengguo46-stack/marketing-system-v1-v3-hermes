import { useEffect, useRef, useState } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { api, PLATFORM_NAMES, PLATFORM_COLORS } from '@/api/client'
import { Activity, BellRing, ChevronRight, ExternalLink, Globe2, Loader2, LogOut, MessageCircle, RefreshCw, Send, ShieldCheck, Trash2 } from 'lucide-react'

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
  const [loginAccountId, setLoginAccountId] = useState<string | null>(null)
  const [loginAttemptId, setLoginAttemptId] = useState<string | null>(null)
  const [loginMode, setLoginMode] = useState<'electron' | 'mcp'>('electron')
  const [loginInteraction, setLoginInteraction] = useState<'qrcode' | 'verification' | 'interactive'>('interactive')
  const [syncing, setSyncing] = useState<string | null>(null)
  const [takingOver, setTakingOver] = useState<string | null>(null)
  const [notice, setNotice] = useState<{ tone: 'error' | 'warning'; message: string } | null>(null)
  const savedLogins = useRef(new Set<string>())

  const load = () => {
    api.accounts()
      .then((data) => { setAccounts(data.accounts || []); setLoading(false) })
      .catch(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  useEffect(() => {
    if (loginMode !== 'mcp' || !loginAccountId || !mOS) return
    const timer = window.setInterval(() => {
      mOS.mcpLoginStatus(loginAccountId).then((attempt) => {
        if (attempt.status === 'authenticated') {
          window.clearInterval(timer)
          if (attempt.platform) localStorage.removeItem(`mcp-pending-account:${attempt.platform}`)
          setLoggingIn(null)
          setLoginAccountId(null)
          setLoginAttemptId(null)
          load()
          return
        }
        if (attempt.status === 'timed_out' || attempt.status === 'error' || attempt.status === 'cancelled') {
          window.clearInterval(timer)
          if (attempt.status !== 'cancelled') {
            setNotice({ tone: 'error', message: attempt.status === 'timed_out' ? '登录等待超时，请重新扫码。' : (attempt.reason || 'MCP 登录窗口异常关闭。') })
          }
          setLoggingIn(null)
          setLoginAccountId(null)
          setLoginAttemptId(null)
        }
      }).catch(() => {})
    }, 2000)
    return () => window.clearInterval(timer)
  }, [loginMode, loginAccountId])

  useEffect(() => {
    if (!mOS) return
    const unsubCookies = mOS.onLoginCookies((data) => {
      if (data.count === 0) {
        setNotice({ tone: 'error', message: `没有读取到 ${PLATFORM_NAMES[data.platform]} 的登录凭据，请确认登录完成后再试。` })
        return
      }
      if (savedLogins.current.has(data.account_id)) return
      savedLogins.current.add(data.account_id)
      api.addAccount({
        account_id: data.account_id,
        platform: data.platform,
        username: data.username || `${data.platform}_session`,
        label: data.label || `${PLATFORM_NAMES[data.platform]}账号`,
      }).then((result) => {
        const payload = result as { warning?: string }
        if (payload.warning) setNotice({ tone: 'warning', message: payload.warning })
        setLoggingIn(null)
        setLoginAccountId(null)
        load()
      }).catch((reason) => {
        savedLogins.current.delete(data.account_id)
        mOS.clearAccountSession(data.platform, data.account_id).catch(() => {})
        setNotice({ tone: 'error', message: String(reason?.message || reason || '账号保存失败') })
      })
    })

    const unsubClosed = mOS.onLoginClosed?.((data: { platform: string }) => {
      setLoggingIn(null)
      setLoginAccountId(null)
    })

    const unsubError = mOS.onLoginError?.((data: { platform: string; message: string }) => {
      setNotice({ tone: 'error', message: data.message })
      setLoggingIn(null)
      setLoginAccountId(null)
    })

    const unsubInteraction = mOS.onLoginInteraction?.((data) => {
      setLoginInteraction(data.kind)
    })

    return () => {
      unsubCookies()
      unsubClosed?.()
      unsubError?.()
      unsubInteraction?.()
    }
  }, [])

  const startLogin = async (platform: string, accountId?: string) => {
    if (!mOS) return
    if (accountId) savedLogins.current.delete(accountId)
    setNotice(null)
    setLoggingIn(platform)
    setLoginAccountId(accountId || null)
    setLoginInteraction('interactive')
    try {
      if (platform === 'douyin') {
        const pendingKey = `mcp-pending-account:${platform}`
        const pendingAccountId = localStorage.getItem(pendingKey)
        const scopedAccountId = accountId || pendingAccountId || `acct_${crypto.randomUUID().replaceAll('-', '').slice(0, 12)}`
        if (!accountId) localStorage.setItem(pendingKey, scopedAccountId)
        try {
          const attempt = await mOS.mcpLoginStart(scopedAccountId, platform)
          if (attempt.status === 'browser_open' || attempt.status === 'starting') {
            setLoginMode('mcp')
            setLoginAccountId(scopedAccountId)
            setLoginAttemptId(attempt.login_attempt_id || null)
            return
          }
          throw new Error(attempt.reason || 'MCP 登录未能启动')
        } catch (mcpReason) {
          const message = String((mcpReason as Error)?.message || mcpReason || '')
          // Feature flag defaults off; preserve the proven Electron login path.
          if (!message.includes('MCP login is not enabled')) throw mcpReason
        }
      }
      setLoginMode('electron')
      const opened = await mOS.openLoginBrowser(platform, accountId)
      setLoginAccountId(opened.account_id)
    } catch (reason: unknown) {
      setLoggingIn(null)
      setLoginAccountId(null)
      setNotice({ tone: 'error', message: String((reason as Error)?.message || reason || '登录页加载失败') })
    }
  }

  const cancelLogin = () => {
    if (mOS && loggingIn) {
      if (loginMode === 'mcp' && loginAccountId) mOS.mcpLoginCancel(loginAccountId, loginAttemptId || undefined).catch(() => {})
      else mOS.closeLoginBrowser(loggingIn, loginAccountId || undefined)
    }
    setLoggingIn(null)
    setLoginAccountId(null)
    setLoginAttemptId(null)
  }

  const remove = async (account: Account) => {
    setNotice(null)
    try {
      await mOS.clearAccountSession(account.platform, account.id)
      await api.deleteAccount(account.id)
      if (localStorage.getItem('agent-active-account-id') === account.id) {
        localStorage.removeItem('agent-active-account-id')
      }
      await load()
    } catch (reason) {
      setNotice({ tone: 'error', message: String((reason as Error)?.message || reason || '账号删除失败') })
    }
  }

  const logout = async (account: Account) => {
    setNotice(null)
    try {
      await mOS.clearAccountSession(account.platform, account.id)
      await api.updateAccountStatus(account.id, 'disconnected')
      await load()
    } catch (reason) {
      setNotice({ tone: 'error', message: String((reason as Error)?.message || reason || '退出登录失败') })
    }
  }

  const sync = async (id: string) => {
    setSyncing(id)
    setNotice(null)
    try {
      const account = accounts.find((item) => item.id === id)
      if (!account || !mOS) throw new Error('账号会话不可用')
      const stats = await mOS.syncAccountSession(account.platform, account.username, account.id)
      await api.updateAccountStats(id, stats)
      await load()
    } catch (reason) {
      setNotice({ tone: 'error', message: String((reason as Error)?.message || reason || '账号指标同步失败') })
    } finally {
      setSyncing(null)
    }
  }

  const takeover = async (account: Account) => {
    if (!mOS) return
    setTakingOver(account.id)
    setNotice(null)
    try {
      await mOS.mcpBrowserTakeover(account.id)
    } catch (reason) {
      setNotice({ tone: 'error', message: String((reason as Error)?.message || reason || '无法打开账号浏览器') })
    } finally {
      setTakingOver(null)
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
          <CardContent className="login-popup-status">
            <div className="login-browser-status">
              <span className="login-live-dot" />
              <div>
                <strong>{PLATFORM_NAMES[loggingIn]} 登录窗口已打开</strong>
                <small>{loginInteraction === 'verification'
                  ? '请在登录窗口完成短信、滑块或安全验证'
                  : loginInteraction === 'qrcode'
                    ? `请在登录窗口用 ${PLATFORM_NAMES[loggingIn]} App 扫码`
                    : '请在弹出的官方页面中自行扫码登录'}</small>
              </div>
            </div>
            <div className="login-popup-actions">
              {loginMode === 'electron' && <Button variant="outline" size="sm" disabled={!loginAccountId} onClick={() => loginAccountId && mOS.navigateLoginBrowser(loggingIn, loginAccountId, 'focus')}><ExternalLink />显示登录窗口</Button>}
              <Button variant="ghost" size="sm" onClick={cancelLogin}>取消</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <NetworkDiagnostic />

      <MessagingChannels />

      {accounts.length > 0 && (
        <section className="connected-accounts">
          <div className="account-section-heading"><div><span className="page-kicker">CONNECTED</span><h2>已连接账号</h2></div><span>{accounts.filter(a => a.status === 'connected').length} 个在线 · {accounts.filter(a => a.status !== 'connected').length} 个离线</span></div>
          <div className="connected-list">
            {accounts.map((account) => (
              <div className="connected-row" key={account.id}>
                <PlatformMark platform={account.platform} />
                <div className="connected-identity"><strong>{account.label || PLATFORM_NAMES[account.platform]}</strong><span>@{account.username} · {account.id.slice(-6)}</span></div>
                <div className="account-stat"><strong>{formatMetric(account.stats?.followers)}</strong><span>粉丝</span></div>
                <div className="account-stat"><strong>{formatMetric(account.stats?.total_views)}</strong><span>近7日播放</span></div>
                <AccountHealthBadge account={account} />
                <Button variant="outline" size="sm" onClick={() => startLogin(account.platform, account.id)}>重新登录</Button>
                {account.platform === 'douyin' && <Button variant="outline" size="sm" disabled={takingOver === account.id} onClick={() => takeover(account)}>{takingOver === account.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <ExternalLink className="h-4 w-4" />}接管</Button>}
                <Button variant="ghost" size="icon" className="h-8 w-8" title="同步账号指标" disabled={syncing === account.id} onClick={() => sync(account.id)}><RefreshCw className={`h-4 w-4 text-muted-foreground ${syncing === account.id ? 'animate-spin' : ''}`} /></Button>
                {account.status === 'connected' && <Button variant="ghost" size="icon" className="h-8 w-8" title="退出登录并保留账号资料" onClick={() => logout(account)}><LogOut className="h-4 w-4 text-muted-foreground" /></Button>}
                <Button variant="ghost" size="icon" className="h-8 w-8" title="删除账号及本地登录会话" onClick={() => remove(account)}><Trash2 className="h-4 w-4 text-muted-foreground" /></Button>
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
          const connectedCount = accounts.filter((account) => account.platform === platform).length
          return (
            <button className="platform-connect-card" key={platform} disabled={disabled} onClick={() => onConnect(platform)}>
              <PlatformMark platform={platform} />
              <span className="platform-name"><strong>{PLATFORM_NAMES[platform]}</strong><small>{connectedCount ? `已连接 ${connectedCount} 个 · 添加账号` : '连接账号'}</small></span>
              <ChevronRight size={15} />
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

function AccountHealthBadge({ account }: { account: Account }) {
  const [health, setHealth] = useState<{ status: string; detail: string; checked_at?: string } | null>(null)
  const [checking, setChecking] = useState(false)

  const check = async () => {
    if (!mOS?.checkAccountHealth) return
    setChecking(true)
    try {
      setHealth(await mOS.checkAccountHealth(account.platform, account.username, account.id))
    } catch {
      setHealth({ status: 'error', detail: '检查失败' })
    } finally {
      setChecking(false)
    }
  }

  // Check on mount and when account status changes (e.g. after logout)
  useEffect(() => { check() }, [account.id, account.status])

  const config = {
    online: { color: 'border-emerald-500/30 text-emerald-500', dot: 'bg-emerald-500', label: '在线' },
    expired: { color: 'border-red-500/30 text-red-500', dot: 'bg-red-500', label: '已过期' },
    no_cookies: { color: 'border-amber-500/30 text-amber-500', dot: 'bg-amber-500', label: '未登录' },
    degraded: { color: 'border-amber-500/30 text-amber-500', dot: 'bg-amber-500', label: '异常' },
    disconnected: { color: 'border-amber-500/30 text-amber-500', dot: 'bg-amber-500', label: '未登录' },
    error: { color: 'border-red-500/30 text-red-500', dot: 'bg-red-500', label: '未知' },
  }
  // If account.status is not connected, show that immediately (don't wait for cookie check)
  const effectiveStatus = account.status === 'connected' ? (health?.status || 'checking') : account.status
  const info = config[effectiveStatus as keyof typeof config] || config.error

  return (
    <Badge variant="outline" className={`${info.color} gap-1.5 cursor-pointer`} title={health?.detail || '检查中…'} onClick={check}>
      {checking ? <Loader2 className="h-3 w-3 animate-spin" /> : <i className={`w-1.5 h-1.5 rounded-full ${info.dot}`} />}
      {effectiveStatus !== 'checking' ? info.label : '检查中'}
    </Badge>
  )
}

function NetworkDiagnostic() {
  const [results, setResults] = useState<Array<{ target: string; status: string; detail: string }> | null>(null)
  const [running, setRunning] = useState(false)

  const run = async () => {
    if (!mOS?.runNetworkDiagnostic) return
    setRunning(true)
    try {
      const data = await mOS.runNetworkDiagnostic() as { results: Array<{ target: string; status: string; detail: string }>; summary: string }
      setResults(data.results)
    } catch {
      setResults([{ target: '诊断', status: 'failed', detail: '诊断服务不可用' }])
    } finally {
      setRunning(false)
    }
  }

  useEffect(() => { run() }, [])

  if (!results) return null

  const ok = results.filter((r) => r.status === 'ok').length

  return (
    <section className="messaging-section">
      <div className="account-section-heading">
        <div><span className="page-kicker">DIAGNOSTICS</span><h2>网络诊断</h2></div>
        <Button size="sm" variant="outline" disabled={running} onClick={run}>
          {running ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : <Activity className="h-3.5 w-3.5 mr-1" />}
          {running ? '检测中' : `重新检测 · ${ok}/${results.length}`}
        </Button>
      </div>
      <div className="diagnostic-grid">
        {results.map((r) => (
          <div key={r.target} className={`diagnostic-item ${r.status}`}>
            <span className={`diagnostic-dot ${r.status}`} />
            <span className="text-xs flex-1">{r.target}</span>
            <span className="text-[10px] text-muted-foreground">{r.detail}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

function formatMetric(value: unknown) {
  const number = Number(value || 0)
  return number ? new Intl.NumberFormat('zh-CN', { notation: number >= 10000 ? 'compact' : 'standard', maximumFractionDigits: 1 }).format(number) : '--'
}
