import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DashboardQuoteWidget from '@/components/dashboard/DashboardQuoteWidget.vue'
import DashboardInstrumentDetailsWidget from '@/components/dashboard/DashboardInstrumentDetailsWidget.vue'

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn() },
}))

import { api } from '@/lib/api'

function instrument(symbol: string) {
  return { id: 7, symbol, name: `${symbol} Corp`, is_active: true, currency: 'USD', stats: { week52_high: 120, week52_low: 80 }, equity_detail: { sector: 'Technology', industry: 'Software' } }
}

describe('dashboard instrument widget lifecycle fencing', () => {
  beforeEach(() => {
    vi.resetAllMocks()
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
})
