import { describe, expect, it } from 'vitest'

import { formatMoney } from '../../../src/lib/format'

describe('formatMoney', () => {
  it('returns an em dash for nullish or NaN values', () => {
    expect(formatMoney(null, 'USD')).toBe('—')
    expect(formatMoney(undefined, 'USD')).toBe('—')
    expect(formatMoney(Number.NaN, 'USD')).toBe('—')
  })

  it('formats plain numbers when no currency is provided', () => {
    expect(formatMoney(12.34567, null, 2)).toBe('12.35')
  })

  it('uses Intl currency formatting for known currency codes', () => {
    const formatted = formatMoney(1234.5, 'USD', 2)
    expect(formatted).toContain('1,234.50')
    expect(formatted).toMatch(/[$]|US\$/)
  })

  it('falls back to a curated symbol map for unsupported Intl currencies', () => {
    expect(formatMoney(12.3, 'CHF', 2).replace(/\s/g, ' ')).toBe('CHF 12.30')
  })

  it('falls back to the currency code when no curated symbol exists', () => {
    expect(formatMoney(99.9, 'USDX', 1)).toBe('USDX 99.9')
  })
})
