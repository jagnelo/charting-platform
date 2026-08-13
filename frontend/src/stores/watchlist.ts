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

// Golden Layout can briefly keep more than one virtual tool root alive while
// activating a newly opened tab. Keep create de-duplication outside the Pinia
// setup closure so duplicate event handlers across those roots still share
// one in-flight request.
const pendingWatchlistCreates = new Map<string, Promise<Watchlist | null>>()
const pendingWatchlistItems = new Map<string, Promise<WatchlistItem | null>>()

function markWatchlistCreateResult(watchlist: Watchlist, created: boolean): Watchlist {
  // Keep the marker non-enumerable so the canonical Watchlist shape remains
  // unchanged for persisted state and existing consumers.
  Object.defineProperty(watchlist, '__createdByRequest', { value: created, configurable: true })
  return watchlist
}

export const useWatchlistStore = defineStore('watchlist', () => {
  const watchlists = ref<Watchlist[]>([])
  const loading = ref(false)
  const loadError = ref('')
  const priceMap = ref<Record<string, WatchlistQuote>>({})
  const flashMap = ref<Record<string, 'up' | 'down' | null>>({})
  // A cross-window invalidation can return after a local mutation.  Do not let
  // that older list response replace the locally updated membership and cause
  // virtualized rows to disappear while the user is interacting with them.
  let mutationGeneration = 0
  // A reload can briefly lag a just-committed create. Preserve those local
  // rows until the canonical response includes them.
  const locallyCreatedWatchlistIds = new Set<number>()
  // Cross-window invalidation can arrive immediately after an item mutation,
  // before the canonical read model has caught up. Preserve those item-level
  // deltas while reconciling the response instead of making the visible list
  // briefly empty again.
  const locallyAddedItems = new Map<number, WatchlistItem[]>()
  const locallyRemovedItemIds = new Map<number, Set<number>>()
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
    loadError.value = ''
    const generation = mutationGeneration
    try {
      const loaded = (await api.get<Watchlist[]>('/watchlists')) ?? []
      if (generation === mutationGeneration) {
        const loadedIds = new Set(loaded.map(watchlist => watchlist.id))
        const locallyMissing = watchlists.value.filter(watchlist => locallyCreatedWatchlistIds.has(watchlist.id) && !loadedIds.has(watchlist.id))
        const reconciled = loaded.map(watchlist => {
          const additions = locallyAddedItems.get(watchlist.id) ?? []
          const removed = locallyRemovedItemIds.get(watchlist.id) ?? new Set<number>()
          const loadedItemIds = new Set(watchlist.items.map(item => item.id))
          const remainingAdditions = additions.filter(item => !loadedItemIds.has(item.id))
          const remainingRemovals = new Set([...removed].filter(itemId => loadedItemIds.has(itemId)))
          if (remainingAdditions.length) locallyAddedItems.set(watchlist.id, remainingAdditions)
          else locallyAddedItems.delete(watchlist.id)
          if (remainingRemovals.size) locallyRemovedItemIds.set(watchlist.id, remainingRemovals)
          else locallyRemovedItemIds.delete(watchlist.id)
          return {
            ...watchlist,
            items: [
              ...watchlist.items.filter(item => !removed.has(item.id)),
              ...remainingAdditions,
            ],
          }
        })
        watchlists.value = [...reconciled, ...locallyMissing]
      }
    } catch (e) {
      if (isTransientLoadError(e)) {
        // A broadcast-triggered refresh can briefly fail while the backend is
        // under load. Keep the last canonical/local snapshot visible instead
        // of clearing the selected list and making a successful mutation look
        // as though it disappeared from the active tool.
        return
      }
      console.error('Failed to load watchlists', e)
      loadError.value = e instanceof Error ? e.message : 'Unable to load watchlists'
    } finally {
      loading.value = false
    }
  }

  async function createWatchlist(name: string, description?: string, screener_id?: number): Promise<Watchlist | null> {
    const key = `${name.trim().toLocaleLowerCase()}\u0000${description ?? ''}\u0000${screener_id ?? ''}`
    const pending = pendingWatchlistCreates.get(key)
    if (pending) return pending
    const operation = createWatchlistOnce(name, description, screener_id)
    pendingWatchlistCreates.set(key, operation)
    try {
      return await operation
    } finally {
      pendingWatchlistCreates.delete(key)
    }
  }

  async function createWatchlistOnce(name: string, description?: string, screener_id?: number): Promise<Watchlist | null> {
    mutationGeneration += 1
    try {
      const body: Record<string, unknown> = { name, description }
      if (screener_id != null) body.screener_id = screener_id
      const wl = await api.post<Watchlist>('/watchlists', body)
      markWatchlistCreateResult(wl, true)
      locallyCreatedWatchlistIds.add(wl.id)
      watchlists.value.push(wl)
      announceChanged(wl.id)
      return wl
    } catch (e) {
      // A second tab (or a duplicate UI dispatch) can win the unique-name
      // race after the create has already committed. Treat that 409 as an
      // idempotent create: reload the canonical list and return the existing
      // row instead of leaving the tool in a false failure state.
      const message = e instanceof Error ? e.message : String(e ?? '')
      if (/API POST \/watchlists → 409/i.test(message)) {
        await loadWatchlists()
        const existing = watchlists.value.find(watchlist => watchlist.name.trim().toLowerCase() === name.trim().toLowerCase())
        if (existing) {
          locallyCreatedWatchlistIds.add(existing.id)
          return markWatchlistCreateResult(existing, false)
        }
      }
      console.error('Failed to create watchlist', e)
      return null
    }
  }

  async function deleteWatchlist(id: number): Promise<boolean> {
    mutationGeneration += 1
    try {
      await api.delete(`/watchlists/${id}`)
      locallyCreatedWatchlistIds.delete(id)
      watchlists.value = watchlists.value.filter(w => w.id !== id)
      announceChanged(id)
      return true
    } catch (e) {
      console.error('Failed to delete watchlist', e)
      return false
    }
  }

  async function addItem(watchlistId: number, instrumentId: number): Promise<WatchlistItem | null> {
    const key = `${watchlistId}:${instrumentId}`
    const existing = watchlists.value.find(watchlist => watchlist.id === watchlistId)?.items.find(item => item.instrument_id === instrumentId)
    if (existing) return existing
    const pending = pendingWatchlistItems.get(key)
    if (pending) return pending
    const operation = addItemOnce(watchlistId, instrumentId)
    pendingWatchlistItems.set(key, operation)
    try {
      return await operation
    } finally {
      pendingWatchlistItems.delete(key)
    }
  }

  async function addItemOnce(watchlistId: number, instrumentId: number): Promise<WatchlistItem | null> {
    mutationGeneration += 1
    try {
      const item = await api.post<WatchlistItem>(`/watchlists/${watchlistId}/items`, {
        instrument_id: instrumentId,
      })
      const wl = watchlists.value.find(w => w.id === watchlistId)
      if (wl) {
        // Replace the containing objects so all virtualized consumers observe
        // the membership mutation immediately, even while a reload is in flight.
        watchlists.value = watchlists.value.map(value => value.id === watchlistId
          ? { ...value, items: [...value.items, item] }
          : value)
      }
      const additions = locallyAddedItems.get(watchlistId) ?? []
      if (!additions.some(existing => existing.id === item.id)) locallyAddedItems.set(watchlistId, [...additions, item])
      announceChanged(watchlistId)
      return item
    } catch (e: any) {
      const message = e instanceof Error ? e.message : String(e ?? '')
      if (e?.status === 409 || /API POST \/watchlists\/\d+\/items → 409/i.test(message)) {
        // Duplicate dispatches are idempotent: the first request may already
        // have inserted the row locally while the second receives the API's
        // uniqueness conflict. Return the visible canonical row so callers
        // do not surface a false add failure or reset their selection.
        return watchlists.value.find(watchlist => watchlist.id === watchlistId)?.items.find(item => item.instrument_id === instrumentId) ?? null
      }
      console.error('Failed to add watchlist item', e)
      return null
    }
  }

  async function removeItem(watchlistId: number, itemId: number) {
    mutationGeneration += 1
    try {
      await api.delete(`/watchlists/${watchlistId}/items/${itemId}`)
      const wl = watchlists.value.find(w => w.id === watchlistId)
      if (wl) wl.items = wl.items.filter(i => i.id !== itemId)
      const additions = locallyAddedItems.get(watchlistId)?.filter(item => item.id !== itemId) ?? []
      if (additions.length) locallyAddedItems.set(watchlistId, additions)
      else locallyAddedItems.delete(watchlistId)
      const removals = locallyRemovedItemIds.get(watchlistId) ?? new Set<number>()
      removals.add(itemId)
      locallyRemovedItemIds.set(watchlistId, removals)
      announceChanged(watchlistId)
    } catch (e) {
      console.error('Failed to remove watchlist item', e)
    }
  }

  async function transferItem(
    sourceWatchlistId: number,
    itemId: number,
    targetWatchlistId: number,
    mode: 'copy' | 'move',
  ): Promise<WatchlistItem | null> {
    if (sourceWatchlistId === targetWatchlistId) return null
    mutationGeneration += 1
    try {
      const transferred = await api.post<WatchlistItem>(
        `/watchlists/${targetWatchlistId}/items/transfer`,
        { source_watchlist_id: sourceWatchlistId, item_id: itemId, mode },
      )
      const target = watchlists.value.find(watchlist => watchlist.id === targetWatchlistId)
      if (target && !target.items.some(item => item.id === transferred.id)) {
        target.items = [...target.items, transferred]
      }
      if (mode === 'move') {
        const source = watchlists.value.find(watchlist => watchlist.id === sourceWatchlistId)
        if (source) source.items = source.items.filter(item => item.id !== itemId)
      }
      locallyAddedItems.set(targetWatchlistId, [
        ...(locallyAddedItems.get(targetWatchlistId) ?? []).filter(item => item.id !== transferred.id),
        transferred,
      ])
      if (mode === 'move') {
        const removals = locallyRemovedItemIds.get(sourceWatchlistId) ?? new Set<number>()
        removals.add(itemId)
        locallyRemovedItemIds.set(sourceWatchlistId, removals)
      }
      announceChanged(sourceWatchlistId)
      announceChanged(targetWatchlistId)
      return transferred
    } catch (e) {
      console.error(`Failed to ${mode} watchlist item`, e)
      return null
    }
  }

  async function transferItems(
    sourceWatchlistId: number,
    itemIds: number[],
    targetWatchlistId: number,
    mode: 'copy' | 'move',
  ): Promise<WatchlistItem[]> {
    if (sourceWatchlistId === targetWatchlistId || !itemIds.length) return []
    mutationGeneration += 1
    try {
      const transferred = await api.post<WatchlistItem[]>(
        `/watchlists/${targetWatchlistId}/items/transfer-batch`,
        { source_watchlist_id: sourceWatchlistId, item_ids: itemIds, mode },
      ) ?? []
      const target = watchlists.value.find(watchlist => watchlist.id === targetWatchlistId)
      if (target) {
        const transferredIds = new Set(transferred.map(item => item.id))
        target.items = [...target.items.filter(item => !transferredIds.has(item.id)), ...transferred]
      }
      if (mode === 'move') {
        const source = watchlists.value.find(watchlist => watchlist.id === sourceWatchlistId)
        if (source) {
          const movedIds = new Set(itemIds)
          source.items = source.items.filter(item => !movedIds.has(item.id))
        }
      }
      locallyAddedItems.set(targetWatchlistId, [
        ...(locallyAddedItems.get(targetWatchlistId) ?? []),
        ...transferred,
      ])
      if (mode === 'move') {
        const removals = locallyRemovedItemIds.get(sourceWatchlistId) ?? new Set<number>()
        itemIds.forEach(itemId => removals.add(itemId))
        locallyRemovedItemIds.set(sourceWatchlistId, removals)
      }
      announceChanged(sourceWatchlistId)
      announceChanged(targetWatchlistId)
      return transferred
    } catch (e) {
      console.error(`Failed to ${mode} watchlist items`, e)
      return []
    }
  }

  async function setItemFlag(watchlistId: number, itemId: number, flagged: boolean): Promise<boolean> {
    mutationGeneration += 1
    try {
      const item = await api.patch<WatchlistItem>(`/watchlists/${watchlistId}/items/${itemId}`, { flagged })
      const wl = watchlists.value.find(value => value.id === watchlistId)
      const local = wl?.items.find(value => value.id === itemId)
      if (local) local.flagged = item.flagged ?? flagged
      announceChanged(watchlistId)
      return true
    } catch (e) {
      console.error('Failed to update watchlist item flag', e)
      return false
    }
  }

  async function reorderItems(watchlistId: number, ids: number[]) {
    mutationGeneration += 1
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
  async function addBySymbol(watchlistId: number, symbol: string, localOnly = false): Promise<WatchlistItem | null> {
    try {
      const resolvedSymbol = await ensureKnownInstrumentSymbol(symbol, 'Watchlist instrument')
      const instr = await api.get<{ id: number }>(`/instruments/${encodeURIComponent(resolvedSymbol)}`)
      const item = await addItem(watchlistId, instr.id)
      // Eagerly fetch price so it shows immediately if the watchlist is already expanded
      // Keep the mutation busy until the eager quote refresh settles.  The
      // watchlist rows derive their numeric cells from priceMap; returning
      // before that update lets a virtualized row remount while a user is
      // opening its context menu immediately after Add.
      if (item) await fetchPrices([resolvedSymbol], false, localOnly)
      return item
    } catch (e) {
      console.error('Failed to resolve instrument for watchlist add', e)
      return null
    }
  }

  async function lockWatchlist(watchlistId: number) {
    mutationGeneration += 1
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
    mutationGeneration += 1
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
    mutationGeneration += 1
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
    mutationGeneration += 1
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
    mutationGeneration += 1
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
    mutationGeneration += 1
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

  async function fetchPrices(symbols: string[], force = false, localOnly = false) {
    const unique = [...new Set(symbols.map(s => s?.toUpperCase()).filter(Boolean))]
    const toFetch = unique.filter(s => force || !priceMap.value[s])
    if (!toFetch.length) return
    await Promise.allSettled(
      toFetch.map(async (symbol) => {
        try {
          const bars: Array<{ open: number; high: number; low: number; close: number; volume?: number }> = await api.get(
            localOnly ? `/ohlcv/local/${symbol}/D1` : `/ohlcv/${symbol}/D1`,
            { limit: 31 },
          )
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
    loadError,
    priceMap,
    flashMap,
    focusRequest,
    requestFocusWatchlist,
    clearFocusRequest,
    loadWatchlists,
    createWatchlist,
    deleteWatchlist,
    addItem,
    removeItem, transferItem, transferItems, setItemFlag, reorderItems,
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
