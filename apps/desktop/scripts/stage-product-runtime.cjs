'use strict'

const { execFileSync, spawnSync } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')

const SOURCE_DIRS = [
  'agent',
  'tools',
  'hermes_cli',
  'providers',
  'plugins',
  'skills',
  'gateway',
  'cron',
  'assets',
  'locales',
  'mcp',
  'optional-mcps',
  'optional-skills/creative/kanban-video-orchestrator',
  'acp_adapter',
  'acp_registry',
  'tui_gateway'
]

const ROOT_FILES = [
  'LICENSE',
  'pyproject.toml',
  'run_agent.py',
  'model_tools.py',
  'toolsets.py',
  'batch_runner.py',
  'trajectory_compressor.py',
  'toolset_distributions.py',
  'cli.py',
  'hermes_bootstrap.py',
  'hermes_constants.py',
  'hermes_state.py',
  'hermes_time.py',
  'hermes_logging.py',
  'marketing_knowledge_protocol.py',
  'utils.py',
  'mcp_serve.py'
]

function copyTree(source, destination, options = {}) {
  fs.cpSync(source, destination, {
    recursive: true,
    dereference: options.dereference !== false,
    preserveTimestamps: true,
    filter(item) {
      const relative = path.relative(source, item)
      const parts = relative.split(path.sep)
      if (options.excludeNodeModules && parts.includes('node_modules')) return false
      if (parts.some(part => part === '__pycache__' || part === '.DS_Store')) return false
      if (/\.py[co]$/i.test(item)) return false
      if (options.sitePackages) {
        const first = parts[0] || ''
        if (first.startsWith('__editable__') || first.startsWith('_virtualenv')) return false
        if (first === '.git' || first === 'pytest' || first === '_pytest' || first === 'PyInstaller') return false
      }
      return true
    }
  })
}

function productionDependencyPathsForRoot(packageRoot) {
  const result = spawnSync('npm', ['ls', '--all', '--parseable', '--omit=dev'], {
    cwd: packageRoot,
    encoding: 'utf8'
  })
  if (result.error) throw result.error
  const output = String(result.stdout || '')
  if (!output.trim()) {
    throw new Error(`Production dependency discovery failed: ${String(result.stderr || '').trim()}`)
  }
  const modulesRoot = path.join(packageRoot, 'node_modules')
  return output
    .split(/\r?\n/)
    .map(value => value.trim())
    .filter(Boolean)
    .filter(value => value.startsWith(`${modulesRoot}${path.sep}`))
    .filter(value => path.basename(value) !== 'fsevents')
}

function discoverPython(pythonExecutable) {
  const script = [
    'import json, platform, sys, sysconfig;',
    'print(json.dumps({',
    '"executable": sys.executable,',
    '"base_prefix": sys.base_prefix,',
    '"purelib": sysconfig.get_paths()["purelib"],',
    '"version": platform.python_version(),',
    '"platform": sys.platform,',
    '"machine": platform.machine()',
    '}))'
  ].join(' ')
  return JSON.parse(execFileSync(pythonExecutable, ['-c', script], { encoding: 'utf8' }))
}

function productionDependencyPaths(agentRoot) {
  const result = spawnSync(
    'npm',
    ['ls', '--all', '--parseable', '--omit=dev', '--workspace', '@marketing-os/browser-mcp'],
    { cwd: agentRoot, encoding: 'utf8' }
  )
  if (result.error) throw result.error
  const output = String(result.stdout || '')
  if (!output.trim()) {
    throw new Error(`Marketing browser dependency discovery failed: ${String(result.stderr || '').trim()}`)
  }
  const modulesRoot = path.join(agentRoot, 'node_modules')
  return output
    .split(/\r?\n/)
    .map(value => value.trim())
    .filter(Boolean)
    .filter(value => value === modulesRoot || value.startsWith(`${modulesRoot}${path.sep}`))
    .filter(value => value !== modulesRoot)
    .filter(value => path.basename(value) !== 'fsevents')
}

function stageMarketingBrowserDependencies({
  agentRoot,
  output,
  dependencyPaths = productionDependencyPaths(agentRoot)
}) {
  const modulesRoot = path.join(agentRoot, 'node_modules')
  const destinationRoot = path.join(output, 'agent', 'node_modules')
  let copied = 0
  for (const source of dependencyPaths) {
    const relative = path.relative(modulesRoot, source)
    if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) continue
    copyTree(source, path.join(destinationRoot, relative))
    copied += 1
  }
  if (!copied) throw new Error('Marketing browser production dependencies are missing')
  return { copied, relative: path.posix.join('agent', 'node_modules') }
}

