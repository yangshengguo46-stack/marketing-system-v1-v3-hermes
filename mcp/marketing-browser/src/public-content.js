import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const { tools } = require('playwright-core/lib/coreBundle')
const { z } = require('playwright-core/lib/utilsBundle')

const TOOL_NAME = 'browser_capture_public_content'

export function installPublicContentTool() {
  if (tools.browserTools.some(tool => tool.schema?.name === TOOL_NAME)) return
  tools.browserTools.push({
    capability: 'core',
    schema: {
      name: TOOL_NAME,
      title: 'Capture public content and feedback',
      description: 'Capture public creator posts and currently visible aggregate feedback from the current page as a time-bounded natural experiment. Repeat this tool later on the same post to measure feedback deltas. It never returns commenter identities or raw comments.',
      inputSchema: z.object({
        max_items: z.number().int().min(1).max(100).optional().default(30).describe('Maximum public posts to capture from the current page'),
      }),
      type: 'readOnly',
    },
    handle: async (context, params, response) => {
      const tab = await context.ensureTab()
      const result = await tab.page.evaluate(extractPublicContent, params.max_items || 30)
      response.addCode('await page.evaluate(/* Marketing OS public content observer */);')
      await response.addResult('Marketing public content observations', JSON.stringify(result, null, 2), {
        prefix: 'public-content-observations',
        ext: 'json',
      })
    },
  })
}

