import { useEffect, useState } from 'react'
import { Check, ChevronRight, Circle, FileText, Film, Image, PenTool, Plus, RefreshCw, Sparkles, Trash2, Upload, X } from 'lucide-react'
import { api, PLATFORM_NAMES } from '@/api/client'

interface ContentAsset {
  id: string; title: string; type: string; status: string
  platform?: string; account_id?: string; version: number
  content: Record<string, unknown>; metrics: Record<string, unknown>
  created_at: string; updated_at: string
}

interface StockImageCandidate {
  provider: string; provider_id: string; preview_url: string; download_url: string
  source_url: string; author: string; author_url: string; alt: string
  width: number; height: number; license: string
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
  learning?: { status?: string; memory_candidate_id?: string | null; prediction?: string }
}

type MetricDraft = {
  views?: string
  likes?: string
  comments?: string
  shares?: string
  completion_rate?: string
  engagement_rate?: string
}

const TYPE_ICONS: Record<string, typeof FileText> = { script: FileText, video: Film, image: Image, caption: PenTool }
const TYPE_LABELS: Record<string, string> = { script: '脚本', video: '视频', image: '图片', caption: '文案' }
const STATUS_LABELS: Record<string, string> = { draft: '草稿', review: '待审', approved: '已通过', published: '已发布', metrics_collected: '有数据', archived: '已归档' }
const STATUS_COLORS: Record<string, string> = { draft: '#6b7280', review: '#f59e0b', approved: '#3b82f6', published: '#62c4a0', metrics_collected: '#8b5cf6', archived: '#4b5563' }
const STATUSES = ['', 'draft', 'review', 'approved', 'published']
type ProductionKind = 'auto' | 'article_soft' | 'faceless_video' | 'premium_human_video'
type FactoryMode = 'all' | 'article' | 'video'

const PRODUCTION_LABELS: Record<ProductionKind, string> = {
  auto: '内容生产',
  article_soft: '知乎/公众号软文',
  faceless_video: '不露脸素材视频',
  premium_human_video: '数字人/AI人视频',
}

const FACTORY_MODE_COPY: Record<FactoryMode, { title: string; copy: string; empty: string; primaryKind: ProductionKind }> = {
  all: {
    title: '内容资产',
    copy: '选题→草稿→审批→发布→指标回收 全链路管理',
    empty: '暂无内容资产。先让 Agent 根据账号定位和热点生成一版草稿，或者手动创建一个选题。',
    primaryKind: 'auto',
  },
  article: {
    title: '图文创作',
    copy: '知乎、公众号、配图和长文素材分开管理；证据、引用和配图需求都要留痕。',
    empty: '暂无图文资产。先让 Agent 生成一篇知乎/公众号软文，或者手动保存一个图文选题。',
    primaryKind: 'article_soft',
  },
  video: {
    title: '视频创作',
    copy: '不露脸素材视频、数字人视频和成片素材单独管理；脚本、镜头、素材和渲染状态都要可追溯。',
    empty: '暂无视频资产。先让 Agent 生成一条素材视频工单，或者手动保存一个视频草稿。',
    primaryKind: 'faceless_video',
  },
}

function assetMatchesMode(asset: ContentAsset, mode: FactoryMode) {
  if (mode === 'all') return true
  if (mode === 'video') return asset.type === 'video'
  return asset.type === 'script' || asset.type === 'caption' || asset.type === 'image'
}

