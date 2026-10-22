import { api } from '@/lib/api'
import { dedupeOhlcvRequest } from '@/lib/workstation/ohlcvRequests'
import {
  calculateCustomDateSortValue,
  resolveCoveredCustomDateSortPrices,
  type CustomDateSortCoverageEvidence,
  type CustomDateSortPriceBar,
  type CustomDateSortPriceEvidence,
  type CustomDateSortRange,
  type CustomDateSortValue,
} from '@/lib/workstation/customDateSort'

const LOCAL_HISTORY_LIMIT = 5000
const CUSTOM_DATE_SORT_LIST_CONCURRENCY = 4

export interface CustomDateSortCoverageResponse extends CustomDateSortCoverageEvidence {
  symbol: string
  timeframe: string
  adjusted: boolean
  requested_start: string
  requested_end: string
  explanation: string
  lineage: {
    source_lineage: string
    unknown_bar_count: number
    provider_bar_count: number
    derived_bar_count: number
    source_timeframes: string[]
  }
}

export interface CustomDateSortLocalEvidenceResult {
  coverage: CustomDateSortCoverageResponse
  prices: CustomDateSortPriceEvidence
}

export type CustomDateSortListValue =
  | {
      symbol: string
      status: 'ready'
      valuePercent: number
      sourceLineage: 'provider_only' | 'derived_only' | 'provider_and_derived'
    }
  | {
      symbol: string
      status: 'unavailable'
      reason:
        | Extract<CustomDateSortPriceEvidence, { status: 'unavailable' }>['reason']
        | Extract<CustomDateSortValue, { status: 'unavailable' }>['reason']
        | 'local_history_request_failed'
    }

export async function loadCustomDateSortLocalEvidence(input: {
  symbol: string
  timeframe: string
  adjusted: boolean
  range: CustomDateSortRange
  signal?: AbortSignal
}): Promise<CustomDateSortLocalEvidenceResult> {
  const symbol = input.symbol.trim().toUpperCase()
  if (!symbol) throw new Error('A canonical instrument symbol is required.')

  const coverage = await api.get<CustomDateSortCoverageResponse>(
    `/coverage/instruments/${encodeURIComponent(symbol)}/ohlcv`,
    {
      timeframe: input.timeframe,
      start: input.range.start,
      end: input.range.end,
      mode: 'historical',
      adjusted: input.adjusted,
    },
    { signal: input.signal },
  )
  const scope = { timeframe: input.timeframe, adjusted: input.adjusted }
  const beforeBars = resolveCoveredCustomDateSortPrices([], input.range, scope, coverage)
  if (beforeBars.status !== 'unavailable' || beforeBars.reason !== 'boundary_price_unavailable') {
    return { coverage, prices: beforeBars }
  }
  if (input.signal?.aborted) throw new Error('Custom Date Sort evidence request was cancelled.')

  const requestKey = `custom-date-sort:local:${symbol}:${input.timeframe}:${input.adjusted}:canonical:${LOCAL_HISTORY_LIMIT}`
  const bars = await dedupeOhlcvRequest(requestKey, () => api.get<CustomDateSortPriceBar[]>(
    `/ohlcv/local/${encodeURIComponent(symbol)}/${encodeURIComponent(input.timeframe)}`,
    { limit: LOCAL_HISTORY_LIMIT, adjusted: input.adjusted, view: 'canonical' },
  ))
  return {
    coverage,
    prices: resolveCoveredCustomDateSortPrices(bars, input.range, scope, coverage),
  }
}

/**
 * Resolve one date-sort value per unique WatchList symbol from canonical local
 * history. Bound concurrent coverage/bar reads so an explicitly requested
 * result column cannot fan out an unbounded burst; callers retain generation
 * ownership and must ignore results after the target window changes.
 */
export async function loadCustomDateSortLocalListValues(input: {
  symbols: readonly string[]
  timeframe: string
  adjusted: boolean
  range: CustomDateSortRange
  signal?: AbortSignal
}): Promise<CustomDateSortListValue[]> {
  const symbols = [...new Set(input.symbols.map(symbol => symbol.trim().toUpperCase()).filter(Boolean))]
  const results: Array<CustomDateSortListValue | undefined> = new Array(symbols.length)
  let nextIndex = 0

  async function resolveNext(): Promise<void> {
    while (!input.signal?.aborted) {
      const index = nextIndex++
      if (index >= symbols.length) return
      const symbol = symbols[index]
      try {
        const evidence = await loadCustomDateSortLocalEvidence({
          symbol,
          timeframe: input.timeframe,
          adjusted: input.adjusted,
          range: input.range,
          signal: input.signal,
        })
        if (input.signal?.aborted) return
        if (evidence.prices.status === 'ready') {
          const value = calculateCustomDateSortValue('percent_change', evidence.prices.prices)
          results[index] = value.status === 'ready'
            ? {
                symbol,
                status: 'ready',
                valuePercent: value.valuePercent,
                sourceLineage: evidence.prices.sourceLineage,
              }
            : { symbol, status: 'unavailable', reason: value.reason }
        } else {
          results[index] = { symbol, status: 'unavailable', reason: evidence.prices.reason }
        }
      } catch {
        if (input.signal?.aborted) return
        results[index] = { symbol, status: 'unavailable', reason: 'local_history_request_failed' }
      }
    }
  }

  await Promise.all(
    Array.from(
      { length: Math.min(CUSTOM_DATE_SORT_LIST_CONCURRENCY, symbols.length) },
      () => resolveNext(),
    ),
  )
  return results.filter((result): result is CustomDateSortListValue => result !== undefined)
}
