import { QueryClient } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchInstrumentCalendar } from '@/lib/workstation/instrumentCalendar'

describe('instrument calendar query sharing', () => {
  let queryClient: QueryClient | null = null

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
})
