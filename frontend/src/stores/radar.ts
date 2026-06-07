import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/lib/api'
import type {
  PriceAlert,
  RadarDetection,
  RadarOutcomeSummary,
  RadarRun,
  RadarWatchlistAction,
  Timeframe,
} from '@/types'

interface PendingChartDetection {
  detectionId: number
  instrumentId: number
  instrumentSymbol: string
  timeframe: Timeframe
}

interface RadarScanOptions {
  universe_type?: string
  universe_filter?: Record<string, unknown> | null
}

interface RadarSavedView {
  name: string
  filters: {
    timeframe?: Timeframe
    setup_type?: string
    state?: string
    min_score?: number
    symbol?: string
    active_only?: boolean
    fresh_only?: boolean
  }
}

const RADAR_SAVED_VIEWS_KEY = 'charting-platform.radar.saved-views'

const RADAR_SETUP_SEQUENCE_PRIORITY: Record<string, number> = {
  approaching_support: 0,
  approaching_resistance: 0,
  compression_support: 0,
  compression_resistance: 0,
  rejection: 1,
  reclaim: 1,
  fakeout: 1,
  fakedown: 1,
  breakout: 2,
  breakdown: 2,
  failed_reclaim: 2,
  failed_breakdown_recovery: 2,
  breakout_retest: 3,
  breakdown_retest: 3,
}

const RADAR_STATE_SEQUENCE_PRIORITY: Record<string, number> = {
  developing: 0,
  confirmed: 1,
  resolved: 2,
  stale: 3,
  invalidated: 4,
}

function compareRadarChronology(left: RadarDetection, right: RadarDetection) {
  const leftTime = new Date(left.signal_at ?? left.observed_at).getTime()
  const rightTime = new Date(right.signal_at ?? right.observed_at).getTime()
  if (Number.isFinite(leftTime) && Number.isFinite(rightTime) && leftTime !== rightTime) {
    return leftTime - rightTime
  }
  const leftCreated = new Date(left.created_at).getTime()
  const rightCreated = new Date(right.created_at).getTime()
  if (Number.isFinite(leftCreated) && Number.isFinite(rightCreated) && leftCreated !== rightCreated) {
    return leftCreated - rightCreated
  }
  const stateDelta =
    (RADAR_STATE_SEQUENCE_PRIORITY[left.state] ?? 99)
    - (RADAR_STATE_SEQUENCE_PRIORITY[right.state] ?? 99)
  if (stateDelta !== 0) {
    return stateDelta
  }
  if (left.thread_id != null && left.thread_id === right.thread_id) {
    const leftIndex = left.thread_event_index ?? Number.MAX_SAFE_INTEGER
    const rightIndex = right.thread_event_index ?? Number.MAX_SAFE_INTEGER
    if (leftIndex !== rightIndex) {
      return leftIndex - rightIndex
    }
  }
  const priorityDelta =
    (RADAR_SETUP_SEQUENCE_PRIORITY[left.setup_type] ?? 99)
    - (RADAR_SETUP_SEQUENCE_PRIORITY[right.setup_type] ?? 99)
  if (priorityDelta !== 0) {
    return priorityDelta
  }
  return left.id - right.id
}

function compareRadarListDetections(left: RadarDetection, right: RadarDetection) {
  if (left.instrument_id === right.instrument_id) {
    return compareRadarChronology(left, right)
  }
  if (left.score !== right.score) {
    return right.score - left.score
  }
  return left.id - right.id
}

