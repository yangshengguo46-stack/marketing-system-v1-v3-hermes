import { useEffect, useState } from 'react'
import {
  ArrowRight,
  Eye,
  Flame,
  Heart,
  Sparkles,
  Users,
} from 'lucide-react'
import { api, PLATFORM_NAMES } from '@/api/client'
import { encodeCreativeBrief } from '@/lib/creativeBrief'
import { formatAudienceHeat } from '@/lib/formatters'

const EMPTY: OverviewData = {
  accounts_connected: 0,
  trending_topics_today: 0,
  suggestions_generated: 0,
  videos_published: 0,
  total_followers: 0,
  follower_growth_today: 0,
  content_pipeline: {
    total_assets: 0,
    drafts: 0,
    in_review: 0,
    approved: 0,
    published: 0,
    ready_to_publish: 0,
    latest_draft: null,
  },
  publishing_receipts: {
    total: 0,
    verified: 0,
    pending_verification: 0,
    failed: 0,
    metric_checkpoints: {
      total: 0,
      scheduled: 0,
      collected: 0,
      due: 0,
    },
    next_metrics_at: null,
    latest: null,
  },
  platform_accounts: [],
}

const PLATFORM_COLORS: Record<string, string> = {
  douyin: '#ff6b64',
  bilibili: '#58c7f3',
  xiaohongshu: '#ff4d6d',
  zhihu: '#4c8dff',
  kuaishou: '#ff8a3d',
  wechat_channels: '#62c4a0',
  wechat_official: '#07c160',
}

const HIDDEN_PLATFORMS = new Set(['weibo'])
const METRIC_DEFS: Array<{ key: MetricKey; label: string; icon: React.ElementType }> = [
  { key: 'growth', label: '涨粉', icon: Users },
  { key: 'views', label: '浏览', icon: Eye },
  { key: 'likes', label: '点赞', icon: Heart },
]
type MetricRange = 'today' | 'week' | 'month'
type MetricKey = 'growth' | 'views' | 'likes'
const METRIC_RANGES: Array<{ id: MetricRange; label: string; days: number }> = [
  { id: 'today', label: '今日', days: 1 },
  { id: 'week', label: '本周', days: 7 },
  { id: 'month', label: '本月', days: 30 },
]

