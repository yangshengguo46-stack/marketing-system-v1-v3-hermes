import { useStore } from '@nanostores/react'
import { useState } from 'react'

import { Activity, Clock, Eye, RefreshCw } from '@/lib/icons'
import {
  $marketingWorkbenchViewState,
  type MarketingAccountSummary,
  type MarketingWorkbenchViewState
} from '@/store/marketing'

interface PublishActionDetail {
  action?: {
    request?: {
      prediction?: Record<string, unknown> | null
    }
    [key: string]: unknown
  }
  metric_checkpoints?: Array<Record<string, unknown>>
  receipt?: {
    summary?: Record<string, unknown>
  } | null
  summary?: {
    platform?: string
    title?: string
    updated_at?: string
  }
}

interface GrowthDashboardProps {
  accounts: MarketingAccountSummary[]
  actionDetails: PublishActionDetail[]
  onRefresh: () => void
  onSelectAccount: (accountId: string) => void
  refreshing: boolean
  selectedAccountId: string
}

interface AccountProjection {
  account: MarketingAccountSummary
  engagementRate: number | null
  interactions: number | null
  newFollowers: number | null
  observedAt: string | null
  views: number | null
}

interface CompassItem {
  color: string
  id: string
  label: string
  projections: AccountProjection[]
}

interface HistoryPoint {
  date: string
  interactions: number | null
  newFollowers: number | null
  views: number | null
}

interface LineSeries {
  color: string
  id: string
  label: string
  points: HistoryPoint[]
}

interface CalibrationDimension {
  actual: number | null
  high: number
  key: string
  label: string
  low: number
  mid: number
  sample: number | null
  unit: string
}

const PLATFORM_COLORS: Record<string, string> = {
  bilibili: '#31a8dc',
  douyin: '#ff5a61',
  kuaishou: '#ff8a34',
  tiktok: '#25b7b1',
  wechat_channels: '#e2a93b',
  wechat_official: '#7eae96',
  xiaohongshu: '#e45d53',
  youtube: '#e23e3e',
  zhihu: '#3d7fd6'
}

const FALLBACK_COLORS = ['#ff655d', '#7ea994', '#4d83d3', '#d79d35', '#8a73c8', '#3aa9b0']

const PLATFORM_LABELS: Record<string, string> = {
  bilibili: '哔哩哔哩',
  douyin: '抖音',
  kuaishou: '快手',
  tiktok: 'TikTok',
  wechat_channels: '视频号',
  wechat_official: '微信公众号',
  xiaohongshu: '小红书',
  youtube: 'YouTube',
  zhihu: '知乎'
}

const RANGE_LABELS = [
  { id: 'live', label: '实时' },
  { id: '7d', label: '近 7 天' },
  { id: '30d', label: '近 30 天' },
  { id: 'all', label: '总数据' }
] as const

type RangeId = (typeof RANGE_LABELS)[number]['id']
type MetricKey = 'views' | 'newFollowers' | 'engagementRate'

