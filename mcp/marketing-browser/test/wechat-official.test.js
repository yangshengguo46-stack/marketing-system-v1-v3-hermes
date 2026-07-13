import assert from 'node:assert/strict'
import test from 'node:test'

import {
  normalizeWechatArticleAnalytics,
  parseWechatPublishPayload,
} from '../src/wechat-official.js'

test('normalizes owned published articles without exposing admin state', () => {
  const result = parseWechatPublishPayload({
    publish_page: JSON.stringify({
      publish_list: [
        {
          publish_info: JSON.stringify({
            sent_info: { time: 1_752_350_400 },
            appmsg_info: [
              {
                aid: 'article-1',
                appmsgid: '2247483743',
                itemidx: 1,
                title: '第一篇文章',
                digest: '摘要',
                content_url: 'https://mp.weixin.qq.com/s?__biz=abc&amp;mid=1',
                pic_cdn_url_235_1: 'https://mp.weixin.qq.com/cover.jpg',
                read_num: 321,
                like_num: 12,
              },
            ],
          }),
        },
      ],
    }),
  })

  assert.equal(result.length, 1)
  assert.equal(result[0].source_item_id, 'article-1')
  assert.equal(result[0].source_url, 'https://mp.weixin.qq.com/s?__biz=abc&mid=1')
  assert.deepEqual(result[0].metrics, {})
  assert.deepEqual(result[0].publish_preview, {
    read_num: 321,
    share_num: null,
    like_num: 12,
    comment_num: null,
  })
  assert.deepEqual(result[0].analytics_ref, { msg_id: '2247483743', item_index: 1 })
  assert.equal(result[0].published_at, 1_752_350_400)
  assert.equal(JSON.stringify(result).includes('token'), false)
})

test('uses 30-day content analysis metrics without conflating preview counters', () => {
  const result = normalizeWechatArticleAnalytics({
    is_new_data: 1,
    article_data_new: {
      avg_article_read_time: 59,
      finished_read_pv_ratio: 0.642857134342,
      follow_after_read_uv: 2,
      zaikan_cnt: 0,
      like_cnt: 1,
      comment_cnt: 0,
      listen_pv: 0,
      read_uv: 14,
      share_uv: 3,
      collection_uv: 0,
      listen_uv: 0,
    },
  })

  assert.deepEqual(result.metrics, {
    read_users: 14,
    share_users: 3,
    like_count: 1,
    recommend_count: 0,
    comment_count: 0,
    collection_users: 0,
    followers_gained: 2,
    avg_read_seconds: 59,
    completion_rate: 0.642857134342,
    listen_users: 0,
    listen_count: 0,
  })
  assert.equal(result.metrics_provenance.window, 'first_30_days_after_publish')
  assert.equal(result.metrics_provenance.read_unit, 'unique_users')
  assert.equal(result.metrics_provenance.share_unit, 'unique_users')
})

test('rejects non-WeChat public article URLs and deduplicates article ids', () => {
  const result = parseWechatPublishPayload({
    publish_page: {
      publish_list: [{
        publish_info: {
          appmsg_info: [
            { aid: 'same', title: 'one', content_url: 'https://mp.weixin.qq.com/s/one' },
            { aid: 'same', title: 'two', content_url: 'https://mp.weixin.qq.com/s/two' },
            { aid: 'foreign', title: 'bad', content_url: 'https://example.com/article' },
          ],
        },
      }],
    },
  })

  assert.deepEqual(result.map(item => item.title), ['one'])
})
