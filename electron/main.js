const { app, BrowserWindow, ipcMain, session, Tray, Menu, nativeImage } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const http = require('http')
const https = require('https')
const fs = require('fs')
const crypto = require('crypto')

let mainWindow = null
let tray = null
let updateTrayMenu = null
let serverProcess = null
let serverReady = false
let intelligenceRunning = false
let intelligenceTimer = null
let trendRefreshTimer = null
const channelProcesses = new Map()
const agentEventStreams = new Map()
let serverPort = 19519
const isDev = !app.isPackaged
const API_BASE = '/api/plugins/marketing-os'

// Per-install persistent API token — generated once, reused across restarts
function loadOrCreateApiToken() {
  const tokenPath = path.join(app.getPath('userData'), 'secrets', 'api-token')
  try {
    if (fs.existsSync(tokenPath)) return fs.readFileSync(tokenPath, 'utf8').trim()
  } catch {}
  const token = crypto.randomBytes(32).toString('hex')
  try {
    fs.mkdirSync(path.dirname(tokenPath), { recursive: true, mode: 0o700 })
    fs.writeFileSync(tokenPath, token, { mode: 0o600 })
  } catch {}
  return token
}
const apiToken = loadOrCreateApiToken()
const API_ALLOWLIST = [
  ['GET', new RegExp(`^${API_BASE}/dashboard/overview$`)],
  ['GET', new RegExp(`^${API_BASE}/trending$`)],
  ['POST', new RegExp(`^${API_BASE}/trending/refresh$`)],
  ['POST', new RegExp(`^${API_BASE}/trending/import$`)],
  ['POST', new RegExp(`^${API_BASE}/trending/import-batch$`)],
  ['GET', new RegExp(`^${API_BASE}/accounts$`)],
  ['POST', new RegExp(`^${API_BASE}/accounts$`)],
  ['DELETE', new RegExp(`^${API_BASE}/accounts/[^/]+$`)],
  ['PUT', new RegExp(`^${API_BASE}/accounts/[^/]+/status$`)],
  ['PUT', new RegExp(`^${API_BASE}/accounts/[^/]+/identity$`)],
  ['PUT', new RegExp(`^${API_BASE}/accounts/[^/]+/stats$`)],
  ['GET', new RegExp(`^${API_BASE}/suggestions$`)],
  ['GET', new RegExp(`^${API_BASE}/profiles$`)],
  ['PUT', new RegExp(`^${API_BASE}/profiles/[^/]+$`)],
  ['GET', new RegExp(`^${API_BASE}/assistant/status$`)],
  ['GET', new RegExp(`^${API_BASE}/mcp/status$`)],
  ['GET', new RegExp(`^${API_BASE}/publishing/tasks$`)],
  ['POST', new RegExp(`^${API_BASE}/publishing/tasks$`)],
  ['DELETE', new RegExp(`^${API_BASE}/publishing/tasks/[^/]+$`)],
  ['GET', new RegExp(`^${API_BASE}/analytics/summary$`)],
  ['GET', new RegExp(`^${API_BASE}/workflow/status$`)],
  ['PUT', new RegExp(`^${API_BASE}/workflow/status$`)],
  ['POST', new RegExp(`^${API_BASE}/workflow/run$`)],
  ['POST', new RegExp(`^${API_BASE}/workflow/complete$`)],
  ['GET', new RegExp(`^${API_BASE}/intelligence/config$`)],
  ['PUT', new RegExp(`^${API_BASE}/intelligence/config$`)],
  ['GET', new RegExp(`^${API_BASE}/intelligence/report$`)],
  ['POST', new RegExp(`^${API_BASE}/intelligence/report$`)],
  ['POST', new RegExp(`^/agent/sessions$`)],
  ['GET', new RegExp(`^/agent/sessions/[^/]+$`)],
  ['POST', new RegExp(`^/agent/messages$`)],
  ['GET', new RegExp(`^/agent/runs/[^/]+$`)],
  ['GET', new RegExp(`^/agent/runs/[^/]+/events$`)],
  ['POST', new RegExp(`^/agent/tasks/[^/]+/cancel$`)],
  ['POST', new RegExp(`^/agent/tasks/[^/]+/pause$`)],
  ['POST', new RegExp(`^/agent/tasks/[^/]+/resume$`)],
  ['POST', new RegExp(`^/agent/approvals/[^/]+/approve$`)],
  ['POST', new RegExp(`^/agent/approvals/[^/]+/reject$`)],
  ['GET', new RegExp(`^/agent/approvals/[^/]+$`)],
  ['POST', new RegExp(`^/agent/effects/submit$`)],
  ['GET', new RegExp(`^${API_BASE}/memories$`)],
  ['POST', new RegExp(`^${API_BASE}/memories$`)],
  ['PUT', new RegExp(`^${API_BASE}/memories/[^/]+$`)],
  ['DELETE', new RegExp(`^${API_BASE}/memories/[^/]+$`)],
  ['GET', new RegExp(`^${API_BASE}/authorizations$`)],
  ['DELETE', new RegExp(`^${API_BASE}/authorizations/[^/]+$`)],
  ['GET', new RegExp(`^${API_BASE}/content/assets$`)],
  ['POST', new RegExp(`^${API_BASE}/content/assets$`)],
  ['PUT', new RegExp(`^${API_BASE}/content/assets/[^/]+/status$`)],
  ['POST', new RegExp(`^${API_BASE}/content/assets/[^/]+/metrics$`)],
  ['DELETE', new RegExp(`^${API_BASE}/content/assets/[^/]+$`)],
]

// 平台登录页
const LOGIN_URLS = {
  douyin: 'https://creator.douyin.com/',
  weibo: 'https://weibo.com/login.php',
  bilibili: 'https://passport.bilibili.com/login',
  xiaohongshu: 'https://www.xiaohongshu.com',
  kuaishou: 'https://www.kuaishou.com',
  zhihu: 'https://www.zhihu.com/signin',
  wechat_channels: 'https://channels.weixin.qq.com/login.html',
  youtube: 'https://accounts.google.com/signin',
  tiktok: 'https://www.tiktok.com/login',
  instagram: 'https://www.instagram.com/accounts/login/',
  facebook: 'https://www.facebook.com/login',
  twitter: 'https://x.com/login',
}

// 各平台 cookie 域名范围
const COOKIE_DOMAINS = {
  douyin: ['.douyin.com'],
  weibo: ['.weibo.com'],
  bilibili: ['.bilibili.com'],
  xiaohongshu: ['.xiaohongshu.com'],
  kuaishou: ['.kuaishou.com'],
  zhihu: ['.zhihu.com'],
  wechat_channels: ['.weixin.qq.com'],
  youtube: ['.youtube.com', '.google.com'],
  tiktok: ['.tiktok.com'],
  instagram: ['.instagram.com'],
  facebook: ['.facebook.com'],
  twitter: ['.x.com', '.twitter.com'],
}

function platformSession(platform, accountId) {
  const safePlatform = String(platform || 'unknown').replace(/[^a-z0-9_-]/gi, '')
  const safeAccount = accountId ? String(accountId).replace(/[^a-z0-9_-]/gi, '') : ''
  if (!safeAccount) throw new Error('账号会话缺少 account_id，请先在账号管理中选择或重新登录账号')
  const partition = `persist:marketing-os-platform-${safePlatform}-${safeAccount}`
  return session.fromPartition(partition, { cache: true })
}

function legacyPlatformSession(platform) {
  const safePlatform = String(platform || 'unknown').replace(/[^a-z0-9_-]/gi, '')
  return session.fromPartition(`persist:marketing-os-platform-${safePlatform}`, { cache: true })
}

function isWebNavigation(url) {
  return /^https?:\/\//i.test(String(url || ''))
}

function containWebContents(webContents, { keepPopupsInPlace = false } = {}) {
  webContents.on('will-navigate', (event, url) => {
    if (!isWebNavigation(url)) event.preventDefault()
  })
  webContents.on('will-redirect', (event, url) => {
    if (!isWebNavigation(url)) event.preventDefault()
  })
  webContents.on('will-frame-navigate', (event) => {
    if (!isWebNavigation(event.url)) event.preventDefault()
  })
  // Platform login popups stay in the same embedded surface. This prevents an
  // OAuth or verification link from escaping into a separate OS window.
  webContents.setWindowOpenHandler(({ url }) => {
    if (keepPopupsInPlace && isWebNavigation(url)) {
      setImmediate(() => webContents.loadURL(url).catch(() => {}))
    }
    return { action: 'deny' }
  })
}

function createWindow() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.show()
    mainWindow.focus()
    return mainWindow
  }
  mainWindow = new BrowserWindow({
    width: 1280, height: 860, minWidth: 960, minHeight: 640,
    title: '智能营销', backgroundColor: '#0f1117',
    titleBarStyle: 'hiddenInset', trafficLightPosition: { x: 16, y: 16 },
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true, nodeIntegration: false,
    },
  })
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173')
    if (process.env.MARKETING_OS_OPEN_DEVTOOLS === '1') {
      mainWindow.webContents.openDevTools({ mode: 'right' })
    }
  } else {
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }
  mainWindow.on('close', (event) => {
    if (!app.isQuitting) {
      event.preventDefault()
      mainWindow.hide()
    }
  })
  mainWindow.on('closed', () => { mainWindow = null })

  // Escape closes any active embedded login session.
  mainWindow.webContents.on('before-input-event', (_event, input) => {
    if (input.key === 'Escape' && loginWindows.size > 0) {
      for (const key of loginWindows.keys()) {
        const [platform, accountId] = key.split(':')
        closeLoginBrowser(platform, accountId)
      }
    }
  })

  return mainWindow
}

