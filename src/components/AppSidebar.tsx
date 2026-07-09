import {
  ChevronDown,
  Clapperboard,
  FileText,
  Film,
  History,
  LayoutDashboard,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  Users,
} from 'lucide-react'
import { useState } from 'react'

const NAV_ITEMS = [
  { id: 'overview', label: '工作台', icon: LayoutDashboard },
  { id: 'chat', label: '新对话', icon: MessageSquarePlus },
  { id: 'factory', label: '内容工厂', icon: Clapperboard },
  { id: 'accounts', label: '账号管理', icon: Users },
]

const FACTORY_SUBNAV = [
  { id: 'factory:article', label: '图文创作', icon: FileText },
  { id: 'factory:video', label: '视频创作', icon: Film },
]

export function AppSidebar({ current, currentChatSessionId, chatSessions = [], onNavigate, runtimeStatus, collapsed, onToggle }: {
  current: string
  currentChatSessionId?: string | null
  chatSessions?: AgentSessionSummary[]
  onNavigate: (id: string) => void
  runtimeStatus: string
  collapsed: boolean
  onToggle: () => void
}) {
  const online = runtimeStatus === 'ready'
  const [factorySubnavOpen, setFactorySubnavOpen] = useState(() => localStorage.getItem('marketing-factory-subnav-collapsed') !== '1')
  const toggleFactorySubnav = () => {
    setFactorySubnavOpen((current) => {
      const next = !current
      localStorage.setItem('marketing-factory-subnav-collapsed', next ? '0' : '1')
      return next
    })
  }

  return (
    <aside className={`app-sidebar ${collapsed ? 'is-collapsed' : ''}`} style={{ WebkitAppRegion: 'drag' } as React.CSSProperties}>
      <div className="sidebar-brand">
        <div className="brand-mark">M</div>
        <div className="min-w-0">
          <div className="brand-name">Marketing OS</div>
          <div className="brand-subtitle">智能营销操作系统</div>
        </div>
        <button className="sidebar-toggle" onClick={onToggle} title={collapsed ? '展开导航' : '收起导航'} style={{ WebkitAppRegion: 'no-drag' } as React.CSSProperties}>{collapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}</button>
      </div>

      <nav className="sidebar-nav" style={{ WebkitAppRegion: 'no-drag' } as React.CSSProperties}>
        <div className="nav-label">工作空间</div>
        {NAV_ITEMS.map((item) => {
          const active = current === item.id || current.startsWith(`${item.id}:`)
          return (
            <div className="nav-item-group" key={item.id}>
              <button
                className={`nav-item ${active ? 'is-active' : ''} ${item.id === 'factory' && !collapsed ? 'has-fold-toggle' : ''}`}
                onClick={() => onNavigate(item.id)}
                title={item.label}
              >
                <item.icon size={17} strokeWidth={active ? 2.2 : 1.8} />
                <span>{item.label}</span>
              </button>
              {item.id === 'factory' && !collapsed && (
                <button
                  className={`nav-fold-toggle ${factorySubnavOpen ? 'is-open' : ''}`}
                  onClick={(event) => { event.stopPropagation(); toggleFactorySubnav() }}
                  title={factorySubnavOpen ? '收起内容工厂目录' : '展开内容工厂目录'}
                  aria-label={factorySubnavOpen ? '收起内容工厂目录' : '展开内容工厂目录'}
                >
                  <ChevronDown size={13} />
                </button>
              )}
              {item.id === 'factory' && !collapsed && factorySubnavOpen && (
                <div className="nav-subitems">
                  {FACTORY_SUBNAV.map((subitem) => {
                    const subActive = current === subitem.id
                    return (
                      <button
                        key={subitem.id}
                        className={`nav-item nav-subitem ${subActive ? 'is-active' : ''}`}
                        onClick={() => onNavigate(subitem.id)}
                        title={subitem.label}
                      >
                        <subitem.icon size={14} strokeWidth={subActive ? 2.1 : 1.8} />
                        <span>{subitem.label}</span>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
        {collapsed && Boolean(chatSessions?.length) && (
          <button
            className={`nav-item chat-history-collapsed ${currentChatSessionId ? 'is-history-active' : ''}`}
            onClick={() => onNavigate(`chat-session:${chatSessions![0].session_id}`)}
            title="历史会话"
          >
            <History size={17} strokeWidth={1.9} />
            <span>历史会话</span>
          </button>
        )}
        {!collapsed && Boolean(chatSessions?.length) && (
          <div className="chat-history-nav">
            <div className="nav-label">历史会话</div>
            {chatSessions!.map((session) => (
              <button
                key={session.session_id}
                className={`chat-history-item ${currentChatSessionId === session.session_id ? 'is-active' : ''}`}
                onClick={() => onNavigate(`chat-session:${session.session_id}`)}
                title={session.last_objective || session.title}
              >
                <span>{session.title || '新对话'}</span>
                <small>{session.last_task_status || 'empty'}</small>
              </button>
            ))}
          </div>
        )}
      </nav>

      <div className="sidebar-footer" style={{ WebkitAppRegion: 'no-drag' } as React.CSSProperties}>
        <div className="engine-status">
          <span className={`status-dot ${online ? 'is-online' : runtimeStatus === 'connecting' ? 'is-connecting' : ''}`} />
          <div>
            <div className="engine-title">AI 引擎</div>
            <div className="engine-copy">{online ? '营销工具集在线' : runtimeStatus === 'connecting' ? '正在连接' : '暂时离线'}</div>
          </div>
        </div>
      </div>
    </aside>
  )
}
