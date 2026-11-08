import { api, type ApiRequestOptions } from '@/lib/api'
import type { ETFHoldingsCapability, ETFHoldingsSnapshot, ETFProfile, OHLCVBar, Timeframe } from '@/types'

export interface AcquisitionSourceOutcome {
  provider: string
  capability: string
  operation: string
  status: 'eligible' | 'held' | 'attempted' | 'returned' | 'no_match' | 'failed' | 'used' | 'cache_hit'
  reason_code?: string | null
  result_count?: number | null
  error_type?: string | null
  retry_at?: string | null
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
  retry_at?: string | null
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
    instrument_type?: string | null
    domain_key?: string | null
    primary_identifier_type?: string | null
    primary_identifier_value?: string | null
    primary_listing_mic?: string | null
  } | null
  source_outcomes: AcquisitionSourceOutcome[]
  retry_at?: string | null
}

/** Trust only the exact canonical result returned for this selected symbol. */
export function isConfirmedInstrumentSelection(
  response: InstrumentAcquireResponse | null | undefined,
  requestedSymbol: string,
  suppliedInstrumentId?: number | null,
): response is InstrumentAcquireResponse {
  const instrument = response?.instrument
  const instrumentId = instrument?.instrument_id
  const identityStatus = instrument?.identity_status?.trim().toLowerCase()
  return response?.status === 'resolved'
    && ['resolved', 'verified'].includes(identityStatus ?? '')
    && instrument?.symbol.trim().toUpperCase() === requestedSymbol.trim().toUpperCase()
    && Number.isSafeInteger(instrumentId)
    && Number(instrumentId) > 0
    && (suppliedInstrumentId == null || suppliedInstrumentId === instrumentId)
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

export interface HistoryAvailabilityResponse {
  instrument_id: number
  symbol: string
  timeframe: Timeframe
  adjusted: boolean
  status: 'eligible' | 'held'
  earliest_start: string | null
  max_requested_bars: number
  reason_code: string | null
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
  retry_at?: string | null
  legal_metadata?: Record<string, unknown> | null
}

export interface HistoryAcquisitionRequest {
  timeframe: Timeframe
  adjusted: boolean
  start: string
  end: string
}

function retryAtFromResponse(response: {
  retry_at?: string | null
  source_outcomes: AcquisitionSourceOutcome[]
}): string | null | undefined {
  return response.retry_at ?? response.source_outcomes.find(outcome => outcome.retry_at)?.retry_at
}

const DAY_MS = 24 * 60 * 60 * 1000
export const HISTORY_ACQUISITION_MAX_REQUESTED_BARS = 2000
// Keep a rolling provider lookback clear of subsecond request/queue transit.
// This is only a transport safety margin; the server's bound remains the limit.
export const HISTORY_BOUNDARY_TRANSPORT_MARGIN_MS = 60_000

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

// Intraday defaults stay deliberately short. Daily, weekly and monthly default
// to the admitted long-history window; the backend remains authoritative for
// entitlement and native provider coverage.
export const HISTORY_DEFAULT_RANGE_DAYS: Record<Timeframe, number> = {
  M1: 1,
  M5: 6,
  M15: 20,
  M30: 30,
  H1: 60,
  H2: 90,
  H4: 90,
  H12: 90,
// Target roughly two years by default. The current admitted window is always
// read from the server before a history POST and may be shorter or longer.
  D1: 728,
  W1: 728,
  MN: 728,
}

export function defaultHistoryRange(timeframe: Timeframe, now = new Date()) {
  const end = now
  const start = new Date(now.getTime() - HISTORY_DEFAULT_RANGE_DAYS[timeframe] * DAY_MS)
  return { start: start.toISOString(), end: end.toISOString() }
}

export function requestedHistoryBarSlots(timeframe: Timeframe, start: string, end: string) {
  const startTime = Date.parse(start)
  const endTime = Date.parse(end)
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime)) return Number.POSITIVE_INFINITY
  return Math.ceil((endTime - startTime) / (HISTORY_TIMEFRAME_SECONDS[timeframe] * 1000)) + 1
}

