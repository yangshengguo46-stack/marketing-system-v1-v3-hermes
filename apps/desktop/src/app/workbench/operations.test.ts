import { describe, expect, it, vi } from 'vitest'

import { launchMarketingOperation } from './operations'

describe('marketing operation entrypoints', () => {
  it('sends object and stage identity instead of a renderer-owned prompt', async () => {
    const request = vi.fn(async () => ({
      account_id: 'acct-1',
      kind: 'video.stage.modify',
      operation_id: 'marketing-operation-1',
      state: 'working',
      title: '修改分镜',
      visible_text: '修改「雨夜唱片店」的分镜阶段'
    }))

    const requestGateway = request as unknown as Parameters<typeof launchMarketingOperation>[0]

    const result = await launchMarketingOperation(requestGateway, {
      accountId: 'acct-1',
      kind: 'video.stage.modify',
      note: '镜头慢一点',
      productionId: 'production-17',
      sceneId: 'scene-02',
      stage: 'storyboard',
      title: '雨夜唱片店'
    })

    expect(request).toHaveBeenCalledWith('marketing.operation.start', {
      account_id: 'acct-1',
      asset_id: undefined,
      attachments: undefined,
      business_goal: undefined,
      constraints: undefined,
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
    expect(result).not.toHaveProperty('prompt')
  })
})