export function GrowthDashboard({
  accounts,
  actionDetails,
  onRefresh,
  onSelectAccount,
  refreshing,
  selectedAccountId
}: GrowthDashboardProps) {
  const connected = accounts.filter(account => account.auth_state === 'authenticated')
  const projections = connected.map(projectAccount)
  const platformItems = buildPlatformItems(projections)
  const viewState = useStore($marketingWorkbenchViewState)
  const range = viewState.range
  const drillPlatform = viewState.drillPlatform || null
  const lineScope = viewState.lineScope
  const lineMode = viewState.lineMode
  const [spinning, setSpinning] = useState(false)
  const selectedAccount = connected.find(account => account.id === selectedAccountId) || connected[0] || null
  const selectedPlatform = selectedAccount?.platform || platformItems[0]?.id || ''

  const compassItems = drillPlatform
    ? buildAccountItems(projections.filter(item => item.account.platform === drillPlatform))
    : platformItems

  const hasHistory = projections.some(item => accountHistory(item).length > 1)
  const lineSeries = buildLineSeries(projections, lineScope, range)
  const calibration = buildCalibration(actionDetails, selectedPlatform)
  const quality = dataQuality(projections)
  const latestObserved = latestObservation(projections)

  const updateViewState = (patch: Partial<MarketingWorkbenchViewState>) => {
    $marketingWorkbenchViewState.set({ ...$marketingWorkbenchViewState.get(), ...patch })
  }

  const enterPlatform = (platform: string) => {
    if (spinning) {
      return
    }

    setSpinning(true)
    window.setTimeout(() => {
      updateViewState({ drillPlatform: platform })
      setSpinning(false)
    }, 420)
  }

  const leavePlatform = () => {
    if (!drillPlatform || spinning) {
      return
    }

    setSpinning(true)
    window.setTimeout(() => {
      updateViewState({ drillPlatform: '' })
      setSpinning(false)
    }, 420)
  }

  return (
    <section
      aria-label="经营数据工作台"
      className="relative mt-5 overflow-hidden rounded-[30px] border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) shadow-[0_22px_70px_rgba(42,34,27,0.07)]"
    >
      <div className="pointer-events-none absolute -left-24 -top-36 size-80 rounded-full bg-(--ui-accent)/7 blur-3xl" />
      <header className="relative flex flex-wrap items-center justify-between gap-4 border-b border-(--ui-stroke-tertiary) px-7 py-5">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold tracking-[-0.02em]">经营工作台</h2>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/8 px-2 py-1 text-[0.65rem] font-medium text-emerald-700 dark:text-emerald-400">
            <span className="size-1.5 rounded-full bg-emerald-500" />
            {latestObserved ? `${relativeTime(latestObserved)}更新` : '等待首次采集'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-full bg-(--ui-fill-secondary) p-1">
            {RANGE_LABELS.map(item => {
              const disabled = item.id !== 'all' && !hasHistory

              return (
                <button
                  aria-pressed={range === item.id}
                  className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                    range === item.id
                      ? 'bg-(--ui-sidebar-surface-background) text-foreground shadow-sm'
                      : 'text-(--ui-text-tertiary) hover:text-foreground'
                  } disabled:cursor-not-allowed disabled:opacity-35`}
                  disabled={disabled}
                  key={item.id}
                  onClick={() => updateViewState({ range: item.id })}
                  title={disabled ? '形成两次以上历史回执后可查看' : undefined}
                  type="button"
                >
                  {item.label}
                </button>
              )
            })}
          </div>
          <button
            aria-label="刷新经营数据"
            className="grid size-9 place-items-center rounded-full text-(--ui-text-tertiary) transition hover:bg-(--ui-control-hover-background) hover:text-foreground"
            onClick={onRefresh}
            type="button"
          >
            <RefreshCw className={`size-4 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </header>

      <div
        className="relative px-7 py-7"
        onClick={event => {
          if (!drillPlatform) {
            return
          }

          const target = event.target as Element

          if (target.closest('button,[data-compass-segment]')) {
            return
          }

          leavePlatform()
        }}
      >
        <div className="flex items-end justify-between gap-4">
          <div>
            <h3 className="text-sm font-semibold">经营罗盘</h3>
            <p className="mt-1 text-xs text-(--ui-text-tertiary)">
              {drillPlatform
                ? `${platformLabel(drillPlatform)} · 各账号贡献，点击空白处返回全部平台`
                : '全部平台 · 悬停查看贡献，点击色块进入账号层'}
            </p>
          </div>
          <span className="text-xs tabular-nums text-(--ui-text-tertiary)">
            {connected.length ? `${connected.length} 个账号` : '还没有已连接账号'}
          </span>
        </div>

        <div className="mt-5 grid min-h-[250px] gap-5 md:grid-cols-3">
          <CompassRing
            coverage={metricCoverage(compassItems, 'views')}
            formatValue={compactNumber}
            items={compassItems}
            label="总浏览量"
            metric="views"
            onItemClick={item => {
              if (drillPlatform) {
                onSelectAccount(item.id)
              } else {
                enterPlatform(item.id)
              }
            }}
            spinning={spinning}
          />
          <CompassRing
            coverage={metricCoverage(compassItems, 'newFollowers')}
            formatValue={value => `+${compactNumber(value)}`}
            items={compassItems}
            label="总新增粉丝量"
            metric="newFollowers"
            onItemClick={item => {
              if (drillPlatform) {
                onSelectAccount(item.id)
              } else {
                enterPlatform(item.id)
              }
            }}
            spinning={spinning}
          />
          <CompassRing
            coverage={metricCoverage(compassItems, 'engagementRate')}
            formatValue={value => `${value.toFixed(1)}%`}
            items={compassItems}
            label="总互动率"
            metric="engagementRate"
            onItemClick={item => {
              if (drillPlatform) {
                onSelectAccount(item.id)
              } else {
                enterPlatform(item.id)
              }
            }}
            spinning={spinning}
          />
        </div>
      </div>

      <div className="border-t border-(--ui-stroke-tertiary) px-7 py-7">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h3 className="text-sm font-semibold">真实增长路径</h3>
            <p className="mt-1 text-xs text-(--ui-text-tertiary)">
              曲线只使用带时间戳的账号快照，不用当前累计值反推历史。
            </p>
          </div>
          <div className="flex items-center rounded-full bg-(--ui-fill-secondary) p-1">
            <button
              aria-pressed={lineMode === 'index'}
              className={`rounded-full px-3 py-1.5 text-xs ${lineMode === 'index' ? 'bg-(--ui-sidebar-surface-background) shadow-sm' : 'text-(--ui-text-tertiary)'}`}
              onClick={() => updateViewState({ lineMode: 'index' })}
              type="button"
            >
              增长指数
            </button>
            <button
              aria-pressed={lineMode === 'raw'}
              className={`rounded-full px-3 py-1.5 text-xs ${lineMode === 'raw' ? 'bg-(--ui-sidebar-surface-background) shadow-sm' : 'text-(--ui-text-tertiary)'}`}
              onClick={() => updateViewState({ lineMode: 'raw' })}
              type="button"
            >
              实际规模
            </button>
          </div>
        </div>

        <div className="mt-5 grid gap-7 xl:grid-cols-[1.35fr_0.85fr]">
          <div className="min-w-0">
            <GrowthLineChart mode={lineMode} series={lineSeries} />
            <div className="mt-3 flex flex-wrap justify-center gap-1">
              <ScopeButton
                active={lineScope === 'all'}
                label="总数据"
                onClick={() => updateViewState({ lineScope: 'all' })}
              />
              {platformItems.map(item => (
                <ScopeButton
                  active={lineScope === item.id}
                  key={item.id}
                  label={item.label}
                  onClick={() => updateViewState({ lineScope: item.id })}
                />
              ))}
            </div>
          </div>

          <div className="min-w-0 border-t border-(--ui-stroke-tertiary) pt-6 xl:border-l xl:border-t-0 xl:pl-7 xl:pt-0">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold">预测校准</h3>
                <p className="mt-1 text-xs text-(--ui-text-tertiary)">
                  {selectedAccount
                    ? `${platformLabel(selectedPlatform)} · ${accountName(selectedAccount)}`
                    : '等待选择账号'}
                </p>
              </div>
              <span className="rounded-full bg-(--ui-fill-secondary) px-2.5 py-1 text-[0.65rem] text-(--ui-text-tertiary)">
                {calibration.length ? '预测中位值 = 100' : '等待可比回执'}
              </span>
            </div>
            <CalibrationChart dimensions={calibration} />
            <div className="mt-3 flex flex-wrap justify-center gap-1">
              {platformItems.map(item => {
                const platformAccount = item.projections[0]?.account

                return (
                  <ScopeButton
                    active={selectedPlatform === item.id}
                    key={item.id}
                    label={item.label}
                    onClick={() => {
                      if (platformAccount) {
                        onSelectAccount(platformAccount.id)
                      }
                    }}
                  />
                )
              })}
            </div>
          </div>
        </div>
      </div>

      <footer className="grid border-t border-(--ui-stroke-tertiary) md:grid-cols-3">
        <EvidenceSummary
          detail="完成稳定基线和可比实验后显示可信区间"
          icon={<Activity className="size-4" />}
          label="智能体估计增量"
          value="待校准"
        />
        <EvidenceSummary
          detail={
            latestObserved ? `最近账号快照 ${formatDateTime(latestObserved)}` : '连接账号并同步后开始形成时间序列'
          }
          icon={<Clock className="size-4" />}
          label="最新数据回执"
          value={latestObserved ? relativeTime(latestObserved) : '等待采集'}
        />
        <EvidenceSummary
          detail={
            quality.total ? `${quality.known}/${quality.total} 个关键字段有可验证来源` : '连接账号后显示采集覆盖范围'
          }
          icon={<Eye className="size-4" />}
          label="数据完整度"
          value={quality.total ? `${Math.round((quality.known / quality.total) * 100)}%` : '—'}
        />
      </footer>
    </section>
  )
}

function CompassRing({
  coverage,
  formatValue,
  items,
  label,
  metric,
  onItemClick,
  spinning
}: {
  coverage: { known: number; total: number }
  formatValue: (value: number) => string
  items: CompassItem[]
  label: string
  metric: MetricKey
  onItemClick: (item: CompassItem) => void
  spinning: boolean
}) {
  const [hovered, setHovered] = useState<{ item: CompassItem; share: number } | null>(null)
  const values = items.map(item => compassValue(item, metric))
  const total = values.reduce<number>((sum, value) => sum + (value || 0), 0)

  const centerValue =
    metric === 'engagementRate' ? weightedEngagement(items.flatMap(item => item.projections)) : total > 0 ? total : null

  const radius = 74
  const circumference = 2 * Math.PI * radius
  let offset = 0

  return (
    <article className="relative flex min-w-0 flex-col items-center rounded-[22px] bg-(--ui-fill-primary)/45 px-4 py-4">
      <div className="relative size-[205px]">
        <svg
          aria-label={`${label} ${centerValue === null ? '暂无数据' : formatValue(centerValue)}`}
          className={`size-full -rotate-90 overflow-visible transition-transform duration-500 ${spinning ? 'rotate-[270deg]' : ''}`}
          role="img"
          viewBox="0 0 200 200"
        >
          <circle cx="100" cy="100" fill="none" r={radius} stroke="var(--ui-fill-tertiary)" strokeWidth="24" />
          {total > 0
            ? items.map((item, index) => {
                const value = values[index] || 0
                const length = (value / total) * circumference
                const gap = Math.min(4, length * 0.08)
                const segmentOffset = offset
                offset += length

                return (
                  <circle
                    className="cursor-pointer transition-[stroke-width,opacity] duration-150 hover:opacity-85"
                    cx="100"
                    cy="100"
                    data-compass-segment
                    fill="none"
                    key={item.id}
                    onClick={event => {
                      event.stopPropagation()
                      onItemClick(item)
                    }}
                    onMouseEnter={() => setHovered({ item, share: value / total })}
                    onMouseLeave={() => setHovered(null)}
                    r={radius}
                    stroke={item.color}
                    strokeDasharray={`${Math.max(0, length - gap)} ${circumference - Math.max(0, length - gap)}`}
                    strokeDashoffset={-segmentOffset}
                    strokeWidth="24"
                  >
                    <title>{`${item.label} · ${Math.round((value / total) * 100)}% 贡献`}</title>
                  </circle>
                )
              })
            : null}
        </svg>
        <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
          <div>
            <span className="block text-[0.68rem] text-(--ui-text-tertiary)">{label}</span>
            <strong className="mt-1 block text-[1.55rem] font-semibold tabular-nums tracking-[-0.05em]">
              {centerValue === null ? '—' : formatValue(centerValue)}
            </strong>
          </div>
        </div>
        {hovered ? (
          <div className="pointer-events-none absolute left-1/2 top-1 z-10 -translate-x-1/2 rounded-xl border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background)/96 px-3 py-2 text-center shadow-lg backdrop-blur">
            <strong className="block whitespace-nowrap text-xs font-semibold">{hovered.item.label}</strong>
            <span className="mt-0.5 block whitespace-nowrap text-[0.65rem] text-(--ui-text-tertiary)">
              {Math.round(hovered.share * 100)}% 贡献
            </span>
          </div>
        ) : null}
      </div>
      <span className="mt-1 text-[0.65rem] text-(--ui-text-quaternary)">
        {coverage.total ? `已覆盖 ${coverage.known}/${coverage.total}` : '等待账号数据'}
      </span>
      <div className="mt-3 flex max-w-full flex-wrap justify-center gap-x-3 gap-y-1">
        {items.map(item => (
          <button
            className="inline-flex min-w-0 items-center gap-1.5 text-[0.65rem] text-(--ui-text-tertiary) hover:text-foreground"
            key={item.id}
            onClick={event => {
              event.stopPropagation()
              onItemClick(item)
            }}
            type="button"
          >
            <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: item.color }} />
            <span className="max-w-24 truncate">{item.label}</span>
          </button>
        ))}
      </div>
    </article>
  )
}

function GrowthLineChart({ mode, series }: { mode: 'index' | 'raw'; series: LineSeries[] }) {
  const usable = series.filter(item => item.points.length > 1)

  if (!usable.length) {
    return (
      <div className="grid h-[286px] place-items-center rounded-[22px] border border-dashed border-(--ui-stroke-secondary) bg-(--ui-fill-primary)/30 text-center">
        <div className="max-w-sm px-6">
          <Activity className="mx-auto size-5 text-(--ui-text-quaternary)" />
          <strong className="mt-3 block text-sm font-medium">还差一次可比快照</strong>
          <p className="mt-2 text-xs leading-5 text-(--ui-text-tertiary)">
            至少两次同口径采集后才绘制增长曲线，当前累计数字不会被伪装成历史趋势。
          </p>
        </div>
      </div>
    )
  }

  const width = 760
  const height = 286
  const left = 48
  const right = 18
  const top = 20
  const bottom = 36
  const dates = Array.from(new Set(usable.flatMap(item => item.points.map(point => point.date)))).sort()

  const normalized = usable.map(item => ({
    ...item,
    values: dates.map(date => {
      const point = latestPointAt(item.points, date)

      return point?.views ?? null
    })
  }))

  const rendered = normalized.map(item => {
    const first = item.values.find(value => value !== null && value > 0) || 1

    return {
      ...item,
      values: item.values.map(value => (value === null ? null : mode === 'index' ? (value / first) * 100 : value))
    }
  })

  const max = Math.max(1, ...rendered.flatMap(item => item.values.filter((value): value is number => value !== null)))
  const x = (index: number) => left + ((width - left - right) * index) / Math.max(1, dates.length - 1)
  const y = (value: number) => top + (height - top - bottom) * (1 - value / (max * 1.12))

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-3 text-[0.68rem] text-(--ui-text-tertiary)">
        {rendered.map(item => (
          <span className="inline-flex items-center gap-1.5" key={item.id}>
            <span className="h-0.5 w-5 rounded-full" style={{ backgroundColor: item.color }} />
            {item.label}
          </span>
        ))}
      </div>
      <svg className="h-[286px] w-full overflow-visible" role="img" viewBox={`0 0 ${width} ${height}`}>
        <title>{mode === 'index' ? '增长指数曲线' : '实际浏览规模曲线'}</title>
        {[0, 0.25, 0.5, 0.75, 1].map(ratio => {
          const value = max * 1.12 * (1 - ratio)
          const yy = top + (height - top - bottom) * ratio

          return (
            <g key={ratio}>
              <line stroke="var(--ui-stroke-tertiary)" strokeWidth="1" x1={left} x2={width - right} y1={yy} y2={yy} />
              <text fill="var(--ui-text-quaternary)" fontSize="10" textAnchor="end" x={left - 8} y={yy + 3}>
                {mode === 'index' ? Math.round(value) : compactNumber(value)}
              </text>
            </g>
          )
        })}
        {dates.map((date, index) => (
          <text
            fill="var(--ui-text-quaternary)"
            fontSize="10"
            key={date}
            textAnchor={index === 0 ? 'start' : index === dates.length - 1 ? 'end' : 'middle'}
            x={x(index)}
            y={height - 10}
          >
            {shortDate(date)}
          </text>
        ))}
        {rendered.map(item => {
          const points = item.values
            .map((value, index) => (value === null ? null : { index, value }))
            .filter((point): point is { index: number; value: number } => point !== null)

          const path = points
            .map((point, index) => `${index ? 'L' : 'M'} ${x(point.index)} ${y(point.value)}`)
            .join(' ')

          return (
            <g key={item.id}>
              <path
                d={path}
                fill="none"
                stroke={item.color}
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="3"
              />
              {points.map(point => (
                <circle
                  cx={x(point.index)}
                  cy={y(point.value)}
                  fill="var(--ui-sidebar-surface-background)"
                  key={`${item.id}-${point.index}`}
                  r="3.5"
                  stroke={item.color}
                  strokeWidth="2.5"
                >
                  <title>{`${item.label} · ${shortDate(dates[point.index])} · ${mode === 'index' ? `${point.value.toFixed(1)} 指数` : compactNumber(point.value)}`}</title>
                </circle>
              ))}
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function CalibrationChart({ dimensions }: { dimensions: CalibrationDimension[] }) {
  if (!dimensions.length) {
    return (
      <div className="grid h-[286px] place-items-center text-center">
        <div className="max-w-xs px-5">
          <Clock className="mx-auto size-5 text-(--ui-text-quaternary)" />
          <strong className="mt-3 block text-sm font-medium">还没有可校准的作品</strong>
          <p className="mt-2 text-xs leading-5 text-(--ui-text-tertiary)">
            作品发布前形成盲预测，平台回执到齐后，这里才比较预测区间与实际值。
          </p>
        </div>
      </div>
    )
  }

  const width = 500
  const height = 286
  const left = 36
  const right = 14
  const top = 24
  const base = 248

  const maxRatio = Math.max(
    140,
    ...dimensions.map(item =>
      Math.max((item.high / item.mid) * 100, item.actual === null ? 0 : (item.actual / item.mid) * 100)
    )
  )

  const slot = (width - left - right) / dimensions.length
  const y = (ratio: number) => top + (base - top) * (1 - ratio / maxRatio)

  return (
    <svg className="mt-4 h-[286px] w-full overflow-visible" role="img" viewBox={`0 0 ${width} ${height}`}>
      <title>预测与实际校准</title>
      {[0, 50, 100, Math.round(maxRatio)].map(ratio => (
        <g key={ratio}>
          <line
            stroke="var(--ui-stroke-tertiary)"
            strokeDasharray={ratio === 100 ? '4 4' : undefined}
            x1={left}
            x2={width - right}
            y1={y(ratio)}
            y2={y(ratio)}
          />
          <text fill="var(--ui-text-quaternary)" fontSize="10" textAnchor="end" x={left - 7} y={y(ratio) + 3}>
            {ratio}%
          </text>
        </g>
      ))}
      {dimensions.map((item, index) => {
        const center = left + slot * (index + 0.5)
        const lowRatio = (item.low / item.mid) * 100
        const highRatio = (item.high / item.mid) * 100
        const actualRatio = item.actual === null ? null : (item.actual / item.mid) * 100
        const barWidth = Math.min(22, slot * 0.32)

        return (
          <g key={item.key}>
            <line stroke="var(--ui-text-quaternary)" x1={center} x2={center} y1={y(highRatio)} y2={y(lowRatio)} />
            <line
              stroke="var(--ui-text-quaternary)"
              x1={center - 5}
              x2={center + 5}
              y1={y(highRatio)}
              y2={y(highRatio)}
            />
            <line
              stroke="var(--ui-text-quaternary)"
              x1={center - 5}
              x2={center + 5}
              y1={y(lowRatio)}
              y2={y(lowRatio)}
            />
            <rect
              fill="color-mix(in srgb, var(--ui-accent) 14%, transparent)"
              height={base - y(100)}
              rx="4"
              width={barWidth}
              x={center - barWidth / 2}
              y={y(100)}
            />
            {actualRatio !== null ? (
              <>
                <rect
                  fill="var(--ui-accent)"
                  height={base - y(Math.min(100, actualRatio))}
                  rx="4"
                  width={barWidth}
                  x={center - barWidth / 2}
                  y={y(Math.min(100, actualRatio))}
                />
                {actualRatio > 100 ? (
                  <rect
                    fill="color-mix(in srgb, var(--ui-accent) 45%, transparent)"
                    height={y(100) - y(actualRatio)}
                    rx="4"
                    width={barWidth}
                    x={center - barWidth / 2}
                    y={y(actualRatio)}
                  />
                ) : null}
                <circle
                  cx={center}
                  cy={y(actualRatio)}
                  fill="var(--ui-sidebar-surface-background)"
                  r="3.5"
                  stroke="var(--ui-accent)"
                  strokeWidth="2"
                >
                  <title>{calibrationTitle(item)}</title>
                </circle>
                <text
                  fill="var(--ui-text-secondary)"
                  fontSize="10"
                  textAnchor="middle"
                  x={center}
                  y={y(actualRatio) - 8}
                >
                  {Math.round(actualRatio)}%
                </text>
              </>
            ) : (
              <text fill="var(--ui-text-quaternary)" fontSize="9" textAnchor="middle" x={center} y={y(100) - 8}>
                待回执
              </text>
            )}
            <line
              stroke="var(--ui-text-secondary)"
              strokeWidth="1.5"
              x1={center - barWidth / 2 - 2}
              x2={center + barWidth / 2 + 2}
              y1={y(100)}
              y2={y(100)}
            />
            <text fill="var(--ui-text-tertiary)" fontSize="10" textAnchor="middle" x={center} y={base + 20}>
              {item.label}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

function ScopeButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      aria-pressed={active}
      className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
        active
          ? 'bg-foreground text-background'
          : 'text-(--ui-text-tertiary) hover:bg-(--ui-fill-secondary) hover:text-foreground'
      }`}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  )
}

function EvidenceSummary({
  detail,
  icon,
  label,
  value
}: {
  detail: string
  icon: React.ReactNode
  label: string
  value: string
}) {
  return (
    <article className="min-w-0 border-b border-(--ui-stroke-tertiary) p-6 last:border-b-0 md:border-b-0 md:border-r md:last:border-r-0">
      <div className="flex items-center gap-2 text-xs text-(--ui-text-tertiary)">
        <span className="grid size-8 place-items-center rounded-xl bg-(--ui-fill-secondary) text-(--ui-text-secondary)">
          {icon}
        </span>
        {label}
      </div>
      <strong className="mt-4 block text-[1.35rem] font-semibold tracking-[-0.04em]">{value}</strong>
      <p className="mt-1.5 text-xs leading-5 text-(--ui-text-tertiary)">{detail}</p>
    </article>
  )
}

function projectAccount(account: MarketingAccountSummary): AccountProjection {
  const stats = account.stats || {}
  const views = firstNumber(stats, ['read_users', 'total_views', 'views', 'play_count', 'view_count'])
  const newFollowers = firstNumber(stats, ['followers_gained', 'new_followers', 'followers_delta', 'fan_delta'])

  const interactions =
    account.platform === 'wechat_official'
      ? sumNumbers(stats, ['share_users', 'like_count', 'recommend_count', 'comment_count', 'collection_users'])
      : account.platform === 'douyin'
        ? firstNumber(stats, ['public_video_likes', 'interactions', 'engagement'])
        : firstNumber(stats, ['interactions', 'engagement', 'total_likes', 'likes'])

  const directRate = firstNumber(stats, ['engagement_rate', 'interaction_rate'])
  const engagementRate = directRate ?? (views && interactions !== null ? (interactions / views) * 100 : null)

  const observedAt =
    firstString(stats, ['observed_at', 'captured_at', 'updated_at']) || normalizeDate(account.last_verified_at)

  return { account, engagementRate, interactions, newFollowers, observedAt, views }
}

function buildPlatformItems(projections: AccountProjection[]): CompassItem[] {
  const grouped = new Map<string, AccountProjection[]>()

  for (const projection of projections) {
    const platform = projection.account.platform || 'unknown'
    grouped.set(platform, [...(grouped.get(platform) || []), projection])
  }

  return Array.from(grouped.entries()).map(([platform, items], index) => ({
    color: PLATFORM_COLORS[platform] || FALLBACK_COLORS[index % FALLBACK_COLORS.length],
    id: platform,
    label: platformLabel(platform),
    projections: items
  }))
}

function buildAccountItems(projections: AccountProjection[]): CompassItem[] {
  return projections.map((projection, index) => ({
    color: FALLBACK_COLORS[index % FALLBACK_COLORS.length],
    id: projection.account.id,
    label: accountName(projection.account),
    projections: [projection]
  }))
}

function compassValue(item: CompassItem, metric: MetricKey): number | null {
  if (metric === 'engagementRate') {
    const interactions = item.projections.reduce((sum, projection) => sum + (projection.interactions || 0), 0)
    const views = item.projections.reduce((sum, projection) => sum + (projection.views || 0), 0)

    return views > 0 && interactions > 0 ? interactions : null
  }

  const values = item.projections
    .map(projection => projection[metric])
    .filter((value): value is number => value !== null)

  return values.length ? values.reduce((sum, value) => sum + value, 0) : null
}

function weightedEngagement(projections: AccountProjection[]): number | null {
  const comparable = projections.filter(item => item.views !== null && item.views > 0 && item.interactions !== null)
  const views = comparable.reduce((sum, item) => sum + (item.views || 0), 0)
  const interactions = comparable.reduce((sum, item) => sum + (item.interactions || 0), 0)

  return views > 0 ? (interactions / views) * 100 : null
}

function metricCoverage(items: CompassItem[], metric: MetricKey) {
  const projections = items.flatMap(item => item.projections)

  return {
    known: projections.filter(item => (metric === 'engagementRate' ? item.engagementRate : item[metric]) !== null)
      .length,
    total: projections.length
  }
}

function buildLineSeries(projections: AccountProjection[], scope: string, range: RangeId): LineSeries[] {
  const filtered = filterByRange(projections, range)

  if (scope === 'all') {
    return buildPlatformItems(filtered).map(item => ({
      color: item.color,
      id: item.id,
      label: item.label,
      points: aggregateHistories(item.projections)
    }))
  }

  return filtered
    .filter(item => item.account.platform === scope)
    .map((item, index) => ({
      color: FALLBACK_COLORS[index % FALLBACK_COLORS.length],
      id: item.account.id,
      label: accountName(item.account),
      points: accountHistory(item)
    }))
}

function accountHistory(projection: AccountProjection): HistoryPoint[] {
  const stats = projection.account.stats || {}

  const raw = [stats.metric_history, stats.history, stats.snapshots].find(Array.isArray) as
    | Array<Record<string, unknown>>
    | undefined

  const points = (raw || [])
    .map(item => ({
      date: firstString(item, ['observed_at', 'captured_at', 'date', 'timestamp']) || '',
      interactions: firstNumber(item, ['interactions', 'engagement', 'likes', 'total_likes']),
      newFollowers: firstNumber(item, ['followers_gained', 'new_followers', 'followers_delta']),
      views: firstNumber(item, ['read_users', 'total_views', 'views', 'play_count'])
    }))
    .filter(item => item.date)
    .sort((left, right) => left.date.localeCompare(right.date))

  if (!points.length && projection.observedAt) {
    return [
      {
        date: projection.observedAt,
        interactions: projection.interactions,
        newFollowers: projection.newFollowers,
        views: projection.views
      }
    ]
  }

  return points
}

function aggregateHistories(projections: AccountProjection[]): HistoryPoint[] {
  const histories = projections.map(accountHistory)
  const dates = Array.from(new Set(histories.flatMap(history => history.map(point => point.date)))).sort()

  return dates.map(date => {
    const latest = histories
      .map(history => latestPointAt(history, date))
      .filter((point): point is HistoryPoint => Boolean(point))

    return {
      date,
      interactions: sumNullable(latest.map(point => point.interactions)),
      newFollowers: sumNullable(latest.map(point => point.newFollowers)),
      views: sumNullable(latest.map(point => point.views))
    }
  })
}

function latestPointAt(points: HistoryPoint[], date: string): HistoryPoint | null {
  return points.filter(point => point.date <= date).at(-1) || null
}

function filterByRange(projections: AccountProjection[], range: RangeId): AccountProjection[] {
  if (range === 'all') {
    return projections
  }

  const days = range === 'live' ? 1 : range === '7d' ? 7 : 30
  const cutoff = Date.now() - days * 86_400_000

  return projections.map(projection => ({
    ...projection,
    account: {
      ...projection.account,
      stats: {
        ...(projection.account.stats || {}),
        metric_history: accountHistory(projection).filter(point => new Date(point.date).getTime() >= cutoff)
      }
    }
  }))
}

function buildCalibration(details: PublishActionDetail[], platform: string): CalibrationDimension[] {
  const detail = details.find(item => (item.summary?.platform || '') === platform) || details[0]
  const prediction = record(detail?.action?.request?.prediction)
  const root = record(prediction.prediction_dimensions)
  const dimensions = record(root.dimensions)
  const actual = findActualMetrics(detail)
  const order = ['attention', 'retention', 'trust', 'action', 'account_fit', 'sound']

  return order
    .map(key => {
      const dimension = record(dimensions[key])
      const range = record(dimension.range)
      const mid = finiteNumber(range.mid)
      const low = finiteNumber(range.low)
      const high = finiteNumber(range.high)
      const metricName = String(dimension.expected_metric || '')

      if (mid === null || mid <= 0 || low === null || high === null) {
        return null
      }

      return {
        actual: firstNumber(actual, [metricName, key]),
        high,
        key,
        label: calibrationLabel(key, metricName),
        low,
        mid,
        sample: firstNumber(actual, ['sample_size', 'sample']),
        unit: calibrationUnit(metricName, mid)
      }
    })
    .filter((item): item is CalibrationDimension => item !== null)
}

function findActualMetrics(detail?: PublishActionDetail): Record<string, unknown> {
  const candidates: unknown[] = [
    detail?.receipt?.summary?.metrics,
    detail?.receipt?.summary,
    detail?.action?.actual,
    ...(detail?.metric_checkpoints || []).map(item => item.metrics)
  ]

  return candidates.map(record).find(item => Object.keys(item).length > 0) || {}
}

function calibrationTitle(item: CalibrationDimension): string {
  const range = `${formatMetric(item.low, item.unit)}–${formatMetric(item.high, item.unit)}`
  const actual = item.actual === null ? '等待回执' : formatMetric(item.actual, item.unit)
  const sample = item.sample === null ? '' : ` · 样本 ${compactNumber(item.sample)}`

  return `${item.label} · 预测 ${formatMetric(item.mid, item.unit)} (${range}) · 实际 ${actual}${sample}`
}

function calibrationLabel(key: string, metricName: string): string {
  const labels: Record<string, string> = {
    account_fit: '受众',
    action: '行动',
    attention: metricName === 'views' ? '浏览' : '触达',
    retention: '留存',
    sound: '声音',
    trust: metricName.includes('share') ? '转发' : '互动'
  }

  return labels[key] || key
}

function calibrationUnit(metricName: string, value: number): string {
  if (metricName === 'views') {
    return ''
  }

  return metricName.includes('rate') || value <= 1 ? '%' : ''
}

function dataQuality(projections: AccountProjection[]) {
  const fields = projections.flatMap(item => [item.views, item.newFollowers, item.engagementRate])

  return { known: fields.filter(value => value !== null).length, total: fields.length }
}

function latestObservation(projections: AccountProjection[]): string | null {
  return (
    projections
      .map(item => item.observedAt)
      .filter((value): value is string => Boolean(value))
      .sort()
      .at(-1) || null
  )
}

function accountName(account: MarketingAccountSummary): string {
  return account.label || account.username || account.id
}

function platformLabel(platform: string): string {
  return PLATFORM_LABELS[platform] || platform || '未知平台'
}

function firstNumber(source: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const value = finiteNumber(source[key])

    if (value !== null && value >= 0) {
      return value
    }
  }

  return null
}

function sumNumbers(source: Record<string, unknown>, keys: string[]): number | null {
  const values = keys
    .map(key => finiteNumber(source[key]))
    .filter((value): value is number => value !== null && value >= 0)

  return values.length ? values.reduce((sum, value) => sum + value, 0) : null
}

function sumNullable(values: Array<number | null>): number | null {
  const known = values.filter((value): value is number => value !== null)

  return known.length ? known.reduce((sum, value) => sum + value, 0) : null
}

function finiteNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') {
    return null
  }

  const number = Number(value)

  return Number.isFinite(number) ? number : null
}

function firstString(source: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = source[key]

    if (typeof value === 'string' && value.trim()) {
      return value
    }
  }

  return null
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function normalizeDate(value: unknown): string | null {
  if (typeof value === 'number') {
    const date = new Date(value > 10_000_000_000 ? value : value * 1000)

    return Number.isNaN(date.getTime()) ? null : date.toISOString()
  }

  if (typeof value === 'string' && value.trim()) {
    const date = new Date(value)

    return Number.isNaN(date.getTime()) ? null : date.toISOString()
  }

  return null
}

function compactNumber(value: number): string {
  if (value >= 100_000_000) {
    return `${(value / 100_000_000).toFixed(value >= 1_000_000_000 ? 0 : 1)}亿`
  }

  if (value >= 10_000) {
    return `${(value / 10_000).toFixed(value >= 100_000 ? 0 : 1)}万`
  }

  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 }).format(value)
}

function formatMetric(value: number, unit: string): string {
  if (unit === '%') {
    return `${value <= 1 ? (value * 100).toFixed(1) : value.toFixed(1)}%`
  }

  return compactNumber(value)
}

function shortDate(value: string): string {
  const date = new Date(value)

  return Number.isNaN(date.getTime()) ? value.slice(0, 10) : `${date.getMonth() + 1}/${date.getDate()}`
}

function formatDateTime(value: string): string {
  const date = new Date(value)

  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat('zh-CN', { day: 'numeric', hour: '2-digit', minute: '2-digit', month: 'short' }).format(
        date
      )
}

function relativeTime(value: string): string {
  const date = new Date(value)
  const delta = Date.now() - date.getTime()

  if (Number.isNaN(delta)) {
    return '最近'
  }

  if (delta < 60_000) {
    return '刚刚'
  }

  if (delta < 3_600_000) {
    return `${Math.max(1, Math.floor(delta / 60_000))} 分钟前`
  }

  if (delta < 86_400_000) {
    return `${Math.floor(delta / 3_600_000)} 小时前`
  }

  return `${Math.floor(delta / 86_400_000)} 天前`
}
