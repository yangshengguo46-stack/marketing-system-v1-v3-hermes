import { existsSync, mkdirSync } from 'node:fs'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const python = process.env.PYTHON_BIN || path.join(
  root,
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
)
const engine = path.join(root, 'engine')
const marketing = process.env.MARKETING_OS_ENGINE_DIR || path.join(engine, 'marketing-os')
const server = path.join(marketing, 'server.py')
const output = path.join(root, 'backend', 'dist')
const hermesRuntime = path.join(root, 'build', 'hermes-runtime')

for (const [label, target] of [['Python environment', python], ['Marketing OS server', server]]) {
  if (!existsSync(target)) {
    console.error(`${label} not found: ${target}`)
    process.exit(1)
  }
}

const mcpCheck = spawnSync(python, [
  '-c',
  "from importlib.metadata import version; assert version('mcp') == '1.26.0'; from mcp import ClientSession, StdioServerParameters",
], { stdio: 'inherit' })
if (mcpCheck.status !== 0) {
  console.error('Pinned Python MCP SDK 1.26.0 is missing; install backend/requirements.txt')
  process.exit(1)
}

const hermesPrep = spawnSync(process.execPath, [path.join(root, 'scripts', 'prepare-hermes-runtime.mjs')], {
  cwd: root,
  env: { ...process.env, PYTHON_BIN: python },
  stdio: 'inherit',
})
if (hermesPrep.status !== 0) {
  console.error('Hermes runtime source verification/staging failed')
  process.exit(hermesPrep.status ?? 1)
}

mkdirSync(output, { recursive: true })
const result = spawnSync(python, [
  '-m', 'PyInstaller',
  '--noconfirm',
  '--clean',
  '--onefile',
  '--name', 'marketing-os-server',
  '--distpath', output,
  '--workpath', path.join(root, 'backend', 'build'),
  '--specpath', path.join(root, 'backend'),
  '--paths', engine,
  '--paths', marketing,
  '--paths', hermesRuntime,
  '--collect-submodules', 'agent_core',
  '--collect-submodules', 'marketing_tools',
  '--collect-submodules', 'agent',
  '--hidden-import', 'run_agent',
  '--hidden-import', 'hermes_state',
  '--hidden-import', 'model_tools',
  '--hidden-import', 'toolsets',
  '--hidden-import', 'tools.registry',
  '--hidden-import', 'hermes_cli.env_loader',
  '--hidden-import', 'hermes_cli.timeouts',
  '--hidden-import', 'yaml',
  '--hidden-import', 'mcp',
  '--hidden-import', 'mcp.client.stdio',
  '--hidden-import', 'mcp.shared.session',
  '--add-data', `${path.join(marketing, 'config')}${path.delimiter}config`,
  server,
], { stdio: 'inherit' })

process.exit(result.status ?? 1)
