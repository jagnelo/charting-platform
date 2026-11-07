import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DashboardAdvancedChartWidget from '@/components/dashboard/DashboardAdvancedChartWidget.vue'
import { usePanelStore } from '@/stores/chart'

const { resolveSymbol, ensurePreparation } = vi.hoisted(() => ({ resolveSymbol: vi.fn(), ensurePreparation: vi.fn() }))

vi.mock('@/lib/instruments', () => ({
  ensureKnownInstrumentSymbol: resolveSymbol,
}))

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn() },
}))

vi.mock('@/lib/dataPreparation', () => ({
  dataPreparationCoordinator: { ensure: ensurePreparation },
  PreparationProgressRefreshQueue: class { request(_response: unknown, refresh: () => Promise<void>) { return refresh() } isLatest() { return true } },
  shouldRefreshAnalysisProgress: (response: any) => ['running', 'partial', 'ready', 'waiting', 'unavailable', 'failed'].includes(response.status),
  instrumentHistoryPreparationRequest: (target: unknown, timeframe: string) => ({ target, timeframe, datasets: ['identity', 'profile', 'history'], adjusted: true }),
  preparationStatusMessage: (response: any) => response.status === 'waiting' ? 'Waiting for requested history.' : 'Preparing requested history…',
}))

describe('DashboardAdvancedChartWidget lifecycle fencing', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.resetAllMocks()
    resolveSymbol.mockImplementation(async (symbol: string) => symbol)
    ensurePreparation.mockResolvedValue({ status: 'ready' })
  })

  it('does not start chart hydration after canonical symbol resolution finishes post-unmount', async () => {
    let resolveTarget!: (symbol: string) => void
    const targetResolved = new Promise<string>(resolve => { resolveTarget = resolve })
    resolveSymbol.mockReturnValueOnce(targetResolved)
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = usePanelStore('dashboard-7')
    const loadBarsSpy = vi.spyOn(store, 'loadBars').mockResolvedValue(undefined)

    const wrapper = mount(DashboardAdvancedChartWidget, {
      props: { widgetId: 7, config: { symbol: 'AAPL' } },
      global: {
        plugins: [pinia],
        stubs: {
          UPlotChart: { name: 'UPlotChart', template: '<div class="dashboard-chart-rendered" />' },
          'router-link': { template: '<a><slot /></a>' },
        },
      },
    })

    await Promise.resolve()
    wrapper.unmount()
    resolveTarget('AAPL')
    await Promise.resolve()
    await Promise.resolve()

    expect(loadBarsSpy).not.toHaveBeenCalled()
  })

  it('shows a local cached advanced chart while preparation remains held', async () => {
    resolveSymbol.mockResolvedValueOnce('AAPL')
    let releasePreparation!: (value: unknown) => void
    ensurePreparation.mockImplementationOnce((_request: unknown, options: any) => {
      options.onProgress?.({ response: { status: 'waiting' } })
      return new Promise(resolve => { releasePreparation = resolve })
    })
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = usePanelStore('dashboard-8')
    const cachedBars = [{ ts: '2026-11-06T00:00:00Z', open: 10, high: 12, low: 9, close: 11, volume: 1 }]
    const loadBarsSpy = vi.spyOn(store, 'loadBars').mockImplementation(async (symbol, timeframe, type) => {
      store.symbol = symbol
      store.timeframe = timeframe
      store.barType = type
      store.bars = cachedBars as any
    })
    const refreshedSymbols: string[] = []
    const refreshLocalSpy = vi.spyOn(store, 'refreshLocalBars').mockImplementation(async () => { refreshedSymbols.push(store.symbol) })
    const wrapper = mount(DashboardAdvancedChartWidget, {
      props: { widgetId: 8, config: { symbol: 'AAPL', timeframe: 'W1' } },
      global: {
        plugins: [pinia],
        stubs: { UPlotChart: { template: '<div />' }, 'router-link': { template: '<a><slot /></a>' } },
      },
    })
    for (let index = 0; index < 20; index++) await Promise.resolve()

    expect(ensurePreparation).toHaveBeenCalledWith(
      { target: { kind: 'instrument', symbol: 'AAPL' }, timeframe: 'W1', datasets: ['identity', 'profile', 'history'], adjusted: true },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
    expect(loadBarsSpy).toHaveBeenCalledWith('AAPL', 'W1', 'candles', true)
    expect(store.bars).toEqual(cachedBars)
    expect(wrapper.find('.advanced-chart-widget [chart-type="candles"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Waiting for requested history.')
    releasePreparation({ status: 'waiting', version: 3, dependencies: [] })
    for (let index = 0; index < 20; index++) await Promise.resolve()
    expect(refreshLocalSpy).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('does not refresh cached bars from an obsolete preparation after the selected symbol changes', async () => {
    let releaseOld!: (value: unknown) => void
    ensurePreparation.mockImplementation((request: any, options: any) => {
      options.onProgress?.({ response: { status: 'waiting' } })
      if (request.target.symbol === 'AAPL') return new Promise(resolve => { releaseOld = resolve })
      return Promise.resolve({ status: 'ready', version: 1, dependencies: [] })
    })
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = usePanelStore('dashboard-9')
    const loadBarsSpy = vi.spyOn(store, 'loadBars').mockImplementation(async symbol => {
      store.symbol = symbol
      store.bars = [{ ts: symbol, open: 1, high: 2, low: 1, close: symbol === 'MSFT' ? 22 : 11, volume: 1 }] as any
    })
    const refreshedSymbols: string[] = []
    vi.spyOn(store, 'refreshLocalBars').mockImplementation(async () => { refreshedSymbols.push(store.symbol) })
    const wrapper = mount(DashboardAdvancedChartWidget, {
      props: { widgetId: 9, config: { symbol: 'AAPL' } },
      global: { plugins: [pinia], stubs: { UPlotChart: { name: 'UPlotChart', template: '<div class="dashboard-chart-rendered" />' }, 'router-link': { template: '<a><slot /></a>' } } },
    })
    await vi.waitFor(() => expect(ensurePreparation.mock.calls.some(([request]) => request.target.symbol === 'AAPL')).toBe(true))
    expect(releaseOld).toBeTypeOf('function')
    await wrapper.setProps({ config: { symbol: 'MSFT' } })
    for (let index = 0; index < 20; index++) await Promise.resolve()
    const afterSymbolChange = refreshedSymbols.length
    expect(store.symbol).toBe('MSFT')
    releaseOld({ status: 'ready', version: 4, dependencies: [] })
    for (let index = 0; index < 20; index++) await Promise.resolve()
    expect(store.symbol).toBe('MSFT')
    expect(store.bars[0].close).toBe(22)
    expect(loadBarsSpy).toHaveBeenCalledWith('MSFT', 'D1', 'candles', true)
    expect(refreshedSymbols.slice(afterSymbolChange)).not.toContain('AAPL')
    wrapper.unmount()
  })
})
