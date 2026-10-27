import { api } from '@/lib/api'
import type { ETFHoldingsCapability, ETFHoldingsSnapshot, ETFProfile, OHLCVBar, Timeframe } from '@/types'

export interface AcquisitionSourceOutcome {
  provider: string
  capability: string
  operation: string
  status: 'eligible' | 'held' | 'attempted' | 'returned' | 'no_match' | 'failed' | 'used' | 'cache_hit'
  reason_code?: string | null
  result_count?: number | null
  error_type?: string | null
}

export interface InstrumentDiscoveryCandidate {
  symbol: string
  name: string
  exchange: string
  type: string
  provider: string
  instrument_id: number | null
  identity_status: string
}

export interface InstrumentDiscoveryResponse {
  request_id: string
  status: 'complete' | 'partial' | 'held' | 'unavailable' | 'no_match'
  candidates: InstrumentDiscoveryCandidate[]
  source_outcomes: AcquisitionSourceOutcome[]
}

export interface ProviderCandidateBinding {
  provider: string
  symbol: string
  exchange?: string | null
}

export interface InstrumentAcquireResponse {
  request_id: string
  status: 'resolved' | 'no_match' | 'identity_conflict' | 'held' | 'failed'
  reason_code?: string | null
  instrument?: {
    instrument_id: number
    symbol: string
    identity_status: string
    domain_key?: string | null
    primary_identifier_type?: string | null
    primary_identifier_value?: string | null
    primary_listing_mic?: string | null
  } | null
  source_outcomes: AcquisitionSourceOutcome[]
}
export interface InstrumentAcquireRequest {
  symbol: string
  provider_candidate?: ProviderCandidateBinding | null
  request_id: string
}

export interface HistoryCoverageSlice { start: string; end: string }
export interface HistoryCoverageSummary {
  status: 'ready' | 'partial' | 'missing' | 'stale'
  covered_start?: string | null
  covered_end?: string | null
  bar_count: number
  missing_slices: HistoryCoverageSlice[]
}

export interface HistoryAcquisitionResponse {
  request_id: string
  status: 'complete' | 'partial' | 'held' | 'no_data' | 'failed'
  reason_code?: string | null
  instrument_id: number
  symbol: string
  timeframe: Timeframe
  adjusted: boolean
  requested_start: string
  requested_end: string
  coverage: HistoryCoverageSummary
  bars: OHLCVBar[]
  source_outcomes: AcquisitionSourceOutcome[]
  legal_metadata?: Record<string, unknown> | null
}

export interface HistoryAcquisitionRequest {
  timeframe: Timeframe
  adjusted: boolean
  start: string
  end: string
}

const DAY_MS = 24 * 60 * 60 * 1000
export const HISTORY_ACQUISITION_MAX_REQUESTED_BARS = 2000

// Mirrors the Provider's accepted approximate TIMEFRAME_SECONDS semantics.
// Its range budget is ceil(elapsed/timeframe) + 1 because both endpoints count.
export const HISTORY_TIMEFRAME_SECONDS: Record<Timeframe, number> = {
  M1: 60,
  M5: 300,
  M15: 900,
  M30: 1800,
  H1: 3600,
  H2: 7200,
  H4: 14400,
  H12: 43200,
  D1: 86400,
  W1: 604800,
  MN: 2592000,
}

// Conservative application defaults fit the inclusive slot budget. Provider-
// specific history coverage and entitlement limits remain backend-owned.
export const HISTORY_RANGE_LIMIT_DAYS: Record<Timeframe, number> = {
  M1: 1,
  M5: 6,
  M15: 20,
  M30: 30,
  H1: 60,
  H2: 90,
  H4: 90,
  H12: 90,
  D1: 180,
  W1: 700,
  MN: 700,
}

export function defaultHistoryRange(timeframe: Timeframe, now = new Date()) {
  const end = now
  const start = new Date(now.getTime() - HISTORY_RANGE_LIMIT_DAYS[timeframe] * DAY_MS)
  return { start: start.toISOString(), end: end.toISOString() }
}

export function requestedHistoryBarSlots(timeframe: Timeframe, start: string, end: string) {
  const startTime = Date.parse(start)
  const endTime = Date.parse(end)
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime)) return Number.POSITIVE_INFINITY
  return Math.ceil((endTime - startTime) / (HISTORY_TIMEFRAME_SECONDS[timeframe] * 1000)) + 1
}

export function historyRangeFitsBarBudget(timeframe: Timeframe, start: string, end: string) {
  return requestedHistoryBarSlots(timeframe, start, end) <= HISTORY_ACQUISITION_MAX_REQUESTED_BARS
}

