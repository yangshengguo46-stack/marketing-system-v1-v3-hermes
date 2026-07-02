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
import { Analytics, PublishCenter, Workflow } from '@/pages/Operations'
import { Memory } from '@/pages/Memory'
import { hermes } from '@/api/client'

type WorkspaceProps = { onNavigate?: (page: string) => void }

const PAGES: Record<string, ComponentType<WorkspaceProps>> = {
  overview: Overview,
  trending: Trending,
  ideas: Suggestions,
  factory: Creator,
  publish: PublishCenter,
  analytics: Analytics,
  workflow: Workflow,
  accounts: Accounts,
  memory: Memory,
}

export default function App() {
  const [page, setPage] = useState('overview')
  const [hermesStatus, setHermesStatus] = useState('connecting')

  useEffect(() => {
    if (!window.marketingOS) {
      setHermesStatus('ready')
      return
    }
    const unsubscribe = hermes.onStatus((data) => setHermesStatus(data.status))
    hermes.status().then((status) => setHermesStatus(status.running ? 'ready' : 'connecting')).catch(() => setHermesStatus('error'))
    return unsubscribe
  }, [])

  const PageComponent = PAGES[page] || Overview
  const navigate = (nextPage: string) => {
    if (page === 'accounts' && nextPage !== 'accounts') {
      window.marketingOS?.closeAllLoginBrowsers().catch(() => {})
    }
    setPage(nextPage)
  }

  return (
    <TooltipProvider delay={300}>
      <div className="app-shell dark">
        <AppSidebar current={page} onNavigate={navigate} hermesStatus={hermesStatus} />
        <TopBar page={page} />
        <main className="workspace">
          <div className="workspace-inner"><PageComponent key={page} onNavigate={navigate} /></div>
        </main>
        <AgentPanel page={page} status={hermesStatus} />
      </div>
    </TooltipProvider>
  )
}
