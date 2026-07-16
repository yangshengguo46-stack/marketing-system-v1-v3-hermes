import { useStore } from '@nanostores/react'
import { useEffect, useMemo } from 'react'

import { Button } from '@/components/ui/button'
import { AlertCircle, ArrowUpRight, CheckCircle2, Loader2, X } from '@/lib/icons'
import {
  $marketingOperationTasks,
  dismissMarketingOperationTask,
  type MarketingOperationTask,
  updateMarketingOperationTask
} from '@/store/marketing'

interface MarketingTaskTrayProps {
  onOpenOperation: (storedSessionId: string) => void
  requestGateway: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
}

export function MarketingTaskTray({ onOpenOperation, requestGateway }: MarketingTaskTrayProps) {
  const tasks = useStore($marketingOperationTasks)

  const pollableTasks = useMemo(
    () => tasks.filter(task => ['starting', 'waiting', 'working'].includes(task.state) && task.sessionId),
    [tasks]
  )

  const pollableSignature = pollableTasks.map(task => `${task.id}:${task.sessionId}`).join('|')

  useEffect(() => {
    if (!pollableTasks.length) {
      return
    }

    let cancelled = false

    const poll = () => {
      for (const task of pollableTasks) {
        void requestGateway<{ status?: string }>('session.status', { session_id: task.sessionId })
          .then(result => {
            if (cancelled) {
              return
            }

            if (result.status === 'idle') {
              updateMarketingOperationTask(task.id, { state: 'complete' })
            } else if (result.status === 'waiting') {
              updateMarketingOperationTask(task.id, { state: 'waiting' })
            } else if (result.status) {
              updateMarketingOperationTask(task.id, { state: 'working' })
            }
          })
          .catch(() => undefined)
      }
    }

    poll()
    const timer = window.setInterval(poll, 1800)

    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  // The signature deliberately restarts polling only when the active sessions change.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pollableSignature, requestGateway])

  const visibleTasks = tasks.slice(0, 3)

  if (!visibleTasks.length) {
    return null
  }

  return (
    <aside
      aria-label="Agent 任务"
      className="pointer-events-none fixed bottom-5 right-5 z-[70] grid w-[min(23rem,calc(100vw-2rem))] gap-2"
    >
      {visibleTasks.map(task => (
        <TaskCard key={task.id} onOpenOperation={onOpenOperation} task={task} />
      ))}
    </aside>
  )
}

function TaskCard({
  onOpenOperation,
  task
}: {
  onOpenOperation: (storedSessionId: string) => void
  task: MarketingOperationTask
}) {
  const settled = task.state === 'complete' || task.state === 'error'

  return (
    <article className="pointer-events-auto rounded-2xl border border-(--ui-stroke-secondary) bg-(--ui-sidebar-surface-background)/95 p-4 shadow-[0_18px_60px_rgba(24,20,17,0.16)] backdrop-blur-xl">
      <div className="flex items-start gap-3">
        <TaskIcon state={task.state} />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-[0.65rem] font-semibold tracking-[0.13em] text-(--ui-text-tertiary)">
                {taskStateLabel(task.state)}
              </p>
              <strong className="mt-1 block truncate text-sm">{task.title}</strong>
            </div>
            {settled ? (
              <button
                aria-label={`关闭任务 ${task.title}`}
                className="grid size-7 shrink-0 place-items-center rounded-lg text-(--ui-text-tertiary) hover:bg-(--ui-row-hover-background) hover:text-foreground"
                onClick={() => dismissMarketingOperationTask(task.id)}
                type="button"
              >
                <X className="size-3.5" />
              </button>
            ) : null}
          </div>
          <p className="mt-2 line-clamp-2 text-xs leading-5 text-(--ui-text-secondary)">
            {task.error || task.label}
          </p>
          {task.storedSessionId ? (
            <Button
              className="mt-3 h-8 rounded-full px-3 text-xs"
              onClick={() => onOpenOperation(task.storedSessionId!)}
              size="sm"
              variant="outline"
            >
              查看执行 <ArrowUpRight className="ml-1 size-3.5" />
            </Button>
          ) : null}
        </div>
      </div>
    </article>
  )
}

function TaskIcon({ state }: { state: MarketingOperationTask['state'] }) {
  if (state === 'complete') {
    return <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-emerald-600" />
  }

  if (state === 'error') {
    return <AlertCircle className="mt-0.5 size-5 shrink-0 text-red-600" />
  }

  return <Loader2 className="mt-0.5 size-5 shrink-0 animate-spin text-(--ui-accent)" />
}

function taskStateLabel(state: MarketingOperationTask['state']): string {
  return {
    complete: '已完成',
    error: '执行失败',
    starting: '正在准备',
    waiting: '等待你的决定',
    working: 'Agent 正在执行'
  }[state]
}
