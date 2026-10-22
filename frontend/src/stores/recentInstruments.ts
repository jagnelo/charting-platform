import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface RecentInstrument {
  symbol: string
  name?: string
  viewedAt: number
}

const STORAGE_KEY = 'chart.recentInstruments.v1'
const HISTORY_STORAGE_KEY = 'chart.symbolHistory.v1'
const MAX_RECENT = 12
const MAX_HISTORY = 50

function loadInitial(): RecentInstrument[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function loadHistory(): string[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(HISTORY_STORAGE_KEY) ?? '[]')
    if (!Array.isArray(parsed)) return []
    return parsed
      .filter((symbol): symbol is string => typeof symbol === 'string' && Boolean(symbol.trim()))
      .map(symbol => symbol.trim().toUpperCase())
      .slice(-MAX_HISTORY)
  } catch {
    return []
  }
}

export const useRecentInstrumentsStore = defineStore('recentInstruments', () => {
  const recent = ref<RecentInstrument[]>(loadInitial())
  const history = ref<string[]>(loadHistory())
  // The cursor points at the currently viewed entry. Backspace moves it toward
  // older entries; selecting a new symbol then truncates the forward branch.
  const historyIndex = ref(history.value.length - 1)

  function persist() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(recent.value))
  }

  function persistHistory() {
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(history.value))
  }

  function add(symbol: string, name?: string, recordHistory = true) {
    const normalized = symbol.trim().toUpperCase()
    if (!normalized) return
    recent.value = [
      { symbol: normalized, name, viewedAt: Date.now() },
      ...recent.value.filter(item => item.symbol !== normalized),
    ].slice(0, MAX_RECENT)
    persist()
    if (!recordHistory) return

    const nextHistory = history.value.slice(0, historyIndex.value + 1)
    if (nextHistory[nextHistory.length - 1] !== normalized) nextHistory.push(normalized)
    history.value = nextHistory.slice(-MAX_HISTORY)
    historyIndex.value = history.value.length - 1
    persistHistory()
  }

  function previous(): string | null {
    if (historyIndex.value <= 0) return null
    historyIndex.value -= 1
    return history.value[historyIndex.value] ?? null
  }

  function clear() {
    recent.value = []
    history.value = []
    historyIndex.value = -1
    persist()
    persistHistory()
  }

  return { recent, history, add, previous, clear }
})