export default function Overview({ onNavigate }: { onNavigate?: (page: string) => void }) {
  const [data, setData] = useState<OverviewData>(EMPTY)
  const [trends, setTrends] = useState<TrendItem[]>([])
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [selectedPlatform, setSelectedPlatform] = useState<string | null>(null)
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null)
  const [activeTrendPlatform, setActiveTrendPlatform] = useState(0)
  const [activeTrendItem, setActiveTrendItem] = useState(0)
  const [activeIdeaItem, setActiveIdeaItem] = useState(0)
  const [metricRange, setMetricRange] = useState<MetricRange>('today')
  const [trendRelevance, setTrendRelevance] = useState<{
    mode?: 'exploration' | 'account_positioning' | string
    hasPositioning?: boolean
  }>({})
  const contentPipeline = data.content_pipeline || EMPTY.content_pipeline
  const publishingReceipts = data.publishing_receipts || EMPTY.publishing_receipts

  useEffect(() => {
    if (!window.marketingOS) return
    api.overview().then((overview) => {
      setData(overview)
    }).catch(() => {})
  }, [])

  const date = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(new Date())
  const visibleAccounts = data.platform_accounts.filter((account) => !HIDDEN_PLATFORMS.has(account.platform))
  const trendScopeAccountId = selectedAccountId || visibleAccounts[0]?.id || null

  useEffect(() => {
    if (!window.marketingOS) return
    Promise.allSettled([api.trending(trendScopeAccountId), api.suggestions(trendScopeAccountId)]).then(([trending, ideas]) => {
      if (trending.status === 'fulfilled') {
        const payload = trending.value as {
          top_trends?: TrendItem[]
          relevance_mode?: string
          relevance_context?: { has_positioning?: boolean }
        }
        setTrends((payload.top_trends || []).filter((trend) => !HIDDEN_PLATFORMS.has(trend.source_platform)))
        setTrendRelevance({
          mode: payload.relevance_mode,
          hasPositioning: Boolean(payload.relevance_context?.has_positioning),
        })
      }
      if (ideas.status === 'fulfilled') {
        const payload = ideas.value as { suggestions?: Suggestion[] }
        setSuggestions((payload.suggestions || []).filter((suggestion) => !HIDDEN_PLATFORMS.has(suggestion.trend_source || '')))
      }
    })
  }, [trendScopeAccountId])

  const leadSuggestion = suggestions[0]
  const platformGroups = groupAccountsByPlatform(visibleAccounts)
  const selectedAccount = visibleAccounts.find((account) => account.id === selectedAccountId) || null
  const activePlatform = selectedAccount?.platform || selectedPlatform
  const activePlatformAccounts = activePlatform ? platformGroups.find((group) => group.platform === activePlatform)?.accounts || [] : []
  const selectedMetrics = selectedAccount ? accountMetricsForRange(selectedAccount, metricRange) : null
  const maxViews = Math.max(1, ...visibleAccounts.map((account) => Math.abs(accountMetricsForRange(account, metricRange).views)))
  const maxGrowth = Math.max(1, ...visibleAccounts.map((account) => Math.abs(accountMetricsForRange(account, metricRange).growth)))
  const maxLikes = Math.max(1, ...visibleAccounts.map((account) => Math.abs(accountMetricsForRange(account, metricRange).likes)))
  const viewLevel = selectedAccount ? 'account' : activePlatform ? 'platform' : 'overview'
  const drillLabel = selectedAccount
    ? `${PLATFORM_NAMES[selectedAccount.platform] || selectedAccount.platform} · ${selectedAccount.label}`
    : activePlatform
      ? `${PLATFORM_NAMES[activePlatform] || activePlatform} · ${activePlatformAccounts.length} 个账号`
      : `${platformGroups.length} 个平台 · ${visibleAccounts.length} 个账号`
  const platformTrendGroups = groupTrendsByPlatform(trends)
  const activeTrendIndex = activeTrendPlatform % Math.max(1, platformTrendGroups.length)
  const activeTrendGroup = platformTrendGroups[activeTrendIndex]
  const activeTrendItems = activeTrendGroup?.items || []
  const activeTrendItemIndex = activeTrendItem % Math.max(1, activeTrendItems.length)
  const visibleTrends = rotateItems(activeTrendItems, activeTrendItemIndex, activeTrendItems.length)
  const activeIdeaIndex = activeIdeaItem % Math.max(1, suggestions.length)
  const visibleIdeas = rotateItems(suggestions, activeIdeaIndex, suggestions.length)
  const trendScopeLabel = trendRelevance.hasPositioning
    ? '账号匹配池'
    : trendScopeAccountId
      ? '探索池 · 完成定位后自动筛选'
      : '公共探索池'
  const openBrief = (brief: CreativeBrief) => onNavigate?.(`chat-brief:${encodeCreativeBrief(brief)}`)
  const ideaBrief = (idea?: Suggestion): CreativeBrief => {
    if (!idea) {
      return {
        id: `daily-${Date.now()}`,
        kind: 'daily',
        title: '今日最值得推进的选题判断',
        source_label: '工作台 · AI 今日判断',
        evidence: [
          { label: '已采集热点', value: `${trends.length} 条` },
          { label: '候选选题', value: `${suggestions.length} 条` },
        ],
        recommended_action: '请基于今天已采集的真实热点、当前账号定位和历史表现，帮我判断今天最值得推进的选题，并给出可执行的内容打磨方案。不要编造未验证数据。',
        created_at: new Date().toISOString(),
      }
    }
    return {
      id: idea.id || `idea-${Date.now()}`,
      kind: 'idea',
      title: idea.trend,
      source_platform: idea.trend_source,
      source_label: PLATFORM_NAMES[idea.trend_source] || idea.trend_source || '未知平台',
      heat: idea.hot_level || idea.estimated_traffic || '待判断',
      hot_level: idea.hot_level,
      target_audience: idea.target_audience,
      angles: idea.angles || [],
      evidence: [
        idea.estimated_traffic ? { label: '预估流量', value: idea.estimated_traffic } : null,
        idea.hot_level ? { label: '热度等级', value: idea.hot_level } : null,
      ].filter(Boolean) as Array<{ label: string; value: string }>,
      recommended_action: '请先判断它是否适合当前账号，再给我 3 个更强的切入角度、标题、脚本结构和需要补充的证据。不要编造未验证数据。',
      created_at: new Date().toISOString(),
    }
  }
  const trendBrief = (trend: TrendItem): CreativeBrief => ({
    id: `trend-${trend.source_platform || 'unknown'}-${trend.rank || Date.now()}`,
    kind: 'trend',
    title: trend.title,
    source_platform: trend.source_platform,
    source_label: PLATFORM_NAMES[trend.source_platform || ''] || trend.source_platform || '未知平台',
    heat: String(trend.heat || trend.heat_value || ''),
    rank: trend.rank,
    evidence: [
      trend.rank ? { label: '热榜排名', value: String(trend.rank) } : null,
      trend.heat || trend.heat_value ? { label: '热度', value: String(trend.heat || trend.heat_value) } : null,
    ].filter(Boolean) as Array<{ label: string; value: string }>,
    recommended_action: '请先做账号匹配判断，再给出可创作角度、风险点、标题和脚本大纲。只使用可追溯证据，不要补假数据。',
    created_at: new Date().toISOString(),
  })

  useEffect(() => {
    if (platformTrendGroups.length <= 1) return
    const timer = window.setInterval(() => {
      setActiveTrendPlatform((current) => (current + 1) % platformTrendGroups.length)
      setActiveTrendItem(0)
    }, 15000)
    return () => window.clearInterval(timer)
  }, [platformTrendGroups.length])

  useEffect(() => {
    if (activeTrendItems.length <= 1) return
    const timer = window.setInterval(() => {
      setActiveTrendItem((current) => (current + 1) % activeTrendItems.length)
    }, 5000)
    return () => window.clearInterval(timer)
  }, [activeTrendGroup?.platform, activeTrendItems.length])

  useEffect(() => {
    if (suggestions.length <= 1) return
    const timer = window.setInterval(() => {
      setActiveIdeaItem((current) => (current + 1) % suggestions.length)
    }, 5000)
    return () => window.clearInterval(timer)
  }, [suggestions.length])

  return (
    <div className="dashboard-page animate-fade-up">
      <section className="dashboard-intro">
        <div>
          <div className="page-kicker">{date}</div>
          <h1>早上好，杨胜果。</h1>
          <p>{trends.length ? `市场扫描已发现 ${data.trending_topics_today} 个热点。` : '还没有热点数据，后台采集完成后会自动出现在这里。'}</p>
        </div>
        <button className="primary-action" onClick={() => openBrief(ideaBrief(leadSuggestion))}>
          <Sparkles size={16} /> 开始今日任务 <ArrowRight size={15} />
        </button>
      </section>

      <section className="platform-command-center">
        <div className="data-center-shell">
          <div className="section-heading data-center-heading">
            <div>
              <span className="page-kicker">DATA CENTER</span>
              <h2>数据罗盘</h2>
              <p>{visibleAccounts.length ? drillLabel : '连接账号后自动汇总各平台表现'}</p>
            </div>
            <div className="data-center-actions">
              {viewLevel !== 'overview' && (
                <button
                  className="text-action"
                  onClick={() => {
                    setSelectedPlatform(null)
                    setSelectedAccountId(null)
                  }}
                >
                  返回全平台
                </button>
              )}
              <div className="range-switch" aria-label="数据时间范围">
                {METRIC_RANGES.map((range) => (
                  <button key={range.id} className={metricRange === range.id ? 'is-active' : ''} onClick={() => setMetricRange(range.id)}>
                    {range.label}
                  </button>
                ))}
              </div>
              <button className="text-action" onClick={() => onNavigate?.('accounts')}>管理账号 <ArrowRight size={14} /></button>
            </div>
          </div>
        {visibleAccounts.length > 0 ? (
          <>
            <div className="data-hero-grid">
              <div className="data-hero-card">
                {selectedAccount && selectedMetrics ? (
                  <>
                    <div className="hero-gauges account-detail-gauges">
                      <Gauge icon={Users} label="涨粉" value={selectedMetrics.growth} progress={Math.abs(selectedMetrics.growth) / maxGrowth} positive />
                      <Gauge icon={Eye} label="浏览" value={selectedMetrics.views} progress={Math.abs(selectedMetrics.views) / maxViews} />
                      <Gauge icon={Heart} label="点赞" value={selectedMetrics.likes} progress={Math.abs(selectedMetrics.likes) / maxLikes} />
                    </div>
                    <div className="data-quick-stats">
                      <div><span>总粉丝</span><strong>{formatNumber(numberOf(selectedAccount.stats.followers))}</strong></div>
                      <div><span>累计播放</span><strong>{formatNumber(numberOf(selectedAccount.stats.total_views))}</strong></div>
                      <div><span>累计点赞</span><strong>{formatNumber(numberOf(selectedAccount.stats.total_likes))}</strong></div>
                      <div><span>作品数</span><strong>{formatNumber(numberOf(selectedAccount.stats.videos_count))}</strong></div>
                    </div>
                  </>
                ) : (
                  <div className="hero-gauges segmented-gauge-row">
                    {METRIC_DEFS.map(({ key, label, icon }) => (
                      <SegmentedGauge
                        key={key}
                        icon={icon}
                        label={label}
                        value={metricTotalForLayer(key, visibleAccounts, metricRange, activePlatform)}
                        segments={segmentsForLayer(key, visibleAccounts, metricRange, activePlatform)}
                        onSelect={(segment) => {
                          if (segment.kind === 'platform') {
                            setSelectedPlatform(segment.id)
                            setSelectedAccountId(null)
                          } else {
                            setSelectedAccountId(segment.id)
                            setSelectedPlatform(segment.platform || activePlatform)
                          }
                        }}
                      />
                    ))}
                  </div>
                )}
              </div>
            </div>
            <PlatformTrendChart
              accounts={visibleAccounts}
              selectedPlatform={activePlatform}
              selectedAccountId={selectedAccount?.id || null}
              range={metricRange}
              onSelectPlatform={(platform) => {
                setSelectedPlatform(platform)
                setSelectedAccountId(null)
              }}
              onSelectAccount={(accountId) => setSelectedAccountId(accountId)}
            />
            <OperatingPulseStrip
              contentPipeline={contentPipeline}
              publishingReceipts={publishingReceipts}
              onNavigate={onNavigate}
            />
            <div className="platform-compass-grid platform-switch-strip">
              {viewLevel !== 'overview' && (
                <button className="platform-compass-card" onClick={() => {
                  setSelectedPlatform(null)
                  setSelectedAccountId(null)
                }}>
                  <div className="compass-platform"><strong>全平台</strong><span>返回第一层</span></div>
                  <div className="platform-mini-metrics"><span>查看平台占比</span></div>
                </button>
              )}
              {visibleAccounts.map((account) => {
                const metrics = accountMetricsForRange(account, metricRange)
                const isRelevant = !activePlatform || account.platform === activePlatform || selectedAccountId === account.id
                return (
                  <button key={account.id} className={`platform-compass-card ${selectedAccount?.id === account.id ? 'is-selected' : ''} ${isRelevant ? '' : 'is-muted'}`} onClick={() => {
                    setSelectedPlatform(account.platform)
                    setSelectedAccountId(account.id)
                  }}>
                    <div className="compass-platform"><strong>{PLATFORM_NAMES[account.platform] || account.platform}</strong><span>{account.label}</span></div>
                    <div className="platform-mini-metrics">
                      <span>涨粉 <strong>{signed(formatNumber(metrics.growth), metrics.growth)}</strong></span>
                      <span>浏览 <strong>{formatNumber(metrics.views)}</strong></span>
                    </div>
                  </button>
                )
              })}
            </div>
          </>
        ) : (
          <>
            <button className="empty-compass" onClick={() => onNavigate?.('accounts')}>连接一个平台后，这里会出现它的数据驾驶舱</button>
            <OperatingPulseStrip
              contentPipeline={contentPipeline}
              publishingReceipts={publishingReceipts}
              onNavigate={onNavigate}
            />
          </>
        )}
        </div>
      </section>

      <div className="dashboard-grid">
        <section className="opportunity-panel">
          <div className="section-heading">
            <div><span className="page-kicker">TREND RADAR</span><h2>趋势</h2></div>
            <span className={`relevance-pill ${trendRelevance.hasPositioning ? 'is-matched' : ''}`}>{trendScopeLabel}</span>
            <span className="decision-count">{trends.length}</span>
          </div>

          <div className="trend-live-stage">
            {activeTrendGroup ? (
              <>
                <div className="trend-live-head">
                  <div className="trend-live-platform">
                    <Flame size={13} />
                    <strong>{PLATFORM_NAMES[activeTrendGroup.platform] || activeTrendGroup.platform}</strong>
                    <small>{activeTrendGroup.items.length} 条</small>
                  </div>
                  <div className="trend-platform-dots">
                    {platformTrendGroups.map((group, index) => (
                      <button
                        key={group.platform}
                        className={index === activeTrendIndex ? 'is-active' : ''}
                        title={PLATFORM_NAMES[group.platform] || group.platform}
                        onClick={() => setActiveTrendPlatform(index)}
                      />
                    ))}
                  </div>
                </div>
                <div className="trend-flip-window">
                  <div className="trend-flip-stack">
                    {visibleTrends.map((trend, index) => (
                      <button key={`${activeTrendGroup.platform}-${index}-${trend.rank}-${trend.title}`} className="trend-flip-row" style={{ animationDelay: `${index * 55}ms` }} onClick={() => {
                        const targetIndex = activeTrendItems.indexOf(trend)
                        if (targetIndex >= 0) setActiveTrendItem(targetIndex)
                        openBrief(trendBrief(trend))
                      }}>
                        <span>{String(trend.rank || index + 1).padStart(2, '0')}</span>
                        <strong>{trend.title}</strong>
                        <small>{formatTrendSignal(trend, index)}</small>
                      </button>
                    ))}
                  </div>
                </div>
              </>
            ) : <div className="empty-inline">暂无热点，等待后台采集新数据。</div>}
          </div>
        </section>

        <aside className="decision-panel">
          <div className="section-heading compact">
            <div><span className="page-kicker">IDEAS</span><h2>选题</h2></div>
            <span className="decision-count">{suggestions.length}</span>
          </div>
          {visibleIdeas.length ? (
            <div className="trend-flip-window idea-flip-window">
              <div className="trend-flip-stack">
                {visibleIdeas.map((idea, index) => (
                  <button key={`idea-${index}-${idea.id}`} className="trend-flip-row" style={{ animationDelay: `${index * 55}ms` }} onClick={() => {
                    const targetIndex = suggestions.indexOf(idea)
                    if (targetIndex >= 0) setActiveIdeaItem(targetIndex)
                    openBrief(ideaBrief(idea))
                  }}>
                    <span>{String(index + 1).padStart(2, '0')}</span>
                    <strong>{index === 0 ? idea.trend : (idea.angles[0] || idea.trend)}</strong>
                    <small>{idea.hot_level || '待判断'}</small>
                  </button>
                ))}
              </div>
            </div>
          ) : <div className="empty-inline">暂无待决策选题</div>}
          <button className="all-tasks" onClick={() => openBrief({
            id: `all-tasks-${Date.now()}`,
            kind: 'all_tasks',
            title: '今日全部候选选题排序',
            source_label: '工作台 · 选题池',
            evidence: [
              { label: '候选选题', value: `${suggestions.length} 条` },
              { label: '热点样本', value: `${trends.length} 条` },
            ],
            recommended_action: '请打开今天的全部候选选题，按当前账号适配度、证据质量、创作成本和预期传播潜力排序，并告诉我先做哪一个。',
            created_at: new Date().toISOString(),
          })}>查看全部任务 <ArrowRight size={14} /></button>
        </aside>
      </div>

    </div>
  )
}

