import { useState, useEffect, useCallback } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { api, PLATFORM_NAMES, PLATFORM_COLORS } from '@/api/client'
import { Radio, TrendingUp } from 'lucide-react'

const PLATFORM_TABS = [
  { id: 'all', label: '全部平台' },
  { id: 'weibo', label: '微博' },
  { id: 'douyin', label: '抖音' },
  { id: 'bilibili', label: 'B站' },
  { id: 'zhihu', label: '知乎' },
]

export default function Trending() {
  const [data, setData] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState('all')

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    return api.trending()
      .then((d) => setData(d as Record<string, unknown>))
      .catch((reason) => setError(String(reason?.message || reason || '趋势数据加载失败')))
      .finally(() => setLoading(false))
  }, [])
  useEffect(() => {
    load()
    const unsubscribe = window.marketingOS?.onTrendingUpdated(() => load())
    const timer = window.setInterval(load, 60_000)
    return () => { unsubscribe?.(); window.clearInterval(timer) }
  }, [load])

  const allTrends = (data?.top_trends as TrendItem[]) || []
  const trends = activeTab === 'all'
    ? allTrends
    : allTrends.filter((trend) => trend.source_platform === activeTab)
  const platformCounts = allTrends.reduce<Record<string, number>>((counts, trend) => {
    counts[trend.source_platform] = (counts[trend.source_platform] || 0) + 1
    return counts
  }, {})

  return (
    <div className="animate-fade-up space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <span className="page-kicker">TREND CENTER</span>
          <h2 className="text-2xl font-bold tracking-tight">趋势中心</h2>
          <p className="text-sm text-muted-foreground mt-1">跨平台实时热搜 · 多维度聚合</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />后台自动更新</div>
      </div>

      <div className="flex gap-2">
        {PLATFORM_TABS.map((t) => (
          <Button key={t.id} variant={activeTab === t.id ? 'default' : 'ghost'} size="sm" onClick={() => setActiveTab(t.id)}
            className={activeTab === t.id ? '' : 'text-muted-foreground'}>
            {t.label}{t.id === 'all' ? ` ${allTrends.length}` : platformCounts[t.id] ? ` ${platformCounts[t.id]}` : ''}
          </Button>
        ))}
      </div>

      <Card>
        <CardContent className="flex items-center gap-3 px-4 py-3">
          <Radio className="h-4 w-4 text-emerald-500" />
          <div className="flex-1">
            <div className="text-sm font-medium">公共热点持续更新，账号会话仅作为增强数据源</div>
            <div className="text-xs text-muted-foreground">应用启动后自动刷新，单个平台失败时继续展示其余来源或上次有效缓存。</div>
          </div>
          <Badge variant="outline">{data?.stale ? '使用有效缓存' : data?.cached_at ? '数据已同步' : '等待首次同步'}</Badge>
        </CardContent>
      </Card>

      {error ? (
        <Card><CardContent className="py-5 text-sm text-destructive">{error}</CardContent></Card>
      ) : loading ? (
        <div className="flex justify-center py-16">
          <div className="flex gap-1.5">{['','',''].map((_,i)=><div key={i} className="w-2 h-2 rounded-full bg-muted-foreground/20 animate-bounce" style={{animationDelay:`${i*0.1}s`}}/>)}</div>
        </div>
      ) : !data || data.status === 'no_data' ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-20">
            <TrendingUp className="h-12 w-12 text-muted-foreground/20 mb-4" />
            <h3 className="text-lg font-semibold mb-2">等待首次抓取</h3>
            <p className="text-sm text-muted-foreground">后台正在尝试公共数据源，成功后会自动出现在这里。</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-1">
          {trends.length === 0 ? (
            <Card><CardContent className="py-12 text-center text-sm text-muted-foreground">该平台本次没有可展示的热点</CardContent></Card>
          ) : trends.map((t, i) => (
            <Card key={i} className="hover:bg-accent/30 transition-colors group" style={{animationDelay:`${i*30}ms`}}>
              <CardContent className="flex items-center gap-4 px-5 py-3">
                <span className={`text-sm font-bold min-w-[32px] tabular-nums ${i<3?'text-primary':'text-muted-foreground/30'}`}>
                  {String(i+1).padStart(2,'0')}
                </span>
                {i<3 && <Badge variant="default" className="text-[10px] px-1.5 py-0">HOT</Badge>}
                <span className="flex-1 text-sm font-medium truncate">{t.title}</span>
                <Badge variant="outline" className="text-[10px] font-medium"
                  style={{color: PLATFORM_COLORS[t.source_platform], borderColor: `${PLATFORM_COLORS[t.source_platform]}30`}}>
                  {PLATFORM_NAMES[t.source_platform]}
                </Badge>
                {(t.heat || t.heat_value) && <span className="text-xs text-muted-foreground min-w-[64px] text-right tabular-nums">{t.heat || t.heat_value}</span>}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
