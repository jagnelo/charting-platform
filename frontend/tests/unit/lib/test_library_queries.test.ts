import { QueryClient } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

const apiGet = vi.hoisted(() => vi.fn())
vi.mock('@/lib/api', () => ({ api: { get: apiGet } }))

import { fetchCodeAssets, invalidateCodeAssets } from '@/lib/workstation/libraryQueries'

describe('workstation library queries', () => {
  afterEach(() => apiGet.mockReset())

  it('deduplicates concurrent code-asset hydration and refetches after invalidation', async () => {
    apiGet.mockResolvedValue([{ kind: 'plot', name: 'Breadth', versions: [{ id: 11, version_number: 1 }] }])
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })

    const [first, second] = await Promise.all([fetchCodeAssets(queryClient), fetchCodeAssets(queryClient)])
    expect(first).toEqual(second)
    expect(apiGet).toHaveBeenCalledTimes(1)

    await invalidateCodeAssets(queryClient)
    await fetchCodeAssets(queryClient)
    expect(apiGet).toHaveBeenCalledTimes(2)
  })
})
