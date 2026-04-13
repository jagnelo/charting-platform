import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { api } from '@/lib/api'

interface ChartSettings {
  showCurrentPriceProjection?: boolean
  showHighLowProjection?: boolean
  chartType?: 'candles' | 'line'
}

interface UserSettings {
  chart?: ChartSettings
}

export const useUserSettingsStore = defineStore('userSettings', () => {
  const showCurrentPriceProjection = ref(false)
  const showHighLowProjection = ref(false)
  const chartType = ref<'candles' | 'line'>('candles')
  const loaded = ref(false)
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  async function loadSettings() {
    const settings = await api.get<UserSettings>('/auth/settings')
    showCurrentPriceProjection.value = !!settings.chart?.showCurrentPriceProjection
    showHighLowProjection.value = !!settings.chart?.showHighLowProjection
    chartType.value = settings.chart?.chartType === 'line' ? 'line' : 'candles'
    loaded.value = true
  }

  async function saveSettings() {
    await api.patch('/auth/settings', {
      settings: {
        chart: {
          showCurrentPriceProjection: showCurrentPriceProjection.value,
          showHighLowProjection: showHighLowProjection.value,
          chartType: chartType.value,
        },
      },
    })
  }

  watch([showCurrentPriceProjection, showHighLowProjection, chartType], () => {
    if (!loaded.value) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => { saveSettings().catch(console.error) }, 350)
  })

  return {
    showCurrentPriceProjection,
    showHighLowProjection,
    chartType,
    loadSettings,
    saveSettings,
  }
})