export const useRadarStore = defineStore('radar', () => {
  const runs = ref<RadarRun[]>([])
  const detections = ref<RadarDetection[]>([])
  const selectedDetection = ref<RadarDetection | null>(null)
  const savedViews = ref<RadarSavedView[]>([])
  const chartDetections = ref<RadarDetection[]>([])
  const activeChartDetectionIds = ref<number[]>([])
  const focusedChartDetectionId = ref<number | null>(null)
  const pendingChartDetection = ref<PendingChartDetection | null>(null)
  const selectedInstrumentHistory = ref<RadarDetection[]>([])
  const outcomeSummary = ref<RadarOutcomeSummary[]>([])
  const isLoading = ref(false)

  function persistSavedViews() {
    if (typeof localStorage === 'undefined') return
    localStorage.setItem(RADAR_SAVED_VIEWS_KEY, JSON.stringify(savedViews.value))
  }

  function loadSavedViews() {
    if (typeof localStorage === 'undefined') return
    const raw = localStorage.getItem(RADAR_SAVED_VIEWS_KEY)
    if (!raw) return
    try {
      const parsed = JSON.parse(raw) as RadarSavedView[]
      savedViews.value = Array.isArray(parsed) ? parsed : []
    } catch {
      savedViews.value = []
    }
  }

  function saveView(name: string, filters: RadarSavedView['filters']) {
    const normalizedName = name.trim()
    if (!normalizedName) return
    savedViews.value = [
      ...savedViews.value.filter(view => view.name !== normalizedName),
      { name: normalizedName, filters },
    ].sort((left, right) => left.name.localeCompare(right.name))
    persistSavedViews()
  }

  function deleteView(name: string) {
    savedViews.value = savedViews.value.filter(view => view.name !== name)
    persistSavedViews()
  }

  async function loadRuns(limit = 5, timeframe?: Timeframe) {
    runs.value = await api.get<RadarRun[]>('/radar/runs', { limit, timeframe })
  }

  async function loadDetections(params: {
    timeframe?: Timeframe
    setup_type?: string
    state?: string
    min_score?: number
    symbol?: string
    limit?: number
    active_only?: boolean
    fresh_only?: boolean
  } = {}) {
    isLoading.value = true
    try {
      const loadedDetections = await api.get<RadarDetection[]>('/radar/detections', params)
      detections.value = [...loadedDetections].sort(compareRadarListDetections)
    } finally {
      isLoading.value = false
    }
  }

  async function loadDetection(id: number) {
    selectedDetection.value = await api.get<RadarDetection>(`/radar/detections/${id}`)
    return selectedDetection.value
  }

  async function runScan(timeframe: Timeframe, options: RadarScanOptions = {}) {
    const run = await api.post<RadarRun>('/radar/run', {
      timeframe,
      universe_type: options.universe_type ?? 'all',
      universe_filter: options.universe_filter ?? null,
    })
    await loadRuns(5, timeframe)
    return run
  }

  async function loadChartDetections(
    instrumentId: number,
    timeframe: Timeframe,
    preferredDetectionId?: number | null,
  ) {
    const loadedDetections = await api.get<RadarDetection[]>(
      `/radar/instruments/${instrumentId}/overlays`,
      { active_only: preferredDetectionId == null, timeframe },
    )
    chartDetections.value = [...loadedDetections].sort(compareRadarChronology)

    const availableIds = chartDetections.value.map(detection => detection.id)
    if (!availableIds.length) {
      activeChartDetectionIds.value = []
      focusedChartDetectionId.value = null
      return chartDetections.value
    }

    if (preferredDetectionId != null && availableIds.includes(preferredDetectionId)) {
      activeChartDetectionIds.value = [preferredDetectionId]
      focusedChartDetectionId.value = preferredDetectionId
      return chartDetections.value
    }

    activeChartDetectionIds.value = []
    focusedChartDetectionId.value = null
    return chartDetections.value
  }

  function clearChartDetections() {
    chartDetections.value = []
    activeChartDetectionIds.value = []
    focusedChartDetectionId.value = null
  }

  function queueChartDetection(
    detection: Pick<RadarDetection, 'id' | 'instrument_id' | 'instrument_symbol' | 'timeframe'>,
  ) {
    pendingChartDetection.value = {
      detectionId: detection.id,
      instrumentId: detection.instrument_id,
      instrumentSymbol: detection.instrument_symbol.toUpperCase(),
      timeframe: detection.timeframe as Timeframe,
    }
  }

  function consumeChartDetectionForInstrument(instrumentId: number, instrumentSymbol: string) {
    const pending = pendingChartDetection.value
    if (!pending) return null
    if (pending.instrumentId !== instrumentId) return null
    if (pending.instrumentSymbol !== instrumentSymbol.toUpperCase()) return null
    pendingChartDetection.value = null
    return pending.detectionId
  }

  function clearPendingChartDetection() {
    pendingChartDetection.value = null
  }

  async function loadInstrumentHistory(instrumentId: number, timeframe: Timeframe, limit = 150) {
    selectedInstrumentHistory.value = await api.get<RadarDetection[]>(
      `/radar/instruments/${instrumentId}/history`,
      { timeframe, limit },
    )
    return selectedInstrumentHistory.value
  }

  async function loadOutcomeSummary(timeframe: Timeframe) {
    outcomeSummary.value = await api.get<RadarOutcomeSummary[]>('/radar/outcomes/summary', {
      timeframe,
    })
    return outcomeSummary.value
  }

  async function addDetectionToWatchlist(detectionId: number, watchlistId?: number | null) {
    return api.post<RadarWatchlistAction>(
      `/radar/detections/${detectionId}/actions/add-to-watchlist`,
      watchlistId != null ? { watchlist_id: watchlistId } : {},
    )
  }

  async function createDetectionPriceAlert(detectionId: number) {
    return api.post<PriceAlert>(`/radar/detections/${detectionId}/actions/create-price-alert`, {})
  }

  function focusChartDetection(id: number) {
    focusedChartDetectionId.value = id
    if (!activeChartDetectionIds.value.includes(id)) {
      activeChartDetectionIds.value = [...activeChartDetectionIds.value, id]
    }
  }

  function toggleChartDetection(id: number) {
    if (activeChartDetectionIds.value.includes(id)) {
      activeChartDetectionIds.value = activeChartDetectionIds.value.filter(activeId => activeId !== id)
      if (focusedChartDetectionId.value === id) {
        focusedChartDetectionId.value = activeChartDetectionIds.value[0] ?? null
      }
      return
    }

    activeChartDetectionIds.value = [...activeChartDetectionIds.value, id]
    focusedChartDetectionId.value = id
  }

  function isChartDetectionActive(id: number) {
    return activeChartDetectionIds.value.includes(id)
  }

  return {
    runs,
    detections,
    selectedDetection,
    savedViews,
    chartDetections,
    activeChartDetectionIds,
    focusedChartDetectionId,
    pendingChartDetection,
    selectedInstrumentHistory,
    outcomeSummary,
    isLoading,
    loadSavedViews,
    saveView,
    deleteView,
    loadRuns,
    loadDetections,
    loadDetection,
    runScan,
    loadChartDetections,
    clearChartDetections,
    queueChartDetection,
    consumeChartDetectionForInstrument,
    clearPendingChartDetection,
    loadInstrumentHistory,
    loadOutcomeSummary,
    addDetectionToWatchlist,
    createDetectionPriceAlert,
    focusChartDetection,
    toggleChartDetection,
    isChartDetectionActive,
  }
})
