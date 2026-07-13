import assert from 'node:assert/strict'
import test from 'node:test'
import { playwrightToolSchemas } from '../src/schema-server.js'

test('discovers the pinned Playwright MCP surface without opening a browser', () => {
  const schemas = playwrightToolSchemas()
  const names = new Set(schemas.map(schema => schema.name))
  assert.equal(schemas.length, 57)
  assert.ok(schemas.some(schema => schema.name === 'browser_start_account_login'))
  assert.ok(schemas.some(schema => schema.name === 'browser_verify_account_login'))
  assert.ok(schemas.some(schema => schema.name === 'browser_extract_short_video_signals'))
  assert.ok(schemas.some(schema => schema.name === 'browser_collect_douyin_portfolio'))
  assert.ok(schemas.some(schema => schema.name === 'browser_collect_wechat_official_portfolio'))
  assert.equal(names.has('browser_snapshot'), true)
  assert.equal(names.has('browser_navigate'), true)
  assert.equal(names.has('browser_take_screenshot'), true)
  assert.equal(names.has('browser_network_requests'), true)
})
