import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '@/i18n/context'
import { $marketingOperationTasks, selectMarketingAccount } from '@/store/marketing'

import { AccountCenterView, ContentFactoryView, ManagedView, VideoCreationView } from './business-surfaces'
import { directorLayoutForWidth } from './video-production-workbench'

afterEach(() => {
  cleanup()
  $marketingOperationTasks.set([])
  window.localStorage.clear()
  Reflect.deleteProperty(window, 'hermesDesktop')
})

describe('Marketing OS business surfaces', () => {
  const onStartOperation = vi.fn()

  const requestGateway = async <T,>(method: string): Promise<T> => {
    let result: unknown = {}

    if (method === 'marketing.accounts.list') {
      result = { accounts: [], source: 'hermes_state', total: 0 }
    }

    if (method === 'marketing.accounts.platforms') {
      result = { platforms: [], total: 0 }
    }

    if (method === 'marketing.content.assets.list') {
      result = { assets: [] }
    }

    if (method === 'marketing.learning.candidates.list') {
      result = { candidates: [], total: 0 }
    }

    return result as T
  }

  it('adapts the director layout to the actual workbench width', () => {
    expect(directorLayoutForWidth(1500)).toBe('wide')
    expect(directorLayoutForWidth(1000)).toBe('compact')
    expect(directorLayoutForWidth(640)).toBe('stacked')
  })

  it('renders the product-owned business destinations without an internal high-end video lane', () => {
    selectMarketingAccount('prospect_default')

    const { rerender } = render(<ContentFactoryView onOpenArticle={vi.fn()} onOpenVideo={vi.fn()} />)

    expect(screen.getByRole('heading', { name: '内容工厂' })).toBeTruthy()
    expect(screen.getByText('图文创作')).toBeTruthy()
    expect(screen.getByText('视频创作')).toBeTruthy()
    expect(screen.queryByText('素材中枢')).toBeNull()
    expect(screen.queryByText('最近内容')).toBeNull()
    expect(screen.queryByText('高阶视频')).toBeNull()
    expect(screen.queryByText('数字人视频')).toBeNull()

    rerender(<AccountCenterView onStartOperation={onStartOperation} requestGateway={requestGateway} />)
    expect(screen.getByText('账号管理')).toBeTruthy()

    rerender(<ManagedView onStartOperation={onStartOperation} requestGateway={requestGateway} />)
    expect(screen.getByText('托管')).toBeTruthy()
  })

  it('opens article creation as a product workbench instead of a conversation', () => {
    selectMarketingAccount('prospect_default')
    const onOpenArticle = vi.fn()

    render(<ContentFactoryView onOpenArticle={onOpenArticle} onOpenVideo={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /图文创作/ }))

    expect(onOpenArticle).toHaveBeenCalledOnce()
    expect(onStartOperation).not.toHaveBeenCalled()
  })

  it('keeps content creation to two focused entrances without a redundant generic action', () => {
    selectMarketingAccount('prospect_default')
    const onOpenArticle = vi.fn()
    const onOpenVideo = vi.fn()

    render(<ContentFactoryView onOpenArticle={onOpenArticle} onOpenVideo={onOpenVideo} />)

    fireEvent.click(screen.getByRole('button', { name: /图文创作/ }))
    fireEvent.click(screen.getByRole('button', { name: /视频创作/ }))

    expect(onOpenArticle).toHaveBeenCalledOnce()
    expect(onOpenVideo).toHaveBeenCalledOnce()
    expect(screen.queryByRole('button', { name: '开始创作' })).toBeNull()
  })

  it('returns an authenticated account to its persistent workbench context', async () => {
    selectMarketingAccount('prospect_default')
    const startOperation = vi.fn()
    const onOpenWorkbench = vi.fn()

    const accountRequestGateway = async <T,>(method: string): Promise<T> => {
      if (method === 'marketing.accounts.list') {
        return {
          accounts: [
            {
              auth_state: 'authenticated',
              id: 'acct-wechat',
              label: '雨夜唱片店',
              platform: 'wechat_official'
            }
          ],
          source: 'hermes_state',
          total: 1
        } as T
      }

      if (method === 'marketing.accounts.platforms') {
        return { platforms: [], total: 0 } as T
      }

      if (method === 'marketing.learning.candidates.list') {
        return { candidates: [], total: 0 } as T
      }

      return {} as T
    }

    const { rerender } = render(
      <AccountCenterView
        onOpenWorkbench={onOpenWorkbench}
        onStartOperation={startOperation}
        requestGateway={accountRequestGateway}
      />
    )

    fireEvent.click(await screen.findByRole('button', { name: '进入经营' }))
    expect(onOpenWorkbench).toHaveBeenCalledOnce()
    expect(startOperation).not.toHaveBeenCalled()

    rerender(<ManagedView onStartOperation={startOperation} requestGateway={accountRequestGateway} />)
    fireEvent.click(screen.getByRole('button', { name: '设置托管' }))
    expect(startOperation).toHaveBeenLastCalledWith({
      accountId: 'acct-wechat',
      kind: 'autopilot.configure'
    })
  })

  it('keeps a new video in the setup workspace and submits the brief to a background Agent', async () => {
    selectMarketingAccount('acct-1')
    const calls = vi.fn()
    const onBack = vi.fn()
    const startOperation = vi.fn(() => 'video-setup-task')
    const selectPaths = vi.fn().mockResolvedValue(['/tmp/rain-night-script.md'])

    Object.defineProperty(window, 'hermesDesktop', {
      configurable: true,
      value: { getPathForFile: vi.fn(), selectPaths }
    })

    const assets = [
      {
        id: 'character-linxi',
        media_type: 'image',
        name: '主角林夕',
        rights_status: 'owned',
        role: 'character',
        size_bytes: 1024,
        source_type: 'user_upload'
      },
      {
        id: 'voice-warm',
        media_type: 'audio',
        name: '温暖女声',
        rights_status: 'licensed',
        role: 'voice',
        size_bytes: 2048,
        source_type: 'licensed_provider'
      },
      {
        id: 'scene-rain',
        media_type: 'image',
        name: '雨夜街道',
        rights_status: 'owned',
        role: 'scene',
        size_bytes: 4096,
        source_type: 'user_upload'
      }
    ]

    const requestGateway = async <T,>(method: string, params?: Record<string, unknown>): Promise<T> => {
      calls(method, params)

      if (method === 'marketing.video.productions.list') {
        return { productions: [], total: 0 } as T
      }

      if (method === 'marketing.assets.list') {
        return { assets } as T
      }

      return {} as T
    }

    render(
      <I18nProvider configClient={null} initialLocale="zh">
        <VideoCreationView onBack={onBack} onStartOperation={startOperation} requestGateway={requestGateway} />
      </I18nProvider>
    )

    expect(screen.queryByLabelText('人物库')).toBeNull()
    expect(screen.queryByText('DIRECTOR CANVAS')).toBeNull()
    expect(screen.queryByText('先定义作品，再生成画面')).toBeNull()
    expect(screen.queryByText('开始一条新作品')).toBeNull()
    expect(screen.queryByRole('button', { name: '开始创作' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '返回' }))
    expect(onBack).toHaveBeenCalledOnce()
    expect(screen.getByLabelText('视频设定素材')).toBeTruthy()
    expect(screen.getByRole('button', { name: '人物' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '声音' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '场景' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '道具' })).toBeTruthy()
    expect(screen.queryByText('AI 生成')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '折叠设定素材栏' }))
    expect(screen.getByRole('button', { name: '展开设定素材栏' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: '人物' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '展开设定素材栏' }))

    fireEvent.click(screen.getByRole('button', { name: '人物' }))
    const characterLibrary = await screen.findByLabelText('人物库')
    expect(characterLibrary.querySelector('button')?.getAttribute('aria-label')).toBe('交给 AI 生成人物')
    fireEvent.click(await screen.findByRole('button', { name: '选择人物 主角林夕' }))
    expect(screen.queryByText('放大预览')).toBeNull()
    expect(screen.getByRole('button', { name: '展开设定素材栏' })).toBeTruthy()
    expect(screen.queryByLabelText('人物库')).toBeNull()
    expect(screen.queryByRole('button', { name: '交给 AI 生成人物' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '展开设定素材栏' }))
    expect(screen.queryByLabelText('人物库')).toBeNull()
    expect(screen.getByLabelText('人物已选择 主角林夕')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '声音' }))
    expect(await screen.findByLabelText('声音库')).toBeTruthy()
    fireEvent.click(await screen.findByRole('button', { name: '选择声音 温暖女声' }))
    expect(screen.getByRole('button', { name: '展开设定素材栏' })).toBeTruthy()
    expect(screen.queryByLabelText('声音库')).toBeNull()

    fireEvent.change(screen.getByLabelText('视频文案'), {
      target: { value: '雨夜里，一个女孩走进旧唱片店。' }
    })
    fireEvent.pointerDown(screen.getByRole('button', { name: '添加素材' }), { button: 0, ctrlKey: false })
    expect(await screen.findByRole('menuitem', { name: '文件…' })).toBeTruthy()
    expect(screen.getByRole('menuitem', { name: '文件夹…' })).toBeTruthy()
    expect(screen.getByRole('menuitem', { name: '图片…' })).toBeTruthy()
    fireEvent.click(screen.getByRole('menuitem', { name: '文件…' }))
    expect(await screen.findByText('rain-night-script.md')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '开始拆分' }))

    await waitFor(() =>
      expect(startOperation).toHaveBeenCalledWith({
        accountId: 'acct-1',
        attachments: [
          {
            dataUrl: undefined,
            name: 'rain-night-script.md',
            path: '/tmp/rain-night-script.md'
          }
        ],
        kind: 'video.setup',
        note: '雨夜里，一个女孩走进旧唱片店。',
        selections: {
          characters: 'character-linxi',
          props: '',
          scenes: '',
          sound: 'voice-warm'
        }
      })
    )
    expect(calls).not.toHaveBeenCalledWith('session.create', expect.anything())
    expect(calls).not.toHaveBeenCalledWith('prompt.submit', expect.anything())
    expect(await screen.findByText(/正在拆分文案并创建分镜/)).toBeTruthy()
  }, 15_000)

  it('renders a real ratio-aware video workbench and records the final review', async () => {
    selectMarketingAccount('acct-1')
    const calls = vi.fn()
    const startOperation = vi.fn(() => 'video-operation-task')

    const summary = {
      canvas: { fps: 30, height: 1080, width: 1920 },
      created_at: '2026-07-15T00:00:00+00:00',
      duration: 12,
      final_video_asset_id: 'media-final',
      human_review_status: 'pending',
      id: 'video-production-1',
      output_asset_id: 'asset-video-output',
      renderers: ['remotion_scene_v1', 'hyperframes_scene_v1'],
      scene_count: 2,
      settled_at: '2026-07-15T00:01:00+00:00',
      source_asset_id: 'asset-video-source',
      status: 'completed',
      title: '横屏品牌解释视频',
      updated_at: '2026-07-15T00:01:00+00:00'
    }

    const projection = {
      media_assets: [
        {
          id: 'media-scene',
          media_type: 'image',
          name: '品牌主视觉',
          rights_status: 'licensed',
          role: 'broll',
          size_bytes: 1024,
          source_type: 'licensed_provider'
        }
      ],
      output_asset: {
        human_review_status: 'pending',
        id: 'asset-video-output',
        title: '横屏品牌解释视频',
        version: 2
      },
      production: {
        final_video_asset_id: 'media-final',
        id: 'video-production-1',
        output_asset_id: 'asset-video-output',
        receipt: {
          summary: {
            technical: {
              quality_assurance: {
                checks: [
                  { id: 'technical_delivery', label: '技术规格', severity: 'observation', status: 'pass' },
                  { id: 'black_frames', label: '异常黑场', severity: 'observation', status: 'pass' },
                  { id: 'frozen_frames', label: '异常冻结', severity: 'observation', status: 'pass' },
                  { id: 'audio_loudness', label: '声音响度', severity: 'observation', status: 'not_applicable' }
                ],
                disposition: 'ready',
                version: 'marketing.media_quality.v1'
              }
            }
          }
        },
        render_plan: {
          executable: true,
          scenes: [
            { fallback_used: false, renderer: 'remotion_scene_v1', scene_id: 'scene-hook', status: 'ready' },
            { fallback_used: false, renderer: 'hyperframes_scene_v1', scene_id: 'scene-proof', status: 'ready' }
          ]
        },
        status: 'completed',
        video_ir: {
          audio: {},
          canvas: { fps: 30, height: 1080, width: 1920 },
          captions: [],
          scenes: [
            {
              duration: 5,
              id: 'scene-hook',
              motion_intent: ['kinetic_typography'],
              purpose: '结果先行',
              text: [{ role: 'headline', text: '先看最终效果' }],
              visuals: [{ fit: 'cover', media_asset_id: 'media-scene' }]
            },
            {
              duration: 7,
              id: 'scene-proof',
              motion_intent: ['html_css_motion'],
              purpose: '方法拆解',
              text: [{ role: 'headline', text: '再拆解方法' }],
              visuals: [{ fit: 'contain', media_asset_id: 'media-scene' }]
            }
          ]
        }
      },
      source_asset: { id: 'asset-video-source', title: '横屏品牌解释视频', version: 1 },
      summary
    }

    const requestGateway = async <T,>(method: string, params?: Record<string, unknown>): Promise<T> => {
      calls(method, params)

      if (method === 'marketing.content.assets.list') {
        return { assets: [] } as T
      }

      if (method === 'marketing.video.productions.list') {
        return { productions: [summary], total: 1 } as T
      }

      if (method === 'marketing.video.production.get') {
        return projection as T
      }

      if (method === 'marketing.audio.catalog') {
        return {
          available: true,
          configured_voice: 'zh_female_vv_uranus_bigtts',
          default_model: 'seed-tts-2.0',
          display_name: 'Volcengine Doubao Speech 2.0',
          metadata: {
            official_voice_count: 325,
            service_families: [{ active: true, id: 'seed-tts-2.0', name: '语音合成 2.0' }]
          },
          provider: 'volcengine-speech',
          voices: [
            { display: 'Vivi 2.0', gender: 'female', id: 'zh_female_vv_uranus_bigtts', language: 'zh-CN' },
            { display: '小何 2.0', gender: 'female', id: 'zh_female_xiaohe_uranus_bigtts', language: 'zh-CN' }
          ]
        } as T
      }

      if (method === 'marketing.audio.voice.set') {
        return {
          available: true,
          configured_voice: params?.voice_id,
          default_model: 'seed-tts-2.0',
          display_name: 'Volcengine Doubao Speech 2.0',
          metadata: { official_voice_count: 325 },
          provider: 'volcengine-speech',
          voices: [
            { display: 'Vivi 2.0', id: 'zh_female_vv_uranus_bigtts' },
            { display: '小何 2.0', id: 'zh_female_xiaohe_uranus_bigtts' }
          ]
        } as T
      }

      if (method === 'marketing.content.asset.review') {
        return { asset: { ...projection.output_asset, human_review_status: params?.decision } } as T
      }

      return {} as T
    }

    render(<VideoCreationView onStartOperation={startOperation} requestGateway={requestGateway} />)

    expect(await screen.findByRole('combobox', { name: '视频项目' })).toBeTruthy()
    await waitFor(() =>
      expect(document.querySelector('[data-director-layout]')?.getAttribute('data-director-layout')).toBe('stacked')
    )
    expect(screen.getByLabelText('视频制作阶段')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '分镜' }))
    expect(screen.queryByLabelText('人物库')).toBeNull()
    expect(screen.queryByLabelText('声音库')).toBeNull()
    expect(screen.queryByRole('button', { name: /交给 AI 生成/ })).toBeNull()
    expect(screen.getByText('镜头列表')).toBeTruthy()
    expect(screen.getByText('项目参考素材')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '折叠项目素材栏' }))
    expect(screen.queryByText('项目参考素材')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '展开项目素材栏' }))
    fireEvent.click(screen.getByRole('button', { name: '折叠镜头列表' }))
    expect(screen.queryByText('镜头列表')).toBeNull()
    expect(screen.getByRole('button', { name: '展开镜头列表' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '展开镜头列表' }))
    expect(screen.getByText('版本')).toBeTruthy()
    expect(screen.getByRole('button', { name: '生成新版本' })).toBeTruthy()
    expect(screen.getByText('项目参考素材')).toBeTruthy()
    expect(screen.getByText('对白')).toBeTruthy()
    expect(screen.getByText('音乐')).toBeTruthy()
    expect((await screen.findAllByText('结果先行')).length).toBe(2)
    expect(screen.getAllByText('16:9').length).toBeGreaterThan(0)
    expect(screen.getByText('1920×1080')).toBeTruthy()
    expect(screen.getAllByText('品牌主视觉').length).toBe(2)
    fireEvent.click(screen.getByRole('button', { name: '场景' }))
    expect(screen.getByText('Remotion')).toBeTruthy()
    expect(screen.getByText('自动质检通过')).toBeTruthy()
    expect(screen.getByText('无需检查')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '声音' }))
    const soundLibrary = screen.getByRole('group', { name: '声音素材库' })
    expect(await within(soundLibrary).findByText('火山声音库')).toBeTruthy()
    expect(within(soundLibrary).getByText('常驻已接通')).toBeTruthy()
    expect(screen.getAllByText('火山声音库')).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: /小何 2.0/ }))
    await waitFor(() =>
      expect(calls).toHaveBeenCalledWith('marketing.audio.voice.set', {
        confirmed: true,
        voice_id: 'zh_female_xiaohe_uranus_bigtts'
      })
    )
    expect(await screen.findByText('小何 2.0 · seed-tts-2.0')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '生成新版本' }))
    expect(startOperation).toHaveBeenCalledWith({
      accountId: 'acct-1',
      kind: 'video.version.generate',
      productionId: 'video-production-1',
      sceneId: 'scene-hook',
      title: '横屏品牌解释视频'
    })
    expect(calls).not.toHaveBeenCalledWith('marketing.operation.prepare', expect.anything())
    expect(calls).not.toHaveBeenCalledWith('prompt.submit', expect.anything())

    fireEvent.click(screen.getByRole('button', { name: '确认成片' }))
    await waitFor(() =>
      expect(calls).toHaveBeenCalledWith('marketing.content.asset.review', {
        account_id: 'acct-1',
        asset_id: 'asset-video-output',
        confirmed: true,
        decision: 'accepted',
        note: ''
      })
    )
    expect(await screen.findByText(/当前成片已经确认并归入草稿箱/)).toBeTruthy()
    expect(screen.getByRole('button', { name: '前往草稿箱' })).toBeTruthy()
  }, 15_000)
})
