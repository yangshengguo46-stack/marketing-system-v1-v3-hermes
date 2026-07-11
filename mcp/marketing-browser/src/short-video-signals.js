import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const { tools } = require('playwright-core/lib/coreBundle')
const { z } = require('playwright-core/lib/utilsBundle')

const TOOL_NAME = 'browser_extract_short_video_signals'

export function installShortVideoSignalTool() {
  if (tools.browserTools.some(tool => tool.schema?.name === TOOL_NAME)) return
  tools.browserTools.push({
    capability: 'core',
    schema: {
      name: TOOL_NAME,
      title: 'Extract short-video and BGM signals',
      description: 'Extract real short-video metrics and soundtrack identities from the current Douyin, TikTok, Bilibili, Xiaohongshu, Kuaishou or WeChat Channels page. Use this instead of inferring music trends from hashtags or captions.',
      inputSchema: z.object({
        max_items: z.number().int().min(1).max(100).optional().default(50).describe('Maximum observed posts to return'),
      }),
      type: 'readOnly',
    },
    handle: async (tab, params, response) => {
      const result = await tab.page.evaluate(extractShortVideoSignals, params.max_items || 50)
      response.addCode('await page.evaluate(/* Marketing OS short-video and BGM extractor */);')
      await response.addResult('Marketing short-video signals', JSON.stringify(result, null, 2), {
        prefix: 'short-video-signals',
        ext: 'json',
      })
    },
  })
}

function extractShortVideoSignals(maxItems) {
  const host = location.hostname.toLowerCase()
  const platform = host.includes('douyin.com') ? 'douyin'
    : host.includes('tiktok.com') ? 'tiktok'
      : host.includes('bilibili.com') ? 'bilibili'
        : host.includes('xiaohongshu.com') ? 'xiaohongshu'
          : host.includes('kuaishou.com') ? 'kuaishou'
            : host.includes('channels.weixin.qq.com') ? 'wechat_channels'
              : 'unknown'
  const cleanUrl = value => {
    try {
      const url = new URL(String(value || ''), location.href)
      if (!/^https?:$/.test(url.protocol)) return ''
      url.search = ''
      url.hash = ''
      return url.toString()
    } catch { return '' }
  }
  const text = value => typeof value === 'string' || typeof value === 'number' ? String(value).trim() : ''
  const first = (obj, keys) => {
    for (const key of keys) {
      const value = obj?.[key]
      if (value !== undefined && value !== null && value !== '') return value
    }
    return undefined
  }
  const count = value => {
    if (typeof value === 'number' && Number.isFinite(value)) return Math.max(0, Math.trunc(value))
    const raw = text(value).replace(/,/g, '').toLowerCase()
    const match = raw.match(/([\d.]+)\s*(亿|万|w|k|m)?/)
    if (!match) return null
    const factor = match[2] === '亿' ? 1e8 : ['万', 'w'].includes(match[2]) ? 1e4 : match[2] === 'k' ? 1e3 : match[2] === 'm' ? 1e6 : 1
    return Math.max(0, Math.round(Number(match[1]) * factor))
  }
  const itemIdFromUrl = value => {
    const url = cleanUrl(value)
    const match = url.match(/\/(?:video|note|explore|BV)(?:\/)?([A-Za-z0-9_-]+)/i)
    return match?.[1] || ''
  }
  const items = []
  const seen = new Set()
  const add = raw => {
    if (items.length >= maxItems || !raw || typeof raw !== 'object') return
    const stats = first(raw, ['statistics', 'stats', 'stat', 'interact_info']) || {}
    const music = first(raw, ['music', 'music_info', 'musicInfo', 'music_detail', 'sound']) || {}
    const author = first(raw, ['author', 'user', 'creator']) || {}
    const sourceUrl = cleanUrl(first(raw, ['share_url', 'url', 'web_url', 'note_url', 'video_url']))
    const sourceItemId = text(first(raw, ['aweme_id', 'item_id', 'itemId', 'video_id', 'videoId', 'note_id', 'noteId', 'bvid', 'id'])) || itemIdFromUrl(sourceUrl)
    if (!sourceItemId || seen.has(sourceItemId)) return
    const platformSoundId = text(first(music, ['mid', 'music_id', 'musicId', 'sound_id', 'soundId', 'id']))
    const musicAuthor = first(music, ['author', 'owner', 'artist', 'user']) || {}
    const soundUrl = cleanUrl(first(music, ['share_url', 'web_url', 'url', 'permalink']))
    const result = {
      source_item_id: sourceItemId,
      source_url: sourceUrl || cleanUrl(location.href),
      caption: text(first(raw, ['desc', 'description', 'title', 'caption', 'display_title'])).slice(0, 1000),
      creator: text(first(author, ['nickname', 'name', 'unique_id', 'uname'])).slice(0, 200),
      published_at: text(first(raw, ['create_time', 'publish_time', 'published_at'])) || null,
      rank: count(first(raw, ['rank', 'position'])),
      view_count: count(first(stats, ['play_count', 'playCount', 'view_count', 'viewCount', 'view'])),
      like_count: count(first(stats, ['digg_count', 'like_count', 'likeCount', 'likes'])),
      comment_count: count(first(stats, ['comment_count', 'commentCount', 'comments'])),
      share_count: count(first(stats, ['share_count', 'shareCount', 'shares'])),
      use_count: count(first(music, ['use_count', 'useCount', 'user_count', 'video_count'])),
      sound: platformSoundId ? {
        platform_sound_id: platformSoundId,
        title: text(first(music, ['title', 'music_name', 'name'])).slice(0, 300),
        artist: text(first(musicAuthor, ['nickname', 'name']) || first(music, ['author_name', 'artist_name'])).slice(0, 200),
        duration_ms: count(first(music, ['duration_ms'])) || (count(first(music, ['duration'])) || 0) * 1000 || null,
        canonical_url: soundUrl,
        rights_status: 'unknown',
        tags: [],
      } : null,
    }
    seen.add(sourceItemId)
    items.push(result)
  }

  const roots = []
  for (const script of document.querySelectorAll('script[type="application/json"],script#__NEXT_DATA__,script#__UNIVERSAL_DATA_FOR_REHYDRATION__,script#SIGI_STATE')) {
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

  if (!items.length) {
    const currentUrl = cleanUrl(location.href)
    const sourceItemId = itemIdFromUrl(currentUrl)
    const soundLink = [...document.querySelectorAll('a[href*="/music/"],a[href*="/sound/"]')][0]
    if (sourceItemId) {
      const soundUrl = cleanUrl(soundLink?.href)
      const soundId = itemIdFromUrl(soundUrl) || soundUrl.match(/\/(?:music|sound)\/([^/]+)/)?.[1] || ''
      add({
        id: sourceItemId,
        url: currentUrl,
        title: document.querySelector('meta[property="og:title"]')?.content || document.title,
        author: { name: document.querySelector('meta[name="author"]')?.content || '' },
        music: soundId ? { id: soundId, title: soundLink?.textContent?.trim() || '', url: soundUrl } : null,
      })
    }
  }
  return {
    schema: 'marketing_short_video_signal.v1',
    platform,
    observed_at: new Date().toISOString(),
    page_url: cleanUrl(location.href),
    items,
    extraction: { embedded_json_roots: roots.length, scanned_nodes: scanned, dom_fallback: roots.length === 0 },
  }
}

export const shortVideoSignalToolName = TOOL_NAME
