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

export interface CustomDateSortPriceBar extends CustomDateSortBarBoundary {
  close: number | null
}

export interface CustomDateSortCoverageEvidence {
  status: 'ready' | 'partial' | 'missing' | 'stale' | string
  provenance: string
  mode: string
  timeframe: string
  adjusted: boolean
  requested_start: string
  requested_end: string
  lineage?: {
    source_lineage?: string
    unknown_bar_count?: number
  } | null
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

export type CustomDateSortPriceEvidence =
  | {
      status: 'ready'
      prices: CustomDateSortPriceRange
      sourceLineage: 'provider_only' | 'derived_only' | 'provider_and_derived'
    }
  | {
      status: 'unavailable'
      reason:
        | 'coverage_not_ready'
        | 'coverage_scope_mismatch'
        | 'non_local_provenance'
        | 'unknown_lineage'
        | 'boundary_price_unavailable'
    }

function percentChange(range: CustomDateSortPriceRange): number | null {
  const { startClose, endClose } = range
  if (
    startClose == null || endClose == null
    || !Number.isFinite(startClose) || !Number.isFinite(endClose)
    || startClose <= 0 || endClose <= 0
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

/**
 * Resolve the two selected closes only from a ready canonical-local coverage
 * response with fully known provider/derived lineage. Coverage is range- and
 * adjustment-specific at the API boundary; this helper preserves that contract
 * instead of treating two present values as sufficient evidence.
 */
export function resolveCoveredCustomDateSortPrices(
  bars: readonly CustomDateSortPriceBar[],
  range: CustomDateSortRange,
  expectedScope: { timeframe: string; adjusted: boolean },
  coverage: CustomDateSortCoverageEvidence,
): CustomDateSortPriceEvidence {
  if (coverage.status !== 'ready') return { status: 'unavailable', reason: 'coverage_not_ready' }
  const startMs = epochMilliseconds(range.start)
  const endMs = epochMilliseconds(range.end)
  if (
    startMs == null || endMs == null || startMs >= endMs
    || coverage.mode !== 'historical'
    || coverage.timeframe !== expectedScope.timeframe
    || coverage.adjusted !== expectedScope.adjusted
    || epochMilliseconds(coverage.requested_start) !== startMs
    || epochMilliseconds(coverage.requested_end) !== endMs
  ) return { status: 'unavailable', reason: 'coverage_scope_mismatch' }
  if (coverage.provenance !== 'canonical_local_database') {
    return { status: 'unavailable', reason: 'non_local_provenance' }
  }
  const sourceLineage = coverage.lineage?.source_lineage
  if (
    coverage.lineage?.unknown_bar_count !== 0
    || !['provider_only', 'derived_only', 'provider_and_derived'].includes(sourceLineage ?? '')
  ) return { status: 'unavailable', reason: 'unknown_lineage' }

  const closeAt = (timestamp: number) => {
    const matches = bars.filter(candidate => epochMilliseconds(candidate.ts) === timestamp)
    if (matches.length !== 1) return null
    const close = matches[0].close
    return typeof close === 'number' && Number.isFinite(close) && close > 0 ? close : null
  }
  const startClose = closeAt(startMs)
  const endClose = closeAt(endMs)
  if (startClose == null || endClose == null) {
    return { status: 'unavailable', reason: 'boundary_price_unavailable' }
  }
  return {
    status: 'ready',
    prices: { startClose, endClose },
    sourceLineage: sourceLineage as 'provider_only' | 'derived_only' | 'provider_and_derived',
  }
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
