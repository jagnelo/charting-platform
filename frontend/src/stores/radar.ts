import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/lib/api'
import type { RadarDetection, RadarRun } from '@/types'

interface PendingChartDetection {
  detectionId: number
  instrumentId: number
  instrumentSymbol: string
}

const RADAR_SETUP_SEQUENCE_PRIORITY: Record<string, number> = {
  approaching_support: 0,
  approaching_resistance: 0,
  rejection: 1,
  reclaim: 1,
  breakout: 2,
  breakdown: 2,
}

function compareRadarChronology(left: RadarDetection, right: RadarDetection) {
  const leftSignalTime = left.evidence?.metrics?.signal_time
  const rightSignalTime = right.evidence?.metrics?.signal_time
  const leftTime = typeof leftSignalTime === 'number'
    ? leftSignalTime * 1000
    : new Date(left.observed_at).getTime()
  const rightTime = typeof rightSignalTime === 'number'
    ? rightSignalTime * 1000
    : new Date(right.observed_at).getTime()
  if (Number.isFinite(leftTime) && Number.isFinite(rightTime) && leftTime !== rightTime) {
    return leftTime - rightTime
  }
  const priorityDelta =
    (RADAR_SETUP_SEQUENCE_PRIORITY[left.setup_type] ?? 99)
    - (RADAR_SETUP_SEQUENCE_PRIORITY[right.setup_type] ?? 99)
  if (priorityDelta !== 0) {
    return priorityDelta
  }
  return left.id - right.id
}

export const useRadarStore = defineStore('radar', () => {
  const runs = ref<RadarRun[]>([])
  const detections = ref<RadarDetection[]>([])
  const selectedDetection = ref<RadarDetection | null>(null)
  const chartDetections = ref<RadarDetection[]>([])
  const activeChartDetectionIds = ref<number[]>([])
  const focusedChartDetectionId = ref<number | null>(null)
  const pendingChartDetection = ref<PendingChartDetection | null>(null)
  const isLoading = ref(false)

  async function loadRuns(limit = 5) {
    runs.value = await api.get<RadarRun[]>('/radar/runs', { limit })
  }

  async function loadDetections(params: {
    setup_type?: string
    min_score?: number
    symbol?: string
    limit?: number
    fresh_only?: boolean
  } = {}) {
    isLoading.value = true
    try {
      detections.value = await api.get<RadarDetection[]>('/radar/detections', params)
    } finally {
      isLoading.value = false
    }
  }

  async function loadDetection(id: number) {
    selectedDetection.value = await api.get<RadarDetection>(`/radar/detections/${id}`)
    return selectedDetection.value
  }

  async function runScan() {
    const run = await api.post<RadarRun>('/radar/run', {})
    await loadRuns()
    return run
  }

  async function loadChartDetections(instrumentId: number, preferredDetectionId?: number | null) {
    const loadedDetections = await api.get<RadarDetection[]>(
      `/radar/instruments/${instrumentId}/overlays`,
      { fresh_only: true },
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

  function queueChartDetection(detection: Pick<RadarDetection, 'id' | 'instrument_id' | 'instrument_symbol'>) {
    pendingChartDetection.value = {
      detectionId: detection.id,
      instrumentId: detection.instrument_id,
      instrumentSymbol: detection.instrument_symbol.toUpperCase(),
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
    chartDetections,
    activeChartDetectionIds,
    focusedChartDetectionId,
    pendingChartDetection,
    isLoading,
    loadRuns,
    loadDetections,
    loadDetection,
    runScan,
    loadChartDetections,
    clearChartDetections,
    queueChartDetection,
    consumeChartDetectionForInstrument,
    clearPendingChartDetection,
    focusChartDetection,
    toggleChartDetection,
    isChartDetectionActive,
  }
})
