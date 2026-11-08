import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { IndicatorPreset, IndicatorConfig } from '@/types'
import { api, setQueuedApiRequestPriority, type ApiRequestPriority } from '@/lib/api'

export const usePresetsStore = defineStore('presets', () => {
  const presets = ref<IndicatorPreset[]>([])
  let pendingPresetLoad: Promise<void> | null = null

  async function loadPresets(priority: ApiRequestPriority = 'auto') {
    if (pendingPresetLoad) {
      if (priority === 'high') setQueuedApiRequestPriority('presets:list', 'high')
      return pendingPresetLoad
    }
    let request!: Promise<void>
    request = (async () => { try {
      presets.value = await api.get('/presets', undefined, { priority, queueKey: 'presets:list' })
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e ?? '')
      if (/Failed to fetch|ERR_ABORTED|Authentication required/i.test(message)) {
        presets.value = []
        return
      }
      throw e
    } })().finally(() => {
      if (pendingPresetLoad === request) pendingPresetLoad = null
    })
    pendingPresetLoad = request
    return request
  }

  async function savePreset(name: string, indicators: IndicatorConfig[], isDefault = false): Promise<IndicatorPreset> {
    const created = await api.post<IndicatorPreset>('/presets', { name, indicators, is_default: isDefault })
    presets.value.push(created)
    return created
  }

  async function updatePreset(id: number, patch: Partial<IndicatorPreset>) {
    const updated = await api.patch<IndicatorPreset>(`/presets/${id}`, patch)
    const idx = presets.value.findIndex(p => p.id === id)
    if (idx !== -1) presets.value[idx] = updated
    return updated
  }

  async function deletePreset(id: number) {
    await api.delete(`/presets/${id}`)
    presets.value = presets.value.filter(p => p.id !== id)
  }

  function getDefault(): IndicatorPreset | null {
    return presets.value.find(p => p.is_default) ?? null
  }

  return { presets, loadPresets, savePreset, updatePreset, deletePreset, getDefault }
})