function numberOf(value: unknown) {
  const parsed = Number(value || 0)
  return Number.isFinite(parsed) ? parsed : 0
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN', { notation: value >= 10_000 ? 'compact' : 'standard', maximumFractionDigits: 1 }).format(value)
}

function signed(value: string, raw: number) {
  return raw > 0 ? `+${value}` : value
}

function rangeLabel(range: MetricRange) {
  return METRIC_RANGES.find((item) => item.id === range)?.label || '今日'
}

function rangeDays(range: MetricRange) {
  return METRIC_RANGES.find((item) => item.id === range)?.days || 1
}

function sortedHistory(account: OverviewData['platform_accounts'][number]) {
  return [...(account.history || [])]
    .filter((item) => item.at)
    .sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime())
}

function historyWindow(account: OverviewData['platform_accounts'][number], range: MetricRange) {
  const history = sortedHistory(account)
  if (!history.length) return []
  const days = rangeDays(range)
  const cutoff = Date.now() - days * 24 * 60 * 60 * 1000
  const windowed = history.filter((item) => new Date(item.at).getTime() >= cutoff)
  return windowed.length ? windowed : history.slice(-Math.min(history.length, days))
}

function metricDeltaFromHistory(account: OverviewData['platform_accounts'][number], range: MetricRange, field: 'followers' | 'views', current: number) {
  const windowed = historyWindow(account, range)
  if (windowed.length < 2) return 0
  const first = numberOf(windowed[0][field])
  return current - first
}

