import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'
import {
  outputDirectory,
  parseAccountLease,
  profileDirectory,
  purgeAccountDirectories,
} from '../src/account-lease.js'

const lease = {
  session_id: 'session-1',
  user_id: 'default',
  account_id: 'acct_ab3145',
  platform: 'douyin',
  profile_key: 'douyin:acct_ab3145',
  auth_state: 'authenticated',
}

test('accepts a secret-free AccountRegistry BrowserContext lease', () => {
  assert.deepEqual(parseAccountLease(JSON.stringify(lease)), lease)
})

test('rejects a lease whose profile does not belong to the account', () => {
  assert.throws(
    () => parseAccountLease(JSON.stringify({ ...lease, profile_key: 'douyin:acct_other' })),
    /does not match/,
  )
})

test('rejects path traversal in account identifiers', () => {
  assert.throws(
    () => parseAccountLease(JSON.stringify({ ...lease, account_id: '../../shared' })),
    /invalid lease account_id/,
  )
  assert.throws(
    () => parseAccountLease(JSON.stringify({ ...lease, account_id: '..', profile_key: 'douyin:..' })),
    /invalid lease account_id/,
  )
})

test('derives one profile directory from the trusted lease', () => {
  assert.equal(
    profileDirectory(lease, '/browser-profiles'),
    path.join('/browser-profiles', 'douyin', 'acct_ab3145'),
  )
})

test('keeps Playwright artifacts outside the source workspace', () => {
  assert.equal(
    outputDirectory(lease, '/browser-output'),
    path.join('/browser-output', 'douyin', 'acct_ab3145'),
  )
})

test('purges only the deleted account profile and output', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'marketing-browser-purge-'))
  const profileRoot = path.join(root, 'profiles')
  const outputRoot = path.join(root, 'output')
  const profile = profileDirectory(lease, profileRoot)
  const output = outputDirectory(lease, outputRoot)
  const sibling = path.join(profileRoot, 'douyin', 'acct_sibling')
  await Promise.all([
    fs.mkdir(profile, { recursive: true }),
    fs.mkdir(output, { recursive: true }),
    fs.mkdir(sibling, { recursive: true }),
  ])

  await purgeAccountDirectories(lease, profileRoot, outputRoot)

  await assert.rejects(fs.stat(profile))
  await assert.rejects(fs.stat(output))
  assert.equal((await fs.stat(sibling)).isDirectory(), true)
  await fs.rm(root, { recursive: true, force: true })
})
