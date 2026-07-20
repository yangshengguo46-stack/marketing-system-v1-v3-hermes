import { useStore } from '@nanostores/react'
import { type DragEvent, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { ContextMenu } from '@/app/chat/composer/context-menu'
import { PRIMARY_ICON_BTN } from '@/app/chat/composer/controls'
import type { ChatBarState } from '@/app/chat/composer/types'
import { titlebarButtonClass } from '@/app/shell/titlebar'
import {
  composerFill,
  composerSurfaceContent,
  composerSurfaceFrame,
  composerSurfaceGlass
} from '@/components/chat/composer-dock'
import { Button } from '@/components/ui/button'
import { Codicon } from '@/components/ui/codicon'
import {
  AlertCircle,
  AudioLines,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock,
  Download,
  FileImage,
  FileText,
  Layers3,
  Loader2,
  Mic,
  MonitorPlay,
  Package,
  Play,
  Plus,
  RefreshCw,
  Trash2,
  Users,
  Volume2,
  X,
  Zap
} from '@/lib/icons'
import { gatewayMediaDataUrl, isRemoteGateway, mediaExternalUrl, mediaStreamUrl } from '@/lib/media'
import { readKey, writeKey } from '@/lib/storage'
import { cn } from '@/lib/utils'
import { $marketingOperationTasks, type MarketingOperationTask } from '@/store/marketing'

import type { MarketingOperationIntent, StartMarketingOperation } from './operations'
import { userFacingError } from './user-facing-copy'

interface CanvasSpec {
  fps: number
  height: number
  width: number
}

type DirectorLayout = 'compact' | 'stacked' | 'wide'

export interface VideoProductionSummary {
  canvas: CanvasSpec
  created_at: string
  duration: number
  failure_code?: string | null
  final_video_asset_id?: string | null
  human_review_status: string
  id: string
  output_asset_id?: string | null
  renderers: string[]
  readiness?: VideoRenderReadiness
  scene_count: number
  settled_at?: string | null
  source_asset_id: string
  status: string
  title: string
  updated_at: string
}

interface VideoTextLayer {
  role?: string
  text?: string
}

interface VideoVisual {
  fit?: string
  media_asset_id?: string
  source_in?: number
}

interface VideoScene {
  duration: number
  id: string
  motion_intent?: string[]
  purpose?: string
  review_rules?: string[]
  text?: VideoTextLayer[]
  visuals?: VideoVisual[]
}

interface VideoProductionDetail {
  approval_ref?: string | null
  failure_code?: string | null
  final_video_asset_id?: string | null
  id: string
  output_asset_id?: string | null
  receipt?: {
    summary?: {
      technical?: {
        quality_assurance?: VideoQualityReport
      }
    }
  }
  render_plan?: {
    executable?: boolean
    render_plan_sha256?: string
    scenes?: Array<{
      fallback_used?: boolean
      reason?: string
      renderer?: string
      scene_id?: string
      status?: string
    }>
  }
  status: string
  video_ir?: {
    audio?: Record<string, unknown>
    canvas?: CanvasSpec
    captions?: Array<Record<string, unknown>>
    ir_sha256?: string
    review_rules?: string[]
    scenes?: VideoScene[]
  }
}

interface VideoQualityCheck {
  evidence?: Record<string, unknown>
  id: string
  label: string
  severity: 'critical' | 'major' | 'observation'
  status: 'fail' | 'not_applicable' | 'pass'
}

interface VideoQualityReport {
  analyzed_at?: string
  checks: VideoQualityCheck[]
  disposition: 'hold' | 'ready' | 'reject'
  version: string
}

interface MediaAssetProjection {
  id: string
  media_type: 'audio' | 'image' | 'video'
  mime_type?: string
  name: string
  playback_path?: string | null
  provider?: string
  rights_status: string
  role: string
  size_bytes: number
  source_type: string
}

interface VideoRenderReadiness {
  blockers?: Array<{
    code?: string
    count?: number
    message?: string
    scene_ids?: string[]
  }>
  placeholder_scene_count?: number
  ready?: boolean
  status?: string
  voice_required?: boolean
}

interface VoiceJobProjection {
  id: string
  status: string
}

interface AudioCatalogVoice {
  display?: string
  entitlement?: string
  gender?: string
  id: string
  language?: string
  scenario?: string
  verified?: boolean
}

interface AudioCatalogProjection {
  available: boolean
  configured_voice?: string
  default_model?: string
  display_name?: string
  metadata?: {
    catalog_scope?: string
    features?: string[]
    full_catalog_sync?: { available?: boolean; reason?: string; requires?: string[] }
    official_voice_count?: number
    service_families?: Array<{ active?: boolean; id: string; name: string }>
  }
  models?: Array<{ display?: string; id: string; languages?: string[] }>
  provider?: string
  voices?: AudioCatalogVoice[]
}

interface ContentAssetProjection {
  human_review_status?: string
  id: string
  title?: string
  version?: number
}

interface VideoReviewProjection {
  material_searches?: never[]
  media_assets: MediaAssetProjection[]
  output_asset?: ContentAssetProjection | null
  production: VideoProductionDetail
  source_asset: ContentAssetProjection
  summary: VideoProductionSummary
  readiness?: VideoRenderReadiness
  voice_job?: VoiceJobProjection | null
}

interface VideoProductionWorkbenchProps {
  accountId: string
  initialProductionId?: string
  onBack?: () => void
  onOpenDrafts?: () => void
  onStartOperation: StartMarketingOperation
  requestGateway: <T>(method: string, params?: Record<string, unknown>) => Promise<T>
}

type DirectorStage = 'dynamic' | 'edit' | 'final' | 'setup' | 'storyboard'
type InspectorTab = 'characters' | 'materials' | 'props' | 'scenes' | 'sound'
type SetupCategory = 'characters' | 'props' | 'scenes' | 'sound'
type StartVideoOperation = (intent: Omit<MarketingOperationIntent, 'accountId'>) => string

export interface VideoSetupDraft {
  documents: string[]
  script: string
  selections: Record<SetupCategory, string>
}

interface VideoWorkspaceViewState {
  inspectorRailHidden: boolean
  inspectorRailFormatVersion: number
  inspectorTab: InspectorTab
  sceneRailCollapsed: boolean
  selectedId: string
  selectedSceneId: string
  setupRailCollapsed: boolean
}

const DIRECTOR_STAGES: Array<{ id: DirectorStage; label: string }> = [
  { id: 'setup', label: '设定' },
  { id: 'storyboard', label: '分镜' },
  { id: 'dynamic', label: '动态' },
  { id: 'edit', label: '剪辑' },
  { id: 'final', label: '成片' }
]

const COMMON_RATIOS = [
  { height: 16, label: '9:16', width: 9 },
  { height: 9, label: '16:9', width: 16 },
  { height: 1, label: '1:1', width: 1 },
  { height: 5, label: '4:5', width: 4 },
  { height: 4, label: '3:4', width: 3 }
]

const VIDEO_REFERENCE_CATEGORIES: Array<{ id: SetupCategory; icon: typeof Users; label: string }> = [
  { id: 'characters', icon: Users, label: '人物' },
  { id: 'sound', icon: AudioLines, label: '声音' },
  { id: 'scenes', icon: Layers3, label: '场景' },
  { id: 'props', icon: Package, label: '道具' }
]

const VIDEO_COMPOSER_MENU_STATE: ChatBarState = {
  model: { canSwitch: false, model: '', provider: '' },
  tools: { enabled: true, label: '添加素材' },
  voice: { active: false, enabled: false }
}

const VIDEO_SETUP_DRAFT_PREFIX = 'marketing-os.desktop.video-setup-draft.v1'
const VIDEO_WORKSPACE_VIEW_PREFIX = 'marketing-os.desktop.video-workspace-view.v1'

function emptySetupSelections(): Record<SetupCategory, string> {
  return { characters: '', props: '', scenes: '', sound: '' }
}

export function videoSetupDraftKey(accountId: string): string {
  return `${VIDEO_SETUP_DRAFT_PREFIX}:${accountId || 'prospect_default'}`
}

export function readVideoSetupDraft(accountId: string): VideoSetupDraft {
  const emptyDraft = { documents: [], script: '', selections: emptySetupSelections() }

  try {
    const raw = readKey(videoSetupDraftKey(accountId))

    if (!raw) {
      return emptyDraft
    }

    const parsed = JSON.parse(raw) as Partial<VideoSetupDraft>

    const selections: Partial<Record<SetupCategory, string>> =
      parsed.selections && typeof parsed.selections === 'object' ? parsed.selections : {}

    return {
      documents: Array.isArray(parsed.documents) ? parsed.documents.filter(item => typeof item === 'string') : [],
      script: typeof parsed.script === 'string' ? parsed.script : '',
      selections: {
        characters: typeof selections.characters === 'string' ? selections.characters : '',
        props: typeof selections.props === 'string' ? selections.props : '',
        scenes: typeof selections.scenes === 'string' ? selections.scenes : '',
        sound: typeof selections.sound === 'string' ? selections.sound : ''
      }
    }
  } catch {
    return emptyDraft
  }
}

export function writeVideoSetupDraft(accountId: string, draft: VideoSetupDraft): void {
  writeKey(videoSetupDraftKey(accountId), JSON.stringify(draft))
}

export function clearVideoSetupDraft(accountId: string): void {
  writeKey(videoSetupDraftKey(accountId), null)
}

function videoWorkspaceViewKey(accountId: string): string {
  return `${VIDEO_WORKSPACE_VIEW_PREFIX}:${accountId || 'prospect_default'}`
}

function readVideoWorkspaceView(accountId: string): VideoWorkspaceViewState {
  const fallback: VideoWorkspaceViewState = {
    inspectorRailFormatVersion: 3,
    inspectorRailHidden: false,
    inspectorTab: 'materials',
    sceneRailCollapsed: false,
    selectedId: '',
    selectedSceneId: '',
    setupRailCollapsed: false
  }

  try {
    const raw = readKey(videoWorkspaceViewKey(accountId))
    const value = raw ? (JSON.parse(raw) as Partial<VideoWorkspaceViewState>) : {}
    const tabs: InspectorTab[] = ['characters', 'materials', 'props', 'scenes', 'sound']

    return {
      inspectorRailHidden:
        value.inspectorRailFormatVersion === fallback.inspectorRailFormatVersion
          ? value.inspectorRailHidden === true
          : fallback.inspectorRailHidden,
      inspectorRailFormatVersion: fallback.inspectorRailFormatVersion,
      inspectorTab: tabs.includes(value.inspectorTab as InspectorTab)
        ? (value.inspectorTab as InspectorTab)
        : fallback.inspectorTab,
      sceneRailCollapsed: value.sceneRailCollapsed === true,
      selectedId: typeof value.selectedId === 'string' ? value.selectedId : '',
      selectedSceneId: typeof value.selectedSceneId === 'string' ? value.selectedSceneId : '',
      setupRailCollapsed: value.setupRailCollapsed === true
    }
  } catch {
    return fallback
  }
}

export function VideoProductionWorkbench({
  accountId,
  initialProductionId,
  onBack,
  onOpenDrafts,
  onStartOperation,
  requestGateway
}: VideoProductionWorkbenchProps) {
  const initialView = useMemo(() => readVideoWorkspaceView(accountId), [accountId])
  const operationTasks = useStore($marketingOperationTasks)
  const [productions, setProductions] = useState<VideoProductionSummary[]>([])
  const [selectedId, setSelectedId] = useState(initialProductionId || initialView.selectedId)
  const [detail, setDetail] = useState<VideoReviewProjection | null>(null)
  const [selectedSceneId, setSelectedSceneId] = useState(initialView.selectedSceneId)
  const [loadingList, setLoadingList] = useState(false)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [detailRefreshToken, setDetailRefreshToken] = useState(0)
  const [error, setError] = useState('')
  const [reviewNote, setReviewNote] = useState('')
  const [reviewing, setReviewing] = useState<'accepted' | 'changes_requested' | null>(null)
  const [activeStage, setActiveStage] = useState<DirectorStage>('setup')
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>(initialView.inspectorTab)
  const [setupCategory, setSetupCategory] = useState<SetupCategory | null>(null)
  const [setupAssets, setSetupAssets] = useState<MediaAssetProjection[]>([])
  const [sceneRailCollapsed, setSceneRailCollapsed] = useState(initialView.sceneRailCollapsed)
  const [inspectorRailHidden, setInspectorRailHidden] = useState(initialView.inspectorRailHidden)
  const [inspectorPanelOpen, setInspectorPanelOpen] = useState(false)
  const [setupRailCollapsed, setSetupRailCollapsed] = useState(initialView.setupRailCollapsed)
  const [operationTaskId, setOperationTaskId] = useState('')
  const [audioCatalog, setAudioCatalog] = useState<AudioCatalogProjection | null>(null)
  const [selectingVoiceId, setSelectingVoiceId] = useState('')

  const operationProgress =
    operationTasks.find(task => task.id === operationTaskId) ||
    operationTasks.find(task => task.accountId === accountId && task.kind.startsWith('video.')) ||
    null

  const settledSetupTaskId = useRef('')
  const directorShellRef = useRef<HTMLElement | null>(null)
  const [directorLayout, setDirectorLayout] = useState<DirectorLayout>('wide')

  const [setupSelections, setSetupSelections] = useState<Record<SetupCategory, string>>(
    () => readVideoSetupDraft(accountId).selections
  )

  const [setupScript, setSetupScript] = useState(() => readVideoSetupDraft(accountId).script)
  const [setupDocuments, setSetupDocuments] = useState<string[]>(() => readVideoSetupDraft(accountId).documents)
  const [setupSubmitting, setSetupSubmitting] = useState(false)
  const [setupStatus, setSetupStatus] = useState('')
  const [setupError, setSetupError] = useState('')
  const setupOperation = operationProgress?.kind === 'video.setup' ? operationProgress : null

  const setupRunning = Boolean(
    setupSubmitting || (setupOperation && ['starting', 'waiting', 'working'].includes(setupOperation.state))
  )

  const refresh = useCallback(async (): Promise<VideoProductionSummary[]> => {
    if (!accountId) {
      setProductions([])
      setSelectedId('')
      setDetail(null)

      return []
    }

    setLoadingList(true)
    setError('')

    try {
      const result = await requestGateway<{ productions: VideoProductionSummary[] }>(
        'marketing.video.productions.list',
        { account_id: accountId, limit: 30 }
      )

      const next = result.productions || []
      setProductions(next)
      setSelectedId(current => (next.some(item => item.id === current) ? current : next[0]?.id || ''))

      return next
    } catch (cause) {
      setProductions([])
      setSelectedId('')
      setDetail(null)
      setError(userFacingError(cause, '视频项目读取失败，请稍后重试。'))

      return []
    } finally {
      setLoadingList(false)
    }
  }, [accountId, requestGateway])

  const startOperation = useCallback<StartVideoOperation>(
    intent => {
      const scopedIntent = { ...intent, accountId: accountId || 'prospect_default' }
      const taskId = onStartOperation(scopedIntent)

      setOperationTaskId(taskId)

      if (['video.revision', 'video.stage.modify'].includes(intent.kind)) {
        setReviewNote('')
      }

      return taskId
    },
    [accountId, onStartOperation]
  )

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    let cancelled = false

    void requestGateway<AudioCatalogProjection>('marketing.audio.catalog')
      .then(result => {
        if (!cancelled) {
          setAudioCatalog(result)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAudioCatalog(null)
        }
      })

    return () => {
      cancelled = true
    }
  }, [requestGateway])

  useEffect(() => {
    const shell = directorShellRef.current

    if (!shell) {
      return
    }

    const updateLayout = () => setDirectorLayout(directorLayoutForWidth(shell.clientWidth))

    updateLayout()

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', updateLayout)

      return () => window.removeEventListener('resize', updateLayout)
    }

    const observer = new ResizeObserver(updateLayout)
    observer.observe(shell)

    return () => observer.disconnect()
  }, [productions.length])

  useEffect(() => {
    if (initialProductionId && productions.some(item => item.id === initialProductionId)) {
      setSelectedId(initialProductionId)
    }
  }, [initialProductionId, productions])

  useEffect(() => {
    writeVideoSetupDraft(accountId, {
      documents: setupDocuments,
      script: setupScript,
      selections: setupSelections
    })
  }, [accountId, setupDocuments, setupScript, setupSelections])

  useEffect(() => {
    writeKey(
      videoWorkspaceViewKey(accountId),
      JSON.stringify({
        inspectorRailFormatVersion: 3,
        inspectorRailHidden,
        inspectorTab,
        sceneRailCollapsed,
        selectedId,
        selectedSceneId,
        setupRailCollapsed
      } satisfies VideoWorkspaceViewState)
    )
  }, [
    accountId,
    inspectorRailHidden,
    inspectorTab,
    sceneRailCollapsed,
    selectedId,
    selectedSceneId,
    setupRailCollapsed
  ])

  useEffect(() => {
    if (operationProgress?.state !== 'complete') {
      return
    }

    setDetailRefreshToken(current => current + 1)
    void refresh().then(next => {
      if (setupSubmitting && operationProgress.kind === 'video.setup' && !next.length) {
        setSetupSubmitting(false)
        setSetupStatus('')
        setSetupError('Agent 已结束，但没有形成可见的视频项目；当前输入已保留，可以重新启动。')
      }
    })
  }, [operationProgress?.kind, operationProgress?.state, refresh, setupSubmitting])

  useEffect(() => {
    if (productions.length) {
      return
    }

    let cancelled = false
    void requestGateway<{ assets: MediaAssetProjection[] }>('marketing.assets.list', {
      account_id: accountId && !accountId.startsWith('prospect_') ? accountId : undefined
    })
      .then(result => {
        if (!cancelled) {
          setSetupAssets(result.assets || [])
        }
      })
      .catch(cause => {
        if (!cancelled) {
          setSetupError(userFacingError(cause, '素材读取失败，请稍后重试。'))
        }
      })

    return () => {
      cancelled = true
    }
  }, [accountId, productions.length, requestGateway])

  useEffect(() => {
    if (!setupRunning || !accountId) {
      return
    }

    const timer = window.setInterval(() => void refresh(), 2500)

    return () => window.clearInterval(timer)
  }, [accountId, refresh, setupRunning])

  useEffect(() => {
    if (setupOperation?.state !== 'error') {
      return
    }

    setSetupSubmitting(false)
    setSetupStatus('')
    setSetupError(setupOperation.error || '视频任务执行失败，当前输入和素材选择已经保留。')
  }, [setupOperation?.error, setupOperation?.state])

  useEffect(() => {
    if (
      productions.length &&
      setupOperation?.state === 'complete' &&
      settledSetupTaskId.current !== setupOperation.id
    ) {
      settledSetupTaskId.current = setupOperation.id
      setSetupSubmitting(false)
      setSetupStatus('拆分完成，已进入导演工作台。')
      clearVideoSetupDraft(accountId)
      setSetupDocuments([])
      setSetupScript('')
      setSetupSelections(emptySetupSelections())
    }
  }, [accountId, productions.length, setupOperation?.id, setupOperation?.state])

  useEffect(() => {
    if (!selectedId || !accountId) {
      setDetail(null)

      return
    }

    let cancelled = false
    setLoadingDetail(true)
    setError('')
    void requestGateway<VideoReviewProjection>('marketing.video.production.get', {
      account_id: accountId,
      production_id: selectedId
    })
      .then(result => {
        if (cancelled) {
          return
        }

        setDetail(result)
        setSelectedSceneId(current => {
          const scenes = result.production.video_ir?.scenes || []

          return scenes.some(scene => scene.id === current) ? current : scenes[0]?.id || ''
        })
        setActiveStage(inferDirectorStage(result.summary.status, result.summary.human_review_status))
        setReviewNote('')
      })
      .catch(cause => {
        if (!cancelled) {
          setDetail(null)
          setError(userFacingError(cause, '视频项目读取失败，请稍后重试。'))
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingDetail(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [accountId, detailRefreshToken, requestGateway, selectedId])

  const submitReview = async (decision: 'accepted' | 'changes_requested') => {
    if (!detail?.output_asset?.id || (decision === 'changes_requested' && !reviewNote.trim())) {
      return
    }

    setReviewing(decision)
    setError('')

    try {
      const result = await requestGateway<{ asset: ContentAssetProjection }>('marketing.content.asset.review', {
        account_id: accountId,
        asset_id: detail.output_asset.id,
        confirmed: true,
        decision,
        note: reviewNote.trim()
      })

      setDetail(current =>
        current
          ? {
              ...current,
              output_asset: result.asset,
              summary: { ...current.summary, human_review_status: decision }
            }
          : current
      )
      setProductions(current =>
        current.map(item => (item.id === selectedId ? { ...item, human_review_status: decision } : item))
      )

      if (decision === 'changes_requested') {
        startOperation({
          assetId: detail.output_asset.id,
          kind: 'video.revision',
          note: reviewNote.trim(),
          productionId: detail.production.id,
          title: detail.summary.title
        })
      }
    } catch (cause) {
      setError(userFacingError(cause, '保存审片结果失败，请稍后重试。'))
    } finally {
      setReviewing(null)
    }
  }

  const selectDefaultVoice = async (voiceId: string) => {
    if (!voiceId || selectingVoiceId) {
      return
    }

    setSelectingVoiceId(voiceId)
    setError('')

    try {
      const result = await requestGateway<AudioCatalogProjection>('marketing.audio.voice.set', {
        confirmed: true,
        voice_id: voiceId
      })

      setAudioCatalog(result)
    } catch (cause) {
      setError(userFacingError(cause, '默认音色保存失败，请检查当前账号是否已开通该音色。'))
    } finally {
      setSelectingVoiceId('')
    }
  }

  const confirmStage = async () => {
    if (!summary) {
      return
    }

    if (summary.status === 'completed' && detail?.output_asset?.id) {
      await submitReview('accepted')

      return
    }

    setError('官方 Hermes 视频团队仍在执行，成片通过 Reviewer 后会自动进入草稿箱。')
  }

  const pickSetupPaths = async (options: Parameters<NonNullable<typeof window.hermesDesktop>['selectPaths']>[0]) => {
    setSetupError('')

    try {
      const paths = (await window.hermesDesktop?.selectPaths(options)) || []

      setSetupDocuments(current => [...new Set([...current, ...paths])])
    } catch (cause) {
      setSetupError(userFacingError(cause, '素材选择失败，请重试。'))
    }
  }

  const pickSetupDocuments = () =>
    pickSetupPaths({
      directories: false,
      filters: [{ name: '文案与脚本', extensions: ['doc', 'docx', 'md', 'pdf', 'rtf', 'txt'] }],
      multiple: true,
      title: '选择文案或脚本文档'
    })

  const pickSetupFolders = () => pickSetupPaths({ directories: true, multiple: true, title: '选择素材文件夹' })

  const pickSetupImages = () =>
    pickSetupPaths({
      directories: false,
      filters: [{ name: '图片', extensions: ['avif', 'gif', 'heic', 'jpeg', 'jpg', 'png', 'webp'] }],
      multiple: true,
      title: '选择图片素材'
    })

  const dropSetupDocuments = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setSetupError('')

    const paths = Array.from(event.dataTransfer.files)
      .map(file => window.hermesDesktop?.getPathForFile(file) || '')
      .filter(Boolean)

    if (!paths.length) {
      setSetupError('没有读取到文档路径，请使用“添加文档”选择文件。')

      return
    }

    setSetupDocuments(current => [...new Set([...current, ...paths])])
  }

  const submitSetup = async () => {
    if ((!setupScript.trim() && !setupDocuments.length) || setupRunning) {
      return
    }

    setSetupSubmitting(true)
    setSetupError('')
    setSetupStatus('正在拆分文案并整理素材…')

    try {
      const attachments = await Promise.all(
        setupDocuments.map(async path => ({
          dataUrl: isRemoteGateway() ? await window.hermesDesktop?.readFileDataUrl(path) : undefined,
          name: pathLabel(path),
          path
        }))
      )

      const taskId = onStartOperation({
        accountId: accountId || 'prospect_default',
        attachments,
        kind: 'video.setup',
        note: setupScript,
        selections: setupSelections
      })

      setOperationTaskId(taskId)
      setSetupStatus('正在拆分文案并创建分镜，完成后会在当前经营对象中自动进入导演工作台。')
    } catch (cause) {
      setSetupSubmitting(false)
      setSetupStatus('')
      setSetupError(userFacingError(cause, '提交失败，请稍后重试。'))
    }
  }

  const openSetupCategory = (category: SetupCategory) => {
    setSetupCategory(category)
    setSetupRailCollapsed(false)
  }

  const selectSetupAsset = (category: SetupCategory, assetId: string) => {
    setSetupSelections(current => ({ ...current, [category]: assetId }))
    setSetupCategory(null)
    setSetupRailCollapsed(true)
  }

  const toggleSetupRail = () => {
    setSetupCategory(null)
    setSetupRailCollapsed(current => !current)
  }

  if (!productions.length) {
    return (
      <VideoSetupWorkspace
        activeCategory={setupCategory}
        assets={setupAssets}
        documents={setupDocuments}
        error={setupError || setupOperation?.error || error}
        onBack={onBack}
        onCategory={openSetupCategory}
        onDocumentDrop={dropSetupDocuments}
        onPickDocuments={() => void pickSetupDocuments()}
        onPickFolders={() => void pickSetupFolders()}
        onPickImages={() => void pickSetupImages()}
        onRemoveDocument={path => setSetupDocuments(current => current.filter(item => item !== path))}
        onScript={setSetupScript}
        onSelect={selectSetupAsset}
        onSubmit={() => void submitSetup()}
        onToggleRail={toggleSetupRail}
        railCollapsed={setupRailCollapsed}
        script={setupScript}
        selections={setupSelections}
        status={setupStatus || setupOperation?.label || ''}
        submitting={setupRunning}
      />
    )
  }

  const production = detail?.production
  const summary = detail?.summary || productions.find(item => item.id === selectedId) || productions[0]
  const scenes = production?.video_ir?.scenes || []
  const selectedScene = scenes.find(scene => scene.id === selectedSceneId) || scenes[0]
  const canvas = production?.video_ir?.canvas || summary?.canvas || { width: 1080, height: 1920, fps: 30 }

  const totalDuration =
    scenes.reduce((total, scene) => total + Number(scene.duration || 0), 0) || summary?.duration || 1

  const finalMedia = detail?.media_assets.find(asset => asset.id === production?.final_video_asset_id)
  const quality = production?.receipt?.summary?.technical?.quality_assurance
  const selectedVisualId = selectedScene?.visuals?.[0]?.media_asset_id
  const selectedVisual = detail?.media_assets.find(asset => asset.id === selectedVisualId)
  const scenePlan = production?.render_plan?.scenes?.find(item => item.scene_id === selectedScene?.id)
  const readiness = detail?.readiness || summary?.readiness
  const ratio = ratioLabel(canvas)
  const accepted = detail?.output_asset?.human_review_status === 'accepted'
  const activeReferenceCategory: SetupCategory = inspectorTab === 'materials' ? 'scenes' : inspectorTab

  const directorColumns =
    directorLayout === 'wide'
      ? inspectorRailHidden
        ? sceneRailCollapsed
          ? 'grid-cols-[3.5rem_minmax(0,1fr)]'
          : 'grid-cols-[15rem_minmax(0,1fr)]'
        : sceneRailCollapsed
          ? 'grid-cols-[3.5rem_minmax(0,1fr)_7rem]'
          : 'grid-cols-[15rem_minmax(0,1fr)_7rem]'
      : directorLayout === 'compact'
        ? inspectorRailHidden
          ? sceneRailCollapsed
            ? 'grid-cols-[3.5rem_minmax(0,1fr)]'
            : 'grid-cols-[12rem_minmax(0,1fr)]'
          : sceneRailCollapsed
            ? 'grid-cols-[3.5rem_minmax(0,1fr)_7rem]'
            : 'grid-cols-[12rem_minmax(0,1fr)_7rem]'
        : 'grid-cols-1'

  return (
    <section
      className="flex min-h-0 flex-1 flex-col overflow-hidden bg-(--ui-chat-surface-background)"
      data-director-layout={directorLayout}
      ref={directorShellRef}
    >
      <header
        className={`grid min-h-[calc(var(--titlebar-height)+2.5rem)] items-center gap-3 border-b border-(--ui-stroke-tertiary) bg-(--ui-chat-surface-background) px-4 pt-(--titlebar-height) pb-2.5 ${directorLayout === 'wide' ? 'grid-cols-[15rem_minmax(0,1fr)_auto] px-5' : 'grid-cols-[minmax(0,1fr)_auto]'}`}
      >
        <div className="flex min-w-0 items-center gap-2">
          <BackButton onBack={onBack} />
          <span className="h-5 w-px shrink-0 bg-(--ui-stroke-tertiary)" />
          <label className="flex min-w-0 items-center gap-2">
            <select
              aria-label="视频项目"
              className="min-w-0 max-w-48 appearance-none truncate bg-transparent text-base font-semibold tracking-[-0.03em] outline-none"
              onChange={event => setSelectedId(event.target.value)}
              value={selectedId}
            >
              {productions.map(item => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
            <ChevronDown className="size-3.5 shrink-0 text-(--ui-text-tertiary)" />
          </label>
        </div>

        <div className={directorLayout === 'wide' ? '' : 'order-3 col-span-full min-w-0 overflow-x-auto'}>
          <StageRail activeStage={activeStage} onSelect={setActiveStage} />
        </div>

        <div className="flex items-center justify-end gap-1.5">
          <button
            className="hidden h-9 items-center gap-1.5 rounded-xl border border-(--ui-stroke-tertiary) bg-(--ui-bg-primary) px-3 text-[0.68rem] font-medium text-(--ui-text-secondary) transition hover:border-(--ui-stroke-primary) hover:text-foreground sm:flex"
            onClick={() =>
              startOperation({
                kind: 'video.autopilot',
                productionId: summary?.id || selectedId,
                title: summary?.title || '当前视频'
              })
            }
            type="button"
          >
            <Zap className="size-3.5" /> 全自动
          </button>
          <button
            className="hidden h-9 items-center gap-1.5 rounded-xl border border-(--ui-stroke-tertiary) bg-(--ui-bg-primary) px-3 text-[0.68rem] font-medium text-(--ui-text-secondary) transition hover:border-(--ui-stroke-primary) hover:text-foreground sm:flex"
            disabled={!finalMedia?.playback_path}
            onClick={() =>
              startOperation({
                kind: 'video.export',
                productionId: summary?.id || selectedId,
                title: summary?.title || '当前视频'
              })
            }
            type="button"
          >
            <Download className="size-3.5" /> 导出
          </button>
          <button
            aria-label="刷新视频生产任务"
            className="grid size-9 place-items-center rounded-xl border border-(--ui-stroke-tertiary) bg-(--ui-bg-primary) text-(--ui-text-tertiary) transition hover:border-(--ui-stroke-primary) hover:text-foreground"
            disabled={loadingList}
            onClick={() => void refresh()}
            type="button"
          >
            <RefreshCw className={`size-3.5 ${loadingList ? 'animate-spin' : ''}`} />
          </button>
          <WorkspaceRailToggle
            collapsed={inspectorRailHidden}
            onToggle={() => {
              setInspectorRailHidden(current => {
                if (!current) {
                  setInspectorPanelOpen(false)
                }

                return !current
              })
            }}
            railName="项目素材栏"
          />
        </div>
      </header>

      {error ? (
        <div className="mx-5 mt-4 flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/5 px-3 py-2 text-xs text-red-600">
          <AlertCircle className="size-4" /> {error}
        </div>
      ) : null}

      {operationProgress ? (
        <div
          aria-live="polite"
          className={`mx-5 mt-4 flex items-center gap-3 rounded-xl border px-3 py-2.5 text-xs ${operationProgress.state === 'error' ? 'border-red-500/20 bg-red-500/5 text-red-700' : 'border-(--ui-stroke-tertiary) bg-(--ui-bg-primary) text-(--ui-text-secondary)'}`}
          role="status"
        >
          {operationProgress.state === 'complete' ? (
            <CheckCircle2 className="size-4 shrink-0 text-emerald-600" />
          ) : operationProgress.state === 'error' ? (
            <AlertCircle className="size-4 shrink-0" />
          ) : operationProgress.state === 'waiting' ? (
            <Clock className="size-4 shrink-0 text-amber-600" />
          ) : (
            <Loader2 className="size-4 shrink-0 animate-spin text-(--ui-accent)" />
          )}
          <div className="min-w-0 flex-1">
            <strong className="block truncate font-medium text-foreground">{operationProgress.label}</strong>
            <span className="mt-0.5 block text-[0.64rem] text-(--ui-text-tertiary)">
              {videoOperationStateLabel(operationProgress.state)}
            </span>
          </div>
        </div>
      ) : null}

      <div
        className={`relative grid min-h-0 flex-1 ${directorColumns} ${directorLayout === 'wide' ? '' : 'overflow-y-auto'}`}
      >
        <aside
          className={`flex min-h-0 flex-col border-(--ui-stroke-tertiary) bg-(--ui-bg-quaternary) transition-[width] ${directorLayout === 'stacked' ? 'max-h-64 border-b' : 'border-r'}`}
        >
          <div
            className={`flex h-12 items-center border-b border-(--ui-stroke-tertiary) ${sceneRailCollapsed ? 'justify-center px-1' : 'justify-between px-3'}`}
          >
            {!sceneRailCollapsed ? (
              <span className="flex items-center gap-2 text-[0.68rem] font-semibold text-(--ui-text-secondary)">
                <Layers3 className="size-3.5" /> 镜头列表
              </span>
            ) : (
              <Layers3 className="size-4 text-(--ui-text-tertiary)" />
            )}
            <div className="flex items-center gap-1">
              {!sceneRailCollapsed ? (
                <button
                  aria-label="新建镜头"
                  className="grid size-7 place-items-center rounded-lg border border-(--ui-stroke-tertiary) bg-(--ui-bg-primary) text-(--ui-text-tertiary) hover:text-foreground"
                  onClick={() =>
                    startOperation({
                      kind: 'video.scene.add',
                      productionId: summary?.id || selectedId,
                      title: summary?.title || '当前视频'
                    })
                  }
                  type="button"
                >
                  <Plus className="size-3.5" />
                </button>
              ) : null}
              <button
                aria-expanded={!sceneRailCollapsed}
                aria-label={sceneRailCollapsed ? '展开镜头列表' : '折叠镜头列表'}
                className="grid size-7 place-items-center rounded-lg text-(--ui-text-tertiary) transition hover:bg-(--ui-row-hover-background) hover:text-foreground"
                onClick={() => setSceneRailCollapsed(current => !current)}
                type="button"
              >
                {sceneRailCollapsed ? <ChevronRight className="size-3.5" /> : <ChevronLeft className="size-3.5" />}
              </button>
            </div>
          </div>
          {!sceneRailCollapsed ? (
            <div className="min-h-0 flex-1 overflow-y-auto p-2.5">
              {loadingDetail ? (
                <div className="flex items-center gap-2 px-2 py-4 text-xs text-[#8d8479]">
                  <Loader2 className="size-4 animate-spin" /> 读取镜头
                </div>
              ) : (
                <div className="grid gap-2.5">
                  {scenes.map((scene, index) => {
                    const sceneAsset = detail?.media_assets.find(
                      asset => asset.id === scene.visuals?.[0]?.media_asset_id
                    )

                    return (
                      <button
                        className={`group relative flex min-w-0 items-center gap-2.5 rounded-xl border p-1.5 text-left transition ${
                          scene.id === selectedScene?.id
                            ? 'border-[#ef704f] bg-[#fff9f1] shadow-[0_8px_22px_-18px_rgba(105,70,45,.7)]'
                            : 'border-[#ddd4c7] bg-[#fbf8f1] hover:border-[#c9bdad]'
                        }`}
                        key={scene.id}
                        onClick={() => setSelectedSceneId(scene.id)}
                        type="button"
                      >
                        <span className="relative h-[4.45rem] w-[6.6rem] shrink-0 overflow-hidden rounded-lg bg-[linear-gradient(145deg,#29363b,#9f6755)]">
                          {sceneAsset?.media_type === 'image' ? <SceneImage asset={sceneAsset} /> : null}
                          <span
                            className={`absolute left-1 top-1 rounded px-1.5 py-0.5 font-mono text-[0.56rem] text-white ${scene.id === selectedScene?.id ? 'bg-[#ef704f]' : 'bg-black/45'}`}
                          >
                            {String(index + 1).padStart(2, '0')}
                          </span>
                        </span>
                        <span className="min-w-0 flex-1">
                          <strong className="block truncate text-[0.72rem] font-semibold text-[#4f483f]">
                            {scene.purpose || `镜头 ${index + 1}`}
                          </strong>
                          <small className="mt-1 block truncate text-[0.6rem] text-[#978d80]">
                            {formatDuration(scene.duration)} ·{' '}
                            {rendererLabel(
                              production?.render_plan?.scenes?.find(item => item.scene_id === scene.id)?.renderer
                            )}
                          </small>
                        </span>
                        {scene.id === selectedScene?.id ? (
                          <span className="size-1.5 shrink-0 rounded-full bg-[#ef704f]" />
                        ) : null}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          ) : null}
          {!sceneRailCollapsed ? (
            <div className="flex h-11 items-center justify-between border-t border-(--ui-stroke-tertiary) px-3 text-(--ui-text-tertiary)">
              <button
                aria-label="删除当前镜头"
                className="grid size-7 place-items-center rounded-lg hover:bg-black/5"
                type="button"
              >
                <Trash2 className="size-3.5" />
              </button>
              <span className="text-[0.6rem]">
                {scenes.length} 个镜头 · {formatDuration(totalDuration)}
              </span>
            </div>
          ) : null}
        </aside>

        <main
          className={`min-w-0 bg-(--ui-chat-surface-background) p-2.5 sm:p-3 ${directorLayout === 'wide' ? 'border-r border-(--ui-stroke-tertiary)' : directorLayout === 'stacked' ? 'border-b border-(--ui-stroke-tertiary)' : ''}`}
        >
          <div
            className="mx-auto overflow-hidden rounded-[14px] border border-[#d4ccbf] bg-[#1b1b1b] shadow-[0_18px_42px_-32px_rgba(54,42,31,.65)]"
            style={{ width: previewFrameStyle(canvas).width }}
          >
            <div className="grid place-items-center">
              <div
                className="relative grid w-full place-items-center overflow-hidden bg-[radial-gradient(circle_at_70%_20%,rgba(236,123,90,0.55),transparent_30%),linear-gradient(145deg,#17283a,#4d2930_58%,#a55743)] text-white"
                style={{ aspectRatio: `${canvas.width} / ${canvas.height}` }}
              >
                {finalMedia?.playback_path ? (
                  <video
                    className="block h-full w-full max-h-full max-w-full object-contain object-center"
                    controls
                    key={finalMedia.playback_path}
                    playsInline
                    preload="metadata"
                    src={playbackUrl(finalMedia.playback_path)}
                  />
                ) : selectedVisual?.playback_path && selectedVisual.media_type === 'image' ? (
                  <SceneImage asset={selectedVisual} />
                ) : (
                  <div className="absolute inset-0 opacity-20 [background-image:linear-gradient(rgba(255,255,255,.08)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.08)_1px,transparent_1px)] [background-size:28px_28px]" />
                )}
                {!finalMedia?.playback_path ? (
                  <div className="relative z-10 max-w-[78%] text-center [text-shadow:0_2px_18px_rgba(0,0,0,.55)]">
                    <span className="text-[0.62rem] font-bold tracking-[0.14em] text-white/65">{ratio}</span>
                    <strong className="mt-2 block text-lg sm:text-xl">
                      {selectedScene?.text?.find(layer => layer.role === 'headline')?.text ||
                        selectedScene?.purpose ||
                        summary?.title}
                    </strong>
                    <small className="mt-2 block text-[0.68rem] leading-relaxed text-white/70">
                      {selectedVisual?.name || '镜头画面尚未生成'}
                    </small>
                  </div>
                ) : null}
                {!finalMedia?.playback_path ? (
                  <span className="absolute right-2.5 bottom-2.5 z-20 rounded bg-black/45 px-1.5 py-1 font-mono text-[0.58rem]">
                    {formatDuration(selectedScene?.duration || totalDuration)}
                  </span>
                ) : null}
              </div>
            </div>
            <div className="flex min-h-10 flex-wrap items-center justify-between gap-2 bg-[#f8f4eb] px-3 py-1.5 text-[#6e665c]">
              <span className="flex items-center gap-3 text-[0.65rem]">
                {finalMedia?.playback_path ? <Volume2 className="size-3.5" /> : <Play className="size-3.5" />}
                {finalMedia?.playback_path
                  ? `${production?.video_ir?.audio?.voice_asset_id ? '旁白已绑定' : '当前成片无旁白'} · ${formatDuration(totalDuration)}`
                  : `${formatDuration(selectedScene?.duration || 0)} / ${formatDuration(totalDuration)}`}
              </span>
              <span className="flex flex-wrap items-center justify-end gap-2 text-[0.62rem]">
                <MetaChip label={ratio} />
                <MetaChip label={`${canvas.width}×${canvas.height}`} />
                <MetaChip label={`${canvas.fps} FPS`} />
              </span>
            </div>
          </div>

          <VersionStrip
            assets={detail?.media_assets || []}
            onStartOperation={startOperation}
            scene={selectedScene}
            selectedAsset={selectedVisual}
            summary={summary}
          />

          <DirectorCommandBox
            accepted={accepted}
            activeStage={activeStage}
            completed={summary?.status === 'completed' && Boolean(detail?.output_asset?.id)}
            onOpenDrafts={onOpenDrafts}
            onReview={decision => void submitReview(decision)}
            onReviewNote={setReviewNote}
            onStartOperation={startOperation}
            reviewing={reviewing}
            reviewNote={reviewNote}
            scene={selectedScene}
            summary={summary}
          />

          <Timeline
            assets={detail?.media_assets || []}
            audio={production?.video_ir?.audio || {}}
            captions={production?.video_ir?.captions || []}
            onSelect={setSelectedSceneId}
            scenes={scenes}
            selectedSceneId={selectedScene?.id || ''}
            totalDuration={totalDuration}
          />
        </main>

        {!inspectorRailHidden && directorLayout !== 'stacked' ? (
          <VideoReferenceRail
            activeCategory={inspectorTab === 'materials' ? null : inspectorTab}
            ariaLabel="项目参考素材"
            onCategory={category => {
              setInspectorTab(category)
              setInspectorPanelOpen(current => (category === inspectorTab ? !current : true))
            }}
            resolveAsset={category => detail?.media_assets.find(item => assetMatchesTab(item, category))}
          >
            <VideoProductionRailSummary
              accepted={accepted}
              activeStage={activeStage}
              canvas={canvas}
              completed={summary?.status === 'completed' && Boolean(detail?.output_asset?.id)}
              confirming={false}
              onConfirm={() => void confirmStage()}
              quality={quality}
              readiness={readiness}
              rendered={summary?.status === 'completed'}
              scenes={scenes}
              summary={summary}
              totalDuration={totalDuration}
            />
          </VideoReferenceRail>
        ) : null}

        {inspectorPanelOpen && !inspectorRailHidden && directorLayout !== 'stacked' ? (
          <div className="absolute inset-y-0 right-28 z-50 flex min-h-0 w-[28rem] max-w-[calc(100%-7rem)] overflow-hidden border-l border-(--ui-stroke-tertiary) bg-(--ui-chat-surface-background) shadow-[-18px_0_42px_-28px_rgba(54,42,31,.55)]">
            <VideoReferenceLibraryPanel
              assets={detail?.media_assets || []}
              audioCatalog={audioCatalog}
              category={activeReferenceCategory}
              onClose={() => setInspectorPanelOpen(false)}
              onSelectVoice={voiceId => void selectDefaultVoice(voiceId)}
              scene={selectedScene}
              scenePlan={scenePlan}
              selectingVoiceId={selectingVoiceId}
            />
          </div>
        ) : null}
      </div>
    </section>
  )
}

function VersionStrip({
  assets,
  onStartOperation,
  scene,
  selectedAsset,
  summary
}: {
  assets: MediaAssetProjection[]
  onStartOperation: StartVideoOperation
  scene?: VideoScene
  selectedAsset?: MediaAssetProjection
  summary?: VideoProductionSummary
}) {
  const alternatives = assets
    .filter(asset => asset.media_type !== 'audio' && ['broll', 'scene', 'storyboard'].includes(asset.role))
    .sort((left, right) => (left.id === selectedAsset?.id ? -1 : right.id === selectedAsset?.id ? 1 : 0))
    .slice(0, 4)

  return (
    <section className="mt-2.5 flex min-h-16 items-center gap-2.5 overflow-x-auto border-y border-[#ded6c9] px-2 py-2">
      <strong className="mr-1 shrink-0 text-[0.66rem] font-semibold text-[#6d645a]">版本</strong>
      {alternatives.length ? (
        alternatives.map((asset, index) => (
          <button
            aria-label={`使用版本 ${index + 1} ${asset.name}`}
            className={`relative h-12 w-20 shrink-0 overflow-hidden rounded-lg border bg-[#29363b] transition ${asset.id === selectedAsset?.id ? 'border-[#ef704f] ring-1 ring-[#ef704f]' : 'border-[#cfc5b6] hover:border-[#a99d8d]'}`}
            key={asset.id}
            onClick={() =>
              onStartOperation({
                kind: 'video.asset.select',
                mediaAssetId: asset.id,
                productionId: summary?.id || '',
                sceneId: scene?.id,
                title: summary?.title || '当前视频'
              })
            }
            type="button"
          >
            {asset.media_type === 'image' ? (
              <SceneImage asset={asset} />
            ) : (
              <MonitorPlay className="m-auto size-5 text-white/55" />
            )}
            <span className="absolute bottom-1 right-1 rounded bg-black/45 px-1 py-0.5 font-mono text-[0.5rem] text-white">
              V{index + 1}
            </span>
          </button>
        ))
      ) : (
        <span className="text-[0.62rem] text-[#a0978a]">当前镜头还没有可切换版本</span>
      )}
      <button
        className="flex h-12 shrink-0 items-center gap-1.5 rounded-lg border border-dashed border-[#cfc5b6] px-3 text-[0.62rem] text-[#796f63] transition hover:border-[#ef704f]/50 hover:text-[#dc603f]"
        onClick={() =>
          onStartOperation({
            kind: 'video.version.generate',
            productionId: summary?.id || '',
            sceneId: scene?.id,
            title: summary?.title || '当前视频'
          })
        }
        type="button"
      >
        <Plus className="size-3.5" /> 生成新版本
      </button>
    </section>
  )
}

function DirectorCommandBox({
  accepted,
  activeStage,
  completed,
  onStartOperation,
  onReview,
  onReviewNote,
  onOpenDrafts,
  reviewNote,
  reviewing,
  scene,
  summary
}: {
  accepted: boolean
  activeStage: DirectorStage
  completed: boolean
  onStartOperation: StartVideoOperation
  onReview: (decision: 'accepted' | 'changes_requested') => void
  onReviewNote: (note: string) => void
  onOpenDrafts?: () => void
  reviewNote: string
  reviewing: 'accepted' | 'changes_requested' | null
  scene?: VideoScene
  summary?: VideoProductionSummary
}) {
  const target = `${stageLabel(activeStage)} · ${scene?.purpose || summary?.title || '整个作品'}`

  return (
    <section className="mt-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2 px-1">
        <h3 className="text-[0.7rem] font-semibold text-(--ui-text-secondary)">
          <span className="mr-1.5 text-(--ui-accent)">当前目标</span>· {target}
        </h3>
        {completed ? (
          <span
            className={`rounded-full px-2.5 py-1 text-[0.62rem] font-semibold ${accepted ? 'bg-emerald-500/10 text-emerald-700' : 'bg-amber-500/10 text-amber-700'}`}
          >
            {accepted ? '成片已确认' : '等待完整审片'}
          </span>
        ) : null}
      </div>
      <div className="mt-2 rounded-2xl">
        <div className={composerSurfaceFrame}>
          <div
            aria-hidden
            className={cn(
              'pointer-events-none absolute inset-0 -z-10 rounded-[inherit]',
              composerFill,
              composerSurfaceGlass
            )}
          />
          <div className={composerSurfaceContent}>
            <div className="grid w-full grid-cols-[1fr_auto] items-center gap-(--composer-control-gap)">
              <textarea
                aria-label="视频修改意见"
                className="min-h-(--composer-input-min-height) max-h-(--composer-input-max-height) min-w-0 resize-none overflow-y-auto bg-transparent px-1 py-1 text-[length:var(--conversation-text-font-size)] leading-(--conversation-line-height) outline-none [field-sizing:content] placeholder:text-(--ui-text-tertiary)"
                onChange={event => onReviewNote(event.target.value)}
                placeholder={`直接说你想怎样修改当前${scene ? '镜头' : '作品'}……`}
                rows={1}
                value={reviewNote}
              />
              <Button
                aria-label={completed ? '局部修改' : '提交修改'}
                className={PRIMARY_ICON_BTN}
                disabled={!reviewNote.trim() || reviewing !== null}
                onClick={() => {
                  if (completed) {
                    onReview('changes_requested')
                  } else {
                    onStartOperation({
                      kind: 'video.stage.modify',
                      note: reviewNote.trim(),
                      productionId: summary?.id || '',
                      sceneId: scene?.id,
                      stage: activeStage,
                      title: summary?.title || '当前视频'
                    })
                  }
                }}
                size="icon"
                type="button"
              >
                <Codicon name="arrow-up" size="0.875rem" />
              </Button>
            </div>
          </div>
        </div>
      </div>
      {accepted ? (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-emerald-500/8 px-3 py-2 text-[0.66rem] text-emerald-700">
          <p>当前成片已经确认并归入草稿箱；发布准备、审批和失败恢复统一从草稿箱继续。</p>
          <Button onClick={onOpenDrafts} size="sm" variant="outline">
            前往草稿箱
          </Button>
        </div>
      ) : null}
    </section>
  )
}

function VoiceLibrary({
  catalog,
  embedded = false,
  onSelect,
  selectingVoiceId
}: {
  catalog: AudioCatalogProjection | null
  embedded?: boolean
  onSelect: (voiceId: string) => void
  selectingVoiceId: string
}) {
  if (!catalog) {
    return (
      <section
        className={cn(
          'bg-[#fffdf8] p-3 text-[0.64rem] text-(--ui-text-tertiary)',
          embedded ? 'border-t border-[#ded6c9]' : 'mt-3 rounded-xl border border-[#ded6c9]'
        )}
      >
        声音服务目录暂时不可用，现有成片不会被修改。
      </section>
    )
  }

  const metadata = catalog.metadata || {}

  return (
    <section
      className={cn(
        'space-y-3 bg-[#fffdf8] p-3',
        embedded ? 'border-t border-[#ded6c9]' : 'mt-3 rounded-xl border border-[#ded6c9]'
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-xs font-semibold">火山声音库</h3>
          <p className="mt-1 text-[0.6rem] leading-5 text-(--ui-text-tertiary)">
            {catalog.display_name || catalog.provider || '未配置语音服务'} ·{' '}
            {catalog.available ? '密钥在线' : '密钥不可用'} · {catalog.default_model || '模型未识别'}
          </p>
        </div>
        <span
          className={`rounded-full px-2 py-1 text-[0.56rem] ${catalog.available ? 'bg-emerald-500/10 text-emerald-700' : 'bg-amber-500/10 text-amber-800'}`}
        >
          {catalog.available ? '常驻已接通' : '需要配置'}
        </span>
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {(catalog.voices || []).map(voice => {
          const selected = catalog.configured_voice === voice.id
          const selecting = selectingVoiceId === voice.id

          return (
            <button
              className={`rounded-lg border p-2.5 text-left transition ${selected ? 'border-(--ui-accent) bg-(--ui-row-active-background)' : 'border-[#ded6c9] bg-white hover:border-[#b8ac9c]'}`}
              disabled={Boolean(selectingVoiceId)}
              key={voice.id}
              onClick={() => onSelect(voice.id)}
              type="button"
            >
              <span className="flex items-center justify-between gap-2">
                <strong className="text-[0.68rem]">{voice.display || voice.id}</strong>
                {selecting ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : selected ? (
                  <CheckCircle2 className="size-3.5 text-(--ui-accent)" />
                ) : null}
              </span>
              <small className="mt-1 block text-[0.55rem] text-(--ui-text-tertiary)">
                {[voice.language, voice.gender === 'female' ? '女声' : voice.gender === 'male' ? '男声' : '', voice.scenario]
                  .filter(Boolean)
                  .join(' · ')}
              </small>
              <small className="mt-1 block truncate font-mono text-[0.48rem] text-(--ui-text-tertiary)">
                {voice.id}
              </small>
            </button>
          )
        })}
      </div>

      <div className="rounded-lg bg-[#f5f0e7] px-2.5 py-2 text-[0.57rem] leading-5 text-[#756b5f]">
        官方大模型音色目录共 {metadata.official_voice_count || '多'} 款；当前先显示与 Seed TTS 2.0
        资源族匹配的常用音色。账户全量目录同步需要火山 OpenAPI 的 AK/SK，语音合成用的 X-Api-Key
        本身不能枚举 ListSpeakers，因此这里不会伪造“已开通”状态。
      </div>

      <div className="flex flex-wrap gap-1.5">
        {(metadata.service_families || []).map(family => (
          <span
            className={`rounded-full border px-2 py-1 text-[0.52rem] ${family.active ? 'border-emerald-500/30 bg-emerald-500/8 text-emerald-700' : 'border-[#ded6c9] text-[#756b5f]'}`}
            key={family.id}
          >
            {family.name}{family.active ? ' · 当前' : ''}
          </span>
        ))}
      </div>
    </section>
  )
}

function VideoReferenceRail({
  activeCategory,
  ariaLabel,
  children,
  className,
  navClassName,
  onCategory,
  resolveAsset
}: {
  activeCategory: SetupCategory | null
  ariaLabel: string
  children?: ReactNode
  className?: string
  navClassName?: string
  onCategory: (category: SetupCategory) => void
  resolveAsset?: (category: SetupCategory) => MediaAssetProjection | undefined
}) {
  return (
    <aside
      className={cn(
        'flex min-h-0 flex-col overflow-hidden border-l border-(--ui-stroke-tertiary) bg-(--ui-chat-surface-background)',
        className
      )}
    >
      <nav aria-label={ariaLabel} className={cn('grid shrink-0 gap-1.5 px-2 py-3', navClassName)}>
        {VIDEO_REFERENCE_CATEGORIES.map(category => {
          const Icon = category.icon
          const asset = resolveAsset?.(category.id)

          return (
            <button
              aria-label={category.label}
              className={`flex min-h-14 flex-col items-center justify-center gap-1.5 rounded-xl border px-1 text-center transition ${activeCategory === category.id ? 'border-(--ui-accent) bg-(--ui-row-active-background) text-(--ui-accent)' : 'border-transparent text-(--ui-text-secondary) hover:border-(--ui-stroke-tertiary) hover:bg-(--ui-row-hover-background)'}`}
              key={category.id}
              onClick={() => onCategory(category.id)}
              type="button"
            >
              <SetupCategoryThumbnail asset={asset} icon={Icon} label={category.label} />
              <strong className="text-[0.65rem]">{category.label}</strong>
            </button>
          )
        })}
      </nav>
      {children}
    </aside>
  )
}

function VideoProductionRailSummary({
  accepted,
  activeStage,
  canvas,
  completed,
  confirming,
  onConfirm,
  quality,
  readiness,
  rendered,
  scenes,
  summary,
  totalDuration
}: {
  accepted: boolean
  activeStage: DirectorStage
  canvas: CanvasSpec
  completed: boolean
  confirming: boolean
  onConfirm: () => void
  quality?: VideoQualityReport
  readiness?: VideoRenderReadiness
  rendered: boolean
  scenes: VideoScene[]
  summary?: VideoProductionSummary
  totalDuration: number
}) {
  const qualityLabel = quality
    ? { hold: '需人工复核', ready: '自动质检通过', reject: '技术拒收' }[quality.disposition]
    : rendered
      ? '待人工审片'
      : '等待质检'

  const confirmLabel = confirming
    ? '正在本地渲染…'
    : completed
        ? accepted
          ? '成片已确认'
          : '确认成片'
        : '官方 Hermes 管线运行中'

  const compactConfirmLabel = confirming
    ? '渲染中'
    : completed
        ? accepted
          ? '已确认'
          : '确认成片'
        : '制作中'

  return (
    <section
      aria-label="作品状态与质检"
      className="flex min-h-0 flex-1 flex-col border-t border-(--ui-stroke-tertiary)"
    >
      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2.5">
        <div className="grid justify-items-center gap-1.5 text-center">
          <span className="text-[0.52rem] font-semibold text-(--ui-text-quaternary)">作品状态</span>
          <ProductionStatus status={summary?.status || 'prepared'} />
        </div>

        <dl className="mt-2.5 grid grid-cols-2 gap-1">
          <RailStat label="画幅" value={ratioLabel(canvas)} />
          <RailStat label="镜头" value={`${scenes.length || summary?.scene_count || 0}`} />
          <RailStat label="时长" value={formatDuration(totalDuration)} />
          <RailStat label="方式" value={`${summary?.renderers?.length || 0}`} />
        </dl>

        <div className="mt-2.5 border-t border-(--ui-stroke-tertiary) pt-2.5">
          <div className="grid justify-items-center gap-1 text-center">
            {quality?.disposition === 'ready' ? (
              <CheckCircle2 className="size-4 text-emerald-600" />
            ) : (
              <AlertCircle
                className={cn(
                  'size-4',
                  quality?.disposition === 'reject' ? 'text-red-600' : 'text-amber-600'
                )}
              />
            )}
            <strong className="text-[0.55rem]">自动媒体质检</strong>
            <span
              className={cn(
                'text-[0.5rem] font-semibold',
                quality?.disposition === 'ready'
                  ? 'text-emerald-700'
                  : quality?.disposition === 'reject'
                    ? 'text-red-700'
                    : 'text-amber-700'
              )}
            >
              {qualityLabel}
            </span>
          </div>

          {quality?.checks?.length ? (
            <div className="mt-2 grid gap-1">
              {quality.checks.map(check => (
                <div
                  className="flex items-center justify-between gap-1 rounded-md bg-(--ui-button-hover-background) px-1.5 py-1 text-[0.48rem]"
                  key={check.id}
                  title={`${check.label}：${qualityCheckLabel(check)}`}
                >
                  <span className="min-w-0 truncate text-(--ui-text-secondary)">{check.label}</span>
                  <span
                    className={cn(
                      'shrink-0',
                      check.status === 'fail' ? 'font-semibold text-red-700' : 'text-(--ui-text-quaternary)'
                    )}
                  >
                    {qualityCheckLabel(check)}
                  </span>
                </div>
              ))}
            </div>
          ) : null}
        </div>

        {readiness?.ready === false ? (
          <div className="mt-2.5 border-t border-(--ui-stroke-tertiary) pt-2.5">
            <strong className="block text-center text-[0.52rem] text-amber-800">
              还缺 {readiness.blockers?.length || 0} 项
            </strong>
            <div className="mt-1.5 grid gap-1">
              {(readiness.blockers || []).map(blocker => (
                <span
                  className="line-clamp-2 rounded-md bg-amber-500/8 px-1.5 py-1 text-[0.48rem] leading-3 text-amber-800"
                  key={blocker.code || blocker.message}
                  title={blocker.message || blocker.code}
                >
                  {blocker.message || blocker.code}
                </span>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      <div className="border-t border-[#d8d0c2] bg-[#faf7ef] p-2">
        <Button
          aria-label={confirmLabel}
          className="h-10 w-full rounded-xl bg-[#f06443] px-1 text-[0.6rem] font-semibold shadow-[0_12px_28px_-18px_rgba(225,83,48,.75)] hover:bg-[#df5838]"
          disabled={
            accepted ||
            confirming ||
            !completed ||
            quality?.disposition === 'reject' ||
            (activeStage === 'edit' && readiness?.ready === false)
          }
          onClick={onConfirm}
          title={confirmLabel}
        >
          {accepted ? <CheckCircle2 className="size-3.5" /> : <Zap className="size-3.5" />}
          {compactConfirmLabel}
        </Button>
      </div>
    </section>
  )
}

function RailStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md bg-(--ui-button-hover-background) px-1 py-1.5 text-center">
      <dt className="text-[0.44rem] text-(--ui-text-quaternary)">{label}</dt>
      <dd className="mt-0.5 truncate text-[0.55rem] font-semibold" title={`${label}：${value}`}>
        {value}
      </dd>
    </div>
  )
}

function VideoReferenceLibraryPanel({
  assets,
  audioCatalog,
  category,
  onClose,
  onSelectVoice,
  scene,
  scenePlan,
  selectingVoiceId
}: {
  assets: MediaAssetProjection[]
  audioCatalog: AudioCatalogProjection | null
  category: SetupCategory
  onClose: () => void
  onSelectVoice: (voiceId: string) => void
  scene?: VideoScene
  scenePlan?: { fallback_used?: boolean; renderer?: string }
  selectingVoiceId: string
}) {
  const definition = VIDEO_REFERENCE_CATEGORIES.find(item => item.id === category) || VIDEO_REFERENCE_CATEGORIES[0]
  const sceneAssetId = scene?.visuals?.[0]?.media_asset_id

  const referenceAssets = assets.filter(
    asset => setupAssetMatches(asset, category) || (category === 'scenes' && asset.id === sceneAssetId)
  )

  return (
    <aside className="flex min-h-0 flex-1 flex-col bg-(--ui-chat-surface-background)">
      <header className="flex h-12 items-center justify-between border-b border-(--ui-stroke-tertiary) px-3.5">
        <h3 className="text-[0.7rem] font-semibold text-(--ui-text-secondary)">{definition.label}库</h3>
        <button
          aria-label={`关闭${definition.label}库`}
          className="grid size-7 place-items-center rounded-lg text-(--ui-text-tertiary) transition hover:bg-(--ui-row-hover-background) hover:text-foreground"
          onClick={onClose}
          type="button"
        >
          <X className="size-3.5" />
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {category === 'sound' ? (
          <VoiceLibrary
            catalog={audioCatalog}
            onSelect={onSelectVoice}
            selectingVoiceId={selectingVoiceId}
          />
        ) : referenceAssets.length ? (
          <section aria-label={`${definition.label}素材`} className="grid gap-2.5">
            {referenceAssets.map(asset => (
              <article
                className="grid min-h-20 grid-cols-[5.5rem_minmax(0,1fr)] items-center gap-3 rounded-xl border border-(--ui-stroke-tertiary) bg-(--ui-bg-primary) p-1.5"
                key={asset.id}
              >
                <ReferenceThumb asset={asset} icon={definition.icon} />
                <span className="min-w-0 pr-2">
                  <strong className="block truncate text-[0.72rem] font-semibold text-foreground">{asset.name}</strong>
                  <small className="mt-1 block truncate text-[0.58rem] text-(--ui-text-tertiary)">
                    {[asset.provider || asset.source_type, asset.rights_status].filter(Boolean).join(' · ')}
                  </small>
                </span>
              </article>
            ))}
          </section>
        ) : (
          <div className="rounded-xl border border-dashed border-(--ui-stroke-tertiary) bg-(--ui-bg-quaternary) px-4 py-8 text-center text-[0.64rem] text-(--ui-text-tertiary)">
            当前项目还没有可用的{definition.label}素材
          </div>
        )}

        {category === 'scenes' ? (
          <dl className="mt-3 space-y-2 rounded-xl border border-[#ded6c9] bg-[#fffdf8] p-3 text-[0.64rem]">
            <InfoRow label="当前镜头" value={scene?.purpose || '未选择'} />
            <InfoRow label="生成方式" value={rendererLabel(scenePlan?.renderer)} />
            <InfoRow label="动态意图" value={scene?.motion_intent?.join(' / ') || '直接剪辑'} />
            <InfoRow label="画面填充" value={fitLabel(scene?.visuals?.[0]?.fit)} />
          </dl>
        ) : null}
      </div>
    </aside>
  )
}

function ReferenceThumb({ asset, icon: Icon }: { asset?: MediaAssetProjection; icon: typeof FileImage }) {
  return (
    <span className="grid h-[4.5rem] overflow-hidden rounded-lg bg-[#e4ddd1] text-[#81776b]">
      {asset?.media_type === 'image' ? <SceneImage asset={asset} /> : null}
      {asset?.media_type === 'audio' ? (
        <span className="grid size-full place-items-center bg-[repeating-linear-gradient(90deg,transparent_0_4px,rgba(100,131,104,.55)_4px_6px,transparent_6px_9px)]">
          <AudioLines className="size-5 rounded-full bg-[#f4efe5] p-0.5 text-[#648368]" />
        </span>
      ) : null}
      {!asset || asset.media_type === 'video' ? <Icon className="m-auto size-5 opacity-55" /> : null}
    </span>
  )
}

function qualityCheckLabel(check: VideoQualityCheck): string {
  if (check.status === 'not_applicable') {
    return '无需检查'
  }

  if (check.status === 'pass') {
    return '通过'
  }

  const evidence = check.evidence || {}

  if (check.id === 'black_frames' || check.id === 'frozen_frames') {
    return `最长 ${Number(evidence.longest_seconds || 0).toFixed(1)}s`
  }

  if (check.id === 'audio_loudness' && typeof evidence.integrated_lufs === 'number') {
    return `${evidence.integrated_lufs.toFixed(1)} LUFS`
  }

  return check.severity === 'critical' ? '未通过' : '需复核'
}

interface VideoSetupWorkspaceProps {
  activeCategory: SetupCategory | null
  assets: MediaAssetProjection[]
  documents: string[]
  error: string
  onBack?: () => void
  onCategory: (category: SetupCategory) => void
  onDocumentDrop: (event: DragEvent<HTMLDivElement>) => void
  onPickDocuments: () => void
  onPickFolders: () => void
  onPickImages: () => void
  onRemoveDocument: (path: string) => void
  onScript: (script: string) => void
  onSelect: (category: SetupCategory, assetId: string) => void
  onSubmit: () => void
  script: string
  selections: Record<SetupCategory, string>
  status: string
  submitting: boolean
  railCollapsed: boolean
  onToggleRail: () => void
}

function VideoSetupWorkspace({
  activeCategory,
  assets,
  documents,
  error,
  onBack,
  onCategory,
  onDocumentDrop,
  onPickDocuments,
  onPickFolders,
  onPickImages,
  onRemoveDocument,
  onScript,
  onSelect,
  onSubmit,
  script,
  selections,
  status,
  submitting,
  railCollapsed,
  onToggleRail
}: VideoSetupWorkspaceProps) {
  const category = VIDEO_REFERENCE_CATEGORIES.find(item => item.id === activeCategory)
  const categoryAssets = activeCategory ? assets.filter(asset => setupAssetMatches(asset, activeCategory)) : []

  return (
    <section
      className={cn(
        'grid min-h-0 flex-1 grid-rows-[var(--video-workbench-topbar-height)_minmax(0,1fr)] overflow-hidden bg-(--ui-chat-surface-background) [--video-workbench-topbar-height:2.75rem]',
        !railCollapsed && 'lg:grid-cols-[minmax(0,1fr)_7rem]'
      )}
    >
      <header className="grid h-(--video-workbench-topbar-height) min-w-0 items-center border-b border-(--ui-stroke-tertiary) bg-(--ui-chat-surface-background) px-3 lg:grid-cols-[7rem_minmax(0,1fr)_7rem]">
        <BackButton onBack={onBack} />
        <StageRail activeStage="setup" compact />
        <span />
      </header>

      <WorkspaceRailToggle collapsed={railCollapsed} onToggle={onToggleRail} railName="设定素材栏" />

      <main className="flex min-h-0 min-w-0 flex-col bg-(--ui-chat-surface-background)">
        <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-5">
          {!railCollapsed && category ? (
            <section
              aria-label={`${category.label}库`}
              className="grid content-start grid-cols-[repeat(auto-fill,minmax(9.5rem,1fr))] gap-3"
            >
              <button
                aria-label={`交给 AI 生成${category.label}`}
                className="grid h-40 place-items-center rounded-xl border border-dashed border-(--ui-stroke-tertiary) bg-(--ui-bg-quaternary) p-3 text-center transition hover:border-(--ui-stroke-primary) hover:bg-(--ui-row-hover-background)"
                onClick={() => onSelect(category.id, '')}
                type="button"
              >
                <span>
                  <Zap className="mx-auto size-5 text-(--ui-accent)" />
                  <strong className="mt-2 block text-xs text-foreground">AI 生成</strong>
                </span>
              </button>
              {categoryAssets.map(asset => (
                <button
                  aria-label={`选择${category.label} ${asset.name}`}
                  className={`h-40 overflow-hidden rounded-xl border bg-(--ui-bg-primary) text-left transition ${selections[category.id] === asset.id ? 'border-(--ui-accent) ring-1 ring-(--ui-accent)' : 'border-(--ui-stroke-tertiary) hover:border-(--ui-stroke-primary)'}`}
                  key={asset.id}
                  onClick={() => onSelect(category.id, asset.id)}
                  type="button"
                >
                  <span className="grid h-[7.75rem] bg-(--ui-bg-quaternary)">
                    <ReferenceThumb asset={asset} icon={category.icon} />
                  </span>
                  <span className="block truncate px-2.5 py-2 text-[0.66rem] font-semibold text-foreground">
                    {asset.name}
                  </span>
                </button>
              ))}
            </section>
          ) : null}
        </div>

        <VideoSetupComposer
          documents={documents}
          error={error}
          onDocumentDrop={onDocumentDrop}
          onPickDocuments={onPickDocuments}
          onPickFolders={onPickFolders}
          onPickImages={onPickImages}
          onRemoveDocument={onRemoveDocument}
          onScript={onScript}
          onSubmit={onSubmit}
          script={script}
          status={status}
          submitting={submitting}
        />
      </main>

      {!railCollapsed ? (
        <VideoReferenceRail
          activeCategory={activeCategory}
          ariaLabel="视频设定素材"
          className="lg:col-start-2 lg:row-span-2 lg:row-start-1"
          navClassName="pt-[calc(var(--video-workbench-topbar-height)+0.75rem)] pb-2"
          onCategory={onCategory}
          resolveAsset={categoryId => assets.find(asset => asset.id === selections[categoryId])}
        />
      ) : null}
    </section>
  )
}

function VideoSetupComposer({
  documents,
  error,
  onDocumentDrop,
  onPickDocuments,
  onPickFolders,
  onPickImages,
  onRemoveDocument,
  onScript,
  onSubmit,
  script,
  status,
  submitting
}: Pick<
  VideoSetupWorkspaceProps,
  | 'documents'
  | 'error'
  | 'onDocumentDrop'
  | 'onPickDocuments'
  | 'onPickFolders'
  | 'onPickImages'
  | 'onRemoveDocument'
  | 'onScript'
  | 'onSubmit'
  | 'script'
  | 'status'
  | 'submitting'
>) {
  const canSubmit = Boolean(script.trim() || documents.length) && !submitting

  return (
    <div className="relative shrink-0 bg-[linear-gradient(to_bottom,transparent,color-mix(in_srgb,var(--dt-background)_10%,transparent))] pt-2 pb-[var(--composer-shell-pad-block-end)]">
      <div
        className="mx-auto w-[min(var(--composer-width),calc(100%-2rem))] max-w-full rounded-2xl"
        onDragOver={event => event.preventDefault()}
        onDrop={onDocumentDrop}
      >
        <div className={composerSurfaceFrame}>
          <div
            aria-hidden
            className={cn(
              'pointer-events-none absolute inset-0 -z-10 rounded-[inherit]',
              composerFill,
              composerSurfaceGlass
            )}
          />
          <div className={composerSurfaceContent}>
            {documents.length ? (
              <div className="flex max-w-full flex-wrap gap-1.5 px-1 pt-1">
                {documents.map(path => (
                  <span
                    className="flex max-w-56 items-center gap-1.5 rounded-full bg-(--ui-bg-quaternary) py-1 pl-2.5 pr-1 text-[0.62rem] text-(--ui-text-secondary)"
                    key={path}
                  >
                    <FileText className="size-3.5 shrink-0" />
                    <span className="truncate">{pathLabel(path)}</span>
                    <button
                      aria-label={`移除 ${pathLabel(path)}`}
                      className="grid size-5 shrink-0 place-items-center rounded-full hover:bg-black/5"
                      onClick={() => onRemoveDocument(path)}
                      type="button"
                    >
                      <X className="size-3" />
                    </button>
                  </span>
                ))}
              </div>
            ) : null}

            {status ? <p className="px-1 text-[0.66rem] text-(--ui-text-secondary)">{status}</p> : null}
            {error ? <p className="px-1 text-[0.66rem] text-red-600">{error}</p> : null}

            <div className="grid w-full grid-cols-[auto_1fr_auto] items-center gap-(--composer-control-gap)">
              <ContextMenu
                onInsertText={text => onScript(script ? `${script}\n${text}` : text)}
                onPickFiles={onPickDocuments}
                onPickFolders={onPickFolders}
                onPickImages={onPickImages}
                state={VIDEO_COMPOSER_MENU_STATE}
              />
              <textarea
                aria-label="视频文案"
                className="min-h-(--composer-input-min-height) max-h-(--composer-input-max-height) min-w-0 resize-none overflow-y-auto bg-transparent px-1 py-1 text-[length:var(--conversation-text-font-size)] leading-(--conversation-line-height) text-foreground outline-none [field-sizing:content] placeholder:text-(--ui-text-tertiary)"
                onChange={event => onScript(event.target.value)}
                onKeyDown={event => {
                  if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                    event.preventDefault()

                    if (canSubmit) {
                      onSubmit()
                    }
                  }
                }}
                placeholder="输入文案或描述你想做的视频，也可以把脚本文档直接拖到这里……"
                rows={1}
                value={script}
              />
              <Button
                aria-label="开始拆分"
                className={PRIMARY_ICON_BTN}
                disabled={!canSubmit}
                onClick={onSubmit}
                size="icon"
                type="button"
              >
                {submitting ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Codicon name="arrow-up" size="0.875rem" />
                )}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function BackButton({ onBack }: { onBack?: () => void }) {
  return (
    <button
      className="inline-flex h-8 items-center gap-1 rounded-lg px-1.5 text-sm font-medium text-(--ui-text-secondary) transition hover:bg-(--ui-row-hover-background) hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
      disabled={!onBack}
      onClick={onBack}
      type="button"
    >
      <ChevronLeft className="size-4" /> 返回
    </button>
  )
}

function WorkspaceRailToggle({
  collapsed,
  onToggle,
  railName
}: {
  collapsed: boolean
  onToggle: () => void
  railName: string
}) {
  return (
    <Button
      aria-expanded={!collapsed}
      aria-label={`${collapsed ? '展开' : '折叠'}${railName}`}
      className={cn(
        titlebarButtonClass,
        'fixed top-(--titlebar-controls-top) right-[calc(var(--titlebar-tools-right)+var(--titlebar-control-size)+1.25rem)] z-70 bg-transparent select-none [-webkit-app-region:no-drag]'
      )}
      onClick={onToggle}
      size="icon-titlebar"
      type="button"
      variant="ghost"
    >
      <Codicon name="layout-sidebar-right" />
    </Button>
  )
}

function SetupCategoryThumbnail({
  asset,
  icon: Icon,
  label
}: {
  asset?: MediaAssetProjection
  icon: typeof Users
  label: string
}) {
  if (!asset) {
    return <Icon className="size-[1.15rem] shrink-0" />
  }

  return (
    <span
      aria-label={`${label}已选择 ${asset.name}`}
      className="relative grid size-8 shrink-0 place-items-center overflow-hidden rounded-lg border border-(--ui-stroke-tertiary) bg-(--ui-bg-primary)"
      role="img"
      title={asset.name}
    >
      <Icon className="size-4 text-(--ui-text-tertiary)" />
      {asset.media_type === 'image' ? (
        <span className="absolute inset-0">
          <SceneImage asset={asset} />
        </span>
      ) : null}
      {asset.media_type === 'video' && asset.playback_path ? (
        <video
          className="absolute inset-0 size-full object-cover"
          muted
          preload="metadata"
          src={playbackUrl(asset.playback_path)}
        />
      ) : null}
      {asset.media_type === 'audio' ? (
        <span className="absolute inset-0 grid place-items-center bg-[repeating-linear-gradient(90deg,#d7e1d3_0_3px,#76907b_3px_5px,#d7e1d3_5px_8px)]">
          <AudioLines className="size-4 rounded-full bg-(--ui-bg-primary) p-0.5 text-(--ui-text-secondary)" />
        </span>
      ) : null}
    </span>
  )
}

function StageRail({
  activeStage,
  compact = false,
  onSelect
}: {
  activeStage: DirectorStage
  compact?: boolean
  onSelect?: (stage: DirectorStage) => void
}) {
  const activeIndex = DIRECTOR_STAGES.findIndex(stage => stage.id === activeStage)

  return (
    <nav aria-label="视频制作阶段" className="hidden items-center justify-center lg:flex">
      {DIRECTOR_STAGES.map((stage, index) => (
        <span className="flex items-center" key={stage.id}>
          <button
            className={`relative font-semibold transition ${compact ? 'px-2.5 py-1 text-sm' : 'px-3 py-2 text-[0.78rem]'} ${index === activeIndex ? 'text-(--ui-accent)' : index < activeIndex ? 'text-(--ui-text-secondary)' : 'text-(--ui-text-tertiary) hover:text-foreground'}`}
            disabled={!onSelect}
            onClick={() => onSelect?.(stage.id)}
            type="button"
          >
            {stage.label}
            {index === activeIndex ? (
              <span className="absolute inset-x-2 -bottom-1 h-0.5 rounded-full bg-(--ui-accent)" />
            ) : null}
          </button>
          {index < DIRECTOR_STAGES.length - 1 ? (
            <ChevronRight className={`${compact ? 'mx-0 size-3.5' : 'mx-1 size-4'} text-(--ui-text-tertiary)`} />
          ) : null}
        </span>
      ))}
    </nav>
  )
}

function Timeline({
  assets,
  audio,
  captions,
  onSelect,
  scenes,
  selectedSceneId,
  totalDuration
}: {
  assets: MediaAssetProjection[]
  audio: Record<string, unknown>
  captions: Array<Record<string, unknown>>
  onSelect: (sceneId: string) => void
  scenes: VideoScene[]
  selectedSceneId: string
  totalDuration: number
}) {
  const selectedIndex = Math.max(
    0,
    scenes.findIndex(scene => scene.id === selectedSceneId)
  )

  const elapsed = scenes.slice(0, selectedIndex).reduce((sum, scene) => sum + Number(scene.duration || 0), 0)
  const playheadLeft = 8 + (elapsed / Math.max(totalDuration, 1)) * 88

  return (
    <section className="relative mt-2.5 overflow-hidden rounded-[14px] border border-[#d8d0c2] bg-[#f8f4eb] p-2.5">
      <div className="flex justify-between pl-14 font-mono text-[0.5rem] text-[#9c9285]">
        <span>00:00</span>
        <span>{formatDuration(totalDuration * 0.25)}</span>
        <span>{formatDuration(totalDuration * 0.5)}</span>
        <span>{formatDuration(totalDuration * 0.75)}</span>
        <span>{formatDuration(totalDuration)}</span>
      </div>
      <span
        className="pointer-events-none absolute bottom-2 top-6 z-20 w-px bg-[#ef704f]"
        style={{ left: `${playheadLeft}%` }}
      >
        <span className="absolute -left-1.5 -top-1 size-3 rotate-45 rounded-[2px] bg-[#ef704f]" />
      </span>
      <div className="mt-2 grid grid-cols-[3.25rem_minmax(0,1fr)] items-center gap-2">
        <strong className="flex items-center gap-1 text-[0.58rem] text-[#6e655b]">
          <MonitorPlay className="size-3" /> 视频
        </strong>
        <div className="flex h-10 gap-0.5 overflow-hidden rounded-lg">
          {scenes.map((scene, index) => (
            <button
              className={`relative min-w-8 overflow-hidden border border-black/10 bg-[#3f4a4d] text-[0.56rem] font-semibold text-white transition ${
                scene.id === selectedSceneId ? 'z-10 ring-2 ring-[#ef704f] ring-inset' : ''
              }`}
              key={scene.id}
              onClick={() => onSelect(scene.id)}
              style={{ width: `${Math.max(8, (scene.duration / totalDuration) * 100)}%` }}
              type="button"
            >
              {(() => {
                const asset = assets.find(item => item.id === scene.visuals?.[0]?.media_asset_id)

                return asset?.media_type === 'image' ? <SceneImage asset={asset} /> : null
              })()}
              <span className="absolute inset-x-1 bottom-1 truncate text-left [text-shadow:0_1px_3px_rgba(0,0,0,.8)]">
                {String(index + 1).padStart(2, '0')}
              </span>
            </button>
          ))}
        </div>
      </div>
      <div className="mt-1.5 grid grid-cols-[3.25rem_minmax(0,1fr)] items-center gap-2">
        <strong className="flex items-center gap-1 text-[0.58rem] text-[#6e655b]">
          <Mic className="size-3" /> 对白
        </strong>
        <div className="flex h-6 overflow-hidden rounded-md bg-[#cfd8c8] text-[0.52rem] text-[#52634f]">
          {scenes.map(scene => (
            <span
              className="grid place-items-center border-r border-white/45 px-2"
              key={scene.id}
              style={{ width: `${Math.max(8, (scene.duration / totalDuration) * 100)}%` }}
            >
              {scene.purpose || '镜头对白'}
            </span>
          ))}
        </div>
      </div>
      <div className="mt-1.5 grid grid-cols-[3.25rem_minmax(0,1fr)] items-center gap-2">
        <strong className="flex items-center gap-1 text-[0.58rem] text-[#6e655b]">
          <AudioLines className="size-3" /> 音乐
        </strong>
        <div className="flex h-6 items-center overflow-hidden rounded-md bg-[#c8d5e7] px-2 text-[0.52rem] text-[#536a86] [background-image:repeating-linear-gradient(90deg,transparent_0_5px,rgba(83,106,134,.3)_5px_7px,transparent_7px_10px)]">
          {Object.values(audio).some(Boolean) ? '音乐 / 旁白轨已绑定' : '声音轨待生成或选择'}
        </div>
      </div>
      <div className="mt-1.5 grid grid-cols-[3.25rem_minmax(0,1fr)] items-center gap-2">
        <strong className="flex items-center gap-1 text-[0.58rem] text-[#6e655b]">
          <FileImage className="size-3" /> 字幕
        </strong>
        <div className="flex h-6 items-center rounded-md bg-[#e8dcc6] px-2 text-[0.52rem] text-[#806f55]">
          {captions.length ? `${captions.length} 条字幕已进入时间线` : '字幕轨待生成'}
        </div>
      </div>
    </section>
  )
}

function SceneImage({ asset }: { asset: MediaAssetProjection }) {
  const [source, setSource] = useState('')
  useEffect(() => {
    if (!asset.playback_path) {
      return
    }

    let cancelled = false

    const reader = isRemoteGateway()
      ? gatewayMediaDataUrl(asset.playback_path)
      : window.hermesDesktop?.readFileDataUrl(asset.playback_path)

    void reader
      ?.then(value => {
        if (!cancelled) {
          setSource(value)
        }
      })
      .catch(() => undefined)

    return () => {
      cancelled = true
    }
  }, [asset.playback_path])

  return source ? <img alt={asset.name} className="size-full object-cover" src={source} /> : null
}

function ProductionStatus({ status }: { status: string }) {
  const labels: Record<string, string> = {
    approved: '已批准',
    completed: '已出片',
    failed: '需恢复',
    prepared: '待批准',
    running: '渲染中'
  }

  return (
    <span
      className={`rounded-full px-2 py-1 text-[0.58rem] font-semibold ${
        status === 'completed'
          ? 'bg-emerald-600/10 text-emerald-700'
          : status === 'failed'
            ? 'bg-red-600/10 text-red-700'
            : status === 'running'
              ? 'bg-amber-600/10 text-amber-700'
              : 'bg-(--ui-button-hover-background) text-(--ui-text-tertiary)'
      }`}
    >
      {status === 'running' ? <Clock className="mr-1 inline size-3" /> : null}
      {labels[status] || status}
    </span>
  )
}

function MetaChip({ label }: { label: string }) {
  return (
    <span className="rounded-lg border border-(--ui-stroke-tertiary) bg-(--ui-background)/65 px-2 py-1 text-[0.62rem] text-(--ui-text-tertiary)">
      {label}
    </span>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="shrink-0 text-(--ui-text-quaternary)">{label}</dt>
      <dd className="min-w-0 text-right text-(--ui-text-secondary)">{value}</dd>
    </div>
  )
}

export function ratioLabel(canvas: CanvasSpec): string {
  const ratio = canvas.width / canvas.height
  const preset = COMMON_RATIOS.find(item => Math.abs(ratio - item.width / item.height) < 0.015)

  if (preset) {
    return preset.label
  }

  const divisor = greatestCommonDivisor(canvas.width, canvas.height)

  return `${Math.round(canvas.width / divisor)}:${Math.round(canvas.height / divisor)}`
}

function greatestCommonDivisor(left: number, right: number): number {
  let a = Math.max(1, Math.round(left))
  let b = Math.max(1, Math.round(right))

  while (b) {
    ;[a, b] = [b, a % b]
  }

  return a
}

export function previewFrameStyle(canvas: CanvasSpec) {
  const ratio = canvas.width / canvas.height

  return {
    aspectRatio: `${canvas.width} / ${canvas.height}`,
    width: ratio >= 1.35 ? 'min(100%, 52rem)' : ratio >= 0.9 ? 'min(78%, 32rem)' : 'min(58%, 21rem)'
  }
}

export function directorLayoutForWidth(width: number): DirectorLayout {
  if (width < 760) {
    return 'stacked'
  }

  if (width < 1320) {
    return 'compact'
  }

  return 'wide'
}

function playbackUrl(path: string): string {
  return isRemoteGateway() ? mediaExternalUrl(path) : mediaStreamUrl(path)
}

function formatDuration(seconds: number): string {
  const safe = Math.max(0, Number(seconds || 0))
  const minutes = Math.floor(safe / 60)
  const remainder = safe - minutes * 60

  return minutes ? `${minutes}:${remainder.toFixed(1).padStart(4, '0')}` : `${remainder.toFixed(1)}s`
}

function rendererLabel(renderer?: string): string {
  return (
    {
      ffmpeg_timeline_v1: 'FFmpeg',
      hyperframes_scene_v1: 'HyperFrames',
      remotion_scene_v1: 'Remotion'
    }[renderer || ''] || '待生成'
  )
}

function fitLabel(fit?: string): string {
  return (
    {
      contain: '完整显示',
      cover: '铺满画面',
      fill: '拉伸填满'
    }[fit || ''] || '铺满画面'
  )
}

function inferDirectorStage(status: string, reviewStatus: string): DirectorStage {
  if (status === 'completed' || reviewStatus === 'accepted' || reviewStatus === 'changes_requested') {
    return 'final'
  }

  if (status === 'running') {
    return 'edit'
  }

  if (status === 'approved') {
    return 'dynamic'
  }

  if (status === 'prepared') {
    return 'storyboard'
  }

  return 'setup'
}

function stageLabel(stage: DirectorStage): string {
  return DIRECTOR_STAGES.find(item => item.id === stage)?.label || '设定'
}

function videoOperationStateLabel(state: MarketingOperationTask['state']): string {
  return {
    complete: '执行完成，工作台已同步最新结果。',
    error: '任务没有启动，当前项目没有被修改。',
    starting: '正在绑定当前项目、阶段和镜头。',
    waiting: 'Agent 正在等待你的决定，确认控件会留在当前经营界面。',
    working: 'Agent 正在后台执行，离开当前页面也不会中断。'
  }[state]
}

function assetMatchesTab(asset: MediaAssetProjection, tab: InspectorTab): boolean {
  const role = `${asset.role || ''} ${asset.name || ''}`.toLowerCase()

  if (tab === 'sound') {
    return asset.media_type === 'audio'
  }

  if (tab === 'characters') {
    return /character|avatar|person|人物|角色/.test(role)
  }

  if (tab === 'props') {
    return /prop|product|object|道具|产品/.test(role)
  }

  if (tab === 'scenes') {
    return asset.media_type !== 'audio' && /scene|background|location|场景|背景/.test(role)
  }

  return asset.media_type !== 'audio'
}

function setupAssetMatches(asset: MediaAssetProjection, category: SetupCategory): boolean {
  if (category !== 'scenes') {
    return assetMatchesTab(asset, category)
  }

  const role = `${asset.role || ''} ${asset.name || ''}`.toLowerCase()

  return (
    asset.media_type !== 'audio' &&
    !/character|avatar|person|portrait|host|人物|角色|主播|prop|product|object|道具|产品/.test(role)
  )
}

function pathLabel(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).pop() || path
}
