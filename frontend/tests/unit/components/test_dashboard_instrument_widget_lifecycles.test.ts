import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DashboardQuoteWidget from '@/components/dashboard/DashboardQuoteWidget.vue'
import DashboardInstrumentDetailsWidget from '@/components/dashboard/DashboardInstrumentDetailsWidget.vue'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn() },
}))

const { ensurePreparation, ensureSymbol } = vi.hoisted(() => ({ ensurePreparation: vi.fn(), ensureSymbol: vi.fn(async (symbol: string) => symbol) }))
vi.mock('@/lib/instruments', () => ({ ensureKnownInstrumentSymbol: ensureSymbol }))
vi.mock('@/lib/dataPreparation', () => ({
  dataPreparationCoordinator: { ensure: ensurePreparation },
  PreparationProgressRefreshQueue: class { request(_response: unknown, refresh: () => Promise<void>) { return refresh() } isLatest() { return true } },
  shouldRefreshAnalysisProgress: (response: any) => ['running', 'partial', 'ready', 'waiting', 'unavailable', 'failed'].includes(response.status),
  instrumentHistoryPreparationRequest: (target: unknown, timeframe: string) => ({ target, timeframe, datasets: ['identity', 'profile', 'history'], adjusted: true }),
  preparationStatusMessage: (response: any) => response.status === 'waiting'
    ? 'Data is temporarily paused. Your current view remains usable.'
    : response.status === 'unavailable'
      ? 'Some requested data is unavailable. Available results remain usable.'
      : 'Preparing requested data…',
}))

import { api } from '@/lib/api'

function instrument(symbol: string) {
  return { id: 7, symbol, name: `${symbol} Corp`, is_active: true, currency: 'USD', stats: { week52_high: 120, week52_low: 80 }, equity_detail: { sector: 'Technology', industry: 'Software' } }
}

async function flushPromises() {
  for (let index = 0; index < 12; index++) await Promise.resolve()
}