export default function Creator({ onNavigate, mode = 'all' }: { onNavigate?: (page: string) => void; mode?: FactoryMode }) {
  const [assets, setAssets] = useState<ContentAsset[]>([])
  const [filter, setFilter] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newType, setNewType] = useState('script')
  const [newBody, setNewBody] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [newAccountId, setNewAccountId] = useState('')
  const [attachments, setAttachments] = useState<Record<string, Array<{ original_name: string; byte_size: number; position: number }>>>({})
  const [mediaNotice, setMediaNotice] = useState<Record<string, string>>({})
  const [stockQueries, setStockQueries] = useState<Record<string, string>>({})
  const [stockResults, setStockResults] = useState<Record<string, StockImageCandidate[]>>({})
  const [stockSearching, setStockSearching] = useState<Record<string, boolean>>({})
  const [pexelsConfigured, setPexelsConfigured] = useState<boolean | null>(null)
  const [pexelsKey, setPexelsKey] = useState('')
  const [sqlTasks, setSqlTasks] = useState<SqlPublishingTask[]>([])
  const [querying, setQuerying] = useState<Record<string, boolean>>({})
  const [queryNotice, setQueryNotice] = useState<Record<string, string>>({})
  const [metricDrafts, setMetricDrafts] = useState<Record<string, MetricDraft>>({})
  const [metricSaving, setMetricSaving] = useState<Record<string, boolean>>({})
  const modeConfig = FACTORY_MODE_COPY[mode] || FACTORY_MODE_COPY.all
  const typeOptions = mode === 'article'
    ? ['script', 'image', 'caption']
    : mode === 'video'
      ? ['video']
      : Object.keys(TYPE_LABELS)

  const fetchAssets = async () => {
    try {
      const status = filter || undefined
      const [result, publishing] = await Promise.all([
        api.contentAssets(status),
        api.sqlPublishingTasks().catch(() => ({ tasks: [] })),
      ])
      const loaded = (result as ContentAsset[]) || []
      setAssets(loaded)
      setSqlTasks((((publishing as { tasks?: SqlPublishingTask[] }).tasks) || []))
      const pairs = await Promise.all(loaded.filter((asset) => ['video', 'image'].includes(asset.type) && asset.account_id).map(async (asset) => {
        try {
          const response = await api.contentAssetAttachment(asset.id, asset.account_id || '')
          return response.attachments?.length ? [asset.id, response.attachments] as const : null
        } catch { return null }
      }))
      setAttachments(Object.fromEntries(pairs.filter(Boolean) as Array<readonly [string, Array<{ original_name: string; byte_size: number; position: number }>] >))
    } catch { setAssets([]); setSqlTasks([]) }
  }
  useEffect(() => { fetchAssets() }, [filter])
  useEffect(() => {
    if (!typeOptions.includes(newType)) setNewType(typeOptions[0] || 'script')
  }, [mode])
  useEffect(() => {
    api.accounts().then(({ accounts: loaded }) => {
      const connected = loaded.filter((account) => account.status === 'connected')
      setAccounts(connected)
      if (connected.length === 1) setNewAccountId(connected[0].id)
    }).catch(() => setAccounts([]))
  }, [])
  useEffect(() => {
    api.stockImageStatus().then((status) => setPexelsConfigured(status.configured)).catch(() => setPexelsConfigured(false))
  }, [])

  const handleCreate = async () => {
    if (!newTitle.trim()) return
    try {
      const account = accounts.find((item) => item.id === newAccountId)
      if ((newType === 'video' || newType === 'image') && !account) return
      await api.createContentAsset({
        title: newTitle, type: newType,
        account_id: account?.id, platform: account?.platform,
        content: newBody.trim() ? { body: newBody.trim() } : undefined,
      })
      setNewTitle(''); setNewBody(''); setShowCreate(false)
      fetchAssets()
    } catch {}
  }

  const handleStatus = async (id: string, status: string) => {
    try { await api.transitionContentAsset(id, status); fetchAssets() } catch {}
  }

  const handleDelete = async (id: string) => {
    try {
      if (attachments[id]) await window.marketingOS.deleteMediaAttachmentForAsset(id)
      await api.deleteContentAsset(id)
      fetchAssets()
    } catch {}
  }

  const handleMediaImport = async (asset: ContentAsset) => {
    setMediaNotice((current) => ({ ...current, [asset.id]: '正在导入…' }))
    try {
      const result = await window.marketingOS.importMediaAttachment(asset.id)
      if (result.cancelled) setMediaNotice((current) => ({ ...current, [asset.id]: '' }))
      else {
        setMediaNotice((current) => ({ ...current, [asset.id]: '媒体已安全导入' }))
        await fetchAssets()
      }
    } catch (error) {
      setMediaNotice((current) => ({
        ...current, [asset.id]: `导入失败：${String((error as Error)?.message || error)}`,
      }))
    }
  }

  const handleStockSearch = async (asset: ContentAsset) => {
    const query = (stockQueries[asset.id] || asset.title).trim()
    if (!query) return
    setStockSearching((current) => ({ ...current, [asset.id]: true }))
    setMediaNotice((current) => ({ ...current, [asset.id]: '正在 Pexels 搜索竖版图片…' }))
    try {
      const result = await api.searchStockImages(query)
      setStockResults((current) => ({ ...current, [asset.id]: result.candidates }))
      setMediaNotice((current) => ({ ...current, [asset.id]: result.candidates.length ? '' : '没有找到合适图片，请更换关键词' }))
    } catch (error) {
      setMediaNotice((current) => ({ ...current, [asset.id]: `找图失败：${String((error as Error)?.message || error)}` }))
    } finally {
      setStockSearching((current) => ({ ...current, [asset.id]: false }))
    }
  }

  const handleSavePexelsKey = async () => {
    if (!pexelsKey.trim()) return
    try {
      await window.marketingOS.setProviderSecret('PEXELS_API_KEY', pexelsKey)
      setPexelsKey('')
      setPexelsConfigured(true)
    } catch (error) {
      setMediaNotice((current) => ({ ...current, global: `密钥保存失败：${String((error as Error)?.message || error)}` }))
    }
  }

  const handleStockImport = async (asset: ContentAsset, candidate: StockImageCandidate) => {
    setMediaNotice((current) => ({ ...current, [asset.id]: '正在下载并校验图片…' }))
    try {
      await window.marketingOS.importStockImage(asset.id, candidate)
      setMediaNotice((current) => ({ ...current, [asset.id]: `已添加 ${candidate.author} 的 Pexels 图片` }))
      await fetchAssets()
    } catch (error) {
      setMediaNotice((current) => ({ ...current, [asset.id]: `添加失败：${String((error as Error)?.message || error)}` }))
    }
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
      await fetchAssets()
    } catch (error) {
      setQueryNotice((current) => ({ ...current, [task.id]: `反查失败：${String((error as Error)?.message || error)}` }))
    } finally {
      setQuerying((current) => ({ ...current, [task.id]: false }))
    }
  }

  const updateMetricDraft = (taskId: string, key: keyof MetricDraft, value: string) => {
    setMetricDrafts((current) => ({ ...current, [taskId]: { ...(current[taskId] || {}), [key]: value } }))
  }

  const submitMetrics = async (task: SqlPublishingTask) => {
    const draft = metricDrafts[task.id] || {}
    const metrics = Object.fromEntries(
      Object.entries(draft)
        .map(([key, value]) => [key, Number(String(value || '').trim())] as const)
        .filter(([, value]) => Number.isFinite(value) && value >= 0),
    ) as Record<string, number>
    if (Object.keys(metrics).length === 0) {
      setQueryNotice((current) => ({ ...current, [task.id]: '请至少填写一个真实指标；未知指标留空，不要写 0。' }))
      return
    }
    const checkpoint = (task.metric_checkpoints || []).find((item) => item.status === 'scheduled')
    setMetricSaving((current) => ({ ...current, [task.id]: true }))
    setQueryNotice((current) => ({ ...current, [task.id]: '正在写入指标并触发复盘…' }))
    try {
      const result = await api.collectSqlPublishingMetrics(task.id, {
        metrics,
        checkpoint_id: checkpoint?.id,
        provenance: {
          source_kind: 'manual_entry',
          source_ref: 'content_factory_manual_metrics',
          captured_at: new Date().toISOString(),
        },
      }) as { task?: SqlPublishingTask }
      const learning = result.task?.learning
      const suffix = learning?.status === 'reconciled'
        ? '已生成复盘候选，等待你确认是否沉淀为长期学习。'
        : learning?.prediction === 'missing'
          ? '已记录指标；该资产没有发布前预测，所以不会伪造学习结论。'
          : '已记录指标。'
      setQueryNotice((current) => ({ ...current, [task.id]: suffix }))
      setMetricDrafts((current) => ({ ...current, [task.id]: {} }))
      await fetchAssets()
    } catch (error) {
      setQueryNotice((current) => ({ ...current, [task.id]: `指标写入失败：${String((error as Error)?.message || error)}` }))
    } finally {
      setMetricSaving((current) => ({ ...current, [task.id]: false }))
    }
  }

  const startAgentProduction = (kind: ProductionKind = 'auto') => {
    const defaults: Record<ProductionKind, { objective: string; platforms: string[] }> = {
      auto: {
        objective: '请帮我生产一条可发布内容',
        platforms: [],
      },
      article_soft: {
        objective: '请帮我生产一篇知乎/公众号可用的软文',
        platforms: ['zhihu', 'wechat_official'],
      },
      faceless_video: {
        objective: '请帮我生产一条不露脸素材拼接视频',
        platforms: ['douyin', 'wechat_channels', 'bilibili'],
      },
      premium_human_video: {
        objective: '请帮我生产一条真人数字人或 AI 人高质量视频',
        platforms: ['douyin', 'wechat_channels', 'bilibili'],
      },
    }
    const selected = defaults[kind]
    const prompt = encodeURIComponent(
      `请启动「${PRODUCTION_LABELS[kind]}」生产线。\n\n` +
      `第一步必须先调用 marketing_plan_content_production，参数：objective=${JSON.stringify(selected.objective)}，kind=${kind}，platforms=${JSON.stringify(selected.platforms)}。\n` +
      '第二步必须在内部调用 marketing_draft_content_preflight 保存总预演，判断受众、证据、平台、成本和生产可行性；数字人/AI人视频的片子预演由独立高阶视频预演 Agent 负责，总预演不能替代镜头、节奏、美术和连续性判断。\n' +
      '然后按工单和内部预演推进：读取账号定位/热点/历史资产/发布表现；软文需要公开证据和平台适配；不露脸视频需要脚本、素材检索包、版权凭证和 EDL；数字人/AI人视频先输出项目画布、样片和预算门，不要冒充已经能生成成片。\n' +
      '不要把工具名、数据库字段、预演流水账或完整证据列表原样贴给用户；这些只放在思考/执行过程里。最终回复只说：能不能做、为什么、已保存的草稿 ID、还缺什么、下一步怎么审核/配图/渲染/发布。\n' +
      '如果是知乎/公众号软文，证据足够时优先保存父稿、平台变体、配图需求和发布前预测；如果是不露脸素材视频，优先保存旁白脚本、镜头清单、素材检索包、缺口生成请求和 EDL 草案。证据不足就先说明缺什么，不要编造数据。',
    )
    onNavigate?.(`chat-prompt:${prompt}`)
  }

  const visibleAssets = assets.filter((asset) => assetMatchesMode(asset, mode))
  const visibleAssetById = new Map(visibleAssets.map((asset) => [asset.id, asset]))
  const visibleSqlTasks = mode === 'all'
    ? sqlTasks
    : sqlTasks.filter((task) => visibleAssetById.has(task.asset_id))

  return (
    <div className="factory-page animate-fade-up">
      <div className="standard-page-header">
        <div><h1>{modeConfig.title}</h1><p>{modeConfig.copy}</p></div>
        <div className="header-actions">
          {mode !== 'video' && <button className="secondary-action" onClick={() => startAgentProduction('article_soft')}><FileText size={15} /> 写软文</button>}
          {mode !== 'article' && <button className="secondary-action" onClick={() => startAgentProduction('faceless_video')}><Film size={15} /> 不露脸视频</button>}
          {mode !== 'article' && <button className="secondary-action" onClick={() => startAgentProduction('premium_human_video')}><Sparkles size={15} /> 数字人视频</button>}
          <button className="primary-action" onClick={() => setShowCreate(true)}><Plus size={15} /> 新建草稿</button>
        </div>
      </div>

      {showCreate && (
        <div className="content-draft-composer">
          <div className="content-create-bar">
            <input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="标题…" onKeyDown={(e) => e.key === 'Enter' && !newBody.trim() && handleCreate()} />
            <select value={newType} onChange={(e) => setNewType(e.target.value)}>
              {typeOptions.map((key) => <option key={key} value={key}>{TYPE_LABELS[key]}</option>)}
            </select>
            {(newType === 'video' || newType === 'image') && (
              <select value={newAccountId} onChange={(e) => setNewAccountId(e.target.value)}>
                <option value="">选择账号</option>
                {accounts.map((account) => <option key={account.id} value={account.id}>{account.label || account.username}</option>)}
              </select>
            )}
            <button className="primary-action" onClick={handleCreate}>保存草稿</button>
            <button className="icon-button" onClick={() => setShowCreate(false)}><X size={14} /></button>
          </div>
          <textarea
            className="content-draft-body"
            value={newBody}
            onChange={(e) => setNewBody(e.target.value)}
            placeholder="可选：直接粘贴正文、脚本大纲、图文文案。留空也可以先只保存一个选题。"
            rows={5}
          />
        </div>
      )}

      <div className="memory-tabs">
        {STATUSES.map((s) => (
          <button key={s || 'all'} className={`tab ${filter === s ? 'active' : ''}`} onClick={() => setFilter(s)}>
            {s ? STATUS_LABELS[s] : '全部'}
          </button>
        ))}
      </div>

      <section className="insight-block">
        <div className="memory-card-header">
          <span className="page-kicker">OFFICIAL RECEIPTS</span>
          <button className="tab" onClick={fetchAssets}><RefreshCw size={12} /> 刷新</button>
        </div>
        <h2>{visibleSqlTasks.length ? '真实发布回执' : '暂无真实发布回执'}</h2>
        <p>内容从这里走到发布后，系统只认官方作品列表里反查到的稳定 URL 或 post_id；没有证据就保持未验证，避免假成功。</p>
        <div className="memory-list">
          {visibleSqlTasks.map((task) => {
            const receipt = task.receipt || {}
            const verified = Boolean(receipt.published_url || receipt.platform_post_id)
            const checkpoints = task.metric_checkpoints || []
            const collected = checkpoints.filter((item) => item.status === 'collected').length
            const nextCheckpoint = checkpoints.find((item) => item.status === 'scheduled')
            const assetTitle = assets.find((asset) => asset.id === task.asset_id)?.title
            return (
              <div className="memory-card" key={task.id}>
                <div className="memory-card-header">
                  <span className="memory-kind-badge">{PLATFORM_NAMES[task.platform] || task.platform}</span>
                  <span style={{fontSize:8,color:verified ? '#62c4a0' : '#f59e0b',fontWeight:600}}>{verified ? '已验证' : task.status}</span>
                  {task.recommended_next_action === 'marketing_publish_query' && <span className="memory-account">建议反查</span>}
                  <span className="memory-confidence">{collected}/{checkpoints.length || 5} 指标点</span>
                </div>
                <p className="memory-content">{assetTitle || task.asset_id}</p>
                <p className="memory-evidence">
                  {verified
                    ? `官方证据：${String(receipt.published_url || receipt.platform_post_id)}`
                    : '未获得稳定官方作品 ID，系统不会把它当成发布成功。'}
                </p>
                {nextCheckpoint && <span className="metric-chip">下一次指标回收：{nextCheckpoint.checkpoint_label}</span>}
                {task.metric_snapshots?.length ? (
                  <div className="content-metrics">
                    <span className="section-eyebrow">已收指标</span>
                    {Object.entries(task.metric_snapshots[task.metric_snapshots.length - 1]?.metrics || {}).slice(0, 5).map(([key, value]) => (
                      <span key={key} className="metric-chip">{key}: {String(value)}</span>
                    ))}
                  </div>
                ) : null}
                {queryNotice[task.id] && <p className="memory-evidence">{queryNotice[task.id]}</p>}
                <div className="content-create-bar metric-entry-bar">
                  {([
                    ['views', '播放'],
                    ['likes', '赞'],
                    ['comments', '评'],
                    ['shares', '转'],
                    ['completion_rate', '完播率'],
                    ['engagement_rate', '互动率'],
                  ] as Array<[keyof MetricDraft, string]>).map(([key, label]) => (
                    <input
                      key={key}
                      value={metricDrafts[task.id]?.[key] || ''}
                      onChange={(event) => updateMetricDraft(task.id, key, event.target.value)}
                      placeholder={label}
                      inputMode="decimal"
                    />
                  ))}
                  <button className="tab active" disabled={metricSaving[task.id]} onClick={() => submitMetrics(task)}>
                    {metricSaving[task.id] ? '写入中…' : '补录指标'}
                  </button>
                </div>
                <div className="content-detail-actions">
                  <button className="tab active" disabled={querying[task.id]} onClick={() => queryPublish(task)}>
                    {querying[task.id] ? '反查中…' : '反查官方作品'}
                  </button>
                </div>
              </div>
            )
          })}
          {visibleAssets.length === 0 && <div className="empty-inline">还没有资产。先让 Agent 生成草稿，或手动新建一个选题。</div>}
          {visibleSqlTasks.length === 0 && visibleAssets.length > 0 && <div className="empty-inline">真实发布任务产生后，这里会显示官方回执、证据和指标回收进度。</div>}
        </div>
      </section>

      {visibleAssets.length === 0 ? (
        <div className="content-empty-state">
          <p className="memory-empty">{modeConfig.empty}</p>
          <button className="primary-action" onClick={() => startAgentProduction(modeConfig.primaryKind)}><Sparkles size={15} /> 让 Agent 生产第一条内容</button>
        </div>
      ) : (
        <div className="memory-list">
          {visibleAssets.map((a) => {
            const Icon = TYPE_ICONS[a.type] || FileText
            const isOpen = expanded === a.id
            return (
              <div key={a.id} className="memory-card">
                <div className="memory-card-header">
                  <span className="memory-kind-badge" style={{background:`${STATUS_COLORS[a.status]}20`,color:STATUS_COLORS[a.status]}}>
                    <Icon size={10} /> {TYPE_LABELS[a.type] || a.type}
                  </span>
                  <span style={{fontSize:8,color:STATUS_COLORS[a.status],fontWeight:600}}>{STATUS_LABELS[a.status] || a.status}</span>
                  {a.platform && <span className="memory-account">{a.platform}</span>}
                  <span className="memory-confidence">v{a.version}</span>
                  <button className="icon-button small" onClick={() => setExpanded(isOpen ? null : a.id)}>
                    <ChevronRight size={12} style={{transform: isOpen ? 'rotate(90deg)' : ''}} />
                  </button>
                  <button className="icon-button small" onClick={() => handleDelete(a.id)}><Trash2 size={11} /></button>
                </div>
                <p className="memory-content">{a.title}</p>
                {isOpen && (
                  <div className="content-detail">
                    <div className="content-detail-actions">
                      {a.status === 'draft' && <button className="tab active" onClick={() => handleStatus(a.id, 'review')}>提交审核</button>}
                      {a.status === 'review' && <><button className="tab active" onClick={() => handleStatus(a.id, 'approved')}>通过</button><button className="tab" onClick={() => handleStatus(a.id, 'draft')}>退回</button></>}
                      {(a.type === 'video' || a.type === 'image') && a.account_id && (
                        <button className="tab" onClick={() => handleMediaImport(a)}><Upload size={10} /> {a.type === 'video' ? (attachments[a.id] ? '更换视频' : '导入视频') : `添加图片${attachments[a.id]?.length ? `（${attachments[a.id].length}/9）` : ''}`}</button>
                      )}
                    </div>
                    {attachments[a.id]?.length > 0 && (
                      <div className="metric-chip">已导入：{attachments[a.id].map((item) => item.original_name).join('、')} · 共 {attachments[a.id].length} 个文件</div>
                    )}
                    {a.type === 'image' && a.account_id && (
                      <div className="content-detail">
                        {pexelsConfigured === false && (
                          <div className="content-create-bar">
                            <input type="password" value={pexelsKey} onChange={(event) => setPexelsKey(event.target.value)} placeholder="填写 Pexels API Key（将加密保存）" />
                            <button className="tab active" onClick={handleSavePexelsKey}>保存图库密钥</button>
                          </div>
                        )}
                        <div className="content-create-bar">
                          <input value={stockQueries[a.id] || ''} onChange={(event) => setStockQueries((current) => ({ ...current, [a.id]: event.target.value }))} placeholder={`找图关键词，默认：${a.title}`} onKeyDown={(event) => event.key === 'Enter' && handleStockSearch(a)} />
                          <button className="tab active" disabled={stockSearching[a.id]} onClick={() => handleStockSearch(a)}>自动找图</button>
                        </div>
                        {stockResults[a.id]?.length > 0 && (
                          <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(120px,1fr))',gap:8}}>
                            {stockResults[a.id].map((candidate) => (
                              <div key={candidate.provider_id} className="metric-chip" style={{display:'block'}}>
                                <img src={candidate.preview_url} alt={candidate.alt} style={{width:'100%',height:150,objectFit:'cover',borderRadius:6}} />
                                <button className="tab" onClick={() => window.marketingOS.openAttribution(candidate.source_url)} style={{display:'block',fontSize:9,margin:'5px 0'}}>Photo by {candidate.author} on Pexels</button>
                                <button className="tab" disabled={(attachments[a.id]?.length || 0) >= 9} onClick={() => handleStockImport(a, candidate)}>添加此图</button>
                              </div>
                            ))}
                          </div>
                        )}
                        <button className="tab" onClick={() => window.marketingOS.openAttribution('https://www.pexels.com')}>Photos provided by Pexels</button>
                      </div>
                    )}
                    {mediaNotice[a.id] && <p className="memory-evidence">{mediaNotice[a.id]}</p>}
                    {a.content && typeof a.content.body === 'string' && (
                      <div className="content-body-preview">{a.content.body}</div>
                    )}
                    {a.content && Object.keys(a.content).length > 0 && typeof a.content.body !== 'string' && (
                      <pre className="content-json">{JSON.stringify(a.content, null, 2).slice(0, 500)}</pre>
                    )}
                    {a.metrics && Object.keys(a.metrics).length > 0 && (
                      <div className="content-metrics">
                        <span className="section-eyebrow">指标数据</span>
                        {Object.entries(a.metrics).map(([k, v]) => (
                          <span key={k} className="metric-chip">{k}: {String(v)}</span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