function accountMetricsForRange(account: OverviewData['platform_accounts'][number], range: MetricRange) {
  const stats = account.stats || {}
  const followers = numberOf(stats.followers)
  const views = numberOf(stats.total_views)
  const historyViewsDelta = metricDeltaFromHistory(account, range, 'views', views)
  const historyFollowerDelta = metricDeltaFromHistory(account, range, 'followers', followers)

  if (range === 'today') {
    return {
      growth: numberOf(stats.follower_growth_today),
      views: Math.max(0, historyViewsDelta || numberOf(stats.views_today)),
      likes: numberOf(stats.likes_today),
    }
  }
  if (range === 'month') {
    return {
      growth: numberOf(stats.new_followers_30d) || historyFollowerDelta,
      views: Math.max(0, numberOf(stats.views_30d) || historyViewsDelta),
      likes: numberOf(stats.likes_30d),
    }
  }
  return {
    growth: historyFollowerDelta,
    views: Math.max(0, historyViewsDelta || numberOf(stats.views_7d)),
    likes: numberOf(stats.likes_7d),
  }
}

function groupTrendsByPlatform(trends: TrendItem[]) {
  const grouped = new Map<string, TrendItem[]>()
  trends.forEach((trend) => {
    const key = trend.source_platform || 'unknown'
    grouped.set(key, [...(grouped.get(key) || []), trend])
  })
  return Array.from(grouped.entries()).map(([platform, items]) => ({ platform: platform as Platform, items }))
}

