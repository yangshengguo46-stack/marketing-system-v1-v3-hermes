import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { selectMarketingAccount } from '@/store/marketing'

import { MaterialLibraryView } from './material-library-view'

const desktopWindow = window as unknown as { hermesDesktop?: Window['hermesDesktop'] }
const initialHermesDesktop = desktopWindow.hermesDesktop

afterEach(() => {
  cleanup()
  selectMarketingAccount('prospect_default')

  if (initialHermesDesktop) {
    desktopWindow.hermesDesktop = initialHermesDesktop
  } else {
    delete desktopWindow.hermesDesktop
  }
})

describe('material library view', () => {
  const onStartOperation = vi.fn()

  it('uses the native picker and imports through the Hermes asset owner after rights confirmation', async () => {
    selectMarketingAccount('acct-1')
    const selectPaths = vi.fn().mockResolvedValue(['/tmp/campaign/shot.mp4'])
    desktopWindow.hermesDesktop = {
      getPathForFile: vi.fn(),
      selectPaths
    } as unknown as Window['hermesDesktop']

    let imported = false
    const calls = vi.fn()

    const requestGateway = async <T,>(method: string, params?: Record<string, unknown>): Promise<T> => {
      calls(method, params)

      if (method === 'marketing.assets.import_paths') {
        imported = true

        return { imported: 1, reused: 0, skipped: [] } as T
      }

      if (method === 'marketing.assets.list') {
        return {
          assets: imported
            ? [
                {
                  account_id: 'acct-1',
                  id: 'media-1',
                  media_type: 'video',
                  name: 'campaign-shot',
                  rights_status: 'user_confirmed',
                  role: 'other',
                  size_bytes: 2048,
                  source_type: 'user_upload',
                  updated_at: '2026-07-15T00:00:00Z'
                }
              ]
            : []
        } as T
      }

      return {} as T
    }

    render(<MaterialLibraryView onStartOperation={onStartOperation} requestGateway={requestGateway} />)
    fireEvent.click(await screen.findByRole('button', { name: /本地库/ }))
    expect(await screen.findByLabelText('导入素材')).toBeTruthy()
    fireEvent.click(await screen.findByLabelText(/我确认拥有这些素材的使用权/))
    fireEvent.click(screen.getByRole('button', { name: '选择文件' }))

    await waitFor(() =>
      expect(calls).toHaveBeenCalledWith('marketing.assets.import_paths', {
        account_id: 'acct-1',
        paths: ['/tmp/campaign/shot.mp4'],
        rights_confirmed: true
      })
    )
    expect(selectPaths).toHaveBeenCalledWith({
      directories: false,
      multiple: true,
      title: '导入图片、视频或音频'
    })
    expect(await screen.findByText('campaign-shot')).toBeTruthy()
    expect(screen.getByText(/用户确认/)).toBeTruthy()
    expect(screen.getByText('账号素材')).toBeTruthy()
  })

  it('keeps the Volcengine cloud lane honest until the provider is connected', async () => {
    const requestGateway = async <T,>(): Promise<T> => ({ assets: [] }) as T
    render(<MaterialLibraryView onStartOperation={onStartOperation} requestGateway={requestGateway} />)

    fireEvent.click(await screen.findByRole('button', { name: '云端素材' }))
    expect(screen.getByText('云端素材即将开放')).toBeTruthy()
    expect(screen.getByText(/桌面、飞书或微信/)).toBeTruthy()
  })

  it('shows temporary lifecycle and promotes a selected asset to the local library', async () => {
    selectMarketingAccount('acct-1')
    const calls = vi.fn()
    let promoted = false

    const requestGateway = async <T,>(method: string, params?: Record<string, unknown>): Promise<T> => {
      calls(method, params)

      if (method === 'marketing.assets.promote') {
        promoted = true

        return {} as T
      }

      return {
        assets: [
          {
            account_id: 'acct-1',
            expires_at: promoted ? null : '2099-07-22T00:00:00Z',
            id: 'media-temp-1',
            media_type: 'video',
            name: '城市空镜',
            rights_status: 'licensed',
            role: 'broll',
            size_bytes: 8192,
            source_type: 'licensed_provider',
            storage_tier: promoted ? 'library' : 'temporary',
            updated_at: '2026-07-15T00:00:00Z'
          }
        ]
      } as T
    }

    render(<MaterialLibraryView onStartOperation={onStartOperation} requestGateway={requestGateway} />)
    expect(await screen.findByText('城市空镜')).toBeTruthy()
    expect(screen.getByText('未使用的素材 7 天后自动清理')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '保留 城市空镜' }))

    await waitFor(() =>
      expect(calls).toHaveBeenCalledWith('marketing.assets.promote', {
        account_id: 'acct-1',
        asset_id: 'media-temp-1',
        target_tier: 'library'
      })
    )
    expect(await screen.findByText('“城市空镜”已保留到本地素材库。')).toBeTruthy()
  })
})
