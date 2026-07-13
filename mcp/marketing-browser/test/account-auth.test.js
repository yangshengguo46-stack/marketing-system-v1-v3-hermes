import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import test from 'node:test'

import {
  accountLoginTarget,
  evaluateAccountAuthentication,
  installAccountAuthTool,
  safePageLocation,
} from '../src/account-auth.js'

const require = createRequire(import.meta.url)
const { tools } = require('playwright-core/lib/coreBundle')

test('owns official creator login targets inside the account browser MCP', () => {
  assert.equal(accountLoginTarget('douyin'), 'https://creator.douyin.com/')
  assert.equal(accountLoginTarget('wechat_official'), 'https://mp.weixin.qq.com/')
  assert.equal(accountLoginTarget('zhihu'), 'https://www.zhihu.com/creator')
  assert.throws(() => accountLoginTarget('weibo'), /unsupported platform/)
})

test('verifies a real first-party Douyin login without returning cookie values', () => {
  const result = evaluateAccountAuthentication({
    platform: 'douyin',
    pageUrl: 'https://creator.douyin.com/creator-micro/home',
    cookies: [
      { name: 'sessionid', value: 'must-never-be-returned', domain: '.douyin.com' },
    ],
  })

  assert.equal(result.verified, true)
  assert.deepEqual(result.verification_basis, ['first_party_session_cookie_set'])
  assert.equal(JSON.stringify(result).includes('must-never-be-returned'), false)
  assert.equal(Object.hasOwn(result, 'cookies'), false)
})

test('rejects cross-platform cookies and incomplete authenticated state', () => {
  const crossPlatform = evaluateAccountAuthentication({
    platform: 'douyin',
    pageUrl: 'https://example.com/',
    cookies: [{ name: 'sessionid', value: 'x', domain: '.douyin.com' }],
  })
  const incomplete = evaluateAccountAuthentication({
    platform: 'bilibili',
    pageUrl: 'https://member.bilibili.com/platform/home',
    cookies: [{ name: 'SESSDATA', value: 'x', domain: '.bilibili.com' }],
  })

  assert.equal(crossPlatform.verified, false)
  assert.equal(crossPlatform.reason, 'current_page_is_outside_platform')
  assert.equal(incomplete.verified, false)
  assert.equal(incomplete.reason, 'authenticated_session_cookie_set_not_found')
})

test('removes login query parameters and fragments from returned page evidence', () => {
  assert.equal(
    safePageLocation('https://creator.douyin.com/login/callback?code=secret#token'),
    'https://creator.douyin.com/login/callback',
  )
  assert.equal(safePageLocation('not-a-url'), '')
})

test('starts login through the current Playwright MCP tab context', async t => {
  const previousLease = process.env.HERMES_MARKETING_ACCOUNT_LEASE
  t.after(() => {
    if (previousLease === undefined) delete process.env.HERMES_MARKETING_ACCOUNT_LEASE
    else process.env.HERMES_MARKETING_ACCOUNT_LEASE = previousLease
  })
  process.env.HERMES_MARKETING_ACCOUNT_LEASE = JSON.stringify({
    session_id: 'session-wechat',
    user_id: 'default',
    account_id: 'acct-wechat',
    platform: 'wechat_official',
    profile_key: 'wechat_official:acct-wechat',
    auth_state: 'unauthenticated',
  })
  installAccountAuthTool()
  const tool = tools.browserTools.find(item => item.schema?.name === 'browser_start_account_login')
  const calls = []
  const page = {
    goto: async (url, options) => calls.push({ url, options }),
    url: () => 'https://mp.weixin.qq.com/',
  }
  const results = []

  await tool.handle(
    { ensureTab: async () => ({ page }) },
    {},
    {
      addCode: code => calls.push({ code }),
      addResult: async (title, result, file) => results.push({ title, result, file }),
    },
  )

  assert.equal(calls[0].url, 'https://mp.weixin.qq.com/')
  assert.equal(calls[0].options.waitUntil, 'domcontentloaded')
  assert.equal(results.length, 1)
  assert.match(results[0].result, /marketing_account_login_started\.v1/)
  assert.deepEqual(results[0].file, { prefix: 'account-login-started', ext: 'json' })
})
