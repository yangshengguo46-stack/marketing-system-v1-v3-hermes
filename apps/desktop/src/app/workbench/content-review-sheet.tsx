import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Textarea } from '@/components/ui/textarea'
import { AlertTriangle, CheckCircle2, MessageSquareText } from '@/lib/icons'

import type { StartMarketingOperation } from './operations'
import { userFacingError } from './user-facing-copy'

export interface ContentAssetSummary {
  id: string
  account_id?: string
  experiment_id?: string
  human_review_note?: string
  human_review_status?: string
  human_reviewed_at?: string
  parent_id?: string
  platform?: string
  production_kind?: string
  review_status?: string
  status?: string
  target_platforms?: string[]
  title?: string
  topic?: string
  type?: string
  updated_at?: string
  validation_issue_count?: number
  validation_ready?: boolean
  version?: number
}

interface ContentAssetDetail extends ContentAssetSummary {
  content?: Record<string, unknown>
}

interface ContentReviewSheetProps {
  accountId: string
  asset: ContentAssetSummary | null
  onOpenChange: (open: boolean) => void
  onReviewed: (asset: ContentAssetDetail) => void
  onStartOperation: StartMarketingOperation
  requestGateway: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
}

export function ContentReviewSheet({
  accountId,
  asset,
  onOpenChange,
  onReviewed,
  onStartOperation,
  requestGateway
}: ContentReviewSheetProps) {
  const [detail, setDetail] = useState<ContentAssetDetail | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [note, setNote] = useState('')
  const [submitting, setSubmitting] = useState<'accepted' | 'changes_requested' | null>(null)

  useEffect(() => {
    if (!asset) {
      setDetail(null)
      setError('')
      setNote('')

      return
    }

    let cancelled = false
    setDetail(null)
    setError('')
    setLoading(true)
    setNote(asset.human_review_note || '')
    void requestGateway<{ asset: ContentAssetDetail }>('marketing.content.asset.get', {
      account_id: accountId,
      asset_id: asset.id
    })
      .then(result => {
        if (!cancelled) {
          setDetail({ ...asset, ...result.asset })
        }
      })
      .catch(cause => {
        if (!cancelled) {
          setError(userFacingError(cause, '内容读取失败，请稍后重试。'))
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [accountId, asset, requestGateway])

  const submitReview = async (decision: 'accepted' | 'changes_requested') => {
    if (!detail || (decision === 'changes_requested' && !note.trim())) {
      return
    }

    setSubmitting(decision)
    setError('')

    try {
      const result = await requestGateway<{ asset: ContentAssetDetail }>('marketing.content.asset.review', {
        account_id: accountId,
        asset_id: detail.id,
        confirmed: true,
        decision,
        note: note.trim()
      })

      setDetail(result.asset)
      onReviewed(result.asset)

      if (decision === 'changes_requested') {
        onOpenChange(false)
        onStartOperation({
          accountId,
          assetId: result.asset.id,
          kind: 'content.revise',
          note: note.trim(),
          title: result.asset.title || result.asset.topic || '内容资产',
          version: result.asset.version || 1
        })
      }
    } catch (cause) {
      setError(userFacingError(cause, '保存失败，请稍后重试。'))
    } finally {
      setSubmitting(null)
    }
  }

  const content = record(detail?.content)
  const parentDraft = record(content.parent_draft)
  const validation = record(content.validation)
  const variants = record(content.platform_variants)
  const evidence = records(content.evidence_pack)
  const visuals = records(content.visual_requirements)
  const prediction = record(content.prediction)
  const reaction = record(prediction.social_reaction_simulation)
  const scenarios = records(reaction.scenarios)
  const issues = strings(validation.issues)
  const pendingChecks = strings(validation.pending_human_checks)
  const accepted = detail?.human_review_status === 'accepted'

  const continueAsset = () => {
    if (!detail) {
      return
    }

    onStartOperation({
      accountId,
      kind: 'content.resume',
      targetId: detail.id,
      title: detail.title || detail.topic || '内容资产'
    })
    onOpenChange(false)
  }

  return (
    <Sheet onOpenChange={onOpenChange} open={Boolean(asset)}>
      <SheetContent className="w-[min(96vw,72rem)] gap-0 p-0 sm:max-w-[72rem]">
        <SheetHeader className="border-b border-(--ui-stroke-tertiary) px-7 py-6 pr-14">
          <div className="flex flex-wrap items-center gap-2">
            <ReviewPill status={detail?.human_review_status || asset?.human_review_status} />
            <span className="text-[0.66rem] font-semibold tracking-[0.15em] text-(--ui-text-tertiary)">
              第 {detail?.version || asset?.version || 1} 版
            </span>
          </div>
          <SheetTitle className="mt-2 text-xl tracking-[-0.03em]">
            {detail?.title || detail?.topic || asset?.title || asset?.topic || '未命名内容'}
          </SheetTitle>
          <SheetDescription>确认内容，或留下具体修改意见。</SheetDescription>
        </SheetHeader>

        <div className="min-h-0 flex-1 overflow-y-auto bg-(--ui-background) px-7 py-6">
          {loading ? <ReviewLoading /> : null}
          {error ? <ReviewError message={error} /> : null}
          {detail ? (
            <div className="space-y-5">
              <section className="grid gap-3 md:grid-cols-3">
                <SignalCard
                  detail={validation.ready === true ? '基础检查已通过' : `${issues.length} 个问题待处理`}
                  label="内容检查"
                  tone={validation.ready === true ? 'positive' : 'warning'}
                />
                <SignalCard
                  detail={humanReviewLabel(detail.human_review_status)}
                  label="你的确认"
                  tone={accepted ? 'positive' : 'neutral'}
                />
                <SignalCard
                  detail={strings(detail.target_platforms).join(' / ') || detail.platform || '平台待确认'}
                  label="目标平台"
                  tone="neutral"
                />
              </section>

              {issues.length || pendingChecks.length ? (
                <ReviewSection title="审核检查">
                  <div className="grid gap-3 md:grid-cols-2">
                    <CheckList items={issues} label="需要修改" warning />
                    <CheckList items={pendingChecks} label="需要你判断" />
                  </div>
                </ReviewSection>
              ) : null}

              <ReviewSection title="母稿">
                <ArticleBody body={text(parentDraft.body_markdown) || '当前没有可展示的正文。'} />
              </ReviewSection>

              {Object.keys(variants).length ? (
                <ReviewSection title="平台版本">
                  <div className="space-y-3">
                    {Object.entries(variants).map(([platform, value]) => {
                      const variant = record(value)

                      return (
                        <details
                          className="rounded-2xl border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) p-4"
                          key={platform}
                        >
                          <summary className="cursor-pointer text-sm font-semibold">
                            {platformLabel(platform)} · {text(variant.title) || '平台适配稿'}
                          </summary>
                          <ArticleBody body={text(variant.body_markdown) || '暂无正文'} className="mt-4" />
                        </details>
                      )
                    })}
                  </div>
                </ReviewSection>
              ) : null}

              {evidence.length ? (
                <ReviewSection title={`参考资料 · ${evidence.length} 条`}>
                  <div className="grid gap-3 md:grid-cols-2">
                    {evidence.map((item, index) => (
                      <div
                        className="rounded-2xl border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) p-4"
                        key={text(item.evidence_id) || index}
                      >
                        <strong className="block text-sm">{text(item.title) || '未命名证据'}</strong>
                        <p className="mt-2 break-all text-xs leading-5 text-(--ui-text-tertiary)">
                          {text(item.canonical_url) || '来源待补充'}
                        </p>
                        <span className="mt-3 inline-block rounded-full bg-(--ui-bg-quaternary) px-2 py-1 text-[0.65rem] text-(--ui-text-secondary)">
                          {verificationLabel(text(item.verification_level))}
                        </span>
                      </div>
                    ))}
                  </div>
                </ReviewSection>
              ) : null}

              {visuals.length ? (
                <ReviewSection title="视觉与版权要求">
                  <div className="grid gap-3 md:grid-cols-2">
                    {visuals.map((item, index) => (
                      <div className="rounded-2xl bg-(--ui-bg-quaternary) p-4" key={`${text(item.slot)}-${index}`}>
                        <strong className="text-sm">{text(item.slot) || '视觉位'}</strong>
                        <p className="mt-1 text-xs leading-5 text-(--ui-text-tertiary)">
                          {platformLabel(text(item.platform))} · {visualStatusLabel(text(item.status))} ·
                          {item.provenance_required === true ? ' 必须记录素材来源' : ' 无强制来源要求'}
                        </p>
                      </div>
                    ))}
                  </div>
                </ReviewSection>
              ) : null}

              {scenarios.length ? (
                <ReviewSection title="发布后评论预演">
                  <div className="mb-3 flex gap-2 rounded-xl border border-amber-500/20 bg-amber-500/8 p-3 text-xs leading-5 text-(--ui-text-secondary)">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" />
                    这里是匿名人群情景和合成评论样例，不是真实评论、具体用户预测或发布后事实。
                  </div>
                  <div className="space-y-3">
                    {scenarios.map((scenario, index) => (
                      <ReactionScenario index={index} key={text(scenario.id) || index} scenario={scenario} />
                    ))}
                  </div>
                </ReviewSection>
              ) : null}
            </div>
          ) : null}
        </div>

        <SheetFooter className="border-t border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) px-7 py-5">
          <label className="text-xs font-semibold" htmlFor="content-review-note">
            修改意见
          </label>
          <Textarea
            className="min-h-20 resize-none"
            id="content-review-note"
            onChange={event => setNote(event.target.value)}
            placeholder="如果需要修改，请具体说明保留什么、调整什么，以及希望达到的效果。"
            value={note}
          />
          <div className="flex flex-wrap justify-end gap-2">
            {accepted ? <Button onClick={continueAsset}>继续推进到发布准备</Button> : null}
            <Button
              disabled={!detail || !note.trim() || submitting !== null}
              onClick={() => void submitReview('changes_requested')}
              variant="outline"
            >
              {submitting === 'changes_requested' ? '正在记录…' : '提出修改并继续'}
            </Button>
            {!accepted ? (
              <Button
                disabled={!detail || detail.status !== 'review_ready' || submitting !== null}
                onClick={() => void submitReview('accepted')}
              >
                <CheckCircle2 className="size-4" />
                {submitting === 'accepted' ? '正在确认…' : '确认当前版本'}
              </Button>
            ) : null}
          </div>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}

function ReviewPill({ status }: { status?: string }) {
  const accepted = status === 'accepted'

  return (
    <span
      className={`rounded-full px-2.5 py-1 text-[0.65rem] font-semibold ${
        accepted ? 'bg-emerald-500/12 text-emerald-700' : 'bg-amber-500/12 text-amber-700'
      }`}
    >
      {humanReviewLabel(status)}
    </span>
  )
}

function ReviewLoading() {
  return (
    <div className="grid min-h-72 place-items-center text-sm text-(--ui-text-tertiary)">
      正在按需读取当前版本、证据与预演…
    </div>
  )
}

function ReviewError({ message }: { message: string }) {
  return (
    <div className="mb-4 flex gap-2 rounded-xl border border-red-500/20 bg-red-500/8 p-3 text-xs text-red-700">
      <AlertTriangle className="size-4 shrink-0" />
      {message}
    </div>
  )
}

function SignalCard({
  detail,
  label,
  tone
}: {
  detail: string
  label: string
  tone: 'neutral' | 'positive' | 'warning'
}) {
  const toneClass = {
    neutral: 'border-(--ui-stroke-tertiary)',
    positive: 'border-emerald-500/25 bg-emerald-500/6',
    warning: 'border-amber-500/25 bg-amber-500/6'
  }[tone]

  return (
    <div className={`rounded-2xl border bg-(--ui-sidebar-surface-background) p-4 ${toneClass}`}>
      <span className="text-[0.65rem] font-semibold tracking-[0.14em] text-(--ui-text-tertiary)">{label}</span>
      <strong className="mt-2 block text-sm">{detail}</strong>
    </div>
  )
}

function ReviewSection({ children, title }: { children: React.ReactNode; title: string }) {
  return (
    <section className="rounded-[22px] border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) p-5">
      <h3 className="text-base font-semibold">{title}</h3>
      <div className="mt-4">{children}</div>
    </section>
  )
}

function CheckList({ items, label, warning = false }: { items: string[]; label: string; warning?: boolean }) {
  return (
    <div className="rounded-xl bg-(--ui-bg-quaternary) p-4">
      <strong className="text-xs">{label}</strong>
      {items.length ? (
        <ul className="mt-2 space-y-1.5 text-xs leading-5 text-(--ui-text-secondary)">
          {items.map(item => (
            <li className="flex gap-2" key={item}>
              {warning ? (
                <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-amber-600" />
              ) : (
                <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-emerald-600" />
              )}
              {humanize(item)}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-xs text-(--ui-text-tertiary)">没有待处理项</p>
      )}
    </div>
  )
}

function ArticleBody({ body, className = '' }: { body: string; className?: string }) {
  return (
    <div
      className={`max-h-[32rem] overflow-y-auto whitespace-pre-wrap rounded-xl bg-(--ui-bg-quaternary) p-5 text-sm leading-7 text-(--ui-text-secondary) ${className}`}
    >
      {body}
    </div>
  )
}

function ReactionScenario({ index, scenario }: { index: number; scenario: Record<string, unknown> }) {
  const examples = strings(scenario.synthetic_comment_examples)
  const themes = strings(scenario.likely_comment_themes)
  const needProjection = text(scenario.need_projection)
  const cognitiveProjection = text(scenario.cognitive_projection)
  const existenceStrategy = text(scenario.existence_strategy) || text(scenario.existence_direction)

  const projectionLabels = [
    needProjection ? `需求投影 ${humanize(needProjection)}` : '',
    cognitiveProjection ? `认知投影 ${humanize(cognitiveProjection)}` : '',
    existenceStrategy ? `存在策略 ${humanize(existenceStrategy)}` : ''
  ].filter(Boolean)

  return (
    <div className="rounded-2xl border border-(--ui-stroke-tertiary) p-4">
      <div className="flex items-start gap-3">
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-(--ui-bg-quaternary) text-xs font-semibold">
          {String(index + 1).padStart(2, '0')}
        </span>
        <div className="min-w-0 flex-1">
          <strong className="block text-sm">{text(scenario.cohort) || '匿名评论人群'}</strong>
          <p className="mt-1 text-xs text-(--ui-text-tertiary)">
            {[humanize(text(scenario.stance)), ...projectionLabels].filter(Boolean).join(' · ')}
          </p>
          {themes.length ? <p className="mt-3 text-xs leading-5">可能主题：{themes.join('、')}</p> : null}
          {examples.map(example => (
            <blockquote
              className="mt-2 flex gap-2 rounded-xl bg-(--ui-bg-quaternary) p-3 text-xs leading-5 text-(--ui-text-secondary)"
              key={example}
            >
              <MessageSquareText className="mt-0.5 size-3.5 shrink-0" />
              <span>合成样例：“{example}”</span>
            </blockquote>
          ))}
        </div>
      </div>
    </div>
  )
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function records(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(record).filter(item => Object.keys(item).length) : []
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.map(text).filter(Boolean) : []
}

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function humanReviewLabel(status?: string): string {
  return (
    {
      accepted: '当前版本已确认',
      changes_requested: '已提出修改',
      pending: '待真人审核'
    }[status || ''] || '待真人审核'
  )
}

function platformLabel(platform?: string): string {
  return (
    {
      bilibili: 'B站',
      douyin: '抖音',
      kuaishou: '快手',
      multi_article: '多平台图文',
      tiktok: 'TikTok',
      wechat_channels: '视频号',
      wechat_official: '微信公众号',
      xiaohongshu: '小红书',
      youtube: 'YouTube',
      zhihu: '知乎'
    }[platform || ''] ||
    platform ||
    '共享'
  )
}

function humanize(value: string): string {
  return value ? value.replaceAll('_', ' ') : '待确认'
}

function verificationLabel(level: string): string {
  return (
    {
      corroborated: '多方印证',
      first_party: '来源已核验',
      official: '官方来源',
      provider_verified: '来源已核验',
      unverified: '待核验'
    }[level] || '待核验'
  )
}

function visualStatusLabel(status: string): string {
  return (
    {
      approved: '已确认',
      missing: '待补充',
      pending: '待确认',
      ready: '已准备'
    }[status] || '待确认'
  )
}
