import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { ensurePreparation, ensureSymbol, plottedData } = vi.hoisted(() => ({
  ensurePreparation: vi.fn(),
  ensureSymbol: vi.fn(async (symbol: string) => symbol),
  plottedData: [] as any[],
}))

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }))
vi.mock('@/lib/instruments', () => ({ ensureKnownInstrumentSymbol: ensureSymbol }))
vi.mock('@/lib/dataPreparation', () => ({
  dataPreparationCoordinator: { ensure: ensurePreparation },
  PreparationProgressRefreshQueue: class { request(_response: unknown, refresh: () => Promise<void>) { return refresh() } isLatest() { return true } },
  shouldRefreshAnalysisProgress: (response: any) => ['running', 'partial', 'ready', 'waiting', 'unavailable', 'failed'].includes(response.status),
  instrumentHistoryPreparationRequest: (target: unknown, timeframe: string) => ({ target, timeframe, datasets: ['identity', 'profile', 'history'], adjusted: true }),
  preparationStatusMessage: (response: any) => response.status === 'waiting'
    ? 'Waiting for requested history.'
    : response.status === 'unavailable'
      ? 'Requested history is unavailable.'
      : 'Preparing requested history…',
}))
vi.mock('uplot', () => ({
  default: class {
    constructor(_options: unknown, data: unknown) { plottedData.push(data) }
    destroy() {}
    setSize() {}
  },
}))

import { api } from '@/lib/api'
import DashboardLineChartWidget from '@/components/dashboard/DashboardLineChartWidget.vue'

function ready() {
  return { status: 'ready', completed: 3, total: 3, dependencies: [] }
}

describe('dashboard comparison history preparation', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    plottedData.length = 0
    ensureSymbol.mockImplementation(async (symbol: string) => symbol)
  })

  it('submits every selected dataset independently and renders a ready peer while another waits', async () => {
    let finishFirst!: (value: unknown) => void
    ensurePreparation.mockImplementation((request: any, options: any) => {
      if (request.target.symbol === 'AAPL') {
        options.onProgress?.({ response: { status: 'waiting' } })
        return new Promise(resolve => { finishFirst = resolve })
      }
      return Promise.resolve(ready())
    })
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValue([
      { ts: '2026-11-06T00:00:00Z', open: 1, high: 2, low: 1, close: 2, volume: 1 },
    ])
    ;(globalThis as any).ResizeObserver = class {
      observe() {}
      disconnect() {}
    }

    const wrapper = mount(DashboardLineChartWidget, {
      props: {
        type: 'comparison_chart',
        config: { targets: [{ symbol: 'AAPL' }, { symbol: 'MSFT' }], timeframe: 'D1' },
      },
    })
    await flushPromises()

    expect(ensurePreparation).toHaveBeenCalledTimes(2)
    expect(ensurePreparation.mock.calls.map(([request]) => request.target.symbol)).toEqual(['AAPL', 'MSFT'])
    expect(api.get).toHaveBeenCalledWith('/ohlcv/MSFT/D1', { limit: 300 })
    expect(wrapper.find('.uplot-host').exists()).toBe(true)
    expect(wrapper.text()).toContain('AAPL: Waiting for requested history.')
    expect(api.get).toHaveBeenCalledWith('/ohlcv/AAPL/D1', { limit: 300 })

    finishFirst({ status: 'unavailable', completed: 1, total: 3, dependencies: [] })
    await flushPromises()
    expect(wrapper.text()).toContain('AAPL: Requested history is unavailable.')
    expect(wrapper.find('.uplot-host').exists()).toBe(true)
    wrapper.unmount()
  })

  it('keeps cached comparison data visible while preparation is held and fences an obsolete context', async () => {
    let releaseAapl!: (value: unknown) => void
    const held = new Promise(resolve => { releaseAapl = resolve })
    ensurePreparation.mockImplementation((request: any, options: any) => {
      options.onProgress?.({ response: { status: 'waiting' } })
      return request.target.symbol === 'AAPL' ? held : Promise.resolve(ready())
    })
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementation(async (path: string) => {
      const symbol = path.match(/\/ohlcv\/([^/]+)/)?.[1]
      const close = symbol === 'MSFT' ? 22 : 11
      return [{ ts: '2026-11-06T00:00:00Z', open: close, high: close + 1, low: close - 1, close, volume: 1 }]
    })
    ;(globalThis as any).ResizeObserver = class { observe() {} disconnect() {} }
    const wrapper = mount(DashboardLineChartWidget, {
      props: { type: 'comparison_chart', config: { targets: [{ symbol: 'AAPL' }], timeframe: 'D1', normalize: false } },
    })
    await flushPromises()
    expect(api.get).toHaveBeenCalledWith('/ohlcv/AAPL/D1', { limit: 300 })
    expect(wrapper.find('.uplot-host').exists()).toBe(true)
    expect(wrapper.text()).toContain('AAPL: Waiting for requested history.')

    await wrapper.setProps({ type: 'comparison_chart', config: { targets: [{ symbol: 'MSFT' }], timeframe: 'D1', normalize: false } })
    await flushPromises()
    expect(wrapper.find('.uplot-host').exists()).toBe(true)
    expect(plottedData.at(-1)?.[1]).toEqual([22])
    releaseAapl({ status: 'ready', completed: 3, total: 3, dependencies: [] })
    await flushPromises()
    expect(plottedData.at(-1)?.[1]).toEqual([22])
    expect(ensurePreparation.mock.calls.map(([request]) => request.target.symbol)).toEqual(['AAPL', 'MSFT'])
    wrapper.unmount()
  })
})
