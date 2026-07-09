import { useEffect, useState } from 'react'
import { Check, ChevronRight, Pause, Play, Plus, RefreshCw, Trash2, TrendingUp } from 'lucide-react'
import { api, PLATFORM_NAMES } from '@/api/client'

type PublishingTask = {
  id: string
  title: string
  platform: string
  status: 'review' | 'scheduled' | 'published'
  scheduled_at?: string
  metrics?: { views?: number }
}

type SqlPublishingTask = {
  id: string
  asset_id: string
  platform: string
  status: string
  receipt?: null | Record<string, unknown>
  published_at?: string | null
  next_metrics_at?: string | null
  recommended_next_action?: string | null
  metric_checkpoints?: Array<{ id: string; checkpoint_label: string; status: string; due_at?: string; last_error?: string | null }>
  metric_snapshots?: Array<{ id: string; metrics?: Record<string, unknown>; provenance?: Record<string, unknown> }>
}

type AnalyticsSummary = {
  views: number
  engagements: number
  comments: number
  follower_growth: number
  published_count: number
  connected_accounts: number
  daily_views: number[]
}

type WorkflowState = {
  enabled: boolean
  schedule_time: string
  last_run: string | null
  next_run?: string | null
  running?: boolean
  due?: boolean
  last_result?: { trends_count?: number; suggestions_count?: number; message?: string } | null
}

type IntelligenceConfig = {
  industries: string[]
  platforms: string[]
  sync_accounts: boolean
}

