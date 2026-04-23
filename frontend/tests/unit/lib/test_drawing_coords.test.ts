/**
 * Unit tests for the drawing coordinate conversion utilities.
 *
 * These functions underpin the drag-without-distortion guarantee: a drawing
 * that crosses the last-bar / future boundary must move smoothly, with no
 * derivative discontinuity.
 */
import { describe, it, expect } from 'vitest'
import {
  estimatedBarStep,
  drawingTimeToBarIndex,
  barIndexToDrawingTime,
} from '@/lib/drawings/coords'

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Generate n uniformly-spaced timestamps starting at `start` with gap `step`. */
function uniform(n: number, start = 1_700_000_000, step = 86_400): number[] {
  return Array.from({ length: n }, (_, i) => start + i * step)
}

const DAY = 86_400

// ── estimatedBarStep ──────────────────────────────────────────────────────────

describe('estimatedBarStep', () => {
  it('returns 86400 for empty array', () => {
    expect(estimatedBarStep([])).toBe(DAY)
  })

  it('returns 86400 for single element', () => {
    expect(estimatedBarStep([1_700_000_000])).toBe(DAY)
  })

  it('returns exact step for uniform daily bars', () => {
    expect(estimatedBarStep(uniform(30, 1_700_000_000, DAY))).toBe(DAY)
  })

  it('returns exact step for uniform hourly bars', () => {
    const HOUR = 3_600
    expect(estimatedBarStep(uniform(30, 1_700_000_000, HOUR))).toBe(HOUR)
  })

  it('returns median (robust to outliers)', () => {
    // 9 bars at 1-day step, 1 large outlier gap → median is still DAY
    const ts = uniform(10, 1_700_000_000, DAY)
    ts[5] = ts[4]! + DAY * 10  // big gap at index 5
    // Adjust subsequent bars to maintain ordering
    for (let i = 6; i < ts.length; i++) ts[i] = ts[5]! + (i - 5) * DAY
    expect(estimatedBarStep(ts)).toBe(DAY)
  })
})

// ── drawingTimeToBarIndex ─────────────────────────────────────────────────────

describe('drawingTimeToBarIndex', () => {
  const ts = uniform(5, 1_000, DAY)  // [1000, 87400, 173800, 260200, 346600]

  it('returns 0 for empty timestamps', () => {
    expect(drawingTimeToBarIndex(99999, [])).toBe(0)
  })

  it('returns 0 at exact first timestamp', () => {
    expect(drawingTimeToBarIndex(ts[0]!, ts)).toBe(0)
  })

  it('returns last index at exact last timestamp', () => {
    expect(drawingTimeToBarIndex(ts[ts.length - 1]!, ts)).toBe(ts.length - 1)
  })

  it('returns 0.5 exactly at midpoint between bar 0 and bar 1', () => {
    const mid = (ts[0]! + ts[1]!) / 2
    expect(drawingTimeToBarIndex(mid, ts)).toBeCloseTo(0.5, 10)
  })

  it('returns negative value before first bar', () => {
    const before = ts[0]! - DAY   // one bar before the first
    expect(drawingTimeToBarIndex(before, ts)).toBeCloseTo(-1, 10)
  })

  it('returns value > last index after last bar', () => {
    const after = ts[ts.length - 1]! + DAY  // one bar after the last
    expect(drawingTimeToBarIndex(after, ts)).toBeCloseTo(ts.length - 1 + 1, 10)
  })

  it('interpolates fractionally within the data range', () => {
    const quarter = ts[0]! + DAY * 0.25
    const idx = drawingTimeToBarIndex(quarter, ts)
    expect(idx).toBeGreaterThan(0)
    expect(idx).toBeLessThan(1)
    expect(idx).toBeCloseTo(0.25, 10)
  })

  it('is monotonically increasing', () => {
    const times = [ts[0]! - DAY, ...ts, ts[ts.length - 1]! + DAY]
    const indices = times.map(t => drawingTimeToBarIndex(t, ts))
    for (let i = 1; i < indices.length; i++) {
      expect(indices[i]).toBeGreaterThan(indices[i - 1]!)
    }
  })
})

// ── barIndexToDrawingTime ─────────────────────────────────────────────────────

describe('barIndexToDrawingTime', () => {
  const ts = uniform(5, 1_000, DAY)

  it('returns 0 for empty timestamps', () => {
    expect(barIndexToDrawingTime(0, [])).toBe(0)
  })

  it('returns first timestamp at index 0', () => {
    expect(barIndexToDrawingTime(0, ts)).toBe(ts[0])
  })

  it('returns last timestamp at last index', () => {
    expect(barIndexToDrawingTime(ts.length - 1, ts)).toBe(ts[ts.length - 1])
  })

  it('interpolates at fractional index 0.5', () => {
    const result = barIndexToDrawingTime(0.5, ts)
    expect(result).toBeCloseTo((ts[0]! + ts[1]!) / 2, 5)
  })

  it('extrapolates backward at negative index', () => {
    const result = barIndexToDrawingTime(-1, ts)
    expect(result).toBeCloseTo(ts[0]! - DAY, 5)
  })

  it('extrapolates forward beyond last bar', () => {
    const result = barIndexToDrawingTime(ts.length, ts)
    expect(result).toBeCloseTo(ts[ts.length - 1]! + DAY, 5)
  })
})

// ── Round-trip invariant ──────────────────────────────────────────────────────

describe('round-trip: barIndexToDrawingTime(drawingTimeToBarIndex(t)) ≈ t', () => {
  const ts = uniform(20, 1_700_000_000, DAY)

  const probes = [
    ts[0]! - DAY * 3,        // well before start
    ts[0]!,                  // first bar
    ts[0]! + DAY * 0.5,      // mid-gap
    ts[5]!,                  // interior bar
    ts[9]! + DAY * 0.37,     // fractional interior
    ts[ts.length - 1]!,      // last bar
    ts[ts.length - 1]! + DAY * 2.5,  // future zone
  ]

  for (const probe of probes) {
    it(`t=${probe} round-trips within 1ms`, () => {
      const idx = drawingTimeToBarIndex(probe, ts)
      const back = barIndexToDrawingTime(idx, ts)
      expect(Math.abs(back - probe)).toBeLessThan(1)
    })
  }
})

// ── Derivative continuity at the data/future boundary ────────────────────────

describe('derivative continuity at last-bar boundary', () => {
  const ts = uniform(10, 1_700_000_000, DAY)
  const lastBar = ts[ts.length - 1]!

  it('dx/dt is the same just inside and just outside the last bar', () => {
    const eps = 1  // 1 second

    const insideBefore  = drawingTimeToBarIndex(lastBar - eps, ts)
    const insideAfter   = drawingTimeToBarIndex(lastBar,       ts)
    const outsideBefore = drawingTimeToBarIndex(lastBar,       ts)
    const outsideAfter  = drawingTimeToBarIndex(lastBar + eps, ts)

    const slopeInside  = (insideAfter  - insideBefore)  / eps
    const slopeOutside = (outsideAfter - outsideBefore) / eps

    // Slopes should agree to within floating-point rounding
    expect(Math.abs(slopeInside - slopeOutside)).toBeLessThan(1e-9)
  })
})
