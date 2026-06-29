const { app, BrowserWindow, BrowserView, ipcMain, session, Tray, Menu, nativeImage } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const http = require('http')
const fs = require('fs')
const crypto = require('crypto')

let mainWindow = null
let tray = null
let loginView = null
let serverProcess = null
let serverReady = false
let intelligenceRunning = false
let intelligenceTimer = null
const channelProcesses = new Map()
let serverPort = 19519
const isDev = !app.isPackaged
const API_BASE = '/api/plugins/marketing-os'
const apiToken = crypto.randomBytes(32).toString('hex')
const API_ALLOWLIST = [
  ['GET', new RegExp(`^${API_BASE}/dashboard/overview$`)],
  ['GET', new RegExp(`^${API_BASE}/trending$`)],
  ['POST', new RegExp(`^${API_BASE}/trending/refresh$`)],
  ['POST', new RegExp(`^${API_BASE}/trending/import$`)],
  ['POST', new RegExp(`^${API_BASE}/trending/import-batch$`)],
  ['GET', new RegExp(`^${API_BASE}/accounts$`)],
  ['POST', new RegExp(`^${API_BASE}/accounts$`)],
  ['DELETE', new RegExp(`^${API_BASE}/accounts/[^/]+$`)],
  ['PUT', new RegExp(`^${API_BASE}/accounts/[^/]+/stats$`)],
  ['POST', new RegExp(`^${API_BASE}/accounts/[^/]+/sync$`)],
  ['GET', new RegExp(`^${API_BASE}/suggestions$`)],
  ['GET', new RegExp(`^${API_BASE}/profiles$`)],
  ['PUT', new RegExp(`^${API_BASE}/profiles/[^/]+$`)],
  ['GET', new RegExp(`^${API_BASE}/assistant/status$`)],
  ['POST', new RegExp(`^${API_BASE}/assistant/message$`)],
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
]

// 平台登录页
const LOGIN_URLS = {
  douyin: 'https://www.douyin.com',
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

// 登录成功检测 — 导航到这个域名说明登录完成
const LOGIN_SUCCESS_HOSTS = {
  douyin: 'www.douyin.com',
  weibo: 'weibo.com',
  bilibili: 'www.bilibili.com',
  xiaohongshu: 'www.xiaohongshu.com',
  kuaishou: 'www.kuaishou.com',
  zhihu: 'www.zhihu.com',
  wechat_channels: 'channels.weixin.qq.com',
  youtube: 'www.youtube.com',
  tiktok: 'www.tiktok.com',
  instagram: 'www.instagram.com',
  facebook: 'www.facebook.com',
  twitter: 'x.com',
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
    mainWindow.webContents.openDevTools({ mode: 'detach' })
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
  return mainWindow
}

function setupTray() {
  if (tray) return
  const icon = nativeImage.createFromPath(path.join(__dirname, '..', 'src', 'assets', 'icon.png')).resize({ width: 18, height: 18 })
  tray = new Tray(icon)
  tray.setToolTip('智能营销 · 后台巡检运行中')
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: '打开智能营销', click: () => createWindow() },
    {
      label: '立即巡检',
      click: async () => {
        try { await runIntelligence() } catch (error) { console.error(`[tray:intelligence] ${error.message}`) }
      },
    },
    { type: 'separator' },
    {
      label: '退出',
      click: () => {
        app.isQuitting = true
        app.quit()
      },
    },
  ]))
  tray.on('click', () => createWindow())
}

// ---- 内嵌浏览器登录 ----

function openLoginBrowser(platform) {
  const url = LOGIN_URLS[platform]
  if (!url) return

  if (loginView) {
    mainWindow.removeBrowserView(loginView)
  }

  loginView = new BrowserView({
    webPreferences: { contextIsolation: true, nodeIntegration: false }
  })

  mainWindow.addBrowserView(loginView)

  // 浏览器窗口占右侧 65%，左侧留出操作空间
  const [wW, wH] = mainWindow.getContentSize()
  const left = Math.floor(wW * 0.35)
  loginView.setBounds({ x: left, y: 0, width: wW - left, height: wH })
  loginView.setAutoResize({ width: true, height: true, horizontal: true })
  loginView.webContents.loadURL(url)

  // 监听导航 — 检测登录成功
  loginView.webContents.on('did-navigate', (_event, navUrl) => {
    const host = new URL(navUrl).hostname
    const successHost = LOGIN_SUCCESS_HOSTS[platform]
    if (host.includes(successHost) && !navUrl.includes('login') && !navUrl.includes('signin')) {
      extractAndSaveCookies(platform)
    }
  })

  // 通知前端
  mainWindow.webContents.send('login:opened', { platform, url })
}

