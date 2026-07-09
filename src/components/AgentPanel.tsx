import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Check, ChevronDown, Circle, Loader2, Pause, Play, ShieldAlert, Sparkles, X } from 'lucide-react'
import { api, agent } from '@/api/client'
import { ApprovalCard } from './ApprovalCard'
import { creativeBriefToPrompt } from '@/lib/creativeBrief'

type ChatMsg = { role: 'user' | 'assistant' | 'system'; content: string; task_id?: string }
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
  chat: { title: '新对话', suggestions: ['帮我分析今天适合做什么内容', '基于账号画像做一次起号规划', '检查热点和选题证据是否可靠'] },
  trending: { title: '趋势研判', suggestions: ['整理今天 AI 教育行业热点', '检查热点来源与采集时间', '把候选热点匹配到账号'] },
  ideas: { title: '创意策略', suggestions: ['根据真实热点生成三个选题', '解释每个选题适合哪个账号', '标出数据不足的判断'] },
  factory: { title: '制作进度', suggestions: ['查看已有内容资产', '整理待确认的制作任务', '检查 Web 工作台连接状态'] },
  analytics: { title: '复盘结论', suggestions: ['只根据真实指标复盘', '区分相关性和因果', '列出下一轮可验证假设'] },
  workflow: { title: '自动化状态', suggestions: ['查看最近巡检报告', '解释本次巡检失败原因', '检查下一次巡检时间'] },
  accounts: { title: '账号健康', suggestions: ['检查账号登录状态', '读取最近同步指标', '说明哪些账号需要重新授权'] },
}

