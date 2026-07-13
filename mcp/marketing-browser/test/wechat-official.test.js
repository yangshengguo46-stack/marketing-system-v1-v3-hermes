import assert from 'node:assert/strict'
import test from 'node:test'

import { parseWechatPublishPayload } from '../src/wechat-official.js'

test('normalizes owned published articles without exposing admin state', () => {
  const result = parseWechatPublishPayload({
    publish_page: JSON.stringify({
      publish_list: [
        {
          publish_info: JSON.stringify({
            publish_time: 1_752_350_400,
            appmsg_info: [
              {
                aid: 'article-1',
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
  assert.deepEqual(result[0].metrics, { read_count: 321, like_count: 12 })
  assert.equal(JSON.stringify(result).includes('token'), false)
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
