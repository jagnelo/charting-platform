import { afterEach, describe, expect, it, vi } from 'vitest'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('@/lib/api', () => ({ api: { get: apiGet } }))
vi.mock('@/lib/workstation/ohlcvRequests', () => ({
  dedupeOhlcvRequest: (_key: string, request: () => Promise<unknown>) => request(),
}))

import { loadCustomDateSortLocalEvidence } from '@/lib/workstation/customDateSortData'

const range = { start: '2026-01-01T00:00:00.000Z', end: '2026-01-02T00:00:00.000Z' }

function readyCoverage(overrides: Record<string, unknown> = {}) {
  return {
    symbol: 'SPY',
    timeframe: 'D1',
    adjusted: true,
    mode: 'historical',
    requested_start: range.start,
    requested_end: range.end,
    status: 'ready',
    provenance: 'canonical_local_database',
    explanation: 'Canonical local bars cover the requested range.',
    lineage: {
      source_lineage: 'provider_only',
      unknown_bar_count: 0,
      provider_bar_count: 2,
      derived_bar_count: 0,
      source_timeframes: [],
    },
    ...overrides,
  }
}

describe('Custom Date Sort local evidence loading', () => {
  afterEach(() => apiGet.mockReset())

  it('stops at non-ready local coverage without requesting bars', async () => {
    apiGet.mockResolvedValueOnce(readyCoverage({ status: 'partial' }))

    const result = await loadCustomDateSortLocalEvidence({
      symbol: 'spy', timeframe: 'D1', adjusted: true, range,
    })

    expect(result.prices).toEqual({ status: 'unavailable', reason: 'coverage_not_ready' })
    expect(apiGet).toHaveBeenCalledTimes(1)
    expect(apiGet.mock.calls[0][0]).toBe('/coverage/instruments/SPY/ohlcv')
    expect(apiGet.mock.calls[0][1]).toEqual({
      timeframe: 'D1', start: range.start, end: range.end, mode: 'historical', adjusted: true,
    })
  })

  it('reads only canonical local bars after matching ready coverage', async () => {
    apiGet
      .mockResolvedValueOnce(readyCoverage())
      .mockResolvedValueOnce([
        { ts: range.start, close: 100 },
        { ts: range.end, close: 110 },
      ])

    const result = await loadCustomDateSortLocalEvidence({
      symbol: 'spy', timeframe: 'D1', adjusted: true, range,
    })

    expect(apiGet).toHaveBeenCalledTimes(2)
    expect(apiGet.mock.calls[1][0]).toBe('/ohlcv/local/SPY/D1')
    expect(apiGet.mock.calls[1][1]).toEqual({ limit: 5000, adjusted: true, view: 'canonical' })
    expect(result.prices).toEqual({
      status: 'ready',
      prices: { startClose: 100, endClose: 110 },
      sourceLineage: 'provider_only',
    })
  })
})
