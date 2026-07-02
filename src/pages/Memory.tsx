import { useEffect, useState } from 'react'
import { Trash2, Database, Shield, ShieldCheck, User, Building, Lightbulb, FileText, Zap, Check, Lock, Unlock, Pencil, X } from 'lucide-react'
import { api } from '@/api/client'

const KIND_ICONS: Record<string, typeof User> = {
  user: User, account: Building, episodic: FileText, semantic: Lightbulb, procedural: Zap,
}
const KIND_LABELS: Record<string, string> = {
  user: '用户记忆', account: '账号DNA', episodic: '项目记忆', semantic: '知识', procedural: '技能',
}
const KINDS = Object.keys(KIND_LABELS)

export function Memory() {
  const [pageTab, setPageTab] = useState<'memories' | 'auth'>('memories')
  const [memories, setMemories] = useState<MemoryEntry[]>([])
  const [tab, setTab] = useState('all')
  const [loading, setLoading] = useState(true)
  const [authorizations, setAuthorizations] = useState<Array<{id: string; capability: string; granted_at: string; constraints?: Record<string, unknown>}>>([])
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingContent, setEditingContent] = useState('')

  const fetchMemories = async () => {
    setLoading(true)
    try {
      const kind = tab === 'all' ? undefined : tab
      const result = await api.memories(kind)
      setMemories((result as MemoryEntry[]) || [])
    } catch {
      setMemories([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchMemories() }, [tab])

  const fetchAuthorizations = async () => {
    try {
      const result = await api.authorizations()
      setAuthorizations((result as Array<{id: string; capability: string; granted_at: string; constraints?: Record<string, unknown>}>) || [])
    } catch { setAuthorizations([]) }
  }
  useEffect(() => { fetchAuthorizations() }, [pageTab])

  const handleRevokeAuth = async (capability: string) => {
    try { await api.revokeAuthorization(capability); fetchAuthorizations() } catch {}
  }

  const handleDelete = async (id: string) => {
    try {
      await api.deleteMemory(id)
      setMemories((current) => current.filter((m) => m.id !== id))
    } catch {}
  }

  const handleUpdate = async (id: string, data: { status?: string; content?: string }) => {
    try {
      await api.updateMemory(id, data)
      setEditingId(null)
      await fetchMemories()
    } catch {}
  }

  return (
    <div className="memory-page">
      <div className="standard-page-header">
        <div>
          <h1>记忆与知识</h1>
          <p>候选记忆先确认再生效；你可以纠正、锁定或遗忘每一条记录</p>
        </div>
      </div>

      <div className="memory-page-tabs">
        <button className={`tab ${pageTab === 'memories' ? 'active' : ''}`} onClick={() => setPageTab('memories')}>
          <Database size={13} /> 记忆
        </button>
        <button className={`tab ${pageTab === 'auth' ? 'active' : ''}`} onClick={() => setPageTab('auth')}>
          <Shield size={13} /> 授权管理
        </button>
      </div>

      {pageTab === 'auth' && (
        <div>
          {authorizations.length === 0 ? (
            <p className="memory-empty">暂无永久授权。Agent 请求敏感操作时可以选择"永久记住"来添加。</p>
          ) : (
            <div className="memory-list">
              {authorizations.map((a) => (
                <div key={a.id} className="memory-card">
                  <div className="memory-card-header">
                    <span className="memory-kind-badge procedural"><ShieldCheck size={10} /> 已授权</span>
                    <code style={{fontSize:9,color:'rgba(255,255,255,.5)'}}>{a.capability}</code>
                    <button className="icon-button small" onClick={() => handleRevokeAuth(a.capability)} title="撤销">
                      <Trash2 size={11} />
                    </button>
                  </div>
                  <p className="memory-content" style={{fontSize:9}}>授予时间：{new Date(a.granted_at).toLocaleString()}</p>
                  {a.constraints && Object.keys(a.constraints).length > 0 && (
                    <div className="memory-evidence">
                      {Object.entries(a.constraints).map(([key, value]) => <span key={key}>{key}: {String(value)}</span>)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {pageTab === 'memories' && (<>
      <div className="memory-tabs">
        <button className={`tab ${tab === 'all' ? 'active' : ''}`} onClick={() => setTab('all')}>
          <Database size={12} /> 全部
        </button>
        {KINDS.map((k) => (
          <button key={k} className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>
            {(() => { const Icon = KIND_ICONS[k] || Database; return <Icon size={12} /> })()}
            {KIND_LABELS[k]}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="memory-empty">加载中…</p>
      ) : memories.length === 0 ? (
        <p className="memory-empty">暂无记录。Agent 会在对话中自动沉淀记忆。</p>
      ) : (
        <div className="memory-list">
          {memories.map((m) => (
            <div key={m.id} className={`memory-card ${m.status === 'rejected' ? 'rejected' : ''}`}>
              <div className="memory-card-header">
                <span className={`memory-kind-badge ${m.kind}`}>
                  {(() => { const Icon = KIND_ICONS[m.kind] || Database; return <Icon size={10} /> })()}
                  {KIND_LABELS[m.kind] || m.kind}
                </span>
                {m.account_id && <span className="memory-account">{m.account_id}</span>}
                <span className={`memory-status ${m.status}`}>{m.status === 'pending' ? '待确认' : m.status === 'verified' ? '已确认' : m.status === 'locked' ? '已锁定' : m.status === 'rejected' ? '已拒绝' : m.status}</span>
                {m.confidence < 0.8 && <span className="memory-confidence">置信度 {Math.round(m.confidence * 100)}%</span>}
                {m.status === 'pending' && <button className="icon-button small" onClick={() => handleUpdate(m.id, { status: 'verified' })} title="确认记忆"><Check size={11} /></button>}
                {m.status === 'verified' && <button className="icon-button small" onClick={() => handleUpdate(m.id, { status: 'locked' })} title="锁定记忆"><Lock size={11} /></button>}
                {m.status === 'locked' && <button className="icon-button small" onClick={() => handleUpdate(m.id, { status: 'verified' })} title="解除锁定"><Unlock size={11} /></button>}
                <button className="icon-button small" onClick={() => { setEditingId(m.id); setEditingContent(m.content) }} title="纠正">
                  <Pencil size={11} />
                </button>
                <button className="icon-button small" onClick={() => handleDelete(m.id)} title="删除">
                  <Trash2 size={11} />
                </button>
              </div>
              {editingId === m.id ? (
                <div className="memory-editor">
                  <textarea value={editingContent} onChange={(event) => setEditingContent(event.target.value)} rows={3} />
                  <button onClick={() => handleUpdate(m.id, { content: editingContent, status: m.status === 'rejected' ? 'verified' : undefined })}><Check size={11} />保存</button>
                  <button onClick={() => setEditingId(null)}><X size={11} />取消</button>
                </div>
              ) : <p className="memory-content">{m.content}</p>}
              {m.evidence && m.evidence.length > 0 && (
                <div className="memory-evidence">
                  {m.evidence.slice(0, 3).map((e, i) => (
                    <span key={i}>{typeof e.source === 'string' ? e.source : JSON.stringify(e).slice(0, 60)}</span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      </>)}
    </div>
  )
}
