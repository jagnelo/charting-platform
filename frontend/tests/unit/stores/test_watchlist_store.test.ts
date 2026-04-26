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

    await store.deleteWatchlist(2)
    expect(store.watchlists.some(w => w.id === 2)).toBe(false)
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
    await expect(store.addItem(1, 20)).resolves.toBeNull()

    await store.removeItem(1, 2)
    expect(store.watchlists[0].items).toHaveLength(1)
  })

  it('resolves symbols before adding by symbol and triggers an eager price fetch', async () => {
    const store = useWatchlistStore()
    store.watchlists = [{ ...makeWatchlist(), items: [] }] as any

    ;(api.get as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ id: 33 })
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
})
