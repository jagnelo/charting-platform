import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

import { api } from '@/lib/api'
import { useFavoritesStore } from '@/stores/favorites'

const favorite = {
  id: 4,
  instrument_id: 17,
  position: 0,
  added_at: '2026-10-16T05:00:00Z',
  symbol: 'NVDA',
  name: 'NVIDIA Corporation',
}

describe('useFavoritesStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
  })

  it('loads and sorts the persisted My Favorites list', async () => {
    const store = useFavoritesStore()
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      { ...favorite, id: 5, instrument_id: 18, position: 1 },
      favorite,
    ])

    await store.load()

    expect(store.favorites.map(item => item.instrument_id)).toEqual([17, 18])
    expect(store.isFavorite(17)).toBe(true)
    expect(api.get).toHaveBeenCalledWith('/favorites')
  })

  it('adds idempotently and removes only the requested instrument', async () => {
    const store = useFavoritesStore()
    ;(api.put as ReturnType<typeof vi.fn>).mockResolvedValueOnce(favorite)
    ;(api.delete as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined)

    await expect(store.add(17)).resolves.toEqual(favorite)
    await expect(store.add(17)).resolves.toEqual(favorite)
    expect(api.put).toHaveBeenCalledTimes(1)
    await expect(store.remove(17)).resolves.toBe(true)
    expect(store.favorites).toEqual([])
    expect(api.delete).toHaveBeenCalledWith('/favorites/instruments/17')
  })

  it('does not issue requests for invalid instrument identities', async () => {
    const store = useFavoritesStore()
    await expect(store.add(0)).resolves.toBeNull()
    await expect(store.remove(-1)).resolves.toBe(false)
    expect(api.put).not.toHaveBeenCalled()
    expect(api.delete).not.toHaveBeenCalled()
  })
})
