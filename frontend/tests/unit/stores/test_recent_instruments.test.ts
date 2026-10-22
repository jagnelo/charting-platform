import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useRecentInstrumentsStore } from '@/stores/recentInstruments'

describe('recent instrument navigation history', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('walks repeated symbol visits backward and truncates forward history on a new selection', () => {
    const store = useRecentInstrumentsStore()
    store.add('spy')
    store.add('QQQ')
    store.add('SPY')

    expect(store.history).toEqual(['SPY', 'QQQ', 'SPY'])
    expect(store.previous()).toBe('QQQ')
    expect(store.previous()).toBe('SPY')
    expect(store.previous()).toBeNull()

    store.add('DIA')
    expect(store.history).toEqual(['SPY', 'DIA'])
    expect(store.previous()).toBe('SPY')
    expect(store.previous()).toBeNull()
  })

  it('persists history, keeps Backspace traversal out of the new-visit stack, and clears both lists', () => {
    const store = useRecentInstrumentsStore()
    store.add('SPY')
    store.add('QQQ')
    expect(store.previous()).toBe('SPY')

    // Selecting a historical entry should refresh the recent-symbol list but
    // leave the history cursor in place so another Backspace can continue back.
    store.add('SPY', undefined, false)
    expect(store.history).toEqual(['SPY', 'QQQ'])
    expect(store.previous()).toBeNull()
    expect(localStorage.getItem('chart.symbolHistory.v1')).toBe('["SPY","QQQ"]')

    store.clear()
    expect(store.recent).toEqual([])
    expect(store.history).toEqual([])
    expect(localStorage.getItem('chart.symbolHistory.v1')).toBe('[]')
  })
})
