const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('marketingOS', {
  // Hermes API
  api: (method, path, body) => ipcRenderer.invoke('hermes:api', { method, path, body }),

  // Hermes 状态
  getHermesStatus: () => ipcRenderer.invoke('hermes:status'),
  restartHermes: () => ipcRenderer.invoke('hermes:restart'),
  onHermesStatus: (cb) => {
    const h = (_e, d) => cb(d)
    ipcRenderer.on('hermes:status', h)
    return () => ipcRenderer.removeListener('hermes:status', h)
  },

  // 内嵌浏览器登录
  openLoginBrowser: (platform) => ipcRenderer.invoke('login:open', platform),
  closeLoginBrowser: (platform) => ipcRenderer.invoke('login:close', platform),
  getLoginCookies: (platform) => ipcRenderer.invoke('login:cookies', platform),
  scrapeIndustry: (platform, keyword) => ipcRenderer.invoke('session:scrape-industry', { platform, keyword }),
  syncAccountSession: (platform, username) => ipcRenderer.invoke('session:sync-account', { platform, username }),
  runIntelligence: () => ipcRenderer.invoke('intelligence:run'),
  onIntelligenceProgress: (cb) => { const h = (_e, d) => cb(d); ipcRenderer.on('intelligence:progress', h); return () => ipcRenderer.removeListener('intelligence:progress', h) },
  getChannelStatus: () => ipcRenderer.invoke('channels:status'),
  connectChannel: (platform) => ipcRenderer.invoke('channels:connect', platform),
  testChannel: (platform) => ipcRenderer.invoke('channels:test', platform),
  retryChannel: (deliveryId) => ipcRenderer.invoke('channels:retry', deliveryId),
  onChannelProgress: (cb) => { const h = (_e, d) => cb(d); ipcRenderer.on('channels:progress', h); return () => ipcRenderer.removeListener('channels:progress', h) },

  // 登录事件监听
  onLoginOpened: (cb) => { const h = (_e, d) => cb(d); ipcRenderer.on('login:opened', h); return () => ipcRenderer.removeListener('login:opened', h) },
  onLoginClosed: (cb) => { const h = (_e, d) => cb(d); ipcRenderer.on('login:closed', h); return () => ipcRenderer.removeListener('login:closed', h) },
  onLoginCookies: (cb) => { const h = (_e, d) => cb(d); ipcRenderer.on('login:cookies', h); return () => ipcRenderer.removeListener('login:cookies', h) },
})
