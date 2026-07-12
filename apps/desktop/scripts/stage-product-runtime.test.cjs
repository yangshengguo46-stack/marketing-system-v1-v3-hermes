const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const {
  ROOT_FILES,
  SOURCE_DIRS,
  discoverPython,
  playwrightBrowserDirectory,
  stageMarketingBrowserDependencies,
  stagePlaywrightBrowser,
  stageProductRuntime
} = require('./stage-product-runtime.cjs')

test('discovers the real build Python used by the product runtime', () => {
  const python =
    process.env.MARKETING_OS_BUILD_PYTHON || path.resolve(__dirname, '..', '..', '..', '.venv', 'bin', 'python')
  assert.ok(fs.existsSync(python), `build Python missing: ${python}`)

  const info = discoverPython(python)

  assert.equal(fs.realpathSync(info.executable), fs.realpathSync(python))
  assert.ok(fs.statSync(info.base_prefix).isDirectory())
  assert.ok(fs.statSync(info.purelib).isDirectory())
  assert.match(info.version, /^\d+\.\d+\.\d+$/)
})

test('stages a self-contained product runtime without editable checkout pointers', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'marketing-os-runtime-stage-'))
  const desktopRoot = path.join(root, 'apps', 'desktop')
  const agentRoot = path.join(root, 'agent-source')
  const pythonRoot = path.join(root, 'python-source')
  const purelib = path.join(root, 'site-packages')
  const executable = path.join(pythonRoot, 'bin', 'python3')
  fs.mkdirSync(path.dirname(executable), { recursive: true })
  fs.writeFileSync(executable, '#!/bin/sh\n')
  fs.mkdirSync(purelib, { recursive: true })
  fs.writeFileSync(path.join(purelib, 'runtime_dependency.py'), 'READY = True\n')
  fs.writeFileSync(path.join(purelib, '__editable__.hermes_agent.pth'), '/developer/checkout\n')
  for (const relative of SOURCE_DIRS) {
    fs.mkdirSync(path.join(agentRoot, relative), { recursive: true })
    fs.writeFileSync(path.join(agentRoot, relative, 'marker.txt'), relative)
  }
  for (const relative of ROOT_FILES) {
    fs.mkdirSync(path.dirname(path.join(agentRoot, relative)), { recursive: true })
    fs.writeFileSync(path.join(agentRoot, relative), relative)
  }

  const result = stageProductRuntime({
    desktopRoot,
    agentRoot,
    productTree: 'a'.repeat(40),
    pythonInfo: {
      base_prefix: pythonRoot,
      executable,
      machine: process.arch,
      platform: process.platform,
      purelib,
      version: '3.13.0'
    }
  })

  assert.equal(result.manifest.productId, 'marketing-os')
  assert.equal(result.manifest.productTree, 'a'.repeat(40))
  assert.equal(result.manifest.python.executable, 'python/bin/python3')
  assert.ok(fs.existsSync(path.join(result.output, 'agent', 'agent', 'marker.txt')))
  assert.equal(SOURCE_DIRS.includes('marketing_os'), false)
  assert.ok(fs.existsSync(path.join(result.output, 'site-packages', 'runtime_dependency.py')))
  assert.equal(fs.existsSync(path.join(result.output, 'site-packages', '__editable__.hermes_agent.pth')), false)
})

test('stages only the marketing browser dependency closure and Chromium runtime', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'marketing-browser-runtime-stage-'))
  const agentRoot = path.join(root, 'agent-source')
  const output = path.join(root, 'output')
  const direct = path.join(agentRoot, 'node_modules', 'playwright')
  const nested = path.join(agentRoot, 'node_modules', 'express', 'node_modules', 'cookie')
  fs.mkdirSync(direct, { recursive: true })
  fs.mkdirSync(nested, { recursive: true })
  fs.writeFileSync(path.join(direct, 'package.json'), '{}')
  fs.writeFileSync(path.join(nested, 'package.json'), '{}')

  const dependencies = stageMarketingBrowserDependencies({
    agentRoot,
    dependencyPaths: [direct, nested],
    output
  })
  assert.equal(dependencies.copied, 2)
  assert.ok(fs.existsSync(path.join(output, 'agent', 'node_modules', 'playwright', 'package.json')))
  assert.ok(
    fs.existsSync(path.join(output, 'agent', 'node_modules', 'express', 'node_modules', 'cookie', 'package.json'))
  )

  const executable = path.join(
    root,
    'cache',
    'chromium-1234',
    'chrome-mac-x64',
    'Chrome.app',
    'Contents',
    'MacOS',
    'Chrome'
  )
  fs.mkdirSync(path.dirname(executable), { recursive: true })
  fs.writeFileSync(executable, '')
  assert.equal(playwrightBrowserDirectory(executable), path.join(root, 'cache', 'chromium-1234'))
  const browser = stagePlaywrightBrowser({ executablePath: executable, output })
  assert.equal(browser.relativeRoot, 'playwright-browsers')
  assert.equal(
    browser.executableRelative,
    path.join('playwright-browsers', 'chromium-1234', 'chrome-mac-x64', 'Chrome.app', 'Contents', 'MacOS', 'Chrome')
  )
  assert.ok(fs.existsSync(path.join(output, browser.executableRelative)))
})
