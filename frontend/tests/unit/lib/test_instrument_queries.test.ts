import { QueryClient } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('@/lib/api', () => ({ api: { get: apiGet } }))

import { fetchCanonicalInstrument } from '@/lib/workstation/instrumentQueries'

describe('instrument query contract', () => {
  beforeEach(() => apiGet.mockReset())

  it('deduplicates concurrent canonical instrument hydration and normalizes symbols', async () => {
    apiGet.mockResolvedValue({ id: 7, symbol: 'XLK' })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const [first, second] = await Promise.all([
      fetchCanonicalInstrument(queryClient, 'xlk'),
      fetchCanonicalInstrument(queryClient, 'XLK'),
    ])
    expect(first).toEqual(second)
    expect(apiGet).toHaveBeenCalledTimes(1)
    expect(apiGet).toHaveBeenCalledWith('/instruments/XLK', { canonical_only: true })
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
