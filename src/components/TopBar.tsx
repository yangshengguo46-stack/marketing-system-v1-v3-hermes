import { Bell, Search, Settings2 } from 'lucide-react'

const PAGE_NAMES: Record<string, string> = {
  overview: '工作台',
  trending: '趋势中心',
  ideas: '创意中心',
  factory: '内容工厂',
  publish: '发布中心',
  analytics: '数据分析',
  workflow: '自动化',
  accounts: '账号管理',
}

export function TopBar({ page }: { page: string }) {
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
        <button className="icon-button" title="通知"><Bell size={17} /></button>
        <button className="icon-button" title="设置"><Settings2 size={17} /></button>
        <button className="user-avatar" title="个人账号">杨</button>
      </div>
    </header>
  )
}
