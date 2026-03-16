import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { IndicatorPreset, IndicatorConfig } from '@/types'
import { api } from '@/lib/api'

export const usePresetsStore = defineStore('presets', () => {
  const presets = ref<IndicatorPreset[]>([])

  async function loadPresets() {
    presets.value = await api.get('/presets')
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
