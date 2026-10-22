import { describe, expect, it } from 'vitest'

import {
  calculateCustomDateSortValue,
  customDateSortRangeFromChartIndices,
  customDateSortRangeFromTrendline,
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

  it('normalizes selected trendline endpoints into chronological UTC bounds', () => {
    expect(customDateSortRangeFromTrendline([
      { time: 1767312000 },
      { time: 1767225600 },
    ])).toEqual({ start: '2026-01-01T00:00:00.000Z', end: '2026-01-02T00:00:00.000Z' })
  })
})
