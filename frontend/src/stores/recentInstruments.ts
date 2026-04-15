import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface RecentInstrument {
  symbol: string
  name?: string
  viewedAt: number
}

const STORAGE_KEY = 'chart.recentInstruments.v1'
const MAX_RECENT = 12

function loadInitial(): RecentInstrument[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export const useRecentInstrumentsStore = defineStore('recentInstruments', () => {
  const recent = ref<RecentInstrument[]>(loadInitial())

  function persist() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(recent.value))
  }

  function add(symbol: string, name?: string) {
    const normalized = symbol.trim().toUpperCase()
    if (!normalized) return
    recent.value = [
      { symbol: normalized, name, viewedAt: Date.now() },
      ...recent.value.filter(item => item.symbol !== normalized),
    ].slice(0, MAX_RECENT)
    persist()
  }

  function clear() {
    recent.value = []
    persist()
  }

  return { recent, add, clear }
})
