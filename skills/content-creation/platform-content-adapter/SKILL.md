---
name: platform-content-adapter
description: Adapt one piece of content across multiple Chinese social media platforms. Handles format conversion, tone adjustment, length optimization, hashtag strategy, and visual requirements for each platform. Use when distributing content across Douyin, Xiaohongshu, Bilibili, Weibo, and WeChat.
---

# Platform Content Adapter

## When to Use
- Distributing one piece of content to multiple platforms
- Adapting a long video into short clips
- Converting a video script into image+text post
- Cross-platform content calendar planning

## Platform Profiles

### 抖音 (Douyin)
| Attribute | Spec |
|-----------|------|
| Format | Vertical video 9:16 |
| Optimal length | 60-90 seconds |
| Max length | 10 minutes |
| Tone | Energetic, direct, punchy |
| Pacing | Fast cuts, 3-5s per shot |
| Subtitles | Required (many watch without sound) |
| Hashtags | 3-5, mix broad + niche |
| Cover | First frame or custom, must be eye-catching |
| Best post time | 12:00-13:00, 18:00-22:00 |
| Algorithm priority | Completion rate > likes > comments > shares |
| Content taboo | 搬运、水印、低质、诱导 |

### 小红书 (Xiaohongshu)
| Attribute | Spec |
|-----------|------|
| Format | Image+text OR video 3:4/1:1 |
| Optimal length | 3-5 min video or 500-800 字图文 |
| Max length | 10 min video |
| Tone | Intimate, aesthetic, authentic |
| Pacing | Slower, more reflective |
| Subtitles | Elegant, smaller font |
| Hashtags | 8-10, very specific long-tail |
| Cover | Must be beautiful as static image |
| Best post time | 7:00-9:00, 12:00-14:00, 20:00-22:00 |
| Algorithm priority | Save rate > click rate > likes |
| Content taboo | 硬广、低质图、无价值 |

### B站 (Bilibili)
| Attribute | Spec |
|-----------|------|
| Format | Horizontal video 16:9 |
| Optimal length | 5-15 minutes |
| Max length | No limit |
| Tone | Nerdy, deep, witty, referential |
| Pacing | Moderate, allows depth |
| Subtitles | Standard, can use platform CC |
| Hashtags | Topic tags + custom tags |
| Cover | Information-rich, text overlay OK |
| Best post time | 17:00-22:00, weekends |
| Algorithm priority | Completion + coins + favorites |
| Content taboo | 标题党、低创、无弹幕互动 |

### 微博 (Weibo)
| Attribute | Spec |
|-----------|------|
| Format | Text + image/video, 16:9 or 1:1 |
| Optimal length | 140 字 text + 1-9 images or 2-5 min video |
| Max length | 5 min video |
| Tone | Sharp, topical, conversational |
| Pacing | Quick consumption |
| Hashtags | 2-3 #话题# |
| Cover | First image in grid |
| Best post time | 8:00-10:00, 12:00-14:00, 20:00-22:00 |
| Algorithm priority | Reposts > comments > likes |
| Content taboo | 时政敏感、低俗、刷屏 |

### 微信公众号 (WeChat MP)
| Attribute | Spec |
|-----------|------|
| Format | Long-form article + images |
| Optimal length | 1500-3000 字 |
| Max length | 20000 字 |
| Tone | Professional, in-depth, thoughtful |
| Pacing | Reading pace, section breaks |
| Hashtags | Not applicable |
| Cover | 900×383 px, must work at small size |
| Best post time | 7:00-9:00, 12:00-14:00, 20:00-22:00 |
| Algorithm priority | Read-through rate > shares > likes |
| Content taboo | 诱导分享、低质、抄袭 |

## Adaptation Matrix

### Video → Multi-Platform

```
Source: 10-min Bilibili video
    ├── Douyin: Cut 3 × 60s clips (hook from best moments)
    ├── Xiaohongshu: Cut 1 × 3min clip + 5-image carousel summary
    ├── Weibo: 30s teaser + 3 key screenshots + summary text
    └── WeChat: 2000字 article version with key frames as images
```

### Script → Multi-Platform

```
Source: Video script (90s)
    ├── Douyin: Direct production (9:16)
    ├── Xiaohongshu: Expand to 500字 image+text with screenshots
    ├── Bilibili: Expand to 5min with behind-the-scenes
    ├── Weibo: Compress to 140字 + 3 key frames
    └── WeChat: Expand to 1500字 article with context
```

### Article → Multi-Platform

```
Source: 2000字 WeChat article
    ├── Douyin: Extract 3 key points → 3 × 60s videos
    ├── Xiaohongshu: Condense to 800字 + 5 images
    ├── Bilibili: Narrate as 5min video with slides
    └── Weibo: Thread of 5 posts, each 140字
```

## Tone Adaptation Examples

### Same content, different platform voice

**Source (neutral)**:
> "今天分享三个提高工作效率的方法：时间块管理、优先级排序、批量处理。"

**Douyin (energetic)**:
> "三个方法让你的效率翻倍！第一个就颠覆认知——时间块管理，把一天切成块，每块只做一件事！"

**Xiaohongshu (intimate)**:
> "最近在尝试提升工作效率，发现三个方法特别好用，分享给你们～时间块管理让我不再被消息打断"

**Bilibili (analytical)**:
> "效率提升的三个核心方法，我会从原理到实操详细讲。首先是时间块管理，这个概念来自Cal Newport的深度工作理论..."

**Weibo (punchy)**:
> "效率翻倍的3个方法：1⃣时间块管理 2⃣优先级排序 3⃣批量处理 你用哪个？"

## Cross-Platform Content Calendar

```markdown
## Week of [Date]

| Day | Douyin | Xiaohongshu | Bilibili | Weibo | WeChat |
|-----|--------|-------------|----------|-------|--------|
| Mon | 新视频发布 | 图文版同步 | — | 预告+链接 | — |
| Tue | — | — | — | 互动话题 | — |
| Wed | 幕后花絮 | 拍摄日常 | — | — | — |
| Thu | — | 好物分享 | — | 转发互动 | — |
| Fri | 新视频发布 | 图文版同步 | 长视频发布 | 预告+链接 | 深度文章 |
| Sat | — | 周末vlog | — | — | — |
| Sun | — | — | — | 本周回顾 | — |
```

## Adaptation Checklist

- [ ] Core message is preserved across all platforms
- [ ] Tone matches each platform's audience expectation
- [ ] Length is within each platform's optimal range
- [ ] Visual format matches platform requirement
- [ ] Hashtags are platform-specific (not copy-pasted)
- [ ] Cover/thumbnail is optimized per platform
- [ ] Posting time is optimized per platform
- [ ] CTA is adapted per platform (关注/收藏/三连/转发/关注)
- [ ] No platform-taboo content
- [ ] Cross-references between platforms (B站视频提到小红书有图文版)
