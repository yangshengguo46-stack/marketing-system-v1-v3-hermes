import { describe, expect, it } from 'vitest'

import {
  appViewForPath,
  isNewChatRoute,
  NEW_CHAT_ROUTE,
  routeSessionId,
  sessionRoute,
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

  it('round-trips native session routes without confusing them with product routes', () => {
    const sessionId = 'account plan/7'
    const route = sessionRoute(sessionId)

    expect(route).toBe('/chat/account%20plan%2F7')
    expect(routeSessionId(route)).toBe(sessionId)
    expect(routeSessionId('/skills')).toBeNull()
    expect(routeSessionId('/chat/nested/path')).toBeNull()
  })
})
