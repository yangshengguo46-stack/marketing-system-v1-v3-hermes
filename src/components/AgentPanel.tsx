import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Check, Circle, Loader2, Pause, Play, ShieldAlert, Sparkles, X } from 'lucide-react'
import { api, agent } from '@/api/client'
import { ApprovalCard } from './ApprovalCard'

type ChatMsg = { role: 'user' | 'assistant' | 'system'; content: string }
type LiveEvent = {
  type: string
  task_id?: string
  label?: string
  detail?: unknown
  status?: string
  tool?: string
  error?: string
  reply?: string
  approval_id?: string
  capability?: string
  risk_summary?: string
  decision?: string
  arguments?: Record<string, unknown>
  plan?: PlanStep[]
  plan_step_id?: string
  plan_total?: number
  plan_version?: number
  resume_step?: string
}

const PAGE_CONTEXT: Record<string, { title: string; suggestions: string[] }> = {
  overview: { title: '今日营销建议', suggestions: ['先读取真实热点数据', '确认账号会话状态', '从真实数据生成选题'] },
  trending: { title: '趋势研判', suggestions: ['整理今天 AI 教育行业热点', '检查热点来源与采集时间', '把候选热点匹配到账号'] },
  ideas: { title: '创意策略', suggestions: ['根据真实热点生成三个选题', '解释每个选题适合哪个账号', '标出数据不足的判断'] },
  factory: { title: '制作进度', suggestions: ['查看已有内容资产', '整理待确认的制作任务', '检查 Web 工作台连接状态'] },
  publish: { title: '发布建议', suggestions: ['查看发布任务状态', '检查待确认动作', '根据真实指标安排复盘'] },
  analytics: { title: '复盘结论', suggestions: ['只根据真实指标复盘', '区分相关性和因果', '列出下一轮可验证假设'] },
  workflow: { title: '自动化状态', suggestions: ['查看最近巡检报告', '解释本次巡检失败原因', '检查下一次巡检时间'] },
  accounts: { title: '账号健康', suggestions: ['检查账号登录状态', '读取最近同步指标', '说明哪些账号需要重新授权'] },
}

