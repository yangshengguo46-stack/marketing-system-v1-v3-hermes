import { useStore } from '@nanostores/react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { AlertCircle, ArrowUpRight, CheckCircle2, Loader2, X } from '@/lib/icons'
import {
  $marketingOperationTasks,
  dismissMarketingOperationTask,
  type MarketingOperationTask,
  type MarketingWorkflowProjection,
  restoreMarketingWorkflowTasks,
  updateMarketingOperationTask,
  workflowTaskState
} from '@/store/marketing'

import {
  ARTICLE_CREATION_ROUTE,
  DRAFT_BOX_ROUTE,
  MANAGED_ROUTE,
  MATERIAL_LIBRARY_ROUTE,
  VIDEO_CREATION_ROUTE,
  WORKBENCH_ROUTE
} from '../routes'

import { readMarketingOperationStatus, readMarketingWorkflow } from './operations'

interface MarketingTaskTrayProps {
  requestGateway: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
}

export function MarketingTaskTray({ requestGateway }: MarketingTaskTrayProps) {
  const tasks = useStore($marketingOperationTasks)
  const navigate = useNavigate()
  const workflowCursorRef = useRef<Record<string, number>>({})

  const pollableTasks = useMemo(
    () =>
      tasks.filter(
        task => ['starting', 'waiting', 'working'].includes(task.state) && (task.workflowId || task.operationId)
      ),
    [tasks]
  )

  const pollableSignature = pollableTasks.map(task => `${task.id}:${task.workflowId || task.operationId}`).join('|')

  useEffect(() => {
    let cancelled = false

    void requestGateway<{ workflows: MarketingWorkflowProjection[] }>('marketing.workflow.list', {
      states: ['queued', 'planning', 'running', 'waiting_approval', 'retrying', 'paused']
    })
      .then(result => {
        if (!cancelled) {
          restoreMarketingWorkflowTasks(result.workflows || [])
        }
      })
      .catch(() => undefined)

    return () => {
      cancelled = true
    }
  }, [requestGateway])

  useEffect(() => {
    if (!pollableTasks.length) {
      return
    }

    let cancelled = false

    const poll = () => {
      for (const task of pollableTasks) {
        if (task.workflowId) {
          const workflowId = task.workflowId
          const afterId = workflowCursorRef.current[workflowId] || 0

          void requestGateway<{ events: Array<{ id: number }> }>('marketing.workflow.events', {
            after_id: afterId,
            workflow_id: workflowId
          })
            .then(async eventResult => {
              if (cancelled || !eventResult.events.length) {
                return
              }

              workflowCursorRef.current[workflowId] = eventResult.events.at(-1)?.id || afterId
              const workflow = await readMarketingWorkflow(requestGateway, workflowId)

              if (cancelled) {
                return
              }

              const activeStep = workflow.steps.find(step =>
                ['leased', 'running', 'waiting_approval', 'retry_wait'].includes(step.state)
              )

              const error = workflow.error?.message || workflow.error?.code

              updateMarketingOperationTask(task.id, {
                error: error || undefined,
                label: activeStep ? `当前步骤：${activeStep.key}` : task.label,
                results: workflow.result?.results || [],
                state: workflowTaskState(workflow.state),
                title: workflow.title || task.title
              })
            })
            .catch(() => undefined)

          continue
        }

        void readMarketingOperationStatus(requestGateway, task.operationId!)
          .then(result => {
            if (cancelled) {
              return
            }

            updateMarketingOperationTask(task.id, {
              error: result.error || undefined,
              label: result.visible_text || task.label,
              results: result.results || [],
              state: result.state,
              title: result.title || task.title
            })
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
        <TaskCard
          key={task.id}
          onOpenResult={() => navigate(operationResultRoute(task))}
          requestGateway={requestGateway}
          task={task}
        />
      ))}
    </aside>
  )
}

function TaskCard({
  onOpenResult,
  requestGateway,
  task
}: {
  onOpenResult: () => void
  requestGateway: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
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
          <p className="mt-2 line-clamp-2 text-xs leading-5 text-(--ui-text-secondary)">{task.error || task.label}</p>
          {task.workflowId && task.state === 'waiting' ? (
            <WorkflowApprovalActions requestGateway={requestGateway} task={task} />
          ) : null}
          {task.workflowId && task.state === 'error' ? (
            <WorkflowRetryAction requestGateway={requestGateway} task={task} />
          ) : null}
          {task.workflowId && task.state === 'working' ? (
            <WorkflowCancelAction requestGateway={requestGateway} task={task} />
          ) : null}
          {task.operationId || task.workflowId ? (
            <Button className="mt-3 h-8 rounded-full px-3 text-xs" onClick={onOpenResult} size="sm" variant="outline">
              {task.state === 'complete' ? '查看结果' : '查看当前对象'} <ArrowUpRight className="ml-1 size-3.5" />
            </Button>
          ) : null}
        </div>
      </div>
    </article>
  )
}

interface PendingWorkflowApproval {
  id: string
  request?: Record<string, unknown>
}

function WorkflowApprovalActions({
  requestGateway,
  task
}: {
  requestGateway: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
  task: MarketingOperationTask
}) {
  const [approval, setApproval] = useState<PendingWorkflowApproval | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false

    void requestGateway<{ approvals: PendingWorkflowApproval[] }>('marketing.workflow.approvals', {
      workflow_id: task.workflowId
    })
      .then(result => {
        if (!cancelled) {
          setApproval(result.approvals[0] || null)
        }
      })
      .catch(() => undefined)

    return () => {
      cancelled = true
    }
  }, [requestGateway, task.workflowId])

  if (!approval) {
    return null
  }

  const respond = (approved: boolean) => {
    setBusy(true)
    void requestGateway('marketing.workflow.approval.respond', {
      approval_id: approval.id,
      approved,
      decision: { confirmed: approved },
      workflow_id: task.workflowId
    })
      .then(() => {
        updateMarketingOperationTask(task.id, {
          error: undefined,
          label: approved ? '审批已通过，等待下一执行 Step。' : '审批已拒绝，工作流已停止。',
          state: approved ? 'working' : 'error'
        })
      })
      .catch(reason => {
        updateMarketingOperationTask(task.id, {
          error: reason instanceof Error ? reason.message : String(reason || '审批失败')
        })
      })
      .finally(() => setBusy(false))
  }

  return (
    <div className="mt-3 rounded-xl bg-(--ui-row-hover-background) p-3">
      <p className="text-[0.7rem] leading-5 text-(--ui-text-secondary)">{approvalSummary(approval.request)}</p>
      <div className="mt-2 flex gap-2">
        <Button disabled={busy} onClick={() => respond(true)} size="sm">
          同意
        </Button>
        <Button disabled={busy} onClick={() => respond(false)} size="sm" variant="outline">
          拒绝
        </Button>
      </div>
    </div>
  )
}

