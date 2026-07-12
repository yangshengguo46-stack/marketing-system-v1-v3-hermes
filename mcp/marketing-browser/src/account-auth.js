import { createRequire } from 'node:module'

import { parseAccountLease } from './account-lease.js'

const require = createRequire(import.meta.url)
const { tools } = require('playwright-core/lib/coreBundle')
const { z } = require('playwright-core/lib/utilsBundle')

const TOOL_NAME = 'browser_verify_account_login'
const SCHEMA = 'marketing_account_auth_verification.v1'

const PLATFORM_AUTH = {
  douyin: {
    hosts: ['douyin.com'],
    cookieSets: [['sessionid'], ['sessionid_ss'], ['sid_guard']],
  },
  bilibili: {
    hosts: ['bilibili.com'],
    cookieSets: [['SESSDATA', 'bili_jct']],
  },
  xiaohongshu: {
    hosts: ['xiaohongshu.com'],
    cookieSets: [['web_session']],
  },
  kuaishou: {
    hosts: ['kuaishou.com'],
    cookieSets: [['kuaishou.server.web_st']],
  },
  wechat_channels: {
    hosts: ['channels.weixin.qq.com'],
    cookieSets: [['finder_username'], ['wxuin', 'pass_ticket']],
  },
  wechat_official: {
    hosts: ['mp.weixin.qq.com'],
    cookieSets: [['slave_sid', 'slave_user']],
  },
  zhihu: {
    hosts: ['zhihu.com'],
    cookieSets: [['z_c0']],
  },
  tiktok: {
    hosts: ['tiktok.com'],
    cookieSets: [['sessionid']],
  },
  youtube: {
    hosts: ['youtube.com', 'google.com'],
    cookieSets: [['SAPISID', 'SID']],
  },
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
    handle: async (tab, _params, response) => {
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
      await response.addResult('Marketing account login verification', JSON.stringify(payload, null, 2))
    },
  })
}

export const accountAuthSchema = SCHEMA
export const accountAuthToolName = TOOL_NAME
