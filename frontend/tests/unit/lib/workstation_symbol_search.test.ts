import { describe, expect, it } from 'vitest'
import { shouldDiscoverTicker } from '@/lib/workstationSymbolSearch'

describe('workstation ticker discovery boundary', () => {
  it('keeps exact local tickers on the local path', () => {
    expect(shouldDiscoverTicker(' spy ', [{ symbol: 'SPY' }])).toBe(false)
  })

  it('discovers a ticker-shaped query when local results are only partial matches', () => {
    expect(shouldDiscoverTicker('BWET', [{ symbol: 'BWETW' }])).toBe(true)
  })

  it('allows a valid single-character ticker when no exact local result exists', () => {
    expect(shouldDiscoverTicker('C', [])).toBe(true)
    expect(shouldDiscoverTicker('C', [{ symbol: 'C' }])).toBe(false)
  })

  it('does not treat names or unfinished expressions as ticker requests', () => {
    expect(shouldDiscoverTicker('small cap growth', [])).toBe(false)
    expect(shouldDiscoverTicker('=SPY/', [])).toBe(false)
  })
})
