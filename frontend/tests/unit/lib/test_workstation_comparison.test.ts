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
})
