import { useStore } from '@nanostores/react'
import { type DragEvent, type ReactNode, useCallback, useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Archive,
  AudioLines,
  CheckCircle2,
  Clock,
  FileImage,
  Globe,
  Loader2,
  MonitorPlay,
  Package,
  Pin,
  RefreshCw,
  Search,
  Upload
} from '@/lib/icons'
import { isRemoteGateway, mediaExternalUrl, mediaStreamUrl } from '@/lib/media'
import { $marketingMaterialViewState, $selectedMarketingAccountId } from '@/store/marketing'

import { ProductPage } from './business-surfaces'
import type { StartMarketingOperation } from './operations'
import { userFacingError } from './user-facing-copy'

type LibraryTab = 'cloud' | 'library' | 'temporary'
type MediaFilter = 'all' | MaterialAsset['media_type']

interface MaterialAsset {
  account_id?: string | null
  expires_at?: string | null
  id: string
  last_used_at?: string | null
  media_type: 'audio' | 'image' | 'video'
  metadata?: {
    collection_name?: string | null
    import_kind?: string
  }
  mime_type?: string
  name: string
  playback_path?: string | null
  provider?: string
  rights_status: string
  role: string
  size_bytes: number
  source_type: string
  storage_tier?: 'cloud' | 'library' | 'temporary'
  updated_at: string
}

interface MaterialLibraryViewProps {
  onStartOperation: StartMarketingOperation
  requestGateway: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
}

