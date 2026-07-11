const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const { productUpdateStatus, rejectRawCoreUpdate } = require('./product-update-policy.cjs')

test('core updates only use the Marketing OS product release channel', () => {
  const status = productUpdateStatus('1.2.3')
  assert.equal(status.currentVersion, '1.2.3')
  assert.equal(status.updateChannel, 'marketing-os-product-release')
  assert.equal(status.canApply, false)
  assert.equal(status.updateAvailable, false)

  const rejected = rejectRawCoreUpdate('1.2.3')
  assert.equal(rejected.ok, false)
  assert.equal(rejected.error, 'marketing-os-product-update-required')
  assert.doesNotMatch(rejected.message, /请运行.*hermes update/i)
})

test('desktop update IPC cannot call the inherited raw Hermes updater', () => {
  const source = fs.readFileSync(path.join(__dirname, 'main.cjs'), 'utf8')
  const start = source.indexOf("ipcMain.handle('hermes:updates:check'")
  const end = source.indexOf("ipcMain.handle('hermes:version'", start)
  assert.notEqual(start, -1)
  assert.notEqual(end, -1)
  const bounded = source.slice(start, end)
  assert.match(bounded, /productUpdateStatus\(app\.getVersion\(\)\)/)
  assert.match(bounded, /rejectRawCoreUpdate\(app\.getVersion\(\)\)/)
  assert.doesNotMatch(bounded, /checkUpdates\(/)
  assert.doesNotMatch(bounded, /applyUpdates\(/)
  assert.doesNotMatch(bounded, /writeDesktopUpdateConfig/)
})