export function historyRangeIsAllowed(timeframe: Timeframe, start: string, end: string, now = new Date()) {
  const startTime = Date.parse(start)
  const endTime = Date.parse(end)
  const nowTime = now.getTime()
  return Number.isFinite(startTime)
    && Number.isFinite(endTime)
    && endTime > startTime
    && startTime <= nowTime
    && endTime <= nowTime
    && endTime - startTime <= HISTORY_RANGE_LIMIT_DAYS[timeframe] * DAY_MS
    && historyRangeFitsBarBudget(timeframe, start, end)
    && /(?:Z|[+-]\d{2}:\d{2})$/i.test(start)
    && /(?:Z|[+-]\d{2}:\d{2})$/i.test(end)
}

export interface ETFProfileAcquireResponse {
  request_id: string
  outcome: 'cached' | 'no_data' | 'acquired' | 'held' | 'failed'
  refresh: boolean
  refresh_attempted: boolean
  refresh_succeeded: boolean
  profile: ETFProfile
  snapshot?: ETFHoldingsSnapshot | null
  capability?: ETFHoldingsCapability | null
  source_provider?: string | null
  source_operation?: string | null
  provider_request_log_ids: number[]
  message?: string | null
}

export function makeAcquisitionRequestId(): string {
  const cryptoApi = globalThis.crypto
  if (typeof cryptoApi?.randomUUID === 'function') return cryptoApi.randomUUID()
  if (typeof cryptoApi?.getRandomValues !== 'function') {
    throw new Error('A cryptographic random source is required for acquisition request IDs.')
  }

  const bytes = cryptoApi.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6]! & 0x0f) | 0x40
  bytes[8] = (bytes[8]! & 0x3f) | 0x80
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

export function discoverInstruments(query: string, types: string[] = [], limit = 10): Promise<InstrumentDiscoveryResponse> {
  const normalizedQuery = query.trim()
  if (!normalizedQuery || normalizedQuery.length > 100 || types.length > 8) {
    throw new RangeError('Discovery requires a nonblank query up to 100 characters and at most 8 types.')
  }
  return api.post('/instruments/discover', {
    query: normalizedQuery,
    types,
    limit: Math.min(Math.max(limit, 1), 10),
    request_id: makeAcquisitionRequestId(),
  })
}

export function resolveDiscoveredInstrument(candidate: InstrumentDiscoveryCandidate): Promise<InstrumentAcquireResponse> {
  return api.post('/instruments/acquire', {
    symbol: candidate.symbol,
    provider_candidate: {
      provider: candidate.provider,
      symbol: candidate.symbol,
      exchange: candidate.exchange || null,
    },
    request_id: makeAcquisitionRequestId(),
  })
}

export function resolveExistingInstrument(symbol: string): Promise<InstrumentAcquireResponse> {
  return api.post('/instruments/acquire', {
    symbol: symbol.trim(),
    request_id: makeAcquisitionRequestId(),
  })
}

export function acquireInstrumentHistory(
  instrumentId: number,
  request: HistoryAcquisitionRequest,
): Promise<HistoryAcquisitionResponse> {
  if (!Number.isSafeInteger(instrumentId) || instrumentId <= 0) {
    throw new TypeError('A positive canonical instrument ID is required for history acquisition.')
  }
  const startTime = Date.parse(request.start)
  const endTime = Date.parse(request.end)
  const timezoneAware = /(?:Z|[+-]\d{2}:\d{2})$/i.test(request.start)
    && /(?:Z|[+-]\d{2}:\d{2})$/i.test(request.end)
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime) || !timezoneAware) {
    throw new RangeError('History acquisition requires a timezone-aware range.')
  }
  if (endTime <= startTime) throw new RangeError('History acquisition requires an end after start.')
  if (!historyRangeIsAllowed(request.timeframe, request.start, request.end)) {
    throw new RangeError(`History acquisition range must stay within the ${HISTORY_RANGE_LIMIT_DAYS[request.timeframe]} day limit and ${HISTORY_ACQUISITION_MAX_REQUESTED_BARS} inclusive slots.`)
  }
  return api.post(`/instruments/${instrumentId}/history-acquisitions`, {
    ...request,
    request_id: makeAcquisitionRequestId(),
  })
}

export function acquireETFHoldings(symbol: string, refresh: boolean): Promise<ETFProfileAcquireResponse> {
  return api.post(`/etf-holdings/${encodeURIComponent(symbol)}/acquire`, {
    request_id: makeAcquisitionRequestId(),
    refresh,
  })
}
