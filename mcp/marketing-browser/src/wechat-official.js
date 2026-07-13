import { createRequire } from 'node:module'

import { parseAccountLease } from './account-lease.js'

const require = createRequire(import.meta.url)
const { tools } = require('playwright-core/lib/coreBundle')
const { z } = require('playwright-core/lib/utilsBundle')

const TOOL_NAME = 'browser_collect_wechat_official_portfolio'
const PORTFOLIO_SCHEMA = 'marketing_wechat_official_portfolio.v1'

export function installWechatOfficialPortfolioTool() {
  if (tools.browserTools.some(tool => tool.schema?.name === TOOL_NAME)) return
  tools.browserTools.push({
    capability: 'core',
    schema: {
      name: TOOL_NAME,
      title: 'Collect owned WeChat Official Account articles',
      description: (
        'Read the authenticated WeChat Official Account publication history and public article bodies ' +
        'from its account-scoped browser profile. Use this before scoring or advising an owned official ' +
        'account. It never returns admin tokens, cookies or passwords.'
      ),
      inputSchema: z.object({
        max_articles: z.number().int().min(1).max(50).optional().default(20)
          .describe('Maximum recent published articles to collect'),
      }),
      type: 'readOnly',
    },
    handle: async (context, params, response) => {
      const tab = await context.ensureTab()
      const lease = parseAccountLease()
      if (lease.platform !== 'wechat_official') {
        throw new Error('This collector requires a session bound to a wechat_official account')
      }
      const page = tab.page
      if (!page.url().includes('mp.weixin.qq.com')) {
        await page.goto('https://mp.weixin.qq.com/', { waitUntil: 'domcontentloaded' })
      }
      const source = await page.evaluate(fetchPublishHistory, params.max_articles || 20)
      const articles = parseWechatPublishPayload(source.payload, params.max_articles || 20)
      const details = articles.length
        ? await page.evaluate(fetchPublicArticleDetails, articles.map(article => article.source_url))
        : []
      const analytics = articles.length
        ? await collectWechatArticleAnalytics(page, articles, source.read_token)
        : []
      const detailByUrl = new Map(details.map(detail => [detail.source_url, detail]))
      const analyticsById = new Map(analytics.map(detail => [detail.source_item_id, detail]))
      const merged = articles.map(article => ({
        ...article,
        ...(detailByUrl.get(article.source_url) || {}),
        ...(analyticsById.get(article.source_item_id) || {}),
        source_url: article.source_url,
      }))
      const result = {
        schema: PORTFOLIO_SCHEMA,
        platform: 'wechat_official',
        observed_at: new Date().toISOString(),
        account: { name: source.account_name || '' },
        articles: merged,
        collection: {
          requested: params.max_articles || 20,
          returned: merged.length,
          body_count: merged.filter(article => article.body_text).length,
          metrics_count: merged.filter(article => Object.keys(article.metrics || {}).length).length,
          metric_source: 'wechat_content_analysis_detail',
          metric_window: 'first_30_days_after_publish',
        },
        data_gaps: [
          ...(merged.length ? [] : ['published_article_list_empty_or_unavailable']),
          ...(merged.some(article => Object.keys(article.metrics || {}).length) ? [] : ['article_30_day_analytics_unavailable']),
          ...(merged.every(article => Object.keys(article.metrics || {}).length) ? [] : ['some_article_30_day_analytics_unavailable']),
          ...(merged.every(article => article.body_text) ? [] : ['some_public_article_bodies_unavailable']),
        ],
      }
      response.addCode('await page.evaluate(/* Marketing OS owned WeChat article collector */);')
      await response.addResult('WeChat Official Account portfolio', JSON.stringify(result, null, 2), {
        prefix: 'wechat-official-portfolio',
        ext: 'json',
      })
    },
  })
}

