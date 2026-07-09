import { Bell, Brain, Database, Moon, Search, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '@/api/client'

const PAGE_NAMES: Record<string, string> = {
  overview: '工作台',
  chat: '新对话',
  trending: '趋势中心',
  ideas: '创意中心',
  factory: '内容工厂',
  'factory:article': '图文创作',
  'factory:video': '视频创作',
  analytics: '数据分析',
  workflow: '自动化',
  accounts: '账号管理',
  memory: '记忆治理',
}

export function TopBar({ page, onNavigate, theme = 'dark', onToggleTheme }: {
  page: string
  onNavigate?: (page: string) => void
  theme?: 'dark' | 'light'
  onToggleTheme?: () => void
}) {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [firecrawlConfigured, setFirecrawlConfigured] = useState(false)
  const [firecrawlMode, setFirecrawlMode] = useState('cloud')
  const [firecrawlKey, setFirecrawlKey] = useState('')
  const [notice, setNotice] = useState('')
  useEffect(() => {
    if (!settingsOpen) return
    api.firecrawlStatus().then((status) => {
      setFirecrawlConfigured(status.configured); setFirecrawlMode(status.mode)
    }).catch(() => setFirecrawlConfigured(false))
  }, [settingsOpen])
  const saveFirecrawlKey = async () => {
    try {
      await window.marketingOS.setProviderSecret('FIRECRAWL_API_KEY', firecrawlKey)
      setFirecrawlKey(''); setFirecrawlConfigured(true); setNotice('Firecrawl 密钥已加密保存，本地后端已重启')
    } catch (error) { setNotice(`保存失败：${String((error as Error)?.message || error)}`) }
  }
  return (
    <header className="top-bar" style={{ WebkitAppRegion: 'drag' } as React.CSSProperties}>
      <div className="page-location">
        <span>Marketing OS</span>
        <span className="location-slash">/</span>
        <strong>{PAGE_NAMES[page] || '工作台'}</strong>
      </div>

      <button className="global-search" style={{ WebkitAppRegion: 'no-drag' } as React.CSSProperties}>
        <Search size={15} />
        <span>搜索热点、内容或账号</span>
        <kbd>⌘ K</kbd>
      </button>

      <div className="top-actions" style={{ WebkitAppRegion: 'no-drag' } as React.CSSProperties}>
        <button className="source-trigger" onClick={() => setSettingsOpen(!settingsOpen)}>
          <Database size={13} />
          <span>研究数据源</span>
        </button>
        <button className="icon-button" title={theme === 'dark' ? '切换白天模式' : '切换夜间模式'} onClick={onToggleTheme}>
          {theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}
        </button>
        <button className="icon-button" title="通知"><Bell size={17} /></button>
        <button className="user-avatar" title="个人账号">杨</button>
      </div>
      {settingsOpen && (
        <div className="memory-card source-popover" style={{ WebkitAppRegion: 'no-drag' } as React.CSSProperties}>
          <div className="memory-card-header"><strong>研究数据源</strong><button className="icon-button small" onClick={() => setSettingsOpen(false)}>×</button></div>
          <p className="memory-content">Firecrawl · {firecrawlConfigured ? `已连接（${firecrawlMode === 'self_hosted' ? '本地' : '云端'}）` : '尚未配置'}</p>
          {!firecrawlConfigured && (
            <div className="content-create-bar">
              <input type="password" value={firecrawlKey} onChange={(event) => setFirecrawlKey(event.target.value)} placeholder="Firecrawl 免费 API Key" />
              <button className="tab active" onClick={saveFirecrawlKey}>保存</button>
            </div>
          )}
          <p className="memory-evidence">未来安装本地 Firecrawl 后可切换到 127.0.0.1:3002，上层 Agent 工具无需修改。</p>
          <button
            className="source-secondary-action"
            onClick={() => {
              setSettingsOpen(false)
              onNavigate?.('memory')
            }}
          >
            <Brain size={13} />
            <span>打开记忆治理</span>
          </button>
          {notice && <p className="memory-evidence">{notice}</p>}
        </div>
      )}
    </header>
  )
}
