import type { CSSProperties } from 'react'

type DragStyle = CSSProperties & { WebkitAppRegion?: 'drag' | 'no-drag' }

const TABS = [
  { id: 'overview', label: '概览', icon: OverviewIcon },
  { id: 'trending', label: '热点趋势', icon: TrendingIcon },
  { id: 'accounts', label: '账号管理', icon: AccountsIcon },
  { id: 'suggestions', label: '选题建议', icon: SuggestionsIcon },
  { id: 'creator', label: '创作工作台', icon: CreatorIcon },
]

export default function Sidebar({ current, onNavigate, hermesStatus }: {
  current: string; onNavigate: (id: string) => void; hermesStatus: string
}) {
  return (
    <aside className="w-[228px] min-w-[228px] h-screen flex flex-col border-r border-white/[0.04] select-none"
           style={{ WebkitAppRegion: 'drag' } as DragStyle}>
      {/* Logo area */}
      <div className="px-5 pt-8 pb-7">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-[14px] flex items-center justify-center"
               style={{ background: 'linear-gradient(135deg, #FE2C55, #FF0050)' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="white"><path d="M22.46 6.86c-.42-1.02-1.01-1.77-2.64-2.08-1.77-.34-3.88.23-5.9 1.6-2.64 1.8-4.98 4.96-7.32 8.42l-.3.45c-.58.88-1.25 1.92-1.92 2.88-.51.73-1.48 1.1-2.24.7-.49-.26-.73-.84-.64-1.38.04-.25.14-.48.3-.68l3.6-4.8c.48-.66.76-1.46.76-2.28V6.4C6.06 4.4 7.66 2.8 9.66 2.8c1.84 0 3.36 1.38 3.56 3.16.02.18.02.36.02.54v4.9c1.5-1.38 2.9-2.42 4.1-3.06 1.66-.9 3.26-1.26 4.54-.98.38.08.7.28.92.58.32.44.38.98.16 1.48l-.5 1.44Z"/></svg>
          </div>
          <div>
            <h1 className="text-[16px] font-extrabold text-white tracking-tight leading-none">智能营销</h1>
            <p className="text-[10px] text-white/25 mt-0.5 leading-none font-medium">Marketing OS</p>
          </div>
        </div>
      </div>

      {/* Status */}
      <div className="px-4 pb-6" style={{ WebkitAppRegion: 'no-drag' } as DragStyle}>
        <div className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl bg-white/[0.03] border border-white/[0.05]">
          <div className="relative">
            <span className={`block w-2.5 h-2.5 rounded-full ${
              hermesStatus === 'ready' ? 'bg-[#25F4EE]' : hermesStatus === 'connecting' ? 'bg-amber-400' : 'bg-red-400'
            }`} />
            {hermesStatus === 'ready' && (
              <span className="absolute inset-0 w-2.5 h-2.5 rounded-full bg-[#25F4EE] animate-live" />
            )}
          </div>
          <span className="text-[11px] text-white/35 font-medium">
            {hermesStatus === 'ready' ? '引擎就绪' : hermesStatus === 'connecting' ? '连接中...' : '已离线'}
          </span>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 flex flex-col gap-0.5 px-3" style={{ WebkitAppRegion: 'no-drag' } as DragStyle}>
        {TABS.map((t) => {
          const active = current === t.id
          return (
            <button key={t.id} onClick={() => onNavigate(t.id)}
              className={`group flex items-center gap-3 px-3.5 py-2.5 rounded-[14px] text-[13px] text-left transition-all duration-200 cursor-pointer border-none relative overflow-hidden
                ${active
                  ? 'text-white font-semibold'
                  : 'text-white/35 hover:text-white/70 font-medium'
                }`}
            >
              {active && (
                <div className="absolute inset-0 rounded-[14px]" style={{ background: 'linear-gradient(135deg, rgba(254,44,85,0.12), rgba(37,244,238,0.06))' }} />
              )}
              <span className={`relative z-10 w-5 h-5 flex items-center justify-center ${active ? '' : 'group-hover:text-white/60'}`}>
                <t.icon />
              </span>
              <span className="relative z-10 flex-1">{t.label}</span>
              {active && <span className="relative z-10 w-1 h-1 rounded-full bg-[#FE2C55]" />}
            </button>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-white/[0.04]">
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-white/15 font-medium">v0.2.0</span>
          <span className="text-[10px] text-white/15 font-medium">7 tools</span>
        </div>
      </div>
    </aside>
  )
}

/* SVG Icons — minimal style */
function OverviewIcon() { return (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="7" height="9" rx="2"/><rect x="14" y="3" width="7" height="5" rx="2"/>
    <rect x="14" y="12" width="7" height="9" rx="2"/><rect x="3" y="16" width="7" height="5" rx="2"/>
  </svg>
)}
function TrendingIcon() { return (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>
  </svg>
)}
function AccountsIcon() { return (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/>
    <path d="M22 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/>
  </svg>
)}
function SuggestionsIcon() { return (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/>
  </svg>
)}
function CreatorIcon() { return (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
  </svg>
)}
