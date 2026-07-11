import assert from 'node:assert/strict'
import test from 'node:test'
import { resolveBrowserExecutable } from '../src/browser-runtime.js'

test('honors an explicit backend browser executable', () => {
  const result = resolveBrowserExecutable({
    env: { HERMES_BROWSER_EXECUTABLE: '/opt/browser/chrome' },
    platform: 'linux',
    exists: candidate => candidate === '/opt/browser/chrome',
  })
  assert.equal(result, '/opt/browser/chrome')
})

test('rejects a stale explicit browser path', () => {
  assert.throws(
    () => resolveBrowserExecutable({
      env: { HERMES_BROWSER_EXECUTABLE: '/missing/chrome' },
      platform: 'linux',
      exists: () => false,
    }),
    /does not exist/,
  )
})

test('discovers a system browser without involving Electron', () => {
  const expected = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
  const result = resolveBrowserExecutable({
    env: {},
    platform: 'darwin',
    exists: candidate => candidate === expected,
  })
  assert.equal(result, expected)
})

test('returns empty when the backend still needs a controlled browser install', () => {
  assert.equal(
    resolveBrowserExecutable({ env: { PATH: '' }, platform: 'linux', exists: () => false }),
    '',
  )
})