async function extractAndSaveCookies(platform) {
  const domains = COOKIE_DOMAINS[platform] || []
  const promises = domains.map(domain =>
    session.defaultSession.cookies.get({ domain })
  )

  return Promise.all(promises).then(async (domainResults) => {
    const allCookies = domainResults.flat()
    let identity = { username: `${platform}_session`, label: `${platform}账号` }
    if (loginView && !loginView.webContents.isDestroyed()) {
      try {
        identity = await loginView.webContents.executeJavaScript(`(() => {
          const current = location.pathname.includes('/user/') ? location.href : ''
          const links = [...document.querySelectorAll('a[href*="/user/"]')]
          const profile = current || links.find(link => link.querySelector('img') || link.getAttribute('aria-label'))?.href || links[0]?.href || ''
          const parts = profile ? new URL(profile).pathname.split('/').filter(Boolean) : []
          const username = parts[0] === 'user' && parts[1] ? parts[1] : '${platform}_session'
          const label = document.querySelector('[data-e2e="user-name"], [class*="user-name"], [class*="nickname"]')?.textContent?.trim() || '${platform}账号'
          return { username, label }
        })()`)
      } catch {}
    }

    // 只发送账号元信息；原始 Cookie 始终留在 Electron session 中。
    mainWindow.webContents.send('login:cookies', {
      platform,
      count: allCookies.length,
      username: identity.username,
      label: identity.label,
    })
  })
}

async function closeLoginBrowser(platform) {
  if (loginView) {
    // 最后再提取一次 cookie
    await extractAndSaveCookies(platform)
    mainWindow.removeBrowserView(loginView)
    loginView = null
    mainWindow.webContents.send('login:closed', { platform })
  }
}

