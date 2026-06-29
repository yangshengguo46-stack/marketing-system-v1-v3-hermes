import {
  BarChart3,
  CalendarClock,
  Clapperboard,
  Flame,
  LayoutDashboard,
  Lightbulb,
  Network,
  Users,
} from 'lucide-react'

const NAV_ITEMS = [
  { id: 'overview', label: '工作台', icon: LayoutDashboard },
  { id: 'trending', label: '趋势中心', icon: Flame },
  { id: 'ideas', label: '创意中心', icon: Lightbulb },
  { id: 'factory', label: '内容工厂', icon: Clapperboard },
  { id: 'publish', label: '发布中心', icon: CalendarClock },
  { id: 'analytics', label: '数据分析', icon: BarChart3 },
  { id: 'workflow', label: '自动化', icon: Network },
  { id: 'accounts', label: '账号管理', icon: Users },
]

export function AppSidebar({ current, onNavigate, hermesStatus }: {
  current: string
  onNavigate: (id: string) => void
  hermesStatus: string
}) {
  const online = hermesStatus === 'ready'

  return (
    <aside className="app-sidebar" style={{ WebkitAppRegion: 'drag' } as React.CSSProperties}>
      <div className="sidebar-brand">
        <div className="brand-mark">M</div>
        <div className="min-w-0">
          <div className="brand-name">Marketing OS</div>
          <div className="brand-subtitle">智能营销操作系统</div>
        </div>
      </div>

      <nav className="sidebar-nav" style={{ WebkitAppRegion: 'no-drag' } as React.CSSProperties}>
        <div className="nav-label">工作空间</div>
        {NAV_ITEMS.map((item) => {
          const active = current === item.id
          return (
            <button
              key={item.id}
              className={`nav-item ${active ? 'is-active' : ''}`}
              onClick={() => onNavigate(item.id)}
              title={item.label}
            >
              <item.icon size={17} strokeWidth={active ? 2.2 : 1.8} />
              <span>{item.label}</span>
              {item.id === 'publish' && <span className="nav-count">3</span>}
            </button>
          )
        })}
      </nav>

      <div className="sidebar-footer" style={{ WebkitAppRegion: 'no-drag' } as React.CSSProperties}>
        <div className="engine-status">
          <span className={`status-dot ${online ? 'is-online' : hermesStatus === 'connecting' ? 'is-connecting' : ''}`} />
          <div>
            <div className="engine-title">AI 引擎</div>
            <div className="engine-copy">{online ? '7 个工具在线' : hermesStatus === 'connecting' ? '正在连接' : '暂时离线'}</div>
          </div>
        </div>
      </div>
    </aside>
  )
}
