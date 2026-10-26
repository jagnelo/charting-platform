import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/lib/api'
import type { FavoriteInstrument } from '@/types'

export const useFavoritesStore = defineStore('favorites', () => {
  const favorites = ref<FavoriteInstrument[]>([])
  const loaded = ref(false)
  const loading = ref(false)
  const error = ref('')
  let loadGeneration = 0
  const pendingAdds = new Map<number, Promise<FavoriteInstrument | null>>()
  const pendingToggles = new Map<number, Promise<boolean>>()

  function invalidateLoadAndCheckRefresh(): boolean {
    const needsReload = !loaded.value
    loadGeneration += 1
    loading.value = false
    return needsReload
  }

  async function load(): Promise<void> {
    if (loading.value || loaded.value) return
    loading.value = true
    error.value = ''
    const generation = ++loadGeneration
    try {
      const rows = await api.get<FavoriteInstrument[]>('/favorites')
      if (generation !== loadGeneration) return
      favorites.value = [...(rows ?? [])].sort((a, b) => a.position - b.position || a.id - b.id)
      loaded.value = true
    } catch (cause) {
      if (generation === loadGeneration) {
        error.value = cause instanceof Error ? cause.message : 'Unable to load My Favorites'
      }
    } finally {
      if (generation === loadGeneration) loading.value = false
    }
  }

  async function add(instrumentId: number): Promise<FavoriteInstrument | null> {
    if (!Number.isInteger(instrumentId) || instrumentId <= 0) return null
    const existing = favorites.value.find(item => item.instrument_id === instrumentId)
    if (existing) return existing
    const pending = pendingAdds.get(instrumentId)
    if (pending) return pending
    const operation = (async () => {
      error.value = ''
      try {
        const favorite = await api.put<FavoriteInstrument>(`/favorites/instruments/${instrumentId}`, {})
        const hadLoadedList = loaded.value
        const refreshIncompleteList = invalidateLoadAndCheckRefresh()
        favorites.value = [...favorites.value.filter(item => item.instrument_id !== instrumentId), favorite]
          .sort((a, b) => a.position - b.position || a.id - b.id)
        loaded.value = hadLoadedList
        if (refreshIncompleteList) void load()
        return favorite
      } catch (cause) {
        error.value = cause instanceof Error ? cause.message : 'Unable to add to My Favorites'
        return null
      }
    })()
    pendingAdds.set(instrumentId, operation)
    try {
      return await operation
    } finally {
      pendingAdds.delete(instrumentId)
    }
  }

  async function remove(instrumentId: number): Promise<boolean> {
    if (!Number.isInteger(instrumentId) || instrumentId <= 0) return false
    error.value = ''
    try {
      await api.delete(`/favorites/instruments/${instrumentId}`)
      const hadLoadedList = loaded.value
      const refreshIncompleteList = invalidateLoadAndCheckRefresh()
      favorites.value = favorites.value.filter(item => item.instrument_id !== instrumentId)
      loaded.value = hadLoadedList
      if (refreshIncompleteList) void load()
      return true
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Unable to remove from My Favorites'
      return false
    }
  }

  async function toggle(instrumentId: number): Promise<boolean> {
    if (!Number.isInteger(instrumentId) || instrumentId <= 0) return false
    const previous = pendingToggles.get(instrumentId) ?? Promise.resolve(true)
    const operation = previous.catch(() => false).then(async () => {
      if (favorites.value.some(item => item.instrument_id === instrumentId)) return remove(instrumentId)
      return (await add(instrumentId)) !== null
    })
    pendingToggles.set(instrumentId, operation)
    try {
      return await operation
    } finally {
      if (pendingToggles.get(instrumentId) === operation) pendingToggles.delete(instrumentId)
    }
  }

  function isFavorite(instrumentId: number | null | undefined): boolean {
    return instrumentId != null && favorites.value.some(item => item.instrument_id === instrumentId)
  }

  return { favorites, loaded, loading, error, load, add, remove, toggle, isFavorite }
})
