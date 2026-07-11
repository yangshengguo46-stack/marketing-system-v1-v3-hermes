#!/usr/bin/env node

import { createConnection } from '@playwright/mcp'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'
import { chromium } from 'playwright'
import { outputDirectory, parseAccountLease, profileDirectory } from './account-lease.js'
import { resolveBrowserExecutable } from './browser-runtime.js'

if (process.argv.includes('--schema-only')) {
  const { runSchemaServer } = await import('./schema-server.js')
  await runSchemaServer()
} else {
  const lease = parseAccountLease()
  const profile = profileDirectory(lease)
  const outputDir = outputDirectory(lease)
  const executablePath = resolveBrowserExecutable()
  const context = await chromium.launchPersistentContext(profile, {
    headless: process.env.HERMES_BROWSER_HEADED !== '1',
    ...(executablePath ? { executablePath } : {}),
  })

  const server = await createConnection(
    {
      browser: { isolated: false },
      capabilities: ['core', 'network', 'pdf', 'storage', 'vision'],
      outputDir,
      saveSession: false,
    },
    async () => context,
  )

  let closing = false
  const closeRuntime = async () => {
    if (closing) return
    closing = true
    await context.close().catch(() => {})
  }
  server.onclose = closeRuntime
  process.once('SIGINT', () => void closeRuntime().finally(() => process.exit(0)))
  process.once('SIGTERM', () => void closeRuntime().finally(() => process.exit(0)))

  await server.connect(new StdioServerTransport())
}
