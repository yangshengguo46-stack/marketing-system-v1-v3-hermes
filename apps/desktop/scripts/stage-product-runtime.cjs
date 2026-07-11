'use strict'

const { execFileSync } = require('node:child_process')
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
  'optional-mcps',
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
  'utils.py',
  'mcp_serve.py'
]

function copyTree(source, destination, options = {}) {
  fs.cpSync(source, destination, {
    recursive: true,
    dereference: true,
    preserveTimestamps: true,
    filter(item) {
      const relative = path.relative(source, item)
      const parts = relative.split(path.sep)
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
  const pythonExecutable = process.env.MARKETING_OS_BUILD_PYTHON || path.join(
    agentRoot,
    '.venv',
    process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'
  )
  if (!fs.existsSync(pythonExecutable)) {
    throw new Error(`Marketing OS build Python missing: ${pythonExecutable}`)
  }
  const pythonInfo = discoverPython(pythonExecutable)
  const productTree = execFileSync('git', ['rev-parse', 'HEAD^{tree}'], {
    cwd: agentRoot,
    encoding: 'utf8'
  }).trim()
  const result = stageProductRuntime({ desktopRoot, agentRoot, pythonInfo, productTree })
  console.log(
    `[stage-product-runtime] ${result.manifest.python.version} ${result.manifest.platform}/${result.manifest.arch} ` +
      `tree ${productTree.slice(0, 12)} -> ${result.output}`
  )
}

module.exports = { SOURCE_DIRS, ROOT_FILES, discoverPython, stageProductRuntime }

if (require.main === module) main()
