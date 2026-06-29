import { useEffect, useState } from 'react'
import {
  ArrowRight,
  ChevronRight,
  Clock3,
  Flame,
  Lightbulb,
  Play,
  Sparkles,
  TrendingUp,
} from 'lucide-react'
import { api, PLATFORM_NAMES } from '@/api/client'

const EMPTY: OverviewData = {
  accounts_connected: 0,
  trending_topics_today: 0,
  suggestions_generated: 0,
  videos_published: 0,
  total_followers: 0,
  follower_growth_today: 0,
}

export default function Overview({ onNavigate }: { onNavigate?: (page: string) => void }) {
  const [data, setData] = useState<OverviewData>(EMPTY)
  const [trends, setTrends] = useState<TrendItem[]>([])
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])

  useEffect(() => {
    if (!window.marketingOS) return
    Promise.allSettled([api.overview(), api.trending(), api.suggestions()]).then(([overview, trending, ideas]) => {
      if (overview.status === 'fulfilled') setData(overview.value)
      if (trending.status === 'fulfilled') {
        const payload = trending.value as { top_trends?: TrendItem[] }
        setTrends(payload.top_trends || [])
      }
      if (ideas.status === 'fulfilled') {
        const payload = ideas.value as { suggestions?: Suggestion[] }
        setSuggestions(payload.suggestions || [])
      }
    })
  }, [])

  const date = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(new Date())
  const opportunities = trends.slice(0, 3).map((trend, index) => ({
    rank: String(index + 1).padStart(2, '0'),
    topic: trend.title,
    source: PLATFORM_NAMES[trend.source_platform] || trend.source_platform,
    growth: trend.heat ? String(trend.heat) : `TOP ${trend.rank || index + 1}`,
    score: index === 0 ? '高' : '中高',
    tone: ['mint', 'coral', 'amber'][index],
  }))
  const leadSuggestion = suggestions[0]

  return (
    <div className="dashboard-page animate-fade-up">
      <section className="dashboard-intro">
        <div>
          <div className="page-kicker">{date}</div>
          <h1>早上好，杨胜果。</h1>
          <p>{opportunities.length ? `市场扫描已发现 ${data.trending_topics_today} 个热点。` : '还没有热点数据，先到趋势中心执行一次抓取。'}</p>
        </div>
        <button className="primary-action" onClick={() => onNavigate?.('ideas')}>
          <Sparkles size={16} /> 开始今日任务 <ArrowRight size={15} />
        </button>
      </section>

      <section className="metric-strip">
        <Metric label="今日发现" value={data.trending_topics_today} unit="个热点" delta="跨 6 个平台" />
        <Metric label="内容建议" value={data.suggestions_generated} unit="条" delta="基于当前画像" accent />
        <Metric label="已连接" value={data.accounts_connected} unit="个账号" delta="账号中心实时同步" />
        <Metric label="今日增长" value={`+${data.follower_growth_today}`} unit="粉丝" delta={`总粉丝 ${data.total_followers}`} positive />
      </section>

      <div className="dashboard-grid">
        <section className="opportunity-panel">
          <div className="section-heading">
            <div>
              <span className="page-kicker">AI PRIORITY</span>
              <h2>今天值得做什么</h2>
            </div>
            <button className="text-action" onClick={() => onNavigate?.('trending')}>查看趋势中心 <ArrowRight size={14} /></button>
          </div>

          <div className="opportunity-list">
            {opportunities.map((item) => (
              <button key={item.topic} className="opportunity-row" onClick={() => onNavigate?.('ideas')}>
                <span className="opportunity-rank">{item.rank}</span>
                <span className={`opportunity-signal ${item.tone}`}><Flame size={17} /></span>
                <span className="opportunity-main">
                  <strong>{item.topic}</strong>
                  <small>{item.source}</small>
                </span>
                <span className="opportunity-growth"><TrendingUp size={13} /> {item.growth}</span>
                <span className="opportunity-score">潜力 {item.score}</span>
                <ChevronRight size={16} className="row-chevron" />
              </button>
            ))}
            {opportunities.length === 0 && <div className="empty-inline">暂无热点，前往趋势中心刷新数据。</div>}
          </div>

          <div className="ai-brief">
            <div className="brief-icon"><Sparkles size={17} /></div>
            <div>
              <strong>AI 今日判断</strong>
              <p>{leadSuggestion?.angles?.[0] || '完成热点抓取后，这里会显示与你的用户画像最匹配的内容建议。'}</p>
            </div>
            <button onClick={() => onNavigate?.('ideas')}>生成创意</button>
          </div>
        </section>

        <aside className="decision-panel">
          <div className="section-heading compact">
            <div><span className="page-kicker">YOUR MOVE</span><h2>等你决定</h2></div>
            <span className="decision-count">{suggestions.length}</span>
          </div>
          {suggestions.slice(0, 3).map((suggestion, index) => (
            <Decision key={suggestion.id} icon={index === 0 ? Play : Lightbulb} title={suggestion.trend} meta={suggestion.angles[0] || '等待确认方向'} tone={['coral', 'amber', 'mint'][index]} />
          ))}
          {suggestions.length === 0 && <div className="empty-inline">暂无待决策选题</div>}
          <button className="all-tasks">查看全部任务 <ArrowRight size={14} /></button>
        </aside>
      </div>

      <section className="schedule-section">
        <div className="section-heading">
          <div><span className="page-kicker">TODAY</span><h2>今日发布节奏</h2></div>
          <button className="text-action" onClick={() => onNavigate?.('publish')}>进入发布中心 <ArrowRight size={14} /></button>
        </div>
        <div className="schedule-list">
          <div className="empty-inline"><Clock3 size={14} /> 暂无真实发布任务</div>
        </div>
      </section>
    </div>
  )
}

function Metric({ label, value, unit, delta, accent, positive }: {
  label: string
  value: string | number
  unit: string
  delta: string
  accent?: boolean
  positive?: boolean
}) {
  return (
    <div className="metric-item">
      <span>{label}</span>
      <div><strong className={accent ? 'accent' : positive ? 'positive' : ''}>{value}</strong><small>{unit}</small></div>
      <p className={positive ? 'positive' : ''}>{delta}</p>
    </div>
  )
}

function Decision({ icon: Icon, title, meta, tone }: {
  icon: React.ElementType
  title: string
  meta: string
  tone: string
}) {
  return (
    <button className="decision-row">
      <span className={`decision-icon ${tone}`}><Icon size={16} /></span>
      <span><strong>{title}</strong><small>{meta}</small></span>
      <ChevronRight size={15} />
    </button>
  )
}
