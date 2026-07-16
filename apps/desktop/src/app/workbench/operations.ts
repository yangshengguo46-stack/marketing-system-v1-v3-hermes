export type MarketingOperationKind =
  | 'account.analyze'
  | 'account.bootstrap'
  | 'account.model.review'
  | 'account.prioritize'
  | 'autopilot.configure'
  | 'content.article.start'
  | 'content.resume'
  | 'content.revise'
  | 'learning.review'
  | 'materials.cloud.status'
  | 'video.asset.select'
  | 'video.autopilot'
  | 'video.export'
  | 'video.revision'
  | 'video.scene.add'
  | 'video.setup'
  | 'video.stage.confirm'
  | 'video.stage.modify'
  | 'video.version.generate'

export interface MarketingOperationIntent {
  accountId: string
  assetId?: string
  attachments?: MarketingOperationAttachment[]
  businessGoal?: string
  constraints?: Record<string, unknown>
  documentRefs?: string[]
  kind: MarketingOperationKind
  mediaAssetId?: string
  note?: string
  productionId?: string
  sceneId?: string
  selections?: Partial<Record<'characters' | 'props' | 'scenes' | 'sound', string>>
  stage?: 'dynamic' | 'edit' | 'final' | 'setup' | 'storyboard'
  targetId?: string
  title?: string
  version?: number
}

export interface MarketingOperationAttachment {
  dataUrl?: string
  name: string
  path: string
}

export interface MarketingOperationResultRef {
  object_id: string
  object_type: 'account' | 'content_asset' | 'strategy_project' | 'video_production' | string
  title: string
}

export interface StartedMarketingOperation {
  account_id: string
  kind: MarketingOperationKind
  operation_id: string
  state: 'working'
  title: string
  visible_text: string
}

export interface MarketingOperationStatus extends Omit<StartedMarketingOperation, 'state'> {
  error?: string
  results: MarketingOperationResultRef[]
  state: 'complete' | 'error' | 'waiting' | 'working'
}

export type StartMarketingOperation = (intent: MarketingOperationIntent) => string

type RequestGateway = <T>(method: string, params?: Record<string, unknown>) => Promise<T>

function operationParams(intent: MarketingOperationIntent): Record<string, unknown> {
  return {
    account_id: intent.accountId,
    asset_id: intent.assetId,
    attachments: intent.attachments,
    business_goal: intent.businessGoal,
    constraints: intent.constraints,
    document_refs: intent.documentRefs,
    kind: intent.kind,
    media_asset_id: intent.mediaAssetId,
    note: intent.note,
    production_id: intent.productionId,
    scene_id: intent.sceneId,
    selections: intent.selections,
    stage: intent.stage,
    target_id: intent.targetId,
    title: intent.title,
    version: intent.version
  }
}

export function launchMarketingOperation(
  requestGateway: RequestGateway,
  intent: MarketingOperationIntent
): Promise<StartedMarketingOperation> {
  return requestGateway<StartedMarketingOperation>('marketing.operation.start', operationParams(intent))
}

export function readMarketingOperationStatus(
  requestGateway: RequestGateway,
  operationId: string
): Promise<MarketingOperationStatus> {
  return requestGateway<MarketingOperationStatus>('marketing.operation.status', { operation_id: operationId })
}
