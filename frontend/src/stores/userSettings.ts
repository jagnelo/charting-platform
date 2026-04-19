import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { api } from '@/lib/api'
import type { ChartBarType } from '@/types'

const VALID_BAR_TYPES: ChartBarType[] = ['candles','line','ohlc','heikin_ashi','area','baseline','renko','kagi','point_figure']

interface ChartSettings {
  showCurrentPriceProjection?: boolean
  showHighLowProjection?: boolean
  showApproxVolumeProfile?: boolean
  chartType?: ChartBarType
}

interface UserSettings {
  chart?: ChartSettings
}

export const useUserSettingsStore = defineStore('userSettings', () => {
  const showCurrentPriceProjection = ref(false)
  const showHighLowProjection = ref(false)
  const showApproxVolumeProfile = ref(false)
  const chartType = ref<ChartBarType>('candles')
  const loaded = ref(false)
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  async function loadSettings() {
    if (loaded.value) return
    const settings = await api.get<UserSettings>('/auth/settings')
    showCurrentPriceProjection.value = !!settings.chart?.showCurrentPriceProjection
    showHighLowProjection.value = !!settings.chart?.showHighLowProjection
    showApproxVolumeProfile.value = !!settings.chart?.showApproxVolumeProfile
    const saved = settings.chart?.chartType
    chartType.value = saved && VALID_BAR_TYPES.includes(saved) ? saved : 'candles'
    loaded.value = true
  }

  async function saveSettings() {
    await api.patch('/auth/settings', {
      settings: {
        chart: {
          showCurrentPriceProjection: showCurrentPriceProjection.value,
          showHighLowProjection: showHighLowProjection.value,
          showApproxVolumeProfile: showApproxVolumeProfile.value,
          chartType: chartType.value,
        },
      },
    })
  }

  watch([showCurrentPriceProjection, showHighLowProjection, showApproxVolumeProfile, chartType], () => {
    if (!loaded.value) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => { saveSettings().catch(console.error) }, 350)
  })

  return {
    showCurrentPriceProjection,
    showHighLowProjection,
    showApproxVolumeProfile,
    chartType,
    loadSettings,
    saveSettings,
  }
})
