import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, nextTick, watch } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ChartView from '@/views/ChartView.vue'
import { useAlertsStore } from '@/stores/alerts'
import { useChartStore, usePanelStore } from '@/stores/chart'
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

  afterEach(() => vi.unstubAllGlobals())

  function mountDeferredPresetsChart(delaySymbolLoad = false) {
    const pinia = createPinia()
    setActivePinia(pinia)
    const chartStore = useChartStore()
    const p0Store = usePanelStore('p0')
    const p1Store = usePanelStore('p1')
    const drawStore = useDrawingsStore()
    const alertsStore = useAlertsStore()
    const layoutStore = useLayoutStore()
    const optionsExposureStore = useOptionsExposureStore()
    const presetsStore = usePresetsStore()
    const radarStore = useRadarStore()
    layoutStore.layout = '1'
    route.params.symbol = 'SPY'
    route.path = '/chart/SPY'

    let presetsReady = false
    let resolvePresets!: () => void
    const presetsLoaded = new Promise<void>(resolve => { resolvePresets = resolve })
    const defaultIndicators = [{ type: 'sma', params: { period: 20 }, style: { color: '#fff' }, pane: 'main' }] as const
    vi.spyOn(presetsStore, 'loadPresets').mockReturnValue(presetsLoaded)
    vi.spyOn(presetsStore, 'getDefault').mockImplementation(() => (
      presetsReady
        ? { id: 1, name: 'Default', description: null, indicators: [...defaultIndicators], is_default: true, created_at: '', updated_at: '' }
        : null
    ) as any)
    let resolveSymbolLoad!: () => void
    const symbolLoaded = delaySymbolLoad ? new Promise<void>(resolve => { resolveSymbolLoad = resolve }) : null
    const globalLoad = vi.spyOn(chartStore, 'loadBars').mockImplementation(async (symbol: string) => {
      chartStore.symbol = symbol
      if (symbolLoaded) await symbolLoaded
      chartStore.instrument = { id: 1, symbol, name: symbol, is_active: true, currency: 'USD' }
    })
    const p0Load = vi.spyOn(p0Store, 'loadBars').mockImplementation(async (symbol: string) => {
      p0Store.symbol = symbol
    })
    const p1Load = vi.spyOn(p1Store, 'loadBars').mockImplementation(async (symbol: string) => {
      p1Store.symbol = symbol
    })
    const setIndicators = vi.spyOn(chartStore, 'setIndicators')
    vi.spyOn(drawStore, 'loadDrawings').mockImplementation(async () => {})
    vi.spyOn(alertsStore, 'loadAlerts').mockImplementation(async () => {})
    vi.spyOn(optionsExposureStore, 'load').mockImplementation(async () => {})
    vi.spyOn(optionsExposureStore, 'reset').mockImplementation(() => {})
    vi.spyOn(radarStore, 'loadChartDetections').mockImplementation(async () => [])

    const wrapper = mount(ChartView, {
      global: {
        plugins: [pinia],
        stubs: {
          SearchBar: { template: '<div />' },
          TimeframeSelector: { template: '<div />' },
          LayoutPicker: { template: '<div />' },
          DrawingToolbar: { template: '<div />' },
          IndicatorPanel: { template: '<div />' },
          WatchlistPanel: defineComponent({
            props: { compactDefault: { type: Boolean, default: false } },
            template: '<div class="watchlist-panel-stub" :data-compact-default="compactDefault" />',
          }),
          ResizeHandle: { template: '<div />' },
          TextPromptModal: { template: '<div />' },
          OptionsChainPanel: { template: '<div />' },
          OptionsExposurePanel: { template: '<div />' },
          MultiChartLayout: { template: '<div />' },
          UPlotChart: { template: '<div />' },
        },
      },
    })

    return {
      chartStore,
      defaultIndicators,
      globalLoad,
      layoutStore,
      p0Load,
      p1Load,
      releasePresets: () => { presetsReady = true; resolvePresets() },
      releaseSymbolLoad: () => resolveSymbolLoad?.(),
      setIndicators,
      wrapper,
    }
  }

  it('starts both chart rails compact on narrow screens while preserving the visible toggle strip', async () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })))
    const chart = mountDeferredPresetsChart()

    expect(chart.wrapper.get('.watchlist-panel-stub').attributes('data-compact-default')).toBe('true')
    expect(chart.wrapper.get('.chart-body').exists()).toBe(true)
    chart.wrapper.unmount()
  })

  it('keeps the indicator rail geometry across a keyed active-panel switch while the new panel is loading', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const chartStore = useChartStore()
    const p0Store = usePanelStore('p0')
    const p1Store = usePanelStore('p1')
    const layoutStore = useLayoutStore()
    const drawStore = useDrawingsStore()
    const alertsStore = useAlertsStore()
    const optionsExposureStore = useOptionsExposureStore()
    const presetsStore = usePresetsStore()
    layoutStore.layout = '2h'
    p0Store.instrument = { id: 7, symbol: 'SPY', name: 'SPDR S&P 500 ETF', currency: 'USD', is_active: true }
    p1Store.instrument = null
    p1Store.isLoading = true
    vi.spyOn(drawStore, 'loadDrawings').mockResolvedValue(undefined)
    vi.spyOn(alertsStore, 'loadAlerts').mockResolvedValue(undefined)
    vi.spyOn(optionsExposureStore, 'load').mockResolvedValue(undefined)
    vi.spyOn(optionsExposureStore, 'reset').mockImplementation(() => {})
    vi.spyOn(chartStore, 'loadBars').mockResolvedValue(undefined)
    vi.spyOn(presetsStore, 'loadPresets').mockResolvedValue(undefined)

    const IndicatorPanelShellStub = defineComponent({
      props: {
        panelId: { type: String, required: true },
        panelWidth: { type: Number, required: false },
        panelOpen: { type: Boolean, required: true },
      },
      emits: ['instrument-available', 'update:panel-open'],
      setup(props, { emit }) {
        const panelStore = usePanelStore(props.panelId)
        watch(() => panelStore.instrument?.id, (id) => {
          if (id) emit('instrument-available')
        }, { immediate: true })
        return { emit }
      },
      template: `<aside class="indicator-panel-shell" :data-open="panelOpen" :style="panelOpen ? { width: panelWidth + 'px' } : { width: '16px' }"><button @click="emit('update:panel-open', !panelOpen)"></button></aside>`,
    })

    const wrapper = mount(ChartView, {
      global: {
        plugins: [pinia],
        stubs: {
          SearchBar: { template: '<div />' },
          TimeframeSelector: { template: '<div />' },
          LayoutPicker: { template: '<div />' },
          DrawingToolbar: { template: '<div />' },
          IndicatorPanel: IndicatorPanelShellStub,
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
    expect(wrapper.get('.indicator-panel-shell').attributes('data-open')).toBe('true')
    expect(wrapper.get('.indicator-panel-shell').attributes('style')).toContain('width: 220px')

    layoutStore.activePanelId = 'p1'
    await nextTick()
    expect(wrapper.get('.indicator-panel-shell').attributes('data-open')).toBe('true')
    expect(wrapper.get('.indicator-panel-shell').attributes('style')).toContain('width: 220px')

    await wrapper.get('.indicator-panel-shell button').trigger('click')
    await nextTick()
    expect(wrapper.get('.indicator-panel-shell').attributes('data-open')).toBe('false')
    expect(wrapper.get('.indicator-panel-shell').attributes('style')).toContain('width: 16px')

    layoutStore.activePanelId = 'p0'
    await nextTick()
    expect(wrapper.get('.indicator-panel-shell').attributes('data-open')).toBe('false')
    expect(wrapper.get('.indicator-panel-shell').attributes('style')).toContain('width: 16px')
    wrapper.unmount()
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
          evidence: { overlays: [], indicator_visuals: [], drawing_visuals: [], metrics: {}, structures: [] },
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

  it('does not publish detached drawing state after a symbol load finishes', async () => {
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

    let resolveBars!: () => void
    const barsLoaded = new Promise<void>(resolve => {
      resolveBars = resolve
    })
    vi.spyOn(chartStore, 'loadBars').mockImplementation(async (symbol: string) => {
      await barsLoaded
      chartStore.symbol = symbol
      chartStore.instrument = { id: 7, symbol, name: 'Tesla', is_active: true, currency: 'USD' }
    })
    const loadDrawingsSpy = vi.spyOn(drawStore, 'loadDrawings').mockImplementation(async () => {})
    vi.spyOn(alertsStore, 'loadAlerts').mockImplementation(async () => {})
    vi.spyOn(optionsExposureStore, 'load').mockImplementation(async () => {})
    vi.spyOn(optionsExposureStore, 'reset').mockImplementation(() => {})
    vi.spyOn(presetsStore, 'loadPresets').mockImplementation(async () => {})
    vi.spyOn(presetsStore, 'getDefault').mockImplementation(() => null)
    vi.spyOn(radarStore, 'loadChartDetections').mockImplementation(async () => [])

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

    const selection = (wrapper.vm as unknown as { onSymbolSelect: (symbol: string) => Promise<void> }).onSymbolSelect('TSLA')
    await Promise.resolve()
    wrapper.unmount()
    resolveBars()
    await selection

    expect(loadDrawingsSpy).not.toHaveBeenCalled()
  })

  it('starts URL symbol hydration before presets settle so a user layout change retains the symbol', async () => {
    const { globalLoad, layoutStore, p0Load, p1Load, releasePresets, wrapper } = mountDeferredPresetsChart()

    await flushPromises()
    expect(globalLoad).toHaveBeenCalledWith('SPY', 'D1')

    layoutStore.setLayout('2h')
    layoutStore.setActivePanel('p1')
    await flushPromises()
    releasePresets()

    await vi.waitFor(() => {
      expect(p0Load).toHaveBeenCalledWith('SPY', 'D1')
      expect(p1Load).toHaveBeenCalledWith('SPY', 'H4')
    })
    expect(layoutStore.panels.map(panel => panel.symbol)).toEqual(['SPY', 'SPY'])
    wrapper.unmount()
  })

  it('applies a late default once when the bootstrap selection remains untouched', async () => {
    const { chartStore, defaultIndicators, releasePresets, setIndicators, wrapper } = mountDeferredPresetsChart()

    await flushPromises()
    expect(chartStore.indicators).toEqual([])
    releasePresets()

    await vi.waitFor(() => expect(setIndicators).toHaveBeenCalledTimes(1))
    expect(chartStore.indicators).toEqual(defaultIndicators)
    wrapper.unmount()
  })

  it('does not apply the default twice when onSymbolSelect observes settled presets', async () => {
    const { defaultIndicators, releasePresets, releaseSymbolLoad, setIndicators, wrapper } = mountDeferredPresetsChart(true)

    await flushPromises()
    releasePresets()
    await flushPromises()
    releaseSymbolLoad()

    await vi.waitFor(() => expect(setIndicators).toHaveBeenCalledTimes(1))
    expect(setIndicators).toHaveBeenCalledWith(defaultIndicators)
    wrapper.unmount()
  })

  it('does not let a late default overwrite a user indicator edit', async () => {
    const { chartStore, releasePresets, setIndicators, wrapper } = mountDeferredPresetsChart()
    const userIndicator = { type: 'rsi', params: { period: 9 }, style: { color: '#ff0' }, pane: 'separate' } as const

    await flushPromises()
    chartStore.addIndicator(userIndicator as any)
    releasePresets()
    await flushPromises()

    expect(setIndicators).not.toHaveBeenCalled()
    expect(chartStore.indicators).toEqual([userIndicator])
    wrapper.unmount()
  })

  it('does not let onSymbolSelect overwrite a user edit made while its symbol load is pending', async () => {
    const { chartStore, releasePresets, releaseSymbolLoad, setIndicators, wrapper } = mountDeferredPresetsChart(true)
    const userIndicator = { type: 'rsi', params: { period: 9 }, style: { color: '#ff0' }, pane: 'separate' } as const

    await flushPromises()
    chartStore.addIndicator(userIndicator as any)
    releasePresets()
    await flushPromises()
    releaseSymbolLoad()
    await flushPromises()

    expect(setIndicators).not.toHaveBeenCalled()
    expect(chartStore.indicators).toEqual([userIndicator])
    wrapper.unmount()
  })

  it('does not let the bootstrap default overwrite a newer same-symbol selection', async () => {
    const { chartStore, releasePresets, setIndicators, wrapper } = mountDeferredPresetsChart()
    const vm = wrapper.vm as unknown as { onSymbolSelect: (symbol: string) => Promise<void> }

    await flushPromises()
    await vm.onSymbolSelect('QQQ')
    await vm.onSymbolSelect('SPY')
    releasePresets()
    await flushPromises()

    expect(chartStore.symbol).toBe('SPY')
    expect(setIndicators).not.toHaveBeenCalled()
    expect(chartStore.indicators).toEqual([])
    wrapper.unmount()
  })
})