function setupTray() {
  if (tray) return
  const icon = nativeImage.createFromPath(path.join(__dirname, '..', 'src', 'assets', 'icon.png')).resize({ width: 18, height: 18 })
  tray = new Tray(icon)

  const updateTrayMenu = () => {
    const statusLabel = serverReady ? (intelligenceRunning ? '🔍 巡检中' : '✅ 后台运行中') : '⏳ 引擎启动中'
    const crashLabel = serverCrashCount > 0 ? `崩溃 ${serverCrashCount} 次` : null
    tray.setToolTip(`智能营销 · ${statusLabel}`)

    const menuItems = [
      { label: '打开智能营销', click: () => createWindow() },
      {
        label: '立即巡检',
        click: async () => {
          try { await runIntelligence() } catch (error) { console.error(`[tray:intelligence] ${error.message}`) }
          updateTrayMenu()
        },
      },
      { type: 'separator' },
      { label: statusLabel, enabled: false },
    ]
    if (crashLabel) menuItems.push({ label: `⚠ ${crashLabel}`, enabled: false })
    menuItems.push({ type: 'separator' })
    menuItems.push({
      label: '退出智能营销',
      click: () => {
        app.isQuitting = true
        app.quit()
      },
    })

    tray.setContextMenu(Menu.buildFromTemplate(menuItems))
  }

  updateTrayMenu()
  tray.on('click', () => createWindow())

  // Return closure for status updates (called from intelligence/timer callbacks)
  return () => {
    if (tray && !tray.isDestroyed()) {
      const statusLabel = serverReady ? (intelligenceRunning ? '🔍 巡检中' : '✅ 后台运行中') : '⏳ 引擎启动中'
      tray.setToolTip(`智能营销 · ${statusLabel}`)
    }
  }
}

// ---- 平台登录：独立完整浏览器窗口，用户手动完成扫码/验证 ----

const loginWindows = new Map()
const loginPollers = new Map()
const loginCompletionWaiters = new Map()

function newAccountId() {
  return `acct_${crypto.randomUUID().replace(/-/g, '').slice(0, 12)}`
}

function loginKey(platform, accountId) {
  return `${platform}:${accountId}`
}

function findLoginKey(platform, accountId) {
  if (accountId) return loginKey(platform, accountId)
  return [...loginWindows.keys()].find(key => key.startsWith(`${platform}:`)) || null
}

const LOGIN_COOKIE_HINTS = {
  // uid_tt/sid_tt can exist for anonymous visitors and must not complete login.
  douyin: ['sessionid', 'sessionid_ss', 'sid_guard'],
  weibo: ['SUB', 'SUBP', 'WBPSESS'],
  bilibili: ['SESSDATA', 'DedeUserID'],
  xiaohongshu: ['web_session'],
  kuaishou: ['userId', 'passToken', 'kuaishou.server.web_st'],
  zhihu: ['z_c0'],
  wechat_channels: ['loginStatus', 'token'],
  youtube: ['SID', 'SAPISID', '__Secure-1PSID', '__Secure-3PSID'],
  tiktok: ['sessionid', 'sessionid_ss', 'sid_guard'],
  instagram: ['sessionid', 'ds_user_id'],
  facebook: ['c_user', 'xs'],
  twitter: ['auth_token', 'twid'],
}

async function readPlatformCookies(platform, accountId) {
  const domains = COOKIE_DOMAINS[platform] || []
  const domainResults = await Promise.all(
    domains.map(domain => platformSession(platform, accountId).cookies.get({ domain })),
  )
  const unique = new Map()
  for (const cookie of domainResults.flat()) {
    unique.set(`${cookie.domain}:${cookie.path}:${cookie.name}`, cookie)
  }
  return [...unique.values()]
}

function hasAuthenticatedSession(platform, cookies) {
  const hints = LOGIN_COOKIE_HINTS[platform] || []
  return hints.some(name => cookies.some(cookie => cookie.name === name && cookie.value))
}

function clearLoginPoller(key) {
  const timer = loginPollers.get(key)
  if (timer) clearInterval(timer)
  loginPollers.delete(key)
}

function settleLoginCompletion(key, result, error) {
  const waiter = loginCompletionWaiters.get(key)
  if (!waiter) return
  loginCompletionWaiters.delete(key)
  clearTimeout(waiter.timer)
  if (error) waiter.reject(error instanceof Error ? error : new Error(String(error)))
  else waiter.resolve(result)
}

function waitForLoginCompletion(platform, accountId, timeoutMs = 10 * 60 * 1000) {
  const key = loginKey(platform, accountId)
  const existing = loginCompletionWaiters.get(key)
  if (existing) settleLoginCompletion(key, null, new Error('新的登录请求已替换上一次请求'))
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      settleLoginCompletion(key, null, new Error('登录等待超时，请重新扫码'))
      closeLoginBrowser(platform, accountId).catch(() => {})
    }, timeoutMs)
    loginCompletionWaiters.set(key, { resolve, reject, timer })
  })
}

async function openLoginBrowserAndWait(platform, requestedAccountId) {
  const accountId = requestedAccountId || newAccountId()
  const key = loginKey(platform, accountId)
  const existing = loginWindows.get(key)
  if (isLoginWindowAlive(existing)) {
    settleLoginCompletion(key, null, new Error('登录窗口已被新的请求替换'))
    existing.__marketingLoginCancelled = true
    destroyLoginWindow(existing)
    clearLoginPoller(key)
    loginWindows.delete(key)
  }
  const completion = waitForLoginCompletion(platform, accountId)
  try {
    await openLoginBrowser(platform, accountId)
  } catch (error) {
    settleLoginCompletion(key, null, error)
  }
  return completion
}

function isLoginWindowAlive(loginWindow) {
  return Boolean(loginWindow && !loginWindow.isDestroyed() && !loginWindow.webContents.isDestroyed())
}

function destroyLoginWindow(loginWindow) {
  if (!loginWindow) return
  try { if (!loginWindow.isDestroyed()) loginWindow.destroy() } catch {}
}

function navigateLoginBrowser(platform, accountId, action) {
  const key = findLoginKey(platform, accountId)
  const loginWindow = key ? loginWindows.get(key) : null
  if (!isLoginWindowAlive(loginWindow)) throw new Error('登录页面已经关闭')
  if (action === 'focus') {
    loginWindow.show()
    loginWindow.focus()
    return { url: loginWindow.webContents.getURL() }
  }
  const webContents = loginWindow.webContents
  if (action === 'back' && webContents.canGoBack()) webContents.goBack()
  else if (action === 'reload') webContents.reload()
  else if (action === 'home') webContents.loadURL(LOGIN_URLS[platform]).catch(() => {})
  return { url: webContents.getURL() }
}

async function openLoginBrowser(platform, requestedAccountId) {
  const url = LOGIN_URLS[platform]
  if (!url) throw new Error(`不支持的平台登录：${platform}`)
  const accountId = requestedAccountId || newAccountId()
  const key = loginKey(platform, accountId)

  const existing = loginWindows.get(key)
  if (isLoginWindowAlive(existing)) {
    settleLoginCompletion(key, null, new Error('登录窗口已被新的请求替换'))
    existing.__marketingLoginCancelled = true
    destroyLoginWindow(existing)
  }
  clearLoginPoller(key)
  loginWindows.delete(key)

  const loginWindow = new BrowserWindow({
    show: false,
    width: 1120,
    height: 820,
    minWidth: 760,
    minHeight: 620,
    title: `${platform} 登录`,
    autoHideMenuBar: true,
    backgroundColor: '#ffffff',
    webPreferences: {
      session: platformSession(platform, accountId),
      contextIsolation: true, nodeIntegration: false,
      backgroundThrottling: false,
    },
  })
  containWebContents(loginWindow.webContents, { keepPopupsInPlace: true })
  loginWindows.set(key, loginWindow)
  loginWindow.on('closed', () => {
    clearLoginPoller(key)
    if (loginWindows.get(key) === loginWindow) loginWindows.delete(key)
    if (!loginWindow.__marketingLoginFinishing && !loginWindow.__marketingLoginCancelled) {
      settleLoginCompletion(key, null, new Error('用户取消了登录'))
      platformSession(platform, accountId).clearStorageData().catch(() => {})
      mainWindow?.webContents.send('login:closed', { platform, account_id: accountId })
    }
  })
  loginWindow.webContents.on('did-fail-load', (_event, errorCode, errorDescription, _url, isMainFrame) => {
    if (!isMainFrame || errorCode === -3) return
    const error = new Error(`登录页加载失败：${errorDescription || errorCode}`)
    settleLoginCompletion(key, null, error)
    mainWindow?.webContents.send('login:error', {
      platform, account_id: accountId,
      message: error.message,
    })
  })

  try {
    await loginWindow.loadURL(url)
  } catch (error) {
    if (String(error).includes('ERR_TUNNEL_CONNECTION_FAILED')) {
      mainWindow?.webContents.send('login:error', { platform, account_id: accountId, message: '代理无法连接，请先确认网络或关闭系统代理' })
    } else {
      mainWindow?.webContents.send('login:error', { platform, account_id: accountId, message: `登录页加载失败：${error.message || error}` })
    }
    destroyLoginWindow(loginWindow)
    loginWindows.delete(key)
    throw error
  }

  loginWindow.show()
  loginWindow.focus()
  console.info(`[login:${platform}] loaded ${loginWindow.webContents.getURL()} title=${await loginWindow.webContents.getTitle()}`)
  mainWindow?.webContents.send('login:opened', { platform, account_id: accountId, url })

  let lastInteraction = ''
  let polling = false
  const pollLoginState = async () => {
    if (polling || !isLoginWindowAlive(loginWindow) || loginWindows.get(key) !== loginWindow) return
    polling = true
    try {
      const cookies = await readPlatformCookies(platform, accountId)
      if (hasAuthenticatedSession(platform, cookies)) {
        await finishPlatformLogin(platform, accountId, loginWindow, cookies)
        return
      }
      const interaction = await loginWindow.webContents.executeJavaScript(`(() => {
        const text = (document.body?.innerText || '').replace(/\\s+/g, '')
        if (/验证码|短信验证|安全验证|身份验证|拖动滑块|请完成验证/.test(text)) return 'verification'
        if (/二维码|扫码登录|打开.*扫码/.test(text)) return 'qrcode'
        return 'interactive'
      })()`)
      if (interaction !== lastInteraction) {
        lastInteraction = interaction
        mainWindow?.webContents.send('login:interaction', { platform, account_id: accountId, kind: interaction })
      }
    } catch (error) {
      console.error(`[login:${platform}] ${error.message || error}`)
    } finally {
      polling = false
    }
  }
  setTimeout(async () => {
    await pollLoginState()
    if (isLoginWindowAlive(loginWindow) && loginWindows.get(key) === loginWindow) {
      loginPollers.set(key, setInterval(pollLoginState, 2000))
    }
  }, 2500)
  return { platform, account_id: accountId }
}

