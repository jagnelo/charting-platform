import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '@/lib/api'
import type { RadarDetection, RadarRun } from '@/types'


export const useRadarStore = defineStore('radar', () => {
  const runs = ref<RadarRun[]>([])
  const detections = ref<RadarDetection[]>([])
  const selectedDetection = ref<RadarDetection | null>(null)
  const chartDetections = ref<RadarDetection[]>([])
  const isLoading = ref(false)
  const overlayEnabled = ref(true)

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

  async function loadChartDetections(instrumentId: number, detectionId?: number | null) {
    chartDetections.value = await api.get<RadarDetection[]>(
      `/radar/instruments/${instrumentId}/overlays`,
      { detection_id: detectionId ?? undefined, fresh_only: true },
    )
    overlayEnabled.value = true
    return chartDetections.value
  }

  function clearChartDetections() {
    chartDetections.value = []
  }

  function setOverlayEnabled(enabled: boolean) {
    overlayEnabled.value = enabled
  }

  return {
    runs,
    detections,
    selectedDetection,
    chartDetections,
    isLoading,
    overlayEnabled,
    loadRuns,
    loadDetections,
    loadDetection,
    runScan,
    loadChartDetections,
    clearChartDetections,
    setOverlayEnabled,
  }
})