/** Construct one bounded older-history slice ending immediately before cache. */
export function olderHistoryRange(
  timeframe: Timeframe,
  before: string,
  slots = HISTORY_ACQUISITION_MAX_REQUESTED_BARS,
  admittedWindowStart?: string,
) {
  const beforeTime = Date.parse(before)
  if (!Number.isFinite(beforeTime) || !Number.isSafeInteger(slots) || slots < 2 || slots > HISTORY_ACQUISITION_MAX_REQUESTED_BARS) {
    throw new RangeError(`Older history requires a valid cursor and 2-${HISTORY_ACQUISITION_MAX_REQUESTED_BARS} slots.`)
  }
  if (timeframe === 'MN') {
    const monthStart = (time: number) => {
      const value = new Date(time)
      value.setUTCDate(1)
      value.setUTCHours(0, 0, 0, 0)
      return value.getTime()
    }
    const previousMonth = (time: number) => {
      const value = new Date(time)
      value.setUTCMonth(value.getUTCMonth() - 1)
      return value.getTime()
    }
    const endTime = monthStart(beforeTime) - 1
    let startTime = monthStart(endTime)
    // Keep month buckets intact while using the same inclusive approximate
    // 30-day slot budget enforced by the application and provider endpoints.
    for (;;) {
      const candidate = previousMonth(startTime)
      if (requestedHistoryBarSlots('MN', new Date(candidate).toISOString(), new Date(endTime).toISOString()) > slots) break
      startTime = candidate
    }
    const windowStart = admittedWindowStart ? Date.parse(admittedWindowStart) : Number.NaN
    if (Number.isFinite(windowStart) && endTime > windowStart) {
      // Include the whole month overlapping the default target. Actual
      // provider entitlement is still enforced by acquireSelectedHistory.
      startTime = Math.max(startTime, monthStart(windowStart))
    }
    if (requestedHistoryBarSlots('MN', new Date(startTime).toISOString(), new Date(endTime).toISOString()) > slots) {
      throw new RangeError(`An older monthly bucket requires more than ${slots} request slots.`)
    }
    return { start: new Date(startTime).toISOString(), end: new Date(endTime).toISOString() }
  }
  const interval = HISTORY_TIMEFRAME_SECONDS[timeframe] * 1000
  const endTime = beforeTime - 1
  const chunkStart = endTime - ((slots - 1) * interval)
  const windowStart = admittedWindowStart ? Date.parse(admittedWindowStart) : Number.NaN
  const calendarWindowStart = Number.isFinite(windowStart) && (timeframe === 'D1' || timeframe === 'W1')
    ? (() => {
      const week = new Date(windowStart)
      week.setUTCDate(week.getUTCDate() - ((week.getUTCDay() + 6) % 7))
      week.setUTCHours(0, 0, 0, 0)
      return week.getTime()
    })()
    : windowStart
  // When filling a short local cache, keep the first request inside the
  // configured default window, aligned to a full UTC week for daily/weekly
  // bars. Once the chart reaches that bucket, later explicit pans may request
  // further bounded chunks for longer entitlements.
  const startTime = Number.isFinite(windowStart) && endTime > windowStart
    ? Math.max(chunkStart, calendarWindowStart)
    : chunkStart
  if (startTime >= endTime) throw new RangeError('Older history cursor is already at the admitted window start.')
  return { start: new Date(startTime).toISOString(), end: new Date(endTime).toISOString() }
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
    && historyRangeFitsBarBudget(timeframe, start, end)
    && /(?:Z|[+-]\d{2}:\d{2})$/i.test(start)
    && /(?:Z|[+-]\d{2}:\d{2})$/i.test(end)
}

export interface ETFProfileAcquireResponse {
  request_id: string
  instrument_id: number
  symbol: string
  outcome: 'cached' | 'no_data' | 'acquired' | 'held' | 'unavailable' | 'failed'
  refresh: boolean
  refresh_attempted: boolean
  refresh_succeeded: boolean
  profile: ETFProfile | null
  snapshot?: ETFHoldingsSnapshot | null
  capability?: ETFHoldingsCapability | null
  source_provider?: string | null
  source_operation?: string | null
  provider_request_log_ids: number[]
  message?: string | null
}

export type SelectedHistoryStage = 'coverage' | 'identity' | 'history' | 'waiting'

export type KnownRetryWaitResult = 'ready' | 'stopped' | 'superseded'

export interface KnownTemporaryRetryLifecycle {
  wait(retryAt: string | null | undefined): Promise<KnownRetryWaitResult>
}

