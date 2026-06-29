import { useState, useEffect, useCallback } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { api, PLATFORM_NAMES, PLATFORM_COLORS } from '@/api/client'
import { LockKeyhole, RefreshCw, Search, TrendingUp } from 'lucide-react'

const PLATFORM_TABS = [
  { id: 'all', label: '全部平台' },
  { id: 'weibo', label: '微博' },
  { id: 'douyin', label: '抖音' },
  { id: 'bilibili', label: 'B站' },
]

export default function Trending() {
  const [data, setData] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [collecting, setCollecting] = useState(false)
  const [keyword, setKeyword] = useState('')
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
  useEffect(() => { load() }, [])

  const refresh = async () => {
    setRefreshing(true)
    setError('')
    try {
      await api.refreshTrending()
      await load()
    } catch (reason) {
      setError(String((reason as Error)?.message || reason || '热点抓取失败'))
    } finally {
      setRefreshing(false)
    }
  }

  const collectIndustry = async () => {
    const query = keyword.trim()
    if (!query) return
    if (!window.marketingOS) {
      setError('登录态行业采集只能在桌面应用中使用')
      return
    }
    setCollecting(true)
    setError('')
    try {
      const collected = await window.marketingOS.scrapeIndustry('douyin', query)
      await api.importTrending(collected)
      await load()
    } catch (reason) {
      setError(String((reason as Error)?.message || reason || '行业热点采集失败'))
    } finally {
      setCollecting(false)
    }
  }

  const allTrends = (data?.top_trends as TrendItem[]) || []
  const trends = activeTab === 'all'
    ? allTrends
    : allTrends.filter((trend) => trend.source_platform === activeTab)

  return (
    <div className="animate-fade-up space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <span className="page-kicker">TREND CENTER</span>
          <h2 className="text-2xl font-bold tracking-tight">趋势中心</h2>
          <p className="text-sm text-muted-foreground mt-1">跨平台实时热搜 · 多维度聚合</p>
        </div>
        <Button variant="outline" size="sm" onClick={refresh} disabled={refreshing} className="gap-1.5">
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} /> {refreshing ? '抓取中' : '刷新'}
        </Button>
      </div>

      <div className="flex gap-2">
        {PLATFORM_TABS.map((t) => (
          <Button key={t.id} variant={activeTab === t.id ? 'default' : 'ghost'} size="sm" onClick={() => setActiveTab(t.id)}
            className={activeTab === t.id ? '' : 'text-muted-foreground'}>
            {t.label}
          </Button>
        ))}
      </div>

      <Card>
        <CardContent className="flex items-center gap-3 px-4 py-3">
          <LockKeyhole className="h-4 w-4 text-emerald-500" />
          <div className="flex-1">
            <div className="text-sm font-medium">使用已登录的抖音会话采集行业内容</div>
            <div className="text-xs text-muted-foreground">Cookie 只保存在桌面应用内，不会传给 Python 后端。</div>
          </div>
          <div className="flex items-center gap-2 rounded-md border px-3 h-9 min-w-[260px]">
            <Search className="h-3.5 w-3.5 text-muted-foreground" />
            <input value={keyword} onChange={(event) => setKeyword(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && collectIndustry()} placeholder="例如：美妆、餐饮、AI 教育" className="min-w-0 flex-1 bg-transparent text-sm outline-none" />
          </div>
          <Button onClick={collectIndustry} disabled={!keyword.trim() || collecting}>{collecting ? '采集中…' : '登录态采集'}</Button>
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
            <p className="text-sm text-muted-foreground mb-6">点击刷新按钮触发多平台热点自动抓取</p>
            <Button onClick={refresh} disabled={refreshing}><RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />立即抓取</Button>
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
                {t.heat && <span className="text-xs text-muted-foreground min-w-[64px] text-right tabular-nums">{t.heat}</span>}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
