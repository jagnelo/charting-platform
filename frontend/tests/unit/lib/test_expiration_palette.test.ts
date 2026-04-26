import { describe, expect, it } from 'vitest'

import { buildExpirationPalette, expirationColor } from '@/lib/expirationPalette'

describe('expirationPalette', () => {
  it('generates stable hsl colors', () => {
    expect(expirationColor(0, 2)).toMatch(/^hsl\(/)
    expect(expirationColor(10, 20)).toMatch(/^hsl\(/)
  })

  it('builds a color map for every expiration', () => {
    const expirations = ['2026-06-19', '2026-07-17', '2026-09-18']
    const palette = buildExpirationPalette(expirations)
    expect(palette.size).toBe(3)
    expect(palette.get('2026-07-17')).toMatch(/^hsl\(/)
  })
})

