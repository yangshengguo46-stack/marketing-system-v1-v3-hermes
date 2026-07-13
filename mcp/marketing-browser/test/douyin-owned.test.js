import assert from 'node:assert/strict'
import test from 'node:test'

import { normalizeDouyinWorkList } from '../src/douyin-owned.js'

test('separates public works from private works and preserves creator metrics', () => {
  const result = normalizeDouyinWorkList({
    status_code: 0,
    has_more: false,
    total: 4,
    items: [
      { item_id: 'one', description: '公开一', create_time: 10, metrics: { view_count: '195', like_count: '2', share_count: '0' } },
      { item_id: 'two', description: '公开二', create_time: 9, metrics: { view_count: '330', like_count: '7', share_count: '0' } },
      { item_id: 'private', description: '私密', create_time: 8, metrics: { view_count: '0', like_count: '1' } },
      { item_id: 'three', description: '公开三', create_time: 7, metrics: { view_count: '4841', like_count: '46', share_count: '3', completion_rate: '0.381971' } },
    ],
    aweme_list: [
      { aweme_id: 'one', author: { nickname: '杨炎昭', follower_count: 4, following_count: 2, total_favorited: '56', aweme_count: 4 }, status: { is_private: false } },
      { aweme_id: 'two', status: { is_private: false } },
      { aweme_id: 'private', status: { is_private: true, private_status: 1 } },
      { aweme_id: 'three', status: { is_private: false } },
    ],
  })

  assert.equal(result.schema, 'marketing_douyin_owned_portfolio.v1')
  assert.equal(result.stats.all_work_count, 4)
  assert.equal(result.stats.public_work_count, 3)
  assert.equal(result.stats.private_work_count, 1)
  assert.equal(result.stats.public_view_count, 5366)
  assert.equal(result.stats.public_like_count, 55)
  assert.equal(result.stats.total_likes, 56)
  assert.equal(result.works[2].visibility, 'private')
  assert.equal(result.works[2].source_url, '')
  assert.equal(result.works[3].metrics.completion_rate, 0.381971)
  assert.deepEqual(result.data_gaps, [])
})

test('does not invent the public/private split when a work list is truncated', () => {
  const result = normalizeDouyinWorkList({
    status_code: 0,
    has_more: true,
    total: 80,
    items: [{ item_id: 'one', metrics: {} }],
    aweme_list: [{ aweme_id: 'one', author: { aweme_count: 80 }, status: { is_private: false } }],
  }, 1)

  assert.equal(result.stats.all_work_count, 80)
  assert.equal(result.stats.public_work_count, null)
  assert.equal(result.stats.private_work_count, null)
  assert.ok(result.data_gaps.includes('public_and_private_breakdown_incomplete'))
})