function groupAccountsByPlatform(accounts: OverviewData['platform_accounts']) {
  const grouped = new Map<string, OverviewData['platform_accounts']>()
  accounts.forEach((account) => {
    grouped.set(account.platform, [...(grouped.get(account.platform) || []), account])
  })
  return Array.from(grouped.entries()).map(([platform, items]) => ({ platform, accounts: items }))
}

function rotateItems<T>(items: T[], start: number, count: number) {
  if (!items.length) return []
  return Array.from({ length: Math.min(count, items.length) }, (_, offset) => items[(start + offset) % items.length])
}

function formatTrendSignal(trend: TrendItem, index: number) {
  const heat = formatAudienceHeat(trend.heat || trend.heat_value) || `TOP ${trend.rank || index + 1}`
  const label = trend.relevance_label
  if (!label) return heat
  const reasons = (trend.match_reasons || []).slice(0, 2).join('、')
  return reasons ? `${label} · ${reasons} · ${heat}` : `${label} · ${heat}`
}

function OperatingPulseStrip({
  contentPipeline,
  publishingReceipts,
  onNavigate,
}: {
  contentPipeline: OverviewData['content_pipeline']
  publishingReceipts: OverviewData['publishing_receipts']
  onNavigate?: (page: string) => void
}) {
  const checkpoints = publishingReceipts.metric_checkpoints || { total: 0, scheduled: 0, collected: 0, due: 0 }
  const nextMetricLabel = publishingReceipts.next_metrics_at
    ? new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(publishingReceipts.next_metrics_at))
    : '暂无计划'
  const productionPrompt = encodeURIComponent(
    '请帮我生产一条可发布内容：先读取当前账号定位、今日热点和已有内容资产；如果证据足够，直接给出标题、开头、正文/脚本结构、CTA，并调用 marketing_draft_content_create 保存为内容资产草稿；如果证据不足，先告诉我缺什么，不要编造数据。',
  )
  return (
    <div className="operating-pulse-strip">
      <button className="operating-pulse-card" onClick={() => onNavigate?.(`chat-prompt:${productionPrompt}`)}>
        <span>内容生产</span>
        <strong>{formatNumber(contentPipeline.drafts)} 草稿</strong>
        <small>{contentPipeline.ready_to_publish ? `${contentPipeline.ready_to_publish} 条可发布` : '让 Agent 生成新草稿'}</small>
      </button>
      <button className="operating-pulse-card" onClick={() => onNavigate?.('factory')}>
        <span>发布回执</span>
        <strong>{formatNumber(publishingReceipts.verified)}/{formatNumber(publishingReceipts.total)}</strong>
        <small>{publishingReceipts.pending_verification ? `${publishingReceipts.pending_verification} 条待验证` : '无待验证回执'}</small>
      </button>
      <button className={`operating-pulse-card ${checkpoints.due ? 'needs-attention' : ''}`} onClick={() => onNavigate?.('factory')}>
        <span>指标回收</span>
        <strong>{formatNumber(checkpoints.collected)}/{formatNumber(checkpoints.total)}</strong>
        <small>{checkpoints.due ? `${checkpoints.due} 个到期` : `下次：${nextMetricLabel}`}</small>
      </button>
      <button className="operating-pulse-card" onClick={() => onNavigate?.('factory')}>
        <span>内容库存</span>
        <strong>{formatNumber(contentPipeline.total_assets)}</strong>
        <small>{contentPipeline.latest_draft?.title || '选题成稿后自动进入内容工厂'}</small>
      </button>
    </div>
  )
}