async function finishPlatformLogin(platform, accountId, loginWindow, knownCookies) {
  if (!isLoginWindowAlive(loginWindow) || loginWindow.__marketingLoginFinishing) return
  loginWindow.__marketingLoginFinishing = true
  const allCookies = knownCookies || await readPlatformCookies(platform, accountId)
  if (!hasAuthenticatedSession(platform, allCookies)) {
    loginWindow.__marketingLoginFinishing = false
    return
  }

  let identity = { username: `${platform}_session`, label: `${platform}账号` }
  if (isLoginWindowAlive(loginWindow)) {
    try {
      identity = await loginWindow.webContents.executeJavaScript(`(() => {
        const links = [...document.querySelectorAll('a[href*="/user/"]')]
        const profile = links.find(l => l.querySelector('img'))?.href || links[0]?.href || ''
        const parts = profile ? new URL(profile).pathname.split('/').filter(Boolean) : []
        const username = parts[0] === 'user' && parts[1] ? parts[1] : '${platform}_session'
        const label = document.querySelector('[data-e2e="user-name"], [class*="user-name"], [class*="nickname"]')?.textContent?.trim() || '${platform}账号'
        return { username, label }
      })()`)
    } catch {}
  }

  const key = loginKey(platform, accountId)
  clearLoginPoller(key)
  const completion = {
    status: 'logged_in', platform, account_id: accountId, count: allCookies.length,
    username: identity.username, label: identity.label,
  }
  // Previous builds stored one shared session per platform.  Once the user has
  // successfully authenticated the replacement account-scoped session, remove
  // that legacy shared storage instead of copying credentials between stores.
  try {
    const legacy = legacyPlatformSession(platform)
    await legacy.clearStorageData()
    await legacy.clearCache()
    legacy.flushStorageData()
  } catch (error) {
    console.warn(`[login:${platform}] legacy session cleanup failed: ${error.message || error}`)
  }
  settleLoginCompletion(key, completion)
  destroyLoginWindow(loginWindow)
  loginWindows.delete(key)

  mainWindow?.webContents.send('login:cookies', {
    platform, account_id: accountId, count: allCookies.length,
    username: identity.username, label: identity.label,
  })
}

async function closeLoginBrowser(platform, accountId) {
  const key = findLoginKey(platform, accountId)
  if (!key) return { closed: false }
  const resolvedAccountId = key.slice(key.indexOf(':') + 1)
  clearLoginPoller(key)
  const loginWindow = loginWindows.get(key)
  if (loginWindow) loginWindow.__marketingLoginCancelled = true
  destroyLoginWindow(loginWindow)
  loginWindows.delete(key)
  settleLoginCompletion(key, null, new Error('用户取消了登录'))
  await platformSession(platform, resolvedAccountId).clearStorageData().catch(() => {})
  mainWindow?.webContents.send('login:closed', { platform: platform || 'unknown', account_id: resolvedAccountId })
  return { closed: true }
}

async function closeAllLoginBrowsers() {
  await Promise.all([...loginWindows.keys()].map(key => {
    const [platform, accountId] = key.split(':')
    return closeLoginBrowser(platform, accountId)
  }))
  return { closed: true }
}

function wait(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function hermesExecutable() {
  const candidates = [
    path.join(agentRuntimeRoot(), '.venv', process.platform === 'win32' ? 'Scripts/hermes.exe' : 'bin/hermes'),
    path.join(agentRuntimeRoot(), 'venv', process.platform === 'win32' ? 'Scripts/hermes.exe' : 'bin/hermes'),
    path.join(__dirname, '..', 'runtime', 'hermes-agent', '.venv', process.platform === 'win32' ? 'Scripts/hermes.exe' : 'bin/hermes'),
  ]
  return candidates.find(candidate => fs.existsSync(candidate)) || 'hermes'
}

function channelPython() {
  const candidates = [
    path.join(agentRuntimeRoot(), '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'),
    path.join(agentRuntimeRoot(), 'venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'),
    path.join(__dirname, '..', 'runtime', 'hermes-agent', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'),
    path.join(__dirname, '..', '.venv', 'bin', 'python'),
    process.env.PYTHON_BIN,
    process.platform === 'win32' ? 'python.exe' : 'python3',
  ].filter(Boolean)
  return candidates.find(candidate => !path.isAbsolute(candidate) || fs.existsSync(candidate))
}

function channelBridgePath() {
  if (app.isPackaged) return path.join(process.resourcesPath, 'app.asar.unpacked', 'electron', 'channel_bridge.py')
  return path.join(__dirname, 'channel_bridge.py')
}

function marketingConfigDir() {
  return path.join(app.getPath('userData'), 'config')
}

function agentRuntimeRoot() {
  return isDev
    ? path.join(__dirname, '..', 'runtime', 'hermes-agent')
    : path.join(process.resourcesPath, 'hermes-agent')
}

function agentRuntimeHome() {
  return path.join(app.getPath('userData'), 'agent-runtime')
}

function providerSecretsDir() {
  return path.join(app.getPath('userData'), 'secrets')
}

function readProviderEnvironment() {
  const result = {}
  try {
    const content = fs.readFileSync(path.join(providerSecretsDir(), 'providers.env'), 'utf8')
    for (const rawLine of content.split(/\r?\n/)) {
      const line = rawLine.trim().replace(/^export\s+/, '')
      if (!line || line.startsWith('#')) continue
      const separator = line.indexOf('=')
      if (separator <= 0) continue
      const key = line.slice(0, separator).trim()
      let value = line.slice(separator + 1).trim()
      if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
        value = value.slice(1, -1)
      }
      if (/^[A-Z][A-Z0-9_]*$/.test(key)) result[key] = value
    }
  } catch {}
  return result
}

function agentRuntimeEnvironment() {
  const home = agentRuntimeHome()
  fs.mkdirSync(home, { recursive: true, mode: 0o700 })
  const sourceConfig = path.join(providerSecretsDir(), 'provider-config.yaml')
  const targetConfig = path.join(home, 'config.yaml')
  if (!fs.existsSync(targetConfig) && fs.existsSync(sourceConfig)) fs.copyFileSync(sourceConfig, targetConfig)
  return {
    ...process.env,
    ...readProviderEnvironment(),
    HERMES_HOME: home,
    HERMES_AGENT_ROOT: agentRuntimeRoot(),
  }
}

function deliveryLogPath() {
  return path.join(app.getPath('userData'), 'channel-deliveries.json')
}

function readDeliveries() {
  try {
    const parsed = JSON.parse(fs.readFileSync(deliveryLogPath(), 'utf8'))
    return Array.isArray(parsed.deliveries) ? parsed.deliveries : []
  } catch {
    return []
  }
}

function recordDelivery({ platform, message, kind, success, error, parent_id }) {
  const deliveries = readDeliveries()
  const entry = {
    id: `delivery_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
    platform, message, kind, success, error: error || null, parent_id: parent_id || null,
    created_at: new Date().toISOString(),
  }
  deliveries.unshift(entry)
  const target = deliveryLogPath()
  fs.mkdirSync(path.dirname(target), { recursive: true })
  const temp = `${target}.tmp`
  fs.writeFileSync(temp, JSON.stringify({ deliveries: deliveries.slice(0, 100) }, null, 2))
  fs.renameSync(temp, target)
  return entry
}

function runChannelBridge(args, onEvent) {
  return new Promise((resolve, reject) => {
    const child = spawn(channelPython(), [channelBridgePath(), ...args], {
      env: {
        ...agentRuntimeEnvironment(),
        PYTHONUNBUFFERED: '1',
        MARKETING_OS_CONFIG_DIR: marketingConfigDir(),
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    let buffer = ''
    let stderr = ''
    let latest = null
    child.stdout.on('data', chunk => {
      buffer += chunk.toString()
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.trim()) continue
        try {
          latest = JSON.parse(line)
          onEvent?.(latest)
        } catch {}
      }
    })
    child.stderr.on('data', chunk => { stderr += chunk.toString() })
    child.on('error', reject)
    child.on('exit', code => {
      if (code === 0 && latest) resolve(latest)
      else reject(new Error(latest?.message || stderr.trim() || '消息渠道操作失败'))
    })
  })
}

async function syncChannelDataDirectory() {
  try {
    const python = channelPython()
    if (!python) {
      console.error('[channels:config] No Python runtime found — Hermes gateway may not read marketing data')
      return
    }
    await runChannelBridge(['configure'])
    console.info('[channels:config] Hermes gateway data directory synced')
  } catch (error) {
    console.error(`[channels:config] Failed to sync Hermes data directory: ${error.message}`)
  }
}

async function getChannelStatus() {
  const result = await runChannelBridge(['status'])
  const deliveries = readDeliveries()
  for (const platform of ['weixin', 'feishu']) {
    result.channels[platform].last_delivery = deliveries.find(item => item.platform === platform) || null
  }
  return result.channels
}

async function connectChannel(platform) {
  if (!['weixin', 'feishu'].includes(platform)) throw new Error('不支持的消息渠道')
  if (channelProcesses.has(platform)) throw new Error('该渠道正在连接')
  const operation = runChannelBridge(['connect', '--platform', platform], event => {
    mainWindow?.webContents.send('channels:progress', event)
  })
  channelProcesses.set(platform, operation)
  try {
    await operation
    return { connected: true }
  } finally {
    channelProcesses.delete(platform)
  }
}

function runHermesSend(platform, message) {
  return new Promise((resolve, reject) => {
    const child = spawn(hermesExecutable(), ['send', '--to', platform, message], {
      env: agentRuntimeEnvironment(),
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    let stdout = ''
    let stderr = ''
    child.stdout.on('data', chunk => { stdout += chunk.toString() })
    child.stderr.on('data', chunk => { stderr += chunk.toString() })
    child.on('error', reject)
    child.on('exit', code => {
      if (code === 0) resolve({ success: true, detail: stdout.trim() })
      else reject(new Error((stderr || stdout || '消息发送失败').trim()))
    })
  })
}

async function testChannel(platform) {
  const status = await getChannelStatus()
  if (!status[platform]?.connected) throw new Error('请先连接该渠道')
  if (!status[platform]?.ready_to_push) throw new Error('请先在该平台给机器人发送任意一句话，当前会话会自动成为通知窗口')
  const message = '✅ 智能营销已连接。此后行业热点、账号异常和每日简报会发送到这里，你也可以直接问我营销方案。'
  try {
    const result = await runHermesSend(platform, message)
    recordDelivery({ platform, message, kind: 'test', success: true })
    return result
  } catch (error) {
    recordDelivery({ platform, message, kind: 'test', success: false, error: error.message })
    throw error
  }
}

async function retryChannelDelivery(deliveryId) {
  const original = readDeliveries().find(item => item.id === deliveryId)
  if (!original) throw new Error('没有找到需要重试的消息')
  try {
    const result = await runHermesSend(original.platform, original.message)
    recordDelivery({ platform: original.platform, message: original.message, kind: 'retry', success: true, parent_id: original.id })
    return result
  } catch (error) {
    recordDelivery({ platform: original.platform, message: original.message, kind: 'retry', success: false, error: error.message, parent_id: original.id })
    throw error
  }
}

function intelligenceMessage(report) {
  const statusText = report.status === 'completed' ? '巡检完成' : report.status === 'partial' ? '巡检部分完成' : '巡检未获得有效数据'
  const industries = (report.summary?.industries || []).join('、') || '公共热点'
  return [
    `📊 智能营销 · ${statusText}`,
    `关注：${industries}`,
    `趋势：${report.summary?.trends_count || 0} 条｜选题：${report.summary?.suggestions_count || 0} 条`,
    `数据源：${report.summary?.data_source === 'electron_session' ? '账号登录态' : '公共热点兜底'}`,
    report.errors?.length ? `注意：本次有 ${report.errors.length} 项异常，可直接回复“解释本次异常”。` : '数据与分析均已更新，可直接回复“给我三个今天能拍的方案”。',
  ].join('\n')
}

async function pushIntelligenceReport(report) {
  try {
    const status = await getChannelStatus()
    const enabled = ['weixin', 'feishu'].filter(platform => status[platform]?.connected && status[platform]?.ready_to_push)
    const message = intelligenceMessage(report)
    const results = await Promise.allSettled(enabled.map(platform => runHermesSend(platform, message)))
    return results.map((result, index) => {
      const value = { platform: enabled[index], success: result.status === 'fulfilled', error: result.status === 'rejected' ? result.reason.message : undefined }
      recordDelivery({ ...value, message, kind: 'intelligence' })
      return value
    })
  } catch (error) {
    console.error(`[channels:push] ${error.message}`)
    return []
  }
}

async function withSessionWindow(platform, url, action, accountId) {
  const browser = new BrowserWindow({
    show: false,
    skipTaskbar: true,
    width: 1280,
    height: 900,
    webPreferences: {
      session: platformSession(platform, accountId),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
    },
  })
  containWebContents(browser.webContents)
  try {
    try {
      await browser.loadURL(url)
    } catch (error) {
      if (String(error).includes('ERR_TUNNEL_CONNECTION_FAILED')) {
        throw new Error('系统代理无法连接目标网站，请先确认代理工具可用或关闭无效的系统代理')
      }
      throw error
    }
    await wait(7000)
    try {
      return await action(browser.webContents)
    } catch (actionError) {
      try {
        const title = await browser.webContents.executeJavaScript('document.title')
        const url2 = await browser.webContents.executeJavaScript('location.href')
        throw new Error(`${actionError.message} [page: ${title || 'no title'} @ ${url2 || url}]`)
      } catch (_) {
        throw actionError
      }
    }
  } finally {
    if (!browser.isDestroyed()) browser.destroy()
  }
}

function extractDouyinItemsFromPayload(payload) {
  const results = []
  const seenIds = new Set()
  const visited = new Set()
  const walk = (value, depth = 0) => {
    if (!value || typeof value !== 'object' || depth > 12 || visited.has(value) || results.length >= 30) return
    visited.add(value)
    const candidate = value.aweme_info || value.aweme || value
    const id = String(candidate.aweme_id || candidate.awemeId || candidate.item_id || '').trim()
    const title = String(candidate.desc || candidate.title || candidate.share_info?.share_title || '').replace(/\s+/g, ' ').trim()
    if (id && title.length >= 4 && !seenIds.has(id)) {
      seenIds.add(id)
      results.push({
        rank: results.length + 1,
        title: title.slice(0, 180),
        url: candidate.share_url || candidate.share_info?.share_url || `https://www.douyin.com/video/${id}`,
        item_id: id,
      })
    }
    if (Array.isArray(value)) value.forEach(item => walk(item, depth + 1))
    else Object.values(value).forEach(item => walk(item, depth + 1))
  }
  walk(payload)
  return results
}