function inlineText(text: string) {
  const clean = text.replace(/`([^`]+)`/g, '$1')
  const chunks = clean.split(/(\*\*[^*]+\*\*)/g).filter(Boolean)
  return chunks.map((chunk, index) => {
    if (chunk.startsWith('**') && chunk.endsWith('**')) {
      return <strong key={`${chunk}-${index}`}>{chunk.slice(2, -2)}</strong>
    }
    return <span key={`${chunk}-${index}`}>{chunk}</span>
  })
}

function AgentMessageContent({ content }: { content: string }) {
  const lines = content
    .replace(/\r\n/g, '\n')
    .split('\n')
    .map((line) => line.trim())
  const blocks: Array<{ type: 'heading' | 'list' | 'paragraph' | 'table'; text?: string; items?: string[]; rows?: string[][] }> = []
  let list: string[] = []
  let table: string[][] = []
  const flushList = () => {
    if (list.length) blocks.push({ type: 'list', items: list.splice(0) })
  }
  const flushTable = () => {
    if (table.length) blocks.push({ type: 'table', rows: table.splice(0) })
  }
  for (const raw of lines) {
    const line = raw.replace(/^[-—]{3,}\s*/, '').trim()
    if (!line) { flushList(); flushTable(); continue }
    if (/^\|.+\|$/.test(line)) {
      flushList()
      const cells = line.split('|').map((cell) => cell.trim()).filter(Boolean)
      if (!cells.every((cell) => /^:?-{2,}:?$/.test(cell))) table.push(cells)
      continue
    }
    flushTable()
    const heading = line.match(/^#{1,6}\s+(.+)/)
    if (heading) { flushList(); blocks.push({ type: 'heading', text: heading[1] }); continue }
    const item = line.match(/^(\d+[.)]|[-*•])\s+(.+)/)
    if (item) { list.push(item[2]); continue }
    flushList()
    blocks.push({ type: 'paragraph', text: line })
  }
  flushList()
  flushTable()
  return (
    <div className="agent-message-content">
      {blocks.map((block, index) => {
        if (block.type === 'heading') return <h4 key={index}>{inlineText(block.text || '')}</h4>
        if (block.type === 'list') return <ul key={index}>{block.items!.map((item, i) => <li key={`${item}-${i}`}>{inlineText(item)}</li>)}</ul>
        if (block.type === 'table') return (
          <div className="agent-mini-table" key={index}>
            {block.rows!.slice(0, 8).map((row, rowIndex) => (
              <div key={rowIndex}>{row.slice(0, 4).map((cell, cellIndex) => <span key={cellIndex}>{inlineText(cell)}</span>)}</div>
            ))}
          </div>
        )
        return <p key={index}>{inlineText(block.text || '')}</p>
      })}
    </div>
  )
}

export function AgentPanel({ page, status, sessionId, newChatToken = 0, initialPrompt = '', creativeBrief = null, onSessionChange, onSessionsChanged }: {
  page: string
  status: string
  sessionId?: string | null
  newChatToken?: number
  initialPrompt?: string
  creativeBrief?: CreativeBrief | null
  onSessionChange?: (id: string) => void
  onSessionsChanged?: () => void
}) {
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
  const [thinkingExpanded, setThinkingExpanded] = useState(false)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [activeAccountId, setActiveAccountId] = useState<string | null>(localStorage.getItem('agent-active-account-id'))
  const sessionRef = useRef<string | null>(sessionId || null)
  const activeTaskRef = useRef<string | null>(null)
  const streamAbortRef = useRef<AbortController | null>(null)
  const locallyCreatedSessionRef = useRef<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  const resetRuntimeState = () => {
    setLiveSteps([])
    setPendingApprovals([])
    setPlan([])
    setPlanTotal(0)
    setCurrentStepId(null)
    setRecoveredTask(null)
  }

  const detachActiveEventStream = (updateState = true) => {
    const taskId = activeTaskRef.current
    streamAbortRef.current?.abort()
    streamAbortRef.current = null
    activeTaskRef.current = null
    if (taskId) agent.stopEventStream(taskId).catch(() => {})
    if (updateState) setSending(false)
  }

  const normalizeMessages = (messages: AgentChatMessage[] = []): ChatMsg[] => messages.map((item) => ({
    role: item.role,
    content: item.content,
    task_id: item.task_id,
  }))

  const reloadSessionHistory = async (targetSessionId: string) => {
    const result = await agent.getSessionMessages(targetSessionId)
    const next = normalizeMessages(result.messages || [])
    if (sessionRef.current === targetSessionId) setHistory(next)
    return next
  }

  useEffect(() => {
    if (!window.marketingOS) return
    let cancelled = false
    const loadRuntime = async () => {
      try {
        const runtime = await api.assistantStatus() as { available?: boolean; tool_count?: number }
        if (cancelled) return
        const available = Boolean(runtime.available)
        setAssistantAvailable(available)
        setToolCount(Number(runtime.tool_count || 0))
        if (available && sessionRef.current) attachActiveSessionTask(sessionRef.current)
      } catch {
        if (!cancelled) setAssistantAvailable(false)
      }

      api.suggestions().then((value) => {
        if (cancelled) return
        const list = (value as { suggestions?: Suggestion[] }).suggestions || []
        setLiveSuggestions(list.slice(0, 3).map((item) => item.angles?.[0] || item.trend))
      }).catch(() => {
        if (!cancelled) setLiveSuggestions([])
      })

      api.accounts().then((value) => {
        if (cancelled) return
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
      }).catch(() => {
        if (!cancelled) setAccounts([])
      })
    }
    loadRuntime()
    const retry = window.setInterval(loadRuntime, 5000)
    return () => {
      cancelled = true
      window.clearInterval(retry)
    }
  }, [])

  useEffect(() => {
    const locallyCreated = sessionId && locallyCreatedSessionRef.current === sessionId
    if (locallyCreated) {
      locallyCreatedSessionRef.current = null
      sessionRef.current = sessionId
      return
    }
    detachActiveEventStream()
    sessionRef.current = sessionId || null
    setHistory([])
    resetRuntimeState()
    if (!sessionId) return
    let cancelled = false
    agent.getSessionMessages(sessionId)
      .then((result) => {
        if (cancelled) return
        setHistory(normalizeMessages(result.messages || []))
      })
      .catch(() => {
        if (!cancelled) setHistory([{ role: 'system', content: '历史会话加载失败' }])
      })
      .finally(() => {
        if (!cancelled) attachActiveSessionTask(sessionId)
      })
    return () => { cancelled = true }
  }, [sessionId, status])

  useEffect(() => {
    if (sessionId) return
    detachActiveEventStream()
    sessionRef.current = null
    setHistory([])
    setMessage(creativeBrief ? creativeBriefToPrompt(creativeBrief) : initialPrompt)
    resetRuntimeState()
  }, [newChatToken, sessionId, initialPrompt, creativeBrief])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [history, liveSteps])

  useEffect(() => () => {
    detachActiveEventStream(false)
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
      let pollBusy = false
      let pollTimer: number | null = null
      const finish = (result?: string, error?: Error) => {
        if (settled) return
        settled = true
        if (pollTimer) window.clearInterval(pollTimer)
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
      pollTimer = window.setInterval(async () => {
        if (settled || pollBusy) return
        pollBusy = true
        try {
          const task = await agent.getTaskStatus(taskId)
          if (task.status === 'completed') finish('')
          if (task.status === 'failed') finish('', new Error(task.last_error || '任务失败'))
          if (task.status === 'cancelled') finish('', new DOMException('任务已取消', 'AbortError'))
        } catch {
          // Keep the SSE path alive; transient polling failures should not kill the run.
        } finally {
          pollBusy = false
        }
      }, 1500)
      controller.signal.addEventListener('abort', () => finish('', new DOMException('任务已取消', 'AbortError')), { once: true })
      agent.startEventStream(taskId).catch((reason: unknown) => finish('', reason instanceof Error ? reason : new Error(String(reason))))
    })
  }

  const attachActiveSessionTask = async (targetSessionId: string) => {
    if (activeTaskRef.current) return
    try {
      const session = await agent.getSession(targetSessionId)
      if (sessionRef.current !== targetSessionId || !session.active_task_id) return
      const task = await agent.getTaskStatus(session.active_task_id)
      if (task.status === 'paused' || task.status === 'failed') {
        setRecoveredTask(task.task_id)
        setLiveSteps([{ type: 'task.paused', task_id: task.task_id, label: '上次任务已安全暂停', status: 'paused', detail: '可从原任务继续' }])
        return
      }
      if (['completed', 'cancelled'].includes(task.status)) return
      const controller = new AbortController()
      setSending(true)
      streamAbortRef.current = controller
      setLiveSteps([{ type: 'task.started', task_id: task.task_id, label: '任务仍在后台运行', status: 'running', detail: task.current_step || '正在恢复事件流' }])
      watchTask(task.task_id, controller)
        .then((reply) => {
          reloadSessionHistory(targetSessionId).catch(() => {
            if (reply) setHistory((current) => [...current, { role: 'assistant', content: reply, task_id: task.task_id }])
          })
          setLiveSteps([])
          onSessionsChanged?.()
        })
        .catch((reason) => {
          if ((reason as Error)?.name !== 'AbortError') {
            setHistory((current) => [...current, { role: 'system', content: `任务失败：${String((reason as Error)?.message || reason)}` }])
          }
        })
        .finally(() => {
          setSending(false)
          streamAbortRef.current = null
        })
    } catch {
      if (sessionRef.current === targetSessionId) sessionRef.current = null
    }
  }

  const ensureSession = async () => {
    if (sessionRef.current) return sessionRef.current
    const session = await agent.createSession(undefined, `chat:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`)
    sessionRef.current = session.session_id
    locallyCreatedSessionRef.current = session.session_id
    onSessionChange?.(session.session_id)
    return session.session_id
  }

  const submit = async () => {
    const value = message.trim()
    if (!value || !assistantAvailable) return
    setMessage('')

    // If a task is currently running, treat the new message as a replan request
    if (sending && activeTaskRef.current) {
      const taskId = activeTaskRef.current
      setHistory((current) => [...current, { role: 'user', content: value }])
      try {
        // Abort the old event stream first
        streamAbortRef.current?.abort()
        streamAbortRef.current = null
        const result = await agent.replanTask(taskId, value)
        if (result.status === 'completed') {
          // Task already finished before replan could interrupt — send as new message instead
          setHistory((current) => [...current, { role: 'system', content: `原任务已完成，正在用新目标重新开始…` }])
          setSending(false)
          activeTaskRef.current = null
          // Send as a fresh message by calling submit logic directly
          const sessionId = await ensureSession()
          setSending(true)
          setLiveSteps([])
          setPlan([])
          setPlanTotal(0)
          setCurrentStepId(null)
          const controller2 = new AbortController()
          streamAbortRef.current = controller2
          const result2 = await agent.sendMessage(sessionId, value, activeAccountId || undefined)
          onSessionsChanged?.()
          setLiveSteps((current) => [...current, { type: 'task.accepted', task_id: result2.task_id, label: '后端已接管', status: 'running', detail: `任务 ${result2.task_id.slice(-8)}` }])
          const reply2 = await watchTask(result2.task_id, controller2)
          await reloadSessionHistory(sessionId).catch(() => {
            if (reply2) setHistory((current) => [...current, { role: 'assistant', content: reply2, task_id: result2.task_id }])
          })
          setLiveSteps([])
        } else {
          setHistory((current) => [...current, { role: 'system', content: `目标已修改为：${result.objective}。已完成步骤已保留，正在用新目标继续执行…` }])
          // Resume the task with the new objective
          await agent.resumeTask(taskId)
          setLiveSteps([])
          const controller = new AbortController()
          streamAbortRef.current = controller
          const reply = await watchTask(taskId, controller)
          const currentSession = sessionRef.current
          if (currentSession) {
            await reloadSessionHistory(currentSession).catch(() => {
              if (reply) setHistory((current) => [...current, { role: 'assistant', content: reply, task_id: taskId }])
            })
          } else if (reply) {
            setHistory((current) => [...current, { role: 'assistant', content: reply, task_id: taskId }])
          }
          setLiveSteps([])
        }
      } catch (reason) {
        if ((reason as Error)?.name !== 'AbortError') {
          setHistory((current) => [...current, { role: 'system', content: `修改目标失败：${String((reason as Error)?.message || reason)}` }])
        }
      } finally {
        setSending(false)
        streamAbortRef.current = null
      }
      return
    }

    setHistory((current) => [...current, { role: 'user', content: value }])
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
      const accountSpecific = /当前账号|这个账号|该账号|抖音账号|账号数据|粉丝|点赞|播放|同步账号|粉丝画像|实验结果|实际粉丝|发布结果/.test(value)
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
      onSessionsChanged?.()
      setLiveSteps((current) => [...current, { type: 'task.accepted', task_id: result.task_id, label: '后端已接管', status: 'running', detail: `任务 ${result.task_id.slice(-8)}` }])
      const reply = await watchTask(result.task_id, controller)
      await reloadSessionHistory(sessionId).catch(() => {
        if (reply) setHistory((current) => [...current, { role: 'assistant', content: reply, task_id: result.task_id }])
      })
      onSessionsChanged?.()
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
      const currentSession = sessionRef.current
      if (currentSession) {
        await reloadSessionHistory(currentSession).catch(() => {
          if (reply) setHistory((current) => [...current, { role: 'assistant', content: reply, task_id: taskId }])
        })
      } else if (reply) {
        setHistory((current) => [...current, { role: 'assistant', content: reply, task_id: taskId }])
      }
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
  const completedPlanCount = plan.filter((s) => s.status === 'completed').length
  const runningStep = [...liveSteps].reverse().find((step) => step.status === 'running') || liveSteps[liveSteps.length - 1]
  const hasThinking = sending || plan.length > 0 || liveSteps.length > 0 || Boolean(recoveredTask)
  const thinkingSummary = sending
    ? (runningStep?.label ? `正在${String(runningStep.label).replace(/^正在/, '')}` : '正在理解目标')
    : plan.length > 0
      ? `已完成 ${completedPlanCount}/${plan.length} 步`
      : '本轮没有后台执行记录'
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
          <div><strong>Marketing Agent</strong><span><i /> {assistantAvailable ? 'Agent Runtime 在线' : 'Agent Runtime 连接中'}</span></div>
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

        {hasThinking && (
          <section className={`agent-thinking ${thinkingExpanded ? 'expanded' : ''}`}>
            <button className="agent-thinking-toggle" onClick={() => setThinkingExpanded((value) => !value)}>
              <span className="thinking-orb">{sending ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />}</span>
              <span>
                <strong>{sending ? '思考中' : '思考与执行'}</strong>
                <small>{thinkingSummary}</small>
              </span>
              {plan.length > 0 && <em>{completedPlanCount}/{plan.length}</em>}
              <ChevronDown size={14} />
            </button>
            {thinkingExpanded && (
              <div className="agent-thinking-body">
                {plan.length > 0 && (
                  <div className="agent-thinking-group">
                    <div className="section-eyebrow">计划</div>
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
                  </div>
                )}
                {liveSteps.length > 0 && (
                  <div className="agent-thinking-group">
                    <div className="section-eyebrow">过程</div>
                    <div className="task-list">
                      {liveSteps.map((step, index) => (
                        <div className="task-item" key={`${step.type}-${step.label}-${index}`}>
                          <span className={`task-state ${step.status || ''}`}>{stepIcon(step)}</span>
                          <span>{step.label || step.type}{typeof step.detail === 'string' && step.detail ? ` · ${step.detail}` : ''}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {recoveredTask && <button className="agent-resume-task" onClick={resume}><Play size={12} />继续上次任务</button>}
              </div>
            )}
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
              : <div className="agent-message" key={`${index}-${turn.content}`}>{turn.role === 'system' ? <ShieldAlert size={14} /> : <Sparkles size={14} />}<AgentMessageContent content={turn.content} /></div>
            )}
            {sending && liveSteps.length === 0 && <div className="agent-message"><Sparkles size={14} /><p>正在理解目标…</p></div>}
          </section>
        )}
      </div>

      <div className="agent-composer">
        <textarea value={message} onChange={(event) => setMessage(event.target.value)} onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit() }
        }} placeholder={sending ? '修改目标或等待完成…' : '告诉 Agent 你想完成什么...'} rows={3} disabled={!assistantAvailable} />
        <div className="composer-footer">
          <div style={{display:'flex',alignItems:'center',gap:6}}>
            <span>{assistantAvailable ? `${toolCount} 工具在线` : 'Agent Runtime 未连接'}</span>
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
          <button onClick={submit} disabled={!message.trim() || !assistantAvailable} title={sending ? '修改目标' : '发送'}><ArrowUp size={16} /></button>
        </div>
      </div>
    </aside>
  )
}