type GaugeSegment = {
  id: string
  label: string
  value: number
  color: string
  kind: 'platform' | 'account'
  platform?: string
}

function metricValue(account: OverviewData['platform_accounts'][number], range: MetricRange, key: MetricKey) {
  return accountMetricsForRange(account, range)[key]
}

function metricTotalForLayer(key: MetricKey, accounts: OverviewData['platform_accounts'], range: MetricRange, platform: string | null) {
  return accounts
    .filter((account) => !platform || account.platform === platform)
    .reduce((sum, account) => sum + metricValue(account, range, key), 0)
}

function segmentsForLayer(key: MetricKey, accounts: OverviewData['platform_accounts'], range: MetricRange, platform: string | null): GaugeSegment[] {
  if (platform) {
    const platformAccounts = accounts.filter((account) => account.platform === platform)
    return platformAccounts.map((account, index) => ({
      id: account.id,
      label: account.label || `账号 ${index + 1}`,
      value: metricValue(account, range, key),
      color: tintColor(PLATFORM_COLORS[account.platform] || '#f2796f', index),
      kind: 'account',
      platform: account.platform,
    }))
  }

  return groupAccountsByPlatform(accounts).map(({ platform: platformId, accounts: platformAccounts }) => ({
    id: platformId,
    label: PLATFORM_NAMES[platformId] || platformId,
    value: platformAccounts.reduce((sum, account) => sum + metricValue(account, range, key), 0),
    color: PLATFORM_COLORS[platformId] || '#f2796f',
    kind: 'platform',
    platform: platformId,
  }))
}

