const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const test = require('node:test')

const desktopRoot = path.resolve(__dirname, '..')

test('all packaged desktop metadata uses the Marketing OS product identity', () => {
  const packageJson = JSON.parse(fs.readFileSync(path.join(desktopRoot, 'package.json'), 'utf8'))
  const build = packageJson.build

  assert.equal(build.appId, 'com.marketing-os.desktop')
  assert.equal(build.productName, 'Marketing OS')
  assert.equal(build.executableName, 'Marketing OS')
  assert.equal(build.win.legalTrademarks, 'Marketing OS')
  assert.equal(build.linux.maintainer, 'Marketing OS')
  assert.equal(build.nsis.shortcutName, 'Marketing OS')
  assert.equal(build.nsis.uninstallDisplayName, 'Marketing OS')
})

test('the Windows identity hook cannot stamp the upstream Hermes brand', () => {
  const stampSource = fs.readFileSync(path.join(desktopRoot, 'scripts', 'set-exe-identity.cjs'), 'utf8')
  const afterPackSource = fs.readFileSync(path.join(desktopRoot, 'scripts', 'after-pack.cjs'), 'utf8')

  assert.match(stampSource, /ProductName: 'Marketing OS'/)
  assert.match(stampSource, /FileDescription: 'Marketing OS'/)
  assert.doesNotMatch(stampSource, /ProductName: 'Hermes'/)
  assert.match(afterPackSource, /productFilename \|\| 'Marketing OS'/)
})
