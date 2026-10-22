export type CustomDateSortMode = 'percent_change' | 'vs_sub_industry' | 'vs_industry'

export interface CustomDateSortPriceRange {
  startClose: number | null
  endClose: number | null
}

export interface CustomDateSortRange {
  start: string
  end: string
}

export interface CustomDateSortBarBoundary {
  ts: string | number
}

export type CustomDateSortValue =
  | {
      status: 'ready'
      valuePercent: number
      instrumentChangePercent: number
      comparisonChangePercent: number | null
    }
  | {
      status: 'unavailable'
      reason: 'instrument_price_unavailable' | 'comparison_history_unavailable'
    }

function percentChange(range: CustomDateSortPriceRange): number | null {
  const { startClose, endClose } = range
  if (
    startClose == null || endClose == null
    || !Number.isFinite(startClose) || !Number.isFinite(endClose)
    || startClose <= 0
  ) return null
  const result = ((endClose - startClose) / startClose) * 100
  return Number.isFinite(result) ? result : null
}

function epochMilliseconds(value: string | number): number | null {
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return null
    const milliseconds = Math.abs(value) > 10_000_000_000 ? value : value * 1000
    return Number.isFinite(milliseconds) ? milliseconds : null
  }
  if (!value.trim()) return null
  const numeric = Number(value)
  if (Number.isFinite(numeric)) return epochMilliseconds(numeric)
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : null
}

function rangeFromEpochs(first: number | null, second: number | null): CustomDateSortRange | null {
  if (first == null || second == null || first === second) return null
  const start = Math.min(first, second)
  const end = Math.max(first, second)
  return { start: new Date(start).toISOString(), end: new Date(end).toISOString() }
}

/** Map a uPlot index-range drag to exact UTC bar boundaries; never estimate dates. */
export function customDateSortRangeFromChartIndices(
  bars: readonly CustomDateSortBarBoundary[],
  firstIndex: number,
  secondIndex: number,
): CustomDateSortRange | null {
  if (
    !Number.isInteger(firstIndex) || !Number.isInteger(secondIndex)
    || firstIndex < 0 || secondIndex < 0
    || firstIndex >= bars.length || secondIndex >= bars.length
  ) return null
  return rangeFromEpochs(
    epochMilliseconds(bars[firstIndex].ts),
    epochMilliseconds(bars[secondIndex].ts),
  )
}

/** Map a selected two-point trendline to its exact time boundaries. */
export function customDateSortRangeFromTrendline(
  points: readonly [{ time: number }, { time: number }],
): CustomDateSortRange | null {
  return rangeFromEpochs(epochMilliseconds(points[0].time), epochMilliseconds(points[1].time))
}

/**
 * Calculate the Custom Date Sort result from already-resolved persisted closes.
 * This helper deliberately does not fetch, date-align, classify, or decide
 * coverage readiness; callers must obtain both ranges from the local persisted
 * history contract and keep its coverage/provenance state alongside the result.
 */
export function calculateCustomDateSortValue(
  mode: CustomDateSortMode,
  instrument: CustomDateSortPriceRange,
  comparison?: CustomDateSortPriceRange | null,
): CustomDateSortValue {
  const instrumentChangePercent = percentChange(instrument)
  if (instrumentChangePercent == null) {
    return { status: 'unavailable', reason: 'instrument_price_unavailable' }
  }

  if (mode === 'percent_change') {
    return {
      status: 'ready',
      valuePercent: instrumentChangePercent,
      instrumentChangePercent,
      comparisonChangePercent: null,
    }
  }

  const comparisonChangePercent = comparison ? percentChange(comparison) : null
  if (comparisonChangePercent == null) {
    return { status: 'unavailable', reason: 'comparison_history_unavailable' }
  }

  return {
    status: 'ready',
    valuePercent: instrumentChangePercent - comparisonChangePercent,
    instrumentChangePercent,
    comparisonChangePercent,
  }
}
