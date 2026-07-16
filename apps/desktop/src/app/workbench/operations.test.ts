import { describe, expect, it, vi } from 'vitest'

import { prepareMarketingOperation } from './operations'

describe('marketing operation entrypoints', () => {
  it('sends object and stage identity instead of a renderer-owned prompt', async () => {
    const request = vi.fn(async () => ({
      account_id: 'acct-1',
      kind: 'video.stage.modify',
      operation: {},
      prompt: 'backend-owned execution contract',
      title: '修改分镜',
      visible_text: '修改「雨夜唱片店」的分镜阶段'
    }))

    const requestGateway = request as unknown as Parameters<typeof prepareMarketingOperation>[0]

    const result = await prepareMarketingOperation(requestGateway, {
      accountId: 'acct-1',
      kind: 'video.stage.modify',
      note: '镜头慢一点',
      productionId: 'production-17',
      sceneId: 'scene-02',
      stage: 'storyboard',
      title: '雨夜唱片店'
    })

    expect(request).toHaveBeenCalledWith('marketing.operation.prepare', {
      account_id: 'acct-1',
      asset_id: undefined,
      document_refs: undefined,
      kind: 'video.stage.modify',
      media_asset_id: undefined,
      note: '镜头慢一点',
      production_id: 'production-17',
      scene_id: 'scene-02',
      selections: undefined,
      stage: 'storyboard',
      target_id: undefined,
      title: '雨夜唱片店',
      version: undefined
    })
    expect(result.prompt).toBe('backend-owned execution contract')
  })
})
