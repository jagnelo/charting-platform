import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DashboardQuoteWidget from '@/components/dashboard/DashboardQuoteWidget.vue'
import DashboardInstrumentDetailsWidget from '@/components/dashboard/DashboardInstrumentDetailsWidget.vue'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn() },
}))

const { ensurePreparation } = vi.hoisted(() => ({ ensurePreparation: vi.fn() }))
vi.mock('@/lib/dataPreparation', () => ({
  dataPreparationCoordinator: { ensure: ensurePreparation },
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

  it('prepares quote history before reading it and shows a terminal unavailable outcome', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValue(instrument('AAPL'))
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
    expect(api.get).toHaveBeenCalledTimes(1) // canonical identity only; no quote or OHLCV read
  })

  it('prepares profile-backed instrument details before loading the instrument profile', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValue(instrument('AAPL'))
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
    await flushPromises()
    await wrapper.setProps({ config: { symbol: 'MSFT' } })
    await flushPromises()

    expect(firstSignal?.aborted).toBe(true)
    expect(ensurePreparation.mock.calls.map(([request]) => request.target.symbol)).toEqual(['AAPL', 'MSFT'])
    expect(wrapper.text()).toContain('Some requested data is unavailable')
    expect(api.get.mock.calls.some(([path]) => String(path).startsWith('/ohlcv/'))).toBe(false)
    wrapper.unmount()
  })
})
