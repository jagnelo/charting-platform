import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ChartView from '@/views/ChartView.vue'
import { useAlertsStore } from '@/stores/alerts'
import { useChartStore } from '@/stores/chart'
import { useDrawingsStore } from '@/stores/drawings'
import { useLayoutStore } from '@/stores/layout'
import { useOptionsExposureStore } from '@/stores/optionsExposure'
import { usePresetsStore } from '@/stores/presets'
import { useRadarStore } from '@/stores/radar'

const route = {
  params: { symbol: '' },
  query: {},
  path: '/chart',
}

const replace = vi.fn()
const push = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({
    replace,
    push,
  }),
}))

async function flushPromises() {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
}

describe('ChartView radar handoff', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
    replace.mockReset()
    push.mockReset()
    route.params.symbol = ''
    route.query = {}
    route.path = '/chart'
  })

  it('keeps the preferred radar detection selected when arriving from the radar page', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const chartStore = useChartStore()
    const drawStore = useDrawingsStore()
    const alertsStore = useAlertsStore()
    const layoutStore = useLayoutStore()
    const optionsExposureStore = useOptionsExposureStore()
    const presetsStore = usePresetsStore()
    const radarStore = useRadarStore()

    layoutStore.layout = '1'

    const loadBarsSpy = vi.spyOn(chartStore, 'loadBars').mockImplementation(async (symbol: string) => {
      chartStore.symbol = symbol
      chartStore.instrument = {
        id: 7,
        symbol,
        name: 'Tesla',
        is_active: true,
        currency: 'USD',
      }
      chartStore.bars = [
        {
          ts: '2026-05-05T14:30:00Z',
          open: 100,
          high: 105,
          low: 99,
          close: 103,
          is_adjusted: true,
        },
      ]
    })
    vi.spyOn(drawStore, 'loadDrawings').mockImplementation(async () => {})
    vi.spyOn(alertsStore, 'loadAlerts').mockImplementation(async () => {})
    vi.spyOn(optionsExposureStore, 'load').mockImplementation(async () => {})
    vi.spyOn(optionsExposureStore, 'reset').mockImplementation(() => {})
    vi.spyOn(presetsStore, 'loadPresets').mockImplementation(async () => {})
    vi.spyOn(presetsStore, 'getDefault').mockImplementation(() => null)
    radarStore.queueChartDetection({
      id: 42,
      instrument_id: 7,
      instrument_symbol: 'TSLA',
      timeframe: 'D1',
    })
    const loadChartDetectionsSpy = vi.spyOn(radarStore, 'loadChartDetections').mockImplementation(async (_instrumentId: number, _timeframe: string, preferredDetectionId?: number | null) => {
      radarStore.chartDetections = [
        {
          id: 42,
          run_id: 1,
          instrument_id: 7,
          instrument_symbol: 'TSLA',
          instrument_name: 'Tesla',
          timeframe: 'D1',
          setup_type: 'rejection',
          state: 'confirmed',
          score: 0.8,
          observed_at: '2026-05-05T00:00:00Z',
          fresh_until: '2026-05-10T00:00:00Z',
          key_level_price: 103,
          summary: 'Rejected resistance',
          invalidation_hint: 'Close above resistance',
          score_factors: { normalized_score: 0.8 },
          outcome_status: 'open',
          outcome_last_evaluated_at: '2026-05-05T00:00:00Z',
          bars_since_signal: 0,
          max_favorable_excursion_pct: null,
          max_adverse_excursion_pct: null,
          target_hit_at: null,
          invalidated_at: null,
          created_at: '2026-05-05T00:00:05Z',
          updated_at: '2026-05-05T00:00:05Z',
          evidence: { overlays: [], metrics: {}, structures: [] },
        },
      ]
      radarStore.activeChartDetectionIds = preferredDetectionId != null ? [preferredDetectionId] : []
      radarStore.focusedChartDetectionId = preferredDetectionId ?? null
      return radarStore.chartDetections
    })

    const wrapper = mount(ChartView, {
      global: {
        plugins: [pinia],
        stubs: {
          SearchBar: { template: '<div />' },
          TimeframeSelector: { template: '<div />' },
          LayoutPicker: { template: '<div />' },
          DrawingToolbar: { template: '<div />' },
          IndicatorPanel: { template: '<div />' },
          WatchlistPanel: { template: '<div />' },
          ResizeHandle: { template: '<div />' },
          TextPromptModal: { template: '<div />' },
          OptionsChainPanel: { template: '<div />' },
          OptionsExposurePanel: { template: '<div />' },
          MultiChartLayout: { template: '<div />' },
          UPlotChart: { template: '<div />' },
        },
      },
    })

    await flushPromises()
    await (wrapper.vm as unknown as { onSymbolSelect: (symbol: string) => Promise<void> }).onSymbolSelect('TSLA')
    await flushPromises()

    expect(loadBarsSpy).toHaveBeenCalledWith('TSLA', 'D1')
    expect(loadChartDetectionsSpy).toHaveBeenCalledTimes(1)
    expect(loadChartDetectionsSpy).toHaveBeenCalledWith(7, 'D1', 42)
    expect(radarStore.activeChartDetectionIds).toEqual([42])
    expect(radarStore.focusedChartDetectionId).toBe(42)
  })
})
