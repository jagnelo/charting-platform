import { api } from '@/lib/api'
import { dedupeOhlcvRequest } from '@/lib/workstation/ohlcvRequests'
import {
  resolveCoveredCustomDateSortPrices,
  type CustomDateSortCoverageEvidence,
  type CustomDateSortPriceBar,
  type CustomDateSortPriceEvidence,
  type CustomDateSortRange,
} from '@/lib/workstation/customDateSort'

const LOCAL_HISTORY_LIMIT = 5000

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

export async function loadCustomDateSortLocalEvidence(input: {
  symbol: string
  timeframe: string
  adjusted: boolean
  range: CustomDateSortRange
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
  )
  const scope = { timeframe: input.timeframe, adjusted: input.adjusted }
  const beforeBars = resolveCoveredCustomDateSortPrices([], input.range, scope, coverage)
  if (beforeBars.status !== 'unavailable' || beforeBars.reason !== 'boundary_price_unavailable') {
    return { coverage, prices: beforeBars }
  }

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