describe('dashboard instrument widget lifecycle fencing', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    ensurePreparation.mockResolvedValue({ status: 'ready' })
    ensureSymbol.mockImplementation(async (symbol: string) => symbol)
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementation(async (path: string) => {
      const symbol = path.match(/\/instruments\/([^/]+)/)?.[1] ?? 'AAPL'
      if (path.includes('/ohlcv/')) return [{ close: 11 }, { close: 12 }]
      return instrument(symbol)
    })
  })

  it('does not publish a late quote response after the widget unmounts', async () => {
    let resolveInstrument!: (value: any) => void
    const instrumentLoaded = new Promise(resolve => { resolveInstrument = resolve })
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementationOnce(() => instrumentLoaded)
    const wrapper = mount(DashboardQuoteWidget, {
      props: { config: { symbol: 'AAPL' } },
      global: { stubs: { 'router-link': { template: '<a><slot /></a>' } } },
    })

    await Promise.resolve()
    const vm = wrapper.vm as unknown as { instrument: any; loading: boolean }
    wrapper.unmount()
    resolveInstrument(instrument('AAPL'))
    await Promise.resolve()
    await Promise.resolve()

    expect(vm.instrument).toBe(null)
    expect(vm.loading).toBe(true)
  })

  it('does not let an obsolete cached quote read replace a newly selected symbol', async () => {
    let releaseAapl!: (value: any) => void
    const aaplProfile = new Promise(resolve => { releaseAapl = resolve })
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementation((path: string) => {
      if (path === '/instruments/AAPL') return aaplProfile
      if (path === '/ohlcv/AAPL/D1') return Promise.resolve([{ close: 10 }])
      if (path === '/instruments/MSFT') return Promise.resolve(instrument('MSFT'))
      if (path === '/ohlcv/MSFT/D1') return Promise.resolve([{ close: 20 }, { close: 22 }])
      return Promise.reject(new Error(`Unexpected request ${path}`))
    })
    ensurePreparation.mockImplementation((request: any, options: any) => {
      if (request.target.symbol === 'AAPL') {
        return new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))))
      }
      return Promise.resolve({ status: 'ready' })
    })
    const wrapper = mount(DashboardQuoteWidget, {
      props: { config: { symbol: 'AAPL' } },
      global: { stubs: { 'router-link': { template: '<a><slot /></a>' } } },
    })
    await wrapper.setProps({ config: { symbol: 'MSFT' } })
    await flushPromises()
    expect(wrapper.find('.quote-symbol').text()).toBe('MSFT')
    expect(wrapper.find('.quote-price').text()).toBe('$22.0000')
    releaseAapl(instrument('AAPL'))
    await flushPromises()
    expect(wrapper.find('.quote-symbol').text()).toBe('MSFT')
    expect(wrapper.find('.quote-price').text()).toBe('$22.0000')
    wrapper.unmount()
  })

  it('does not publish a late instrument-details response after the widget unmounts', async () => {
    let resolveInstrument!: (value: any) => void
    const instrumentLoaded = new Promise(resolve => { resolveInstrument = resolve })
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementationOnce(() => instrumentLoaded)
    const wrapper = mount(DashboardInstrumentDetailsWidget, {
      props: { config: { symbol: 'AAPL' } },
      global: { stubs: { 'router-link': { template: '<a><slot /></a>' } } },
    })

    await Promise.resolve()
    const vm = wrapper.vm as unknown as { instrument: any; loading: boolean }
    wrapper.unmount()
    resolveInstrument(instrument('AAPL'))
    await Promise.resolve()
    await Promise.resolve()

    expect(vm.instrument).toBe(null)
    expect(vm.loading).toBe(true)
  })

  it('shows cached quote content while preparation is held and retains the held explanation', async () => {
    ensurePreparation.mockImplementationOnce(async (_request: unknown, options: any) => {
      options.onProgress?.({ response: { status: 'waiting' } })
      return { status: 'unavailable' }
    })

    const wrapper = mount(DashboardQuoteWidget, {
      props: { config: { symbol: 'AAPL' } },
      global: { stubs: { 'router-link': { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    expect(ensurePreparation).toHaveBeenCalledWith(
      { target: { kind: 'instrument', symbol: 'AAPL' }, timeframe: 'D1', datasets: ['identity', 'profile', 'history'], adjusted: true },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
    expect(wrapper.text()).toContain('Some requested data is unavailable')
    expect(wrapper.find('.quote-price').text()).toBe('$12.0000')
    expect(api.get).toHaveBeenCalledWith('/instruments/AAPL')
    expect(api.get).toHaveBeenCalledWith('/ohlcv/AAPL/D1', { limit: 2 })
    wrapper.unmount()
  })

  it('prepares profile-backed instrument details before loading the instrument profile', async () => {
    const wrapper = mount(DashboardInstrumentDetailsWidget, {
      props: { config: { symbol: 'AAPL' } },
      global: { stubs: { 'router-link': { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    expect(ensurePreparation).toHaveBeenCalledWith(
      { target: { kind: 'instrument', symbol: 'AAPL' }, timeframe: 'D1', datasets: ['identity', 'profile', 'history'], adjusted: true },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
    expect(api.get).toHaveBeenCalledWith('/instruments/AAPL')
    wrapper.unmount()
  })

  it('shows cached instrument details before a held ensure and ignores a stale history response after context changes', async () => {
    let releaseOldHistory!: (value: unknown) => void
    const oldHistory = new Promise(resolve => { releaseOldHistory = resolve })
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementation((path: string) => {
      if (path === '/ohlcv/AAPL/D1') return oldHistory
      if (path === '/ohlcv/MSFT/D1') return Promise.resolve([{ close: 21 }])
      const symbol = path.includes('/instruments/') ? path.split('/').pop()! : 'MSFT'
      const loaded = instrument(symbol)
      return Promise.resolve(symbol === 'AAPL' ? { ...loaded, stats: {} } : loaded)
    })
    ensurePreparation.mockImplementation((request: any, options: any) => {
      options.onProgress?.({ response: { status: 'waiting' } })
      return new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))))
    })
    const wrapper = mount(DashboardInstrumentDetailsWidget, {
      props: { config: { symbol: 'AAPL' } },
      global: { stubs: { 'router-link': { template: '<a><slot /></a>' } } },
    })
    await flushPromises()
    expect(wrapper.find('.details-symbol').text()).toBe('AAPL')
    expect(wrapper.find('.details-preparation').text()).toContain('Data is temporarily paused')

    await wrapper.setProps({ config: { symbol: 'MSFT' } })
    await flushPromises()
    expect(wrapper.find('.details-symbol').text()).toBe('MSFT')
    releaseOldHistory([{ close: 10 }])
    await flushPromises()
    expect(wrapper.find('.details-symbol').text()).toBe('MSFT')
    expect(wrapper.text()).not.toContain('AAPL Corp')
    wrapper.unmount()
  })

  it('aborts an obsolete preparation subscription when the selected symbol changes', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockImplementation(async path => ({ symbol: String(path).split('/').pop() }))
    let firstSignal: AbortSignal | undefined
    ensurePreparation.mockImplementation((request: any, options: any) => {
      if (request.target.symbol === 'AAPL') {
        firstSignal = options.signal
        return new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))))
      }
      return Promise.resolve({ status: 'unavailable' })
    })

    const wrapper = mount(DashboardQuoteWidget, {
      props: { config: { symbol: 'AAPL' } },
      global: { stubs: { 'router-link': { template: '<a><slot /></a>' } } },
    })
    await vi.waitFor(() => expect(ensurePreparation.mock.calls.some(([request]) => request.target.symbol === 'AAPL')).toBe(true))
    await wrapper.setProps({ config: { symbol: 'MSFT' } })
    await flushPromises()

    expect(firstSignal?.aborted).toBe(true)
    expect(ensurePreparation.mock.calls.map(([request]) => request.target.symbol)).toEqual(['AAPL', 'MSFT'])
    expect(wrapper.text()).toContain('Some requested data is unavailable')
    expect(api.get.mock.calls.some(([path]) => path === '/ohlcv/MSFT/D1')).toBe(true)
    expect(wrapper.find('.quote-symbol').text()).toBe('MSFT')
    wrapper.unmount()
  })
})
