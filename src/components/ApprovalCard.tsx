import { useState } from 'react'
import { Check, Loader2, ShieldAlert, X } from 'lucide-react'
import { agent } from '@/api/client'

interface Props {
  approvalId: string
  capability: string
  args: Record<string, unknown>
  riskSummary: string
  onSettled: (approved: boolean, error?: string) => void
  onClose: () => void
}

const CAPABILITY_LABELS: Record<string, string> = {
  marketing_trending_search: '行业搜索',
  marketing_session_login: '平台登录',
  marketing_accounts_sync: '账号同步',
}

export function ApprovalCard({ approvalId, capability, args, riskSummary, onSettled, onClose }: Props) {
  const [state, setState] = useState<'idle' | 'executing' | 'completed' | 'rejected' | 'error'>('idle')
  const [errorMsg, setErrorMsg] = useState('')

  const label = CAPABILITY_LABELS[capability] || capability

  const handleApprove = async (scope: 'once' | 'session' | 'permanent') => {
    setState('executing')
    try {
      await agent.executeCapability(approvalId, scope)
      setState('completed')
      onSettled(true)
    } catch (err) {
      setState('error')
      setErrorMsg((err as Error).message || '执行失败')
    }
  }

  const handleReject = async () => {
    try {
      await agent.rejectAction(approvalId, '用户拒绝')
      setState('rejected')
      onSettled(false)
    } catch (err) {
      setErrorMsg((err as Error).message || '拒绝失败')
    }
  }

  if (state === 'completed' || state === 'rejected') {
    return (
      <div className={`approval-card ${state}`}>
        <div className="approval-card-header">
          <ShieldAlert size={14} />
          <span>{state === 'completed' ? '已授权' : '已拒绝'} — {label}</span>
          <button className="icon-button small" onClick={onClose}><X size={12} /></button>
        </div>
      </div>
    )
  }

  return (
    <div className={`approval-card ${state}`}>
      <div className="approval-card-header">
        <ShieldAlert size={14} />
        <span>需要确认 — {label}</span>
      </div>
      <div className="approval-card-body">
        <p className="approval-risk">{riskSummary}</p>
        {Object.keys(args).length > 0 && (
          <ul className="approval-args">
            {Object.entries(args).map(([key, val]) => (
              <li key={key}><code>{key}</code> {String(val)}</li>
            ))}
          </ul>
        )}
      </div>
      {state === 'error' && <p className="approval-error">{errorMsg}</p>}
      <div className="approval-card-footer">
        <button className="btn-approve-once" onClick={() => handleApprove('once')} disabled={state === 'executing'}>
          {state === 'executing' ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
          仅本次
        </button>
        <button className="btn-approve-session" onClick={() => handleApprove('session')} disabled={state === 'executing'}>
          本次对话
        </button>
        <button className="btn-approve-permanent" onClick={() => handleApprove('permanent')} disabled={state === 'executing'}>
          永久记住
        </button>
        <button className="btn-reject" onClick={handleReject} disabled={state === 'executing'}>
          <X size={12} /> 拒绝
        </button>
      </div>
    </div>
  )
}
