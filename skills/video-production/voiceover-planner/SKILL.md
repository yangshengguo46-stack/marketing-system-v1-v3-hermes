---
name: voiceover-planner
description: Plan voiceover and TTS for video production. Assigns voices to characters, plans narration vs dialogue, specifies emotion and pacing, and maps to TTS providers. Use when planning audio for any video content.
---

# Voiceover Planner

## When to Use
- Planning voiceover for a video
- Assigning TTS voices to characters
- Creating an audio production plan
- Matching voice to content style and platform

## Voice Assignment Process

### Step 1: Identify All Speaking Parts
List every line that needs voice:
- Narrator/VO lines
- Character dialogue
- On-screen text that should be read aloud
- CTA lines

### Step 2: Define Voice Profiles

```markdown
## Voice Profile: [Name]
- Gender: [Male/Female/Neutral]
- Age range: [Young adult/Middle-aged/Mature]
- Tone: [Warm/Authoritative/Energetic/Calm/Playful]
- Language: [zh-CN/en-US/...]
- Accent: [Standard/Northern/Southern/...]
- Speed: [Slow(0.8x)/Normal(1.0x)/Fast(1.2x)]
- Emotion default: [Neutral/Cheerful/Serious]
```

### Step 3: Match Voice to Content Type

| Content Type | Voice Style | TTS Provider | Notes |
|--------------|-------------|-------------|-------|
| 知识科普 | Warm, clear, authoritative | Fish Audio (zh) | Steady pace, articulate |
| 情感故事 | Intimate, varied emotion | ElevenLabs | Dynamic range, pauses |
| 搞笑娱乐 | Energetic, exaggerated | Fish Audio | Fast pace, playful |
| 产品测评 | Professional, neutral | Gemini TTS | Clear, objective |
| 品牌广告 | Confident, aspirational | ElevenLabs | Premium feel |
| 教程教学 | Patient, clear, structured | Gemini TTS | Consistent pace |

### Step 4: Create Audio Timeline

```
TIME    | VOICE    | TEXT                          | EMOTION    | SPEED
--------|----------|-------------------------------|------------|-------
0-3s    | Narrator | "你知道吗？90%的人都做错了"    | Curious    | 1.1x
3-8s    | Narrator | "今天教你正确的做法"            | Confident  | 1.0x
8-15s   | -        | (B-roll, no VO)               | -          | -
15-25s  | Narrator | "第一步，先准备好这个工具"      | Instructive| 0.95x
25-35s  | Narrator | "然后像这样操作"               | Encouraging| 1.0x
35-45s  | Narrator | "看，效果是不是好多了？"        | Pleased    | 1.0x
45-52s  | Narrator | "关注我，每天一个实用技巧"      | Warm CTA   | 1.0x
```

## TTS Provider Comparison

| Provider | Chinese Quality | English Quality | Voice Clone | Cost | Best For |
|----------|----------------|-----------------|-------------|------|----------|
| Fish Audio | Excellent | Good | Yes (3-15s) | ~$0.01/req | Chinese content, cost-effective |
| ElevenLabs | Good | Excellent | Yes (10s+) | Free tier + paid | English, premium feel |
| Gemini TTS | Very good | Very good | No | API pricing | Multi-language, 31 voices |
| Local (NeuTTS) | Good | Good | Yes | Free | Privacy, offline |
| AllTalk + RVC | Good | Good | Yes (RVC) | Free | Narrator mode, GPU |

## Emotion Tags

Most TTS providers support emotion control via tags or SSML:

| Tag | Effect | Example |
|-----|--------|---------|
| `[whispers]` | Lowers volume, intimate | `[whispers]其实我也做过` |
| `[excited]` | Raises pitch, energy | `[excited]太棒了！` |
| `[serious]` | Drops pitch, formal | `[serious]这一点很重要` |
| `[pause]` | Brief silence | `第一步[pause]准备好工具` |
| `[laughs]` | Insert laugh | `[laughs]别担心，很简单` |
| `(sighs)` | Exhale, resignation | `(sighs)又来了` |

## Narrator Mode

For content with both narration and character dialogue:

```
NARRATOR (warm, steady): 在一个普通的下午，小李打开了手机。
CHARACTER A (young, energetic): 哇，这个视频好火！
NARRATOR: 她不知道的是，这条视频将改变她的一生。
CHARACTER A (surprised): 什么？这怎么可能？
```

- Narrator voice: distinct from character voices
- Narrator handles transitions and context
- Characters handle dialogue and emotion
- Use RVC or voice cloning for consistent character voices across episodes

## BGM Planning

### Emotional Mapping

| Story Beat | Music Mood | Tempo | Dynamics |
|------------|-----------|-------|----------|
| Hook | Tension, curiosity | Moderate | Building |
| Problem | Unease, concern | Slow | Low |
| Solution intro | Hope, uplift | Moderate | Rising |
| Demonstration | Energetic, positive | Upbeat | Medium-high |
| Result | Triumphant, warm | Moderate | Peak then settle |
| CTA | Warm, inviting | Moderate | Gentle |

### Music vs Silence
- **Music under VO**: Standard, fills dead air
- **Music swell (no VO)**: Emotional moment, let music speak
- **Silence**: Dramatic pause, emphasis — use sparingly
- **Music out then in**: Scene transition, reset attention

## Platform Audio Specs

| Platform | Format | Max Size | Sample Rate | Notes |
|----------|--------|----------|-------------|-------|
| Douyin | AAC/MP3 | 300MB | 44.1kHz | Loudness: -14 LUFS |
| Xiaohongshu | AAC | 100MB | 44.1kHz | Voice-forward mix |
| Bilibili | AAC/FLAC | 8GB | 48kHz | Higher quality allowed |
| YouTube | AAC/Opus | No limit | 48kHz | Loudness: -14 LUFS |