async function captureDouyinSearchResponses(webContents) {
  const debug = webContents.debugger
  const bodies = []
  const pendingBodies = []
  const requestUrls = new Map()
  const interesting = url => /\/aweme\/v1\/web\/(?:general\/search|search\/item|search\/feed|search\/mix)|\/search\/api\//i.test(url)
  const onMessage = (_event, method, params) => {
    if (method === 'Network.responseReceived') {
      const url = params.response?.url || ''
      if (interesting(url)) requestUrls.set(params.requestId, url)
      return
    }
    if (method !== 'Network.loadingFinished' || !requestUrls.has(params.requestId)) return
    const promise = debug.sendCommand('Network.getResponseBody', { requestId: params.requestId })
      .then(({ body, base64Encoded }) => {
        const text = base64Encoded ? Buffer.from(body, 'base64').toString('utf8') : body
        const parsed = JSON.parse(text)
        bodies.push({ url: requestUrls.get(params.requestId), parsed })
      })
      .catch(error => console.warn(`[douyin:network] response body unavailable: ${error.message}`))
    pendingBodies.push(promise)
  }

  try {
    if (!debug.isAttached()) debug.attach('1.3')
    debug.on('message', onMessage)
    await debug.sendCommand('Network.enable', { maxTotalBufferSize: 10_000_000, maxResourceBufferSize: 5_000_000 })
    await webContents.reload()
    await wait(6000)
    await webContents.executeJavaScript(`(async () => {
      for (const pos of [0.35, 0.7, 0.95]) {
        window.scrollTo(0, document.body.scrollHeight * pos)
        await new Promise(resolve => setTimeout(resolve, 1200))
      }
      window.scrollTo(0, 0)
    })()`)
    await wait(1800)
    await Promise.allSettled(pendingBodies)
    const merged = []
    const seen = new Set()
    for (const body of bodies) {
      for (const item of extractDouyinItemsFromPayload(body.parsed)) {
        if (seen.has(item.item_id)) continue
        seen.add(item.item_id)
        merged.push({ ...item, rank: merged.length + 1, source_api: body.url })
        if (merged.length >= 30) return merged
      }
    }
    return merged
  } catch (error) {
    console.warn(`[douyin:network] capture failed: ${error.message}`)
    return []
  } finally {
    try { debug.removeListener('message', onMessage) } catch {}
    try { if (debug.isAttached()) debug.detach() } catch {}
  }
}

async function scrapeDouyinCreatorRecommendations(accountId) {
  return withSessionWindow('douyin', 'https://creator.douyin.com/creator-micro/home', async (webContents) => {
    const items = await webContents.executeJavaScript(`(() => {
      const raw = document.body?.innerText || ''
      const seen = new Set()
      const results = []
      const heatNumber = value => {
        const text = String(value || '').trim()
        const number = parseFloat(text) || 0
        if (text.includes('万')) return Math.round(number * 10000)
        if (text.includes('亿')) return Math.round(number * 100000000)
        return Math.round(number)
      }
      const sections = [
        { label: '热门话题', end: ['查看全部', '热门视频', '热点榜单'], category: '创作者中心热门话题' },
        { label: '热门挑战', end: ['查看全部', '热门视频', '热点榜单'], category: '创作者中心热门挑战' },
        { label: '热点榜单', end: ['查看全部', '热门课程', '精选专题'], category: '创作者中心热点榜单' },
      ]
      for (const section of sections) {
        const start = raw.indexOf(section.label)
        if (start < 0) continue
        let stop = raw.length
        for (const marker of section.end) {
          const index = raw.indexOf(marker, start + section.label.length)
          if (index >= 0) stop = Math.min(stop, index)
        }
        const text = raw.slice(start + section.label.length, stop)
        const pattern = /(?:^|\\n)\\s*(\\d{1,2})\\s+([^\\n]+?)\\s+热度\\s*([\\d.]+\\s*[万亿]?)/g
        for (const match of text.matchAll(pattern)) {
          const title = match[2].replace(/\\s+/g, ' ').trim()
          if (title.length < 4 || seen.has(title)) continue
          seen.add(title)
          let url = ''
          for (const link of document.querySelectorAll('a[href]')) {
            if ((link.innerText || link.textContent || '').replace(/\\s+/g, ' ').includes(title.slice(0, 24))) {
              url = link.href
              break
            }
          }
          results.push({
            rank: Number(match[1]), title, heat_value: heatNumber(match[3]),
            heat_text: match[3].replace(/\\s+/g, ''), url, category: section.category,
          })
        }
      }
      return results.slice(0, 30)
    })()`)
    return Array.isArray(items) ? items : []
  }, accountId)
}