/** One advancing, server-timed retry lifecycle shared by selected-data tasks. */
export function createKnownTemporaryRetryLifecycle(
  isCurrent: () => boolean,
  onWaiting?: (retryAt: string) => void,
  signal?: AbortSignal,
): KnownTemporaryRetryLifecycle {
  let previousRetryAt = 0
  return {
    async wait(retryAt) {
      const dueAt = retryAt ? Date.parse(retryAt) : Number.NaN
      if (!Number.isFinite(dueAt) || dueAt <= Date.now() || dueAt <= previousRetryAt) return 'stopped'
      previousRetryAt = dueAt
      onWaiting?.(retryAt!)
      while (Date.now() < dueAt) {
        if (!isCurrent() || signal?.aborted) return 'superseded'
        const remaining = dueAt - Date.now()
        await new Promise<void>(resolve => {
          const timer = setTimeout(() => {
            signal?.removeEventListener('abort', abort)
            resolve()
          }, Math.min(remaining, 2_147_000_000))
          const abort = () => {
            clearTimeout(timer)
            signal?.removeEventListener('abort', abort)
            resolve()
          }
          if (signal?.aborted) abort()
          else signal?.addEventListener('abort', abort, { once: true })
        })
      }
      return isCurrent() && !signal?.aborted ? 'ready' : 'superseded'
    },
  }
}

export type SelectedHistoryOutcome =
  | { kind: 'already-covered'; coverage: HistoryCoverageSummary }
  | { kind: 'coverage-unavailable' }
  | { kind: 'identity-unavailable'; coverage: HistoryCoverageSummary; status: InstrumentAcquireResponse['status']; reasonCode?: string | null; retryAt?: string | null }
  | { kind: 'admission-held'; coverage: HistoryCoverageSummary }
  | { kind: 'admission-unavailable'; coverage: HistoryCoverageSummary }
  | { kind: 'at-earliest-bound'; coverage: HistoryCoverageSummary; earliestStart: string }
  | { kind: 'acquired'; coverage: HistoryCoverageSummary; result: HistoryAcquisitionResponse }
  | { kind: 'superseded' }

export interface SelectedHistoryOptions {
  retryLifecycle?: KnownTemporaryRetryLifecycle
  signal?: AbortSignal
  onRetryWait?: (retryAt: string) => void
}

function validatedHistoryCoverage(value: unknown): HistoryCoverageSummary | null {
  if (!value || typeof value !== 'object') return null
  const coverage = value as Partial<HistoryCoverageSummary>
  if (!['ready', 'partial', 'missing', 'stale'].includes(String(coverage.status))
    || !Number.isSafeInteger(coverage.bar_count) || (coverage.bar_count ?? -1) < 0
    || !Array.isArray(coverage.missing_slices)) return null
  const slices = coverage.missing_slices
  if (!slices.every(slice => {
    if (!slice || typeof slice.start !== 'string' || typeof slice.end !== 'string') return false
    const start = Date.parse(slice.start)
    const end = Date.parse(slice.end)
    return Number.isFinite(start) && Number.isFinite(end) && start <= end
  })) return null
  if (coverage.status === 'ready') {
    if (slices.length !== 0 || coverage.bar_count === 0) return null
  } else if (slices.length === 0) {
    // A non-ready historical assessment without missing ranges contradicts
    // the response contract; it cannot certify that the requested range is covered.
    return null
  }
  return coverage as HistoryCoverageSummary
}

/**
 * Run the same bounded local-coverage -> canonical-identity -> admitted-history
 * sequence for a deliberate Workstation ticker selection. Merely opening or
 * hydrating a chart never calls this helper.
 */
