import { useStore } from '@nanostores/react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { AlertCircle, CheckCircle2, ChevronRight, FileText, Loader2, RefreshCw } from '@/lib/icons'
import {
  $marketingAccounts,
  $marketingArticleDrafts,
  $marketingOperationTasks,
  $selectedMarketingAccountId,
  setMarketingArticleDraft
} from '@/store/marketing'

import { ProductPage } from './business-surfaces'
import { type ContentAssetSummary, ContentReviewSheet } from './content-review-sheet'
import type { StartMarketingOperation } from './operations'
import { userFacingError } from './user-facing-copy'

interface ArticleCreationViewProps {
  onBack: () => void
  onOpenDrafts?: () => void
  onStartOperation: StartMarketingOperation
  requestGateway: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
}

interface AccountContext {
  lifecycle?: {
    business_goal?: string
    data_gaps?: string[]
  }
}

export function ArticleCreationView({
  onBack,
  onOpenDrafts,
  onStartOperation,
  requestGateway
}: ArticleCreationViewProps) {
  const accountId = useStore($selectedMarketingAccountId) || 'prospect_default'
  const accounts = useStore($marketingAccounts)
  const drafts = useStore($marketingArticleDrafts)
  const operationTasks = useStore($marketingOperationTasks)
  const [searchParams, setSearchParams] = useSearchParams()
  const [assets, setAssets] = useState<ContentAssetSummary[]>([])
  const [context, setContext] = useState<AccountContext | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [operationTaskId, setOperationTaskId] = useState('')
  const openedResultTaskId = useRef('')
  const brief = drafts[accountId] || ''
  const account = accounts.find(item => item.id === accountId)

  const activeTask =
    operationTasks.find(task => task.id === operationTaskId) ||
    operationTasks.find(task => task.accountId === accountId && task.kind === 'content.article.start') ||
    null

  const articles = useMemo(
    () =>
      assets.filter(
        asset =>
          asset.production_kind === 'article_soft' ||
          asset.platform === 'multi_article' ||
          asset.type === 'article' ||
          asset.type === 'script'
      ),
    [assets]
  )

  const selectedAssetId = searchParams.get('asset') || ''
  const selectedAsset = assets.find(asset => asset.id === selectedAssetId) || null

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')

    try {
      const [assetResult, contextResult] = await Promise.all([
        requestGateway<{ assets: ContentAssetSummary[] }>('marketing.content.assets.list', {
          account_id: accountId,
          limit: 30
        }),
        requestGateway<AccountContext>('marketing.account.context', { account_id: accountId })
      ])

      setAssets(assetResult.assets || [])
      setContext(contextResult)
    } catch (cause) {
      setError(userFacingError(cause, '图文工作区暂时无法读取，请稍后重试。'))
    } finally {
      setLoading(false)
    }
  }, [accountId, requestGateway])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    if (activeTask?.state !== 'complete') {
      return
    }

    void refresh()
    setMarketingArticleDraft(accountId, '')
  }, [accountId, activeTask?.id, activeTask?.state, refresh])

  useEffect(() => {
    if (activeTask?.state !== 'complete' || openedResultTaskId.current === activeTask.id) {
      return
    }

    const result = activeTask.results?.find(item => item.object_type === 'content_asset')

    if (result && assets.some(asset => asset.id === result.object_id)) {
      openedResultTaskId.current = activeTask.id
      setSearchParams({ asset: result.object_id }, { replace: true })
    }
  }, [activeTask, assets, setSearchParams])

  const startArticle = () => {
    const normalized = brief.trim()

    if (normalized.length < 4) {
      setError('先说清楚这篇内容要解决什么问题，至少输入 4 个字。')

      return
    }

    setError('')

    const taskId = onStartOperation({
      accountId,
      kind: 'content.article.start',
      note: normalized,
      title: normalized.split(/\r?\n/, 1)[0]?.slice(0, 80) || '新的图文作品'
    })

    setOperationTaskId(taskId)
  }

  const evidenceDetail = context?.lifecycle?.business_goal
    ? `围绕经营目标「${context.lifecycle.business_goal}」推进；当前还有 ${context.lifecycle.data_gaps?.length || 0} 个证据缺口。`
    : account
      ? '将先读取这个账号的真实作品、受众和经营证据，再建立内容对象。'
      : '暂不登录也可以开始；Agent 会把公开研究、假设和证据缺口明确分开。'

  return (
    <ProductPage
      action={
        <Button aria-label="刷新图文工作区" onClick={() => void refresh()} size="icon-sm" variant="ghost">
          <RefreshCw className={`size-4 ${loading ? 'animate-spin' : ''}`} />
        </Button>
      }
      description="从选题、研究、草稿到审核都留在这一条内容资产里。"
      maxWidth="1180px"
      onBack={onBack}
      parentLabel="内容工厂"
      title="图文创作"
    >
      {error ? (
        <p className="mb-5 flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/6 px-4 py-3 text-xs text-red-600">
          <AlertCircle className="size-4" /> {error}
        </p>
      ) : null}

      <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_21rem]">
        <div className="rounded-[24px] border border-(--ui-stroke-tertiary) bg-(--ui-sidebar-surface-background) p-6">
          <p className="text-xs font-medium text-(--ui-accent)">当前主动作</p>
          <h2 className="mt-2 text-xl font-semibold tracking-[-0.035em]">告诉 Agent 这篇内容要解决什么问题</h2>
          <p className="mt-2 text-sm leading-6 text-(--ui-text-secondary)">
            这是内容任务的业务输入，不会被塞进新对话，也不需要再点一次发送。
          </p>
          <Textarea
            aria-label="图文创作目标"
            className="mt-5 min-h-36 resize-y"
            disabled={Boolean(activeTask && ['starting', 'waiting', 'working'].includes(activeTask.state))}
            onChange={event => setMarketingArticleDraft(accountId, event.target.value)}
            placeholder="例如：面向刚开始做知识付费的自由职业者，解释为什么先验证付费问题，而不是先做一套大课。"
            value={brief}
          />
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <span className="text-xs text-(--ui-text-tertiary)">
              点击后立即开始研究，并在这里生成可审阅的内容资产。
            </span>
            <Button
              disabled={Boolean(activeTask && ['starting', 'waiting', 'working'].includes(activeTask.state))}
              onClick={startArticle}
            >
              {activeTask && ['starting', 'waiting', 'working'].includes(activeTask.state) ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <FileText className="size-4" />
              )}
              {activeTask && ['starting', 'waiting', 'working'].includes(activeTask.state)
                ? 'Agent 正在推进'
                : '开始创作'}
            </Button>
          </div>
        </div>

        <aside className="rounded-[24px] border border-(--ui-stroke-tertiary) bg-(--ui-fill-primary)/45 p-5">
          <span className="text-[0.66rem] font-semibold tracking-[0.14em] text-(--ui-text-tertiary)">
            为什么现在这样做
          </span>
          <p className="mt-3 text-sm leading-6 text-(--ui-text-secondary)">{evidenceDetail}</p>
          {activeTask ? (
            <div className="mt-5 border-t border-(--ui-stroke-tertiary) pt-4" role="status">
              <div className="flex items-start gap-2">
                {activeTask.state === 'complete' ? (
                  <CheckCircle2 className="mt-0.5 size-4 text-emerald-600" />
                ) : activeTask.state === 'error' ? (
                  <AlertCircle className="mt-0.5 size-4 text-red-600" />
                ) : (
                  <Loader2 className="mt-0.5 size-4 animate-spin text-(--ui-accent)" />
                )}
                <div>
                  <strong className="text-xs">{activeTask.title}</strong>
                  <p className="mt-1 text-xs leading-5 text-(--ui-text-tertiary)">
                    {activeTask.error || activeTask.label}
                  </p>
                </div>
              </div>
            </div>
          ) : null}
        </aside>
      </section>

      <section className="mt-8">
        <header className="flex items-end justify-between gap-4 border-b border-(--ui-stroke-tertiary) pb-3">
          <div>
            <h2 className="text-base font-semibold">这个账号的图文资产</h2>
            <p className="mt-1 text-xs text-(--ui-text-tertiary)">任务完成后会回到这里，不会埋在聊天记录里。</p>
          </div>
          <span className="text-xs tabular-nums text-(--ui-text-tertiary)">{articles.length} 条</span>
        </header>

        {articles.length ? (
          <div className="divide-y divide-(--ui-stroke-tertiary)">
            {articles.map(asset => (
              <button
                className="group flex w-full items-center gap-4 py-4 text-left"
                key={asset.id}
                onClick={() => setSearchParams({ asset: asset.id })}
                type="button"
              >
                <FileText className="size-4 text-(--ui-text-tertiary)" />
                <span className="min-w-0 flex-1">
                  <strong className="block truncate text-sm">{asset.title || asset.topic || '未命名图文'}</strong>
                  <small className="mt-1 block text-xs text-(--ui-text-tertiary)">
                    第 {asset.version || 1} 版 · {articleStatusLabel(asset)}
                  </small>
                </span>
                <ChevronRight className="size-4 text-(--ui-text-quaternary) group-hover:text-foreground" />
              </button>
            ))}
          </div>
        ) : (
          <div className="grid min-h-44 place-items-center text-center">
            <div>
              <strong className="text-sm">还没有图文资产</strong>
              <p className="mt-2 text-xs text-(--ui-text-tertiary)">上方启动一次创作，第一份可审阅结果会出现在这里。</p>
            </div>
          </div>
        )}
      </section>

      <ContentReviewSheet
        accountId={accountId}
        asset={selectedAsset}
        onOpenChange={open => {
          if (!open) {
            setSearchParams({}, { replace: true })
          }
        }}
        onOpenDrafts={onOpenDrafts}
        onReviewed={reviewed =>
          setAssets(current => current.map(asset => (asset.id === reviewed.id ? reviewed : asset)))
        }
        onStartOperation={onStartOperation}
        requestGateway={requestGateway}
      />
    </ProductPage>
  )
}

function articleStatusLabel(asset: ContentAssetSummary): string {
  if (asset.human_review_status === 'accepted') {
    return '已确认'
  }

  if (asset.status === 'review_ready') {
    return '等待审核'
  }

  if (asset.status === 'published') {
    return '已发布'
  }

  return 'Agent 正在推进'
}