function wait(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function hermesExecutable() {
  const candidates = [
    path.join(__dirname, '..', 'runtime', 'hermes-agent', '.venv', process.platform === 'win32' ? 'Scripts/hermes.exe' : 'bin/hermes'),
    path.join(__dirname, '..', 'runtime', 'hermes-agent', 'venv', process.platform === 'win32' ? 'Scripts/hermes.exe' : 'bin/hermes'),
    path.join(process.env.HOME || '', '.local', 'bin', process.platform === 'win32' ? 'hermes.exe' : 'hermes'),
    path.join(process.env.HOME || '', '.hermes', 'hermes-agent', 'venv', process.platform === 'win32' ? 'Scripts/hermes.exe' : 'bin/hermes'),
  ]
  return candidates.find(candidate => fs.existsSync(candidate)) || 'hermes'
}

function channelPython() {
  const candidates = [
    path.join(__dirname, '..', 'runtime', 'hermes-agent', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'),
    path.join(__dirname, '..', 'runtime', 'hermes-agent', 'venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'),
    path.join(process.env.HOME || '', '.hermes', 'hermes-agent', 'venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'),
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
    await runChannelBridge(['configure'])
  } catch (error) {
    console.warn(`[channels:config] ${error.message}`)
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

async function withSessionWindow(url, action) {
  const browser = new BrowserWindow({
    show: false,
    width: 1280,
    height: 900,
    webPreferences: {
      session: session.defaultSession,
      contextIsolation: true,
      nodeIntegration: false,
    },
  })
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
    return await action(browser.webContents)
  } finally {
    if (!browser.isDestroyed()) browser.destroy()
  }
}

async function scrapeIndustryWithSession(platform, keyword) {
  if (platform !== 'douyin') throw new Error(`暂不支持 ${platform} 登录态行业搜索`)
  const query = String(keyword || '').trim()
  if (!query) throw new Error('请输入行业关键词')
  const url = `https://www.douyin.com/search/${encodeURIComponent(query)}?type=video`
  return withSessionWindow(url, async (webContents) => {
    await webContents.executeJavaScript('window.scrollTo(0, document.body.scrollHeight * 0.65)')
    await wait(3000)
    const items = await webContents.executeJavaScript(`(() => {
      const seen = new Set()
      const results = []
      for (const link of document.querySelectorAll('a[href*="/video/"]')) {
        const href = link.href
        if (!href || seen.has(href)) continue
        const title = (link.getAttribute('aria-label') || link.querySelector('img')?.alt || link.textContent || '').replace(/\\s+/g, ' ').trim()
        if (title.length < 4) continue
        seen.add(href)
        results.push({ rank: results.length + 1, title: title.slice(0, 120), url: href })
        if (results.length >= 30) break
      }
      return results
    })()`)
    if (!Array.isArray(items) || items.length === 0) {
      throw new Error('没有读取到搜索结果；请确认抖音已登录，且页面没有出现验证码')
    }
    return { platform, keyword: query, items, collected_at: new Date().toISOString() }
  })
}

async function syncAccountWithSession(platform, username) {
  const userId = String(username || '').trim()
  if (!userId || userId.endsWith('_session')) throw new Error('未识别到账号主页 ID，请在登录窗口进入“我的主页”后再完成登录')
  const urls = {
    douyin: `https://www.douyin.com/user/${encodeURIComponent(userId)}`,
    bilibili: `https://space.bilibili.com/${encodeURIComponent(userId)}`,
  }
  const url = urls[platform]
  if (!url) throw new Error(`暂不支持 ${platform} 会话同步`)
  return withSessionWindow(url, async (webContents) => {
    const stats = await webContents.executeJavaScript(`(() => {
      const parse = value => {
        const text = String(value || '').replace(/,/g, '').trim()
        const number = parseFloat(text) || 0
        if (text.includes('万')) return Math.round(number * 10000)
        if (text.includes('亿')) return Math.round(number * 100000000)
        return Math.round(number)
      }
      const text = selector => document.querySelector(selector)?.textContent?.trim() || ''
      return {
        followers: parse(text('[data-e2e="follower-count"], .h-fans, [class*="follower"], [class*="fans"]')),
        total_likes: parse(text('[data-e2e="like-count"], [class*="like-count"], [class*="likes"]')),
        total_views: parse(text('[class*="play-count"], [class*="view-count"]')),
      }
    })()`)
    if (!stats.followers && !stats.total_likes && !stats.total_views) {
      throw new Error('账号页面已打开，但没有识别到指标；平台页面结构可能已变化')
    }
    return stats
  })
}

// 窗口 resize 时调整 BrowserView
function setupResizeHandler() {
  mainWindow.on('resize', () => {
    if (loginView && mainWindow) {
      const [wW, wH] = mainWindow.getContentSize()
      const left = Math.floor(wW * 0.35)
      loginView.setBounds({ x: left, y: 0, width: wW - left, height: wH })
    }
  })
}

// ---- API 服务器生命周期 ----

function startServer() {
  serverReady = false
  const bundledServer = path.join(
    process.resourcesPath,
    'backend',
    process.platform === 'win32' ? 'marketing-os-server.exe' : 'marketing-os-server',
  )
  const pythonBin = process.env.PYTHON_BIN || path.join(__dirname, '..', '.venv', 'bin', 'python')
  const serverScript = isDev
    ? path.join(__dirname, '..', 'engine', 'marketing-os', 'server.py')
    : path.join(process.resourcesPath, 'hermes-plugins', 'marketing-os', 'server.py')
  const useBundledServer = !isDev && fs.existsSync(bundledServer)
  const command = useBundledServer ? bundledServer : pythonBin
  const args = useBundledServer ? ['--port', String(serverPort)] : [serverScript, '--port', String(serverPort)]

  const env = {
    ...agentRuntimeEnvironment(), PYTHONUNBUFFERED: '1',
    MARKETING_OS_API_TOKEN: apiToken,
    MARKETING_OS_CONFIG_DIR: marketingConfigDir(),
    MARKETING_OS_SESSION_ORCHESTRATOR: 'electron',
    HERMES_CLI: hermesExecutable(),
    HERMES_AGENT_ROOT: agentRuntimeRoot(),
  }

  const child = spawn(command, args, {
    env, stdio: ['pipe', 'pipe', 'pipe'],
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
    } else setTimeout(() => waitForServer(retries - 1), 1000)
  })
  req.on('error', () => setTimeout(() => waitForServer(retries - 1), 1000))
  req.setTimeout(2000, () => { req.destroy(); setTimeout(() => waitForServer(retries - 1), 1000) })
}

function stopServer() {
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

function emitIntelligenceProgress(report) {
  mainWindow?.webContents.send('intelligence:progress', report)
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
        if (!['douyin', 'bilibili'].includes(account.platform) || String(account.username || '').endsWith('_session')) continue
        try {
          const stats = await syncAccountWithSession(account.platform, account.username)
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

    const collections = []
    for (const industry of config.industries || []) {
      const id = `industry:${industry}`
      step(id, `采集行业：${industry}`, 'running', '使用抖音登录会话搜索')
      try {
        const collected = await scrapeIndustryWithSession('douyin', industry)
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
  intelligenceTimer = setInterval(async () => {
    if (!serverReady || intelligenceRunning) return
    try {
      const state = await callLocalApi('GET', `${API_BASE}/workflow/status`)
      if (state.enabled && state.due) await runIntelligence()
    } catch (error) {
      console.error(`[intelligence:scheduler] ${error.message}`)
    }
  }, 30000)
}

// ---- IPC ----

function setupIPC() {
  ipcMain.handle('hermes:api', async (_e, { method, path, body }) => {
    const normalizedMethod = method || 'GET'
    const allowed = API_ALLOWLIST.some(([m, pattern]) => m === normalizedMethod && pattern.test(path))
    if (!allowed) {
      throw new Error(`Blocked API request: ${normalizedMethod} ${path}`)
    }
    const timeout = path.includes('/assistant/message') || path.includes('/workflow/run') ? 120000 : 30000
    return callLocalApi(normalizedMethod, path, body, timeout)
  })

  ipcMain.handle('hermes:status', () => ({
    running: serverReady, port: serverPort,
  }))

  ipcMain.handle('hermes:restart', () => {
    stopServer(); setTimeout(() => startServer(), 2000); return { status: 'restarting' }
  })

  // 内嵌浏览器登录
  ipcMain.handle('login:open', (_e, platform) => { openLoginBrowser(platform) })
  ipcMain.handle('login:close', (_e, platform) => closeLoginBrowser(platform || 'unknown'))
  ipcMain.handle('login:cookies', async (_e, platform) => {
    const domains = COOKIE_DOMAINS[platform] || []
    const results = await Promise.all(domains.map(d => session.defaultSession.cookies.get({ domain: d })))
    const all = results.flat()
    return { platform, count: all.length }
  })
  ipcMain.handle('session:scrape-industry', (_e, { platform, keyword }) => scrapeIndustryWithSession(platform, keyword))
  ipcMain.handle('session:sync-account', (_e, { platform, username }) => syncAccountWithSession(platform, username))
  ipcMain.handle('intelligence:run', () => runIntelligence())
  ipcMain.handle('channels:status', () => getChannelStatus())
  ipcMain.handle('channels:connect', (_e, platform) => connectChannel(platform))
  ipcMain.handle('channels:test', (_e, platform) => testChannel(platform))
  ipcMain.handle('channels:retry', (_e, deliveryId) => retryChannelDelivery(deliveryId))
}

// ---- Lifecycle ----

app.whenReady().then(() => {
  setupIPC()
  createWindow()
  setupTray()
  startServer()
  syncChannelDataDirectory()
  setupResizeHandler()
  setupIntelligenceScheduler()
  app.on('activate', () => createWindow())
})

app.on('window-all-closed', () => {})
app.on('before-quit', () => {
  app.isQuitting = true
  if (intelligenceTimer) clearInterval(intelligenceTimer)
  stopServer()
})
