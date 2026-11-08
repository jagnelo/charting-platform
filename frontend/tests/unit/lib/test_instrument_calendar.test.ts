import { QueryClient } from '@tanstack/vue-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { promoteQueued } = vi.hoisted(() => ({ promoteQueued: vi.fn() }))
vi.mock('@/lib/api', () => ({ setQueuedApiRequestPriority: promoteQueued }))

import { fetchInstrumentCalendar } from '@/lib/workstation/instrumentCalendar'

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
})
