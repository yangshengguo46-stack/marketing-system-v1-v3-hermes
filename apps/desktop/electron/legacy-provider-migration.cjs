const fs = require('node:fs')
const path = require('node:path')

// This list describes the retired Marketing OS secret file, not a second
// provider registry. New credentials are owned by Hermes' provider catalog and
// /api/env flow. Keep this bounded so a tampered legacy file cannot inject
// process-control variables into the Hermes runtime.
const LEGACY_PROVIDER_ENV = new Set([
  'ANTHROPIC_API_KEY',
  'DEEPSEEK_API_KEY',
  'DEEPSEEK_BASE_URL',
  'DEEPSEEK_MODEL',
  'FIRECRAWL_API_KEY',
  'FIRECRAWL_API_URL',
  'NOUS_API_KEY',
  'OPENAI_API_KEY',
  'OPENAI_BASE_URL',
  'OPENAI_MODEL',
  'OPENROUTER_API_KEY',
  'PEXELS_API_KEY',
  'TAVILY_API_KEY',
  'XAI_API_KEY'
])

function parseLegacyProviderEnvironment(content) {
  const result = {}
  for (const rawLine of String(content || '').split(/\r?\n/)) {
    const line = rawLine.trim().replace(/^export\s+/, '')
    if (!line || line.startsWith('#')) continue
    const separator = line.indexOf('=')
    if (separator <= 0) continue
    const key = line.slice(0, separator).trim()
    if (!LEGACY_PROVIDER_ENV.has(key)) continue
    let value = line.slice(separator + 1).trim()
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1)
    }
    if (!value || /[\r\n\0]/.test(value)) continue
    result[key] = value
  }
  return result
}

function existingEnvKeys(content) {
  const keys = new Set()
  for (const rawLine of String(content || '').split(/\r?\n/)) {
    const match = rawLine.trim().match(/^([A-Z][A-Z0-9_]*)\s*=/)
    if (match) keys.add(match[1])
  }
  return keys
}

function quoteEnvValue(value) {
  if (!/[\s#'"\\]/.test(value)) return value
  return `"${value.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`
}

function migrateLegacyProviderEnvironment({
  userDataPath,
  hermesHome,
  safeStorage,
  fsImpl = fs
} = {}) {
  if (!userDataPath || !hermesHome) {
    return { migrated: false, reason: 'missing-path' }
  }

  const legacyPath = path.join(path.resolve(userDataPath), 'secrets', 'providers.env.encrypted')
  if (!fsImpl.existsSync(legacyPath)) {
    return { migrated: false, reason: 'no-legacy-store' }
  }
  // Electron safeStorage can synchronously block on the macOS keychain.  The
  // retired file is absent for virtually every current install, so prove that
  // migration work exists before touching secure storage at all.
  if (!safeStorage?.isEncryptionAvailable?.()) {
    return { migrated: false, reason: 'secure-storage-unavailable' }
  }

  let values
  try {
    values = parseLegacyProviderEnvironment(
      safeStorage.decryptString(fsImpl.readFileSync(legacyPath))
    )
  } catch {
    return { migrated: false, reason: 'legacy-decrypt-failed' }
  }

  const targetDir = path.resolve(hermesHome)
  const targetPath = path.join(targetDir, '.env')
  let existing = ''
  try {
    existing = fsImpl.readFileSync(targetPath, 'utf8')
  } catch {
    // A missing target is the normal first-run case.
  }

  const present = existingEnvKeys(existing)
  const imported = Object.entries(values).filter(([key]) => !present.has(key))

  try {
    fsImpl.mkdirSync(targetDir, { recursive: true, mode: 0o700 })
    if (imported.length) {
      const prefix = existing && !existing.endsWith('\n') ? `${existing}\n` : existing
      const appended = imported.map(([key, value]) => `${key}=${quoteEnvValue(value)}`).join('\n')
      const tempPath = `${targetPath}.migration-${process.pid}.tmp`
      fsImpl.writeFileSync(tempPath, `${prefix}${appended}\n`, { mode: 0o600 })
      fsImpl.renameSync(tempPath, targetPath)
      try {
        fsImpl.chmodSync(targetPath, 0o600)
      } catch {
        // Some filesystems do not expose POSIX modes; atomic write still won.
      }
    }
    // Successful import (or an already-complete Hermes .env) ends the
    // compatibility period. The retired encrypted store is not a live owner.
    fsImpl.unlinkSync(legacyPath)
  } catch {
    return { migrated: false, reason: 'target-write-failed' }
  }

  return {
    migrated: true,
    importedKeys: imported.map(([key]) => key),
    skippedExistingKeys: Object.keys(values).filter(key => present.has(key))
  }
}

module.exports = {
  LEGACY_PROVIDER_ENV,
  migrateLegacyProviderEnvironment,
  parseLegacyProviderEnvironment
}
