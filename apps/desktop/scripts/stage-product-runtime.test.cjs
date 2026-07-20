const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const test = require('node:test')

const {
  ROOT_FILES,
  REMOTION_UPGRADE_REQUIREMENTS,
  SOURCE_DIRS,
  VIDEO_RENDERER_PINS,
  discoverPython,
  playwrightBrowserDirectory,
  stageMarketingBrowserDependencies,
  stagePlaywrightBrowser,
  stageProductRuntime,
  stageVideoRenderers,
  validateVideoRendererPins
} = require('./stage-product-runtime.cjs')

function writePinnedVideoRendererFixture(rendererRoot) {
  const packages = { '': { dependencies: VIDEO_RENDERER_PINS } }
  const installedPackages = {}
  const dependencyPaths = []
  for (const [name, version] of Object.entries(VIDEO_RENDERER_PINS)) {
    const key = `node_modules/${name}`
    const dependency = path.join(rendererRoot, ...key.split('/'))
    fs.mkdirSync(dependency, { recursive: true })
    fs.writeFileSync(path.join(dependency, 'package.json'), JSON.stringify({ name, version }))
    packages[key] = { version }
    installedPackages[key] = { version }
    dependencyPaths.push(dependency)
  }
  fs.mkdirSync(path.join(rendererRoot, 'remotion'), { recursive: true })
  fs.writeFileSync(path.join(rendererRoot, 'package.json'), JSON.stringify({ dependencies: VIDEO_RENDERER_PINS }))
  fs.writeFileSync(path.join(rendererRoot, 'package-lock.json'), JSON.stringify({ lockfileVersion: 3, packages }))
  fs.writeFileSync(
    path.join(rendererRoot, 'version-policy.json'),
    JSON.stringify({
      dependencies: VIDEO_RENDERER_PINS,
      remotion_upgrade_gate: {
        blocked_major: 5,
        locked_version: VIDEO_RENDERER_PINS.remotion,
        requires: REMOTION_UPGRADE_REQUIREMENTS
      }
    })
  )
  fs.writeFileSync(
    path.join(rendererRoot, 'node_modules', '.package-lock.json'),
    JSON.stringify({ lockfileVersion: 3, packages: installedPackages })
  )
  fs.writeFileSync(path.join(rendererRoot, 'render-remotion.mjs'), '')
  fs.writeFileSync(path.join(rendererRoot, 'render-hyperframes.mjs'), '')
  fs.writeFileSync(path.join(rendererRoot, 'remotion', 'index.ts'), '')
  return dependencyPaths
}

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
  assert.ok(
    fs.existsSync(
      path.join(
        result.output,
        'agent',
        'optional-skills',
        'creative',
        'kanban-video-orchestrator',
        'marker.txt'
      )
    )
  )
  assert.ok(fs.existsSync(path.join(result.output, 'agent', 'skills', 'marker.txt')))
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

test('stages pinned video renderer sources and their production dependency closure', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'marketing-video-renderers-stage-'))
  const agentRoot = path.join(root, 'agent-source')
  const rendererRoot = path.join(agentRoot, 'video-renderers')
  const output = path.join(root, 'output')
  const dependencyPaths = writePinnedVideoRendererFixture(rendererRoot)

  const result = stageVideoRenderers({ agentRoot, output, dependencyPaths })

  assert.equal(result.relative, 'video-renderers')
  assert.equal(result.copied, Object.keys(VIDEO_RENDERER_PINS).length)
  assert.ok(fs.existsSync(path.join(output, 'video-renderers', 'render-remotion.mjs')))
  assert.ok(fs.existsSync(path.join(output, 'video-renderers', 'node_modules', 'hyperframes', 'package.json')))
  assert.ok(fs.existsSync(path.join(output, 'video-renderers', 'node_modules', '.package-lock.json')))
  assert.deepEqual(
    validateVideoRendererPins(path.join(output, 'video-renderers')),
    { ...VIDEO_RENDERER_PINS }
  )
})

test('rejects Remotion version drift before staging a product build', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'marketing-video-renderers-drift-'))
  const rendererRoot = path.join(root, 'video-renderers')
  writePinnedVideoRendererFixture(rendererRoot)
  const manifestPath = path.join(rendererRoot, 'package.json')
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'))
  manifest.dependencies.remotion = '5.0.0'
  fs.writeFileSync(manifestPath, JSON.stringify(manifest))

  assert.throws(
    () => validateVideoRendererPins(rendererRoot),
    /remotion must remain 4\.0\.488/
  )
})
