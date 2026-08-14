import { describe, expect, it } from 'vitest'

import { buildNormalizedComparisonSeries } from '@/lib/workstation/comparison'

const bar = (ts: number, close: number) => ({ ts, open: close, high: close, low: close, close, is_adjusted: true })

describe('workstation normalized comparisons', () => {
  it('aligns by timestamp, anchors each target, and reports its return', () => {
    const result = buildNormalizedComparisonSeries(
      [bar(1, 100), bar(2, 110), bar(3, 120)],
      [{ symbol: 'RSP', label: 'RSP', color: '#f00', bars: [bar(1, 50), bar(3, 55)] }],
    )
    expect(result[0].values[0]).toBe(100)
    expect(result[0].values[1]).toBeNull()
    expect(result[0].values[2]).toBeCloseTo(110)
    expect(result[0].percentChange).toBe(10)
  })

  it('returns null values when there is no valid positive comparison anchor', () => {
    const result = buildNormalizedComparisonSeries([bar(1, 100)], [{ symbol: 'EMPTY', label: 'EMPTY', color: '#f00', bars: [bar(1, 0)] }])
    expect(result[0].values).toEqual([null])
    expect(result[0].percentChange).toBeNull()
  })

  it('aligns ISO primary bars with epoch comparison timestamps', () => {
    const result = buildNormalizedComparisonSeries(
      [bar('2026-01-01T00:00:00Z', 100), bar('2026-01-02T00:00:00Z', 110)] as any,
      [{ symbol: 'RSP', label: 'RSP', color: '#f00', bars: [bar(1767225600, 50), bar(1767312000, 55)] as any }],
    )
    expect(result[0].values[0]).toBe(100)
    expect(result[0].values[1]).toBeCloseTo(110)
    expect(result[0].percentChange).toBe(10)
  })

  it('does not align malformed timestamps to an unrelated bar', () => {
    const result = buildNormalizedComparisonSeries(
      [bar('not-a-date', 100)] as any,
      [{ symbol: 'RSP', label: 'RSP', color: '#f00', bars: [bar(1, 50)] as any }],
    )
    expect(result[0].values).toEqual([null])
    expect(result[0].percentChange).toBeNull()
  })
})
