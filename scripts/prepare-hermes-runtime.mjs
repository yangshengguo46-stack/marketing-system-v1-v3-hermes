import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const source = path.join(root, 'runtime', 'hermes-agent')
const output = path.join(root, 'build', 'hermes-runtime')
const lockPath = path.join(root, 'runtime', 'hermes-runtime.lock.json')

const SOURCE_DIRS = [
  'agent', 'tools', 'hermes_cli', 'providers', 'plugins', 'skills',
  'gateway', 'cron', 'assets', 'locales', 'acp_adapter', 'acp_registry',
  'tui_gateway',
]

const ROOT_FILES = [
  'LICENSE', 'pyproject.toml', 'hermes',
  'run_agent.py', 'hermes_state.py', 'hermes_constants.py', 'hermes_logging.py',
  'hermes_time.py', 'model_tools.py', 'toolsets.py', 'toolset_distributions.py',
  'trajectory_compressor.py', 'utils.py', 'batch_runner.py', 'mcp_serve.py',
]

export function prepareHermesRuntime() {
  const python = process.env.PYTHON_BIN || path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
  const verifier = spawnSync(python, [path.join(root, 'scripts', 'verify-hermes-runtime.py')], {
    cwd: root,
    stdio: 'inherit',
  })
  if (verifier.status !== 0) process.exit(verifier.status ?? 1)

  rmSync(output, { recursive: true, force: true })
  mkdirSync(output, { recursive: true })
  for (const relative of SOURCE_DIRS) {
    const from = path.join(source, relative)
    if (!existsSync(from)) throw new Error(`Hermes runtime directory missing: ${relative}`)
    cpSync(from, path.join(output, relative), {
      recursive: true,
      filter: (item) => !item.split(path.sep).some((part) => part === '__pycache__' || part === '.DS_Store'),
    })
  }
  for (const relative of ROOT_FILES) {
    const from = path.join(source, relative)
    if (!existsSync(from)) throw new Error(`Hermes runtime file missing: ${relative}`)
    cpSync(from, path.join(output, relative))
  }

  const lock = JSON.parse(readFileSync(lockPath, 'utf8'))
  const pyproject = readFileSync(path.join(source, 'pyproject.toml'), 'utf8')
  const version = pyproject.match(/^version\s*=\s*"([^"]+)"/m)?.[1] || 'unknown'
  writeFileSync(path.join(output, 'runtime-manifest.json'), JSON.stringify({
    name: 'hermes-agent',
    version,
    repository: lock.repository,
    baselineCommit: lock.baseline_commit,
    productTree: lock.product_tree,
    patchChecksums: lock.patches,
    includesPythonEnvironment: false,
  }, null, 2) + '\n')
  console.log(`Prepared Hermes runtime source: ${version}, tree ${lock.product_tree.slice(0, 12)}`)
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  prepareHermesRuntime()
}
