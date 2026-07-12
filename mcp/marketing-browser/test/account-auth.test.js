import assert from 'node:assert/strict'
import test from 'node:test'

import { evaluateAccountAuthentication, safePageLocation } from '../src/account-auth.js'

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