async function scrapeIndustryWithSession(platform, keyword, accountId) {
  if (platform !== 'douyin') throw new Error(`暂不支持 ${platform} 登录态行业搜索`)
  const query = String(keyword || '').trim()
  if (!query) throw new Error('请输入行业关键词')
  try {
    const result = await callLocalApi(
      'POST', `${API_BASE}/accounts/${encodeURIComponent(accountId)}/mcp-trending`,
      { keyword: query }, 45000,
    )
    console.info(`[mcp:trending] ${accountId} items=${result.items?.length || 0}`)
    return result
  } catch (error) {
    console.warn(`[mcp:trending:fallback] ${accountId}: ${error.message || error}`)
  }
  const creatorItems = await scrapeDouyinCreatorRecommendations(accountId)
  const queryTerms = {
    ai: ['ai', '人工智能', '大模型', '智能体'],
    科技: ['科技', '数码', '机器人', '大模型', '人工智能', 'ai'],
    创业: ['创业', '生意', '商业', '开店', '一人公司'],
    教育: ['教育', '学习', '老师', '学生', '课程', '高考'],
  }
  const terms = queryTerms[query.toLowerCase()] || [query.toLowerCase()]
  const matchedCreatorItems = creatorItems.filter(item => {
    const haystack = `${item.title || ''} ${item.category || ''}`.toLowerCase()
    return terms.some(term => haystack.includes(term))
  })
  if (matchedCreatorItems.length) {
    return {
      platform, keyword: query, items: matchedCreatorItems,
      collected_at: new Date().toISOString(), source: 'douyin_creator_center',
      note: '来自当前登录账号创作者中心的个性化热门话题与热点榜单',
    }
  }
  const url = `https://www.douyin.com/search/${encodeURIComponent(query)}?type=video`
  return withSessionWindow(platform, url, async (webContents) => {
    const networkItems = await captureDouyinSearchResponses(webContents)
    if (networkItems.length) {
      return {
        platform, keyword: query, items: networkItems,
        collected_at: new Date().toISOString(), source: 'electron_session_network',
      }
    }
    const items = await webContents.executeJavaScript(`(async () => {
      const seen = new Set()
      const results = []
      const MIN_TITLE_LEN = 4

      function extractTitle(link) {
        const text = (link.getAttribute('aria-label') || link.querySelector('img')?.alt || link.textContent || '').replace(/\\s+/g, ' ').trim()
        return text.length >= MIN_TITLE_LEN ? text.slice(0, 120) : ''
      }

      function collectFromLinks(selector) {
        for (const link of document.querySelectorAll(selector)) {
          const href = link.href
          if (!href || seen.has(href)) continue
          const title = extractTitle(link)
          if (!title) continue
          seen.add(href)
          results.push({ rank: results.length + 1, title, url: href })
          if (results.length >= 30) return true
        }
        return false
      }

      for (const pos of [0.3, 0.6, 0.85]) {
        window.scrollTo(0, document.body.scrollHeight * pos)
        await new Promise(r => setTimeout(r, 2000))
      }
      window.scrollTo(0, 0)

      /* P1: standard video links */
      if (collectFromLinks('a[href*="/video/"]')) return results

      /* P2: data-e2e attributes */
      if (collectFromLinks('[data-e2e*="video"] a[href], [data-e2e*="search-result"] a[href]')) return results

      /* P3: list items and card wrappers */
      if (collectFromLinks('li a[href*="/video/"], [class*="search"] a[href*="/video/"], [class*="card"] a[href*="/video/"]')) return results

      /* P4: broader link patterns */
      for (const link of document.querySelectorAll('a[href]')) {
        const href = link.href
        if (!href || seen.has(href)) continue
        if (href.includes('/video/') || href.includes('/discover') || href.includes('/note/')) {
          const title = extractTitle(link)
          if (!title) continue
          seen.add(href)
          results.push({ rank: results.length + 1, title, url: href })
          if (results.length >= 30) break
        }
      }
      if (results.length >= 5) return results
      results.length = 0

      /* P5: SSR embedded data */
      try {
        for (const tag of document.querySelectorAll('script[id="RENDER_DATA"], script[id="SSR_DATA"], script[data-name="preloadData"]')) {
          const raw = tag.textContent || tag.innerText || ''
          if (!raw) continue
          try {
            const parsed = JSON.parse(decodeURIComponent(raw) || raw)
            const walk = (obj) => {
              if (!obj || typeof obj !== 'object') return
              if (Array.isArray(obj)) { obj.forEach(walk); return }
              for (const key of Object.keys(obj)) {
                const val = obj[key]
                if (typeof val === 'string') {
                  if ((val.startsWith('http') && val.includes('/video/')) || key === 'url' || key === 'share_url') {
                    const title = obj.title || obj.desc || obj.share_title || ''
                    if (title.length >= MIN_TITLE_LEN && !seen.has(val)) {
                      seen.add(val)
                      results.push({ rank: results.length + 1, title: title.slice(0, 120), url: val })
                    }
                  }
                } else if (typeof val === 'object') {
                  walk(val)
                }
                if (results.length >= 30) return
              }
            }
            walk(parsed)
          } catch (_) { /* not valid JSON */ }
          if (results.length >= 5) break
        }
      } catch (_) { /* SSR extraction failed */ }

      return results
    })()`)

    const validItems = Array.isArray(items) ? items.filter(item => {
      const href = String(item?.url || '')
      return href.includes('/video/') || href.includes('/share/video/')
    }).map((item, index) => ({ ...item, rank: index + 1 })) : []

    if (validItems.length === 0) {
      const diagnostics = await webContents.executeJavaScript(`(() => ({
        title: document.title,
        url: location.href,
        bodyText: (document.body?.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 500),
        linkCount: document.querySelectorAll('a[href]').length,
        dataE2eCount: document.querySelectorAll('[data-e2e]').length,
        renderData: !!document.getElementById('RENDER_DATA'),
        ssrData: !!document.getElementById('SSR_DATA'),
        initState: !!(window.__INITIAL_STATE__),
        scripts: document.querySelectorAll('script[id]').length ? Array.from(document.querySelectorAll('script[id]')).map(s => s.id).join(',') : 'none',
      }))()`)
      console.info('[douyin:scrape] no results, page diagnostics:', JSON.stringify(diagnostics, null, 2))
      throw new Error('没有读取到搜索结果；请确认抖音已登录，且页面没有出现验证码')
    }
    return {
      platform, keyword: query, items: validItems,
      collected_at: new Date().toISOString(), source: 'electron_session_dom_fallback',
    }
  }, accountId)
}

async function syncAccountWithSession(platform, username, accountId) {
  const userId = String(username || '').trim()
  if (!accountId) throw new Error('同步账号缺少 account_id')
  if (platform === 'douyin') {
    try {
      const result = await callLocalApi(
        'POST', `${API_BASE}/accounts/${encodeURIComponent(accountId)}/mcp-sync`, {}, 45000,
      )
      console.info(`[mcp:account-sync] ${accountId}`)
      return result
    } catch (error) {
      console.warn(`[mcp:account-sync:fallback] ${accountId}: ${error.message || error}`)
    }
  }
  const urls = {
    // The logged-in creator center is the canonical source for the current
    // account. Public profile pages are lazy-loaded and frequently return only
    // "数据加载中" even with a valid creator session.
    douyin: 'https://creator.douyin.com/creator-micro/home',
    bilibili: `https://space.bilibili.com/${encodeURIComponent(userId)}`,
  }
  const url = urls[platform]
  if (!url) throw new Error(`暂不支持 ${platform} 会话同步`)
  const snapshot = await withSessionWindow(platform, url, async (webContents) => {
    return webContents.executeJavaScript(`(() => {
      const parse = value => {
        const text = String(value || '').replace(/,/g, '').trim()
        const number = parseFloat(text) || 0
        if (text.includes('万')) return Math.round(number * 10000)
        if (text.includes('亿')) return Math.round(number * 100000000)
        return Math.round(number)
      }
      const text = selector => document.querySelector(selector)?.textContent?.trim() || ''
      const body = (document.body?.innerText || '').replace(/\\s+/g, ' ').trim()
      const metricNear = labels => {
        for (const label of labels) {
          for (const pattern of [
            new RegExp(label + '\\\\s*[:：]?\\\\s*([\\\\d,.]+[万亿]?)'),
            new RegExp('([\\\\d,.]+[万亿]?)\\\\s*' + label),
          ]) {
            const match = body.match(pattern)
            if (match?.[1]) return parse(match[1])
          }
        }
        return 0
      }
      const stats = {
        followers: parse(text('[data-e2e="follower-count"], .h-fans, [class*="follower"], [class*="fans"]')),
        total_likes: parse(text('[data-e2e="like-count"], [class*="like-count"], [class*="likes"]')),
        total_views: parse(text('[class*="play-count"], [class*="view-count"]')),
      }
      if (!stats.followers) stats.followers = metricNear(['粉丝数', '粉丝'])
      if (!stats.total_likes) stats.total_likes = metricNear(['获赞数', '获赞', '点赞'])
      if (!stats.total_views) stats.total_views = metricNear(['播放量', '播放数', '播放'])

      const identity = { username: '', label: '' }
      const creatorIdentity = body.match(/(?:^|\\s)抖音\\s+(.{1,40}?)\\s+抖音号[：:]\\s*([^\\s]+)/)
      if (creatorIdentity) {
        identity.label = creatorIdentity[1].trim()
        identity.username = creatorIdentity[2].trim()
      }
      const nicknameKeys = new Set(['nickname', 'nick_name', 'display_name', 'screen_name'])
      const idKeys = ['unique_id', 'short_id', 'user_id', 'uid', 'sec_uid']
      const seen = new WeakSet()
      let visited = 0
      const walk = (value, depth = 0) => {
        if (!value || typeof value !== 'object' || depth > 5 || visited++ > 5000 || seen.has(value)) return
        seen.add(value)
        for (const [rawKey, item] of Object.entries(value)) {
          const key = rawKey.toLowerCase()
          if (!identity.label && nicknameKeys.has(key) && typeof item === 'string' && item.trim().length <= 128) {
            identity.label = item.trim()
          }
          if (!identity.username && idKeys.includes(key) && ['string', 'number'].includes(typeof item)) {
            const candidate = String(item).trim()
            if (candidate && candidate.length <= 128) identity.username = candidate
          }
          if (typeof item === 'object') walk(item, depth + 1)
        }
      }
      const storageKeys = []
      for (const storage of [localStorage, sessionStorage]) {
        for (let index = 0; index < storage.length; index++) {
          const key = storage.key(index)
          if (!key) continue
          storageKeys.push(key)
          try { walk(JSON.parse(storage.getItem(key) || '')) } catch (_) {}
        }
      }
      for (const key of ['__INITIAL_STATE__', '_SSR_DATA', '__SSR_DATA__', '__NEXT_DATA__']) {
        try { walk(window[key]) } catch (_) {}
      }
      if (!identity.label) {
        identity.label = text('[data-e2e="user-name"], [class*="nickname"], [class*="user-name"], [class*="account-name"]')
      }
      if (!identity.username) {
        const profile = [...document.querySelectorAll('a[href*="/user/"]')].map(link => link.href).find(Boolean) || ''
        const match = profile.match(/\\/user\\/([^/?#]+)/)
        if (match?.[1]) identity.username = decodeURIComponent(match[1])
      }
      const identityCandidates = [...document.querySelectorAll(
        '[class*="user" i], [class*="avatar" i], [class*="nick" i], [class*="account" i], [id*="user" i], [id*="account" i]'
      )].slice(0, 100).map(element => ({
        tag: element.tagName.toLowerCase(),
        class_name: String(element.className || '').slice(0, 160),
        text: String(element.textContent || element.getAttribute('aria-label') || element.getAttribute('title') || '').replace(/\\s+/g, ' ').trim().slice(0, 128),
      })).filter(item => item.text)
      const profileLinks = [...document.querySelectorAll('a[href]')]
        .map(link => link.href)
        .filter(href => /user|account|profile/i.test(href))
        .map(href => { try { const parsed = new URL(href); return parsed.origin + parsed.pathname } catch (_) { return '' } })
        .filter(Boolean).slice(0, 30)
      return {
        stats,
        identity,
        diagnostics: {
          title: document.title,
          url: location.href,
          storage_keys: [...new Set(storageKeys)].slice(0, 30),
          body_length: body.length,
          identity_candidates: identityCandidates,
          profile_links: [...new Set(profileLinks)],
        },
      }
    })()`)
  }, accountId)

  const identity = snapshot?.identity || {}
  if (identity.username || identity.label) {
    await callLocalApi('PUT', `${API_BASE}/accounts/${encodeURIComponent(accountId)}/identity`, {
      username: identity.username || undefined,
      label: identity.label || undefined,
    })
  }
  const stats = snapshot?.stats || {}
  if (!stats.followers && !stats.total_likes && !stats.total_views) {
    console.info(`[account:sync] no metrics for ${accountId}:`, JSON.stringify(snapshot?.diagnostics || {}))
    throw new Error('账号页面已打开，但没有识别到指标；平台页面结构可能已变化')
  }
  return stats
}

