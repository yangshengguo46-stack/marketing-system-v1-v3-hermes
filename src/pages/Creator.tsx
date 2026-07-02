import { useEffect, useState } from 'react'
import { Check, ChevronRight, Circle, FileText, Film, Image, PenTool, Plus, Trash2, X } from 'lucide-react'
import { api } from '@/api/client'

interface ContentAsset {
  id: string; title: string; type: string; status: string
  platform?: string; account_id?: string; version: number
  content: Record<string, unknown>; metrics: Record<string, unknown>
  created_at: string; updated_at: string
}

const TYPE_ICONS: Record<string, typeof FileText> = { script: FileText, video: Film, image: Image, caption: PenTool }
const TYPE_LABELS: Record<string, string> = { script: '脚本', video: '视频', image: '图片', caption: '文案' }
const STATUS_LABELS: Record<string, string> = { draft: '草稿', review: '待审', approved: '已通过', published: '已发布', metrics_collected: '有数据', archived: '已归档' }
const STATUS_COLORS: Record<string, string> = { draft: '#6b7280', review: '#f59e0b', approved: '#3b82f6', published: '#62c4a0', metrics_collected: '#8b5cf6', archived: '#4b5563' }
const STATUSES = ['', 'draft', 'review', 'approved', 'published']

export default function Creator() {
  const [assets, setAssets] = useState<ContentAsset[]>([])
  const [filter, setFilter] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newType, setNewType] = useState('script')
  const [expanded, setExpanded] = useState<string | null>(null)

  const fetchAssets = async () => {
    try {
      const status = filter || undefined
      const result = await api.contentAssets(status)
      setAssets((result as ContentAsset[]) || [])
    } catch { setAssets([]) }
  }
  useEffect(() => { fetchAssets() }, [filter])

  const handleCreate = async () => {
    if (!newTitle.trim()) return
    try {
      await api.createContentAsset({ title: newTitle, type: newType })
      setNewTitle(''); setShowCreate(false)
      fetchAssets()
    } catch {}
  }

  const handleStatus = async (id: string, status: string) => {
    try { await api.transitionContentAsset(id, status); fetchAssets() } catch {}
  }

  const handleDelete = async (id: string) => {
    try { await api.deleteContentAsset(id); fetchAssets() } catch {}
  }

  return (
    <div className="factory-page animate-fade-up">
      <div className="standard-page-header">
        <div><h1>内容资产</h1><p>选题→草稿→审批→发布→指标回收 全链路管理</p></div>
        <button className="primary-action" onClick={() => setShowCreate(true)}><Plus size={15} /> 新建草稿</button>
      </div>

      {showCreate && (
        <div className="content-create-bar">
          <input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} placeholder="标题…" onKeyDown={(e) => e.key === 'Enter' && handleCreate()} />
          <select value={newType} onChange={(e) => setNewType(e.target.value)}>
            {Object.entries(TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <button className="primary-action" onClick={handleCreate}>创建</button>
          <button className="icon-button" onClick={() => setShowCreate(false)}><X size={14} /></button>
        </div>
      )}

      <div className="memory-tabs">
        {STATUSES.map((s) => (
          <button key={s || 'all'} className={`tab ${filter === s ? 'active' : ''}`} onClick={() => setFilter(s)}>
            {s ? STATUS_LABELS[s] : '全部'}
          </button>
        ))}
      </div>

      {assets.length === 0 ? (
        <p className="memory-empty">暂无内容资产。点击"新建草稿"或让 Agent 帮你创建选题和脚本。</p>
      ) : (
        <div className="memory-list">
          {assets.map((a) => {
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
                      {a.status === 'approved' && <button className="tab active" onClick={() => handleStatus(a.id, 'published')}>标记已发布</button>}
                    </div>
                    {a.content && Object.keys(a.content).length > 0 && (
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
