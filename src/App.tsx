import { useEffect, useState, type ComponentType } from 'react'
import { TooltipProvider } from '@/components/ui/tooltip'
import { AppSidebar } from '@/components/AppSidebar'
import { AgentPanel } from '@/components/AgentPanel'
import { TopBar } from '@/components/TopBar'
import Overview from '@/pages/Overview'
import Trending from '@/pages/Trending'
import Accounts from '@/pages/Accounts'
import Suggestions from '@/pages/Suggestions'
import Creator from '@/pages/Creator'
import { Analytics, Workflow } from '@/pages/Operations'
import { Memory } from '@/pages/Memory'
import { agent, runtime } from '@/api/client'
import { decodeCreativeBrief } from '@/lib/creativeBrief'

type WorkspaceProps = { onNavigate?: (page: string) => void; mode?: 'all' | 'article' | 'video' }

const PAGES: Record<string, ComponentType<WorkspaceProps>> = {
  overview: Overview,
  trending: Trending,
  ideas: Suggestions,
  factory: Creator,
  analytics: Analytics,
  workflow: Workflow,
  accounts: Accounts,
  memory: Memory,
}

export default function App() {
  const [page, setPage] = useState('overview')
  const [runtimeStatus, setRuntimeStatus] = useState('connecting')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem('marketing-sidebar-collapsed') === '1')
  const [chatSessionId, setChatSessionId] = useState<string | null>(null)
  const [newChatToken, setNewChatToken] = useState(0)
  const [chatDraft, setChatDraft] = useState('')
  const [creativeBrief, setCreativeBrief] = useState<CreativeBrief | null>(null)
  const [chatSessions, setChatSessions] = useState<AgentSessionSummary[]>([])
  const [theme, setTheme] = useState<'dark' | 'light'>(() => localStorage.getItem('marketing-theme') === 'light' ? 'light' : 'dark')

  const refreshChatSessions = () => {
    if (!window.marketingOS) return
    agent.listSessions()
      .then((result) => setChatSessions(result.sessions || []))
      .catch(() => setChatSessions([]))
  }

  useEffect(() => {
    if (!window.marketingOS) {
      setRuntimeStatus('ready')
      return
    }
    const unsubscribe = runtime.onStatus((data) => setRuntimeStatus(data.status))
    runtime.status().then((status) => setRuntimeStatus(status.running ? 'ready' : 'connecting')).catch(() => setRuntimeStatus('error'))
    return unsubscribe
  }, [])

  useEffect(() => {
    if (runtimeStatus === 'ready') refreshChatSessions()
  }, [runtimeStatus])

  const pageBase = page.startsWith('factory:') ? 'factory' : page
  const factoryMode: WorkspaceProps['mode'] = page === 'factory:article' ? 'article' : page === 'factory:video' ? 'video' : 'all'
  const PageComponent = PAGES[pageBase] || Overview
  const navigate = (nextPage: string) => {
    if (nextPage.startsWith('chat-brief:')) {
      const brief = decodeCreativeBrief(nextPage.slice('chat-brief:'.length))
      setChatSessionId(null)
      setCreativeBrief(brief)
      setChatDraft('')
      setNewChatToken((token) => token + 1)
      setPage('chat')
      return
    }
    if (nextPage.startsWith('chat-prompt:')) {
      setChatSessionId(null)
      setCreativeBrief(null)
      setChatDraft(decodeURIComponent(nextPage.slice('chat-prompt:'.length)))
      setNewChatToken((token) => token + 1)
      setPage('chat')
      return
    }
    if (nextPage.startsWith('chat-session:')) {
      setChatSessionId(nextPage.slice('chat-session:'.length))
      setChatDraft('')
      setCreativeBrief(null)
      setPage('chat')
      return
    }
    const targetPage = nextPage === 'publish' ? 'factory' : nextPage
    if (page === 'accounts' && targetPage !== 'accounts') {
      window.marketingOS?.closeAllLoginBrowsers().catch(() => {})
    }
    if (targetPage === 'chat') {
      setChatSessionId(null)
      setChatDraft('')
      setCreativeBrief(null)
      setNewChatToken((token) => token + 1)
    } else {
      refreshChatSessions()
    }
    setPage(targetPage)
  }

  return (
    <TooltipProvider delay={300}>
      <div className={`app-shell ${theme} no-agent-column ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
        <AppSidebar current={page} currentChatSessionId={chatSessionId} chatSessions={chatSessions} onNavigate={navigate} runtimeStatus={runtimeStatus} collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed((current) => {
          const next = !current; localStorage.setItem('marketing-sidebar-collapsed', next ? '1' : '0'); return next
        })} />
        <TopBar page={page} onNavigate={navigate} theme={theme} onToggleTheme={() => setTheme((current) => {
          const next = current === 'dark' ? 'light' : 'dark'
          localStorage.setItem('marketing-theme', next)
          return next
        })} />
        <main className={`workspace ${pageBase === 'overview' ? 'workspace-dashboard' : ''} ${pageBase === 'chat' ? 'workspace-chat' : ''}`}>
          <div className="workspace-inner">
            {page === 'chat'
              ? <ChatWorkspace status={runtimeStatus} sessionId={chatSessionId} newChatToken={newChatToken} initialPrompt={chatDraft} creativeBrief={creativeBrief} onSessionChange={(id) => { setChatSessionId(id); refreshChatSessions() }} onSessionsChanged={refreshChatSessions} />
              : <PageComponent key={page} onNavigate={navigate} mode={factoryMode} />}
          </div>
        </main>
      </div>
    </TooltipProvider>
  )
}

function ChatWorkspace({ status, sessionId, newChatToken, initialPrompt, creativeBrief, onSessionChange, onSessionsChanged }: {
  status: string
  sessionId: string | null
  newChatToken: number
  initialPrompt: string
  creativeBrief: CreativeBrief | null
  onSessionChange: (id: string) => void
  onSessionsChanged: () => void
}) {
  return (
    <div className="chat-workspace">
      <AgentPanel page="chat" status={status} sessionId={sessionId} newChatToken={newChatToken} initialPrompt={initialPrompt} creativeBrief={creativeBrief} onSessionChange={onSessionChange} onSessionsChanged={onSessionsChanged} />
    </div>
  )
}
