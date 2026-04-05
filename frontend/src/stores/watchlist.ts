import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Watchlist, WatchlistItem } from '@/types'
import { api } from '@/lib/api'

export const useWatchlistStore = defineStore('watchlist', () => {
  const watchlists = ref<Watchlist[]>([])
  const loading = ref(false)
  const priceMap = ref<Record<string, { close: number; prevClose: number; pct: number }>>({})

  async function loadWatchlists() {
    loading.value = true
    try {
      watchlists.value = await api.get('/watchlists')
    } catch (e) {
      console.error('Failed to load watchlists', e)
    } finally {
      loading.value = false
    }
  }

  async function createWatchlist(name: string, description?: string): Promise<Watchlist | null> {
    try {
      const wl = await api.post<Watchlist>('/watchlists', { name, description })
      watchlists.value.push(wl)
      return wl
    } catch (e) {
      console.error('Failed to create watchlist', e)
      return null
    }
  }

  async function deleteWatchlist(id: number) {
    try {
      await api.delete(`/watchlists/${id}`)
      watchlists.value = watchlists.value.filter(w => w.id !== id)
    } catch (e) {
      console.error('Failed to delete watchlist', e)
    }
  }

  async function addItem(watchlistId: number, instrumentId: number): Promise<WatchlistItem | null> {
    try {
      const item = await api.post<WatchlistItem>(`/watchlists/${watchlistId}/items`, {
        instrument_id: instrumentId,
      })
      const wl = watchlists.value.find(w => w.id === watchlistId)
      if (wl) wl.items.push(item)
      return item
    } catch (e: any) {
      if (e?.status === 409) return null // already in watchlist — silently ignore
      console.error('Failed to add watchlist item', e)
      return null
    }
  }

  async function removeItem(watchlistId: number, itemId: number) {
    try {
      await api.delete(`/watchlists/${watchlistId}/items/${itemId}`)
      const wl = watchlists.value.find(w => w.id === watchlistId)
      if (wl) wl.items = wl.items.filter(i => i.id !== itemId)
    } catch (e) {
      console.error('Failed to remove watchlist item', e)
    }
  }

  /** Add an instrument to a watchlist by symbol — auto-resolves instrument_id via API. */
  async function addBySymbol(watchlistId: number, symbol: string): Promise<WatchlistItem | null> {
    try {
      const instr = await api.get<{ id: number }>(`/instruments/${symbol.toUpperCase()}`)
      return await addItem(watchlistId, instr.id)
    } catch (e) {
      console.error('Failed to resolve instrument for watchlist add', e)
      return null
    }
  }

  async function fetchPrices(symbols: string[]) {
    const toFetch = symbols.filter(s => s && !priceMap.value[s])
    if (!toFetch.length) return
    await Promise.allSettled(
      toFetch.map(async (symbol) => {
        try {
          const bars: Array<{ close: number }> = await api.get(`/ohlcv/${symbol}/D1`, { limit: 2 })
          if (bars.length >= 2) {
            const close = bars[bars.length - 1].close
            const prevClose = bars[bars.length - 2].close
            priceMap.value[symbol] = { close, prevClose, pct: (close - prevClose) / prevClose }
          } else if (bars.length === 1) {
            const close = bars[0].close
            priceMap.value[symbol] = { close, prevClose: close, pct: 0 }
          }
        } catch { /* no bars */ }
      })
    )
  }

  return {
    watchlists,
    loading,
    priceMap,
    loadWatchlists,
    createWatchlist,
    deleteWatchlist,
    addItem,
    removeItem,
    addBySymbol,
    fetchPrices,
  }
})
