import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { api } from '@/api/client'
import { Lightbulb, Clock, Users, ArrowRight } from 'lucide-react'
import { encodeCreativeBrief } from '@/lib/creativeBrief'

export default function Suggestions({ onNavigate }: { onNavigate?: (page: string) => void }) {
  const [data, setData] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState('')
  const [adding, setAdding] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  useEffect(() => {
    api.suggestions()
      .then((d) => setData(d as Record<string, unknown>))
      .catch((reason) => setError(String(reason?.message || reason || '选题建议加载失败')))
  }, [])

  const addToPublishing = async (suggestion: Suggestion) => {
    setAdding(suggestion.id)
    setNotice('')
    try {
      await api.createPublishingTask({
        title: suggestion.angles?.[0] || suggestion.trend,
        platform: suggestion.trend_source || 'douyin',
        status: 'review',
      })
      setNotice('已加入内容工厂的待审核队列。')
    } catch (reason) {
      setError(String((reason as Error)?.message || reason || '加入发布任务失败'))
    } finally {
      setAdding(null)
    }
  }
  const startDrafting = (suggestion: Suggestion) => {
    const brief: CreativeBrief = {
      id: suggestion.id || `idea-${Date.now()}`,
      kind: 'idea',
      title: suggestion.trend,
      source_platform: suggestion.trend_source,
      source_label: suggestion.trend_source || '未知平台',
      heat: suggestion.hot_level || suggestion.estimated_traffic || '待判断',
      hot_level: suggestion.hot_level,
      target_audience: suggestion.target_audience,
      angles: suggestion.angles || [],
      evidence: [
        suggestion.estimated_traffic ? { label: '预估流量', value: suggestion.estimated_traffic } : null,
        suggestion.hot_level ? { label: '热度等级', value: suggestion.hot_level } : null,
      ].filter(Boolean) as Array<{ label: string; value: string }>,
      recommended_action: '请先判断它是否适合当前账号，再给我 3 个更强的切入角度、标题、脚本结构和需要补充的证据。不要编造未验证数据。',
      created_at: new Date().toISOString(),
    }
    onNavigate?.(`chat-brief:${encodeCreativeBrief(brief)}`)
  }

  if (error) return <Card><CardContent className="py-5 text-sm text-destructive">{error}</CardContent></Card>
  if (!data) return (
    <div className="flex justify-center py-24">{[...Array(3)].map((_,i)=><div key={i} className="w-2 h-2 rounded-full bg-muted-foreground/20 animate-bounce mx-0.5" style={{animationDelay:`${i*0.1}s`}}/>)}</div>
  )

  if (data.status === 'no_data') return (
    <div className="animate-fade-up space-y-8">
      <div><span className="page-kicker">IDEA CENTER</span><h2 className="text-2xl font-bold">创意中心</h2><p className="text-sm text-muted-foreground mt-1">AI 智能匹配 · 个性化角度</p></div>
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-20">
          <Lightbulb className="h-12 w-12 text-muted-foreground/20 mb-4" />
          <h3 className="text-lg font-semibold mb-2">尚未生成选题建议</h3>
          <p className="text-sm text-muted-foreground">等待热点抓取完成后，AI 将基于用户画像自动生成</p>
        </CardContent>
      </Card>
    </div>
  )

  return (
    <div className="animate-fade-up space-y-8">
      <div>
        <span className="page-kicker">IDEA CENTER</span>
        <h2 className="text-2xl font-bold tracking-tight">创意中心</h2>
        <p className="text-sm text-muted-foreground mt-1">AI 智能匹配 · 个性化角度推荐</p>
      </div>
      {notice && <div className="empty-inline text-emerald-500">{notice}</div>}

      <div className="space-y-4">
        {(data.suggestions as Suggestion[] || []).map((s, i) => (
          <Card key={s.id} className="overflow-hidden" style={{animationDelay:`${i*80}ms`}}>
            <CardHeader className="flex flex-row items-center gap-3 px-6 py-4 border-b">
              <span className="text-xl">{s.hot_level}</span>
              <span className="flex-1 text-base font-semibold">{s.trend}</span>
              <Badge variant="secondary" className="text-[10px]">{s.trend_source}</Badge>
              <Badge variant="outline" className={`text-[11px] font-medium ${
                s.estimated_traffic === '高' ? 'border-emerald-500/30 text-emerald-500' :
                s.estimated_traffic === '中' ? 'border-amber-500/30 text-amber-500' :
                ''}`}>
                流量 {s.estimated_traffic}
              </Badge>
            </CardHeader>
            <CardContent className="p-5 space-y-2">
              {s.angles.map((angle: string, j: number) => (
                <div key={j} className="flex items-start gap-3 px-4 py-3 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors group cursor-default">
                  <span className={`flex h-6 w-6 items-center justify-center rounded-md text-[11px] font-bold flex-shrink-0 ${
                    j===0?'bg-primary/10 text-primary':j===1?'bg-chart-2/10 text-chart-2':'bg-muted text-muted-foreground'
                  }`}>{j+1}</span>
                  <span className="text-sm text-muted-foreground leading-relaxed group-hover:text-foreground transition-colors">{angle}</span>
                </div>
              ))}
            </CardContent>
            <div className="flex items-center gap-6 px-6 py-3 border-t bg-muted/20">
              <span className="text-xs text-muted-foreground flex items-center gap-1.5"><Clock className="h-3 w-3" />建议时长 30s</span>
              <span className="text-xs text-muted-foreground flex items-center gap-1.5"><Users className="h-3 w-3" />{s.target_audience}</span>
              <div className="flex-1" />
              <Button variant="outline" size="sm" disabled={adding === s.id} onClick={() => addToPublishing(s)}>{adding === s.id ? '添加中' : '加入发布任务'}</Button>
              <Button size="sm" className="gap-1.5" onClick={() => startDrafting(s)}>开始创作 <ArrowRight className="h-3.5 w-3.5" /></Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
