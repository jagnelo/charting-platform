import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ChartDrawing, DrawingType, Timeframe } from '@/types'
import type { AnyDrawing } from '@/lib/drawings/types'
import { api } from '@/lib/api'

export const useDrawingsStore = defineStore('drawings', () => {
  const drawings = ref<ChartDrawing[]>([])
  const activeToolType = ref<DrawingType | null>(null)
  const avwapDropActive = ref(false)
  const selectedId = ref<number | null>(null)
  const editRequestId = ref<number | null>(null)
  const instrumentId = ref<number | null>(null)
  const currentTimeframe = ref<Timeframe | null>(null)

  function renderableDrawingsFor(indicatorKey: string | null): AnyDrawing[] {
    return [...drawings.value].reverse()
      .filter(d => d.is_visible && (d.indicator_key ?? null) === indicatorKey)
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
  }

  // Main-pane drawings only (indicator_key === null).
  // Reversed so that index 0 (top of UI list) is rendered last → highest z-index.
  const renderableDrawings = computed<AnyDrawing[]>(() => renderableDrawingsFor(null))

  async function loadDrawings(instId: number, tf: Timeframe) {
    // A chart tool can still finish its symbol hydration while logout is
    // routing the application away. Do not start a protected request after
    // the token has been cleared, and reset the cache so the next session
    // cannot inherit the previous user's drawings.
    if (!localStorage.getItem('access_token')) {
      drawings.value = []
      instrumentId.value = null
      currentTimeframe.value = null
      return
    }
    // Skip fetch if we already have this instrument's drawings loaded
    if (instrumentId.value === instId) {
      currentTimeframe.value = tf
      return
    }
    instrumentId.value = instId
    currentTimeframe.value = tf
    try {
      // No timeframe filter — drawings belong to the symbol, not a specific timeframe.
      // The creation timeframe is stored as metadata only.
      drawings.value = await api.get('/drawings', { instrument_id: instId })
    } catch (e) {
      // Logout can invalidate an in-flight request after the fetch has been
      // issued. That is an expected auth-boundary race, not a drawing failure
      // and must not surface as a console error during redirect.
      if (e instanceof Error && e.message === 'Authentication required') return
      console.error('Failed to load drawings', e)
    }
  }

  async function saveDrawing(drawing: AnyDrawing, pinToAll = false, indicatorKey: string | null = null): Promise<ChartDrawing | null> {
    if (!instrumentId.value) return null
    const { points, style, type, label, isSelected, isLocked, ...rest } = drawing
    try {
      const saved = await api.post<ChartDrawing>('/drawings', {
        instrument_id: instrumentId.value,
        timeframe: pinToAll ? null : currentTimeframe.value,
        pin_to_all: pinToAll,
        indicator_key: indicatorKey,
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

  function requestEditDrawing(id: number | null) {
    editRequestId.value = id
  }

  function setActiveTool(tool: DrawingType | null) {
    activeToolType.value = tool
    avwapDropActive.value = false
    selectedId.value = null
  }

  function setAvwapDrop(active: boolean) {
    avwapDropActive.value = active
    if (active) activeToolType.value = null
    selectedId.value = null
  }

  async function reorderDrawings(ids: number[]) {
    // Optimistically reorder locally
    const byId = Object.fromEntries(drawings.value.map(d => [d.id, d]))
    const reordered = ids.map(id => byId[id]).filter(Boolean)
    const rest = drawings.value.filter(d => !ids.includes(d.id))
    drawings.value = [...reordered, ...rest]
    try {
      await api.post('/drawings/reorder', { ids })
    } catch (e) {
      console.error('Failed to reorder drawings', e)
    }
  }

  const drawingProjections = computed(() =>
    drawings.value.map(d => `${d.id}:${!!(d.data as any)?.showProjection}`).join('|')
  )

  function getDrawingProjection(id: number): boolean {
    const drawing = drawings.value.find(d => d.id === id)
    return !!(drawing?.data as any)?.showProjection
  }

  function toggleDrawingProjection(id: number) {
    const drawing = drawings.value.find(d => d.id === id)
    if (!drawing) return
    const data = { ...(drawing.data as any), showProjection: !getDrawingProjection(id) }
    localUpdateDrawing(id, { data } as any)
    updateDrawing(id, { data } as any)
  }

  return {
    drawings, activeToolType, avwapDropActive, selectedId, editRequestId, renderableDrawings,
    drawingProjections,
    loadDrawings, saveDrawing, updateDrawing, localUpdateDrawing, deleteDrawing,
    selectDrawing, requestEditDrawing, setActiveTool, setAvwapDrop, reorderDrawings,
    getDrawingProjection, toggleDrawingProjection, renderableDrawingsFor,
  }
})