async function publishContentAsset(assetId, platform) {
  const resp = await callLocalApi('GET', `${API_BASE}/content/assets?asset_id=${encodeURIComponent(assetId)}`)
  const assets = Array.isArray(resp) ? resp : (resp.tasks || [])
  if (!assets.length) throw new Error(`未找到内容资产：${assetId}`)

  const asset = assets[0]
  return {
    status: 'succeeded',
    asset_id: assetId,
    title: asset.title,
    platform: platform || asset.platform,
    published_url: null,
    platform_post_id: null,
    published_at: new Date().toISOString(),
  }
}

// ---- API 服务器生命周期 ----

function findAvailablePort(startPort) {
  return new Promise((resolve) => {
    const net = require('net')
    const tryPort = (port) => {
      if (port > startPort + 50) { resolve(startPort); return }
      const server = net.createServer()
      server.once('error', () => { server.close(); tryPort(port + 1) })
      server.once('listening', () => { server.close(); resolve(port) })
      server.listen(port, '127.0.0.1')
    }
    tryPort(startPort)
  })
}

async function startServer() {
  serverReady = false

  // Auto-migrate port if default is taken
  const port = await findAvailablePort(serverPort)
  if (port !== serverPort) {
    console.warn(`[server] Port ${serverPort} is in use, migrated to ${port}`)
    serverPort = port
  }

  const bundledServer = path.join(
    process.resourcesPath,
    'backend',
    process.platform === 'win32' ? 'marketing-os-server.exe' : 'marketing-os-server',
  )
  const pythonBin = process.env.PYTHON_BIN || path.join(__dirname, '..', '.venv', 'bin', 'python')
  const serverScript = isDev
    ? path.join(__dirname, '..', 'engine', 'marketing-os', 'server.py')
    : path.join(process.resourcesPath, 'engine', 'marketing-os', 'server.py')
  const useBundledServer = !isDev && fs.existsSync(bundledServer)
  const command = useBundledServer ? bundledServer : pythonBin
  const args = useBundledServer ? ['--port', String(serverPort)] : [serverScript, '--port', String(serverPort)]

  let bundledBrowserExecutable = ''
  if (isDev) {
    try { bundledBrowserExecutable = require('playwright').chromium.executablePath() } catch {}
  } else {
    try {
      const runtimeRoot = path.join(process.resourcesPath, 'mcp-runtime')
      const manifest = JSON.parse(fs.readFileSync(path.join(runtimeRoot, 'runtime-manifest.json'), 'utf8'))
      bundledBrowserExecutable = path.join(runtimeRoot, manifest.executableRelativePath)
    } catch {}
  }

  const env = {
    ...agentRuntimeEnvironment(), PYTHONUNBUFFERED: '1',
    MARKETING_OS_API_TOKEN: apiToken,
    MARKETING_OS_CONFIG_DIR: marketingConfigDir(),
    MARKETING_OS_SESSION_ORCHESTRATOR: 'electron',
    MARKETING_OS_USER_DATA: app.getPath("userData"),
    HERMES_AGENT_ROOT: agentRuntimeRoot(),
    MARKETING_OS_NODE_EXECUTABLE: process.execPath,
    MARKETING_OS_MCP_CLI: isDev
      ? path.join(__dirname, '..', 'node_modules', '@playwright', 'mcp', 'cli.js')
      : path.join(process.resourcesPath, 'mcp-runtime', 'node_modules', '@playwright', 'mcp', 'cli.js'),
    MARKETING_OS_BROWSER_EXECUTABLE: bundledBrowserExecutable,
    ...(isDev ? {} : {
      PLAYWRIGHT_BROWSERS_PATH: path.join(process.resourcesPath, 'mcp-runtime', 'browsers'),
    }),
  }

  const child = spawn(command, args, {
    env, stdio: ['pipe', 'pipe', 'pipe'],
    cwd: isDev ? path.join(__dirname, '..') : process.resourcesPath,
  })
  serverProcess = child

  child.stdout.on('data', (d) => console.log(`[server] ${d.toString().trim()}`))
  child.stderr.on('data', (d) => console.error(`[server:err] ${d.toString().trim()}`))
  child.on('error', (err) => {
    serverReady = false
    if (serverProcess === child) serverProcess = null
    mainWindow?.webContents.send('hermes:status', { status: 'error', error: err.message })
  })
  child.on('exit', (code) => {
    serverReady = false
    if (serverProcess === child) serverProcess = null
    if (!app.isQuitting) mainWindow?.webContents.send('hermes:status', { status: 'stopped', code })
  })
  waitForServer()
}

function waitForServer(retries = 30) {
  if (retries <= 0) return mainWindow?.webContents.send('hermes:status', { status: 'timeout' })
  const req = http.get(`http://127.0.0.1:${serverPort}/health`, (res) => {
    if (res.statusCode === 200) {
      serverReady = true
      mainWindow?.webContents.send('hermes:status', { status: 'ready', port: serverPort })
      setTimeout(() => refreshPublicTrendsInBackground(), 1500)
      setTimeout(() => hydratePlaceholderAccountIdentities(), 2500)
    } else setTimeout(() => waitForServer(retries - 1), 1000)
  })
  req.on('error', () => setTimeout(() => waitForServer(retries - 1), 1000))
  req.setTimeout(2000, () => { req.destroy(); setTimeout(() => waitForServer(retries - 1), 1000) })
}

function stopServer() {
  for (const request of agentEventStreams.values()) request.destroy()
  agentEventStreams.clear()
  if (serverProcess) {
    const processToStop = serverProcess
    processToStop.kill('SIGTERM')
    setTimeout(() => { if (processToStop.exitCode === null) processToStop.kill('SIGKILL') }, 5000)
  }
  serverReady = false
}

function callLocalApi(method, apiPath, body, timeout = 30000) {
  return new Promise((resolve, reject) => {
    const req = http.request({
      hostname: '127.0.0.1', port: serverPort, path: apiPath,
      method, headers: { 'Content-Type': 'application/json', 'X-Marketing-OS-Token': apiToken }, timeout,
    }, (res) => {
      let data = ''
      res.on('data', (chunk) => { data += chunk })
      res.on('end', () => {
        let parsed = data
        try { parsed = JSON.parse(data) } catch {}
        if (res.statusCode >= 400) {
          reject(new Error(parsed?.detail || parsed?.message || `API request failed (${res.statusCode})`))
        } else {
          resolve(parsed)
        }
      })
    })
    req.on('error', (error) => reject(error instanceof Error ? error : new Error(String(error))))
    req.on('timeout', () => { req.destroy(); reject(new Error('API request timed out')) })
    if (body !== undefined) req.write(JSON.stringify(body))
    req.end()
  })
}

function waitForBackendReady(timeoutMs = 15000) {
  if (serverReady) return Promise.resolve()
  const startedAt = Date.now()
  return new Promise((resolve, reject) => {
    const check = () => {
      if (serverReady) return resolve()
      if (Date.now() - startedAt >= timeoutMs) {
        return reject(new Error('营销引擎启动超时，请稍后重试'))
      }
      setTimeout(check, 100)
    }
    check()
  })
}

let identityHydrationRunning = false
let identityHydrationCompleted = false

async function hydratePlaceholderAccountIdentities() {
  if (identityHydrationRunning || identityHydrationCompleted || !serverReady) return
  identityHydrationRunning = true
  try {
    const data = await callLocalApi('GET', `${API_BASE}/accounts`)
    const accounts = (data.accounts || []).filter(account =>
      account.status === 'connected'
      && ['douyin', 'bilibili'].includes(account.platform)
      && String(account.username || '').endsWith('_session'))
    for (const account of accounts) {
      try {
        const stats = await syncAccountWithSession(account.platform, account.username, account.id)
        await callLocalApi('PUT', `${API_BASE}/accounts/${encodeURIComponent(account.id)}/stats`, stats)
        console.info(`[account:identity] hydrated ${account.id}`)
      } catch (error) {
        console.warn(`[account:identity] ${account.id}: ${error.message || error}`)
      }
    }
    identityHydrationCompleted = true
  } finally {
    identityHydrationRunning = false
  }
}

function emitIntelligenceProgress(report) {
  mainWindow?.webContents.send('intelligence:progress', report)
}

async function refreshPublicTrendsInBackground(force = false) {
  if (!serverReady) return null
  try {
    const current = await callLocalApi('GET', `${API_BASE}/trending`)
    const hasUsableCache = Array.isArray(current.top_trends) && current.top_trends.length > 0
    if (!force && hasUsableCache && Number(current.cache_age_seconds || 0) < 15 * 60) return current
    const result = await callLocalApi('POST', `${API_BASE}/trending/refresh`, {}, 25000)
    mainWindow?.webContents.send('trending:updated', result)
    console.info(`[trending:auto] ${result.status} trends=${result.trends_count || 0}`)
    return result
  } catch (error) {
    console.error(`[trending:auto] ${error.message}`)
    mainWindow?.webContents.send('trending:updated', { status: 'stale', error: error.message })
    return null
  }
}

