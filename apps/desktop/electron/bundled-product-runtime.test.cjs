const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const { resolveBundledProductRuntime } = require('./bundled-product-runtime.cjs')

function fixture() {
  const resources = fs.mkdtempSync(path.join(os.tmpdir(), 'marketing-os-bundled-runtime-'))
  const root = path.join(resources, 'marketing-os-runtime')
  const python = path.join(root, 'python', 'bin', 'python3')
  const agent = path.join(root, 'agent', 'hermes_cli')
  const browserMcp = path.join(root, 'agent', 'mcp', 'marketing-browser', 'src')
  const nodeModules = path.join(root, 'agent', 'node_modules')
  const playwrightBrowsers = path.join(root, 'playwright-browsers')
  const playwrightBrowserExecutable = path.join(playwrightBrowsers, 'chromium-1234', 'chrome')
  const sitePackages = path.join(root, 'site-packages')
  fs.mkdirSync(path.dirname(python), { recursive: true })
  fs.mkdirSync(agent, { recursive: true })
  fs.mkdirSync(browserMcp, { recursive: true })
  fs.mkdirSync(nodeModules, { recursive: true })
  fs.mkdirSync(playwrightBrowsers, { recursive: true })
  fs.mkdirSync(sitePackages, { recursive: true })
  fs.writeFileSync(python, '')
  fs.writeFileSync(path.join(agent, 'main.py'), '')
  fs.writeFileSync(path.join(browserMcp, 'server.js'), '')
  fs.mkdirSync(path.dirname(playwrightBrowserExecutable), { recursive: true })
  fs.writeFileSync(playwrightBrowserExecutable, '')
  return { resources, root }
}

test('resolves the packaged runtime for the current platform and architecture', () => {
  const { resources, root } = fixture()
  fs.writeFileSync(
    path.join(root, 'runtime-manifest.json'),
    JSON.stringify({
      schemaVersion: 1,
      productId: 'marketing-os',
      productTree: 'a'.repeat(40),
      platform: process.platform,
      arch: process.arch,
      python: { executable: 'python/bin/python3', version: '3.13.0' },
      paths: {
        agent: 'agent',
        nodeModules: 'agent/node_modules',
        playwrightBrowserExecutable: 'playwright-browsers/chromium-1234/chrome',
        playwrightBrowsers: 'playwright-browsers',
        sitePackages: 'site-packages'
      }
    })
  )

  const result = resolveBundledProductRuntime(resources)
  assert.equal(result.manifest.productTree, 'a'.repeat(40))
  assert.equal(result.pythonExecutable, path.join(root, 'python', 'bin', 'python3'))
})

test('rejects manifest paths that escape the packaged runtime', () => {
  const { resources, root } = fixture()
  fs.writeFileSync(
    path.join(root, 'runtime-manifest.json'),
    JSON.stringify({
      schemaVersion: 1,
      productId: 'marketing-os',
      platform: process.platform,
      arch: process.arch,
      python: { executable: '../python' },
      paths: {
        agent: 'agent',
        nodeModules: 'agent/node_modules',
        playwrightBrowserExecutable: 'playwright-browsers/chromium-1234/chrome',
        playwrightBrowsers: 'playwright-browsers',
        sitePackages: 'site-packages'
      }
    })
  )

  assert.throws(() => resolveBundledProductRuntime(resources), /escapes bundled runtime root/)
})

test('rejects a runtime staged for another target', () => {
  const { resources, root } = fixture()
  fs.writeFileSync(
    path.join(root, 'runtime-manifest.json'),
    JSON.stringify({
      schemaVersion: 1,
      productId: 'marketing-os',
      platform: process.platform,
      arch: process.arch === 'x64' ? 'arm64' : 'x64',
      python: { executable: 'python/bin/python3' },
      paths: {
        agent: 'agent',
        nodeModules: 'agent/node_modules',
        playwrightBrowserExecutable: 'playwright-browsers/chromium-1234/chrome',
        playwrightBrowsers: 'playwright-browsers',
        sitePackages: 'site-packages'
      }
    })
  )

  assert.throws(() => resolveBundledProductRuntime(resources), /target mismatch/)
})
