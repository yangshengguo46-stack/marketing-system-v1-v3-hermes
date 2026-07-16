import { createRequire } from 'node:module'
import { Server } from '@modelcontextprotocol/sdk/server/index.js'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'
import { CallToolRequestSchema, ListToolsRequestSchema } from '@modelcontextprotocol/sdk/types.js'
import { installAccountAuthTool } from './account-auth.js'
import { installDouyinPortfolioTool } from './douyin-owned.js'
import { installShortVideoSignalTool } from './short-video-signals.js'
import { installPublicContentTool } from './public-content.js'
import { installWechatOfficialPortfolioTool } from './wechat-official.js'

const require = createRequire(import.meta.url)
const { tools } = require('playwright-core/lib/coreBundle')
installAccountAuthTool()
installDouyinPortfolioTool()
installShortVideoSignalTool()
installPublicContentTool()
installWechatOfficialPortfolioTool()

export function playwrightToolSchemas() {
  return tools.filteredTools({
    capabilities: ['core', 'network', 'pdf', 'storage', 'vision'],
  }).map(tool => ({
    name: tool.schema.name,
    title: tool.schema.title,
    description: tool.schema.description,
    inputSchema: tool.schema.inputSchema.toJSONSchema(),
  }))
}

export async function runSchemaServer() {
  const server = new Server(
    { name: 'marketing-browser-schema', version: '0.1.0' },
    { capabilities: { tools: {} } },
  )
  server.setRequestHandler(ListToolsRequestSchema, async () => ({
    tools: playwrightToolSchemas(),
  }))
  server.setRequestHandler(CallToolRequestSchema, async () => ({
    isError: true,
    content: [{ type: 'text', text: 'schema-only connection cannot execute browser tools' }],
  }))
  await server.connect(new StdioServerTransport())
}
