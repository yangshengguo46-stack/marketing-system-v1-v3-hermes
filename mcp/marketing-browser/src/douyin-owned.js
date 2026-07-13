import { createRequire } from 'node:module'

import { parseAccountLease } from './account-lease.js'

const require = createRequire(import.meta.url)
const { tools } = require('playwright-core/lib/coreBundle')
const { z } = require('playwright-core/lib/utilsBundle')

const TOOL_NAME = 'browser_collect_douyin_portfolio'
const PORTFOLIO_SCHEMA = 'marketing_douyin_owned_portfolio.v1'
const WORK_LIST_PATH = '/janus/douyin/creator/pc/work_list'

export function installDouyinPortfolioTool() {
  if (tools.browserTools.some(tool => tool.schema?.name === TOOL_NAME)) return
  tools.browserTools.push({
    capability: 'core',
    schema: {
      name: TOOL_NAME,
      title: 'Collect owned Douyin account works',
      description: (
        'Read the authenticated Douyin Creator Center work list and first-party work metrics. ' +
        'Use this for an owned Douyin account instead of treating a recent-post window as the ' +
        'account lifetime total. Public and private work counts are returned separately.'
      ),
      inputSchema: z.object({
        max_works: z.number().int().min(1).max(50).optional().default(50)
          .describe('Maximum recent works to return with per-work metrics'),
      }),
      type: 'readOnly',
    },
    handle: async (context, params, response) => {
      const tab = await context.ensureTab()
      const lease = parseAccountLease()
      if (lease.platform !== 'douyin') {
        throw new Error('This collector requires a session bound to a douyin account')
      }
      const page = tab.page
      const workList = page.waitForResponse(item => {
        try {
          return new URL(item.url()).pathname === WORK_LIST_PATH && item.request().method() === 'GET'
        } catch {
          return false
        }
      }, { timeout: 30_000 })
      await page.goto('https://creator.douyin.com/creator-micro/content/manage', {
        waitUntil: 'domcontentloaded',
        timeout: 45_000,
      })
      const apiResponse = await workList
      if (!apiResponse.ok()) throw new Error(`Douyin Creator Center returned HTTP ${apiResponse.status()}`)
      const payload = await apiResponse.json()
      const result = normalizeDouyinWorkList(payload, params.max_works || 50)
      if (result.collection.returned === 0 && result.stats.all_work_count > 0) {
        throw new Error('Douyin Creator Center returned a work total without readable work records')
      }
      response.addCode('await page.goto(/* Douyin Creator Center owned work list */);')
      await response.addResult('Douyin owned account portfolio', JSON.stringify(result, null, 2), {
        prefix: 'douyin-owned-portfolio',
        ext: 'json',
      })
    },
  })
}

export function normalizeDouyinWorkList(payload, maxWorks = 50) {
  if (!payload || typeof payload !== 'object' || Number(payload.status_code || 0) !== 0) {
    throw new Error('Douyin Creator Center work list is unavailable')
  }
  const items = Array.isArray(payload.items) ? payload.items : []
  const awemes = Array.isArray(payload.aweme_list) ? payload.aweme_list : []
  const limit = Math.max(1, Math.min(Number(maxWorks) || 50, 50))
  const integer = value => {
    const number = Number(value)
    return Number.isFinite(number) && number >= 0 ? Math.trunc(number) : null
  }
  const decimal = value => {
    const number = Number(value)
    return Number.isFinite(number) && number >= 0 ? number : null
  }
  const text = (value, max = 1_000) => String(value ?? '').replace(/\s+/g, ' ').trim().slice(0, max)
  const firstAuthor = awemes.find(item => item?.author)?.author || {}
  const works = []

  for (let index = 0; index < Math.min(items.length, awemes.length, limit); index += 1) {
    const item = items[index] || {}
    const aweme = awemes[index] || {}
    const sourceItemId = text(aweme.aweme_id || item.item_id || item.aweme_id, 200)
    if (!sourceItemId) continue
    const status = aweme.status || {}
    const isPrivate = status.is_private === true || Number(status.private_status || 0) !== 0
    const metrics = item.metrics || {}
    const normalizedMetrics = {}
    for (const [name, value] of Object.entries({
      view_count: integer(metrics.view_count),
      like_count: integer(metrics.like_count),
      comment_count: integer(metrics.comment_count),
      share_count: integer(metrics.share_count),
      favorite_count: integer(metrics.favorite_count),
      homepage_visit_count: integer(metrics.homepage_visit_count),
      followers_gained: integer(metrics.subscribe_count),
      followers_lost: integer(metrics.unsubscribe_count),
      avg_view_seconds: decimal(metrics.avg_view_second),
      avg_view_proportion: decimal(metrics.avg_view_proportion),
      completion_rate: decimal(metrics.completion_rate),
      two_second_bounce_rate: decimal(metrics.bounce_rate_2s),
    })) {
      if (value !== null) normalizedMetrics[name] = value
    }
    works.push({
      source_item_id: sourceItemId,
      source_url: isPrivate ? '' : `https://www.douyin.com/video/${sourceItemId}`,
      description: text(item.description || aweme.desc || aweme.caption, 2_000),
      published_at: integer(item.create_time || aweme.create_time),
      duration_ms: integer(item.video_info?.duration || aweme.video?.duration),
      visibility: isPrivate ? 'private' : 'public',
      publication_state: status.in_reviewing ? 'reviewing' : status.is_prohibited ? 'prohibited' : 'published',
      metrics: normalizedMetrics,
      metrics_provenance: {
        source: 'douyin_creator_center_work_list',
        window: 'current_lifetime_counter',
      },
    })
  }

  const publicWorks = works.filter(work => work.visibility === 'public' && work.publication_state === 'published')
  const privateWorks = works.filter(work => work.visibility === 'private')
  const knownTotal = integer(payload.total) ?? integer(firstAuthor.aweme_count) ?? works.length
  const complete = payload.has_more !== true && works.length >= knownTotal
  const sumPublic = name => publicWorks.reduce((total, work) => total + (integer(work.metrics[name]) || 0), 0)

  return {
    schema: PORTFOLIO_SCHEMA,
    platform: 'douyin',
    observed_at: new Date().toISOString(),
    account: { name: text(firstAuthor.nickname, 300) },
    stats: {
      followers: integer(firstAuthor.follower_count),
      following: integer(firstAuthor.following_count),
      total_likes: integer(firstAuthor.total_favorited),
      all_work_count: knownTotal,
      public_work_count: complete ? publicWorks.length : null,
      private_work_count: complete ? privateWorks.length : null,
      public_view_count: sumPublic('view_count'),
      public_like_count: sumPublic('like_count'),
    },
    works,
    collection: {
      source: 'douyin_creator_center_work_list',
      returned: works.length,
      total: knownTotal,
      complete,
    },
    data_gaps: [
      ...(complete ? [] : ['public_and_private_breakdown_incomplete']),
      ...(works.every(work => Object.keys(work.metrics).length) ? [] : ['some_work_metrics_unavailable']),
    ],
  }
}

export const douyinPortfolioToolName = TOOL_NAME
