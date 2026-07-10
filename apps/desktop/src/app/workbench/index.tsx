import { useEffect, useState } from 'react'

import { BrandMark } from '@/components/brand-mark'
import { Button } from '@/components/ui/button'
import { PRODUCT_NAME, PRODUCT_TAGLINE } from '@/product'

interface MarketingProductStatus {
  product_id: string
  product_name: string
  runtime: string
  agent_owner: string
  desktop_owner: string
  surfaces: string[]
}

interface MarketingAccountsSummary {
  accounts: Array<{ id: string; label?: string; platform?: string; username?: string }>
  total: number
  source: string
}

interface WorkbenchViewProps {
  onNewChat: () => void
  requestGateway: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
}

export function WorkbenchView({ onNewChat, requestGateway }: WorkbenchViewProps) {
  const [status, setStatus] = useState<MarketingProductStatus | null>(null)
  const [accounts, setAccounts] = useState<MarketingAccountsSummary | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true

    void requestGateway<MarketingProductStatus>('marketing.product.status')
      .then(result => {
        if (active) setStatus(result)
      })
      .catch(reason => {
        if (active) setError(reason instanceof Error ? reason.message : String(reason))
      })

    void requestGateway<MarketingAccountsSummary>('marketing.accounts.list')
      .then(result => {
        if (active) setAccounts(result)
      })
      .catch(reason => {
        if (active) setError(reason instanceof Error ? reason.message : String(reason))
      })

    return () => {
      active = false
    }
  }, [requestGateway])

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
          <Button onClick={onNewChat}>开始新对话</Button>
        </header>

        <section className="grid gap-4 md:grid-cols-3">
          <WorkbenchSignal label="智能体" value={status ? '原生运行' : '正在连接'} detail="会话、长任务、记忆和技能由同一个内核运行" />
          <WorkbenchSignal
            label="经营对象"
            value={accounts ? `${accounts.total} 个账号` : '正在读取'}
            detail={
              accounts?.accounts[0]
                ? `${accounts.accounts[0].platform || '平台'} · ${accounts.accounts[0].label || accounts.accounts[0].username || accounts.accounts[0].id}`
                : '未登录也可以先从自然对话建立目标受众和账号方向'
            }
          />
          <WorkbenchSignal label="产品界面" value="原生桌面" detail="工作台、对话和后台任务共享同一会话与运行时" />
        </section>

        <section className="rounded-2xl border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) p-7">
          <p className="text-[0.68rem] font-semibold uppercase tracking-[0.2em] text-(--ui-text-tertiary)">Today</p>
          <h2 className="mt-3 text-xl font-semibold">告诉 Agent 你想经营什么</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-(--ui-text-secondary)">
            不知道账号定位也可以直接开始。Marketing OS 会先了解你的能力、兴趣、可投入时间和目标受众，再形成第一轮可验证方向。
          </p>
          <Button className="mt-6" onClick={onNewChat} variant="outline">
            从自然对话开始
          </Button>
          {error ? <p className="mt-4 text-xs text-red-400">原生 Gateway 尚未就绪：{error}</p> : null}
        </section>
      </div>
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
