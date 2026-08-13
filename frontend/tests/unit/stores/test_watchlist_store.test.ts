import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

import { api } from '@/lib/api'
import { useWatchlistStore } from '@/stores/watchlist'

function makeWatchlist() {
  return {
    id: 1,
    name: 'Momentum',
    is_default: false,
    is_managed: false,
    is_locked: false,
    position: 0,
    items: [{ id: 1, instrument_id: 10, symbol: 'NVDA', position: 0 }],
  }
}

describe('useWatchlistStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
    vi.useFakeTimers()
  })

  it('loads, creates, deletes, and renames watchlists', async () => {
    const store = useWatchlistStore()
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([makeWatchlist()])
    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ ...makeWatchlist(), id: 2, name: 'Growth', items: [] })
    ;(api.patch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ ...makeWatchlist(), name: 'Renamed' })
    ;(api.delete as ReturnType<typeof vi.fn>).mockResolvedValue(undefined)

    await store.loadWatchlists()
    expect(store.watchlists).toHaveLength(1)

    await store.createWatchlist('Growth')
    expect(store.watchlists.map(w => w.name)).toContain('Growth')

    await store.renameWatchlist(1, 'Renamed')
    expect(store.watchlists.find(w => w.id === 1)?.name).toBe('Renamed')

    await expect(store.deleteWatchlist(2)).resolves.toBe(true)
    expect(store.watchlists.some(w => w.id === 2)).toBe(false)
  })

  it('retains a load error without clearing existing watchlists', async () => {
    const store = useWatchlistStore()
    store.watchlists = [makeWatchlist()] as any
    ;(api.get as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('API GET /watchlists → 503'))

    await store.loadWatchlists()

    expect(store.loadError).toContain('503')
    expect(store.watchlists).toHaveLength(1)
    expect(store.loading).toBe(false)
  })

  it('treats a duplicate-name create race as an idempotent create', async () => {
    const store = useWatchlistStore()
    const existing = { ...makeWatchlist(), id: 7, name: 'Shared list' }
    ;(api.post as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("API POST /watchlists → 409: already exists"))
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([existing])

    await expect(store.createWatchlist('Shared list')).resolves.toMatchObject({ id: 7, name: 'Shared list' })
    expect(store.watchlists).toContainEqual(existing)
  })

  it('deduplicates concurrent creates for the same watchlist name', async () => {
    const store = useWatchlistStore()
    const created = { ...makeWatchlist(), id: 8, name: 'Concurrent list' }
    let resolveCreate!: (value: typeof created) => void
    ;(api.post as ReturnType<typeof vi.fn>).mockReturnValueOnce(new Promise(resolve => { resolveCreate = resolve }))

    const first = store.createWatchlist('Concurrent list')
    const second = store.createWatchlist('Concurrent list')
    resolveCreate(created)

    await expect(Promise.all([first, second])).resolves.toEqual([created, created])
    expect(api.post).toHaveBeenCalledTimes(1)
  })

  it('deduplicates creates across separate Pinia store instances during virtual-root activation', async () => {
    const firstPinia = createPinia()
    setActivePinia(firstPinia)
    const firstStore = useWatchlistStore()
    const secondPinia = createPinia()
    setActivePinia(secondPinia)
    const secondStore = useWatchlistStore()
    const created = { ...makeWatchlist(), id: 9, name: 'Cross-root list' }
    let resolveCreate!: (value: typeof created) => void
    ;(api.post as ReturnType<typeof vi.fn>).mockReturnValueOnce(new Promise(resolve => { resolveCreate = resolve }))

    const first = firstStore.createWatchlist('Cross-root list')
    const second = secondStore.createWatchlist('Cross-root list')
    resolveCreate(created)

    await expect(Promise.all([first, second])).resolves.toEqual([created, created])
    expect(api.post).toHaveBeenCalledTimes(1)
  })

  it('adds items, ignores conflicts, and removes items', async () => {
    const store = useWatchlistStore()
    store.watchlists = [makeWatchlist()] as any
    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ id: 2, instrument_id: 20, symbol: 'AAPL', position: 1 })
    ;(api.delete as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined)

    const created = await store.addItem(1, 20)
    expect(created?.symbol).toBe('AAPL')
    expect(store.watchlists[0].items).toHaveLength(2)

    ;(api.post as ReturnType<typeof vi.fn>).mockRejectedValueOnce({ status: 409 })
    await expect(store.addItem(1, 20)).resolves.toMatchObject({ instrument_id: 20, symbol: 'AAPL' })

    await store.removeItem(1, 2)
    expect(store.watchlists[0].items).toHaveLength(1)
  })

  it('uses one atomic transfer request and updates both local memberships', async () => {
    const store = useWatchlistStore()
    store.watchlists = [
      makeWatchlist(),
      { ...makeWatchlist(), id: 2, name: 'Destination', items: [] },
    ] as any
    const transferred = { id: 9, instrument_id: 10, symbol: 'NVDA', position: 0 }
    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce(transferred)

    await expect(store.transferItem(1, 1, 2, 'move')).resolves.toEqual(transferred)
    expect(api.post).toHaveBeenCalledWith('/watchlists/2/items/transfer', {
      source_watchlist_id: 1,
      item_id: 1,
      mode: 'move',
    })
    expect(store.watchlists[0].items).toHaveLength(0)
    expect(store.watchlists[1].items).toEqual([transferred])
  })

  it('deduplicates concurrent item adds across separate Pinia store instances', async () => {
    const firstPinia = createPinia()
    setActivePinia(firstPinia)
    const firstStore = useWatchlistStore()
    const secondPinia = createPinia()
    setActivePinia(secondPinia)
    const secondStore = useWatchlistStore()
    const firstList = { ...makeWatchlist(), items: [] }
    firstStore.watchlists = [firstList] as any
    secondStore.watchlists = [{ ...firstList }] as any
    const created = { id: 22, instrument_id: 20, symbol: 'AAPL', position: 0 }
    let resolveAdd!: (value: typeof created) => void
    ;(api.post as ReturnType<typeof vi.fn>).mockReturnValueOnce(new Promise(resolve => { resolveAdd = resolve }))

    const first = firstStore.addItem(1, 20)
    const second = secondStore.addItem(1, 20)
    resolveAdd(created)

    await expect(Promise.all([first, second])).resolves.toEqual([created, created])
    expect(api.post).toHaveBeenCalledTimes(1)
  })

  it('persists an item flag and updates the local canonical row', async () => {
    const store = useWatchlistStore()
    store.watchlists = [makeWatchlist()] as any
    ;(api.patch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ id: 1, instrument_id: 10, flagged: true })

    await expect(store.setItemFlag(1, 1, true)).resolves.toBe(true)
    expect(api.patch).toHaveBeenCalledWith('/watchlists/1/items/1', { flagged: true })
    expect(store.watchlists[0].items[0].flagged).toBe(true)
  })

  it('resolves symbols before adding by symbol and triggers an eager price fetch', async () => {
    const store = useWatchlistStore()
    store.watchlists = [makeWatchlist()] as any

    ;(api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ id: 33, symbol: 'MSFT' })
      .mockResolvedValueOnce({ id: 33, symbol: 'MSFT' })
      .mockResolvedValueOnce([
        { open: 100, high: 104, low: 98, close: 103, volume: 250 },
        { open: 103, high: 108, low: 101, close: 107, volume: 300 },
      ])
    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ id: 2, instrument_id: 33, symbol: 'MSFT', position: 0 })

    const item = await store.addBySymbol(1, 'msft')
    await vi.runAllTimersAsync()

    expect(item?.symbol).toBe('MSFT')
    expect(store.priceMap.MSFT.close).toBe(107)
  })

  it('locks, unlocks, seeds, copies, reorders, and focuses watchlists', async () => {
    const store = useWatchlistStore()
    store.watchlists = [
      makeWatchlist(),
      { ...makeWatchlist(), id: 2, name: 'Second', position: 1, items: [] },
    ] as any

    ;(api.post as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce({ ...makeWatchlist(), id: 1, items: [{ id: 5, instrument_id: 99, symbol: 'TSLA', position: 0 }] })
      .mockResolvedValueOnce({ ...makeWatchlist(), id: 3, name: 'Copy', items: [] })
      .mockResolvedValueOnce(undefined)

    await store.lockWatchlist(1)
    expect(store.watchlists[0].is_locked).toBe(true)

    await store.unlockWatchlist(1)
    expect(store.watchlists[0].is_locked).toBe(false)

    await store.seedWatchlist(1, [99])
    expect(store.watchlists[0].items[0].symbol).toBe('TSLA')

    await store.copyWatchlist(1)
    expect(store.watchlists.some(w => w.id === 3)).toBe(true)

    await store.reorderWatchlists([2, 1])
    expect(store.watchlists.map(w => w.id).slice(0, 2)).toEqual([2, 1])

    store.requestFocusWatchlist(2)
    expect(store.focusRequest).toBe(2)
    store.clearFocusRequest()
    expect(store.focusRequest).toBeNull()
  })

  it('optimistically reorders personal watchlist items and restores on failure', async () => {
    const store = useWatchlistStore()
    store.watchlists = [{ ...makeWatchlist(), items: [
      { id: 1, instrument_id: 10, symbol: 'NVDA', position: 0 },
      { id: 2, instrument_id: 20, symbol: 'AAPL', position: 1 },
    ] }] as any

    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce(undefined)
    await store.reorderItems(1, [2, 1])
    expect(store.watchlists[0].items.map(item => item.id)).toEqual([2, 1])
    expect(api.post).toHaveBeenCalledWith('/watchlists/1/items/reorder', { ids: [2, 1] })

    ;(api.post as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('conflict'))
    await store.reorderItems(1, [1, 2])
    expect(store.watchlists[0].items.map(item => item.id)).toEqual([2, 1])
  })

  it('reloads canonical lists when another workstation window broadcasts a mutation', async () => {
    const originalChannel = (globalThis as typeof globalThis & { BroadcastChannel?: unknown }).BroadcastChannel
    const channels: Array<{ onmessage: ((event: MessageEvent<{ type: string }>) => void) | null }> = []
    class FakeBroadcastChannel {
      onmessage: ((event: MessageEvent<{ type: string }>) => void) | null = null
      constructor() { channels.push(this) }
      postMessage = vi.fn()
    }
    Object.defineProperty(globalThis, 'BroadcastChannel', { configurable: true, value: FakeBroadcastChannel })
    try {
      const store = useWatchlistStore()
      ;(api.get as ReturnType<typeof vi.fn>)
        .mockResolvedValueOnce([makeWatchlist()])
        .mockResolvedValueOnce([{ ...makeWatchlist(), name: 'Reloaded' }])
      await store.loadWatchlists()
      channels[0]?.onmessage?.({ data: { type: 'watchlists-changed' } } as MessageEvent<{ type: string }>)
      await vi.waitFor(() => expect(store.watchlists[0]?.name).toBe('Reloaded'))
      expect(api.get).toHaveBeenLastCalledWith('/watchlists')
    } finally {
      if (originalChannel === undefined) delete (globalThis as typeof globalThis & { BroadcastChannel?: unknown }).BroadcastChannel
      else Object.defineProperty(globalThis, 'BroadcastChannel', { configurable: true, value: originalChannel })
    }
  })

  it('does not let an in-flight invalidation reload erase a local membership mutation', async () => {
    const store = useWatchlistStore()
    store.watchlists = [makeWatchlist()] as any
    let resolveReload!: (value: unknown) => void
    ;(api.get as ReturnType<typeof vi.fn>).mockReturnValueOnce(new Promise(resolve => { resolveReload = resolve }))
    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ id: 2, instrument_id: 20, symbol: 'AAPL', position: 0 })

    const reload = store.loadWatchlists()
    await store.addItem(1, 20)
    resolveReload([{ ...makeWatchlist(), items: [] }])
    await reload

    expect(store.watchlists[0].items.map(item => item.symbol)).toEqual(['NVDA', 'AAPL'])
  })

  it('reconciles a post-mutation stale reload without dropping the local item', async () => {
    const store = useWatchlistStore()
    store.watchlists = [{ ...makeWatchlist(), items: [] }] as any
    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ id: 2, instrument_id: 20, symbol: 'AAPL', position: 0 })
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([{ ...makeWatchlist(), items: [] }])

    await store.addItem(1, 20)
    await store.loadWatchlists()

    expect(store.watchlists[0].items.map(item => item.symbol)).toEqual(['AAPL'])
  })

  it('keeps the last watchlists visible when a refresh fails transiently', async () => {
    const store = useWatchlistStore()
    store.watchlists = [makeWatchlist()] as any
    ;(api.get as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('Failed to fetch'))

    await store.loadWatchlists()

    expect(store.watchlists).toHaveLength(1)
    expect(store.watchlists[0]?.items[0]?.symbol).toBe('NVDA')
  })

  it('falls back to storage events when BroadcastChannel is unavailable', async () => {
    const originalChannel = (globalThis as typeof globalThis & { BroadcastChannel?: unknown }).BroadcastChannel
    delete (globalThis as typeof globalThis & { BroadcastChannel?: unknown }).BroadcastChannel
    try {
      const store = useWatchlistStore()
      ;(api.get as ReturnType<typeof vi.fn>)
        .mockResolvedValueOnce([makeWatchlist()])
        .mockResolvedValueOnce([{ ...makeWatchlist(), name: 'Storage reload' }])
      await store.loadWatchlists()
      window.dispatchEvent(new StorageEvent('storage', {
        key: 'charting-platform-watchlists-event',
        newValue: JSON.stringify({ type: 'watchlists-changed', watchlistId: 1 }),
      }))
      await vi.waitFor(() => expect(store.watchlists[0]?.name).toBe('Storage reload'))
    } finally {
      if (originalChannel !== undefined) Object.defineProperty(globalThis, 'BroadcastChannel', { configurable: true, value: originalChannel })
    }
  })

  it('reports destructive delete failures without changing local list state', async () => {
    const store = useWatchlistStore()
    store.watchlists = [makeWatchlist()] as any
    ;(api.delete as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error('conflict'))
    await expect(store.deleteWatchlist(1)).resolves.toBe(false)
    expect(store.watchlists).toHaveLength(1)
  })

  it('computes quotes, price flashes, and single-bar fallbacks', async () => {
    const store = useWatchlistStore()
    store.priceMap.NVDA = {
      close: 100,
      prevClose: 98,
      pct: 0.0204,
      updatedAt: Date.now(),
    }

    ;(api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce([
        { open: 100, high: 110, low: 90, close: 105, volume: 200 },
        { open: 106, high: 112, low: 95, close: 110, volume: 300 },
      ])
      .mockResolvedValueOnce([
        { open: 50, high: 55, low: 48, close: 54, volume: 80 },
      ])

    await store.fetchPrices(['nvda'], true)
    expect(store.priceMap.NVDA.close).toBe(110)
    expect(store.flashMap.NVDA).toBe('up')

    vi.advanceTimersByTime(900)
    expect(store.flashMap.NVDA).toBeNull()

    await store.fetchPrices(['aapl'], true)
    expect(store.priceMap.AAPL.prevClose).toBe(54)
    expect(store.priceMap.AAPL.pct).toBe(0)
  })

  it('supports local-only price hydration for workstation watchlists', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      { open: 10, high: 11, low: 9, close: 10, volume: 100 },
      { open: 10, high: 12, low: 9, close: 11, volume: 120 },
    ])
    const store = useWatchlistStore()
    await store.fetchPrices(['spy'], false, true)
    expect(api.get).toHaveBeenCalledWith('/ohlcv/local/SPY/D1', { limit: 31 })
    expect(store.priceMap.SPY.close).toBe(11)
  })

  it('propagates local-only mode when adding a workstation watchlist symbol', async () => {
    ;(api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ id: 7, symbol: 'SPY' })
      .mockResolvedValueOnce({ id: 7, symbol: 'SPY' })
      .mockResolvedValueOnce([
        { open: 10, high: 11, low: 9, close: 10, volume: 100 },
        { open: 10, high: 12, low: 9, close: 11, volume: 120 },
      ])
    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ id: 99, symbol: 'SPY' })
    const store = useWatchlistStore()
    await store.addBySymbol(42, 'spy', true)
    expect(api.get).toHaveBeenCalledWith('/ohlcv/local/SPY/D1', { limit: 31 })
    expect(api.get).not.toHaveBeenCalledWith('/ohlcv/SPY/D1', { limit: 31 })
  })
})