export function AgentPanel({ page, status }: { page: string; status: string }) {
  const context = PAGE_CONTEXT[page] || PAGE_CONTEXT.overview
  const [message, setMessage] = useState('')
  const [history, setHistory] = useState<ChatMsg[]>([])
  const [sending, setSending] = useState(false)
  const [assistantAvailable, setAssistantAvailable] = useState(false)
  const [toolCount, setToolCount] = useState(0)
  const [liveSuggestions, setLiveSuggestions] = useState<string[]>([])
  const [liveSteps, setLiveSteps] = useState<LiveEvent[]>([])
  const [recoveredTask, setRecoveredTask] = useState<string | null>(null)
  const [pendingApprovals, setPendingApprovals] = useState<LiveEvent[]>([])
  const [plan, setPlan] = useState<PlanStep[]>([])
  const [planTotal, setPlanTotal] = useState(0)
  const [currentStepId, setCurrentStepId] = useState<string | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [activeAccountId, setActiveAccountId] = useState<string | null>(localStorage.getItem('agent-active-account-id'))
  const sessionRef = useRef<string | null>(localStorage.getItem('agent-session-id'))
  const activeTaskRef = useRef<string | null>(null)
  const streamAbortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (status !== 'ready') return
    api.assistantStatus().then(async (value) => {
      const runtime = value as { available?: boolean; tool_count?: number }
      const available = Boolean(runtime.available)
      setAssistantAvailable(available)
      setToolCount(Number(runtime.tool_count || 0))
      if (!available || !sessionRef.current) return
      try {
        const session = await agent.getSession(sessionRef.current)
        if (!session.active_task_id) return
        const task = await agent.getTaskStatus(session.active_task_id)
        if (task.status === 'paused' || task.status === 'failed') {
          setRecoveredTask(task.task_id)
          setLiveSteps([{ type: 'task.paused', task_id: task.task_id, label: '上次任务已安全暂停', status: 'paused', detail: '可从原任务继续' }])
        } else if (!['completed', 'cancelled'].includes(task.status)) {
          const controller = new AbortController()
          setSending(true)
          streamAbortRef.current = controller
          setLiveSteps([{ type: 'task.started', task_id: task.task_id, label: '任务仍在后台运行', status: 'running', detail: task.current_step || '正在恢复事件流' }])
          watchTask(task.task_id, controller).then((reply) => {
            if (reply) setHistory((current) => [...current, { role: 'assistant', content: reply }])
            setLiveSteps([])
          }).catch((reason) => {
            if ((reason as Error)?.name !== 'AbortError') {
              setHistory((current) => [...current, { role: 'system', content: `任务失败：${String((reason as Error)?.message || reason)}` }])
            }
          }).finally(() => {
            setSending(false)
            streamAbortRef.current = null
          })
        }
      } catch {
        sessionRef.current = null
        localStorage.removeItem('agent-session-id')
      }
    }).catch(() => setAssistantAvailable(false))

    api.suggestions().then((value) => {
      const list = (value as { suggestions?: Suggestion[] }).suggestions || []
      setLiveSuggestions(list.slice(0, 3).map((item) => item.angles?.[0] || item.trend))
    }).catch(() => setLiveSuggestions([]))

    api.accounts().then((value) => {
      const loaded = (value as { accounts?: Account[] }).accounts || []
      setAccounts(loaded)
      setActiveAccountId((current) => {
        if (current && loaded.some((account) => account.id === current && account.status === 'connected')) return current
        const connected = loaded.filter((account) => account.status === 'connected')
        if (connected.length === 1) {
          localStorage.setItem('agent-active-account-id', connected[0].id)
          return connected[0].id
        }
        localStorage.removeItem('agent-active-account-id')
        return null
      })
    }).catch(() => setAccounts([]))
  }, [status])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [history, liveSteps])

  useEffect(() => () => {
    const taskId = activeTaskRef.current
    if (taskId) agent.stopEventStream(taskId).catch(() => {})
  }, [])

  const handleEvent = (event: LiveEvent) => {
    if (event.type === 'step.update') {
      if (event.plan) { setPlan(event.plan); setPlanTotal(event.plan_total || 0) }
      if (event.plan_step_id) setCurrentStepId(event.plan_step_id)
      const tools = Array.isArray(event.detail)
        ? event.detail.map((item) => String((item as { name?: string }).name || '').replace('marketing_read_', '')).filter(Boolean)
        : []
      const step = {
        ...event,
        detail: tools.length ? `读取 ${tools.join('、')}` : '规划与判断中',
        status: event.status || 'running',
      }
      setLiveSteps((current) => [...current.filter((item) => item.label !== step.label), step])
    } else if (event.type === 'tool.started') {
      setLiveSteps((current) => [...current, { ...event, label: String(event.tool || '').replace('marketing_read_', ''), status: 'running' }])
    } else if (event.type === 'tool.completed') {
      setLiveSteps((current) => current.map((item) => item.tool === event.tool ? { ...item, status: 'completed' } : item))
    } else if (event.type === 'task.failed') {
      setLiveSteps((current) => [...current, { ...event, label: '任务失败', detail: event.error, status: 'failed' }])
    } else if (event.type === 'approval.requested') {
      setPendingApprovals((current) => {
        if (current.some((a) => a.approval_id === event.approval_id)) return current
        return [...current, event]
      })
    } else if (event.type === 'approval.decided') {
      if (event.approval_id && event.decision === 'rejected') {
        setPendingApprovals((current) => current.filter((a) => a.approval_id !== event.approval_id))
      }
    } else if (event.type === 'effect.executed') {
      if (event.approval_id) {
        setPendingApprovals((current) => current.filter((a) => a.approval_id !== event.approval_id))
      }
    } else if (event.type === 'plan.ready') {
      if (event.plan) {
        setPlan(event.plan)
        setPlanTotal(event.plan_total || event.plan.length)
      }
    } else if (event.type === 'plan.updated') {
      if (event.plan) {
        setPlan(event.plan)
        setPlanTotal(event.plan_total || event.plan.length)
      }
    } else if (event.type === 'task.resumed') {
      setLiveSteps([])
      if (event.plan) {
        setPlan(event.plan)
        setPlanTotal(event.plan.length)
      }
      if (event.resume_step) setCurrentStepId(event.resume_step)
    }
  }

  const watchTask = async (taskId: string, controller: AbortController) => {
    activeTaskRef.current = taskId
    return new Promise<string>((resolve, reject) => {
      let settled = false
      const finish = (result?: string, error?: Error) => {
        if (settled) return
        settled = true
        unsubscribe()
        agent.stopEventStream(taskId).catch(() => {})
        activeTaskRef.current = null
        if (error) reject(error)
        else resolve(result || '')
      }
      const unsubscribe = agent.onEvent((raw) => {
        const event = raw as LiveEvent
        if (event.task_id !== taskId) return
        handleEvent(event)
        if (event.type === 'task.completed') finish(event.reply || '')
        if (event.type === 'task.failed') finish('', new Error(event.error || '任务失败'))
        if (event.type === 'task.cancelled') finish('', new DOMException('任务已取消', 'AbortError'))
        if (event.type === 'done' && event.error) finish('', new Error(event.error))
      })
      controller.signal.addEventListener('abort', () => finish('', new DOMException('任务已取消', 'AbortError')), { once: true })
      agent.startEventStream(taskId).catch((reason: unknown) => finish('', reason instanceof Error ? reason : new Error(String(reason))))
    })
  }

  const ensureSession = async () => {
    if (sessionRef.current) return sessionRef.current
    const session = await agent.createSession()
    sessionRef.current = session.session_id
    localStorage.setItem('agent-session-id', session.session_id)
    return session.session_id
  }

  const submit = async () => {
    const value = message.trim()
    if (!value || sending || !assistantAvailable) return
    setHistory((current) => [...current, { role: 'user', content: value }])
    setMessage('')
    setSending(true)
    setLiveSteps([])
    setPlan([])
    setPlanTotal(0)
    setCurrentStepId(null)
    const controller = new AbortController()
    streamAbortRef.current = controller
    try {
      const sessionId = await ensureSession()
      const connected = accounts.filter((account) => account.status === 'connected')
      const accountSpecific = /当前账号|这个账号|该账号|抖音账号|账号数据|粉丝|点赞|播放|同步账号/.test(value)
      let resolvedAccountId = activeAccountId
      if (!resolvedAccountId && accountSpecific && connected.length === 1) {
        resolvedAccountId = connected[0].id
        setActiveAccountId(resolvedAccountId)
        localStorage.setItem('agent-active-account-id', resolvedAccountId)
      }
      if (!resolvedAccountId && accountSpecific && connected.length > 1) {
        throw new Error('这个任务需要指定账号，请先在输入框下方选择一个账号')
      }
      const result = await agent.sendMessage(sessionId, value, resolvedAccountId || undefined)
      const reply = await watchTask(result.task_id, controller)
      if (reply) setHistory((current) => [...current, { role: 'assistant', content: reply }])
      setLiveSteps([])
    } catch (reason) {
      if ((reason as Error)?.name !== 'AbortError') {
        setHistory((current) => [...current, { role: 'system', content: `任务失败：${String((reason as Error)?.message || reason)}` }])
      }
    } finally {
      setSending(false)
      streamAbortRef.current = null
    }
  }

  const resume = async () => {
    if (!recoveredTask || sending) return
    setSending(true)
    const controller = new AbortController()
    streamAbortRef.current = controller
    try {
      await agent.resumeTask(recoveredTask)
      const taskId = recoveredTask
      setRecoveredTask(null)
      const reply = await watchTask(taskId, controller)
      if (reply) setHistory((current) => [...current, { role: 'assistant', content: reply }])
      setLiveSteps([])
    } catch (reason) {
      setHistory((current) => [...current, { role: 'system', content: `恢复失败：${String((reason as Error)?.message || reason)}` }])
    } finally {
      setSending(false)
      streamAbortRef.current = null
    }
  }

  const cancel = async () => {
    const taskId = activeTaskRef.current
    if (taskId) {
      await agent.cancelTask(taskId).catch(() => {})
      await agent.stopEventStream(taskId).catch(() => {})
    }
    streamAbortRef.current?.abort()
    setSending(false)
    setLiveSteps([])
  }

  const displayedSuggestions = liveSuggestions.length ? liveSuggestions : context.suggestions
  const stepIcon = (event: LiveEvent) => {
    if (event.status === 'completed') return <Check size={11} />
    if (event.status === 'failed') return <X size={11} />
    if (event.status === 'paused') return <Pause size={11} />
    if (event.status === 'running') return <Loader2 size={11} className="animate-spin" />
    return <Circle size={10} />
  }

  return (
    <aside className="agent-panel">
      <div className="agent-header">
        <div className="agent-identity">
          <div className="agent-mark"><Sparkles size={16} /></div>
          <div><strong>Marketing Agent</strong><span><i /> {assistantAvailable ? 'Hermes 源码运行时' : '引擎未就绪'}</span></div>
        </div>
        {sending && <button className="icon-button small" onClick={cancel} title="取消任务"><X size={16} /></button>}
      </div>

      <div className="agent-scroll" ref={scrollRef}>
        {history.length === 0 && liveSteps.length === 0 && (
          <section className="agent-section">
            <div className="section-eyebrow">可以直接交代目标</div>
            <h3>{context.title}</h3>
            <div className="agent-suggestions">
              {displayedSuggestions.map((suggestion, index) => (
                <button key={suggestion} className="agent-suggestion" onClick={() => setMessage(suggestion)}>
                  <span>{String(index + 1).padStart(2, '0')}</span><p>{suggestion}</p>
                </button>
              ))}
            </div>
          </section>
        )}

        {plan.length > 0 && (
          <section className="agent-section agent-plan">
            <div className="section-row">
              <div className="section-eyebrow">
                执行计划 {plan.filter((s) => s.status === 'completed').length}/{plan.length}
              </div>
            </div>
            <div className="plan-list">
              {plan.map((step) => {
                const isCompleted = step.status === 'completed'
                const isCurrent = step.id === currentStepId || step.status === 'running'
                const isPending = step.status === 'pending'
                const isSkipped = step.status === 'skipped'
                return (
                  <div className={`plan-item ${isCompleted ? 'completed' : ''} ${isCurrent ? 'current' : ''} ${isPending || isSkipped ? 'pending' : ''}`} key={step.id}>
                    <span className="plan-number">{step.id}</span>
                    <span className="plan-description">{step.description}</span>
                    <span className="plan-status">
                      {isCompleted && <Check size={11} />}
                      {isCurrent && <Loader2 size={11} className="animate-spin" />}
                      {isPending && <Circle size={10} />}
                      {isSkipped && <span title="本次未执行">—</span>}
                    </span>
                  </div>
                )
              })}
            </div>
          </section>
        )}

        {liveSteps.length > 0 && (
          <section className="agent-section agent-progress">
            <div className="section-row"><div className="section-eyebrow">任务进度</div></div>
            <div className="task-list">
              {liveSteps.map((step, index) => (
                <div className="task-item" key={`${step.type}-${step.label}-${index}`}>
                  <span className={`task-state ${step.status || ''}`}>{stepIcon(step)}</span>
                  <span>{step.label || step.type}{typeof step.detail === 'string' && step.detail ? ` · ${step.detail}` : ''}</span>
                </div>
              ))}
            </div>
            {recoveredTask && <button className="mt-3 flex items-center gap-2 text-xs" onClick={resume}><Play size={12} />继续上次任务</button>}
          </section>
        )}

        {pendingApprovals.length > 0 && (
          <section className="agent-approvals-section">
            {pendingApprovals.map((approval) => (
              <ApprovalCard
                key={approval.approval_id || approval.label}
                approvalId={approval.approval_id || ''}
                capability={approval.capability || ''}
                args={(approval.arguments as Record<string, unknown>) || {}}
                riskSummary={approval.risk_summary || ''}
                onSettled={() => {
                  setPendingApprovals((current) =>
                    current.filter((a) => a.approval_id !== approval.approval_id)
                  )
                }}
                onClose={() => {
                  setPendingApprovals((current) =>
                    current.filter((a) => a.approval_id !== approval.approval_id)
                  )
                }}
              />
            ))}
          </section>
        )}

        {(history.length > 0 || sending) && (
          <section className="agent-reply">
            {history.map((turn, index) => turn.role === 'user'
              ? <p className="user-message" key={`${index}-${turn.content}`}>{turn.content}</p>
              : <div className="agent-message" key={`${index}-${turn.content}`}>{turn.role === 'system' ? <ShieldAlert size={14} /> : <Sparkles size={14} />}<p>{turn.content}</p></div>
            )}
            {sending && liveSteps.length === 0 && <div className="agent-message"><Sparkles size={14} /><p>正在理解目标…</p></div>}
          </section>
        )}
      </div>

      <div className="agent-composer">
        <textarea value={message} onChange={(event) => setMessage(event.target.value)} onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit() }
        }} placeholder="告诉 Agent 你想完成什么..." rows={3} disabled={!assistantAvailable || sending} />
        <div className="composer-footer">
          <div style={{display:'flex',alignItems:'center',gap:6}}>
            <span>{assistantAvailable ? `${toolCount} 工具在线` : 'Hermes 不可用'}</span>
            {accounts.length > 0 && (
              <select
                className="account-select"
                value={activeAccountId || ''}
                onChange={(e) => {
                  const value = e.target.value || null
                  setActiveAccountId(value)
                  if (value) localStorage.setItem('agent-active-account-id', value)
                  else localStorage.removeItem('agent-active-account-id')
                }}
                style={{background:'rgba(255,255,255,.04)',border:'1px solid rgba(255,255,255,.08)',borderRadius:5,color:'rgba(255,255,255,.5)',fontSize:8,padding:'2px 6px',outline:'none',maxWidth:100}}
              >
                <option value="">全部账号</option>
                {accounts.filter((a) => a.status === 'connected').map((a) => (
                  <option key={a.id} value={a.id}>{a.label || a.username} · {a.id.slice(-6)}</option>
                ))}
              </select>
            )}
          </div>
          <button onClick={submit} disabled={!message.trim() || !assistantAvailable || sending} title="发送"><ArrowUp size={16} /></button>
        </div>
      </div>
    </aside>
  )
}
