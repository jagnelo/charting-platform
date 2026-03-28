import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { PriceAlert, AlertCondition } from '@/types'
import { api } from '@/lib/api'

export interface IndicatorAlertCreate {
  instrument_id: number
  timeframe: string
  indicator_a_type: string
  indicator_a_params: Record<string, number>
  condition: string
  threshold_value?: number
  indicator_b_type?: string
  indicator_b_params?: Record<string, number>
  repeat?: boolean
  notes?: string
}

export const useAlertsStore = defineStore('alerts', () => {
  const alerts = ref<PriceAlert[]>([])
  const wsConnected = ref(false)
  let ws: WebSocket | null = null

  async function loadAlerts(instrumentId?: number) {
    const params: Record<string, any> = {}
    if (instrumentId) params.instrument_id = instrumentId
    alerts.value = await api.get('/alerts/price', params)
  }

  async function createAlert(
    instrumentId: number,
    condition: AlertCondition,
    thresholdPrice: number,
    repeat: boolean = false,
    notes?: string,
  ): Promise<PriceAlert> {
    const created = await api.post<PriceAlert>('/alerts/price', {
      instrument_id: instrumentId,
      condition,
      threshold_price: thresholdPrice,
      repeat,
      notes,
    })
    alerts.value.unshift(created)
    return created
  }

  async function deleteAlert(id: number) {
    await api.delete(`/alerts/price/${id}`)
    alerts.value = alerts.value.filter(a => a.id !== id)
  }

  async function rearmAlert(id: number) {
    const updated = await api.post<PriceAlert>(`/alerts/price/${id}/rearm`, {})
    const idx = alerts.value.findIndex(a => a.id === id)
    if (idx !== -1) alerts.value[idx] = updated
  }

  async function createIndicatorAlert(body: IndicatorAlertCreate) {
    await api.post('/alerts/indicator', body)
    // Indicator alerts are not in the price alerts list — no local state update needed
  }

  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const wsUrl = `${protocol}://${window.location.host}/api/v1/alerts/ws`
    ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      wsConnected.value = true
      // Ping every 30s to keep connection alive
      setInterval(() => ws?.send(JSON.stringify({ type: 'ping' })), 30000)
    }

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.type === 'alert_triggered') {
        // Update the alert status in our local list
        const alert = alerts.value.find(a => a.id === msg.alert_id)
        if (alert) {
          alert.status = 'triggered'
          alert.triggered_at = msg.triggered_at
          alert.last_known_price = msg.current_price
        }
        // Show in-app toast
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

  return {
    alerts, wsConnected,
    loadAlerts, createAlert, createIndicatorAlert, deleteAlert, rearmAlert,
    connectWebSocket, disconnectWebSocket,
  }
})
