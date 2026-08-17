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
  marketMap?: {
    followedSourceIds?: string[]
    pinnedSourceIds?: string[]
  }
}

export const useUserSettingsStore = defineStore('userSettings', () => {
  const showCurrentPriceProjection = ref(false)
  const showHighLowProjection = ref(false)
  const showApproxVolumeProfile = ref(false)
  const chartType = ref<ChartBarType>('candles')
  const followedSourceIds = ref<string[]>([])
  const pinnedSourceIds = ref<string[]>([])
  const loaded = ref(false)
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  function sourceIds(value: unknown): string[] {
    if (!Array.isArray(value)) return []
    return [...new Set(value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0))]
  }

  async function loadSettings() {
    if (loaded.value) return
    const settings = await api.get<UserSettings>('/auth/settings')
    showCurrentPriceProjection.value = !!settings.chart?.showCurrentPriceProjection
    showHighLowProjection.value = !!settings.chart?.showHighLowProjection
    showApproxVolumeProfile.value = !!settings.chart?.showApproxVolumeProfile
    const saved = settings.chart?.chartType
    chartType.value = saved && VALID_BAR_TYPES.includes(saved) ? saved : 'candles'
    followedSourceIds.value = sourceIds(settings.marketMap?.followedSourceIds)
    pinnedSourceIds.value = sourceIds(settings.marketMap?.pinnedSourceIds)
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
        marketMap: {
          followedSourceIds: followedSourceIds.value,
          pinnedSourceIds: pinnedSourceIds.value,
        },
      },
    })
  }

  function toggleSourceId(target: typeof followedSourceIds, sourceId: string) {
    const normalized = sourceId.trim()
    if (!normalized) return
    target.value = target.value.includes(normalized)
      ? target.value.filter(item => item !== normalized)
      : [...target.value, normalized]
  }

  function toggleFollowedSource(sourceId: string) {
    toggleSourceId(followedSourceIds, sourceId)
  }

  function togglePinnedSource(sourceId: string) {
    toggleSourceId(pinnedSourceIds, sourceId)
  }

  watch([showCurrentPriceProjection, showHighLowProjection, showApproxVolumeProfile, chartType, followedSourceIds, pinnedSourceIds], () => {
    if (!loaded.value) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => { saveSettings().catch(console.error) }, 350)
  })

  return {
    showCurrentPriceProjection,
    showHighLowProjection,
    showApproxVolumeProfile,
    chartType,
    followedSourceIds,
    pinnedSourceIds,
    toggleFollowedSource,
    togglePinnedSource,
    loadSettings,
    saveSettings,
  }
})
