import { QueryClient } from '@tanstack/vue-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { promoteQueued } = vi.hoisted(() => ({ promoteQueued: vi.fn() }))
vi.mock('@/lib/api', () => ({ setQueuedApiRequestPriority: promoteQueued }))

import {
  fetchInstrumentCalendar,
  instrumentCalendarStatusQueryKey,
  instrumentCalendarStatusRefetchInterval,
  invalidateInstrumentCalendar,
  isCurrentInstrumentCalendarContext,
  shouldRefreshInstrumentCalendar,
  type InstrumentCalendarStatus,
} from '@/lib/workstation/instrumentCalendar'

const calendarStatus = (overrides: Partial<InstrumentCalendarStatus> = {}): InstrumentCalendarStatus => ({
  version: 1,
  status: 'queued',
  has_pending_work: true,
  retry_at: null,
  reason_code: null,
  updated_at: '2026-11-08T10:00:00Z',
  ...overrides,
})

describe('instrument calendar query sharing', () => {
  let queryClient: QueryClient | null = null

  beforeEach(() => promoteQueued.mockReset())

  afterEach(() => {
    queryClient?.clear()
    queryClient = null
  })

  it('deduplicates an in-flight exact range and reuses its short-lived result', async () => {
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 300_000 } } })
    let resolve!: (value: string[]) => void
    const load = vi.fn(() => new Promise<string[]>(done => { resolve = done }))

    const first = fetchInstrumentCalendar(queryClient, 'spy', '2024-01-01T00:00:00Z', '2026-11-07T00:00:00Z', load)
    const second = fetchInstrumentCalendar(queryClient, 'SPY', '2024-01-01T00:00:00Z', '2026-11-07T00:00:00Z', load)
    expect(load).toHaveBeenCalledTimes(1)
    resolve(['event'])
    await expect(Promise.all([first, second])).resolves.toEqual([['event'], ['event']])

    await expect(fetchInstrumentCalendar(
      queryClient, 'SPY', '2024-01-01T00:00:00Z', '2026-11-07T00:00:00Z', load,
    )).resolves.toEqual(['event'])
    expect(load).toHaveBeenCalledTimes(1)
  })

  it('keeps different symbols and ranges isolated', async () => {
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const load = vi.fn(async () => ['event'])

    await fetchInstrumentCalendar(queryClient, 'SPY', 'start-a', 'end-a', load)
    await fetchInstrumentCalendar(queryClient, 'QQQ', 'start-a', 'end-a', load)
    await fetchInstrumentCalendar(queryClient, 'SPY', 'start-b', 'end-a', load)

    expect(load).toHaveBeenCalledTimes(3)
  })

  it('promotes an in-flight hidden-chart calendar read when its chart becomes visible without duplicating the GET', async () => {
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 300_000 } } })
    let resolve!: (value: string[]) => void
    const load = vi.fn(() => new Promise<string[]>(done => { resolve = done }))
    const queueKey = 'chart-calendar:SPY:2024-01-01:2026-11-07'

    const hiddenRead = fetchInstrumentCalendar(
      queryClient, 'SPY', '2024-01-01', '2026-11-07', load,
      { priority: 'auto', queueKey },
    )
    const visibleJoin = fetchInstrumentCalendar(
      queryClient, 'SPY', '2024-01-01', '2026-11-07', load,
      { priority: 'high', queueKey },
    )

    expect(promoteQueued).toHaveBeenCalledWith(queueKey, 'high')
    expect(load).toHaveBeenCalledOnce()
    resolve(['event'])
    await expect(Promise.all([hiddenRead, visibleJoin])).resolves.toEqual([['event'], ['event']])
  })

  it('invalidates only the exact range and displays newer calendar rows on a forced refresh', async () => {
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 300_000 } } })
    const load = vi.fn()
      .mockResolvedValueOnce(['cached event'])
      .mockResolvedValueOnce(['cached event', 'new event'])
    const range = { symbol: 'SPY', start: '2026-11-01', end: '2026-12-01' }

    await expect(fetchInstrumentCalendar(queryClient, range.symbol, range.start, range.end, load))
      .resolves.toEqual(['cached event'])
    await fetchInstrumentCalendar(queryClient, range.symbol, '2026-10-01', range.end, async () => ['other range'])
    await invalidateInstrumentCalendar(queryClient, range.symbol, range.start, range.end)
    await expect(fetchInstrumentCalendar(
      queryClient, range.symbol, range.start, range.end, load,
      { priority: 'high', queueKey: 'chart-calendar:SPY:range', refresh: true },
    )).resolves.toEqual(['cached event', 'new event'])

    expect(load).toHaveBeenCalledTimes(2)
    expect(queryClient.getQueryData(['workstation', 'instrument-calendar', 'SPY', '2026-10-01', range.end]))
      .toEqual(['other range'])
  })

  it('refreshes on a real queued-to-ready completion or newer ready progress, not unchanged or stale status', () => {
    const queued = calendarStatus()
    expect(shouldRefreshInstrumentCalendar(queued, calendarStatus({
      status: 'ready', has_pending_work: false,
    }))).toBe(true)
    expect(shouldRefreshInstrumentCalendar(calendarStatus({
      status: 'ready', has_pending_work: false,
    }), calendarStatus({
      status: 'ready', has_pending_work: false, updated_at: '2026-11-08T10:00:01Z',
    }))).toBe(true)
    expect(shouldRefreshInstrumentCalendar(calendarStatus({
      status: 'ready', has_pending_work: false,
    }), calendarStatus({
      status: 'ready', has_pending_work: false,
    }))).toBe(false)
    expect(shouldRefreshInstrumentCalendar(calendarStatus({
      status: 'ready', has_pending_work: false, updated_at: '2026-11-08T10:00:02Z',
    }), calendarStatus({
      status: 'partial', has_pending_work: false, updated_at: '2026-11-08T10:00:01Z',
    }))).toBe(false)
    expect(shouldRefreshInstrumentCalendar(null, calendarStatus({
      status: 'ready', has_pending_work: false, updated_at: null,
    }))).toBe(false)
  })

  it('scopes status cache and stale-response acceptance to symbol and authenticated session', () => {
    expect(instrumentCalendarStatusQueryKey('spy', 4)).toEqual(instrumentCalendarStatusQueryKey('SPY', 4))
    expect(instrumentCalendarStatusQueryKey('SPY', 4)).not.toEqual(instrumentCalendarStatusQueryKey('SPY', 5))
    expect(instrumentCalendarStatusQueryKey('SPY', 4, 2)).not.toEqual(instrumentCalendarStatusQueryKey('SPY', 4, 3))
    expect(isCurrentInstrumentCalendarContext('SPY', 'spy', 4, 4)).toBe(true)
    expect(isCurrentInstrumentCalendarContext('SPY', 'SPY', 4, 4, 2, 2)).toBe(true)
    expect(isCurrentInstrumentCalendarContext('SPY', 'SPY', 4, 4, 2, 3)).toBe(false)
    expect(isCurrentInstrumentCalendarContext('SPY', 'QQQ', 4, 4)).toBe(false)
    expect(isCurrentInstrumentCalendarContext('SPY', 'SPY', 4, 5)).toBe(false)
  })

  it('uses provider retry_at for deferred work and pauses its background poll when complete', () => {
    const now = Date.parse('2026-11-08T10:00:00Z')
    expect(instrumentCalendarStatusRefetchInterval(calendarStatus({
      status: 'deferred', retry_at: '2026-11-08T10:00:30Z', has_pending_work: true,
    }), now)).toBe(30_000)
    expect(instrumentCalendarStatusRefetchInterval(calendarStatus({ retry_at: null }), now)).toBe(2_000)
    expect(instrumentCalendarStatusRefetchInterval(calendarStatus({
      status: 'ready', has_pending_work: false,
    }), now)).toBe(15_000)
  })
})