export async function acquireSelectedHistory(
  symbol: string,
  timeframe: Timeframe,
  adjusted: boolean,
  range: HistoryAcquisitionRequest,
  onStage?: (stage: SelectedHistoryStage, retryAt?: string) => void,
  isCurrent: () => boolean = () => true,
  selectedIdentity?: Promise<InstrumentAcquireResponse>,
  options: SelectedHistoryOptions = {},
): Promise<SelectedHistoryOutcome> {
  const normalized = symbol.trim().toUpperCase()
  if (!normalized) throw new TypeError('A selected ticker is required for history acquisition.')
  const lifecycle = options.retryLifecycle ?? createKnownTemporaryRetryLifecycle(
    isCurrent,
    retryAt => {
      options.onRetryWait?.(retryAt)
      onStage?.('waiting', retryAt)
    },
    options.signal,
  )
  let identity: InstrumentAcquireResponse | null = null

  while (isCurrent() && !options.signal?.aborted) {
    onStage?.('coverage')
    const rawCoverage = await api.get<unknown>(`/coverage/instruments/${encodeURIComponent(normalized)}/ohlcv`, {
      timeframe,
      start: range.start,
      end: range.end,
      mode: 'historical',
      adjusted,
    })
    if (!isCurrent() || options.signal?.aborted) return { kind: 'superseded' }
    const coverage = validatedHistoryCoverage(rawCoverage)
    if (!coverage) return { kind: 'coverage-unavailable' }
    if (coverage.status === 'ready') {
      return { kind: 'already-covered', coverage }
    }

    if (!identity) {
      onStage?.('identity')
      if (selectedIdentity) {
        identity = await selectedIdentity
        if (!isCurrent() || options.signal?.aborted) return { kind: 'superseded' }
        if (identity.status === 'held') {
          const retryAt = retryAtFromResponse(identity)
          if (await lifecycle.wait(retryAt) !== 'ready') {
            if (!isCurrent() || options.signal?.aborted) return { kind: 'superseded' }
          } else {
            identity = await resolveExistingInstrumentWithRetry(normalized, lifecycle, isCurrent)
          }
        }
      } else identity = await resolveExistingInstrumentWithRetry(normalized, lifecycle, isCurrent)
      if (!isCurrent() || options.signal?.aborted) return { kind: 'superseded' }
    }

    if (!identity || identity.status !== 'resolved' || !identity.instrument
      || identity.instrument.symbol.trim().toUpperCase() !== normalized
      || !Number.isSafeInteger(identity.instrument.instrument_id) || identity.instrument.instrument_id <= 0) {
      return {
        kind: 'identity-unavailable',
        coverage,
        status: identity?.status ?? 'failed',
        reasonCode: identity?.reason_code ?? identity?.source_outcomes.find(outcome => outcome.status === 'held')?.reason_code,
        retryAt: identity?.retry_at ?? identity?.source_outcomes.find(outcome => outcome.retry_at)?.retry_at ?? null,
      }
    }

    const availability = await api.get<HistoryAvailabilityResponse>(
      `/instruments/${identity.instrument.instrument_id}/history-availability`,
      { timeframe, adjusted },
    )
    if (!isCurrent() || options.signal?.aborted) return { kind: 'superseded' }
    if (availability.instrument_id !== identity.instrument.instrument_id
      || availability.symbol.trim().toUpperCase() !== normalized
      || availability.timeframe !== timeframe
      || availability.adjusted !== adjusted
      || !['eligible', 'held'].includes(availability.status)
      || !Number.isSafeInteger(availability.max_requested_bars)
      || availability.max_requested_bars < 1) {
      return { kind: 'admission-unavailable', coverage }
    }
    if (availability.status === 'held') return { kind: 'admission-held', coverage }
    if (availability.earliest_start === null || !Number.isFinite(Date.parse(availability.earliest_start))) {
      return { kind: 'admission-unavailable', coverage }
    }

    let admittedRange = { ...range }
    const earliestTime = Date.parse(availability.earliest_start) + HISTORY_BOUNDARY_TRANSPORT_MARGIN_MS
    const rangeEnd = Date.parse(admittedRange.end)
    if (rangeEnd <= earliestTime) {
      return { kind: 'at-earliest-bound', coverage, earliestStart: availability.earliest_start }
    }
    const intervalMs = HISTORY_TIMEFRAME_SECONDS[timeframe] * 1000
    const slotLimit = Math.min(HISTORY_ACQUISITION_MAX_REQUESTED_BARS, availability.max_requested_bars)
    let rangeStart = Date.parse(admittedRange.start)
    rangeStart = Math.max(rangeStart, earliestTime)
    rangeStart = Math.max(rangeStart, rangeEnd - ((slotLimit - 1) * intervalMs))
    if (rangeStart >= rangeEnd) return { kind: 'admission-unavailable', coverage }
    if (rangeStart !== Date.parse(admittedRange.start)) {
      admittedRange = { ...admittedRange, start: new Date(rangeStart).toISOString() }
      const rawBoundedCoverage = await api.get<unknown>(`/coverage/instruments/${encodeURIComponent(normalized)}/ohlcv`, {
        timeframe,
        start: admittedRange.start,
        end: admittedRange.end,
        mode: 'historical',
        adjusted,
      })
      if (!isCurrent() || options.signal?.aborted) return { kind: 'superseded' }
      const boundedCoverage = validatedHistoryCoverage(rawBoundedCoverage)
      if (!boundedCoverage) return { kind: 'coverage-unavailable' }
      if (boundedCoverage.status === 'ready') {
        return { kind: 'already-covered', coverage: boundedCoverage }
      }
    }

    onStage?.('history')
    const result = await acquireInstrumentHistory(identity.instrument.instrument_id, {
      ...admittedRange,
      timeframe,
      adjusted,
    })
    if (!isCurrent() || options.signal?.aborted) return { kind: 'superseded' }
    if (result.status === 'held') {
      const retryAt = retryAtFromResponse(result)
      const waited = await lifecycle.wait(retryAt)
      if (waited === 'ready') continue
      if (waited === 'superseded' || !isCurrent() || options.signal?.aborted) return { kind: 'superseded' }
    }
    return { kind: 'acquired', coverage, result }
  }
  return { kind: 'superseded' }
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

export function discoverInstruments(
  query: string,
  types: string[] = [],
  limit = 10,
  options: ApiRequestOptions = { priority: 'high' },
): Promise<InstrumentDiscoveryResponse> {
  const normalizedQuery = query.trim()
  if (!normalizedQuery || normalizedQuery.length > 100 || types.length > 8) {
    throw new RangeError('Discovery requires a nonblank query up to 100 characters and at most 8 types.')
  }
  return api.post('/instruments/discover', {
    query: normalizedQuery,
    types,
    limit: Math.min(Math.max(limit, 1), 10),
    request_id: makeAcquisitionRequestId(),
  }, options)
}

export function resolveDiscoveredInstrument(
  candidate: InstrumentDiscoveryCandidate,
  options: ApiRequestOptions = { priority: 'high' },
): Promise<InstrumentAcquireResponse> {
  return api.post('/instruments/acquire', {
    symbol: candidate.symbol,
    provider_candidate: {
      provider: candidate.provider,
      symbol: candidate.symbol,
      exchange: candidate.exchange || null,
    },
    request_id: makeAcquisitionRequestId(),
  }, options)
}

export function resolveExistingInstrument(symbol: string): Promise<InstrumentAcquireResponse> {
  return api.post('/instruments/acquire', {
    symbol: symbol.trim(),
    request_id: makeAcquisitionRequestId(),
  })
}

export async function resolveExistingInstrumentWithRetry(
  symbol: string,
  lifecycle: KnownTemporaryRetryLifecycle,
  isCurrent: () => boolean = () => true,
): Promise<InstrumentAcquireResponse> {
  if (!isCurrent()) throw new DOMException('The selected ticker changed before identity resolution.', 'AbortError')
  let response = await resolveExistingInstrument(symbol)
  while (isCurrent() && response.status === 'held') {
    const retryAt = retryAtFromResponse(response)
    if (await lifecycle.wait(retryAt) !== 'ready') return response
    response = await resolveExistingInstrument(symbol)
  }
  return response
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
    throw new RangeError(`History acquisition range must stay within ${HISTORY_ACQUISITION_MAX_REQUESTED_BARS} inclusive slots.`)
  }
  return api.post(`/instruments/${instrumentId}/history-acquisitions`, {
    ...request,
    request_id: makeAcquisitionRequestId(),
  })
}

