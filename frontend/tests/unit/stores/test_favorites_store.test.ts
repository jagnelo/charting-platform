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
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([favorite])
    ;(api.put as ReturnType<typeof vi.fn>).mockResolvedValueOnce(favorite)
    ;(api.delete as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined)

    await expect(store.add(17)).resolves.toEqual(favorite)
    await expect(store.add(17)).resolves.toEqual(favorite)
    expect(api.put).toHaveBeenCalledTimes(1)
    await expect(store.remove(17)).resolves.toBe(true)
    expect(store.favorites).toEqual([])
    expect(api.delete).toHaveBeenCalledWith('/favorites/instruments/17')
  })

  it('does not let a stale in-flight load erase a successful favorite addition', async () => {
    let resolveLoad!: (rows: typeof favorite[]) => void
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementationOnce(() => new Promise(resolve => {
      resolveLoad = resolve
    })).mockResolvedValueOnce([favorite])
    ;(api.put as ReturnType<typeof vi.fn>).mockResolvedValueOnce(favorite)

    const store = useFavoritesStore()
    const load = store.load()
    expect(store.loading).toBe(true)

    await expect(store.add(17)).resolves.toEqual(favorite)
    resolveLoad([])
    await load

    expect(store.favorites).toEqual([favorite])
    expect(store.isFavorite(17)).toBe(true)
    expect(store.loaded).toBe(true)
    expect(store.loading).toBe(false)
  })

  it('reloads the complete list when an add wins an incomplete initial load', async () => {
    const otherFavorite = { ...favorite, id: 5, instrument_id: 18, position: 1, symbol: 'MSFT' }
    let resolveInitialLoad!: (rows: typeof favorite[]) => void
    ;(api.get as ReturnType<typeof vi.fn>)
      .mockImplementationOnce(() => new Promise(resolve => { resolveInitialLoad = resolve }))
      .mockResolvedValueOnce([favorite, otherFavorite])
    ;(api.put as ReturnType<typeof vi.fn>).mockResolvedValueOnce(favorite)

    const store = useFavoritesStore()
    const initialLoad = store.load()
    await expect(store.add(17)).resolves.toEqual(favorite)
    resolveInitialLoad([otherFavorite])
    await initialLoad

    await vi.waitFor(() => expect(store.favorites.map(item => item.instrument_id)).toEqual([17, 18]))
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(store.loaded).toBe(true)
    expect(store.loading).toBe(false)
  })

  it('reloads the complete list after a failed initial load and a successful add', async () => {
    const otherFavorite = { ...favorite, id: 5, instrument_id: 18, position: 1, symbol: 'MSFT' }
    ;(api.get as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(new Error('initial list unavailable'))
      .mockResolvedValueOnce([favorite, otherFavorite])
    ;(api.put as ReturnType<typeof vi.fn>).mockResolvedValueOnce(favorite)

    const store = useFavoritesStore()
    await store.load()
    expect(store.loaded).toBe(false)
    expect(store.error).toBe('initial list unavailable')

    await expect(store.add(17)).resolves.toEqual(favorite)
    await vi.waitFor(() => expect(store.favorites.map(item => item.instrument_id)).toEqual([17, 18]))
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(store.loaded).toBe(true)
    expect(store.loading).toBe(false)
  })

  it('does not let a stale in-flight load restore a successfully removed favorite', async () => {
    const otherFavorite = { ...favorite, id: 5, instrument_id: 18, position: 1, symbol: 'MSFT' }
    let resolveLoad!: (rows: typeof favorite[]) => void
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementationOnce(() => new Promise(resolve => {
      resolveLoad = resolve
    })).mockResolvedValueOnce([otherFavorite])
    ;(api.delete as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined)

    const store = useFavoritesStore()
    const load = store.load()
    await expect(store.remove(17)).resolves.toBe(true)
    resolveLoad([favorite, otherFavorite])
    await load

    expect(store.favorites).toEqual([otherFavorite])
    expect(store.isFavorite(17)).toBe(false)
    expect(store.isFavorite(18)).toBe(true)
    expect(store.loaded).toBe(true)
    expect(store.loading).toBe(false)
  })

  it('does not surface a stale load error after a favorite mutation succeeds', async () => {
    let rejectLoad!: (cause: Error) => void
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementationOnce(() => new Promise((_resolve, reject) => {
      rejectLoad = reject
    })).mockResolvedValueOnce([favorite])
    ;(api.put as ReturnType<typeof vi.fn>).mockResolvedValueOnce(favorite)

    const store = useFavoritesStore()
    const load = store.load()
    await expect(store.add(17)).resolves.toEqual(favorite)
    rejectLoad(new Error('stale load failed'))
    await load

    expect(store.error).toBe('')
    expect(store.favorites).toEqual([favorite])
    expect(store.loaded).toBe(true)
    expect(store.loading).toBe(false)
  })

  it('does not issue requests for invalid instrument identities', async () => {
    const store = useFavoritesStore()
    await expect(store.add(0)).resolves.toBeNull()
    await expect(store.remove(-1)).resolves.toBe(false)
    expect(api.put).not.toHaveBeenCalled()
    expect(api.delete).not.toHaveBeenCalled()
  })
})
