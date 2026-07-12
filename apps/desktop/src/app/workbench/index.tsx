import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useState } from 'react'

import { BrandMark } from '@/components/brand-mark'
import { Button } from '@/components/ui/button'
import { Plus } from '@/lib/icons'
import { PRODUCT_NAME, PRODUCT_TAGLINE } from '@/product'
import {
  $selectedMarketingAccountId,
  type MarketingAccountSummary,
  type MarketingPlatformSummary,
  selectMarketingAccount,
  setMarketingAccounts
} from '@/store/marketing'

import { AccountConnectDialog, MarketingPlatformAvatar } from './account-connect-dialog'

interface MarketingProductStatus {
  product_id: string
  product_name: string
  runtime: string
  architecture: string
  surfaces: string[]
  enhancements: string[]
}

interface MarketingAccountsSummary {
  accounts: MarketingAccountSummary[]
  total: number
  source: string
}

interface MarketingPlatformsSummary {
  platforms: MarketingPlatformSummary[]
  total: number
}

interface WorkbenchViewProps {
  onNewChat: () => void
  requestGateway: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
}

export function WorkbenchView({ onNewChat, requestGateway }: WorkbenchViewProps) {
  const [status, setStatus] = useState<MarketingProductStatus | null>(null)
  const [accounts, setAccounts] = useState<MarketingAccountsSummary | null>(null)
  const [platforms, setPlatforms] = useState<MarketingPlatformSummary[]>([])
  const [connectOpen, setConnectOpen] = useState(false)
  const [resumeAccount, setResumeAccount] = useState<MarketingAccountSummary | null>(null)
  const [error, setError] = useState('')
  const selectedAccountId = useStore($selectedMarketingAccountId)

  const startForAccount = (accountId: string) => {
    selectMarketingAccount(accountId)
    onNewChat()
  }

  const applyAccounts = useCallback((result: MarketingAccountsSummary) => {
    setAccounts(result)
    setMarketingAccounts(result.accounts)
  }, [])

  const refreshAccounts = useCallback(async () => {
    const result = await requestGateway<MarketingAccountsSummary>('marketing.accounts.list')
    applyAccounts(result)
  }, [applyAccounts, requestGateway])

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

  useEffect(() => {
    let active = true

    void requestGateway<MarketingProductStatus>('marketing.product.status')
      .then(result => {
        if (active) {
          setStatus(result)
        }
      })
      .catch(reason => {
        if (active) {
          setError(reason instanceof Error ? reason.message : String(reason))
        }
      })

    void requestGateway<MarketingAccountsSummary>('marketing.accounts.list')
      .then(result => {
        if (active) {
          applyAccounts(result)
        }
      })

    void requestGateway<MarketingPlatformsSummary>('marketing.accounts.platforms')
      .then(result => {
        if (active) {setPlatforms(result.platforms)}
      })
      .catch(reason => {
        if (active) {setError(reason instanceof Error ? reason.message : String(reason))}
      })
      .catch(reason => {
        if (active) {
          setError(reason instanceof Error ? reason.message : String(reason))
        }
      })

    return () => {
      active = false
    }
  }, [applyAccounts, requestGateway])

  return (
    <main className="h-full overflow-y-auto bg-(--ui-background) px-10 pb-16 pt-[calc(var(--titlebar-height)+2.5rem)] text-foreground">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-10">
        <header className="flex items-center justify-between gap-8 border-b border-(--ui-stroke-tertiary) pb-8">
          <div className="flex min-w-0 items-center gap-4">
            <BrandMark className="size-12 text-4xl" />
            <div>
              <p className="text-[0.68rem] font-semibold uppercase tracking-[0.24em] text-(--ui-text-tertiary)">
                Native agent workspace
              </p>
              <h1 className="mt-1 text-3xl font-semibold tracking-[-0.04em]">{PRODUCT_NAME}</h1>
              <p className="mt-1 text-sm text-(--ui-text-secondary)">{PRODUCT_TAGLINE}</p>
            </div>
          </div>
          <Button onClick={() => startForAccount(selectedAccountId || accounts?.accounts[0]?.id || 'prospect_default')}>
            开始新对话
          </Button>
        </header>

        <section className="grid gap-4 md:grid-cols-3">
          <WorkbenchSignal
            detail="会话、长任务、记忆和技能由同一个内核运行"
            label="智能体"
            value={status ? '原生运行' : '正在连接'}
          />
          <article className="min-h-40 rounded-2xl border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) p-6">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-xs text-(--ui-text-tertiary)">经营对象</p>
                <strong className="mt-5 block text-xl font-semibold tracking-[-0.03em]">
                  {accounts ? `${accounts.total} 个账号` : '正在读取'}
                </strong>
              </div>
              <Button aria-label="连接平台账号" onClick={() => openAccountConnect()} size="icon-sm" variant="outline">
                <Plus className="size-4" />
              </Button>
            </div>
            <div className="mt-4 flex flex-col gap-2">
              {accounts?.accounts.map(account => (
                <button
                  className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-left text-xs transition-colors ${
                    selectedAccountId === account.id
                      ? 'border-(--ui-accent) bg-(--ui-accent)/10 text-foreground'
                      : 'border-(--ui-stroke-tertiary) text-(--ui-text-secondary) hover:text-foreground'
                  }`}
                  key={account.id}
                  onClick={() =>
                    account.auth_state === 'authenticated' ? startForAccount(account.id) : openAccountConnect(account)
                  }
                  type="button"
                >
                  <MarketingPlatformAvatar platform={account.platform || ''} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-foreground">
                      {account.label || account.username || account.id}
                    </span>
                    <span className="mt-0.5 block text-[0.68rem] text-(--ui-text-tertiary)">
                      {account.auth_state === 'authenticated' ? '已连接 · 点击开始工作' : '等待登录 · 点击继续'}
                    </span>
                  </span>
                </button>
              ))}
              {accounts?.total === 0 ? (
                <button
                  className="rounded-full border border-(--ui-stroke-tertiary) px-3 py-1.5 text-xs text-(--ui-text-secondary) hover:text-foreground"
                  onClick={() => startForAccount('prospect_default')}
                  type="button"
                >
                  先聊方向，不登录账号
                </button>
              ) : null}
            </div>
          </article>
          <WorkbenchSignal detail="工作台、对话和后台任务共享同一会话与运行时" label="产品界面" value="原生桌面" />
        </section>

        <section className="rounded-2xl border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) p-7">
          <p className="text-[0.68rem] font-semibold uppercase tracking-[0.2em] text-(--ui-text-tertiary)">Today</p>
          <h2 className="mt-3 text-xl font-semibold">告诉 Agent 你想经营什么</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-(--ui-text-secondary)">
            不知道账号定位也可以直接开始。Marketing OS
            会先了解你的能力、兴趣、可投入时间和目标受众，再形成第一轮可验证方向。
          </p>
          <Button className="mt-6" onClick={() => startForAccount('prospect_default')} variant="outline">
            从自然对话开始
          </Button>
          {error ? <p className="mt-4 text-xs text-red-400">原生 Gateway 尚未就绪：{error}</p> : null}
        </section>
      </div>
      <AccountConnectDialog
        onAccountChanged={handleAccountChanged}
        onOpenChange={setConnectOpen}
        open={connectOpen}
        platforms={platforms}
        requestGateway={requestGateway}
        resumeAccount={resumeAccount}
      />
    </main>
  )
}

function WorkbenchSignal({ detail, label, value }: { detail: string; label: string; value: string }) {
  return (
    <article className="min-h-40 rounded-2xl border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) p-6">
      <p className="text-xs text-(--ui-text-tertiary)">{label}</p>
      <strong className="mt-5 block text-xl font-semibold tracking-[-0.03em]">{value}</strong>
      <p className="mt-3 text-sm leading-6 text-(--ui-text-secondary)">{detail}</p>
    </article>
  )
}
