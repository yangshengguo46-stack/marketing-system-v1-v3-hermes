import { describe, expect, it } from 'vitest'

import {
  clearVideoSetupDraft,
  previewFrameStyle,
  ratioLabel,
  readVideoSetupDraft,
  videoSetupDraftKey,
  writeVideoSetupDraft
} from './video-production-workbench'

describe('video production canvas presets', () => {
  it.each([
    [{ fps: 30, height: 1920, width: 1080 }, '9:16'],
    [{ fps: 30, height: 1080, width: 1920 }, '16:9'],
    [{ fps: 30, height: 1080, width: 1080 }, '1:1'],
    [{ fps: 30, height: 1350, width: 1080 }, '4:5'],
    [{ fps: 30, height: 1440, width: 1080 }, '3:4'],
    [{ fps: 24, height: 1080, width: 2560 }, '64:27']
  ])('labels the canvas %o as %s', (canvas, expected) => {
    expect(ratioLabel(canvas)).toBe(expected)
  })

  it('sizes horizontal, square and vertical previews without changing the canvas ratio', () => {
    expect(previewFrameStyle({ fps: 30, height: 1080, width: 1920 })).toEqual({
      aspectRatio: '1920 / 1080',
      width: 'min(100%, 52rem)'
    })
    expect(previewFrameStyle({ fps: 30, height: 1080, width: 1080 })).toEqual({
      aspectRatio: '1080 / 1080',
      width: 'min(78%, 32rem)'
    })
    expect(previewFrameStyle({ fps: 30, height: 1920, width: 1080 })).toEqual({
      aspectRatio: '1080 / 1920',
      width: 'min(58%, 21rem)'
    })
  })

  it('keeps an unsubmitted setup draft scoped to its account', () => {
    const values = new Map<string, string>()

    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      value: {
        getItem: (key: string) => values.get(key) ?? null,
        removeItem: (key: string) => values.delete(key),
        setItem: (key: string, value: string) => values.set(key, value)
      } as unknown as Storage
    })

    writeVideoSetupDraft('acct-rain', {
      documents: ['/tmp/story.md'],
      script: '雨夜里，一个女孩走进旧唱片店。',
      selections: { characters: 'linxi', props: '', scenes: 'rain-street', sound: 'warm-voice' }
    })

    expect(readVideoSetupDraft('acct-rain')).toEqual({
      documents: ['/tmp/story.md'],
      script: '雨夜里，一个女孩走进旧唱片店。',
      selections: { characters: 'linxi', props: '', scenes: 'rain-street', sound: 'warm-voice' }
    })
    expect(readVideoSetupDraft('acct-other').script).toBe('')

    clearVideoSetupDraft('acct-rain')
    expect(readVideoSetupDraft('acct-rain').script).toBe('')
    expect(videoSetupDraftKey('acct-rain')).toContain('acct-rain')
  })
})
