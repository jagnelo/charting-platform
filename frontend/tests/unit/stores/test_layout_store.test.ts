/**
 * Unit tests for the layout store — panel counts, grid parsing,
 * panel-width persistence, and layout switching.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import {
  parseLayoutPanelCount,
  parseLayoutGrid,
  useLayoutStore,
} from '@/stores/layout'

// ── parseLayoutPanelCount ─────────────────────────────────────────────────────

describe('parseLayoutPanelCount — preset layouts', () => {
  it("'1'  → 1", () => expect(parseLayoutPanelCount('1')).toBe(1))
  it("'2h' → 2", () => expect(parseLayoutPanelCount('2h')).toBe(2))
  it("'2v' → 2", () => expect(parseLayoutPanelCount('2v')).toBe(2))
  it("'3l' → 3", () => expect(parseLayoutPanelCount('3l')).toBe(3))
  it("'3r' → 3", () => expect(parseLayoutPanelCount('3r')).toBe(3))
  it("'4'  → 4", () => expect(parseLayoutPanelCount('4')).toBe(4))
})

describe('parseLayoutPanelCount — NxM grid layouts', () => {
  it("'2x2' → 4", () => expect(parseLayoutPanelCount('2x2')).toBe(4))
  it("'3x2' → 6", () => expect(parseLayoutPanelCount('3x2')).toBe(6))
  it("'4x3' → 12", () => expect(parseLayoutPanelCount('4x3')).toBe(12))
  it("'1x1' → 1", () => expect(parseLayoutPanelCount('1x1')).toBe(1))
})

describe('parseLayoutPanelCount — unknown format defaults to 1', () => {
  it("'unknown' → 1", () => expect(parseLayoutPanelCount('unknown')).toBe(1))
  it("'' → 1",          () => expect(parseLayoutPanelCount('')).toBe(1))
})

// ── parseLayoutGrid ───────────────────────────────────────────────────────────

describe('parseLayoutGrid', () => {
  it("'3x2' → {cols:3, rows:2}", () => {
    expect(parseLayoutGrid('3x2')).toEqual({ cols: 3, rows: 2 })
  })

  it("'2x4' → {cols:2, rows:4}", () => {
    expect(parseLayoutGrid('2x4')).toEqual({ cols: 2, rows: 4 })
  })

  it("'1' → null (not NxM)", () => {
    expect(parseLayoutGrid('1')).toBeNull()
  })

  it("'2h' → null (not NxM)", () => {
    expect(parseLayoutGrid('2h')).toBeNull()
  })

  it("'' → null", () => {
    expect(parseLayoutGrid('')).toBeNull()
  })
})

// ── useLayoutStore ────────────────────────────────────────────────────────────

describe('useLayoutStore', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('initial panelWidths are defaults when localStorage is empty', () => {
    const store = useLayoutStore()
    expect(store.panelWidths.watchlist).toBe(300)
    expect(store.panelWidths.indicatorPanel).toBe(220)
  })

  it('setPanelWidth updates state', () => {
    const store = useLayoutStore()
    store.setPanelWidth('watchlist', 400)
    expect(store.panelWidths.watchlist).toBe(400)
  })

  it('setPanelWidth persists to localStorage', () => {
    const store = useLayoutStore()
    store.setPanelWidth('indicatorPanel', 350)
    const saved = JSON.parse(localStorage.getItem('chart.panelWidths.v1')!)
    expect(saved.indicatorPanel).toBe(350)
  })

  it('loads persisted widths from localStorage', () => {
    localStorage.setItem('chart.panelWidths.v1', JSON.stringify({ watchlist: 480, indicatorPanel: 300 }))
    setActivePinia(createPinia())
    const store = useLayoutStore()
    expect(store.panelWidths.watchlist).toBe(480)
    expect(store.panelWidths.indicatorPanel).toBe(300)
  })

  it('falls back to defaults on malformed localStorage', () => {
    localStorage.setItem('chart.panelWidths.v1', 'not-json{{{')
    setActivePinia(createPinia())
    const store = useLayoutStore()
    expect(store.panelWidths.watchlist).toBe(300)
    expect(store.panelWidths.indicatorPanel).toBe(220)
  })

  it('initial layout is 1 panel', () => {
    const store = useLayoutStore()
    expect(store.layout).toBe('1')
    expect(store.panels).toHaveLength(1)
    expect(store.panelCount).toBe(1)
  })

  it('setLayout("2h") creates 2 panels', () => {
    const store = useLayoutStore()
    store.setLayout('2h')
    expect(store.panels).toHaveLength(2)
    expect(store.panelCount).toBe(2)
  })

  it('setLayout("4") creates 4 panels', () => {
    const store = useLayoutStore()
    store.setLayout('4')
    expect(store.panels).toHaveLength(4)
  })

  it('setLayout preserves existing panel symbols', () => {
    const store = useLayoutStore()
    store.panels[0].symbol = 'AAPL'
    store.setLayout('2h')
    expect(store.panels[0].symbol).toBe('AAPL')
  })

  it('activePanelId resets to first panel when switching to smaller layout', () => {
    const store = useLayoutStore()
    store.setLayout('4')
    store.setActivePanel('p3')
    store.setLayout('2h')  // p3 no longer exists
    expect(store.panels.find(p => p.id === store.activePanelId)).toBeTruthy()
  })

  it('updatePanel patches only the specified fields', () => {
    const store = useLayoutStore()
    store.updatePanel('p0', { symbol: 'MSFT', timeframe: 'H1' })
    expect(store.panels[0].symbol).toBe('MSFT')
    expect(store.panels[0].timeframe).toBe('H1')
    expect(store.panels[0].id).toBe('p0')  // id unchanged
  })

  it('saveProfile stores current layout and panels', () => {
    const store = useLayoutStore()
    store.setLayout('2h')
    store.panels[0].symbol = 'AAPL'
    store.saveProfile('MyLayout')
    expect(store.profiles).toHaveLength(1)
    expect(store.profiles[0].name).toBe('MyLayout')
    expect(store.profiles[0].layout).toBe('2h')
  })

  it('deleteProfile removes only the targeted profile', () => {
    const store = useLayoutStore()
    store.saveProfile('A')
    store.saveProfile('B')
    const idA = store.profiles.find(p => p.name === 'A')!.id
    store.deleteProfile(idA)
    expect(store.profiles.map(p => p.name)).not.toContain('A')
    expect(store.profiles.map(p => p.name)).toContain('B')
  })

  it('loadProfile restores layout and panel count', () => {
    const store = useLayoutStore()
    store.setLayout('4')
    store.saveProfile('FourUp')
    store.setLayout('1')
    const profileId = store.profiles[0].id
    store.loadProfile(profileId)
    expect(store.layout).toBe('4')
    expect(store.panels).toHaveLength(4)
  })

  it('toggleSync flips isSyncEnabled', () => {
    const store = useLayoutStore()
    expect(store.isSyncEnabled).toBe(true)
    store.toggleSync()
    expect(store.isSyncEnabled).toBe(false)
    store.toggleSync()
    expect(store.isSyncEnabled).toBe(true)
  })

  it('setSyncedTs is ignored when sync is disabled', () => {
    const store = useLayoutStore()
    store.toggleSync()
    store.setSyncedTs('2024-01-01T00:00:00Z', 'p0')
    expect(store.syncedTs).toBeNull()
  })
})
