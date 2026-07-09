const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('marketingOS', {
  // Marketing Agent Runtime API
  runtimeApi: (method, path, body) => ipcRenderer.invoke('runtime:api', { method, path, body }),

  // Marketing Agent Runtime 状态
  getRuntimeStatus: () => ipcRenderer.invoke('runtime:status'),
  restartRuntime: () => ipcRenderer.invoke('runtime:restart'),
  onRuntimeStatus: (cb) => {
    const h = (_e, d) => cb(d)
    ipcRenderer.on('runtime:status', h)
    return () => ipcRenderer.removeListener('runtime:status', h)
  },
  setProviderSecret: (name, value) => ipcRenderer.invoke('provider:set-secret', { name, value }),
  openAttribution: (url) => ipcRenderer.invoke('app:open-attribution', url),

  // 内嵌浏览器登录（旧路径，feature flag 关闭时使用）
  openLoginBrowser: (platform, accountId) => ipcRenderer.invoke('login:open', { platform, account_id: accountId }),
  closeLoginBrowser: (platform, accountId) => ipcRenderer.invoke('login:close', { platform, account_id: accountId }),

  // MCP headed login（MCP-06，feature flag 开启时使用）
  mcpLoginStart: (account_id, platform) => ipcRenderer.invoke('mcp-login:start', { account_id, platform }),
  mcpLoginStatus: (account_id) => ipcRenderer.invoke('mcp-login:status', { account_id }),
  mcpLoginCancel: (account_id, login_attempt_id) => ipcRenderer.invoke('mcp-login:cancel', { account_id, login_attempt_id }),
  mcpBrowserTakeover: (account_id) => ipcRenderer.invoke('mcp-browser:takeover', { account_id }),
  mcpBrowserBackground: (account_id) => ipcRenderer.invoke('mcp-browser:background', { account_id }),
  mcpBrowserStop: (account_id) => ipcRenderer.invoke('mcp-browser:stop', { account_id }),
  closeAllLoginBrowsers: () => ipcRenderer.invoke('login:close-all'),
  navigateLoginBrowser: (platform, accountId, action) => ipcRenderer.invoke('login:navigate', { platform, account_id: accountId, action }),
  getLoginCookies: (platform, accountId) => ipcRenderer.invoke('login:cookies', { platform, account_id: accountId }),
  runIntelligence: () => ipcRenderer.invoke('intelligence:run'),
  onIntelligenceProgress: (cb) => { const h = (_e, d) => cb(d); ipcRenderer.on('intelligence:progress', h); return () => ipcRenderer.removeListener('intelligence:progress', h) },
  onTrendingUpdated: (cb) => { const h = (_e, d) => cb(d); ipcRenderer.on('trending:updated', h); return () => ipcRenderer.removeListener('trending:updated', h) },
  getChannelStatus: () => ipcRenderer.invoke('channels:status'),
  connectChannel: (platform) => ipcRenderer.invoke('channels:connect', platform),
  cancelChannel: (platform) => ipcRenderer.invoke('channels:cancel', platform),
  testChannel: (platform) => ipcRenderer.invoke('channels:test', platform),
  retryChannel: (deliveryId) => ipcRenderer.invoke('channels:retry', deliveryId),
  onChannelProgress: (cb) => { const h = (_e, d) => cb(d); ipcRenderer.on('channels:progress', h); return () => ipcRenderer.removeListener('channels:progress', h) },

  // 登录事件监听
  onLoginOpened: (cb) => { const h = (_e, d) => cb(d); ipcRenderer.on('login:opened', h); return () => ipcRenderer.removeListener('login:opened', h) },
  onLoginClosed: (cb) => { const h = (_e, d) => cb(d); ipcRenderer.on('login:closed', h); return () => ipcRenderer.removeListener('login:closed', h) },
  onLoginCookies: (cb) => { const h = (_e, d) => cb(d); ipcRenderer.on('login:cookies', h); return () => ipcRenderer.removeListener('login:cookies', h) },
  onLoginQr: (cb) => { const h = (_e, d) => cb(d); ipcRenderer.on('login:qr', h); return () => ipcRenderer.removeListener('login:qr', h) },
  onLoginError: (cb) => { const h = (_e, d) => cb(d); ipcRenderer.on('login:error', h); return () => ipcRenderer.removeListener('login:error', h) },
  onLoginInteraction: (cb) => { const h = (_e, d) => cb(d); ipcRenderer.on('login:interaction', h); return () => ipcRenderer.removeListener('login:interaction', h) },

  // Agent SSE stream — main process proxies SSE events to renderer
  streamAgentEvents: (taskId) => ipcRenderer.invoke('agent:stream-events', taskId),
  stopAgentEvents: (taskId) => ipcRenderer.invoke('agent:stop-events', taskId),
  onAgentEvent: (cb) => { const h = (_e, d) => cb(d); ipcRenderer.on('agent:event', h); return () => ipcRenderer.removeListener('agent:event', h) },

  // Account health & diagnostics
  checkAccountHealth: (platform, username, accountId) => ipcRenderer.invoke('account:health', { platform, username, account_id: accountId }),
  syncAccountMetrics: (accountId) => ipcRenderer.invoke('account:sync', { account_id: accountId }),
  clearAccountSession: (platform, accountId) => ipcRenderer.invoke('account:clear', { platform, account_id: accountId }),
  runNetworkDiagnostic: () => ipcRenderer.invoke('app:networkDiagnostic'),

  // Capability bridge: main process validates approval + canonical arguments
  // before touching an Electron session. The renderer never supplies either.
  executeApprovedCapability: (approvalId, scope) =>
    ipcRenderer.invoke('agent:execute-approved-capability', { approvalId, scope }),
  importMediaAttachment: (assetId) => ipcRenderer.invoke('media:import', { assetId }),
  importStockImage: (assetId, candidate) => ipcRenderer.invoke('media:import-stock-image', { assetId, candidate }),
  deleteMediaAttachmentForAsset: (assetId) => ipcRenderer.invoke('media:delete-for-asset', { assetId }),
})
