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
          UPlotChart: { template: '<div />' },
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

  it('does not load the advanced chart until its selected timeframe is prepared', async () => {
    resolveSymbol.mockResolvedValueOnce('AAPL')
    ensurePreparation.mockImplementationOnce(async (_request: unknown, options: any) => {
      options.onProgress?.({ response: { status: 'waiting' } })
      return { status: 'waiting' }
    })
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = usePanelStore('dashboard-8')
    const loadBarsSpy = vi.spyOn(store, 'loadBars').mockResolvedValue(undefined)
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
    expect(loadBarsSpy).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Waiting for requested history.')
    wrapper.unmount()
  })
})
