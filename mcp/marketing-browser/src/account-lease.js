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
  if (!target.startsWith(`${base}${path.sep}`)) {
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
