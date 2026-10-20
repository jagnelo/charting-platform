import { describe, expect, it } from 'vitest'
import {
  adjustChartProjectionRange,
  isChartRangeAtLatest,
  MAX_CHART_PROJECTION_STEPS,
  normalizeChartProjectionSteps,
} from '@/lib/workstation/chart-projection'

describe('chart projection space', () => {
  it('normalizes persisted projection levels and bounds keyboard changes', () => {
    expect(normalizeChartProjectionSteps(undefined)).toBe(0)
    expect(normalizeChartProjectionSteps(2.8)).toBe(2)
    expect(normalizeChartProjectionSteps(-1)).toBe(0)
    expect(normalizeChartProjectionSteps(MAX_CHART_PROJECTION_STEPS + 1)).toBe(MAX_CHART_PROJECTION_STEPS)
  })

  it('expands and contracts a linear range symmetrically', () => {
    const expanded = adjustChartProjectionRange(90, 110, 2)
    expect((expanded[0] + expanded[1]) / 2).toBeCloseTo(100)
    expect(expanded[1] - expanded[0]).toBeCloseTo(20 * 1.08 ** 2)
    expect(adjustChartProjectionRange(...expanded, -2)).toEqual([90, 110])
  })

  it('adjusts logarithmic ranges symmetrically in log space', () => {
    const expanded = adjustChartProjectionRange(10, 100, 1, true)
    expect(Math.sqrt(expanded[0] * expanded[1])).toBeCloseTo(Math.sqrt(1000))
    expect(adjustChartProjectionRange(...expanded, -1, true)[0]).toBeCloseTo(10)
    expect(adjustChartProjectionRange(...expanded, -1, true)[1]).toBeCloseTo(100)
  })

  it('derives latest-bar state from the requested range across an older-page prepend', () => {
    const latest = 499
    const span = 150
    const staleRendererMax = 544
    const requestedHistoricalMax = 473

    // uPlot commits setScale through a microtask. The still-current renderer
    // range can therefore say "latest" while the wheel-requested range has
    // already moved into history.
    expect(isChartRangeAtLatest(staleRendererMax, latest, span)).toBe(true)
    expect(isChartRangeAtLatest(requestedHistoricalMax, latest, span)).toBe(false)

    // Loading the preceding fixture page prepends 20 bars and shifts both the
    // requested viewport and latest index equally. The interaction state must
    // remain historical while the data update preserves that viewport.
    expect(isChartRangeAtLatest(requestedHistoricalMax + 20, latest + 20, span)).toBe(false)
    expect(isChartRangeAtLatest(latest - span * 0.08, latest, span)).toBe(true)
    expect(isChartRangeAtLatest(Number.NaN, latest, span)).toBe(false)
  })
})
