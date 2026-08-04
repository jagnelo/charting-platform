import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { AlertFiringEvent, PriceAlert, IndicatorAlert, AlertCondition } from '@/types'
import { api } from '@/lib/api'

export interface IndicatorAlertCreate {
  instrument_id: number
  timeframe: string
  indicator_a_type: string
  indicator_a_params: Record<string, unknown>
  condition: string
  threshold_value?: number
  indicator_b_type?: string
  indicator_b_params?: Record<string, unknown>
  repeat?: boolean
  notes?: string
}

export const useAlertsStore = defineStore('alerts', () => {
  const alerts = ref<PriceAlert[]>([])
  const indicatorAlerts = ref<IndicatorAlert[]>([])
  const firingHistory = ref<AlertFiringEvent[]>([])
  const wsConnected = ref(false)
  const selectedAlertId = ref<number | null>(null)
  const editRequestAlertId = ref<number | null>(null)
  let ws: WebSocket | null = null
  let _loadedInstrumentId: number | undefined = undefined

  async function loadAlerts(instrumentId?: number) {
    // Skip fetch if we already have alerts loaded for this instrument
    if (instrumentId !== undefined && instrumentId === _loadedInstrumentId) return
    _loadedInstrumentId = instrumentId
    const params: Record<string, any> = {}
    if (instrumentId) params.instrument_id = instrumentId
    alerts.value = await api.get('/alerts/price', params)
    indicatorAlerts.value = await api.get('/alerts/indicator', params)
  }

  async function createAlert(
    instrumentId: number,
    condition: AlertCondition,
    thresholdPrice: number,
    repeat: boolean = false,
    notes?: string,
    priceField: string = 'close',
    withinPercent?: number,
  ): Promise<PriceAlert> {
    const created = await api.post<PriceAlert>('/alerts/price', {
      instrument_id: instrumentId,
      condition,
      threshold_price: thresholdPrice,
      repeat,
      notes,
      price_field: priceField,
      within_percent: withinPercent,
    })
    alerts.value.unshift(created)
    _loadedInstrumentId = undefined  // invalidate cache so a future loadAlerts re-fetches
    return created
  }

  async function updateAlert(id: number, patch: Partial<{ repeat: boolean; show_projection: boolean; notes: string; status: string }>) {
    const updated = await api.patch<PriceAlert>(`/alerts/price/${id}`, patch)
    const idx = alerts.value.findIndex(a => a.id === id)
    if (idx !== -1) alerts.value[idx] = updated
  }

  async function deleteAlert(id: number) {
    await api.delete(`/alerts/price/${id}`)
    alerts.value = alerts.value.filter(a => a.id !== id)
    _loadedInstrumentId = undefined
  }

  async function rearmAlert(id: number) {
    const updated = await api.post<PriceAlert>(`/alerts/price/${id}/rearm`, {})
    const idx = alerts.value.findIndex(a => a.id === id)
    if (idx !== -1) alerts.value[idx] = updated
  }

  async function createIndicatorAlert(body: IndicatorAlertCreate) {
    const created = await api.post<IndicatorAlert>('/alerts/indicator', body)
    indicatorAlerts.value.unshift(created)
    _loadedInstrumentId = undefined
  }

  async function updateIndicatorAlert(id: number, patch: Partial<{ repeat: boolean; notes: string; status: string }>) {
    const updated = await api.patch<IndicatorAlert>(`/alerts/indicator/${id}`, patch)
    const idx = indicatorAlerts.value.findIndex(a => a.id === id)
    if (idx !== -1) indicatorAlerts.value[idx] = updated
  }

  async function deleteIndicatorAlert(id: number) {
    await api.delete(`/alerts/indicator/${id}`)
    indicatorAlerts.value = indicatorAlerts.value.filter(a => a.id !== id)
    _loadedInstrumentId = undefined
  }

  async function rearmIndicatorAlert(id: number) {
    const updated = await api.post<IndicatorAlert>(`/alerts/indicator/${id}/rearm`, {})
    const idx = indicatorAlerts.value.findIndex(a => a.id === id)
    if (idx !== -1) indicatorAlerts.value[idx] = updated
  }

  // ── Firing history ──────────────────────────────────────────────────────────

  async function loadHistory(opts: { instrumentId?: number; unviewedOnly?: boolean } = {}) {
    const params: Record<string, any> = { limit: 200 }
    if (opts.instrumentId) params.instrument_id = opts.instrumentId
    if (opts.unviewedOnly) params.unviewed_only = true
    firingHistory.value = await api.get('/alerts/history', params)
  }

  async function loadInstrumentHistory(instrumentId: number): Promise<AlertFiringEvent[]> {
    return api.get<AlertFiringEvent[]>(`/alerts/history/instrument/${instrumentId}`)
  }

  async function markViewed(id: number) {
    const updated = await api.patch<AlertFiringEvent>(`/alerts/history/${id}/view`, {})
    const idx = firingHistory.value.findIndex(e => e.id === id)
    if (idx !== -1) firingHistory.value[idx] = updated
  }

  async function markAllViewed() {
    await api.post('/alerts/history/view-all', {})
    firingHistory.value.forEach(e => { e.is_viewed = true })
  }

  async function deleteFiringEvent(id: number) {
    await api.delete(`/alerts/history/${id}`)
    firingHistory.value = firingHistory.value.filter(e => e.id !== id)
  }

  // ── Computed ────────────────────────────────────────────────────────────────

  // Total active alert count across both types — used by badge
  const totalActiveCount = computed(() =>
    alerts.value.filter(a => a.status === 'active').length +
    indicatorAlerts.value.filter(a => a.status === 'active').length
  )

  const unviewedCount = computed(() =>
    firingHistory.value.filter(e => !e.is_viewed).length
  )

  // Active alerts for a specific instrument (both types)
  function activeCountForInstrument(instrumentId: number): number {
    return alerts.value.filter(a => a.status === 'active' && a.instrument_id === instrumentId).length +
      indicatorAlerts.value.filter(a => a.status === 'active' && a.instrument_id === instrumentId).length
  }

  // ── WebSocket ───────────────────────────────────────────────────────────────

  function connectWebSocket() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const accessToken = localStorage.getItem('access_token')
    const tokenQuery = accessToken ? `?token=${encodeURIComponent(accessToken)}` : ''
    const wsUrl = `${protocol}://${window.location.host}/api/v1/alerts/ws${tokenQuery}`
    ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      wsConnected.value = true
      // Ping every 30s to keep connection alive
      setInterval(() => ws?.send(JSON.stringify({ type: 'ping' })), 30000)
      // Fetch unviewed count on reconnect
      loadHistory().catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : String(e ?? '')
        if (/Authentication required/i.test(msg)) return
        console.error(e)
      })
    }

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.type === 'screener_alert_triggered') {
        showAlertToast({
          ...msg,
          symbol: msg.screener_name ?? `Scan #${msg.screener_id}`,
          condition: `${msg.trigger_type} · ${msg.entered_ids?.length ?? 0} entered · ${msg.left_ids?.length ?? 0} left`,
          alert_kind: 'screener',
        })
      } else if (msg.type === 'alert_triggered') {
        if (msg.alert_kind === 'indicator') {
          const alert = indicatorAlerts.value.find(a => a.id === msg.alert_id)
          if (alert) {
            alert.status = 'triggered'
            alert.triggered_at = msg.triggered_at
            alert.last_value_a = msg.value_a
            alert.last_value_b = msg.value_b
          }
        } else {
          const alert = alerts.value.find(a => a.id === msg.alert_id)
          if (alert) {
            alert.status = 'triggered'
            alert.triggered_at = msg.triggered_at
            alert.last_known_price = msg.current_price
          }
        }
        // Prepend a stub firing event into history so the badge increments immediately.
        // A full reload is deferred to when the user opens the history panel.
        if (msg.firing_event_id) {
          const stub: AlertFiringEvent = {
            id: msg.firing_event_id,
            instrument_id: null,
            instrument_symbol: msg.symbol ?? null,
            alert_type: msg.alert_kind ?? 'price',
            alert_id: msg.alert_id ?? 0,
            fired_at: msg.triggered_at ?? new Date().toISOString(),
            trigger_value: msg.current_price ?? msg.value_a ?? null,
            condition_snapshot: {
              condition: msg.condition,
              threshold: msg.threshold,
              symbol: msg.symbol,
            },
            is_viewed: false,
            created_at: msg.triggered_at ?? new Date().toISOString(),
          }
          firingHistory.value.unshift(stub)
        }
        showAlertToast(msg)
      }
    }

    ws.onclose = () => {
      wsConnected.value = false
      // Reconnect after 5 seconds
      setTimeout(connectWebSocket, 5000)
    }

    ws.onerror = () => {
      ws?.close()
    }
  }

  function showAlertToast(msg: any) {
    // Dispatch a custom event that the Notification component listens to
    window.dispatchEvent(new CustomEvent('chart:alert-triggered', { detail: msg }))
  }

  function disconnectWebSocket() {
    ws?.close()
    ws = null
  }

  function getAlertProjection(id: number): boolean {
    return alerts.value.find(a => a.id === id)?.show_projection ?? false
  }

  function toggleAlertProjection(id: number) {
    updateAlert(id, { show_projection: !getAlertProjection(id) }).catch(console.error)
  }

  function selectAlert(id: number | null) { selectedAlertId.value = id }
  function requestEditAlert(id: number | null) { editRequestAlertId.value = id }

  return {
    alerts, indicatorAlerts, firingHistory, wsConnected,
    totalActiveCount, unviewedCount,
    selectedAlertId, editRequestAlertId,
    loadAlerts, createAlert, createIndicatorAlert,
    updateAlert, updateIndicatorAlert,
    deleteAlert, rearmAlert,
    deleteIndicatorAlert, rearmIndicatorAlert,
    activeCountForInstrument,
    loadHistory, loadInstrumentHistory,
    markViewed, markAllViewed, deleteFiringEvent,
    selectAlert, requestEditAlert,
    getAlertProjection, toggleAlertProjection,
    connectWebSocket, disconnectWebSocket,
  }
})
