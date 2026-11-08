import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }))
import { api } from '@/lib/api'
import {
  acquireETFHoldings,
  acquireInstrumentHistory,
  acquireSelectedHistory,
  createKnownTemporaryRetryLifecycle,
  defaultHistoryRange,
  discoverInstruments,
  HISTORY_ACQUISITION_MAX_REQUESTED_BARS,
  HISTORY_DEFAULT_RANGE_DAYS,
  HISTORY_TIMEFRAME_SECONDS,
  historyRangeFitsBarBudget,
  historyRangeIsAllowed,
  isEligibleETFHoldingsInstrumentType,
  isCurrentETFHoldingsCapability,
  isConfirmedInstrumentSelection,
  makeAcquisitionRequestId,
  olderHistoryRange,
  requestedHistoryBarSlots,
  readETFHoldingsCapability,
  resolveExistingInstrumentWithRetry,
  resolveDiscoveredInstrument,
  type InstrumentDiscoveryCandidate,
} from '@/lib/onDemandAcquisition'

const candidate: InstrumentDiscoveryCandidate = {
  symbol: 'OIH', name: 'Oil Services ETF', exchange: 'NYSE Arca', type: 'ETF',
  provider: 'free-source', instrument_id: null, identity_status: 'provider_candidate',
}

describe('confirmed instrument selection', () => {
  const resolved = {
    request_id: 'resolved',
    status: 'resolved' as const,
    instrument: { instrument_id: 44, symbol: 'TCNEW', identity_status: 'verified' },
    source_outcomes: [],
  }

  it('trusts the exact resolved identity without another canonical lookup', () => {
    expect(isConfirmedInstrumentSelection(resolved, 'tcnew')).toBe(true)
    expect(isConfirmedInstrumentSelection(resolved, 'TCNEW', 44)).toBe(true)
  })

  it.each([
    ['different symbol', { ...resolved, instrument: { ...resolved.instrument, symbol: 'OTHER' } }, 'TCNEW', 44],
    ['conflicting supplied id', resolved, 'TCNEW', 45],
    ['non-resolved acquisition', { ...resolved, status: 'held' as const }, 'TCNEW', 44],
    ['unverified identity', { ...resolved, instrument: { ...resolved.instrument, identity_status: 'provider_candidate' } }, 'TCNEW', 44],
    ['invalid canonical id', { ...resolved, instrument: { ...resolved.instrument, instrument_id: 0 } }, 'TCNEW', 0],
  ])('rejects %s', (_label, response, symbol, id) => {
    expect(isConfirmedInstrumentSelection(response as typeof resolved, symbol, id)).toBe(false)
  })
})

beforeEach(() => {
  vi.resetAllMocks()
  vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
})