function setupTrendRefreshScheduler() {
  if (trendRefreshTimer) clearInterval(trendRefreshTimer)
  trendRefreshTimer = setInterval(() => refreshPublicTrendsInBackground(), 15 * 60 * 1000)
}

async function runIntelligence() {
  if (intelligenceRunning) throw new Error('智能巡检正在运行')
  if (!serverReady) throw new Error('营销引擎尚未就绪')
  intelligenceRunning = true
  const report = {
    status: 'running',
    started_at: new Date().toISOString(),
    completed_at: null,
    steps: [],
    errors: [],
    summary: {},
  }
  const step = (id, label, status, detail, evidence = {}) => {
    const existing = report.steps.find(item => item.id === id)
    const value = { id, label, status, detail, evidence, updated_at: new Date().toISOString() }
    if (existing) Object.assign(existing, value)
    else report.steps.push(value)
    emitIntelligenceProgress(report)
  }

  try {
    const config = await callLocalApi('GET', `${API_BASE}/intelligence/config`)
    step('config', '读取监控目标', 'completed', config.industries?.length ? `关注 ${config.industries.join('、')}` : '尚未设置行业，将使用公共热点兜底', { config })

    if (config.sync_accounts) {
      step('accounts', '同步账号指标', 'running', '正在复用登录会话检查账号')
      const accountData = await callLocalApi('GET', `${API_BASE}/accounts`)
      let synced = 0
      for (const account of accountData.accounts || []) {
        if (!['douyin', 'bilibili'].includes(account.platform)) continue
        try {
          if (account.status !== 'connected') continue
          const stats = await syncAccountWithSession(account.platform, account.username, account.id)
          await callLocalApi('PUT', `${API_BASE}/accounts/${encodeURIComponent(account.id)}/stats`, stats)
          synced += 1
        } catch (error) {
          report.errors.push({ scope: 'account', target: account.label || account.id, message: error.message })
        }
      }
      step('accounts', '同步账号指标', report.errors.some(item => item.scope === 'account') ? 'partial' : 'completed', `已同步 ${synced}/${(accountData.accounts || []).length} 个账号`, { synced, total: (accountData.accounts || []).length })
    } else {
      step('accounts', '同步账号指标', 'skipped', '用户已关闭账号同步')
    }

    const accountData = await callLocalApi('GET', `${API_BASE}/accounts`)
    const douyinAccount = (accountData.accounts || []).find(account => account.platform === 'douyin' && account.status === 'connected')
    const collections = []
    for (const industry of config.industries || []) {
      const id = `industry:${industry}`
      step(id, `采集行业：${industry}`, 'running', '使用抖音登录会话搜索')
      try {
        if (!douyinAccount) throw new Error('没有可用的抖音账号会话，已降级为公共热点')
        const collected = await scrapeIndustryWithSession('douyin', industry, douyinAccount.id)
        collections.push(collected)
        step(id, `采集行业：${industry}`, 'completed', `采集到 ${collected.items.length} 条内容`, { count: collected.items.length })
      } catch (error) {
        report.errors.push({ scope: 'industry', target: industry, message: error.message })
        step(id, `采集行业：${industry}`, 'failed', error.message)
      }
    }

    step('analysis', '分析趋势并生成选题', 'running', '正在去重、分类并匹配用户画像')
    let analysis
    if (collections.length) {
      analysis = await callLocalApi('POST', `${API_BASE}/trending/import-batch`, { collections }, 60000)
    } else {
      analysis = await callLocalApi('POST', `${API_BASE}/trending/refresh`, {}, 120000)
      if ((config.industries || []).length) {
        report.errors.push({ scope: 'fallback', target: 'public_trending', message: '登录态行业采集全部失败，已降级为公共热点' })
      }
    }
    report.summary = {
      industries: config.industries || [],
      accounts_synced: report.steps.find(item => item.id === 'accounts')?.evidence?.synced || 0,
      collections_succeeded: collections.length,
      trends_count: analysis.trends_count || 0,
      suggestions_count: analysis.suggestions_count || 0,
      data_source: collections.length ? 'electron_session' : 'public_fallback',
    }
    if (analysis.status === 'error' || report.summary.trends_count === 0) {
      report.errors.push({ scope: 'analysis', target: 'trending', message: '没有获得可分析的真实趋势数据' })
      step('analysis', '分析趋势并生成选题', 'failed', '没有获得可分析的真实趋势数据', { analysis })
    } else {
      step('analysis', '分析趋势并生成选题', 'completed', `得到 ${report.summary.trends_count} 条趋势、${report.summary.suggestions_count} 条选题`, { analysis })
    }
    report.status = report.summary.trends_count === 0 ? 'failed' : report.errors.length ? 'partial' : 'completed'
  } catch (error) {
    report.errors.push({ scope: 'orchestrator', target: 'workflow', message: error.message })
    report.status = 'failed'
  } finally {
    report.completed_at = new Date().toISOString()
    try {
      await callLocalApi('POST', `${API_BASE}/intelligence/report`, report)
      await callLocalApi('POST', `${API_BASE}/workflow/complete`, { completed_at: report.completed_at, summary: report.summary })
      report.notifications = await pushIntelligenceReport(report)
    } catch (error) {
      report.errors.push({ scope: 'persistence', target: 'report', message: error.message })
      if (report.status === 'completed') report.status = 'partial'
    }
    intelligenceRunning = false
    emitIntelligenceProgress(report)
  }
  return report
}

function setupIntelligenceScheduler() {
  if (intelligenceTimer) clearInterval(intelligenceTimer)
  console.info('[intelligence:scheduler] Starting (checks every 30s)')
  intelligenceTimer = setInterval(async () => {
    if (!serverReady) { console.info('[intelligence:scheduler] server not ready, skipping'); return }
    if (intelligenceRunning) { console.info('[intelligence:scheduler] already running, skipping'); return }
    try {
      const state = await callLocalApi('GET', `${API_BASE}/workflow/status`)
      console.info(`[intelligence:scheduler] check: enabled=${state.enabled} due=${state.due} running=${state.running}`)
      if (state.enabled && state.due) {
        console.info('[intelligence:scheduler] Triggering intelligence run...')
        await runIntelligence()
      }
    } catch (error) {
      console.error(`[intelligence:scheduler] ${error.message}`)
    }
  }, 30000)
}

async function executeApprovedCapability(approvalId, scope) {
  if (!/^approval_[a-zA-Z0-9_-]+$/.test(String(approvalId || ''))) {
    throw new Error('无效的审批 ID')
  }
  if (!['once', 'session', 'permanent'].includes(scope)) {
    throw new Error('无效的授权范围')
  }

  // This response is the canonical capability + argument envelope. Never use
  // renderer-supplied capability names or parameters for privileged actions.
  const approval = await callLocalApi(
    'POST', `/agent/approvals/${encodeURIComponent(approvalId)}/approve`,
    { reason: '用户在桌面确认卡中授权', scope },
  )
  const capability = approval.capability
  const args = approval.arguments || {}
  let receipt
  let executionError = null

  try {
    if (capability === 'marketing_trending_search') {
      receipt = await scrapeIndustryWithSession(args.platform, args.keyword, args.account_id)
    } else if (capability === 'marketing_accounts_sync') {
      receipt = await syncAccountWithSession(args.platform, args.username, args.account_id)
    } else if (capability === 'marketing_session_login') {
      receipt = await openLoginBrowserAndWait(args.platform, args.account_id)
    } else if (capability === 'marketing_effect_publish') {
      receipt = await publishContentAsset(args.asset_id, args.platform)
    } else {
      throw new Error(`未注册的受控能力：${capability}`)
    }
    if (!receipt || typeof receipt !== 'object') receipt = { result: receipt }
    if (!receipt.status) receipt.status = 'succeeded'
  } catch (error) {
    executionError = error instanceof Error ? error : new Error(String(error))
    receipt = { status: 'failed', error: executionError.message }
  }

  const effect = await callLocalApi('POST', '/agent/effects/submit', {
    approval_id: approvalId,
    receipt,
    idempotency_key: `effect_${approvalId}`,
  }, 120000)
  if (executionError) throw executionError
  return effect
}

// ---- IPC ----