export function MaterialLibraryView({ onStartOperation, requestGateway }: MaterialLibraryViewProps) {
  const accountId = useStore($selectedMarketingAccountId)
  const viewState = useStore($marketingMaterialViewState)
  const tab = viewState.tab as LibraryTab
  const [assets, setAssets] = useState<MaterialAsset[]>([])
  const filter = viewState.filter as MediaFilter
  const query = viewState.query
  const [loading, setLoading] = useState(true)
  const [importing, setImporting] = useState(false)
  const [promotingId, setPromotingId] = useState('')
  const [rightsConfirmed, setRightsConfirmed] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const setTab = (value: LibraryTab) =>
    $marketingMaterialViewState.set({ ...$marketingMaterialViewState.get(), tab: value })

  const setFilter = (value: MediaFilter) =>
    $marketingMaterialViewState.set({ ...$marketingMaterialViewState.get(), filter: value })

  const setQuery = (value: string) =>
    $marketingMaterialViewState.set({ ...$marketingMaterialViewState.get(), query: value })

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')

    try {
      const result = await requestGateway<{ assets: MaterialAsset[] }>('marketing.assets.list', {
        account_id: accountId && !accountId.startsWith('prospect_') ? accountId : undefined
      })

      setAssets(result.assets || [])
    } catch (cause) {
      setAssets([])
      setError(userFacingError(cause, '素材库读取失败，请稍后重试。'))
    } finally {
      setLoading(false)
    }
  }, [accountId, requestGateway])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const importPaths = async (paths: string[]) => {
    const unique = [...new Set(paths.map(path => path.trim()).filter(Boolean))]

    if (!unique.length) {
      return
    }

    if (!rightsConfirmed) {
      setError('请先确认你拥有这些素材的使用权。')

      return
    }

    setImporting(true)
    setError('')
    setNotice('')

    try {
      const result = await requestGateway<{ imported: number; reused: number; skipped: unknown[] }>(
        'marketing.assets.import_paths',
        {
          account_id: accountId && !accountId.startsWith('prospect_') ? accountId : undefined,
          paths: unique,
          rights_confirmed: true
        }
      )

      const skipped = result.skipped || []

      setNotice(
        `已入库 ${result.imported} 项，复用 ${result.reused} 项${skipped.length ? `，跳过 ${skipped.length} 项` : ''}。`
      )
      setTab('library')
      setRightsConfirmed(false)
      await refresh()
    } catch (cause) {
      setError(userFacingError(cause, '素材导入失败，请稍后重试。'))
    } finally {
      setImporting(false)
    }
  }

  const pickPaths = async (directories: boolean) => {
    const selected = await window.hermesDesktop?.selectPaths({
      directories,
      multiple: !directories,
      title: directories ? '导入素材文件夹' : '导入图片、视频或音频'
    })

    await importPaths(selected || [])
  }

  const handleDrop = async (event: DragEvent<HTMLElement>) => {
    event.preventDefault()

    const paths = Array.from(event.dataTransfer.files)
      .map(file => window.hermesDesktop?.getPathForFile?.(file) || '')
      .filter(Boolean)

    await importPaths(paths)
  }

  const promote = async (asset: MaterialAsset) => {
    setPromotingId(asset.id)
    setError('')

    try {
      await requestGateway('marketing.assets.promote', {
        account_id: accountId && !accountId.startsWith('prospect_') ? accountId : undefined,
        asset_id: asset.id,
        target_tier: 'library'
      })
      setNotice(`“${asset.name}”已保留到本地素材库。`)
      await refresh()
    } catch (cause) {
      setError(userFacingError(cause, '素材保留失败，请稍后重试。'))
    } finally {
      setPromotingId('')
    }
  }

  const temporaryAssets = assets.filter(asset => assetTier(asset) === 'temporary')
  const libraryAssets = assets.filter(asset => assetTier(asset) === 'library')

  const visibleAssets = (tab === 'temporary' ? temporaryAssets : libraryAssets).filter(asset => {
    const matchesType = filter === 'all' || asset.media_type === filter
    const needle = query.trim().toLowerCase()

    return matchesType && (!needle || `${asset.name} ${asset.role}`.toLowerCase().includes(needle))
  })

  return (
    <ProductPage action={null} maxWidth="1640px" title="素材中枢">
      {error ? (
        <p className="mt-4 rounded-2xl border border-red-500/18 bg-red-500/6 px-4 py-3 text-xs text-red-600">{error}</p>
      ) : null}
      {notice ? (
        <p className="mt-4 rounded-2xl border border-emerald-500/18 bg-emerald-500/6 px-4 py-3 text-xs text-emerald-700">
          {notice}
        </p>
      ) : null}

      <section className="mt-5">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-(--ui-stroke-tertiary) px-5 py-4 sm:px-6">
          <div className="flex items-center gap-1 rounded-full bg-(--ui-fill-secondary) p-1">
            <LibraryTabButton
              active={tab === 'temporary'}
              count={temporaryAssets.length}
              icon={<Clock className="size-3.5" />}
              label="临时区"
              onClick={() => setTab('temporary')}
            />
            <LibraryTabButton
              active={tab === 'library'}
              count={libraryAssets.length}
              icon={<Archive className="size-3.5" />}
              label="本地库"
              onClick={() => setTab('library')}
            />
            <LibraryTabButton
              active={tab === 'cloud'}
              icon={<Globe className="size-3.5" />}
              label="云端素材"
              onClick={() => setTab('cloud')}
            />
          </div>
          <div className="flex items-center gap-2">
            <label className="flex h-9 items-center gap-2 rounded-full border border-(--ui-stroke-tertiary) bg-(--ui-background) px-3 text-(--ui-text-tertiary)">
              <Search className="size-3.5" />
              <input
                className="w-28 bg-transparent text-xs text-foreground outline-none placeholder:text-(--ui-text-quaternary)"
                onChange={event => setQuery(event.target.value)}
                placeholder="搜索素材"
                value={query}
              />
            </label>
            <button
              aria-label="刷新素材库"
              className="grid size-9 place-items-center rounded-full border border-(--ui-stroke-tertiary) hover:bg-(--ui-fill-secondary)"
              onClick={() => void refresh()}
              type="button"
            >
              <RefreshCw className={`size-3.5 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </header>

        {tab === 'cloud' ? (
          <CloudEmpty accountId={accountId || 'prospect_default'} onStartOperation={onStartOperation} />
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 px-6 pt-5">
              <div className="flex gap-1.5">
                {(['all', 'video', 'image', 'audio'] as MediaFilter[]).map(item => (
                  <button
                    className={`rounded-full px-3 py-1.5 text-[0.66rem] font-medium transition-colors duration-[var(--mos-motion-fast)] ${filter === item ? 'bg-(--ui-row-active-background) text-foreground shadow-xs' : 'text-(--ui-text-tertiary) hover:bg-(--ui-row-hover-background) hover:text-foreground'}`}
                    key={item}
                    onClick={() => setFilter(item)}
                    type="button"
                  >
                    {filterLabel(item)}
                  </button>
                ))}
              </div>
              <p className="text-[0.66rem] text-(--ui-text-quaternary)">
                {tab === 'temporary' ? '未使用的素材 7 天后自动清理' : '保留在这里，之后可以继续使用'}
              </p>
            </div>
            {tab === 'library' ? (
              <div className="grid gap-4 p-6 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
                <ImportMaterialCard
                  importing={importing}
                  onDrop={handleDrop}
                  onPickFiles={() => void pickPaths(false)}
                  onPickFolder={() => void pickPaths(true)}
                  onRightsConfirmed={setRightsConfirmed}
                  rightsConfirmed={rightsConfirmed}
                />
                {visibleAssets.map((asset, index) => (
                  <MaterialCard
                    asset={asset}
                    index={index}
                    key={asset.id}
                    onPromote={() => void promote(asset)}
                    promoting={promotingId === asset.id}
                  />
                ))}
              </div>
            ) : visibleAssets.length ? (
              <div className="grid gap-4 p-6 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
                {visibleAssets.map((asset, index) => (
                  <MaterialCard
                    asset={asset}
                    index={index}
                    key={asset.id}
                    onPromote={() => void promote(asset)}
                    promoting={promotingId === asset.id}
                  />
                ))}
              </div>
            ) : !loading ? (
              <AssetEmpty temporary={tab === 'temporary'} />
            ) : null}
          </>
        )}
      </section>
    </ProductPage>
  )
}

function LibraryTabButton({
  active,
  count,
  icon,
  label,
  onClick
}: {
  active: boolean
  count?: number
  icon: ReactNode
  label: string
  onClick: () => void
}) {
  return (
    <button
      className={`flex items-center gap-1.5 rounded-full px-3.5 py-2 text-[0.7rem] font-medium transition ${active ? 'bg-(--ui-sidebar-surface-background) text-foreground shadow-sm' : 'text-(--ui-text-tertiary)'}`}
      onClick={onClick}
      type="button"
    >
      {icon}
      {label}
      {typeof count === 'number' ? <span className="ml-0.5 text-[0.58rem] opacity-50">{count}</span> : null}
    </button>
  )
}

function ImportMaterialCard({
  importing,
  onDrop,
  onPickFiles,
  onPickFolder,
  onRightsConfirmed,
  rightsConfirmed
}: {
  importing: boolean
  onDrop: (event: DragEvent<HTMLElement>) => void
  onPickFiles: () => void
  onPickFolder: () => void
  onRightsConfirmed: (confirmed: boolean) => void
  rightsConfirmed: boolean
}) {
  return (
    <article
      aria-label="导入素材"
      className="grid min-h-72 place-items-center rounded-[18px] border border-dashed border-(--ui-stroke-secondary) bg-(--ui-fill-secondary) p-5 text-center transition-colors duration-[var(--mos-motion-standard)] hover:border-(--ui-stroke-primary) hover:bg-(--ui-bg-tertiary)"
      onDragOver={event => event.preventDefault()}
      onDrop={event => void onDrop(event)}
    >
      <div>
        <span className="mx-auto grid size-11 place-items-center rounded-full bg-(--ui-background) text-(--ui-accent) shadow-sm">
          {importing ? <Loader2 className="size-5 animate-spin" /> : <Upload className="size-5" />}
        </span>
        <strong className="mt-3 block text-sm">导入素材</strong>
        <p className="mt-1.5 text-[0.64rem] text-(--ui-text-tertiary)">拖入文件或文件夹</p>
        <label className="mt-4 flex cursor-pointer items-start justify-center gap-2 text-left text-[0.6rem] leading-4 text-(--ui-text-tertiary)">
          <input
            checked={rightsConfirmed}
            className="mt-0.5 accent-(--ui-accent)"
            onChange={event => onRightsConfirmed(event.target.checked)}
            type="checkbox"
          />
          <span>我确认拥有这些素材的使用权或必要授权</span>
        </label>
        <div className="mt-4 flex justify-center gap-2">
          <button
            className="rounded-full bg-(--ui-text-primary) px-3 py-2 text-[0.64rem] font-semibold text-(--ui-background) transition-opacity disabled:opacity-30"
            disabled={importing || !rightsConfirmed}
            onClick={onPickFiles}
            type="button"
          >
            选择文件
          </button>
          <button
            className="rounded-full border border-(--ui-stroke-tertiary) bg-(--ui-background) px-3 py-2 text-[0.64rem] font-semibold disabled:opacity-30"
            disabled={importing || !rightsConfirmed}
            onClick={onPickFolder}
            type="button"
          >
            文件夹
          </button>
        </div>
      </div>
    </article>
  )
}

function MaterialCard({
  asset,
  index,
  onPromote,
  promoting
}: {
  asset: MaterialAsset
  index: number
  onPromote: () => void
  promoting: boolean
}) {
  const Icon = asset.media_type === 'audio' ? AudioLines : asset.media_type === 'video' ? MonitorPlay : FileImage

  const source = asset.playback_path
    ? isRemoteGateway()
      ? mediaExternalUrl(asset.playback_path)
      : mediaStreamUrl(asset.playback_path)
    : ''

  const temporary = assetTier(asset) === 'temporary'

  return (
    <article className="group overflow-hidden rounded-[18px] border border-(--ui-stroke-tertiary) bg-(--ui-background) transition-[border-color,box-shadow] duration-[var(--mos-motion-standard)] hover:border-(--ui-stroke-secondary) hover:shadow-sm">
      <div className="relative grid aspect-[4/3] place-items-center overflow-hidden bg-(--ui-bg-tertiary)">
        {source && asset.media_type === 'image' ? (
          <img
            alt={asset.name}
            className="size-full object-cover transition duration-500 group-hover:scale-[1.03]"
            src={source}
          />
        ) : null}
        {source && asset.media_type === 'video' ? (
          <video className="size-full object-cover" muted preload="metadata" src={source} />
        ) : null}
        {asset.media_type === 'audio' || !source ? <Icon className="size-9 text-(--ui-text-quaternary)" /> : null}
        <span className="absolute left-3 top-3 rounded-full bg-black/50 px-2.5 py-1 text-[0.58rem] font-medium tabular-nums text-white backdrop-blur">
          #{String(index + 1).padStart(2, '0')}
        </span>
        {temporary ? (
          <span className="absolute right-3 top-3 flex items-center gap-1 rounded-full bg-(--ui-accent) px-2.5 py-1 text-[0.58rem] font-semibold text-white">
            <Clock className="size-3" /> {expiryLabel(asset.expires_at)}
          </span>
        ) : null}
      </div>
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <span className="min-w-0">
            <strong className="block truncate text-sm">{asset.name}</strong>
            <small className="mt-1 block truncate text-[0.63rem] text-(--ui-text-tertiary)">
              {asset.metadata?.collection_name || sourceLabel(asset.source_type)} · {rightsLabel(asset.rights_status)}
            </small>
          </span>
          {temporary ? (
            <button
              aria-label={`保留 ${asset.name}`}
              className="grid size-8 shrink-0 place-items-center rounded-full border border-(--ui-stroke-tertiary) text-(--ui-text-tertiary) transition-colors duration-[var(--mos-motion-fast)] hover:border-(--ui-stroke-primary) hover:bg-(--ui-bg-tertiary) hover:text-(--ui-accent)"
              disabled={promoting}
              onClick={onPromote}
              type="button"
            >
              {promoting ? <Loader2 className="size-3.5 animate-spin" /> : <Pin className="size-3.5" />}
            </button>
          ) : (
            <CheckCircle2 className="size-4 shrink-0 text-emerald-600" />
          )}
        </div>
        <div className="mt-4 flex items-center justify-between border-t border-(--ui-stroke-tertiary) pt-3 text-[0.6rem] text-(--ui-text-quaternary)">
          <span>
            {mediaTypeLabel(asset.media_type)} · {formatBytes(asset.size_bytes)}
          </span>
          <span>{asset.account_id ? '账号素材' : '全局复用'}</span>
        </div>
      </div>
    </article>
  )
}

function CloudEmpty({ accountId, onStartOperation }: { accountId: string; onStartOperation: StartMarketingOperation }) {
  return (
    <div className="grid min-h-[30rem] place-items-center p-8 text-center">
      <div className="max-w-xl">
        <h2 className="text-lg font-semibold tracking-[-0.03em]">云端素材即将开放</h2>
        <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-(--ui-text-tertiary)">
          开放后，你可以在桌面、飞书或微信中把常用素材保存到云端。
        </p>
        <Button
          className="mt-6 rounded-full"
          onClick={() => onStartOperation({ accountId, kind: 'materials.cloud.status' })}
          variant="outline"
        >
          查看接入状态
        </Button>
      </div>
    </div>
  )
}

function AssetEmpty({ temporary }: { temporary: boolean }) {
  return (
    <div className="grid min-h-72 place-items-center p-8 text-center">
      <div className="max-w-sm">
        <span className="mx-auto grid size-12 place-items-center rounded-full bg-(--ui-fill-secondary) text-(--ui-text-tertiary)">
          {temporary ? <Clock className="size-5" /> : <Package className="size-5" />}
        </span>
        <strong className="mt-4 block text-sm">{temporary ? '临时区很干净' : '正式素材库还是空的'}</strong>
        <p className="mt-2 text-xs leading-5 text-(--ui-text-tertiary)">
          {temporary
            ? '从网上找到并下载的素材会先出现在这里，默认保留 7 天。'
            : '导入本地文件，或把临时素材固定下来，之后就能跨项目复用。'}
        </p>
      </div>
    </div>
  )
}

function assetTier(asset: MaterialAsset): 'cloud' | 'library' | 'temporary' {
  return asset.storage_tier || 'library'
}

function expiryLabel(value?: string | null): string {
  if (!value) {
    return '7 天'
  }

  const remaining = new Date(value).getTime() - Date.now()
  const hours = Math.max(0, Math.ceil(remaining / 3_600_000))

  return hours > 48 ? `${Math.ceil(hours / 24)} 天` : `${hours} 小时`
}

function filterLabel(filter: MediaFilter): string {
  return { all: '全部', audio: '音频', image: '图片', video: '视频' }[filter]
}

function sourceLabel(source: string): string {
  return (
    {
      ai_generated: 'AI 生成',
      derived: '成片派生',
      licensed_provider: '授权素材商',
      user_upload: '本地导入',
      volcengine_trusted: '火山可信资产'
    }[source] || source
  )
}

function rightsLabel(status: string): string {
  return (
    {
      generated: '生成授权',
      inherited: '继承授权',
      licensed: '已许可',
      provider_verified: '平台验证',
      user_confirmed: '用户确认'
    }[status] || '待确认'
  )
}

function mediaTypeLabel(type: MaterialAsset['media_type']): string {
  return { audio: '音频', image: '图片', video: '视频' }[type]
}

function formatBytes(value: number): string {
  if (value >= 1024 * 1024 * 1024) {
    return `${(value / 1024 / 1024 / 1024).toFixed(1)} GB`
  }

  if (value >= 1024 * 1024) {
    return `${(value / 1024 / 1024).toFixed(1)} MB`
  }

  if (value >= 1024) {
    return `${(value / 1024).toFixed(0)} KB`
  }

  return `${value || 0} B`
}