function tintColor(hex: string, index: number) {
  if (index === 0) return hex
  const variants = ['cc', 'aa', '88', 'e6']
  return `${hex}${variants[index % variants.length]}`
}

function SegmentedGauge({
  icon: Icon,
  label,
  value,
  segments,
  onSelect,
}: {
  icon: React.ElementType
  label: string
  value: number
  segments: GaugeSegment[]
  onSelect: (segment: GaugeSegment) => void
}) {
  const radius = 43
  const circumference = 2 * Math.PI * radius
  const gap = Math.min(3.4, circumference / Math.max(8, segments.length * 8))
  const visualTotal = segments.reduce((sum, segment) => sum + Math.max(0, Math.abs(segment.value)), 0)
  let consumed = 0

  return (
    <div className="segmented-gauge">
      <svg viewBox="0 0 110 110" aria-label={`${label}罗盘`}>
        <circle className="gauge-track" cx="55" cy="55" r={radius} />
        {segments.map((segment) => {
          const visualValue = visualTotal > 0 ? Math.max(0, Math.abs(segment.value)) : 1
          const baseTotal = visualTotal > 0 ? visualTotal : segments.length || 1
          const length = Math.max(8, (visualValue / baseTotal) * circumference - gap)
          const dashOffset = -consumed
          consumed += length + gap
          return (
            <circle
              key={segment.id}
              className="segmented-gauge-slice"
              cx="55"
              cy="55"
              r={radius}
              stroke={segment.color}
              strokeDasharray={`${length} ${circumference - length}`}
              strokeDashoffset={dashOffset}
              onClick={() => onSelect(segment)}
            >
              <title>{segment.label} · {formatNumber(segment.value)}</title>
            </circle>
          )
        })}
      </svg>
      <div className="gauge-center">
        <Icon size={14} />
        <strong>{value > 0 && label === '涨粉' ? '+' : ''}{formatNumber(value)}</strong>
        <span>{label}</span>
      </div>
    </div>
  )
}

function Gauge({ icon: Icon, label, value, progress, positive }: { icon: React.ElementType; label: string; value: number; progress: number; positive?: boolean }) {
  const radius = 38
  const circumference = 2 * Math.PI * radius
  const normalized = Math.max(0.04, Math.min(1, progress || 0))
  return (
    <div className="data-gauge">
      <svg viewBox="0 0 92 92"><circle className="gauge-track" cx="46" cy="46" r={radius} /><circle className={positive ? 'gauge-value positive-ring' : 'gauge-value'} cx="46" cy="46" r={radius} strokeDasharray={circumference} strokeDashoffset={circumference * (1 - normalized)} /></svg>
      <div className="gauge-center"><Icon size={12} /><strong>{value > 0 && positive ? '+' : ''}{formatNumber(value)}</strong><span>{label}</span></div>
    </div>
  )
}

