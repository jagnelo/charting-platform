import { describe, expect, it } from 'vitest'

import {
  calculateCustomDateSortValue,
  customDateSortRangeFromChartIndices,
  customDateSortRangeFromChartPositions,
  customDateSortRangeFromTrendline,
  resolveCoveredCustomDateSortPrices,
} from '@/lib/workstation/customDateSort'

describe('persisted Custom Date Sort calculations', () => {
  it('returns the instrument percentage change without rounding', () => {
    expect(calculateCustomDateSortValue('percent_change', { startClose: 100, endClose: 125 })).toEqual({
      status: 'ready',
      valuePercent: 25,
      instrumentChangePercent: 25,
      comparisonChangePercent: null,
    })
  })

  it.each(['vs_sub_industry', 'vs_industry'] as const)(
    'returns the difference from the selected %s persisted series',
    mode => {
      expect(calculateCustomDateSortValue(
        mode,
        { startClose: 100, endClose: 120 },
        { startClose: 200, endClose: 220 },
      )).toEqual({
        status: 'ready',
        valuePercent: 10,
        instrumentChangePercent: 20,
        comparisonChangePercent: 10,
      })
    },
  )

  it('keeps a relative result unavailable when comparator history is missing or invalid', () => {
    expect(calculateCustomDateSortValue('vs_industry', { startClose: 100, endClose: 110 })).toEqual({
      status: 'unavailable',
      reason: 'comparison_history_unavailable',
    })
    expect(calculateCustomDateSortValue(
      'vs_sub_industry',
      { startClose: 100, endClose: 110 },
      { startClose: 0, endClose: 12 },
    )).toEqual({ status: 'unavailable', reason: 'comparison_history_unavailable' })
  })

  it.each([
    { startClose: null, endClose: 110 },
    { startClose: 0, endClose: 110 },
    { startClose: 100, endClose: Number.NaN },
    { startClose: Number.MIN_VALUE, endClose: Number.MAX_VALUE },
  ])('keeps an instrument result unavailable without valid boundary prices: %o', range => {
    expect(calculateCustomDateSortValue('percent_change', range)).toEqual({
      status: 'unavailable',
      reason: 'instrument_price_unavailable',
    })
  })

  it('requires ready local coverage, known lineage, and unique exact boundary bars', () => {
    const range = { start: '2026-01-01T00:00:00.000Z', end: '2026-01-02T00:00:00.000Z' }
    const bars = [
      { ts: range.start, close: 100 },
      { ts: range.end, close: 110 },
      { ts: '2026-01-03T00:00:00.000Z', close: 120 },
    ]
    const ready = {
      status: 'ready',
      provenance: 'canonical_local_database',
      mode: 'historical',
      timeframe: 'D1',
      adjusted: true,
      requested_start: range.start,
      requested_end: range.end,
      lineage: { source_lineage: 'provider_only', unknown_bar_count: 0 },
    } as const
    expect(resolveCoveredCustomDateSortPrices(bars, range, { timeframe: 'D1', adjusted: true }, ready)).toEqual({
      status: 'ready',
      prices: { startClose: 100, endClose: 110 },
      sourceLineage: 'provider_only',
    })
    expect(resolveCoveredCustomDateSortPrices(bars, range, { timeframe: 'D1', adjusted: true }, { ...ready, status: 'partial' })).toEqual({
      status: 'unavailable', reason: 'coverage_not_ready',
    })
    expect(resolveCoveredCustomDateSortPrices(bars, range, { timeframe: 'D1', adjusted: true }, { ...ready, provenance: 'unknown' })).toEqual({
      status: 'unavailable', reason: 'non_local_provenance',
    })
    expect(resolveCoveredCustomDateSortPrices(bars, range, { timeframe: 'D1', adjusted: false }, ready)).toEqual({
      status: 'unavailable', reason: 'coverage_scope_mismatch',
    })
    expect(resolveCoveredCustomDateSortPrices(bars, range, { timeframe: 'D1', adjusted: true }, {
      ...ready,
      requested_end: '2026-01-03T00:00:00.000Z',
    })).toEqual({ status: 'unavailable', reason: 'coverage_scope_mismatch' })
    expect(resolveCoveredCustomDateSortPrices(bars, range, {
      timeframe: 'D1', adjusted: true,
    }, { ...ready, lineage: { source_lineage: 'provider_only', unknown_bar_count: 1 } })).toEqual({
      status: 'unavailable', reason: 'unknown_lineage',
    })
    expect(resolveCoveredCustomDateSortPrices(bars.slice(1), range, { timeframe: 'D1', adjusted: true }, ready)).toEqual({
      status: 'unavailable', reason: 'boundary_price_unavailable',
    })
    expect(resolveCoveredCustomDateSortPrices([...bars, bars[0]], range, { timeframe: 'D1', adjusted: true }, ready)).toEqual({
      status: 'unavailable', reason: 'boundary_price_unavailable',
    })
    expect(resolveCoveredCustomDateSortPrices([
      bars[0], { ...bars[1], close: 0 },
    ], range, { timeframe: 'D1', adjusted: true }, ready)).toEqual({
      status: 'unavailable', reason: 'boundary_price_unavailable',
    })
  })
})

describe('Custom Date Sort range sources', () => {
  it('maps chart selection indices to exact normalized bar times', () => {
    expect(customDateSortRangeFromChartIndices([
      { ts: '2026-02-03T00:00:00Z' },
      { ts: 1770163200 },
    ], 0, 1)).toEqual({ start: '2026-02-03T00:00:00.000Z', end: '2026-02-04T00:00:00.000Z' })
  })

  it('rejects invalid or same-bar selections instead of estimating a period', () => {
    const bars = [{ ts: 1767225600 }, { ts: 1767312000 }]
    expect(customDateSortRangeFromChartIndices(bars, -1, 1)).toBeNull()
    expect(customDateSortRangeFromChartIndices(bars, 0, 2)).toBeNull()
    expect(customDateSortRangeFromChartIndices(bars, 0.5, 1)).toBeNull()
    expect(customDateSortRangeFromChartIndices(bars, 1, 1)).toBeNull()
  })

  it('snaps fractional plot positions to loaded bars and clamps overscroll gutters', () => {
    const bars = [
      { ts: '2026-02-03T00:00:00Z' },
      { ts: 1770163200 },
      { ts: '2026-02-05T00:00:00Z' },
    ]
    expect(customDateSortRangeFromChartPositions(bars, 0.2, 1.7)).toEqual({
      start: '2026-02-03T00:00:00.000Z',
      end: '2026-02-05T00:00:00.000Z',
    })
    expect(customDateSortRangeFromChartPositions(bars, -4, 1)).toEqual({
      start: '2026-02-03T00:00:00.000Z',
      end: '2026-02-04T00:00:00.000Z',
    })
    expect(customDateSortRangeFromChartPositions(bars, 1.1, 1.3)).toBeNull()
    expect(customDateSortRangeFromChartPositions(bars, Number.NaN, 2)).toBeNull()
    expect(customDateSortRangeFromChartPositions([], 0, 1)).toBeNull()
  })

  it('normalizes selected trendline endpoints into chronological UTC bounds', () => {
    expect(customDateSortRangeFromTrendline([
      { time: 1767312000 },
      { time: 1767225600 },
    ])).toEqual({ start: '2026-01-01T00:00:00.000Z', end: '2026-01-02T00:00:00.000Z' })
  })
})
