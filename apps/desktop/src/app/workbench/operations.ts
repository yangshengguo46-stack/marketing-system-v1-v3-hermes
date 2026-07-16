export type MarketingOperationKind =
  | 'account.analyze'
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

export interface PreparedMarketingOperation {
  account_id: string
  kind: MarketingOperationKind
  operation: Record<string, unknown>
  prompt: string
  title: string
  visible_text: string
}

export type StartMarketingOperation = (intent: MarketingOperationIntent) => void

type RequestGateway = <T>(method: string, params?: Record<string, unknown>) => Promise<T>

export function prepareMarketingOperation(
  requestGateway: RequestGateway,
  intent: MarketingOperationIntent
): Promise<PreparedMarketingOperation> {
  return requestGateway<PreparedMarketingOperation>('marketing.operation.prepare', {
    account_id: intent.accountId,
    asset_id: intent.assetId,
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
  })
}
