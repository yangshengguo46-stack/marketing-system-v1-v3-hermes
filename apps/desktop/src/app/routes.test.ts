import { describe, expect, it } from 'vitest'

import {
  appViewForPath,
  ARTICLE_CREATION_ROUTE,
  DRAFT_BOX_ROUTE,
  isNewChatRoute,
  MATERIAL_LIBRARY_ROUTE,
  NEW_CHAT_ROUTE,
  routeSessionId,
  sessionRoute,
  VIDEO_CREATION_ROUTE,
  WORKBENCH_ROUTE
} from './routes'

describe('Marketing OS native routes', () => {
  it('uses the root route for the workbench and a dedicated chat route', () => {
    expect(WORKBENCH_ROUTE).toBe('/')
    expect(NEW_CHAT_ROUTE).toBe('/chat')
    expect(appViewForPath('/')).toBe('workbench')
    expect(appViewForPath('/chat')).toBe('chat')
    expect(isNewChatRoute('/chat')).toBe(true)
  })

  it('keeps drafts, article, video and materials as native product destinations', () => {
    expect(ARTICLE_CREATION_ROUTE).toBe('/content/article')
    expect(VIDEO_CREATION_ROUTE).toBe('/content/video')
    expect(MATERIAL_LIBRARY_ROUTE).toBe('/materials')
    expect(DRAFT_BOX_ROUTE).toBe('/drafts')
    expect(appViewForPath(ARTICLE_CREATION_ROUTE)).toBe('article-creation')
    expect(appViewForPath(VIDEO_CREATION_ROUTE)).toBe('video-creation')
    expect(appViewForPath(MATERIAL_LIBRARY_ROUTE)).toBe('materials')
    expect(appViewForPath(DRAFT_BOX_ROUTE)).toBe('drafts')
  })

  it('round-trips native session routes without confusing them with product routes', () => {
    const sessionId = 'account plan/7'
    const route = sessionRoute(sessionId)

    expect(route).toBe('/chat/account%20plan%2F7')
    expect(routeSessionId(route)).toBe(sessionId)
    expect(routeSessionId('/skills')).toBeNull()
    expect(routeSessionId('/chat/nested/path')).toBeNull()
  })
})
