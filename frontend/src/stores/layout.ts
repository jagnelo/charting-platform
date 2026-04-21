import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Timeframe } from '@/types'

// ── Layout types ──────────────────────────────────────────────────────────────
//
//  '1'   single panel
//  '2h'  two columns
//  '2v'  two rows
//  '3l'  large left + two stacked right
//  '3r'  two stacked left + large right
//  '4'   2 × 2 grid
//  'NxM' custom grid, e.g. '3x2' = 3 cols × 2 rows

export type PresetLayout = '1' | '2h' | '2v' | '3l' | '3r' | '4'
export type LayoutType = PresetLayout | string  // includes 'NxM' custom strings

export interface PanelConfig {
  id: string
  symbol: string
  timeframe: Timeframe
  linkedToGlobal: boolean
}

export interface LayoutProfile {
  id: string
  name: string
  layout: LayoutType
  panels: PanelConfig[]
  createdAt: number
}

const PRESET_PANEL_COUNT: Record<PresetLayout, number> = {
  '1':  1,
  '2h': 2,
  '2v': 2,
  '3l': 3,
  '3r': 3,
  '4':  4,
}

const DEFAULT_TIMEFRAMES: Timeframe[] = ['D1', 'H4', 'H1', 'M15', 'M30', 'W1', 'M5', 'M1']
const PROFILE_STORAGE_KEY  = 'chart.layoutProfiles.v1'
const WIDTHS_STORAGE_KEY   = 'chart.panelWidths.v1'

export interface PanelWidths {
  watchlist: number
  indicatorPanel: number
}

function loadPanelWidths(): PanelWidths {
  try {
    const parsed = JSON.parse(localStorage.getItem(WIDTHS_STORAGE_KEY) ?? '{}')
    return {
      watchlist:      typeof parsed.watchlist      === 'number' ? parsed.watchlist      : 300,
      indicatorPanel: typeof parsed.indicatorPanel === 'number' ? parsed.indicatorPanel : 220,
    }
  } catch {
    return { watchlist: 300, indicatorPanel: 220 }
  }
}

function loadProfiles(): LayoutProfile[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(PROFILE_STORAGE_KEY) ?? '[]')
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function parseLayoutPanelCount(layout: LayoutType): number {
  if (layout in PRESET_PANEL_COUNT) return PRESET_PANEL_COUNT[layout as PresetLayout]
  // NxM format: cols × rows
  const m = layout.match(/^(\d+)x(\d+)$/)
  if (m) return parseInt(m[1]) * parseInt(m[2])
  return 1
}

export function parseLayoutGrid(layout: LayoutType): { cols: number; rows: number } | null {
  const m = layout.match(/^(\d+)x(\d+)$/)
  if (m) return { cols: parseInt(m[1]), rows: parseInt(m[2]) }
  return null
}

function makePanels(count: number, current: PanelConfig[], fallbackSymbol = ''): PanelConfig[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `p${i}`,
    symbol:         current[i]?.symbol         ?? fallbackSymbol,
    timeframe:      current[i]?.timeframe      ?? DEFAULT_TIMEFRAMES[i] ?? 'D1',
    linkedToGlobal: current[i]?.linkedToGlobal ?? true,
  }))
}

export const useLayoutStore = defineStore('layout', () => {
  const layout        = ref<LayoutType>('1')
  const panels        = ref<PanelConfig[]>(makePanels(1, []))
  const activePanelId = ref<string>('p0')
  const profiles      = ref<LayoutProfile[]>(loadProfiles())
  const panelWidths   = ref<PanelWidths>(loadPanelWidths())

  const syncedTs        = ref<string | null>(null)
  const syncSourcePanel = ref<string | null>(null)
  const isSyncEnabled   = ref(true)

  const panelCount = computed(() => parseLayoutPanelCount(layout.value))

  function setLayout(l: LayoutType) {
    const fallback = panels.value.find(p => p.id === activePanelId.value)?.symbol ?? panels.value[0]?.symbol ?? ''
    layout.value = l
    panels.value = makePanels(parseLayoutPanelCount(l), panels.value, fallback)
    if (!panels.value.find(p => p.id === activePanelId.value)) {
      activePanelId.value = panels.value[0].id
    }
  }

  function setActivePanel(id: string) {
    activePanelId.value = id
  }

  function updatePanel(id: string, patch: Partial<Omit<PanelConfig, 'id'>>) {
    const p = panels.value.find(p => p.id === id)
    if (p) Object.assign(p, patch)
  }

  function setSyncedTs(ts: string, sourcePanel: string) {
    if (!isSyncEnabled.value) return
    syncedTs.value        = ts
    syncSourcePanel.value = sourcePanel
  }

  function toggleSync() {
    isSyncEnabled.value = !isSyncEnabled.value
  }

  function setPanelWidth(key: keyof PanelWidths, value: number) {
    panelWidths.value[key] = value
    localStorage.setItem(WIDTHS_STORAGE_KEY, JSON.stringify(panelWidths.value))
  }

  function persistProfiles() {
    localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(profiles.value))
  }

  function saveProfile(name: string) {
    const trimmed = name.trim()
    if (!trimmed) return
    const profile: LayoutProfile = {
      id: `${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      name: trimmed,
      layout: layout.value,
      panels: panels.value.map(panel => ({ ...panel })),
      createdAt: Date.now(),
    }
    profiles.value = [profile, ...profiles.value.filter(p => p.name !== trimmed)].slice(0, 12)
    persistProfiles()
  }

  function loadProfile(id: string) {
    const profile = profiles.value.find(p => p.id === id)
    if (!profile) return
    layout.value = profile.layout
    panels.value = makePanels(parseLayoutPanelCount(profile.layout), profile.panels)
    activePanelId.value = panels.value[0]?.id ?? 'p0'
  }

  function deleteProfile(id: string) {
    profiles.value = profiles.value.filter(p => p.id !== id)
    persistProfiles()
  }

  return {
    layout, panels, activePanelId, panelCount, profiles, panelWidths,
    syncedTs, syncSourcePanel, isSyncEnabled,
    setLayout, setActivePanel, updatePanel,
    setSyncedTs, toggleSync,
    saveProfile, loadProfile, deleteProfile,
    setPanelWidth,
  }
})
