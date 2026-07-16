import { useStore } from '@nanostores/react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { AlertCircle, CheckCircle2, CircleIcon, Loader2, SteeringWheel, Users } from '@/lib/icons'
import { $marketingJourneyGoalDraft, $marketingOperationTasks, type MarketingAccountSummary } from '@/store/marketing'

import type { StartMarketingOperation } from './operations'

interface FirstRunJourneyProps {
  accounts: MarketingAccountSummary[]
  businessGoal?: string
  hasFirstAsset: boolean
  hasFirstDecision: boolean
  onOpenAccounts: () => void
  onReviewFirstAsset: () => void
  onSelectAccount: (accountId: string) => void
  onStartOperation: StartMarketingOperation
  selectedAccountId: string
}

const JOURNEY_STEPS = ['经营目标', '真实研究', '首个经营对象', '你的第一次决定']

export function FirstRunJourney({
  accounts,
  businessGoal,
  hasFirstAsset,
  hasFirstDecision,
  onOpenAccounts,
  onReviewFirstAsset,
  onSelectAccount,
  onStartOperation,
  selectedAccountId
}: FirstRunJourneyProps) {
  const goal = useStore($marketingJourneyGoalDraft)
  const tasks = useStore($marketingOperationTasks)
  const [error, setError] = useState('')
  const task = tasks.find(item => item.accountId === selectedAccountId && item.kind === 'account.bootstrap') || null
  const running = Boolean(task && ['starting', 'waiting', 'working'].includes(task.state))
  const connected = accounts.filter(account => account.auth_state === 'authenticated')

  const startGoal = (value: string) => {
    const normalized = value.trim()

    if (normalized.length < 6) {
      setError('请用一句话说清楚你想经营成什么，至少输入 6 个字。')

      return
    }

    setError('')
    onStartOperation({
      accountId: selectedAccountId || 'prospect_default',
      businessGoal: normalized,
      kind: 'account.bootstrap',
      title: '首次经营研究'
    })
  }

  const startJourney = () => startGoal(goal)

  if (businessGoal) {
    const researchComplete = task?.state === 'complete' || hasFirstAsset

    return (
      <section className="mt-6 overflow-hidden rounded-[28px] border border-(--ui-stroke-secondary) bg-(--ui-sidebar-surface-background) shadow-[0_22px_65px_rgba(42,34,27,0.07)]">
        <div className="grid gap-7 p-7 lg:grid-cols-[minmax(0,1fr)_minmax(20rem,0.72fr)] lg:p-9">
          <div>
            <p className="text-xs font-semibold tracking-[0.14em] text-(--ui-accent)">首次经营闭环正在形成</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-[-0.045em]">{businessGoal}</h2>
            <p className="mt-3 text-sm leading-7 text-(--ui-text-secondary)">
              目标、研究、内容资产和你的决定都留在这条经营链上。页面切换不会中断 Agent。
            </p>
            {task ? (
              <div
                className="mt-6 flex items-start gap-3 rounded-2xl border border-(--ui-stroke-tertiary) bg-(--ui-fill-primary)/45 p-4"
                role="status"
              >
                {task.state === 'complete' ? (
                  <CheckCircle2 className="mt-0.5 size-4 text-emerald-600" />
                ) : task.state === 'error' ? (
                  <AlertCircle className="mt-0.5 size-4 text-red-600" />
                ) : (
                  <Loader2 className="mt-0.5 size-4 animate-spin text-(--ui-accent)" />
                )}
                <div>
                  <strong className="text-sm">{task.title}</strong>
                  <p className="mt-1 text-xs leading-5 text-(--ui-text-tertiary)">{task.error || task.label}</p>
                </div>
              </div>
            ) : null}
            {hasFirstAsset && !hasFirstDecision ? (
              <Button className="mt-6" onClick={onReviewFirstAsset}>
                审阅第一个经营对象
              </Button>
            ) : null}
            {!hasFirstAsset && !running ? (
              <Button className="mt-6" onClick={() => startGoal(businessGoal)} variant="outline">
                {task?.state === 'error' ? '重新启动首次研究' : '继续形成首个经营对象'}
              </Button>
            ) : null}
          </div>
          <ol className="space-y-5 border-t border-(--ui-stroke-tertiary) pt-6 lg:border-l lg:border-t-0 lg:pl-7 lg:pt-0">
            {JOURNEY_STEPS.map((step, index) => {
              const completed =
                index === 0 ||
                (index === 1 && researchComplete) ||
                (index === 2 && hasFirstAsset) ||
                (index === 3 && hasFirstDecision)

              const active =
                !completed &&
                ((index === 1 && !researchComplete) ||
                  (index === 2 && researchComplete) ||
                  (index === 3 && hasFirstAsset))

              return (
                <li className="flex items-start gap-3" key={step}>
                  {completed ? (
                    <CheckCircle2 className="mt-0.5 size-4 text-emerald-600" />
                  ) : active && running ? (
                    <Loader2 className="mt-0.5 size-4 animate-spin text-(--ui-accent)" />
                  ) : (
                    <CircleIcon className="mt-0.5 size-4 text-(--ui-text-quaternary)" />
                  )}
                  <strong className="text-sm">{step}</strong>
                </li>
              )
            })}
          </ol>
        </div>
      </section>
    )
  }

  return (
    <section className="mt-6 overflow-hidden rounded-[28px] border border-(--ui-stroke-secondary) bg-(--ui-sidebar-surface-background) shadow-[0_22px_65px_rgba(42,34,27,0.07)]">
      <div className="grid lg:grid-cols-[minmax(0,1.2fr)_minmax(20rem,0.8fr)]">
        <div className="p-7 lg:p-9">
          <p className="text-xs font-semibold tracking-[0.14em] text-(--ui-accent)">首个半小时</p>
          <h2 className="mt-3 text-2xl font-semibold tracking-[-0.045em]">先完成第一条真实经营闭环</h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-(--ui-text-secondary)">
            选择经营对象并说出目标。Agent 会立即开始研究，运行状态和产物会一直留在工作台，不会把你带去一段陌生对话。
          </p>

          <div className="mt-7">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <label className="text-xs font-semibold" htmlFor="marketing-first-goal">
                1. 选择账号，或者暂不登录
              </label>
              <Button onClick={onOpenAccounts} size="sm" variant="ghost">
                管理账号
              </Button>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <AccountChoice
                active={selectedAccountId.startsWith('prospect_') || !selectedAccountId}
                label="暂不登录，先从目标开始"
                onClick={() => onSelectAccount('prospect_default')}
              />
              {connected.map(account => (
                <AccountChoice
                  active={selectedAccountId === account.id}
                  key={account.id}
                  label={account.label || account.username || account.id}
                  onClick={() => onSelectAccount(account.id)}
                />
              ))}
            </div>
          </div>

          <div className="mt-6">
            <label className="text-xs font-semibold" htmlFor="marketing-first-goal">
              2. 说出你真正想实现的经营目标
            </label>
            <Textarea
              className="mt-3 min-h-28 resize-y"
              disabled={running}
              id="marketing-first-goal"
              onChange={event => $marketingJourneyGoalDraft.set(event.target.value)}
              placeholder="例如：未来 30 天验证 AI 教育这个方向，找到第一批愿意持续关注并付费的目标用户。"
              value={goal}
            />
            {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}
          </div>

          <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
            <span className="text-xs text-(--ui-text-tertiary)">
              点击一次就会启动，不会再让你确认或发送预设提示词。
            </span>
            <Button disabled={running} onClick={startJourney}>
              {running ? <Loader2 className="size-4 animate-spin" /> : <SteeringWheel className="size-4" />}
              {running ? 'Agent 正在研究' : '开始经营'}
            </Button>
          </div>
        </div>

        <aside className="border-t border-(--ui-stroke-tertiary) bg-(--ui-fill-primary)/55 p-7 lg:border-l lg:border-t-0 lg:p-9">
          <span className="text-[0.66rem] font-semibold tracking-[0.14em] text-(--ui-text-tertiary)">
            接下来会发生什么
          </span>
          <ol className="mt-5 space-y-5">
            {JOURNEY_STEPS.map((step, index) => {
              const completed = task?.state === 'complete' || (index === 0 && goal.trim().length >= 6)
              const active = Boolean(task && ['starting', 'waiting', 'working'].includes(task.state) && index === 1)

              return (
                <li className="flex items-start gap-3" key={step}>
                  {completed ? (
                    <CheckCircle2 className="mt-0.5 size-4 text-emerald-600" />
                  ) : active ? (
                    <Loader2 className="mt-0.5 size-4 animate-spin text-(--ui-accent)" />
                  ) : (
                    <CircleIcon className="mt-0.5 size-4 text-(--ui-text-quaternary)" />
                  )}
                  <div>
                    <strong className="block text-sm">{step}</strong>
                    {active ? (
                      <span className="mt-1 block text-xs text-(--ui-text-tertiary)">{task?.label}</span>
                    ) : null}
                  </div>
                </li>
              )
            })}
          </ol>
          <div className="mt-7 flex gap-3 rounded-2xl border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) p-4">
            <Users className="mt-0.5 size-4 text-(--ui-accent)" />
            <p className="text-xs leading-5 text-(--ui-text-secondary)">
              发布、付费和长期策略变化仍然会停下来等你确认；研究与低风险整理会持续推进。
            </p>
          </div>
        </aside>
      </div>
    </section>
  )
}

function AccountChoice({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      aria-pressed={active}
      className={`rounded-full border px-3.5 py-2 text-xs transition-colors ${active ? 'border-(--ui-accent) bg-(--ui-accent)/8 text-foreground' : 'border-(--ui-stroke-tertiary) text-(--ui-text-secondary) hover:bg-(--ui-fill-secondary)'}`}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  )
}
