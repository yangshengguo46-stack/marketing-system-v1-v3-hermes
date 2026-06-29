import { existsSync, readdirSync } from 'node:fs'
import { homedir } from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const version = require('electron/package.json').version
const platform = process.platform === 'darwin' ? 'darwin' : process.platform
const arch = process.arch === 'x64' ? 'x64' : process.arch
const filename = `electron-v${version}-${platform}-${arch}.zip`
const cacheRoot = process.env.ELECTRON_CACHE || (process.platform === 'darwin'
  ? path.join(homedir(), 'Library', 'Caches', 'electron')
  : path.join(homedir(), '.cache', 'electron'))

function findCachedElectron() {
  if (!existsSync(cacheRoot)) return null
  for (const entry of readdirSync(cacheRoot, { withFileTypes: true })) {
    const candidate = entry.isDirectory() ? path.join(cacheRoot, entry.name, filename) : path.join(cacheRoot, filename)
    if (existsSync(candidate)) return candidate
  }
  return null
}

const target = process.argv.slice(2)
const args = ['electron-builder', ...target]
const cachedElectron = findCachedElectron()
if (cachedElectron) args.push(`--config.electronDist=${cachedElectron}`)

const executable = process.platform === 'win32' ? 'npx.cmd' : 'npx'
const result = spawnSync(executable, args, { stdio: 'inherit' })
process.exit(result.status ?? 1)
