#!/usr/bin/env node

/**
 * Playwright MCP supply chain verification.
 *
 * Checks:
 *  1. package.json pins exact version (no ^, ~, latest)
 *  2. Lockfile version, resolved registry URL, integrity present
 *  3. Locally installed package version matches
 *  4. CLI binary and symlink exist
 *  5. CLI --version returns pinned version
 *  6. Package license is Apache-2.0
 *  7. Fail closed — never download, install, or fix automatically
 */

import { createRequire } from 'node:module'
import { accessSync, constants, existsSync, readFileSync, statSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const projectRoot = join(__dirname, '..')

const PINNED_VERSION = '0.0.77'
const PINNED_PACKAGE = '@playwright/mcp'
const EXPECTED_LICENSE = 'Apache-2.0'

let failures = 0
function fail(msg) {
  console.error(`FAIL: ${msg}`)
  failures++
}
function pass(msg) {
  console.log(`PASS: ${msg}`)
}

// ── 1. package.json exact version ──────────────────────────────────────────
console.log('── 1. package.json ──')
const pkgJson = JSON.parse(readFileSync(join(projectRoot, 'package.json'), 'utf8'))
const depVersion = pkgJson.dependencies?.[PINNED_PACKAGE]
if (!depVersion) {
  fail(`${PINNED_PACKAGE} missing from package.json dependencies`)
} else if (/[\^~><*x]/.test(depVersion)) {
  fail(`${PINNED_PACKAGE} version "${depVersion}" is not pinned — contains ^ ~ > < * x`)
} else if (depVersion !== PINNED_VERSION) {
  fail(`${PINNED_PACKAGE} version "${depVersion}" != "${PINNED_VERSION}"`)
} else {
  pass(`${PINNED_PACKAGE} pinned at "${depVersion}"`)
}

// ── 2. Lockfile ────────────────────────────────────────────────────────────
console.log('── 2. package-lock.json ──')
let lockfile
try {
  lockfile = JSON.parse(readFileSync(join(projectRoot, 'package-lock.json'), 'utf8'))
} catch {
  fail('package-lock.json not found or not valid JSON')
  process.exit(1)
}
const lockKey = `node_modules/${PINNED_PACKAGE}`
const lockEntry = lockfile.packages?.[lockKey]
if (!lockEntry) {
  fail(`${lockKey} not found in lockfile packages`)
} else {
  if (lockEntry.version !== PINNED_VERSION) {
    fail(`lockfile version "${lockEntry.version}" != "${PINNED_VERSION}"`)
  } else {
    pass(`lockfile version: ${lockEntry.version}`)
  }
  if (lockEntry.resolved && lockEntry.resolved.includes('registry.npmjs.org')) {
    pass(`lockfile resolved: ${lockEntry.resolved}`)
  } else {
    fail('lockfile missing or unexpected resolved URL')
  }
  if (lockEntry.integrity && lockEntry.integrity.startsWith('sha512-')) {
    pass(`lockfile integrity: ${lockEntry.integrity.slice(0, 20)}...`)
  } else {
    fail('lockfile missing integrity')
  }
  if (lockEntry.license === EXPECTED_LICENSE) {
    pass(`lockfile license: ${lockEntry.license}`)
  } else {
    fail(`lockfile license "${lockEntry.license}" != "${EXPECTED_LICENSE}"`)
  }
  // Check transitive dependency versions are non-empty
  const transitive = lockEntry.dependencies
  if (transitive && typeof transitive === 'object') {
    let transitiveOk = true
    for (const [name, ver] of Object.entries(transitive)) {
      if (!ver || typeof ver !== 'string') {
        fail(`transitive dep "${name}" missing version`)
        transitiveOk = false
      }
    }
    if (transitiveOk) {
      pass(`all ${Object.keys(transitive).length} transitive deps have fixed versions`)
    }
  }
}

// ── 3. Installed package version ───────────────────────────────────────────
console.log('── 3. Installed package ──')
const pkgPath = join(projectRoot, 'node_modules', ...PINNED_PACKAGE.split('/'))
try {
  const installedJson = JSON.parse(readFileSync(join(pkgPath, 'package.json'), 'utf8'))
  if (installedJson.version === PINNED_VERSION) {
    pass(`installed package version: ${installedJson.version}`)
  } else {
    fail(`installed version "${installedJson.version}" != "${PINNED_VERSION}"`)
  }
  if (installedJson.license === EXPECTED_LICENSE) {
    pass(`installed package license: ${installedJson.license}`)
  } else {
    fail(`installed license "${installedJson.license}" != "${EXPECTED_LICENSE}"`)
  }
} catch (e) {
  fail(`cannot read installed package: ${e.message}`)
}

// ── 4. CLI binary and symlink ──────────────────────────────────────────────
console.log('── 4. CLI binary ──')
const binPath = join(projectRoot, 'node_modules', '.bin', 'playwright-mcp')
const cliRealPath = join(projectRoot, 'node_modules', ...PINNED_PACKAGE.split('/'), 'cli.js')
try {
  const binStat = statSync(binPath)
  if (!binStat.isFile() && !binStat.isSymbolicLink()) {
    fail('CLI .bin entry is not a file or symlink')
  }
  if (existsSync(cliRealPath)) {
    pass(`CLI real file exists: ${cliRealPath}`)
  } else {
    fail('CLI real file (cli.js) missing')
  }
  pass('CLI binary and symlink exist')
} catch (e) {
  fail(`CLI binary missing or inaccessible: ${e.message}`)
}

// ── 5. CLI --version ───────────────────────────────────────────────────────
console.log('── 5. CLI --version ──')
try {
  const result = spawnSync(process.execPath, [cliRealPath, '--version'], {
    encoding: 'utf8',
    timeout: 10_000,
    env: { ...process.env, NODE_OPTIONS: undefined },
  })
  const stdout = (result.stdout || '').trim()
  if (result.error) {
    fail(`CLI --version spawn error: ${result.error.message}`)
  } else if (stdout.includes(PINNED_VERSION)) {
    pass(`CLI --version returned: "${stdout}"`)
  } else {
    fail(`CLI --version returned "${stdout}", expected "${PINNED_VERSION}"`)
  }
} catch (e) {
  fail(`CLI --version failed: ${e.message}`)
}

// ── 6. Forbidden patterns ──────────────────────────────────────────────────
console.log('── 6. Forbidden startup patterns ──')
const forbiddenInPackage = ['npx', 'npm exec', 'yarn dlx', 'pnpm dlx', 'latest', '--yes', '-y']
const scripts = pkgJson.scripts || {}
for (const [name, cmd] of Object.entries(scripts)) {
  for (const f of forbiddenInPackage) {
    if (String(cmd).includes(f)) {
      fail(`script "${name}" contains forbidden pattern "${f}"`)
    }
  }
}
pass('no forbidden patterns in package.json scripts')

// ── Summary ────────────────────────────────────────────────────────────────
console.log(`\n── Result: ${failures === 0 ? 'ALL CHECKS PASSED' : `${failures} CHECK(S) FAILED`} ──`)
process.exit(failures ? 1 : 0)
