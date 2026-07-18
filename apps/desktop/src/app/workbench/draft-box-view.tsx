import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { AlertCircle, Archive, ArchiveOff, FileText, Loader2, MonitorPlay, RefreshCw } from '@/lib/icons'
import { $selectedMarketingAccountId } from '@/store/marketing'

import { ProductPage } from './business-surfaces'
import type { StartMarketingOperation } from './operations'
import { userFacingError } from './user-facing-copy'

type DraftObjectType = 'content_asset' | 'video_production'
type DraftTab = 'active' | 'archived'

export interface DraftBoxItem {
  can_archive: boolean
  can_resume: boolean
  content_kind: 'article' | 'video' | 'video_source'
  created_at: string
  failure_code: string
  human_review_status: string
  id: string
  object_type: DraftObjectType
  previous_status: string
  source_asset_id: string
  status: string
  title: string
  updated_at: string
  version: number
}

interface DraftBoxViewProps {
  onOpenArticle: (assetId: string) => void
  onOpenVideo: (productionId: string) => void
  onStartOperation: StartMarketingOperation
  requestGateway: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
}

export function DraftBoxView({ onOpenArticle, onOpenVideo, onStartOperation, requestGateway }: DraftBoxViewProps) {
  const accountId = useStore($selectedMarketingAccountId) || 'prospect_default'
  const [tab, setTab] = useState<DraftTab>('active')
  const [items, setItems] = useState<DraftBoxItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [archiveTarget, setArchiveTarget] = useState<DraftBoxItem | null>(null)
  const [restoringId, setRestoringId] = useState('')

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')

    try {
      const result = await requestGateway<{ items: DraftBoxItem[] }>('marketing.drafts.list', {
        account_id: accountId,
        archived: tab === 'archived',
        limit: 100
      })

      setItems(result.items || [])
    } catch (cause) {
      setItems([])
      setError(userFacingError(cause, '草稿箱暂时无法读取，请稍后重试。'))
    } finally {
      setLoading(false)
    }
  }, [accountId, requestGateway, tab])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const counts = useMemo(
    () => ({
      article: items.filter(item => item.content_kind === 'article').length,
      video: items.filter(item => item.content_kind !== 'article').length
    }),
    [items]
  )

  const continueDraft = (item: DraftBoxItem) => {
    if (item.object_type === 'video_production') {
      onOpenVideo(item.id)

      return
    }

    if (item.content_kind === 'video_source') {
      onStartOperation({
        accountId,
        kind: 'content.resume',
        targetId: item.id,
        title: item.title || '继续视频草稿'
      })

      return
    }

    onOpenArticle(item.id)
  }

  const archive = async (item: DraftBoxItem) => {
    await requestGateway('marketing.draft.archive', {
      account_id: accountId,
      confirmed: true,
      object_id: item.id,
      object_type: item.object_type
    })
    setNotice(`“${item.title || '未命名草稿'}”已移入归档。`)
    await refresh()
  }

  const restore = async (item: DraftBoxItem) => {
    setRestoringId(item.id)
    setError('')

    try {
      await requestGateway('marketing.draft.restore', {
        account_id: accountId,
        object_id: item.id,
        object_type: item.object_type
      })
      setNotice(`“${item.title || '未命名草稿'}”已恢复，可以继续推进。`)
      await refresh()
    } catch (cause) {
      setError(userFacingError(cause, '草稿恢复失败，请稍后重试。'))
    } finally {
      setRestoringId('')
    }
  }

  return (
    <ProductPage
      action={
        <Button aria-label="刷新草稿箱" onClick={() => void refresh()} size="icon-sm" variant="ghost">
          <RefreshCw className={`size-4 ${loading ? 'animate-spin' : ''}`} />
        </Button>
      }
      description="做到一半的图文和视频统一留在这里；归档不会删除历史，恢复后继续原管线。"
      maxWidth="1180px"
      title="草稿箱"
    >
      {error ? (
        <p className="mb-5 flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/6 px-4 py-3 text-xs text-red-600">
          <AlertCircle className="size-4" /> {error}
        </p>
      ) : null}
      {notice ? (
        <p className="mb-5 rounded-xl border border-emerald-500/20 bg-emerald-500/6 px-4 py-3 text-xs text-emerald-700">
          {notice}
        </p>
      ) : null}

      <section>
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-(--ui-stroke-tertiary) pb-3">
          <div className="flex items-center gap-1 rounded-full bg-(--ui-fill-secondary) p-1">
            <DraftTabButton active={tab === 'active'} label="进行中" onClick={() => setTab('active')} />
            <DraftTabButton active={tab === 'archived'} label="已归档" onClick={() => setTab('archived')} />
          </div>
          <span className="text-xs tabular-nums text-(--ui-text-tertiary)">
            图文 {counts.article} · 视频 {counts.video}
          </span>
        </header>

        {loading && !items.length ? (
          <div className="grid min-h-52 place-items-center text-xs text-(--ui-text-tertiary)">
            <span className="flex items-center gap-2">
              <Loader2 className="size-4 animate-spin" /> 正在读取草稿
            </span>
          </div>
        ) : items.length ? (
          <div className="divide-y divide-(--ui-stroke-tertiary)">
            {items.map(item => (
              <DraftRow
                item={item}
                key={`${item.object_type}:${item.id}`}
                onArchive={() => setArchiveTarget(item)}
                onContinue={() => continueDraft(item)}
                onRestore={() => void restore(item)}
                restoring={restoringId === item.id}
                tab={tab}
              />
            ))}
          </div>
        ) : (
          <div className="grid min-h-52 place-items-center text-center">
            <div>
              <Archive className="mx-auto size-5 text-(--ui-text-tertiary)" />
              <strong className="mt-3 block text-sm">{tab === 'active' ? '没有待继续的草稿' : '归档区是空的'}</strong>
              <p className="mt-2 text-xs text-(--ui-text-tertiary)">
                {tab === 'active' ? '内容工厂里的半成品会自动汇总到这里。' : '从进行中归档的内容会保留在这里。'}
              </p>
            </div>
          </div>
        )}
      </section>

      <ConfirmDialog
        confirmLabel="移入归档"
        description="草稿和关联生产计划会一起归档，但不会删除；之后可以从“已归档”恢复。"
        destructive
        onClose={() => setArchiveTarget(null)}
        onConfirm={() => (archiveTarget ? archive(archiveTarget) : Promise.resolve())}
        open={Boolean(archiveTarget)}
        title={`归档“${archiveTarget?.title || '未命名草稿'}”？`}
      />
    </ProductPage>
  )
}

