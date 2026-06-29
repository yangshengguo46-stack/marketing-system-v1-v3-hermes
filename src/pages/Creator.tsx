import { AudioWaveform, Check, ChevronRight, Circle, MoreHorizontal, Play, RefreshCw, Sparkles } from 'lucide-react'

const STEPS = [
  { name: '创意', detail: 'AI 创业的三个错误认知', state: 'done' },
  { name: '脚本', detail: '45 秒观点教程 · 326 字', state: 'done' },
  { name: '配音', detail: '专业自然 · 男声 03', state: 'working' },
  { name: '分镜', detail: '等待配音完成', state: 'waiting' },
  { name: '视频', detail: '等待生成', state: 'waiting' },
  { name: '封面与字幕', detail: '等待生成', state: 'waiting' },
]

export default function Creator() {
  return (
    <div className="factory-page animate-fade-up">
      <div className="standard-page-header">
        <div><span className="page-kicker">CONTENT FACTORY</span><h1>内容工厂</h1><p>AI 正在把创意变成可发布内容。</p></div>
        <button className="secondary-action"><MoreHorizontal size={17} /></button>
      </div>

      <div className="factory-layout">
        <aside className="pipeline-panel">
          <div className="pipeline-title"><span>生产流程</span><small>2 / 6 完成</small></div>
          <div className="pipeline-progress"><div /></div>
          <div className="pipeline-steps">
            {STEPS.map((step, index) => (
              <button className={`pipeline-step ${step.state} ${index === 2 ? 'selected' : ''}`} key={step.name}>
                <span className="step-index">{step.state === 'done' ? <Check size={12} /> : step.state === 'working' ? <RefreshCw size={12} /> : <Circle size={9} />}</span>
                <span><strong>{step.name}</strong><small>{step.detail}</small></span>
                <ChevronRight size={14} />
              </button>
            ))}
          </div>
        </aside>

        <section className="production-workspace">
          <div className="production-header">
            <div><span className="page-kicker">VOICE GENERATION</span><h2>配音</h2></div>
            <span className="working-badge"><i /> 生成中</span>
          </div>
          <div className="voice-preview">
            <div className="wave-visual" aria-label="音频波形">
              {Array.from({ length: 42 }).map((_, index) => <i key={index} style={{ height: `${16 + ((index * 17) % 46)}px` }} />)}
            </div>
            <div className="voice-controls">
              <button className="play-button" title="播放预览"><Play size={17} fill="currentColor" /></button>
              <div><strong>专业自然 · 男声 03</strong><span>00:00 / 00:45</span></div>
              <AudioWaveform size={20} />
            </div>
          </div>
          <div className="generation-status">
            <Sparkles size={17} />
            <div><strong>正在优化语气和停顿</strong><p>已完成文本清理，正在生成最终音频。预计还需 1 分钟。</p></div>
            <span>68%</span>
          </div>
          <div className="script-preview">
            <div className="script-header"><span>当前脚本</span><button><RefreshCw size={13} /> 重新生成</button></div>
            <p><mark>99% 的人理解错了 AI 创业。</mark> 真正的机会，不是再做一个聊天机器人，而是找到一个每天都在重复发生、又没人愿意解决的具体问题……</p>
          </div>
        </section>
      </div>
    </div>
  )
}