export function PublishCenter() {
  const [tasks, setTasks] = useState<PublishingTask[]>([])
  const [sqlTasks, setSqlTasks] = useState<SqlPublishingTask[]>([])
  const [draft, setDraft] = useState('')
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState('')
  const [querying, setQuerying] = useState<Record<string, boolean>>({})
  const [queryNotice, setQueryNotice] = useState<Record<string, string>>({})

  const load = async () => {
    try {
      const [legacy, sql] = await Promise.all([
        api.publishingTasks(),
        api.sqlPublishingTasks().catch(() => ({ tasks: [], total: 0, source: 'sql_store' })),
      ])
      setTasks(((legacy as { tasks?: PublishingTask[] }).tasks || []))
      setSqlTasks(((sql as { tasks?: SqlPublishingTask[] }).tasks || []))
    } catch (reason) {
      setError(String((reason as Error)?.message || reason || '发布任务加载失败'))
    }
  }

  useEffect(() => { load() }, [])

  const create = async () => {
    if (!draft.trim()) return
    try {
      await api.createPublishingTask({ title: draft.trim(), status: 'review' })
      setDraft('')
      setCreating(false)
      await load()
    } catch (reason) {
      setError(String((reason as Error)?.message || reason || '创建失败'))
    }
  }

  const remove = async (id: string) => {
    await api.deletePublishingTask(id)
    await load()
  }

  const queryPublish = async (task: SqlPublishingTask) => {
    setQuerying((current) => ({ ...current, [task.id]: true }))
    setQueryNotice((current) => ({ ...current, [task.id]: '正在反查官方作品列表…' }))
    try {
      const result = await api.querySqlPublishingTask(task.id, true) as { status?: string; reason?: string; receipt?: Record<string, unknown> }
      const status = result.status || 'unknown'
      const message = status === 'verified' || status === 'already_verified'
        ? `已验证：${String(result.receipt?.published_url || result.receipt?.platform_post_id || '官方作品已匹配')}`
        : status === 'found_unverified'
          ? '只匹配到疑似作品，但没有稳定 URL / post_id，暂不标记成功。'
          : status === 'not_found'
            ? '官方作品列表暂未找到匹配内容。'
            : `反查未完成：${result.reason || status}`
      setQueryNotice((current) => ({ ...current, [task.id]: message }))
      await load()
    } catch (reason) {
      setQueryNotice((current) => ({ ...current, [task.id]: `反查失败：${String((reason as Error)?.message || reason)}` }))
    } finally {
      setQuerying((current) => ({ ...current, [task.id]: false }))
    }
  }

  const columns = [
    { title: '待审核', status: 'review' },
    { title: '等待发布', status: 'scheduled' },
    { title: '已发布', status: 'published' },
  ] as const

  return (
    <div className="operations-page animate-fade-up">
      <StandardHeader kicker="PUBLISH PIPELINE" title="发布管道" copy={`${tasks.length + sqlTasks.length} 条任务保存在本机；主入口已并入内容工厂，真实回执以官方作品反查为准。`} action="创建发布任务" onAction={() => setCreating(true)} />
      {error && <div className="empty-inline text-destructive">{error}</div>}
      <section className="insight-block">
        <span className="page-kicker">OFFICIAL RECEIPTS</span>
        <h2>{sqlTasks.length ? '真实发布回执' : '暂无真实发布回执'}</h2>
        <p>这里展示 SQL 发布链路：只有从官方作品列表反查到稳定 URL 或 post_id，才会标记为已发布并启动指标回收。</p>
        <div className="memory-list">
          {sqlTasks.map((task) => {
            const receipt = task.receipt || {}
            const verified = Boolean(receipt.published_url || receipt.platform_post_id)
            const checkpoints = task.metric_checkpoints || []
            const nextCheckpoint = checkpoints.find((item) => item.status === 'scheduled')
            return (
              <div className="memory-card" key={task.id}>
                <div className="memory-card-header">
                  <span className="memory-kind-badge">{PLATFORM_NAMES[task.platform] || task.platform}</span>
                  <span style={{fontSize:8,color:verified ? '#62c4a0' : '#f59e0b',fontWeight:600}}>{verified ? '已验证' : task.status}</span>
                  {task.recommended_next_action === 'marketing_publish_query' && <span className="memory-account">建议反查</span>}
                  <span className="memory-confidence">{checkpoints.filter((item) => item.status === 'collected').length}/{checkpoints.length || 5} 指标点</span>
                </div>
                <p className="memory-content">{task.id} · asset {task.asset_id}</p>
                <p className="memory-evidence">
                  {verified
                    ? `官方证据：${String(receipt.published_url || receipt.platform_post_id)}`
                    : '未获得稳定官方作品 ID，系统不会把它当成发布成功。'}
                </p>
                {nextCheckpoint && <span className="metric-chip">下一次指标回收：{nextCheckpoint.checkpoint_label}</span>}
                {queryNotice[task.id] && <p className="memory-evidence">{queryNotice[task.id]}</p>}
                <div className="content-detail-actions">
                  <button className="tab active" disabled={querying[task.id]} onClick={() => queryPublish(task)}>
                    {querying[task.id] ? '反查中…' : '反查官方作品'}
                  </button>
                </div>
              </div>
            )
          })}
          {sqlTasks.length === 0 && <div className="empty-inline">通过内容资产创建真实发布任务后，这里会显示回执和指标回收状态。</div>}
        </div>
      </section>
      {creating && (
        <div className="publish-summary">
          <input className="flex-1 bg-transparent outline-none text-sm" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="输入内容标题" autoFocus onKeyDown={(event) => event.key === 'Enter' && create()} />
          <button className="primary-action" onClick={create} disabled={!draft.trim()}>保存任务</button>
        </div>
      )}
      <div className="kanban-board">
        {columns.map((column) => {
          const items = tasks.filter((task) => task.status === column.status)
          return (
            <section className="kanban-column" key={column.status}>
              <div className="kanban-heading"><strong>{column.title}</strong><span>{items.length}</span></div>
              {items.map((task, index) => (
                <div className="content-card" key={task.id}>
                  <div className={`content-thumb thumb-${(index % 2) + 1}`}><Play size={16} /></div>
                  <div><strong>{task.title}</strong><span>{PLATFORM_NAMES[task.platform] || task.platform}{task.scheduled_at ? ` · ${task.scheduled_at}` : ''}</span></div>
                  <button className="icon-button small" title="删除任务" onClick={() => remove(task.id)}><Trash2 size={14} /></button>
                </div>
              ))}
              {items.length === 0 && <div className="empty-inline">暂无任务</div>}
              <button className="column-action" onClick={() => setCreating(true)}><Plus size={14} /> 添加内容</button>
            </section>
          )
        })}
      </div>
    </div>
  )
}