const VIDEO_RENDERER_PINS = Object.freeze({
  '@remotion/cli': '4.0.488',
  gsap: '3.14.2',
  hyperframes: '0.7.57',
  react: '19.2.4',
  'react-dom': '19.2.4',
  remotion: '4.0.488'
})
const REMOTION_UPGRADE_REQUIREMENTS = Object.freeze([
  'explicit_user_approval',
  'license_review',
  'renderer_regression'
])

function validateVideoRendererPins(sourceRoot) {
  const readJson = relative => JSON.parse(fs.readFileSync(path.join(sourceRoot, relative), 'utf8'))
  const manifest = readJson('package.json')
  const policy = readJson('version-policy.json')
  const lock = readJson('package-lock.json')
  const installed = readJson(path.join('node_modules', '.package-lock.json'))
  const versionMaps = [
    ['package.json', manifest.dependencies],
    ['version policy', policy.dependencies],
    ['package-lock root', lock.packages?.['']?.dependencies]
  ]
  for (const [name, version] of Object.entries(VIDEO_RENDERER_PINS)) {
    for (const [label, versions] of versionMaps) {
      if (versions?.[name] !== version) {
        throw new Error(`Video renderer pin drift in ${label}: ${name} must remain ${version}`)
      }
    }
    const packageKey = `node_modules/${name}`
    for (const [label, actual] of [
      ['package-lock package', lock.packages?.[packageKey]?.version],
      ['installed lockfile', installed.packages?.[packageKey]?.version],
      ['installed package', readJson(path.join(packageKey, 'package.json')).version]
    ]) {
      if (actual !== version) {
        throw new Error(`Video renderer pin drift in ${label}: ${name} must remain ${version}`)
      }
    }
  }
  if (policy.remotion_upgrade_gate?.locked_version !== VIDEO_RENDERER_PINS.remotion) {
    throw new Error('Remotion upgrade gate and dependency pin disagree')
  }
  if (policy.remotion_upgrade_gate?.blocked_major !== 5) {
    throw new Error('Remotion 5 upgrade gate is missing')
  }
  if (JSON.stringify(policy.remotion_upgrade_gate?.requires) !== JSON.stringify(REMOTION_UPGRADE_REQUIREMENTS)) {
    throw new Error('Remotion upgrade requirements have drifted')
  }
  if (Number(VIDEO_RENDERER_PINS.remotion.split('.')[0]) >= Number(policy.remotion_upgrade_gate?.blocked_major)) {
    throw new Error('Remotion major upgrade requires explicit approval and license review')
  }
  return { ...VIDEO_RENDERER_PINS }
}

function stageVideoRenderers({
  agentRoot,
  output,
  dependencyPaths
}) {
  const sourceRoot = path.join(agentRoot, 'video-renderers')
  const destinationRoot = path.join(output, 'video-renderers')
  if (!fs.existsSync(path.join(sourceRoot, 'package-lock.json'))) {
    throw new Error('Pinned video renderer lockfile is missing')
  }
  validateVideoRendererPins(sourceRoot)
  copyTree(sourceRoot, destinationRoot, { excludeNodeModules: true })
  const modulesRoot = path.join(sourceRoot, 'node_modules')
  const resolvedDependencies = dependencyPaths || productionDependencyPathsForRoot(sourceRoot)
  let copied = 0
  for (const source of resolvedDependencies) {
    const relative = path.relative(modulesRoot, source)
    if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) continue
    copyTree(source, path.join(destinationRoot, 'node_modules', relative))
    copied += 1
  }
  if (!copied) throw new Error('Video renderer production dependencies are missing')
  const destinationModules = path.join(destinationRoot, 'node_modules')
  fs.mkdirSync(destinationModules, { recursive: true })
  fs.copyFileSync(
    path.join(modulesRoot, '.package-lock.json'),
    path.join(destinationModules, '.package-lock.json')
  )
  return { copied, relative: 'video-renderers' }
}

function playwrightBrowserDirectory(executablePath) {
  let current = path.resolve(executablePath)
  while (current !== path.dirname(current)) {
    if (/^chromium-\d+$/.test(path.basename(current))) return current
    current = path.dirname(current)
  }
  throw new Error(`Playwright Chromium directory could not be derived from ${executablePath}`)
}

function stagePlaywrightBrowser({ executablePath, output }) {
  if (!executablePath || !fs.existsSync(executablePath)) {
    throw new Error('Playwright Chromium is missing; run `npx playwright install chromium` before packaging')
  }
  const source = playwrightBrowserDirectory(executablePath)
  const relativeRoot = 'playwright-browsers'
  const browserRelative = path.join(relativeRoot, path.basename(source))
  copyTree(source, path.join(output, browserRelative), { dereference: false })
  const executableRelative = path.join(browserRelative, path.relative(source, executablePath))
  return { executableRelative, relativeRoot }
}

