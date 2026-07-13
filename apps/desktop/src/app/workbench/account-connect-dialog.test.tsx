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

  it('puts WeChat Official Account first and starts evidence-backed diagnosis after login', async () => {
    const analyze = vi.fn()

    const requestGateway = async <T,>(method: string): Promise<T> => {
      const account = {
        auth_state: method === 'marketing.account.login.verify' ? 'authenticated' : 'unauthenticated',
        id: 'acct-wechat',
        label: '微信公众号账号',
        platform: 'wechat_official',
        status: method === 'marketing.account.login.verify' ? 'active' : 'pending'
      }

      if (method === 'marketing.accounts.register') {
        return { account } as T
      }

      if (method === 'marketing.account.login.start') {
        return { account, browser_owner: 'marketing-browser-mcp', login_state: 'waiting_for_user' } as T
      }

      if (method === 'marketing.account.login.verify') {
        return { account, verified: true } as T
      }

      throw new Error(`unexpected method: ${method}`)
    }

    render(
      <AccountConnectDialog
        onAccountChanged={() => undefined}
        onAnalyzeAccount={analyze}
        onOpenChange={() => undefined}
        open
        platforms={platforms}
        requestGateway={requestGateway}
      />
    )

    const choices = screen.getAllByRole('button')
    expect(choices[0].textContent).toContain('微信公众号')
    fireEvent.click(screen.getByRole('button', { name: /微信公众号/ }))
    fireEvent.click(await screen.findByRole('button', { name: '我已完成，立即检查' }))
    fireEvent.click(await screen.findByRole('button', { name: '同步文章并评分' }))
    expect(analyze).toHaveBeenCalledWith(expect.objectContaining({ id: 'acct-wechat' }))
  })
})
