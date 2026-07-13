import { createRequire } from 'node:module'

import { parseAccountLease } from './account-lease.js'

const require = createRequire(import.meta.url)
const { tools } = require('playwright-core/lib/coreBundle')
const { z } = require('playwright-core/lib/utilsBundle')

const START_TOOL_NAME = 'browser_start_account_login'
const TOOL_NAME = 'browser_verify_account_login'
const SCHEMA = 'marketing_account_auth_verification.v1'

const PLATFORM_AUTH = {
  douyin: {
    hosts: ['douyin.com'],
    cookieSets: [['sessionid'], ['sessionid_ss'], ['sid_guard']],
    loginUrl: 'https://creator.douyin.com/',
  },
  bilibili: {
    hosts: ['bilibili.com'],
    cookieSets: [['SESSDATA', 'bili_jct']],
    loginUrl: 'https://member.bilibili.com/platform/home',
  },
  xiaohongshu: {
    hosts: ['xiaohongshu.com'],
    cookieSets: [['web_session']],
    loginUrl: 'https://creator.xiaohongshu.com/',
  },
  kuaishou: {
    hosts: ['kuaishou.com'],
    cookieSets: [['kuaishou.server.web_st']],
    loginUrl: 'https://cp.kuaishou.com/',
  },
  wechat_channels: {
    hosts: ['channels.weixin.qq.com'],
    cookieSets: [['finder_username'], ['wxuin', 'pass_ticket']],
    loginUrl: 'https://channels.weixin.qq.com/',
  },
  wechat_official: {
    hosts: ['mp.weixin.qq.com'],
    cookieSets: [['slave_sid', 'slave_user']],
    loginUrl: 'https://mp.weixin.qq.com/',
  },
  zhihu: {
    hosts: ['zhihu.com'],
    cookieSets: [['z_c0']],
    loginUrl: 'https://www.zhihu.com/creator',
  },
  tiktok: {
    hosts: ['tiktok.com'],
    cookieSets: [['sessionid']],
    loginUrl: 'https://www.tiktok.com/tiktokstudio',
  },
  youtube: {
    hosts: ['youtube.com', 'google.com'],
    cookieSets: [['SAPISID', 'SID']],
    loginUrl: 'https://studio.youtube.com/',
  },
}

export function accountLoginTarget(platform) {
  const config = PLATFORM_AUTH[String(platform || '').toLowerCase()]
  if (!config?.loginUrl) throw new Error('unsupported platform account login')
  return config.loginUrl
}

export function evaluateAccountAuthentication({ platform, pageUrl, cookies }) {
  const config = PLATFORM_AUTH[String(platform || '').toLowerCase()]
  let host = ''
  try { host = new URL(String(pageUrl || '')).hostname.toLowerCase() } catch {}
  const hostMatches = Boolean(config?.hosts.some(value => host === value || host.endsWith(`.${value}`)))
  const firstPartyNames = new Set(
    (Array.isArray(cookies) ? cookies : [])
      .filter(cookie => {
        const domain = String(cookie?.domain || '').replace(/^\./, '').toLowerCase()
        return config?.hosts.some(value => domain === value || domain.endsWith(`.${value}`))
      })
      .map(cookie => String(cookie?.name || '')),
  )
  const matchedSet = config?.cookieSets.find(set => set.every(name => firstPartyNames.has(name))) || []
  return {
    verified: Boolean(config && hostMatches && matchedSet.length),
    host_matches_platform: hostMatches,
    signal_count: matchedSet.length,
    verification_basis: matchedSet.length ? ['first_party_session_cookie_set'] : [],
    reason: !config
      ? 'unsupported_platform'
      : !hostMatches
        ? 'current_page_is_outside_platform'
        : !matchedSet.length
          ? 'authenticated_session_cookie_set_not_found'
          : 'authenticated_session_verified',
  }
}

export function safePageLocation(pageUrl) {
  try {
    const value = new URL(String(pageUrl || ''))
    return `${value.origin}${value.pathname}`
  } catch {
    return ''
  }
}

export function installAccountAuthTool() {
  if (!tools.browserTools.some(tool => tool.schema?.name === START_TOOL_NAME)) {
    tools.browserTools.push({
      capability: 'core',
      schema: {
        name: START_TOOL_NAME,
        title: 'Start the bound account login',
        description: 'Open the official creator surface for the bound platform in its isolated persistent browser profile. Use only for an explicit user login action.',
        inputSchema: z.object({}),
        type: 'destructive',
      },
      handle: async (context, _params, response) => {
        const tab = await context.ensureTab()
        const lease = parseAccountLease()
        const loginUrl = accountLoginTarget(lease.platform)
        await tab.page.goto(loginUrl, { waitUntil: 'domcontentloaded', timeout: 45_000 })
        const payload = {
          schema: 'marketing_account_login_started.v1',
          account_id: lease.account_id,
          platform: lease.platform,
          page_url: safePageLocation(tab.page.url()),
          started_at: new Date().toISOString(),
        }
        response.addCode(`await page.goto(${JSON.stringify(loginUrl)});`)
        await response.addResult(
          'Marketing account login started',
          JSON.stringify(payload, null, 2),
          { prefix: 'account-login-started', ext: 'json' },
        )
      },
    })
  }
  if (tools.browserTools.some(tool => tool.schema?.name === TOOL_NAME)) return
  tools.browserTools.push({
    capability: 'core',
    schema: {
      name: TOOL_NAME,
      title: 'Verify the bound account login',
      description: 'Verify the current bound platform account from the real persistent browser context. Returns no cookie values or login secrets. Use after the user finishes QR, password or verification-code login.',
      inputSchema: z.object({}),
      type: 'readOnly',
    },
    handle: async (context, _params, response) => {
      const tab = await context.ensureTab()
      const lease = parseAccountLease()
      const page = tab.page
      const pageUrl = page.url()
      const cookies = await page.context().cookies()
      const verification = evaluateAccountAuthentication({
        platform: lease.platform,
        pageUrl,
        cookies,
      })
      const payload = {
        schema: SCHEMA,
        account_id: lease.account_id,
        platform: lease.platform,
        observed_at: new Date().toISOString(),
        // OAuth and login URLs may carry short-lived codes.  The Agent only
        // receives the safe origin/path, never query parameters or fragments.
        page_url: safePageLocation(pageUrl),
        ...verification,
      }
      response.addCode('await context.cookies(); // values never leave the browser owner')
      await response.addResult(
        'Marketing account login verification',
        JSON.stringify(payload, null, 2),
        { prefix: 'account-login-verification', ext: 'json' },
      )
    },
  })
}

export const accountAuthSchema = SCHEMA
export const accountAuthToolName = TOOL_NAME
export const accountLoginStartToolName = START_TOOL_NAME
