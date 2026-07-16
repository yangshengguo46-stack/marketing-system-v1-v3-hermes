import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js'
import { resolveBrowserExecutable } from '../src/browser-runtime.js'

const executable = resolveBrowserExecutable()

test('flushes one account profile before MCP shutdown and recovers it', {
  skip: !executable,
  // Two real browser startups routinely take 13-15s on an idle machine and
  // can cross 20s while the desktop regression suite is running in parallel.
  timeout: 30_000,
}, async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'marketing-browser-restart-'))
  const entry = fileURLToPath(new URL('../src/server.js', import.meta.url))
  const lease = {
    session_id: 'session-restart',
    user_id: 'default',
    account_id: 'acct-restart',
    platform: 'zhihu',
    profile_key: 'zhihu:acct-restart',
    auth_state: 'authenticated',
  }
  const env = {
    ...process.env,
    HERMES_MARKETING_ACCOUNT_LEASE: JSON.stringify(lease),
    HERMES_BROWSER_PROFILE_ROOT: path.join(root, 'profiles'),
    HERMES_BROWSER_OUTPUT_ROOT: path.join(root, 'output'),
    HERMES_BROWSER_EXECUTABLE: executable,
  }

  async function withBrowser(run) {
    const transport = new StdioClientTransport({
      command: process.execPath,
      args: [entry],
      env,
    })
    const client = new Client({ name: 'restart-test', version: '1.0.0' })
    await client.connect(transport)
    try {
      return await run(client)
    } finally {
      await client.close()
    }
  }

  try {
    const expires = Math.floor(Date.now() / 1000) + 3600
    const stored = await withBrowser(client => client.callTool({
      name: 'browser_cookie_set',
      arguments: {
        name: 'marketing_os_restart',
        value: 'kept',
        domain: 'example.com',
        path: '/',
        expires,
      },
    }))
    assert.notEqual(stored.isError, true)

    const recovered = await withBrowser(client => client.callTool({
      name: 'browser_cookie_get',
      arguments: { name: 'marketing_os_restart' },
    }))
    const output = recovered.content?.map(block => block.text || '').join('\n') || ''
    assert.notEqual(recovered.isError, true)
    assert.match(output, /kept/)
  } finally {
    await fs.rm(root, { recursive: true, force: true })
  }
})
