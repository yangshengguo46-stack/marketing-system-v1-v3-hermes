const assert = require('node:assert/strict')
const test = require('node:test')

const {
  migrateLegacyProviderEnvironment,
  parseLegacyProviderEnvironment
} = require('./legacy-provider-migration.cjs')

test('legacy parser accepts provider values but rejects process-control injection', () => {
  const parsed = parseLegacyProviderEnvironment(`
    DEEPSEEK_API_KEY=secret-key
    DEEPSEEK_BASE_URL=https://api.deepseek.com
    export DEEPSEEK_MODEL="deepseek-chat"
    HERMES_HOME=/tmp/attacker
    PYTHONPATH=/tmp/attacker
    PATH=/tmp/attacker
  `)

  assert.deepEqual(parsed, {
    DEEPSEEK_API_KEY: 'secret-key',
    DEEPSEEK_BASE_URL: 'https://api.deepseek.com',
    DEEPSEEK_MODEL: 'deepseek-chat'
  })
})

test('legacy credentials migrate once into Hermes native env without overwriting it', () => {
  const files = new Map([
    ['/product/secrets/providers.env.encrypted', Buffer.from('encrypted-bytes')],
    ['/product/agent-runtime/.env', 'DEEPSEEK_MODEL=existing-model\n']
  ])
  const removed = []

  const result = migrateLegacyProviderEnvironment({
    userDataPath: '/product',
    hermesHome: '/product/agent-runtime',
    safeStorage: {
      isEncryptionAvailable: () => true,
      decryptString: encrypted => {
        assert.equal(String(encrypted), 'encrypted-bytes')
        return 'DEEPSEEK_API_KEY=decrypted-key\nDEEPSEEK_MODEL=legacy-model\n'
      }
    },
    fsImpl: {
      existsSync: target => files.has(target),
      readFileSync: (target, encoding) => {
        const value = files.get(target)
        if (value === undefined) throw new Error('ENOENT')
        return encoding ? String(value) : value
      },
      mkdirSync: () => undefined,
      writeFileSync: (target, value) => files.set(target, String(value)),
      renameSync: (source, target) => {
        files.set(target, files.get(source))
        files.delete(source)
      },
      chmodSync: () => undefined,
      unlinkSync: target => {
        removed.push(target)
        files.delete(target)
      }
    }
  })

  assert.equal(result.migrated, true)
  assert.deepEqual(result.importedKeys, ['DEEPSEEK_API_KEY'])
  assert.deepEqual(result.skippedExistingKeys, ['DEEPSEEK_MODEL'])
  assert.equal(
    files.get('/product/agent-runtime/.env'),
    'DEEPSEEK_MODEL=existing-model\nDEEPSEEK_API_KEY=decrypted-key\n'
  )
  assert.deepEqual(removed, ['/product/secrets/providers.env.encrypted'])
})

test('migration leaves the legacy store untouched when secure storage is unavailable', () => {
  const result = migrateLegacyProviderEnvironment({
    userDataPath: '/product',
    hermesHome: '/product/agent-runtime',
    safeStorage: { isEncryptionAvailable: () => false }
  })

  assert.deepEqual(result, {
    migrated: false,
    reason: 'secure-storage-unavailable'
  })
})