export function parseWechatPublishPayload(payload, maxArticles = 20) {
  const parse = value => {
    if (value && typeof value === 'object') return value
    if (typeof value !== 'string' || !value.trim()) return {}
    try { return JSON.parse(value) } catch { return {} }
  }
  const page = parse(payload?.publish_page) || {}
  const publishList = Array.isArray(page.publish_list)
    ? page.publish_list
    : Array.isArray(payload?.publish_list) ? payload.publish_list : []
  const output = []
  const seen = new Set()
  const text = (value, limit = 2_000) => String(value ?? '').replace(/\s+/g, ' ').trim().slice(0, limit)
  const integer = value => {
    const number = Number(value)
    return Number.isFinite(number) && number >= 0 ? Math.trunc(number) : null
  }
  const url = value => {
    const raw = text(value, 4_000).replace(/&amp;/g, '&')
    if (!raw) return ''
    try {
      const resolved = new URL(raw, 'https://mp.weixin.qq.com/')
      return resolved.protocol === 'https:' && resolved.hostname === 'mp.weixin.qq.com' ? resolved.toString() : ''
    } catch { return '' }
  }
  for (const published of publishList) {
    const info = parse(published?.publish_info)
    const entries = Array.isArray(info?.appmsg_info) ? info.appmsg_info : []
    for (const raw of entries) {
      const sourceUrl = url(raw?.content_url || raw?.link || raw?.url)
      const sourceItemId = text(raw?.aid || raw?.appmsgid || raw?.appmsg_id || sourceUrl, 300)
      if (!sourceUrl || !sourceItemId || seen.has(sourceItemId) || output.length >= maxArticles) continue
      const publishedAt = integer(
        info?.sent_info?.time ||
        info?.publish_info?.create_time ||
        raw?.line_info?.send_time ||
        info?.publish_time ||
        raw?.publish_time ||
        raw?.create_time,
      )
      output.push({
        source_item_id: sourceItemId,
        source_url: sourceUrl,
        title: text(raw?.title, 500),
        digest: text(raw?.digest, 2_000),
        cover_url: url(raw?.cover || raw?.cover_url || raw?.pic_cdn_url_235_1),
        published_at: publishedAt,
        analytics_ref: {
          msg_id: text(raw?.appmsgid || raw?.appmsg_id || raw?.aid, 300),
          item_index: integer(raw?.itemidx || raw?.item_idx) || 1,
        },
        publish_preview: {
          read_num: integer(raw?.read_num),
          share_num: integer(raw?.share_num),
          like_num: integer(raw?.like_num),
          comment_num: integer(raw?.comment_num),
        },
        metrics: {},
      })
      seen.add(sourceItemId)
    }
    if (output.length >= maxArticles) break
  }
  return output
}

export function normalizeWechatArticleAnalytics(articleData) {
  const raw = articleData?.article_data_new
  if (!raw || typeof raw !== 'object') return null
  const integer = value => {
    const number = Number(value)
    return Number.isFinite(number) && number >= 0 ? Math.trunc(number) : null
  }
  const decimal = value => {
    const number = Number(value)
    return Number.isFinite(number) && number >= 0 ? number : null
  }
  const metrics = {}
  for (const [name, value] of Object.entries({
    read_users: integer(raw.read_uv),
    share_users: integer(raw.share_uv),
    like_count: integer(raw.like_cnt),
    recommend_count: integer(raw.zaikan_cnt),
    comment_count: integer(raw.comment_cnt),
    collection_users: integer(raw.collection_uv),
    followers_gained: integer(raw.follow_after_read_uv),
    avg_read_seconds: integer(raw.avg_article_read_time),
    completion_rate: decimal(raw.finished_read_pv_ratio),
    listen_users: integer(raw.listen_uv),
    listen_count: integer(raw.listen_pv),
  })) {
    if (value !== null) metrics[name] = value
  }
  if (!Object.keys(metrics).length) return null
  return {
    metrics,
    metrics_provenance: {
      source: 'wechat_content_analysis_detail',
      window: 'first_30_days_after_publish',
      read_unit: 'unique_users',
      share_unit: 'unique_users',
      is_new_data: Number(articleData?.is_new_data || 0) === 1,
    },
  }
}

async function collectWechatArticleAnalytics(page, articles, readToken) {
  if (!readToken) return []
  const analyticsPage = await page.context().newPage()
  const output = []
  try {
    for (const article of articles.slice(0, 50)) {
      const msgId = String(article?.analytics_ref?.msg_id || '').trim()
      const itemIndex = Number(article?.analytics_ref?.item_index || 1)
      const timestamp = Number(article?.published_at || 0)
      if (!msgId || !Number.isFinite(timestamp) || timestamp <= 0) continue
      const publishDate = new Date(timestamp * 1000).toISOString().slice(0, 10)
      const endpoint = new URL('/misc/appmsganalysis', page.url())
      endpoint.search = new URLSearchParams({
        action: 'detailpage',
        msgid: `${msgId}_${itemIndex}`,
        publish_date: publishDate,
        type: 'int',
        pageVersion: '1',
        token: String(readToken),
        lang: 'zh_CN',
      }).toString()
      try {
        await analyticsPage.goto(endpoint.toString(), {
          waitUntil: 'domcontentloaded',
          timeout: 30_000,
        })
        await analyticsPage.waitForFunction(
          () => Boolean(globalThis.wx?.cgiData?.articleData?.article_data_new),
          undefined,
          { timeout: 15_000 },
        )
        const detail = await analyticsPage.evaluate(() => {
          const data = globalThis.wx?.cgiData?.articleData || {}
          return {
            msgid: String(data.msgid || ''),
            publish_date: String(data.publish_date || ''),
            is_new_data: data.is_new_data,
            article_data_new: data.article_data_new || null,
          }
        })
        if (detail.msgid.split('_')[0] !== msgId) continue
        const normalized = normalizeWechatArticleAnalytics(detail)
        if (normalized) output.push({ source_item_id: article.source_item_id, ...normalized })
      } catch {}
    }
  } finally {
    await analyticsPage.close().catch(() => {})
  }
  return output
}

