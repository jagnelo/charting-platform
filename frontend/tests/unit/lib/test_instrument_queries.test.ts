import { QueryClient } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet, promoteQueuedRequest } = vi.hoisted(() => ({ apiGet: vi.fn(), promoteQueuedRequest: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet }, setQueuedApiRequestPriority: promoteQueuedRequest }))

import { fetchCanonicalInstrument } from '@/lib/workstation/instrumentQueries'

describe('instrument query contract', () => {
  beforeEach(() => { apiGet.mockReset(); promoteQueuedRequest.mockReset() })

  it('deduplicates concurrent canonical instrument hydration and normalizes symbols', async () => {
    apiGet.mockResolvedValue({ id: 7, symbol: 'XLK' })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const [first, second] = await Promise.all([
      fetchCanonicalInstrument(queryClient, 'xlk'),
      fetchCanonicalInstrument(queryClient, 'XLK'),
    ])
    expect(first).toEqual(second)
    expect(apiGet).toHaveBeenCalledTimes(1)
    expect(apiGet).toHaveBeenCalledWith('/instruments/XLK', { canonical_only: true }, {
      priority: 'high', queueKey: 'instrument-lookup:XLK:canonical',
    })
  })

  it('promotes a shared canonical identity lookup when a visible user action joins it', async () => {
    apiGet.mockResolvedValue({ id: 7, symbol: 'RSP' })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    await fetchCanonicalInstrument(queryClient, 'rsp', { priority: 'high', foreground: true })

    expect(promoteQueuedRequest).toHaveBeenCalledWith('instrument-lookup:RSP:canonical', 'high', true)
    expect(apiGet).toHaveBeenCalledWith('/instruments/RSP', { canonical_only: true }, {
      priority: 'high', foreground: true, queueKey: 'instrument-lookup:RSP:canonical',
    })
  })

  it('refetches after the shared instrument cache is invalidated', async () => {
    apiGet.mockResolvedValueOnce({ id: 7, symbol: 'XLK' }).mockResolvedValueOnce({ id: 7, symbol: 'XLK', name: 'Technology' })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    await fetchCanonicalInstrument(queryClient, 'XLK')
    await queryClient.invalidateQueries({ queryKey: ['workstation', 'instrument'] })
    await fetchCanonicalInstrument(queryClient, 'XLK')
    expect(apiGet).toHaveBeenCalledTimes(2)
  })
})
