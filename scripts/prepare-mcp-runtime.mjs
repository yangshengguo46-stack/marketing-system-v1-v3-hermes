import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const project = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..')
const output = path.join(project, 'build', 'mcp-runtime')
// electron-builder prunes directories named node_modules even inside an
// extraResources FileSet.  Stage the same package tree under `modules` and
// pass it through NODE_PATH at runtime so the packaged MCP CLI is not lost.
const runtimeModules = path.join(output, 'modules')

rmSync(output, { recursive: true, force: true })
mkdirSync(runtimeModules, { recursive: true })

for (const packageName of ['@playwright/mcp', 'playwright', 'playwright-core']) {
  const packageJson = require.resolve(`${packageName}/package.json`)
  const source = path.dirname(packageJson)
  const target = path.join(runtimeModules, ...packageName.split('/'))
  mkdirSync(path.dirname(target), { recursive: true })
  cpSync(source, target, { recursive: true, dereference: true })
}

const { chromium } = require('playwright')
const executable = chromium.executablePath()
if (!existsSync(executable)) {
  throw new Error(`Playwright Chromium is missing: ${executable}. Run npx playwright install chromium.`)
}

// executable lives under <registry>/<browser-revision>/<platform>/...
let browserRoot = path.dirname(executable)
while (path.dirname(browserRoot) !== browserRoot && !path.basename(browserRoot).startsWith('chromium-')) {
  browserRoot = path.dirname(browserRoot)
}
if (!path.basename(browserRoot).startsWith('chromium-')) {
  throw new Error(`Cannot determine Chromium revision directory from ${executable}`)
}
const browsersDir = path.join(output, 'browsers')
mkdirSync(browsersDir, { recursive: true })
cpSync(browserRoot, path.join(browsersDir, path.basename(browserRoot)), { recursive: true, dereference: true })

const mcpPackage = JSON.parse(readFileSync(require.resolve('@playwright/mcp/package.json'), 'utf8'))
const playwrightPackage = JSON.parse(readFileSync(require.resolve('playwright/package.json'), 'utf8'))
writeFileSync(path.join(output, 'runtime-manifest.json'), JSON.stringify({
  mcp: mcpPackage.version,
  playwright: playwrightPackage.version,
  browserRevision: path.basename(browserRoot),
  moduleRootRelativePath: 'modules',
  cliRelativePath: path.join('modules', '@playwright', 'mcp', 'cli.js'),
  executableRelativePath: path.join(
    'browsers', path.basename(browserRoot), path.relative(browserRoot, executable),
  ),
}, null, 2))

console.log(`Prepared MCP runtime: ${mcpPackage.version}, ${path.basename(browserRoot)}`)