export function Analytics() {
  const [data, setData] = useState<AnalyticsSummary | null>(null)
  const [error, setError] = useState('')

  const load = () => api.analyticsSummary()
    .then((value) => setData(value as AnalyticsSummary))
    .catch((reason) => setError(String(reason?.message || reason || '分析数据加载失败')))

  useEffect(() => { load() }, [])
  const values = data || { views: 0, engagements: 0, comments: 0, follower_growth: 0, published_count: 0, connected_accounts: 0, daily_views: [] }

  return (
    <div className="operations-page animate-fade-up">
      <StandardHeader kicker="PERFORMANCE" title="数据分析" copy="所有指标来自本机已发布任务与账号数据。" action="刷新数据" onAction={load} />
      {error && <div className="empty-inline text-destructive">{error}</div>}
      <section className="analytics-strip">
        <AnalyticsMetric label="播放" value={formatNumber(values.views)} />
        <AnalyticsMetric label="互动" value={formatNumber(values.engagements)} />
        <AnalyticsMetric label="评论" value={formatNumber(values.comments)} />
        <AnalyticsMetric label="净增粉丝" value={`+${formatNumber(values.follower_growth)}`} />
      </section>
      <div className="analysis-layout">
        <section className="insight-block">
          <span className="page-kicker">CURRENT DATA</span>
          <h2>{values.published_count ? `已汇总 ${values.published_count} 条发布内容` : '尚无真实发布数据'}</h2>
          <p>{values.published_count ? '随着账号监控和发布任务写入指标，这里会持续更新汇总结果。' : '创建发布任务并录入平台表现后，系统才会生成可信的复盘结论。'}</p>
          <div className="insight-tags"><span>{values.connected_accounts} 个账号</span><span>{values.published_count} 条已发布</span></div>
        </section>
        <section className="next-action-block">
          <span className="page-kicker">DATA QUALITY</span><h2>下一步</h2>
          {['连接至少一个平台账号', '完成首次真实发布', '同步播放与互动指标'].map((item, index) => <div className="recommendation" key={item}><span>0{index + 1}</span><p>{item}</p><Check size={14} /></div>)}
        </section>
      </div>
    </div>
  )
}

