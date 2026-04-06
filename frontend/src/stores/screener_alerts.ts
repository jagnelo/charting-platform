import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ScreenerAlert, ScreenerAlertTriggerType } from '@/types'
import { api } from '@/lib/api'

export const useScreenerAlertsStore = defineStore('screener_alerts', () => {
  const alerts = ref<ScreenerAlert[]>([])
  const loading = ref(false)

  async function loadAlerts() {
    loading.value = true
    try {
      alerts.value = await api.get<ScreenerAlert[]>('/alerts/screener')
    } catch (e) {
      console.error('Failed to load screener alerts', e)
    } finally {
      loading.value = false
    }
  }

  async function createAlert(
    screenerId: number,
    triggerType: ScreenerAlertTriggerType = 'both',
    repeat = false,
    notes?: string,
  ): Promise<ScreenerAlert | null> {
    try {
      const created = await api.post<ScreenerAlert>('/alerts/screener', {
        screener_id: screenerId,
        trigger_type: triggerType,
        repeat,
        notes,
      })
      alerts.value.unshift(created)
      return created
    } catch (e) {
      console.error('Failed to create screener alert', e)
      return null
    }
  }

  async function updateAlert(
    id: number,
    patch: Partial<{ trigger_type: ScreenerAlertTriggerType; repeat: boolean; notes: string; status: string }>,
  ): Promise<void> {
    try {
      const updated = await api.patch<ScreenerAlert>(`/alerts/screener/${id}`, patch)
      const idx = alerts.value.findIndex(a => a.id === id)
      if (idx !== -1) alerts.value[idx] = updated
    } catch (e) {
      console.error('Failed to update screener alert', e)
    }
  }

  async function rearmAlert(id: number): Promise<void> {
    try {
      const updated = await api.post<ScreenerAlert>(`/alerts/screener/${id}/rearm`, {})
      const idx = alerts.value.findIndex(a => a.id === id)
      if (idx !== -1) alerts.value[idx] = updated
    } catch (e) {
      console.error('Failed to rearm screener alert', e)
    }
  }

  async function deleteAlert(id: number): Promise<void> {
    try {
      await api.delete(`/alerts/screener/${id}`)
      alerts.value = alerts.value.filter(a => a.id !== id)
    } catch (e) {
      console.error('Failed to delete screener alert', e)
    }
  }

  /** Return the alert (if any) for a given screener id */
  function forScreener(screenerId: number): ScreenerAlert | undefined {
    return alerts.value.find(a => a.screener_id === screenerId)
  }

  return {
    alerts,
    loading,
    loadAlerts,
    createAlert,
    updateAlert,
    rearmAlert,
    deleteAlert,
    forScreener,
  }
})