function stageProductRuntime({ desktopRoot, agentRoot, pythonInfo, productTree }) {
  const output = path.join(desktopRoot, 'build', 'product-runtime')
  const pythonSource = fs.realpathSync(pythonInfo.base_prefix)
  const executableSource = fs.realpathSync(pythonInfo.executable)
  const executableRelative = path.relative(pythonSource, executableSource)
  if (!executableRelative || executableRelative.startsWith('..') || path.isAbsolute(executableRelative)) {
    throw new Error(`Python executable is outside base_prefix: ${executableSource}`)
  }
  if (!fs.statSync(pythonInfo.purelib).isDirectory()) {
    throw new Error(`Python site-packages missing: ${pythonInfo.purelib}`)
  }

  fs.rmSync(output, { recursive: true, force: true })
  fs.mkdirSync(output, { recursive: true })
  copyTree(pythonSource, path.join(output, 'python'))
  copyTree(pythonInfo.purelib, path.join(output, 'site-packages'), { sitePackages: true })

  const stagedAgent = path.join(output, 'agent')
  fs.mkdirSync(stagedAgent, { recursive: true })
  for (const relative of SOURCE_DIRS) {
    const source = path.join(agentRoot, relative)
    if (!fs.existsSync(source)) throw new Error(`Hermes runtime directory missing: ${relative}`)
    copyTree(source, path.join(stagedAgent, relative))
  }
  for (const relative of ROOT_FILES) {
    const source = path.join(agentRoot, relative)
    if (!fs.existsSync(source)) throw new Error(`Hermes runtime file missing: ${relative}`)
    fs.copyFileSync(source, path.join(stagedAgent, relative))
  }

  const executable = path.posix.join('python', ...executableRelative.split(path.sep))
  const manifest = {
    schemaVersion: 1,
    productId: 'marketing-os',
    productTree,
    platform: process.platform,
    arch: process.arch,
    python: {
      version: pythonInfo.version,
      executable
    },
    paths: {
      agent: 'agent',
      sitePackages: 'site-packages'
    }
  }
  fs.writeFileSync(path.join(output, 'runtime-manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`)
  return { output, manifest }
}

function main() {
  const desktopRoot = path.resolve(__dirname, '..')
  const agentRoot = path.resolve(desktopRoot, '..', '..')
  const pythonExecutable =
    process.env.MARKETING_OS_BUILD_PYTHON ||
    path.join(agentRoot, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
  if (!fs.existsSync(pythonExecutable)) {
    throw new Error(`Marketing OS build Python missing: ${pythonExecutable}`)
  }
  const pythonInfo = discoverPython(pythonExecutable)
  const productTree = execFileSync('git', ['rev-parse', 'HEAD^{tree}'], {
    cwd: agentRoot,
    encoding: 'utf8'
  }).trim()
  const result = stageProductRuntime({ desktopRoot, agentRoot, pythonInfo, productTree })
  const dependencies = stageMarketingBrowserDependencies({ agentRoot, output: result.output })
  const renderers = stageVideoRenderers({ agentRoot, output: result.output })
  const { chromium } = require('playwright')
  const browser = stagePlaywrightBrowser({
    executablePath: chromium.executablePath(),
    output: result.output
  })
  result.manifest.paths.nodeModules = dependencies.relative
  result.manifest.paths.playwrightBrowsers = browser.relativeRoot
  result.manifest.paths.playwrightBrowserExecutable = browser.executableRelative
  result.manifest.paths.videoRenderers = renderers.relative
  fs.writeFileSync(path.join(result.output, 'runtime-manifest.json'), `${JSON.stringify(result.manifest, null, 2)}\n`)
  console.log(
    `[stage-product-runtime] ${result.manifest.python.version} ${result.manifest.platform}/${result.manifest.arch} ` +
      `tree ${productTree.slice(0, 12)} -> ${result.output}`
  )
}

module.exports = {
  SOURCE_DIRS,
  ROOT_FILES,
  REMOTION_UPGRADE_REQUIREMENTS,
  VIDEO_RENDERER_PINS,
  discoverPython,
  playwrightBrowserDirectory,
  productionDependencyPaths,
  stageMarketingBrowserDependencies,
  stageVideoRenderers,
  validateVideoRendererPins,
  stagePlaywrightBrowser,
  stageProductRuntime
}

if (require.main === module) main()