function extractPublicContent(maxItems) {
  const host = location.hostname.toLowerCase()
  const platform = host.includes('douyin.com') ? 'douyin'
    : host.includes('tiktok.com') ? 'tiktok'
      : host.includes('bilibili.com') ? 'bilibili'
        : host.includes('xiaohongshu.com') ? 'xiaohongshu'
          : host.includes('kuaishou.com') ? 'kuaishou'
            : host.includes('channels.weixin.qq.com') ? 'wechat_channels'
              : host.includes('mp.weixin.qq.com') ? 'wechat_official'
                : host.includes('weibo.com') ? 'weibo'
                  : host.includes('zhihu.com') ? 'zhihu'
                    : 'unknown'
  const text = value => typeof value === 'string' || typeof value === 'number' ? String(value).trim() : ''
  const first = (object, keys) => {
    for (const key of keys) {
      const value = object?.[key]
      if (value !== undefined && value !== null && value !== '') return value
    }
    return undefined
  }
  const cleanUrl = value => {
    try {
      const url = new URL(String(value || ''), location.href)
      if (!/^https?:$/.test(url.protocol)) return ''
      if (url.hostname === 'mp.weixin.qq.com') {
        const kept = new URLSearchParams()
        for (const key of ['__biz', 'mid', 'idx', 'sn']) if (url.searchParams.has(key)) kept.set(key, url.searchParams.get(key))
        url.search = kept.toString()
      } else {
        url.search = ''
      }
      url.hash = ''
      return url.toString()
    } catch { return '' }
  }
  const count = value => {
    if (typeof value === 'number' && Number.isFinite(value)) return Math.max(0, Math.trunc(value))
    const raw = text(value).replace(/,/g, '').toLowerCase()
    const match = raw.match(/([\d.]+)\s*(亿|万|w|k|m)?/)
    if (!match) return null
    const factor = match[2] === '亿' ? 1e8 : ['万', 'w'].includes(match[2]) ? 1e4 : match[2] === 'k' ? 1e3 : match[2] === 'm' ? 1e6 : 1
    return Math.max(0, Math.round(Number(match[1]) * factor))
  }
  const itemId = value => {
    const url = cleanUrl(value)
    const patterns = [
      /\/(?:video|note|explore|answer|p|article)\/([A-Za-z0-9_-]+)/i,
      /\/BV([A-Za-z0-9]+)/i,
      /[?&](?:mid|id|__biz)=([^&#]+)/i,
    ]
    for (const pattern of patterns) {
      const match = String(value || '').match(pattern) || url.match(pattern)
      if (match?.[1]) return match[1]
    }
    return location.pathname.replace(/\W+/g, '_').replace(/^_|_$/g, '').slice(0, 240)
  }
  const hashtags = value => {
    const source = Array.isArray(value) ? value.map(item => text(first(item, ['name', 'title']) || item)) : text(value).match(/#[^#\s，。；;]+/g) || []
    return [...new Set(source.map(item => text(item).replace(/^#/, '')).filter(Boolean))].slice(0, 30)
  }
  const items = []
  const seen = new Set()
  const add = raw => {
    if (!raw || typeof raw !== 'object' || items.length >= maxItems) return
    const postIdentityKeys = ['aweme_id', 'item_id', 'itemId', 'video_id', 'videoId', 'note_id', 'noteId', 'article_id', 'answer_id', 'bvid']
    const postUrlKeys = ['share_url', 'web_url', 'note_url', 'article_url', 'video_url']
    const schemaType = text(raw['@type']).toLowerCase()
    const looksLikePost = raw.__marketing_fallback === true
      || postIdentityKeys.some(key => raw[key] !== undefined && raw[key] !== null)
      || postUrlKeys.some(key => text(raw[key]))
      || ['article', 'videoobject', 'socialmediaposting'].includes(schemaType)
    if (!looksLikePost) return
    const stats = first(raw, ['statistics', 'stats', 'stat', 'interact_info', 'metrics']) || {}
    const author = first(raw, ['author', 'user', 'creator', 'account']) || {}
    const sourceUrl = cleanUrl(first(raw, ['share_url', 'url', 'web_url', 'note_url', 'article_url', 'video_url'])) || cleanUrl(location.href)
    const sourceItemId = text(first(raw, ['aweme_id', 'item_id', 'itemId', 'video_id', 'videoId', 'note_id', 'noteId', 'article_id', 'answer_id', 'bvid', 'mid', 'id'])) || itemId(sourceUrl)
    if (!sourceItemId || seen.has(sourceItemId)) return
    const caption = text(first(raw, ['desc', 'description', 'summary', 'content', 'caption', 'display_title'])).slice(0, 4000)
    const title = text(first(raw, ['title', 'name', 'subject'])).slice(0, 1000)
    const duration = count(first(raw, ['duration_ms'])) || ((count(first(raw, ['duration'])) || 0) * 1000 || null)
    const contentType = duration ? 'video' : platform === 'wechat_official' ? 'article' : 'unknown'
    const profileUrl = cleanUrl(first(author, ['profile_url', 'homepage', 'url', 'share_url']))
    const metrics = {
      views: count(first(stats, ['play_count', 'playCount', 'view_count', 'viewCount', 'read_count', 'views'])),
      likes: count(first(stats, ['digg_count', 'like_count', 'likeCount', 'likes', 'voteup_count'])),
      comments: count(first(stats, ['comment_count', 'commentCount', 'comments'])),
      shares: count(first(stats, ['share_count', 'shareCount', 'shares'])),
      favorites: count(first(stats, ['collect_count', 'favorite_count', 'favoriteCount', 'favorites'])),
      reposts: count(first(stats, ['repost_count', 'repostCount', 'reposts'])),
      danmaku: count(first(stats, ['danmaku_count', 'danmakuCount', 'danmaku'])),
    }
    for (const key of Object.keys(metrics)) if (metrics[key] === null) delete metrics[key]
    if (!title && !caption && !duration && Object.keys(metrics).length === 0) return
    seen.add(sourceItemId)
    items.push({
      source_item_id: sourceItemId,
      source_url: sourceUrl,
      creator: {
        platform_account_id: text(first(author, ['uid', 'user_id', 'sec_uid', 'mid', 'id'])).slice(0, 300),
        handle: text(first(author, ['unique_id', 'username', 'handle'])).slice(0, 200),
        name: text(first(author, ['nickname', 'name', 'uname'])).slice(0, 300),
        profile_url: profileUrl,
      },
      content: {
        content_type: contentType,
        title,
        caption,
        body_excerpt: '',
        duration_ms: duration,
        hashtags: hashtags(first(raw, ['hashtags', 'challenges', 'topics']) || `${title} ${caption}`),
        sound_id: text(first(first(raw, ['music', 'sound']) || {}, ['id', 'mid', 'music_id'])).slice(0, 300),
      },
      published_at: text(first(raw, ['create_time', 'publish_time', 'published_at', 'datePublished'])) || null,
      feedback: { metrics },
      rank: count(first(raw, ['rank', 'position'])),
    })
  }

  const roots = []
  for (const script of document.querySelectorAll('script[type="application/json"],script[type="application/ld+json"],script#__NEXT_DATA__,script#__UNIVERSAL_DATA_FOR_REHYDRATION__,script#SIGI_STATE')) {
    const raw = script.textContent?.trim()
    if (!raw || raw.length > 20_000_000) continue
    try { roots.push(JSON.parse(raw)) } catch {}
  }
  const stack = [...roots]
  const visited = new Set()
  let scanned = 0
  while (stack.length && scanned < 100_000 && items.length < maxItems) {
    const value = stack.pop()
    if (!value || typeof value !== 'object' || visited.has(value)) continue
    visited.add(value)
    scanned += 1
    if (!Array.isArray(value)) add(value)
    for (const child of Array.isArray(value) ? value : Object.values(value)) {
      if (child && typeof child === 'object') stack.push(child)
    }
  }

  if (!items.length && platform !== 'unknown') {
    const sourceUrl = cleanUrl(location.href)
    const body = document.querySelector('article,#js_content,.RichContent-inner,.note-content,.video-info')
    const authorLink = document.querySelector('a[rel="author"],a[href*="/user/"],a[href*="/account/"]')
    add({
      __marketing_fallback: true,
      id: itemId(location.href),
      url: sourceUrl,
      title: document.querySelector('meta[property="og:title"]')?.content || document.querySelector('h1')?.textContent || document.title,
      description: document.querySelector('meta[property="og:description"]')?.content || '',
      content: body?.textContent?.trim().slice(0, 8000) || '',
      author: {
        name: document.querySelector('meta[name="author"]')?.content || authorLink?.textContent || '',
        url: authorLink?.href || '',
      },
      published_at: document.querySelector('meta[property="article:published_time"]')?.content || null,
      metrics: {},
    })
    if (items[0]) items[0].content.body_excerpt = body?.textContent?.trim().slice(0, 8000) || ''
  }

  return {
    schema: 'marketing_public_content_observation.v1',
    platform,
    observed_at: new Date().toISOString(),
    page_url: cleanUrl(location.href),
    items,
    extraction: {
      embedded_json_roots: roots.length,
      scanned_nodes: scanned,
      commenter_identity_collected: false,
      raw_comments_collected: false,
    },
  }
}

export const publicContentToolName = TOOL_NAME