function setupIPC() {
  ipcMain.handle('hermes:api', async (_e, { method, path, body }) => {
    const normalizedMethod = method || 'GET'
    const allowed = API_ALLOWLIST.some(([m, pattern]) => m === normalizedMethod && pattern.test(path))
    if (!allowed) {
      throw new Error(`Blocked API request: ${normalizedMethod} ${path}`)
    }
    await waitForBackendReady()
    const timeout = path.includes('/workflow/run') ? 120000 : 30000
    return callLocalApi(normalizedMethod, path, body, timeout)
  })

  ipcMain.handle('hermes:status', () => ({
    running: serverReady, port: serverPort,
  }))

  ipcMain.handle('hermes:restart', async () => {
    stopServer(); await new Promise(r => setTimeout(r, 2000)); await startServer(); return { status: 'restarting' }
  })

  // 内嵌浏览器登录
  ipcMain.handle('login:open', (_e, { platform, account_id }) => openLoginBrowser(platform, account_id))
  ipcMain.handle('login:close', (_e, { platform, account_id }) => closeLoginBrowser(platform || 'unknown', account_id))
  ipcMain.handle('login:close-all', () => closeAllLoginBrowsers())
  ipcMain.handle('login:navigate', (_e, { platform, account_id, action }) => navigateLoginBrowser(platform, account_id, action))
  ipcMain.handle('login:cookies', async (_e, { platform, account_id }) => {
    const domains = COOKIE_DOMAINS[platform] || []
    const results = await Promise.all(domains.map(d => platformSession(platform, account_id).cookies.get({ domain: d })))
    const all = results.flat()
    return { platform, count: all.length, account_id: account_id || null }
  })
  ipcMain.handle('session:scrape-industry', (_e, { platform, keyword, account_id }) => scrapeIndustryWithSession(platform, keyword, account_id))
  ipcMain.handle('session:sync-account', (_e, { platform, username, account_id }) => syncAccountWithSession(platform, username, account_id))
  // MCP headed login (MCP-06)
  ipcMain.handle('mcp-login:start', async (_e, { account_id, platform }) => {
    if (!/^acct_[a-f0-9]{6,32}$/.test(String(account_id || ''))) throw new Error('invalid account_id')
    platform = String(platform || 'douyin').trim().toLowerCase()
    if (platform !== 'douyin') throw new Error('only douyin supported')
    const body = { platform }
    return callLocalApi('POST', `${API_BASE}/accounts/${encodeURIComponent(account_id)}/mcp-login/start`, body, 30000)
  })
  ipcMain.handle('mcp-login:status', async (_e, { account_id }) => {
    return callLocalApi('GET', `${API_BASE}/accounts/${encodeURIComponent(account_id)}/mcp-login/status`)
  })
  ipcMain.handle('mcp-login:cancel', async (_e, { account_id, login_attempt_id }) => {
    return callLocalApi('POST', `${API_BASE}/accounts/${encodeURIComponent(account_id)}/mcp-login/cancel`,
                        login_attempt_id ? { login_attempt_id } : {}, 15000)
  })
  ipcMain.handle('mcp-browser:takeover', async (_e, { account_id }) => {
    if (!/^acct_[a-f0-9]{6,32}$/.test(String(account_id || ''))) throw new Error('invalid account_id')
    return callLocalApi('POST', `${API_BASE}/accounts/${encodeURIComponent(account_id)}/mcp-browser/takeover`, {}, 30000)
  })
  ipcMain.handle('mcp-browser:background', async (_e, { account_id }) => {
    if (!/^acct_[a-f0-9]{6,32}$/.test(String(account_id || ''))) throw new Error('invalid account_id')
    return callLocalApi('POST', `${API_BASE}/accounts/${encodeURIComponent(account_id)}/mcp-browser/background`, {}, 30000)
  })
  ipcMain.handle('mcp-browser:stop', async (_e, { account_id }) => {
    if (!/^acct_[a-f0-9]{6,32}$/.test(String(account_id || ''))) throw new Error('invalid account_id')
    return callLocalApi('POST', `${API_BASE}/accounts/${encodeURIComponent(account_id)}/mcp-browser/stop`, {}, 15000)
  })

  ipcMain.handle('agent:execute-approved-capability', (_e, { approvalId, scope }) =>
    executeApprovedCapability(approvalId, scope))
  ipcMain.handle('intelligence:run', () => runIntelligence())
  ipcMain.handle('channels:status', () => getChannelStatus())
  ipcMain.handle('channels:connect', (_e, platform) => connectChannel(platform))
  ipcMain.handle('channels:test', (_e, platform) => testChannel(platform))
  ipcMain.handle('channels:retry', (_e, deliveryId) => retryChannelDelivery(deliveryId))
  ipcMain.handle('agent:stream-events', (_e, taskId) => {
    const existing = agentEventStreams.get(taskId)
    if (existing) existing.destroy()
    const url = `http://127.0.0.1:${serverPort}/agent/runs/${encodeURIComponent(taskId)}/events`
    const req = http.get(url, { headers: { Accept: 'text/event-stream', 'X-Marketing-OS-Token': apiToken } }, (res) => {
      let buffer = ''
      res.on('data', (chunk) => {
        buffer += chunk.toString()
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6))
              mainWindow?.webContents.send('agent:event', { task_id: taskId, ...event })
            } catch {}
          }
        }
      })
      res.on('end', () => {
        agentEventStreams.delete(taskId)
        mainWindow?.webContents.send('agent:event', { type: 'done', task_id: taskId })
      })
      res.on('error', () => {
        agentEventStreams.delete(taskId)
        mainWindow?.webContents.send('agent:event', { type: 'done', task_id: taskId, error: 'stream error' })
      })
    })
    agentEventStreams.set(taskId, req)
    req.on('error', () => {
      agentEventStreams.delete(taskId)
      mainWindow?.webContents.send('agent:event', { type: 'done', task_id: taskId, error: 'connection failed' })
    })
    req.setTimeout(300000, () => {
      req.destroy()
      agentEventStreams.delete(taskId)
      mainWindow?.webContents.send('agent:event', { type: 'done', task_id: taskId, error: 'timeout' })
    })
    return { started: true, task_id: taskId }
  })
  ipcMain.handle('agent:stop-events', (_e, taskId) => {
    const request = agentEventStreams.get(taskId)
    if (request) request.destroy()
    agentEventStreams.delete(taskId)
    return { stopped: true, task_id: taskId }
  })
}

// ---- Server crash recovery ----

let serverRestartTimer = null
let serverCrashCount = 0
let serverRestartPending = false

async function startServerWithRecovery() {
  if (app.isQuitting) return
  await startServer()
  // Monitor: if server exits and we're not quitting, restart it
  const check = () => {
    if (app.isQuitting) return
    if ((!serverProcess || serverProcess.exitCode !== null) && !serverRestartPending) {
      serverReady = false
      serverCrashCount++
      serverRestartPending = true
      console.error(`[server:crash] Server died unexpectedly (crash #${serverCrashCount}), restarting in 3s...`)
      mainWindow?.webContents.send('hermes:status', { status: 'restarting', crashCount: serverCrashCount })
      setTimeout(async () => {
        serverRestartPending = false
        if (!app.isQuitting && !serverProcess) await startServer()
      }, 3000)
    }
  }
  if (serverRestartTimer) clearInterval(serverRestartTimer)
  serverRestartTimer = setInterval(check, 5000)
}

// ---- Lifecycle ----

app.whenReady().then(() => {
  setupIPC()
  createWindow()
  updateTrayMenu = setupTray()
  startServerWithRecovery()
  syncChannelDataDirectory()
  setupIntelligenceScheduler()
  setupTrendRefreshScheduler()
  app.on('activate', () => createWindow())

  // IPC: toggle auto-launch
  ipcMain.handle('app:getAutoLaunch', () => app.getLoginItemSettings().openAtLogin)
  ipcMain.handle('app:setAutoLaunch', (_e, enabled) => {
    app.setLoginItemSettings({ openAtLogin: Boolean(enabled) })
    return app.getLoginItemSettings().openAtLogin
  })

  // IPC: account health check
  ipcMain.handle('account:health', async (_e, { platform, username, account_id }) => {
    const domains = COOKIE_DOMAINS[platform] || []
    const results = await Promise.all(domains.map((d) => platformSession(platform, account_id).cookies.get({ domain: d })))
    const cookies = results.flat()
    const now = Date.now() / 1000

    if (cookies.length === 0) return { status: 'no_cookies', platform, detail: '没有找到任何登录凭据', checked_at: new Date().toISOString() }

    const expired = cookies.every((c) => c.expirationDate && c.expirationDate < now)
    const validCount = cookies.filter((c) => !c.expirationDate || c.expirationDate > now).length
    const hasSessionCookie = cookies.some((c) => !c.expirationDate) // session cookie never expires

    if (expired) return { status: 'expired', platform, detail: '登录凭据已过期，请重新登录', cookie_count: cookies.length, expired_count: cookies.length, checked_at: new Date().toISOString() }
    if (validCount < 2 && !hasSessionCookie) return { status: 'degraded', platform, detail: '凭据可能不完整，建议重新登录', cookie_count: cookies.length, valid_count: validCount, checked_at: new Date().toISOString() }

    return { status: 'online', platform, account_id, detail: '登录正常', cookie_count: cookies.length, valid_count: validCount, username: username || null, checked_at: new Date().toISOString() }
  })

  // IPC: account management
  ipcMain.handle('account:clear', async (_e, { platform, account_id }) => {
    const key = loginKey(platform, account_id)
    const loginWindow = loginWindows.get(key)
    if (loginWindow) {
      loginWindow.__marketingLoginCancelled = true
      clearLoginPoller(key)
      destroyLoginWindow(loginWindow)
      loginWindows.delete(key)
      settleLoginCompletion(key, null, new Error('账号会话已清理'))
    }
    const s = platformSession(platform, account_id)
    await s.clearStorageData()
    await s.clearCache()
    s.flushStorageData()
    return { cleared: true, platform, account_id }
  })

  // IPC: network diagnostic
  ipcMain.handle('app:networkDiagnostic', async () => {
    const results = []
    const add = (target, status, detail) => results.push({ target, status, detail, checked_at: new Date().toISOString() })

    // 1. DNS
    try {
      await new Promise((resolve, reject) => {
        const req = http.get(`http://127.0.0.1:${serverPort}/health`, { timeout: 5000 }, (res) => { res.resume(); resolve(null) })
        req.on('error', reject); req.on('timeout', () => { req.destroy(); reject(new Error('timeout')) })
      })
      add('API 服务器', 'ok', `127.0.0.1:${serverPort} 响应正常`)
    } catch (e) {
      add('API 服务器', 'failed', e.message)
    }

    // 2. Target sites
    for (const [platform, url] of [['douyin', 'https://www.douyin.com'], ['weibo', 'https://weibo.com']]) {
      try {
        await new Promise((resolve, reject) => {
          const req = https.get(url, { timeout: 8000 }, (res) => { res.resume(); resolve(null) })
          req.on('error', reject); req.on('timeout', () => { req.destroy(); reject(new Error('timeout')) })
        })
        add(`目标站点: ${platform}`, 'ok', `${url} 可达`)
      } catch (e) {
        add(`目标站点: ${platform}`, 'failed', e.message)
      }
    }

    // 3. Hermes gateway
    try {
      const status = await getChannelStatus()
      const connected = Object.values(status).filter((c) => c.connected).length
      add('消息网关', connected > 0 ? 'ok' : 'idle', connected > 0 ? `${connected} 个渠道已连接` : '未连接消息渠道')
    } catch (e) {
      add('消息网关', 'failed', e.message)
    }

    // 4. Model API (check via server)
    try {
      await callLocalApi('GET', `${API_BASE}/assistant/status`)
      add('模型 API', 'ok', 'DeepSeek API 可用')
    } catch (e) {
      add('模型 API', 'failed', e.message)
    }

    const ok = results.filter((r) => r.status === 'ok').length
    return { results, summary: `${ok}/${results.length} 项正常`, checked_at: new Date().toISOString() }
  })
})

app.on('window-all-closed', () => {})
app.on('before-quit', () => {
  app.isQuitting = true
  if (intelligenceTimer) clearInterval(intelligenceTimer)
  if (trendRefreshTimer) clearInterval(trendRefreshTimer)
  if (serverRestartTimer) clearInterval(serverRestartTimer)
  stopServer()
})