async function fetchPublishHistory(maxArticles) {
  const readToken = () => {
    const fromUrl = new URL(location.href).searchParams.get('token')
    if (fromUrl) return fromUrl
    const data = globalThis.wx?.commonData?.data || globalThis.wx?.commonData || {}
    return String(data.t || data.token || '')
  }
  const token = readToken()
  if (!token) throw new Error('WeChat Official Account login is not active in this browser profile')
  const endpoint = new URL('/cgi-bin/appmsgpublish', location.origin)
  endpoint.search = new URLSearchParams({
    sub: 'list',
    begin: '0',
    count: String(Math.max(1, Math.min(Number(maxArticles) || 20, 50))),
    token,
    lang: 'zh_CN',
    f: 'json',
  }).toString()
  const result = await fetch(endpoint, { credentials: 'include' })
  if (!result.ok) throw new Error(`WeChat publication history request failed (${result.status})`)
  const payload = await result.json()
  const baseRet = payload?.base_resp || payload?.baseResp || {}
  if (Number(baseRet.ret || 0) !== 0) {
    throw new Error(`WeChat publication history rejected (${baseRet.ret}: ${baseRet.err_msg || 'unknown'})`)
  }
  const data = globalThis.wx?.commonData?.data || globalThis.wx?.commonData || {}
  const selectors = ['.weui-desktop-account__nickname', '.account_nickname', '#js_account_name']
  const domName = selectors.map(selector => document.querySelector(selector)?.textContent?.trim()).find(Boolean)
  return {
    payload,
    account_name: String(data.nick_name || data.nickname || data.user_name || domName || '').trim().slice(0, 300),
    read_token: String(token),
  }
}

async function fetchPublicArticleDetails(urls) {
  const clean = value => String(value || '').replace(/\s+/g, ' ').trim()
  const details = []
  for (const sourceUrl of urls.slice(0, 50)) {
    try {
      const response = await fetch(sourceUrl, { credentials: 'include' })
      if (!response.ok) continue
      const body = await response.text()
      let title = ''
      let author = ''
      let contentHtml = ''
      let coverUrl = ''
      if (body.trim().startsWith('{')) {
        try {
          const payload = JSON.parse(body)
          title = clean(payload.title)
          author = clean(payload.nickname || payload.author)
          contentHtml = String(payload.content_noencode || payload.content || '')
          coverUrl = clean(payload.cdn_url_235_1 || payload.cover)
        } catch {}
      }
      const documentValue = new DOMParser().parseFromString(contentHtml || body, 'text/html')
      const content = contentHtml
        ? documentValue.body
        : documentValue.querySelector('#js_content') || documentValue.querySelector('.rich_media_content') || documentValue.body
      title ||= clean(documentValue.querySelector('#activity-name')?.textContent || documentValue.querySelector('meta[property="og:title"]')?.content)
      author ||= clean(documentValue.querySelector('#js_name')?.textContent || documentValue.querySelector('meta[name="author"]')?.content)
      coverUrl ||= clean(documentValue.querySelector('meta[property="og:image"]')?.content)
      const bodyText = clean(content?.textContent).slice(0, 20_000)
      const paragraphs = [...content.querySelectorAll('p,section')].filter(node => clean(node.textContent)).length
      const imageCount = content.querySelectorAll('img').length
      details.push({
        source_url: sourceUrl,
        ...(title ? { title } : {}),
        author,
        body_text: bodyText,
        character_count: bodyText.length,
        paragraph_count: paragraphs,
        image_count: imageCount,
        ...(coverUrl ? { cover_url: coverUrl } : {}),
      })
    } catch {}
  }
  return details
}

export const wechatOfficialPortfolioToolName = TOOL_NAME
export const wechatOfficialPortfolioSchema = PORTFOLIO_SCHEMA
