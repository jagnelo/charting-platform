import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/api', () => ({ api: { post: vi.fn() } }))
import { api } from '@/lib/api'
import {
  acquireETFHoldings,
  acquireInstrumentHistory,
  defaultHistoryRange,
  discoverInstruments,
  HISTORY_ACQUISITION_MAX_REQUESTED_BARS,
  HISTORY_RANGE_LIMIT_DAYS,
  HISTORY_TIMEFRAME_SECONDS,
  historyRangeFitsBarBudget,
  historyRangeIsAllowed,
  makeAcquisitionRequestId,
  requestedHistoryBarSlots,
  resolveDiscoveredInstrument,
  type InstrumentDiscoveryCandidate,
} from '@/lib/onDemandAcquisition'

const candidate: InstrumentDiscoveryCandidate = {
  symbol: 'OIH', name: 'Oil Services ETF', exchange: 'NYSE Arca', type: 'ETF',
  provider: 'free-source', instrument_id: null, identity_status: 'provider_candidate',
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.stubGlobal('crypto', { randomUUID: () => 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d' })
})

describe('explicit acquisition API contracts', () => {
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
    })
  })

  it('resolves a selected candidate without treating its nullable ID as canonical', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ request_id: 'r2', status: 'resolved', instrument: { instrument_id: 43, symbol: 'OIH', identity_status: 'verified' }, source_outcomes: [] })
    await resolveDiscoveredInstrument(candidate)
    expect(api.post).toHaveBeenCalledWith('/instruments/acquire', {
      symbol: 'OIH', provider_candidate: { provider: 'free-source', symbol: 'OIH', exchange: 'NYSE Arca' },
      request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d',
    })
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

  it('provides timeframe-sized recent presets and rejects future or over-limit ranges', () => {
    const now = new Date('2026-10-27T12:00:00.000Z')
    const daily = defaultHistoryRange('D1', now)
    const intraday = defaultHistoryRange('M5', now)
    expect(Date.parse(daily.end)).toBe(now.getTime())
    expect(Date.parse(daily.end) - Date.parse(daily.start)).toBe(180 * 24 * 60 * 60 * 1000)
    expect(Date.parse(intraday.end) - Date.parse(intraday.start)).toBe(6 * 24 * 60 * 60 * 1000)
    expect(historyRangeIsAllowed('D1', daily.start, daily.end, now)).toBe(true)
    expect(historyRangeIsAllowed('D1', '2025-10-01T00:00:00.000Z', daily.end, now)).toBe(false)
    expect(historyRangeIsAllowed('D1', daily.start, '2026-10-28T00:00:00.000Z', now)).toBe(false)
  })

  it('keeps every timeframe default below the Provider inclusive 2,000-slot budget', () => {
    const now = new Date('2026-10-27T12:00:00.000Z')
    const expectedSeconds = {
      M1: 60, M5: 300, M15: 900, M30: 1800, H1: 3600, H2: 7200,
      H4: 14400, H12: 43200, D1: 86400, W1: 604800, MN: 2592000,
    }
    expect(HISTORY_TIMEFRAME_SECONDS).toEqual(expectedSeconds)
    expect(HISTORY_RANGE_LIMIT_DAYS).toMatchObject({ M1: 1, M5: 6, M15: 20, W1: 700, MN: 700 })
    expect(HISTORY_ACQUISITION_MAX_REQUESTED_BARS).toBe(2000)

    for (const [timeframe, days] of Object.entries(HISTORY_RANGE_LIMIT_DAYS) as [keyof typeof expectedSeconds, number][]) {
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
})
