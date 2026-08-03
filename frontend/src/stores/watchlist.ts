import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Watchlist, WatchlistItem } from '@/types'
import { api } from '@/lib/api'
import { ensureKnownInstrumentSymbol } from '@/lib/instruments'

export interface WatchlistQuote {
  close: number
  prevClose: number
  pct: number
  open?: number
  dayHigh?: number
  dayLow?: number
  volume?: number
  avgVolume?: number
  updatedAt: number
}

export const useWatchlistStore = defineStore('watchlist', () => {
  const watchlists = ref<Watchlist[]>([])
  const loading = ref(false)
  const priceMap = ref<Record<string, WatchlistQuote>>({})
  const flashMap = ref<Record<string, 'up' | 'down' | null>>({})
  /** When set, WatchlistPanel should open, collapse all others, and expand this watchlist. */
  const focusRequest = ref<number | null>(null)
  const watchlistChannel = typeof BroadcastChannel !== 'undefined'
    ? new BroadcastChannel('charting-platform-watchlists')
    : null
  const WATCHLIST_STORAGE_KEY = 'charting-platform-watchlists-event'

  function announceChanged(watchlistId?: number) {
    const message = { type: 'watchlists-changed', watchlistId: watchlistId ?? null }
    if (watchlistChannel) watchlistChannel.postMessage(message)
    else if (typeof window !== 'undefined') {
      try { window.localStorage.setItem(WATCHLIST_STORAGE_KEY, JSON.stringify({ ...message, nonce: Date.now() })) } catch { /* storage may be unavailable */ }
    }
  }

  function handleInvalidation(event: { data?: { type?: string } }) {
    if (event.data?.type === 'watchlists-changed') void loadWatchlists()
  }

  if (watchlistChannel) {
    watchlistChannel.onmessage = handleInvalidation
  } else if (typeof window !== 'undefined') {
    window.addEventListener('storage', event => {
      if (event.key !== WATCHLIST_STORAGE_KEY || !event.newValue) return
      try { handleInvalidation({ data: JSON.parse(event.newValue) }) } catch { /* ignore malformed fallback events */ }
    })
  }

  function isTransientLoadError(error: unknown): boolean {
    const message = error instanceof Error ? error.message : String(error ?? '')
    return /Failed to fetch|ERR_ABORTED|Authentication required/i.test(message)
  }

  async function loadWatchlists() {
    loading.value = true
    try {
      watchlists.value = await api.get('/watchlists')
    } catch (e) {
      if (isTransientLoadError(e)) {
        watchlists.value = []
        return
      }
      console.error('Failed to load watchlists', e)
    } finally {
      loading.value = false
    }
  }

  async function createWatchlist(name: string, description?: string, screener_id?: number): Promise<Watchlist | null> {
    try {
      const body: Record<string, unknown> = { name, description }
      if (screener_id != null) body.screener_id = screener_id
      const wl = await api.post<Watchlist>('/watchlists', body)
      watchlists.value.push(wl)
      announceChanged(wl.id)
      return wl
    } catch (e) {
      console.error('Failed to create watchlist', e)
      return null
    }
  }

  async function deleteWatchlist(id: number): Promise<boolean> {
    try {
      await api.delete(`/watchlists/${id}`)
      watchlists.value = watchlists.value.filter(w => w.id !== id)
      announceChanged(id)
      return true
    } catch (e) {
      console.error('Failed to delete watchlist', e)
      return false
    }
  }

  async function addItem(watchlistId: number, instrumentId: number): Promise<WatchlistItem | null> {
    try {
      const item = await api.post<WatchlistItem>(`/watchlists/${watchlistId}/items`, {
        instrument_id: instrumentId,
      })
      const wl = watchlists.value.find(w => w.id === watchlistId)
      if (wl) wl.items.push(item)
      announceChanged(watchlistId)
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
      announceChanged(watchlistId)
    } catch (e) {
      console.error('Failed to remove watchlist item', e)
    }
  }

  async function reorderItems(watchlistId: number, ids: number[]) {
    const wl = watchlists.value.find(item => item.id === watchlistId)
    if (!wl) return
    const original = [...wl.items]
    const byId = Object.fromEntries(original.map(item => [item.id, item]))
    const reordered = ids.map(id => byId[id]).filter(Boolean)
    wl.items = [...reordered, ...original.filter(item => !ids.includes(item.id))]
      .map((item, position) => ({ ...item, position }))
    try {
      await api.post(`/watchlists/${watchlistId}/items/reorder`, { ids })
      announceChanged(watchlistId)
    } catch (error) {
      wl.items = original
      console.error('Failed to reorder watchlist items', error)
    }
  }

  /** Add an instrument to a watchlist by symbol — auto-resolves instrument_id via API. */
  async function addBySymbol(watchlistId: number, symbol: string): Promise<WatchlistItem | null> {
    try {
      const resolvedSymbol = await ensureKnownInstrumentSymbol(symbol, 'Watchlist instrument')
      const instr = await api.get<{ id: number }>(`/instruments/${encodeURIComponent(resolvedSymbol)}`)
      const item = await addItem(watchlistId, instr.id)
      // Eagerly fetch price so it shows immediately if the watchlist is already expanded
      if (item) fetchPrices([resolvedSymbol])
      return item
    } catch (e) {
      console.error('Failed to resolve instrument for watchlist add', e)
      return null
    }
  }

  async function lockWatchlist(watchlistId: number) {
    try {
      await api.post(`/watchlists/${watchlistId}/lock`, {})
      const wl = watchlists.value.find(w => w.id === watchlistId)
      if (wl) wl.is_locked = true
      announceChanged(watchlistId)
    } catch (e) {
      console.error('Failed to lock watchlist', e)
    }
  }

  async function unlockWatchlist(watchlistId: number) {
    try {
      await api.post(`/watchlists/${watchlistId}/unlock`, {})
      const wl = watchlists.value.find(w => w.id === watchlistId)
      if (wl) wl.is_locked = false
      announceChanged(watchlistId)
    } catch (e) {
      console.error('Failed to unlock watchlist', e)
    }
  }

  async function renameWatchlist(watchlistId: number, name: string): Promise<Watchlist | null> {
    try {
      const wl = await api.patch<Watchlist>(`/watchlists/${watchlistId}`, { name })
      const idx = watchlists.value.findIndex(w => w.id === watchlistId)
      if (idx !== -1) watchlists.value[idx] = wl
      announceChanged(watchlistId)
      return wl
    } catch (e: any) {
      if (e?.status === 409) throw e  // propagate conflict for UI to show
      console.error('Failed to rename watchlist', e)
      return null
    }
  }

  async function seedWatchlist(watchlistId: number, instrumentIds: number[]): Promise<Watchlist | null> {
    try {
      const wl = await api.post<Watchlist>(`/watchlists/${watchlistId}/seed`, { instrument_ids: instrumentIds })
      const idx = watchlists.value.findIndex(w => w.id === watchlistId)
      if (idx !== -1) watchlists.value[idx] = wl
      announceChanged(watchlistId)
      return wl
    } catch (e) {
      console.error('Failed to seed watchlist', e)
      return null
    }
  }

  async function copyWatchlist(watchlistId: number): Promise<Watchlist | null> {
    try {
      const copy = await api.post<Watchlist>(`/watchlists/${watchlistId}/copy`, {})
      watchlists.value.push(copy)
      announceChanged(copy.id)
      return copy
    } catch (e) {
      console.error('Failed to copy watchlist', e)
      return null
    }
  }

  async function reorderWatchlists(ids: number[]) {
    // Optimistically reorder locally
    const byId = Object.fromEntries(watchlists.value.map(w => [w.id, w]))
    const reordered = ids.map(id => byId[id]).filter(Boolean)
    // Keep any watchlists not in the ids list at the end
    const rest = watchlists.value.filter(w => !ids.includes(w.id))
    watchlists.value = [...reordered, ...rest]
    try {
      await api.post('/watchlists/reorder', { ids })
      announceChanged()
    } catch (e) {
      console.error('Failed to reorder watchlists', e)
    }
  }

  async function fetchPrices(symbols: string[], force = false) {
    const unique = [...new Set(symbols.map(s => s?.toUpperCase()).filter(Boolean))]
    const toFetch = unique.filter(s => force || !priceMap.value[s])
    if (!toFetch.length) return
    await Promise.allSettled(
      toFetch.map(async (symbol) => {
        try {
          const bars: Array<{ open: number; high: number; low: number; close: number; volume?: number }> = await api.get(`/ohlcv/${symbol}/D1`, { limit: 31 })
          if (bars.length >= 2) {
            const last = bars[bars.length - 1]
            const prev = bars[bars.length - 2]
            const close = Number(last.close)
            const oldClose = priceMap.value[symbol]?.close
            if (oldClose != null && oldClose !== close) {
              flashMap.value[symbol] = close > oldClose ? 'up' : 'down'
              setTimeout(() => { flashMap.value[symbol] = null }, 900)
            }
            const volumeBars = bars.slice(0, -1).map(b => Number(b.volume ?? 0)).filter(v => v > 0)
            const avgVolume = volumeBars.length
              ? volumeBars.reduce((sum, v) => sum + v, 0) / volumeBars.length
              : undefined
            priceMap.value[symbol] = {
              close,
              prevClose: Number(prev.close),
              pct: Number(prev.close) ? (close - Number(prev.close)) / Number(prev.close) : 0,
              open: Number(last.open),
              dayHigh: Number(last.high),
              dayLow: Number(last.low),
              volume: Number(last.volume ?? 0),
              avgVolume,
              updatedAt: Date.now(),
            }
          } else if (bars.length === 1) {
            const last = bars[0]
            const close = Number(last.close)
            priceMap.value[symbol] = {
              close,
              prevClose: close,
              pct: 0,
              open: Number(last.open),
              dayHigh: Number(last.high),
              dayLow: Number(last.low),
              volume: Number(last.volume ?? 0),
              updatedAt: Date.now(),
            }
          }
        } catch { /* no bars */ }
      })
    )
  }

  function requestFocusWatchlist(id: number) {
    focusRequest.value = id
  }

  function clearFocusRequest() {
    focusRequest.value = null
  }

  return {
    watchlists,
    loading,
    priceMap,
    flashMap,
    focusRequest,
    requestFocusWatchlist,
    clearFocusRequest,
    loadWatchlists,
    createWatchlist,
    deleteWatchlist,
    addItem,
    removeItem, reorderItems,
    addBySymbol,
    renameWatchlist,
    seedWatchlist,
    lockWatchlist,
    unlockWatchlist,
    copyWatchlist,
    reorderWatchlists,
    fetchPrices,
  }
})
