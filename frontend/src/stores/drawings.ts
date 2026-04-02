import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ChartDrawing, DrawingType, Timeframe } from '@/types'
import type { AnyDrawing } from '@/lib/drawings/types'
import { api } from '@/lib/api'

export const useDrawingsStore = defineStore('drawings', () => {
  const drawings = ref<ChartDrawing[]>([])
  const activeToolType = ref<DrawingType | null>(null)
  const selectedId = ref<number | null>(null)
  const instrumentId = ref<number | null>(null)
  const currentTimeframe = ref<Timeframe | null>(null)

  // Convert server drawings to renderer-friendly format
  const renderableDrawings = computed<AnyDrawing[]>(() =>
    drawings.value
      .filter(d => d.is_visible)
      .map(d => ({
        id: d.id,
        type: d.drawing_type as DrawingType,
        points: (d.data as any).points ?? [],
        style: d.style,
        label: d.label,
        isSelected: d.id === selectedId.value,
        isLocked: d.is_locked,
        isVisible: d.is_visible,
        ...(d.data as any),
      }))
  )

  async function loadDrawings(instId: number, tf: Timeframe) {
    instrumentId.value = instId
    currentTimeframe.value = tf
    try {
      drawings.value = await api.get('/drawings', { instrument_id: instId, timeframe: tf })
    } catch (e) {
      console.error('Failed to load drawings', e)
    }
  }

  async function saveDrawing(drawing: AnyDrawing, pinToAll = false): Promise<ChartDrawing | null> {
    if (!instrumentId.value) return null
    const { points, style, type, label, isSelected, isLocked, ...rest } = drawing
    try {
      const saved = await api.post<ChartDrawing>('/drawings', {
        instrument_id: instrumentId.value,
        timeframe: pinToAll ? null : currentTimeframe.value,
        pin_to_all: pinToAll,
        drawing_type: type,
        label: label,
        data: { points, ...rest },
        style,
        is_visible: true,
        is_locked: isLocked ?? false,
      })
      drawings.value.push(saved)
      return saved
    } catch (e) {
      console.error('Failed to save drawing', e)
      return null
    }
  }

  async function updateDrawing(id: number, patch: Partial<ChartDrawing>) {
    try {
      const updated = await api.patch<ChartDrawing>(`/drawings/${id}`, patch)
      const idx = drawings.value.findIndex(d => d.id === id)
      if (idx !== -1) drawings.value[idx] = updated
    } catch (e) {
      console.error('Failed to update drawing', e)
    }
  }

  async function deleteDrawing(id: number) {
    try {
      await api.delete(`/drawings/${id}`)
      drawings.value = drawings.value.filter(d => d.id !== id)
      if (selectedId.value === id) selectedId.value = null
    } catch (e) {
      console.error('Failed to delete drawing', e)
    }
  }

  /** Update a drawing locally (no API call) — used for live coordinate preview in the editor. */
  function localUpdateDrawing(id: number, patch: Partial<ChartDrawing>) {
    const idx = drawings.value.findIndex(d => d.id === id)
    if (idx !== -1) drawings.value[idx] = { ...drawings.value[idx], ...patch }
  }

  function selectDrawing(id: number | null) {
    selectedId.value = id
  }

  function setActiveTool(tool: DrawingType | null) {
    activeToolType.value = tool
    selectedId.value = null
  }

  return {
    drawings, activeToolType, selectedId, renderableDrawings,
    loadDrawings, saveDrawing, updateDrawing, localUpdateDrawing, deleteDrawing,
    selectDrawing, setActiveTool,
  }
})