describe('explicit acquisition API contracts', () => {
  it('shares retry-aware identity and history waits, rechecks availability, and completes only for the current selection', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-06T12:00:00.000Z'))
    const identityRetryAt = new Date(Date.now() + 1_000).toISOString()
    const historyRetryAt = new Date(Date.now() + 2_000).toISOString()
    vi.mocked(api.get)
      .mockResolvedValueOnce({ status: 'missing', bar_count: 0, missing_slices: [{ start: '2026-01-01T00:00:00Z', end: '2026-11-01T00:00:00Z' }] })
      .mockResolvedValueOnce({ instrument_id: 82, symbol: 'IGV', timeframe: 'D1', adjusted: true, status: 'eligible', earliest_start: '2024-01-01T00:00:00Z', max_requested_bars: 2000, reason_code: null })
      .mockResolvedValueOnce({ status: 'missing', bar_count: 0, missing_slices: [{ start: '2026-01-01T00:00:00Z', end: '2026-11-01T00:00:00Z' }] })
      .mockResolvedValueOnce({ instrument_id: 82, symbol: 'IGV', timeframe: 'D1', adjusted: true, status: 'eligible', earliest_start: '2024-01-01T00:00:00Z', max_requested_bars: 2000, reason_code: null })
    vi.mocked(api.post)
      .mockResolvedValueOnce({ request_id: 'identity-held', status: 'held', instrument: null, source_outcomes: [{ provider: 'massive', capability: 'instrument_search', operation: 'resolve', status: 'used', result_count: 1, retry_at: identityRetryAt }] })
      .mockResolvedValueOnce({ request_id: 'identity-ready', status: 'resolved', instrument: { instrument_id: 82, symbol: 'IGV', identity_status: 'resolved' }, source_outcomes: [] })
      .mockResolvedValueOnce({ request_id: 'history-held', status: 'held', instrument_id: 82, symbol: 'IGV', timeframe: 'D1', adjusted: true, requested_start: '2026-01-01T00:00:00Z', requested_end: '2026-11-01T00:00:00Z', coverage: { status: 'missing', bar_count: 0, missing_slices: [] }, bars: [], source_outcomes: [{ provider: 'massive', capability: 'price_history', operation: 'history', status: 'held', retry_at: historyRetryAt }] })
      .mockResolvedValueOnce({ request_id: 'history-ready', status: 'complete', instrument_id: 82, symbol: 'IGV', timeframe: 'D1', adjusted: true, requested_start: '2026-01-01T00:00:00Z', requested_end: '2026-11-01T00:00:00Z', coverage: { status: 'ready', bar_count: 2, missing_slices: [] }, bars: [], source_outcomes: [] })

    const isCurrent = vi.fn(() => true)
    const stageReads: Array<{ stage: string; retryAt?: string }> = []
    const retryLifecycle = createKnownTemporaryRetryLifecycle(isCurrent, retryAt => stageReads.push({ stage: 'waiting', retryAt }))
    const identityPromise = resolveExistingInstrumentWithRetry('IGV', retryLifecycle, isCurrent)
    const acquisition = acquireSelectedHistory('IGV', 'D1', true, {
      timeframe: 'D1', adjusted: true, start: '2026-01-01T00:00:00Z', end: '2026-11-01T00:00:00Z',
    }, (stage, retryAt) => stageReads.push({ stage, retryAt }), isCurrent, identityPromise, { retryLifecycle })

    await vi.advanceTimersByTimeAsync(1_000)
    await vi.advanceTimersByTimeAsync(1_000)
    const result = await acquisition
    expect(result).toMatchObject({ kind: 'acquired', result: { status: 'complete' } })
    expect(api.post.mock.calls.map(([path]) => path)).toEqual([
      '/instruments/acquire', '/instruments/acquire',
      '/instruments/82/history-acquisitions', '/instruments/82/history-acquisitions',
    ])
    expect(api.get.mock.calls.map(([path]) => path)).toEqual([
      '/coverage/instruments/IGV/ohlcv', '/instruments/82/history-availability',
      '/coverage/instruments/IGV/ohlcv', '/instruments/82/history-availability',
    ])
    expect(stageReads.filter(stage => stage.stage === 'waiting').map(stage => stage.retryAt)).toEqual([identityRetryAt, historyRetryAt])
    vi.useRealTimers()
  })

  it('resumes a held history response when cached fallback bars report a known retry on a used outcome', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-06T12:00:00.000Z'))
    const retryAt = new Date(Date.now() + 1_000).toISOString()
    const missing = { status: 'missing', bar_count: 0, missing_slices: [{ start: '2026-01-01T00:00:00Z', end: '2026-11-01T00:00:00Z' }] }
    const availability = { instrument_id: 82, symbol: 'IGV', timeframe: 'D1', adjusted: true, status: 'eligible', earliest_start: '2024-01-01T00:00:00Z', max_requested_bars: 2000, reason_code: null }
    vi.mocked(api.get)
      .mockResolvedValueOnce(missing)
      .mockResolvedValueOnce(availability)
      .mockResolvedValueOnce(missing)
      .mockResolvedValueOnce(availability)
    const cachedBars = Array.from({ length: 124 }, (_, index) => ({
      ts: new Date(Date.now() - index * 86_400_000).toISOString(),
      open: 10, high: 11, low: 9, close: 10, volume: 100,
    }))
    vi.mocked(api.post)
      .mockResolvedValueOnce({
        request_id: 'history-held-cached', status: 'held', instrument_id: 82, symbol: 'IGV', timeframe: 'D1', adjusted: true,
        requested_start: '2026-01-01T00:00:00Z', requested_end: '2026-11-01T00:00:00Z',
        coverage: { status: 'partial', bar_count: 124, missing_slices: [{ start: '2026-01-01T00:00:00Z', end: '2026-11-01T00:00:00Z' }] },
        bars: cachedBars,
        source_outcomes: [{ provider: 'massive', capability: 'price_history', operation: 'fetch_ohlcv:D1', status: 'used', result_count: 124, error_type: 'ProviderQuotaAdmissionError', reason_code: 'provider_quota_admission_denied', retry_at: retryAt }],
      })
      .mockResolvedValueOnce({
        request_id: 'history-ready-after-cache', status: 'complete', instrument_id: 82, symbol: 'IGV', timeframe: 'D1', adjusted: true,
        requested_start: '2026-01-01T00:00:00Z', requested_end: '2026-11-01T00:00:00Z',
        coverage: { status: 'ready', bar_count: 124, missing_slices: [] }, bars: cachedBars, source_outcomes: [],
      })

    const waits: string[] = []
    const lifecycle = createKnownTemporaryRetryLifecycle(() => true, value => waits.push(value))
    const identity = Promise.resolve({
      request_id: 'identity-ready', status: 'resolved',
      instrument: { instrument_id: 82, symbol: 'IGV', identity_status: 'resolved' }, source_outcomes: [],
    } as any)
    const acquisition = acquireSelectedHistory('IGV', 'D1', true, {
      timeframe: 'D1', adjusted: true, start: '2026-01-01T00:00:00Z', end: '2026-11-01T00:00:00Z',
    }, undefined, () => true, identity, { retryLifecycle: lifecycle })

    await vi.advanceTimersByTimeAsync(1_000)
    const result = await acquisition
    expect(result).toMatchObject({ kind: 'acquired', result: { status: 'complete' } })
    expect(cachedBars).toHaveLength(124)
    expect(waits).toEqual([retryAt])
    expect(api.post).toHaveBeenCalledTimes(2)
    expect(api.post.mock.calls.map(([path]) => path)).toEqual([
      '/instruments/82/history-acquisitions', '/instruments/82/history-acquisitions',
    ])
    vi.useRealTimers()
  })

  it('cancels a held cached-fallback retry after the selection is superseded', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-06T12:00:00.000Z'))
    const retryAt = new Date(Date.now() + 30_000).toISOString()
    vi.mocked(api.get)
      .mockResolvedValueOnce({ status: 'missing', bar_count: 0, missing_slices: [{ start: '2026-01-01T00:00:00Z', end: '2026-11-01T00:00:00Z' }] })
      .mockResolvedValueOnce({ instrument_id: 82, symbol: 'IGV', timeframe: 'D1', adjusted: true, status: 'eligible', earliest_start: '2024-01-01T00:00:00Z', max_requested_bars: 2000, reason_code: null })
    vi.mocked(api.post).mockResolvedValueOnce({
      request_id: 'history-held-cached', status: 'held', instrument_id: 82, symbol: 'IGV', timeframe: 'D1', adjusted: true,
      requested_start: '2026-01-01T00:00:00Z', requested_end: '2026-11-01T00:00:00Z',
      coverage: { status: 'partial', bar_count: 124, missing_slices: [{ start: '2026-01-01T00:00:00Z', end: '2026-11-01T00:00:00Z' }] },
      bars: [{ ts: '2026-11-05T00:00:00Z', open: 10, high: 11, low: 9, close: 10, volume: 100 }],
      source_outcomes: [{ provider: 'massive', capability: 'price_history', operation: 'fetch_ohlcv:D1', status: 'used', result_count: 124, error_type: 'ProviderQuotaAdmissionError', reason_code: 'provider_quota_admission_denied', retry_at: retryAt }],
    })

    const controller = new AbortController()
    let current = true
    const waits: string[] = []
    const lifecycle = createKnownTemporaryRetryLifecycle(() => current, value => waits.push(value), controller.signal)
    const identity = Promise.resolve({
      request_id: 'identity-ready', status: 'resolved',
      instrument: { instrument_id: 82, symbol: 'IGV', identity_status: 'resolved' }, source_outcomes: [],
    } as any)
    const acquisition = acquireSelectedHistory('IGV', 'D1', true, {
      timeframe: 'D1', adjusted: true, start: '2026-01-01T00:00:00Z', end: '2026-11-01T00:00:00Z',
    }, undefined, () => current, identity, { retryLifecycle: lifecycle, signal: controller.signal })
    await vi.advanceTimersByTimeAsync(0)
    expect(waits).toEqual([retryAt])
    current = false
    controller.abort()

    await expect(acquisition).resolves.toMatchObject({ kind: 'superseded' })
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(api.get).toHaveBeenCalledTimes(2)
    vi.useRealTimers()
  })

  it('cancels a superseded known hold without sending its obsolete retry request', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-06T12:00:00.000Z'))
    const retryAt = new Date(Date.now() + 30_000).toISOString()
    vi.mocked(api.get).mockResolvedValueOnce({ status: 'missing', bar_count: 0, missing_slices: [{ start: '2026-01-01T00:00:00Z', end: '2026-11-01T00:00:00Z' }] })
    vi.mocked(api.post).mockResolvedValueOnce({ request_id: 'identity-held', status: 'held', instrument: null, source_outcomes: [{ provider: 'massive', capability: 'instrument_search', operation: 'resolve', status: 'held', retry_at: retryAt }] })
    const controller = new AbortController()
    let current = true
    const lifecycle = createKnownTemporaryRetryLifecycle(() => current, undefined, controller.signal)
    const identityPromise = resolveExistingInstrumentWithRetry('IGV', lifecycle, () => current)
    const acquisition = acquireSelectedHistory('IGV', 'D1', true, {
      timeframe: 'D1', adjusted: true, start: '2026-01-01T00:00:00Z', end: '2026-11-01T00:00:00Z',
    }, undefined, () => current, identityPromise, { retryLifecycle: lifecycle, signal: controller.signal })
    await vi.advanceTimersByTimeAsync(0)
    current = false
    controller.abort()
    const result = await acquisition
    expect(result.kind).toBe('superseded')
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(api.get).toHaveBeenCalledTimes(1)
    vi.useRealTimers()
  })

  it('admits issuer holdings only for confirmed ETF vehicle types and keeps ETN distinct', () => {
    expect(isEligibleETFHoldingsInstrumentType('ETF')).toBe(true)
    expect(isEligibleETFHoldingsInstrumentType('Index ETF')).toBe(true)
    expect(isEligibleETFHoldingsInstrumentType(' Exchange   Traded Vehicle ')).toBe(true)
    expect(isEligibleETFHoldingsInstrumentType('ETV')).toBe(true)
    expect(isEligibleETFHoldingsInstrumentType('ETN')).toBe(false)
    expect(isEligibleETFHoldingsInstrumentType('Exchange Traded Product')).toBe(false)
    expect(isEligibleETFHoldingsInstrumentType('Stock')).toBe(false)
    expect(isEligibleETFHoldingsInstrumentType(null)).toBe(false)
  })

  it('reads the selected ETF capability without turning the read into acquisition', async () => {
    const capability = {
      availability: 'current', source_tier: 'issuer_native', identity_verified: true,
      usable_for_current_analysis: true, displayable_last_known: true,
      consecutive_failures: 0, reason: 'Current fixture cache.',
      symbol_audit: { tier: 0, outcome: 'not_run', evidence_state: 'test_fixture', next_action: '', evidence_refs: [] },
    }
    vi.mocked(api.get).mockResolvedValueOnce(capability)

    expect(await readETFHoldingsCapability(' spy ')).toEqual(capability)
    expect(api.get).toHaveBeenCalledWith('/etf-holdings/SPY/capability')
    expect(api.post).not.toHaveBeenCalled()
    expect(isCurrentETFHoldingsCapability(capability)).toBe(true)
    expect(isCurrentETFHoldingsCapability({ ...capability, availability: 'stale' })).toBe(false)
    expect(isCurrentETFHoldingsCapability({ ...capability, usable_for_current_analysis: false })).toBe(false)
    expect(isCurrentETFHoldingsCapability({ ...capability, identity_verified: false })).toBe(false)
  })

  it('treats a capability-read failure as unknown rather than current', async () => {
    vi.mocked(api.get).mockRejectedValueOnce(new Error('offline'))
    const capability = await readETFHoldingsCapability('OIH')
    expect(capability).toBeNull()
    expect(isCurrentETFHoldingsCapability(capability)).toBe(false)
  })

  it('uses the secure-context UUID API when available', () => {
    expect(makeAcquisitionRequestId()).toBe('f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d')
  })

  it('creates an RFC 4122 version 4 ID from cryptographic bytes when randomUUID is unavailable', () => {
    vi.stubGlobal('crypto', {
      getRandomValues: (bytes: Uint8Array) => {
        bytes.set(Array.from({ length: 16 }, (_, index) => index))
        return bytes
      },
    } as unknown as Crypto)

    expect(makeAcquisitionRequestId()).toBe('00010203-0405-4607-8809-0a0b0c0d0e0f')
  })

  it('fails closed when no cryptographic random source is available', () => {
    vi.stubGlobal('crypto', {} as Crypto)
    expect(() => makeAcquisitionRequestId()).toThrow('A cryptographic random source is required')
  })

  it('submits bounded discovery only through its explicit service call', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ request_id: 'r1', status: 'complete', candidates: [], source_outcomes: [] })
    await discoverInstruments(' OIH ', ['ETF'], 100)
    expect(api.post).toHaveBeenCalledWith('/instruments/discover', {
      query: 'OIH', types: ['ETF'], limit: 10, request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
    }, expect.objectContaining({ priority: 'high' }))
  })

  it('resolves a selected candidate without treating its nullable ID as canonical', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ request_id: 'r2', status: 'resolved', instrument: { instrument_id: 43, symbol: 'OIH', identity_status: 'verified' }, source_outcomes: [] })
    await resolveDiscoveredInstrument(candidate)
    expect(api.post).toHaveBeenCalledWith('/instruments/acquire', {
      symbol: 'OIH', provider_candidate: { provider: 'free-source', symbol: 'OIH', exchange: 'NYSE Arca' },
      request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
    }, expect.objectContaining({ priority: 'high' }))
  })

  it('requests one canonical instrument and finite UTC history range', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ status: 'held' })
    await acquireInstrumentHistory(43, {
      timeframe: 'D1', adjusted: true,
      start: '2026-01-01T00:00:00.000Z', end: '2026-01-31T23:59:59.999Z',
    })
    expect(api.post).toHaveBeenCalledWith('/instruments/43/history-acquisitions', {
      timeframe: 'D1', adjusted: true,
      start: '2026-01-01T00:00:00.000Z', end: '2026-01-31T23:59:59.999Z',
      request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
    })
  })

  it('rejects invalid identity or non-finite history bounds before transport', () => {
    expect(() => acquireInstrumentHistory(0, {
      timeframe: 'D1', adjusted: true,
      start: '2026-01-01T00:00:00.000Z', end: '2026-01-31T23:59:59.999Z',
    })).toThrow('positive canonical instrument ID')
    expect(() => acquireInstrumentHistory(43, {
      timeframe: 'D1', adjusted: true,
      start: '2026-01-01', end: '2026-01-31',
    })).toThrow('timezone-aware range')
    expect(() => acquireInstrumentHistory(43, {
      timeframe: 'D1', adjusted: true,
      start: '2026-02-01T00:00:00.000Z', end: '2026-01-31T23:59:59.999Z',
    })).toThrow('end after start')
    expect(api.post).not.toHaveBeenCalled()
  })

  it('defaults daily and slower charts to the admitted long-history window without a lifetime day ceiling', () => {
    const now = new Date('2026-10-27T12:00:00.000Z')
    const daily = defaultHistoryRange('D1', now)
    const intraday = defaultHistoryRange('M5', now)
    expect(Date.parse(daily.end)).toBe(now.getTime())
    expect(Date.parse(daily.end) - Date.parse(daily.start)).toBe(728 * 24 * 60 * 60 * 1000)
    expect(Date.parse(intraday.end) - Date.parse(intraday.start)).toBe(6 * 24 * 60 * 60 * 1000)
    expect(historyRangeIsAllowed('D1', daily.start, daily.end, now)).toBe(true)
    expect(historyRangeIsAllowed('D1', '2025-06-01T00:00:00.000Z', daily.end, now)).toBe(true)
    expect(historyRangeIsAllowed('D1', daily.start, '2026-10-28T00:00:00.000Z', now)).toBe(false)
    expect(historyRangeIsAllowed('M1', '2026-01-01T00:00:00.000Z', daily.end, now)).toBe(false)
  })

  it('keeps every timeframe default below the Provider inclusive 2,000-slot budget', () => {
    const now = new Date('2026-10-27T12:00:00.000Z')
    const expectedSeconds = {
      M1: 60, M5: 300, M15: 900, M30: 1800, H1: 3600, H2: 7200,
      H4: 14400, H12: 43200, D1: 86400, W1: 604800, MN: 2592000,
    }
    expect(HISTORY_TIMEFRAME_SECONDS).toEqual(expectedSeconds)
    expect(HISTORY_DEFAULT_RANGE_DAYS).toMatchObject({ M1: 1, M5: 6, M15: 20, D1: 728, W1: 728, MN: 728 })
    expect(HISTORY_ACQUISITION_MAX_REQUESTED_BARS).toBe(2000)

    for (const [timeframe, days] of Object.entries(HISTORY_DEFAULT_RANGE_DAYS) as [keyof typeof expectedSeconds, number][]) {
      const range = defaultHistoryRange(timeframe, now)
      const expectedSlots = Math.ceil((days * 86400) / expectedSeconds[timeframe]) + 1
      expect(requestedHistoryBarSlots(timeframe, range.start, range.end)).toBe(expectedSlots)
      expect(expectedSlots).toBeLessThanOrEqual(2000)
      expect(historyRangeIsAllowed(timeframe, range.start, range.end, now)).toBe(true)
    }
  })

  it('counts both inclusive endpoints at the exact 2,000-slot boundary', () => {
    const now = new Date('2026-10-27T12:00:00.000Z')
    const end = now.toISOString()
    const withinStart = new Date(now.getTime() - 1999 * 60_000).toISOString()
    const overStart = new Date(now.getTime() - 2000 * 60_000).toISOString()

    expect(requestedHistoryBarSlots('M1', withinStart, end)).toBe(2000)
    expect(historyRangeFitsBarBudget('M1', withinStart, end)).toBe(true)
    expect(requestedHistoryBarSlots('M1', overStart, end)).toBe(2001)
    expect(historyRangeFitsBarBudget('M1', overStart, end)).toBe(false)
  })

  it('clamps the first older request to the admitted default window and keeps each slice within 2,000 slots', () => {
    const now = new Date('2026-11-06T12:00:00.000Z')
    const cachedStart = new Date(now.getTime() - 180 * 24 * 60 * 60 * 1000).toISOString()
    const defaultStart = defaultHistoryRange('D1', now).start
    const gap = olderHistoryRange('D1', cachedStart, undefined, defaultStart)
    expect(gap.start).toBe('2024-11-04T00:00:00.000Z')
    expect(Date.parse(gap.end)).toBeLessThan(Date.parse(cachedStart))
    expect(historyRangeIsAllowed('D1', gap.start, gap.end, now)).toBe(true)
    expect(requestedHistoryBarSlots('D1', gap.start, gap.end)).toBeLessThanOrEqual(HISTORY_ACQUISITION_MAX_REQUESTED_BARS)

    const beyondDefault = olderHistoryRange('W1', defaultStart, undefined, defaultStart)
    expect(requestedHistoryBarSlots('W1', beyondDefault.start, beyondDefault.end)).toBe(HISTORY_ACQUISITION_MAX_REQUESTED_BARS)
  })

  it('aligns D1/W1 default-window backfill to Monday UTC and continues in bounded older chunks', () => {
    const admittedStart = '2024-11-08T07:00:00.000Z'
    const mondayCursor = '2024-11-11T05:00:00.000Z'

    const daily = olderHistoryRange('D1', mondayCursor, undefined, admittedStart)
    expect(daily.start).toBe('2024-11-04T00:00:00.000Z')
    expect(daily.end).toBe('2024-11-11T04:59:59.999Z')
    expect(Date.parse(daily.start)).toBeLessThanOrEqual(Date.parse('2024-11-08T05:00:00.000Z'))
    expect(requestedHistoryBarSlots('D1', daily.start, daily.end)).toBeLessThanOrEqual(2000)

    const weekly = olderHistoryRange('W1', mondayCursor, undefined, admittedStart)
    expect(weekly.start).toBe('2024-11-04T00:00:00.000Z')
    expect(weekly.end).toBe('2024-11-11T04:59:59.999Z')
    expect(new Date(weekly.start).getUTCDay()).toBe(1)
    expect(requestedHistoryBarSlots('W1', weekly.start, weekly.end)).toBeLessThanOrEqual(2000)

    for (const timeframe of ['D1', 'W1'] as const) {
      const first = olderHistoryRange(timeframe, '2026-06-01T00:00:00.000Z', undefined, admittedStart)
      const continuation = olderHistoryRange(timeframe, first.start, undefined, admittedStart)
      expect(Date.parse(continuation.start)).toBeLessThan(Date.parse(admittedStart))
      expect(requestedHistoryBarSlots(timeframe, continuation.start, continuation.end)).toBeLessThanOrEqual(2000)
    }
  })

  it('builds older monthly history from whole calendar buckets within the existing slot bound', () => {
    const before = '2026-11-01T00:00:00.000Z'
    const bounded = olderHistoryRange('MN', before, 25)
    expect(bounded.end).toBe('2026-10-31T23:59:59.999Z')
    expect(new Date(bounded.start).toISOString().slice(8, 10)).toBe('01')
    expect(new Date(bounded.start).toISOString().slice(11, 23)).toBe('00:00:00.000')
    expect(requestedHistoryBarSlots('MN', bounded.start, bounded.end)).toBeLessThanOrEqual(25)

    const maxBounded = olderHistoryRange('MN', before)
    expect(new Date(maxBounded.start).toISOString().slice(8, 10)).toBe('01')
    expect(requestedHistoryBarSlots('MN', maxBounded.start, maxBounded.end)).toBeLessThanOrEqual(2000)

    const defaultWindow = olderHistoryRange('MN', before, 25, '2024-11-08T12:00:00.000Z')
    // The 25-slot approximation cannot fit every day of the overlapping
    // November bucket, so start at the next complete month within budget.
    expect(defaultWindow.start).toBe('2024-12-01T00:00:00.000Z')
    expect(requestedHistoryBarSlots('MN', defaultWindow.start, defaultWindow.end)).toBeLessThanOrEqual(25)
  })

  it('keeps ETF acquire refresh semantics explicit and distinct', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ outcome: 'cached', refresh: false })
    await acquireETFHoldings('OIH', false)
    await acquireETFHoldings('OIH', true)
    expect(api.post).toHaveBeenNthCalledWith(1, '/etf-holdings/OIH/acquire', {
      request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d', refresh: false,
    })
    expect(api.post).toHaveBeenNthCalledWith(2, '/etf-holdings/OIH/acquire', {
      request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d', refresh: true,
    })
  })

  it('checks selected-ticker coverage locally before any identity or history request', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ status: 'ready', bar_count: 20, missing_slices: [] })
    const stages: string[] = []

    const result = await acquireSelectedHistory('SPY', 'D1', true, {
      timeframe: 'D1', adjusted: true,
      start: '2026-10-01T00:00:00.000Z', end: '2026-10-20T00:00:00.000Z',
    }, stage => stages.push(stage))

    expect(result.kind).toBe('already-covered')
    expect(stages).toEqual(['coverage'])
    expect(api.get).toHaveBeenCalledWith('/coverage/instruments/SPY/ohlcv', {
      timeframe: 'D1', start: '2026-10-01T00:00:00.000Z', end: '2026-10-20T00:00:00.000Z',
      mode: 'historical', adjusted: true,
    })
    expect(api.post).not.toHaveBeenCalled()
  })

  it.each([
    ['non-ready assessment without missing ranges', { status: 'partial', bar_count: 8, missing_slices: [] }],
    ['missing slice list', { status: 'partial', bar_count: 8 }],
    ['ready assessment with missing ranges', { status: 'ready', bar_count: 8, missing_slices: [{ start: '2026-01-01T00:00:00Z', end: '2026-01-02T00:00:00Z' }] }],
  ])('does not accept contradictory or malformed coverage as complete (%s)', async (_name, response) => {
    vi.mocked(api.get).mockResolvedValueOnce(response as any)
    const result = await acquireSelectedHistory('SPY', 'D1', true, {
      timeframe: 'D1', adjusted: true,
      start: '2026-01-01T00:00:00.000Z', end: '2026-10-20T00:00:00.000Z',
    })

    expect(result.kind).toBe('coverage-unavailable')
    expect(api.get).toHaveBeenCalledTimes(1)
    expect(api.post).not.toHaveBeenCalled()
  })

  it('fails honestly when bounded recheck returns a non-ready assessment with no gaps', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce({ status: 'partial', bar_count: 1, missing_slices: [{ start: '2024-01-01T00:00:00Z', end: '2026-01-01T00:00:00Z' }] })
      .mockResolvedValueOnce({ instrument_id: 82, symbol: 'IGV', timeframe: 'D1', adjusted: true, status: 'eligible', earliest_start: '2025-01-01T00:00:00Z', max_requested_bars: 2000, reason_code: null })
      .mockResolvedValueOnce({ status: 'partial', bar_count: 1, missing_slices: [] })
    const identity = Promise.resolve({ request_id: 'cached-identity', status: 'resolved', instrument: { instrument_id: 82, symbol: 'IGV', identity_status: 'resolved' }, source_outcomes: [] } as any)

    const result = await acquireSelectedHistory('IGV', 'D1', true, {
      timeframe: 'D1', adjusted: true,
      start: '2024-01-01T00:00:00.000Z', end: '2026-01-01T00:00:00.000Z',
    }, undefined, () => true, identity)

    expect(result.kind).toBe('coverage-unavailable')
    expect(api.get).toHaveBeenCalledTimes(3)
    expect(api.post).not.toHaveBeenCalled()
  })

  it('stops before history when selected-instrument identity is not resolved', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ status: 'missing', bar_count: 0, missing_slices: [{ start: '2026-10-01T00:00:00Z', end: '2026-10-20T00:00:00Z' }] })
    vi.mocked(api.post).mockResolvedValueOnce({ request_id: 'held', status: 'held', instrument: null, source_outcomes: [] })
    const stages: string[] = []

    const result = await acquireSelectedHistory('BWET', 'D1', true, {
      timeframe: 'D1', adjusted: true,
      start: '2026-10-01T00:00:00.000Z', end: '2026-10-20T00:00:00.000Z',
    }, stage => stages.push(stage))

    expect(result).toMatchObject({ kind: 'identity-unavailable', status: 'held' })
    expect(stages).toEqual(['coverage', 'identity'])
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(api.post).toHaveBeenCalledWith('/instruments/acquire', {
      symbol: 'BWET', request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
    })
  })

  it('fails closed when an eligible availability response has no reviewed lower bound', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ status: 'missing', bar_count: 0, missing_slices: [{ start: '2025-01-01T00:00:00Z', end: '2026-01-01T00:00:00Z' }] })
      .mockResolvedValueOnce({
        instrument_id: 82, symbol: 'IGV', timeframe: 'D1', adjusted: true, status: 'eligible',
        earliest_start: null, max_requested_bars: 2000, reason_code: null,
      })
    vi.mocked(api.post).mockResolvedValueOnce({ request_id: 'identity', status: 'resolved', instrument: { instrument_id: 82, symbol: 'IGV', identity_status: 'resolved' }, source_outcomes: [] })

    const result = await acquireSelectedHistory('IGV', 'D1', true, {
      timeframe: 'D1', adjusted: true,
      start: '2025-01-01T00:00:00.000Z', end: '2026-01-01T00:00:00.000Z',
    })

    expect(result.kind).toBe('admission-unavailable')
    expect(api.get).toHaveBeenNthCalledWith(2, '/instruments/82/history-availability', { timeframe: 'D1', adjusted: true })
    expect(api.post).toHaveBeenCalledTimes(1)
  })

  it('keeps a held availability response retryable and does not submit history', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ status: 'missing', bar_count: 2, missing_slices: [{ start: '2024-01-01T00:00:00Z', end: '2025-01-01T00:00:00Z' }] })
      .mockResolvedValueOnce({
        instrument_id: 82, symbol: 'IGV', timeframe: 'D1', adjusted: true, status: 'held',
        earliest_start: null, max_requested_bars: 2000, reason_code: 'provider_quota_admission_denied',
      })
    vi.mocked(api.post).mockResolvedValueOnce({ request_id: 'identity', status: 'resolved', instrument: { instrument_id: 82, symbol: 'IGV', identity_status: 'resolved' }, source_outcomes: [] })

    const result = await acquireSelectedHistory('IGV', 'D1', true, {
      timeframe: 'D1', adjusted: true,
      start: '2024-01-01T00:00:00.000Z', end: '2025-01-01T00:00:00.000Z',
    })

    expect(result.kind).toBe('admission-held')
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(api.post).not.toHaveBeenCalledWith('/instruments/82/history-acquisitions', expect.anything())
  })

  it('clamps older history to the reviewed rolling bound plus a transport margin and the server slot limit', async () => {
    const availabilityStart = '2024-01-01T00:00:00.000Z'
    vi.mocked(api.get)
      .mockResolvedValueOnce({ status: 'missing', bar_count: 10, missing_slices: [{ start: '2020-01-01T00:00:00Z', end: '2024-01-02T00:00:00Z' }] })
      .mockResolvedValueOnce({
        instrument_id: 82, symbol: 'IGV', timeframe: 'D1', adjusted: true, status: 'eligible',
        earliest_start: availabilityStart, max_requested_bars: 120, reason_code: null,
      })
      .mockResolvedValueOnce({ status: 'partial', bar_count: 10, missing_slices: [{ start: '2024-01-01T00:00:00Z', end: '2024-01-02T00:00:00Z' }] })
    vi.mocked(api.post)
      .mockResolvedValueOnce({ request_id: 'identity', status: 'resolved', instrument: { instrument_id: 82, symbol: 'IGV', identity_status: 'resolved' }, source_outcomes: [] })
      .mockResolvedValueOnce({ request_id: 'history', status: 'partial', instrument_id: 82, symbol: 'IGV', timeframe: 'D1', adjusted: true, requested_start: availabilityStart, requested_end: '2024-01-02T00:00:00Z', coverage: { status: 'partial', bar_count: 1, missing_slices: [] }, bars: [], source_outcomes: [] })

    const result = await acquireSelectedHistory('IGV', 'D1', true, {
      timeframe: 'D1', adjusted: true,
      start: '2020-01-01T00:00:00.000Z', end: '2024-01-02T00:00:00.000Z',
    })

    expect(result.kind).toBe('acquired')
    const request = vi.mocked(api.post).mock.calls.find(([path]) => String(path).includes('/history-acquisitions'))
    const payload = request?.[1] as { start: string; end: string }
    expect(Date.parse(payload.start)).toBeGreaterThanOrEqual(Date.parse(availabilityStart) + 60_000)
    expect(Date.parse(payload.end) - Date.parse(payload.start)).toBeLessThanOrEqual(119 * 86_400_000)
    expect(payload.end).toBe('2024-01-02T00:00:00.000Z')
  })

  it('acquires only the selected canonical ticker and selected bounded interval', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce({ status: 'missing', bar_count: 0, missing_slices: [{ start: '2026-10-01T00:00:00Z', end: '2026-10-20T00:00:00Z' }] })
      .mockResolvedValueOnce({ instrument_id: 82, symbol: 'IGV', timeframe: 'D1', adjusted: true, status: 'eligible', earliest_start: '2024-01-01T00:00:00Z', max_requested_bars: 2000, reason_code: null })
    vi.mocked(api.post)
      .mockResolvedValueOnce({ request_id: 'identity', status: 'resolved', instrument: { instrument_id: 82, symbol: 'IGV', identity_status: 'resolved' }, source_outcomes: [] })
      .mockResolvedValueOnce({ request_id: 'history', status: 'partial', instrument_id: 82, symbol: 'IGV', timeframe: 'D1', adjusted: true, requested_start: '2026-10-01T00:00:00Z', requested_end: '2026-10-20T00:00:00Z', coverage: { status: 'partial', bar_count: 3, missing_slices: [] }, bars: [], source_outcomes: [] })
    const stages: string[] = []

    const result = await acquireSelectedHistory('IGV', 'D1', true, {
      timeframe: 'D1', adjusted: true,
      start: '2026-10-01T00:00:00.000Z', end: '2026-10-20T00:00:00.000Z',
    }, stage => stages.push(stage))

    expect(result.kind).toBe('acquired')
    expect(stages).toEqual(['coverage', 'identity', 'history'])
    expect(api.post).toHaveBeenNthCalledWith(2, '/instruments/82/history-acquisitions', {
      timeframe: 'D1', adjusted: true,
      start: '2026-10-01T00:00:00.000Z', end: '2026-10-20T00:00:00.000Z',
      request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
    })
  })

  it('reuses an identity promise supplied by the deliberate selection instead of resolving twice', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce({ status: 'missing', bar_count: 0, missing_slices: [{ start: '2026-10-01T00:00:00Z', end: '2026-10-20T00:00:00Z' }] })
      .mockResolvedValueOnce({ instrument_id: 82, symbol: 'IGV', timeframe: 'D1', adjusted: true, status: 'eligible', earliest_start: '2024-01-01T00:00:00Z', max_requested_bars: 2000, reason_code: null })
    vi.mocked(api.post).mockResolvedValueOnce({ request_id: 'history', status: 'partial', instrument_id: 82, symbol: 'IGV', timeframe: 'D1', adjusted: true, requested_start: '2026-10-01T00:00:00Z', requested_end: '2026-10-20T00:00:00Z', coverage: { status: 'partial', bar_count: 3, missing_slices: [] }, bars: [], source_outcomes: [] })
    const selectedIdentity = Promise.resolve({
      request_id: 'selection-identity', status: 'resolved' as const,
      instrument: { instrument_id: 82, symbol: 'IGV', identity_status: 'resolved' }, source_outcomes: [],
    })

    const result = await acquireSelectedHistory('IGV', 'D1', true, {
      timeframe: 'D1', adjusted: true,
      start: '2026-10-01T00:00:00.000Z', end: '2026-10-20T00:00:00.000Z',
    }, undefined, () => true, selectedIdentity)

    expect(result.kind).toBe('acquired')
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(api.post).toHaveBeenCalledWith('/instruments/82/history-acquisitions', expect.any(Object))
  })

  it('does not advance a stale selection from local coverage into identity or history requests', async () => {
    let resolveCoverage!: (value: unknown) => void
    vi.mocked(api.get).mockReturnValueOnce(new Promise(resolve => { resolveCoverage = resolve }) as never)
    let current = true
    const pending = acquireSelectedHistory('OIH', 'D1', true, {
      timeframe: 'D1', adjusted: true,
      start: '2026-10-01T00:00:00.000Z', end: '2026-10-20T00:00:00.000Z',
    }, undefined, () => current)
    current = false
    resolveCoverage({ status: 'missing', bar_count: 0, missing_slices: [{ start: '2026-10-01T00:00:00Z', end: '2026-10-20T00:00:00Z' }] })

    await expect(pending).resolves.toEqual({ kind: 'superseded' })
    expect(api.post).not.toHaveBeenCalled()
  })

  it('includes an optional selected canonical ID on explicit ETF preparation', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ outcome: 'acquired', refresh: true })
    await acquireETFHoldings('IGV', true, 82)
    expect(api.post).toHaveBeenCalledWith('/etf-holdings/IGV/acquire', {
      request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d', refresh: true, instrument_id: 82,
    })
  })
})