function PlatformTrendChart({
  accounts,
  selectedPlatform,
  selectedAccountId,
  range,
  onSelectPlatform,
  onSelectAccount,
}: {
  accounts: OverviewData['platform_accounts']
  selectedPlatform: string | null
  selectedAccountId: string | null
  range: MetricRange
  onSelectPlatform: (platform: string) => void
  onSelectAccount: (accountId: string) => void
}) {
  const series = chartSeriesForLayer(accounts, selectedPlatform, selectedAccountId, range)
  const allValues = series.flatMap((item) => item.values)
  const max = Math.max(1, ...allValues)
  const maxLength = Math.max(0, ...series.map((item) => item.values.length))
  const hasChart = maxLength > 1 && allValues.length > 1
  const chartHint = selectedAccountId
    ? '该账号浏览变化'
    : selectedPlatform
      ? '点账号线进入详情'
      : '点平台线进入平台层'

  const linePoints = (values: number[]) => values.map((value, index) => {
    const x = values.length <= 1 ? 50 : index * (100 / (values.length - 1))
    const y = 40 - (value / max) * 34
    return `${x},${y}`
  }).join(' ')

  return (
    <div className="platform-detail-card data-chart-card">
      <div>
        <span className="page-kicker">CURVE</span>
        <h3>浏览曲线</h3>
        <p>{rangeLabel(range)} · {chartHint}</p>
        <div className="platform-chart-legend">
          {series.map((item) => (
            <button
              key={item.id}
              className={item.active ? 'is-active' : ''}
              onClick={() => item.kind === 'platform' ? onSelectPlatform(item.id) : onSelectAccount(item.id)}
            >
              <i style={{ background: item.color }} />{item.label}
            </button>
          ))}
        </div>
      </div>
      <div className="platform-line-chart multi-line">
        {hasChart ? (
          <svg viewBox="0 0 100 42" preserveAspectRatio="none">
            {[0.25, 0.5, 0.75].map((y) => <line key={y} className="chart-grid-line" x1="0" x2="100" y1={40 - y * 34} y2={40 - y * 34} />)}
            {series.map((item) => (
              item.values.length > 1 && (
                <polyline
                  key={item.id}
                  points={linePoints(item.values)}
                  onClick={() => item.kind === 'platform' ? onSelectPlatform(item.id) : onSelectAccount(item.id)}
                  style={{
                    stroke: item.color,
                    opacity: item.active ? 1 : 0.48,
                    strokeWidth: item.active ? 2.1 : 1.35,
                    cursor: 'pointer',
                  }}
                />
              )
            ))}
          </svg>
        ) : <div className="chart-empty">再同步一次数据后显示多平台真实趋势曲线</div>}
        <span>{rangeLabel(range)}浏览快照 · {series.length} 条线</span>
      </div>
    </div>
  )
}

function chartSeriesForLayer(
  accounts: OverviewData['platform_accounts'],
  selectedPlatform: string | null,
  selectedAccountId: string | null,
  range: MetricRange,
) {
  if (selectedAccountId) {
    const account = accounts.find((item) => item.id === selectedAccountId)
    return account ? [accountSeries(account, range, PLATFORM_COLORS[account.platform] || '#f2796f', true)] : []
  }

  if (selectedPlatform) {
    return accounts
      .filter((account) => account.platform === selectedPlatform)
      .map((account, index) => accountSeries(account, range, tintColor(PLATFORM_COLORS[account.platform] || '#f2796f', index), true))
  }

  return groupAccountsByPlatform(accounts).map(({ platform, accounts: platformAccounts }) => ({
    id: platform,
    kind: 'platform' as const,
    label: PLATFORM_NAMES[platform] || platform,
    color: PLATFORM_COLORS[platform] || '#f2796f',
    values: aggregateViewValues(platformAccounts, range),
    active: true,
  }))
}

function accountSeries(account: OverviewData['platform_accounts'][number], range: MetricRange, color: string, active: boolean) {
  const history = historyWindow(account, range)
  const rawValues = history.map((item) => numberOf(item.views))
  const fallback = numberOf(account.stats.total_views)
  return {
    id: account.id,
    kind: 'account' as const,
    label: account.label || PLATFORM_NAMES[account.platform] || account.platform,
    color,
    values: rawValues.length > 1 ? rawValues : Array.from({ length: 4 }, () => rawValues[0] || fallback),
    active,
  }
}

function aggregateViewValues(accounts: OverviewData['platform_accounts'], range: MetricRange) {
  const accountValues = accounts.map((account) => accountSeries(account, range, '#fff', true).values)
  const maxLength = Math.max(4, ...accountValues.map((values) => values.length))
  return Array.from({ length: maxLength }, (_, index) => accountValues.reduce((sum, values) => {
    const offset = Math.max(0, values.length - maxLength)
    const value = values[index + offset] ?? values[values.length - 1] ?? 0
    return sum + value
  }, 0))
}