export function acquireETFHoldings(symbol: string, refresh: boolean, instrumentId?: number | null): Promise<ETFProfileAcquireResponse> {
  if (instrumentId != null && (!Number.isSafeInteger(instrumentId) || instrumentId <= 0)) {
    throw new TypeError('A positive canonical instrument ID is required when supplied.')
  }
  return api.post(`/etf-holdings/${encodeURIComponent(symbol)}/acquire`, {
    request_id: makeAcquisitionRequestId(),
    refresh,
    ...(instrumentId != null ? { instrument_id: instrumentId } : {}),
  })
}

/** Read the producer's authoritative freshness/admission view for one ETF. */
export async function readETFHoldingsCapability(symbol: string, options?: Pick<ApiRequestOptions, 'priority' | 'queueKey' | 'signal'>): Promise<ETFHoldingsCapability | null> {
  const normalized = symbol.trim().toUpperCase()
  if (!normalized) return null
  try {
    const path = `/etf-holdings/${encodeURIComponent(normalized)}/capability`
    return await (options ? api.get<ETFHoldingsCapability>(path, undefined, options) : api.get<ETFHoldingsCapability>(path))
  } catch {
    // An unavailable capability read is unknown, not evidence that a saved
    // snapshot is current. The caller may make one ordinary admitted refresh.
    return null
  }
}

/** Only a producer-qualified current cache is sufficient to skip refresh. */
export function isCurrentETFHoldingsCapability(capability: ETFHoldingsCapability | null | undefined): boolean {
  return capability?.availability === 'current'
    && capability.identity_verified === true
    && capability.usable_for_current_analysis === true
}

/** Holdings eligibility follows the confirmed canonical type, not a search hint. */
export function isEligibleETFHoldingsInstrumentType(instrumentType: string | null | undefined): boolean {
  const normalized = instrumentType?.trim().replace(/\s+/g, ' ').toLowerCase()
  return normalized === 'etf'
    || normalized === 'index etf'
    || normalized === 'etv'
    || normalized === 'exchange traded vehicle'
}
