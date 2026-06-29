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
const plugin = process.env.MARKETING_OS_PLUGIN_DIR || path.join(root, 'engine', 'marketing-os')
const server = path.join(plugin, 'server.py')
const output = path.join(root, 'backend', 'dist')

for (const [label, target] of [['Python environment', python], ['Marketing OS server', server]]) {
  if (!existsSync(target)) {
    console.error(`${label} not found: ${target}`)
    process.exit(1)
  }
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
  '--paths', plugin,
  '--collect-submodules', 'tools',
  '--hidden-import', 'yaml',
  '--add-data', `${path.join(plugin, 'config')}${path.delimiter}config`,
  server,
], { stdio: 'inherit' })

process.exit(result.status ?? 1)
