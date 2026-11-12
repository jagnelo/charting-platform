import { describe, expect, it } from 'vitest'
import { chartErrorPresentation } from '@/lib/workstation/chartErrorPresentation'

describe('chartErrorPresentation', () => {
  it('turns a typed local-history 404 into a useful message while leaving raw diagnostics untouched', () => {
    const raw = 'API GET /ohlcv/local/SPY/D1 → 404: {"detail":"No local observations"}'

    expect(chartErrorPresentation(raw)).toBe('No local D1 price history is available for SPY.')
    expect(raw).toContain('API GET /ohlcv/local/SPY/D1 → 404:')
    expect(raw).toContain('{"detail":"No local observations"}')
  })

  it('keeps source and programming errors outside the known local-history contract visible verbatim', () => {
    const providerError = 'API GET /analysis/relative-strength → 503: service unavailable'
    const applicationError = 'A chart initialization error occurred'

    expect(chartErrorPresentation(providerError)).toBe(providerError)
    expect(chartErrorPresentation(applicationError)).toBe(applicationError)
  })

  it('presents a saved-basket chart error without showing the internal API path', () => {
    const raw = 'API GET /baskets/63/ohlcv/D1 → 404: {"detail":"No cached basket bars"}'

    expect(chartErrorPresentation(raw)).toBe('No local D1 price history is available for this saved basket.')
    expect(raw).toContain('/baskets/63/ohlcv/D1 → 404:')
  })
})
