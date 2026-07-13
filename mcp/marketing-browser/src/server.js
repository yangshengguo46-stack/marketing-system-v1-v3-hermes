#!/usr/bin/env node

import { createConnection } from '@playwright/mcp'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'
import { chromium } from 'playwright'
import {
  outputDirectory,
  parseAccountLease,
  profileDirectory,
  migrateLegacyProfile,
  purgeAccountDirectories,
} from './account-lease.js'
import { resolveBrowserExecutable } from './browser-runtime.js'
import { installAccountAuthTool } from './account-auth.js'
import { installDouyinPortfolioTool } from './douyin-owned.js'
import { installShortVideoSignalTool } from './short-video-signals.js'
import { installWechatOfficialPortfolioTool } from './wechat-official.js'

installAccountAuthTool()
installDouyinPortfolioTool()
installShortVideoSignalTool()
installWechatOfficialPortfolioTool()

if (process.argv.includes('--purge-profile')) {
  const lease = parseAccountLease()
  await purgeAccountDirectories(lease)
} else if (process.argv.includes('--schema-only')) {
  const { runSchemaServer } = await import('./schema-server.js')
  await runSchemaServer()
} else {
  const lease = parseAccountLease()
  await migrateLegacyProfile(lease)
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
  const shutdownAndExit = () => void closeRuntime().finally(() => process.exit(0))
  server.onclose = closeRuntime
  // The MCP SDK's stdio server transport does not close itself when the
  // parent ends stdin. Flush the persistent BrowserContext before the
  // client reaches its SIGTERM fallback, otherwise login cookies can vanish.
  process.stdin.once('end', shutdownAndExit)
  process.once('SIGINT', shutdownAndExit)
  process.once('SIGTERM', shutdownAndExit)

  await server.connect(new StdioServerTransport())
}
