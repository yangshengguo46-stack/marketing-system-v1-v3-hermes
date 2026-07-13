import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'

const ID_PATTERN = /^[A-Za-z0-9_.:@-]{1,160}$/
const PLATFORM_PATTERN = /^[a-z0-9_-]{1,48}$/

function assertSafeIdentifier(value, label) {
  if (!ID_PATTERN.test(value) || value === '.' || value === '..') {
    throw new Error(`invalid lease ${label}`)
  }
}

function accountDirectory(root, lease) {
  const base = path.resolve(root)
  const target = path.resolve(base, lease.platform, lease.account_id)
  const prefix = base.endsWith(path.sep) ? base : `${base}${path.sep}`
  if (!target.startsWith(prefix)) {
    throw new Error('account profile escaped the configured browser root')
  }
  return target
}

export function parseAccountLease(raw = process.env.HERMES_MARKETING_ACCOUNT_LEASE) {
  let value
  try {
    value = JSON.parse(String(raw || ''))
  } catch {
    throw new Error('Hermes BrowserContext lease is missing or invalid')
  }
  const lease = {
    session_id: String(value?.session_id || '').trim(),
    user_id: String(value?.user_id || 'default').trim(),
    account_id: String(value?.account_id || '').trim(),
    platform: String(value?.platform || '').trim().toLowerCase(),
    profile_key: String(value?.profile_key || '').trim(),
    auth_state: String(value?.auth_state || 'unknown').trim().toLowerCase(),
  }
  assertSafeIdentifier(lease.session_id, 'session_id')
  assertSafeIdentifier(lease.user_id, 'user_id')
  assertSafeIdentifier(lease.account_id, 'account_id')
  if (!PLATFORM_PATTERN.test(lease.platform)) throw new Error('invalid lease platform')
  if (lease.profile_key !== `${lease.platform}:${lease.account_id}`) {
    throw new Error('lease profile_key does not match the bound account')
  }
  return Object.freeze(lease)
}

export function profileDirectory(
  lease,
  root = process.env.HERMES_BROWSER_PROFILE_ROOT,
) {
  const normalized = parseAccountLease(JSON.stringify(lease))
  const base = root
    ? path.resolve(root)
    : path.join(os.homedir(), '.hermes', 'browser-profiles')
  return accountDirectory(base, normalized)
}

export function outputDirectory(
  lease,
  root = process.env.HERMES_BROWSER_OUTPUT_ROOT,
) {
  const normalized = parseAccountLease(JSON.stringify(lease))
  const base = root
    ? path.resolve(root)
    : path.join(os.homedir(), '.hermes', 'browser-output')
  return accountDirectory(base, normalized)
}

export async function migrateLegacyProfile(
  lease,
  profileRoot = process.env.HERMES_BROWSER_PROFILE_ROOT,
  legacyRoot = process.env.HERMES_LEGACY_BROWSER_PROFILE_ROOT,
) {
  if (!legacyRoot) return false
  const normalized = parseAccountLease(JSON.stringify(lease))
  const target = profileDirectory(normalized, profileRoot)
  const source = accountDirectory(path.resolve(legacyRoot), normalized)
  try {
    await fs.access(target)
    return false
  } catch {}
  try {
    await fs.access(source)
  } catch {
    return false
  }
  await fs.mkdir(path.dirname(target), { recursive: true })
  try {
    await fs.rename(source, target)
  } catch (error) {
    if (error?.code !== 'EXDEV') throw error
    await fs.cp(source, target, { recursive: true, errorOnExist: true })
    await fs.rm(source, { recursive: true, force: true })
  }
  await Promise.all(
    ['SingletonCookie', 'SingletonLock', 'SingletonSocket'].map(name =>
      fs.rm(path.join(target, name), { force: true, recursive: true }),
    ),
  )
  return true
}

export async function purgeAccountDirectories(
  lease,
  profileRoot = process.env.HERMES_BROWSER_PROFILE_ROOT,
  outputRoot = process.env.HERMES_BROWSER_OUTPUT_ROOT,
) {
  await Promise.all([
    fs.rm(profileDirectory(lease, profileRoot), { recursive: true, force: true }),
    fs.rm(outputDirectory(lease, outputRoot), { recursive: true, force: true }),
  ])
}
