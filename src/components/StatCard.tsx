import type { ReactElement } from 'react'

export default function StatCard({ label, value, unit, icon: Icon, trend, color = 'pink' }: {
  label: string; value: string | number; unit?: string; icon?: () => ReactElement
  trend?: { val: string; up: boolean }; color?: 'pink' | 'cyan' | 'purple' | 'green'
}) {
  const gradients: Record<string, string> = {
    pink: 'linear-gradient(135deg, rgba(254,44,85,0.1), rgba(254,44,85,0.03))',
    cyan: 'linear-gradient(135deg, rgba(37,244,238,0.1), rgba(37,244,238,0.03))',
    purple: 'linear-gradient(135deg, rgba(139,92,246,0.1), rgba(139,92,246,0.03))',
    green: 'linear-gradient(135deg, rgba(34,197,94,0.1), rgba(34,197,94,0.03))',
  }
  const borders: Record<string, string> = {
    pink: 'rgba(254,44,85,0.15)', cyan: 'rgba(37,244,238,0.15)',
    purple: 'rgba(139,92,246,0.15)', green: 'rgba(34,197,94,0.15)',
  }
  const iconColors: Record<string, string> = {
    pink: 'text-[#FE2C55] bg-[#FE2C55]/8', cyan: 'text-[#25F4EE] bg-[#25F4EE]/8',
    purple: 'text-[#a78bfa] bg-[#a78bfa]/8', green: 'text-[#22c55e] bg-[#22c55e]/8',
  }

  return (
    <div className="relative overflow-hidden rounded-[20px] p-5 transition-all duration-300 hover:-translate-y-0.5 group cursor-default"
         style={{ background: gradients[color], border: `1px solid ${borders[color]}`, backdropFilter: 'blur(20px)' }}>
      {/* Top row */}
      <div className="flex items-start justify-between mb-4">
        <span className="text-[11px] font-semibold text-white/30 uppercase tracking-widest">{label}</span>
        {Icon && (
          <span className={`w-9 h-9 rounded-[14px] flex items-center justify-center ${iconColors[color]}`}>
            <Icon />
          </span>
        )}
      </div>
      {/* Value */}
      <div className="flex items-baseline gap-1">
        <span className="text-[30px] font-extrabold text-white tracking-tight leading-none">{value}</span>
        {unit && <span className="text-[13px] text-white/25 font-semibold">{unit}</span>}
      </div>
      {/* Trend */}
      {trend && (
        <div className={`flex items-center gap-1.5 mt-2.5 text-[11px] font-semibold ${trend.up ? 'text-[#22c55e]' : 'text-[#FE2C55]'}`}>
          <span>{trend.up ? '↑' : '↓'}</span>
          <span>{trend.val}</span>
        </div>
      )}
      {/* Glow orb */}
      <div className="absolute -top-10 -right-10 w-28 h-28 rounded-full opacity-[0.04] group-hover:opacity-[0.08] transition-opacity pointer-events-none"
           style={{ background: `radial-gradient(circle, ${color === 'pink' ? '#FE2C55' : color === 'cyan' ? '#25F4EE' : color === 'purple' ? '#8b5cf6' : '#22c55e'}, transparent 70%)` }} />
    </div>
  )
}

export function EmptyState({ icon: Icon, title, desc, action }: {
  icon?: () => ReactElement; title: string; desc: string; action?: { label: string; onClick: () => void }
}) {
  return (
    <div className="flex flex-col items-center justify-center py-20 px-8">
      {Icon && (
        <div className="w-20 h-20 rounded-[24px] bg-white/[0.02] border border-white/[0.04] flex items-center justify-center mb-6 text-white/15">
          <Icon />
        </div>
      )}
      <h3 className="text-[16px] font-bold text-white mb-2">{title}</h3>
      <p className="text-[13px] text-white/25 text-center max-w-[360px] mb-8 leading-relaxed">{desc}</p>
      {action && (
        <button onClick={action.onClick}
          className="px-6 py-3 rounded-[14px] text-[13px] font-bold text-white cursor-pointer border-none transition-all duration-200 hover:scale-105"
          style={{ background: 'linear-gradient(135deg, #FE2C55, #FF0050)' }}>
          {action.label}
        </button>
      )}
    </div>
  )
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center py-20">
      <div className="flex gap-1.5">
        {[0, 1, 2].map(i => (
          <div key={i} className="w-2 h-2 rounded-full bg-white/20 animate-bounce" style={{ animationDelay: `${i * 0.12}s` }} />
        ))}
      </div>
    </div>
  )
}