function WorkflowRetryAction({
  requestGateway,
  task
}: {
  requestGateway: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
  task: MarketingOperationTask
}) {
  const [busy, setBusy] = useState(false)

  const retry = () => {
    setBusy(true)
    void readMarketingWorkflow(requestGateway, task.workflowId!)
      .then(workflow => {
        if (workflow.state === 'cancelled') {
          return requestGateway('marketing.workflow.restart', {
            confirmed: true,
            workflow_id: workflow.id
          })
        }

        const step = workflow.steps.find(item => item.state === 'failed' || item.state === 'retry_wait')

        if (!step) {
          throw new Error('当前没有可重试的 Step。')
        }

        return requestGateway('marketing.workflow.retry', {
          allow_additional_attempt: true,
          confirmed: true,
          step_id: step.id,
          workflow_id: workflow.id
        })
      })
      .then(() => {
        updateMarketingOperationTask(task.id, {
          error: undefined,
          label: '已恢复未完成节点并继续执行。',
          state: 'working'
        })
      })
      .catch(reason => {
        updateMarketingOperationTask(task.id, {
          error: reason instanceof Error ? reason.message : String(reason || '重试失败')
        })
      })
      .finally(() => setBusy(false))
  }

  return (
    <Button className="mt-3" disabled={busy} onClick={retry} size="sm" variant="outline">
      继续未完成任务
    </Button>
  )
}

function WorkflowCancelAction({
  requestGateway,
  task
}: {
  requestGateway: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
  task: MarketingOperationTask
}) {
  const [busy, setBusy] = useState(false)

  const cancel = () => {
    if (!window.confirm(`停止“${task.title}”？已完成的产物会保留。`)) {
      return
    }

    setBusy(true)
    void requestGateway('marketing.workflow.cancel', {
      confirmed: true,
      reason: '用户从 Desktop 任务托盘停止',
      workflow_id: task.workflowId
    })
      .then(() => {
        updateMarketingOperationTask(task.id, {
          error: '任务已由你停止，已完成产物仍然保留。',
          label: '任务已停止。',
          state: 'error'
        })
      })
      .catch(reason => {
        updateMarketingOperationTask(task.id, {
          error: reason instanceof Error ? reason.message : String(reason || '停止失败')
        })
      })
      .finally(() => setBusy(false))
  }

  return (
    <button
      className="mt-3 text-[0.68rem] text-(--ui-text-tertiary) hover:text-foreground"
      disabled={busy}
      onClick={cancel}
      type="button"
    >
      停止任务
    </button>
  )
}

function approvalSummary(request?: Record<string, unknown>): string {
  if (!request) {
    return '该步骤需要你的明确确认。'
  }

  for (const key of ['summary', 'message', 'title', 'effect']) {
    const value = request[key]

    if (typeof value === 'string' && value.trim()) {
      return value
    }
  }

  return '该步骤需要你的明确确认。'
}

function operationResultRoute(task: MarketingOperationTask): string {
  const result = task.results?.[0]

  if (task.kind === 'topic.production') {
    return DRAFT_BOX_ROUTE
  }

  if (task.kind.startsWith('video.')) {
    return result?.object_type === 'video_production'
      ? `${VIDEO_CREATION_ROUTE}?production=${encodeURIComponent(result.object_id)}`
      : VIDEO_CREATION_ROUTE
  }

  if (task.kind.startsWith('content.')) {
    return result?.object_type === 'content_asset'
      ? `${ARTICLE_CREATION_ROUTE}?asset=${encodeURIComponent(result.object_id)}`
      : ARTICLE_CREATION_ROUTE
  }

  if (task.kind.startsWith('materials.')) {
    return MATERIAL_LIBRARY_ROUTE
  }

  if (task.kind.startsWith('autopilot.')) {
    return MANAGED_ROUTE
  }

  return WORKBENCH_ROUTE
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
