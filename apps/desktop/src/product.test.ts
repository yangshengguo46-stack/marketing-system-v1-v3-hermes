import { describe, expect, it } from 'vitest'

import { PRODUCT_APP_ID, PRODUCT_ID, PRODUCT_NAME, PRODUCT_TAGLINE } from './product'

describe('Marketing OS product identity', () => {
  it('is the native desktop product rather than an external Hermes shell', () => {
    expect(PRODUCT_ID).toBe('marketing-os')
    expect(PRODUCT_NAME).toBe('Marketing OS')
    expect(PRODUCT_APP_ID).toBe('com.marketingos.desktop')
    expect(PRODUCT_TAGLINE).toContain('账号')
  })
})