function DraftRow({
  item,
  onArchive,
  onContinue,
  onRestore,
  restoring,
  tab
}: {
  item: DraftBoxItem
  onArchive: () => void
  onContinue: () => void
  onRestore: () => void
  restoring: boolean
  tab: DraftTab
}) {
  const isArticle = item.content_kind === 'article'

  return (
    <article className="flex flex-wrap items-center gap-4 py-4">
      <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-(--ui-fill-secondary) text-(--ui-text-secondary)">
        {isArticle ? <FileText className="size-4" /> : <MonitorPlay className="size-4" />}
      </span>
      <div className="min-w-48 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <strong className="max-w-[36rem] truncate text-sm">{item.title || '未命名草稿'}</strong>
          <span className="rounded-full bg-(--ui-fill-secondary) px-2 py-0.5 text-[0.65rem] text-(--ui-text-tertiary)">
            {isArticle ? '图文' : '视频'}
          </span>
        </div>
        <p className="mt-1 text-xs text-(--ui-text-tertiary)">
          第 {item.version || 1} 版 · {draftStatusLabel(item)} · {formatUpdatedAt(item.updated_at)}
        </p>
        {item.failure_code ? <p className="mt-1 text-xs text-red-600">阻塞原因：{item.failure_code}</p> : null}
      </div>
      <div className="ml-auto flex items-center gap-2">
        {tab === 'active' ? (
          <>
            {item.can_archive ? (
              <Button aria-label={`归档 ${item.title}`} onClick={onArchive} size="sm" variant="ghost">
                <Archive className="size-4" /> 归档
              </Button>
            ) : null}
            <Button onClick={onContinue} size="sm">
              继续
            </Button>
          </>
        ) : (
          <Button disabled={restoring} onClick={onRestore} size="sm" variant="outline">
            {restoring ? <Loader2 className="size-4 animate-spin" /> : <ArchiveOff className="size-4" />} 恢复
          </Button>
        )}
      </div>
    </article>
  )
}

function DraftTabButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      aria-pressed={active}
      className={`rounded-full px-4 py-1.5 text-xs transition-colors ${
        active ? 'bg-(--ui-sidebar-surface-background) text-foreground shadow-sm' : 'text-(--ui-text-tertiary)'
      }`}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  )
}

function draftStatusLabel(item: DraftBoxItem): string {
  if (item.status === 'archived') {
    return `归档前：${statusText(item.previous_status)}`
  }

  if (item.status === 'completed' && item.human_review_status !== 'accepted') {
    return '等待验收'
  }

  return statusText(item.status)
}

function statusText(status: string): string {
  return (
    {
      approved: '已确认制作',
      completed: '制作完成',
      draft: '草稿中',
      failed: '制作受阻',
      prepared: '待制作',
      review_ready: '等待审核',
      running: '制作中'
    }[status] ||
    status ||
    '状态未知'
  )
}

function formatUpdatedAt(value: string): string {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return '更新时间未知'
  }

  return new Intl.DateTimeFormat('zh-CN', {
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    month: 'short'
  }).format(date)
}