export function Workflow() {
  const [state, setState] = useState<WorkflowState>({ enabled: false, schedule_time: '08:03', last_run: null, last_result: null })
  const [config, setConfig] = useState<IntelligenceConfig>({ industries: [], platforms: ['douyin'], sync_accounts: true })
  const [industryInput, setIndustryInput] = useState('')
  const [report, setReport] = useState<IntelligenceReport>({ status: 'never_run', steps: [], errors: [], summary: {} })
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const [workflow, intelligence, lastReport] = await Promise.all([
        api.workflowStatus(), api.intelligenceConfig(), api.intelligenceReport(),
      ])
      setState(workflow as WorkflowState)
      setConfig(intelligence as IntelligenceConfig)
      setIndustryInput((intelligence as IntelligenceConfig).industries.join('、'))
      setReport(lastReport as IntelligenceReport)
    } catch (reason) {
      setError(String((reason as Error)?.message || reason))
    }
  }

  useEffect(() => {
    load()
    if (!window.marketingOS) return
    return window.marketingOS.onIntelligenceProgress((progress) => {
      setReport(progress)
      setRunning(progress.status === 'running')
    })
  }, [])

  const saveTargets = async () => {
    const industries = industryInput.split(/[、,，\n]/).map((item) => item.trim()).filter(Boolean)
    const value = await api.updateIntelligenceConfig({ industries, sync_accounts: config.sync_accounts, platforms: ['douyin'] })
    setConfig(value as IntelligenceConfig)
    setIndustryInput((value as IntelligenceConfig).industries.join('、'))
  }

  const toggle = async () => {
    if (!state.enabled && config.industries.length === 0) {
      setError('请先设置至少一个关注行业，再启用每日巡检。')
      return
    }
    const value = await api.updateWorkflowStatus({ enabled: !state.enabled })
    setState(value as WorkflowState)
  }

  const changeSchedule = async (schedule_time: string) => {
    setState((current) => ({ ...current, schedule_time }))
    const value = await api.updateWorkflowStatus({ schedule_time })
    setState(value as WorkflowState)
  }

  const run = async () => {
    setRunning(true)
    setError('')
    try {
      await saveTargets()
      if (!window.marketingOS) throw new Error('统一智能巡检只能在桌面应用中运行')
      const result = await window.marketingOS.runIntelligence()
      setReport(result)
      await load()
    } catch (reason) {
      setError(String((reason as Error)?.message || reason || '工作流执行失败'))
    } finally {
      setRunning(false)
    }
  }

  const nodes = report.steps.length ? report.steps.map((item) => ({
    title: item.label,
    detail: item.detail,
    state: item.status === 'completed' ? 'done' : item.status === 'running' || item.status === 'partial' ? 'active' : 'waiting',
  })) : [
    { title: '等待设置智能目标', detail: '系统会根据行业目标自动同步账号、采集内容并生成选题', state: 'waiting' },
  ]

  return (
    <div className="operations-page animate-fade-up">
      <StandardHeader kicker="AUTOMATION" title="自动化" copy={state.next_run ? `下次运行：${new Date(state.next_run).toLocaleString('zh-CN')}` : '当前工作流负责热点抓取、分析和选题生成。'} action={running || state.running ? '运行中' : '立即运行'} onAction={run} disabled={running || state.running} />
      {error && <div className="empty-inline text-destructive">{error}</div>}
      <section className="insight-block">
        <span className="page-kicker">INTELLIGENCE GOAL</span>
        <h2>告诉系统持续关注什么</h2>
        <p>设置一次后，每日巡检会复用已登录账号，同步账号表现、采集行业内容、生成选题，并保留数据来源与失败原因。</p>
        <div className="flex gap-3 mt-4">
          <input className="flex-1 rounded-md border bg-transparent px-3 text-sm outline-none" value={industryInput} onChange={(event) => setIndustryInput(event.target.value)} placeholder="例如：国货美妆、连锁餐饮、AI 教育（用逗号分隔）" />
          <label className="flex items-center gap-2 text-xs text-muted-foreground"><input type="checkbox" checked={config.sync_accounts} onChange={(event) => setConfig((current) => ({ ...current, sync_accounts: event.target.checked }))} />同步账号指标</label>
          <button className="primary-action" onClick={saveTargets}>保存目标</button>
        </div>
      </section>
      <div className="workflow-toolbar"><div><i /> 每日内容增长循环 <span>{state.enabled ? '已启用' : '已暂停'}</span></div><div><input type="time" value={state.schedule_time} onChange={(event) => changeSchedule(event.target.value)} className="bg-transparent text-xs text-muted-foreground outline-none" /><button className="icon-button small" title={state.enabled ? '暂停' : '启用'} onClick={toggle}>{state.enabled ? <Pause size={14} /> : <Play size={14} />}</button><button className="icon-button small" title="立即运行" onClick={run} disabled={running || state.running}><RefreshCw size={14} className={running || state.running ? 'animate-spin' : ''} /></button></div></div>
      <section className="workflow-canvas">
        {nodes.map((node, index) => (
          <div className={`workflow-node ${node.state}`} key={node.title}>
            <span className="node-time">{index === 0 && state.last_run ? new Date(state.last_run).toLocaleString('zh-CN') : `步骤 ${index + 1}`}</span>
            <span className="node-marker">{node.state === 'done' ? <Check size={13} /> : node.state === 'active' ? <Play size={12} /> : index + 1}</span>
            <div><strong>{node.title}</strong><p>{node.detail}</p></div>
            <ChevronRight size={15} />
          </div>
        ))}
      </section>
      {report.errors.length > 0 && (
        <section className="next-action-block">
          <span className="page-kicker">HONEST REPORT</span><h2>本次未完成的步骤</h2>
          {report.errors.map((item, index) => <div className="recommendation" key={`${item.scope}-${item.target}-${index}`}><span>!</span><p>{item.target}：{item.message}</p></div>)}
        </section>
      )}
    </div>
  )
}

function StandardHeader({ kicker, title, copy, action, onAction, disabled }: { kicker: string; title: string; copy: string; action: string; onAction: () => void; disabled?: boolean }) {
  return <div className="standard-page-header"><div><span className="page-kicker">{kicker}</span><h1>{title}</h1><p>{copy}</p></div><button className="primary-action" onClick={onAction} disabled={disabled}><Plus size={15} /> {action}</button></div>
}

function AnalyticsMetric({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong><p><TrendingUp size={13} />真实累计</p></div>
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN', { notation: value >= 10000 ? 'compact' : 'standard', maximumFractionDigits: 1 }).format(value)
}
