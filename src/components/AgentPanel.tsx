import { useEffect, useState } from 'react'
import { ArrowUp, Check, ChevronRight, Circle, Sparkles } from 'lucide-react'
import { api } from '@/api/client'

type ChatTurn = { role: 'user' | 'assistant'; content: string }

const PAGE_CONTEXT: Record<string, { title: string; suggestions: string[] }> = {
  overview: { title: '今日营销建议', suggestions: ['先刷新真实热点数据', '确认账号连接状态', '从创意中心选择方向'] },
  trending: { title: '趋势研判', suggestions: ['关注排名靠前的话题', '切换平台检查数据分布', '把候选热点带入创意中心'] },
  ideas: { title: '创意策略', suggestions: ['先生成 3 个冲突型开场', '教程方向更匹配当前账号', '保留一个故事型备选'] },
  factory: { title: '制作进度', suggestions: ['脚本已通过品牌语气检查', '配音预计 1 分钟后完成', '封面标题建议控制在 12 字内'] },
  publish: { title: '发布建议', suggestions: ['先创建一条真实发布任务', '确认目标平台与发布时间', '发布后同步表现数据'] },
  analytics: { title: '复盘结论', suggestions: ['真实数据不足时不生成结论', '先连接账号并完成一次发布', '持续同步播放与互动指标'] },
  workflow: { title: '自动化状态', suggestions: ['立即运行会刷新热点与选题', '启用状态会保存在本机', '发布自动化仍需人工确认'] },
  accounts: { title: '账号健康', suggestions: ['使用平台官方登录页授权', '凭据优先存入 Bitwarden', '定期检查授权是否过期'] },
}

export function AgentPanel({ page, status }: { page: string; status: string }) {
  const context = PAGE_CONTEXT[page] || PAGE_CONTEXT.overview
  const [message, setMessage] = useState('')
  const [history, setHistory] = useState<ChatTurn[]>([])
  const [sending, setSending] = useState(false)
  const [assistantAvailable, setAssistantAvailable] = useState(false)
  const [liveSuggestions, setLiveSuggestions] = useState<string[]>([])

  useEffect(() => {
    if (status !== 'ready') return
    api.assistantStatus().then((value) => setAssistantAvailable(Boolean((value as { available?: boolean }).available))).catch(() => setAssistantAvailable(false))
    api.suggestions().then((value) => {
      const suggestions = (value as { suggestions?: Suggestion[] }).suggestions || []
      setLiveSuggestions(suggestions.slice(0, 3).map((item) => item.angles?.[0] || item.trend))
    }).catch(() => setLiveSuggestions([]))
  }, [status])

  const displayedSuggestions = liveSuggestions.length ? liveSuggestions : context.suggestions
  const tasks = [
    { label: '连接营销引擎', done: status === 'ready' },
    { label: '读取真实选题数据', done: liveSuggestions.length > 0 },
    { label: '接入自由对话执行', done: false },
  ]
  const completedTasks = tasks.filter((task) => task.done).length

  const submit = async () => {
    const value = message.trim()
    if (!value || !assistantAvailable || sending) return
    const requestHistory = history.slice(-12)
    setHistory((current) => [...current, { role: 'user', content: value }])
    setMessage('')
    setSending(true)
    try {
      const result = await api.assistantMessage(value, requestHistory) as { reply?: string }
      setHistory((current) => [...current, { role: 'assistant', content: result.reply || 'Hermes 未返回内容。' }])
    } catch (reason) {
      setHistory((current) => [...current, { role: 'assistant', content: `调用失败：${String((reason as Error)?.message || reason)}` }])
    } finally {
      setSending(false)
    }
  }

  return (
    <aside className="agent-panel">
      <div className="agent-header">
        <div className="agent-identity">
          <div className="agent-mark"><Sparkles size={16} /></div>
          <div>
            <strong>Marketing Agent</strong>
            <span><i /> {status === 'ready' ? '引擎就绪' : status === 'error' ? '引擎异常' : '正在连接'}</span>
          </div>
        </div>
        <button className="icon-button small" title="打开任务详情"><ChevronRight size={16} /></button>
      </div>

      <div className="agent-scroll">
        <section className="agent-section">
          <div className="section-eyebrow">AI 判断</div>
          <h3>{context.title}</h3>
          <div className="agent-suggestions">
            {displayedSuggestions.map((suggestion, index) => (
              <button key={suggestion} className="agent-suggestion">
                <span>{String(index + 1).padStart(2, '0')}</span>
                <p>{suggestion}</p>
                <ChevronRight size={14} />
              </button>
            ))}
          </div>
        </section>

        <section className="agent-section agent-progress">
          <div className="section-row">
            <div className="section-eyebrow">今日任务</div>
            <span>{completedTasks} / {tasks.length}</span>
          </div>
          <div className="progress-track"><div style={{ width: `${(completedTasks / tasks.length) * 100}%` }} /></div>
          <div className="task-list">
            {tasks.map((task) => (
              <div className="task-item" key={task.label}>
                <span className={`task-state ${task.done ? 'done' : ''}`}>
                  {task.done ? <Check size={11} /> : <Circle size={10} />}
                </span>
                <span>{task.label}</span>
              </div>
            ))}
          </div>
        </section>

        {(history.length > 0 || sending) && (
          <section className="agent-reply">
            {history.map((turn, index) => turn.role === 'user'
              ? <p className="user-message" key={`${index}-${turn.content}`}>{turn.content}</p>
              : <div className="agent-message" key={`${index}-${turn.content}`}><Sparkles size={14} /><p>{turn.content}</p></div>
            )}
            {sending && <div className="agent-message"><Sparkles size={14} /><p>Hermes 正在思考…</p></div>}
          </section>
        )}
      </div>

      <div className="agent-composer">
        <textarea
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              submit()
            }
          }}
          placeholder="告诉 AI 你想完成什么..."
          rows={3}
          disabled={!assistantAvailable || sending}
        />
        <div className="composer-footer">
          <span>{assistantAvailable ? 'Hermes 只读模式' : 'Hermes 不可用'}</span>
          <button onClick={submit} disabled={!message.trim() || !assistantAvailable || sending} title="发送"><ArrowUp size={16} /></button>
        </div>
      </div>
    </aside>
  )
}
