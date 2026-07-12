// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { MarketingAccountSummary, MarketingPlatformSummary } from '@/store/marketing'

import { AccountConnectDialog } from './account-connect-dialog'

const platforms: MarketingPlatformSummary[] = [
  { content: ['video'], id: 'douyin', label: '抖音', region: 'china' },
  { content: ['article'], id: 'wechat_official', label: '微信公众号', region: 'china' }
]

afterEach(() => cleanup())

describe('AccountConnectDialog', () => {
  it('turns a platform choice into native registration, MCP login and verified account truth', async () => {
    const changed: MarketingAccountSummary[] = []

    const requestGatewayMock = vi.fn(async (method: string) => {
      if (method === 'marketing.accounts.register') {
        return {
          account: {
            auth_state: 'unauthenticated',
            id: 'acct-douyin',
            label: '抖音账号',
            platform: 'douyin',
            status: 'pending'
          }
        }
      }

      if (method === 'marketing.account.login.start') {
        return {
          account: {
            auth_state: 'unauthenticated',
            id: 'acct-douyin',
            label: '抖音账号',
            platform: 'douyin',
            status: 'pending'
          },
          browser_owner: 'marketing-browser-mcp',
          login_state: 'waiting_for_user'
        }
      }

      if (method === 'marketing.account.login.verify') {
        return {
          account: {
            auth_state: 'authenticated',
            id: 'acct-douyin',
            label: '抖音账号',
            platform: 'douyin',
            status: 'active'
          },
          verified: true
        }
      }

      throw new Error(`unexpected method: ${method}`)
    })

    const requestGateway = async <T,>(method: string): Promise<T> => (await requestGatewayMock(method)) as T

    render(
      <AccountConnectDialog
        onAccountChanged={account => changed.push(account)}
        onOpenChange={() => undefined}
        open
        platforms={platforms}
        requestGateway={requestGateway}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: /抖音/ }))
    expect(await screen.findByText('等待抖音登录')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '我已完成，立即检查' }))

    expect(await screen.findByText('登录验证成功')).toBeTruthy()
    expect(requestGatewayMock.mock.calls.map(call => call[0])).toEqual([
      'marketing.accounts.register',
      'marketing.account.login.start',
      'marketing.account.login.verify'
    ])
    await waitFor(() => expect(changed.at(-1)?.auth_state).toBe('authenticated'))
  })
})
