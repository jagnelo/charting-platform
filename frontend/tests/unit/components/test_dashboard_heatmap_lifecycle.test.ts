import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const stores = vi.hoisted(() => ({
  watchlist: {
    watchlists: [] as any[],
    loadWatchlists: vi.fn(),
    fetchPrices: vi.fn(),
    priceMap: {} as Record<string, any>,
  },
  alerts: {
    activeCountForInstrument: vi.fn(),
  },
}))

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn() },
}))
vi.mock('@/stores/watchlist', () => ({
  useWatchlistStore: () => stores.watchlist,
}))
vi.mock('@/stores/alerts', () => ({
  useAlertsStore: () => stores.alerts,
}))

import DashboardHeatMapWidget from '@/components/dashboard/DashboardHeatMapWidget.vue'
import { api } from '@/lib/api'

vi.stubGlobal('ResizeObserver', class {
  observe() {}
  disconnect() {}
})

const globalStubs = {
  Sparkline: { template: '<span />' },
  'router-link': { template: '<a><slot /></a>' },
}

describe('DashboardHeatMapWidget lifecycle fencing', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    stores.watchlist.watchlists = []
    stores.watchlist.priceMap = {}
    stores.watchlist.fetchPrices.mockResolvedValue(undefined)
    stores.watchlist.loadWatchlists.mockResolvedValue(undefined)
    stores.alerts.activeCountForInstrument.mockReturnValue(0)
  })

  it('does not publish late heatmap data after the widget unmounts', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([{ matched_ids: [7] }])
    let resolveData!: (rows: any[]) => void
    const dataLoaded = new Promise<any[]>(resolve => { resolveData = resolve })
    ;(api.post as ReturnType<typeof vi.fn>).mockReturnValueOnce(dataLoaded)

    const wrapper = mount(DashboardHeatMapWidget, {
      props: { config: { universeType: 'screener', screenerId: 1 } },
      global: { stubs: globalStubs },
    })

    await vi.waitFor(() => expect(api.post).toHaveBeenCalledWith('/instruments/heatmap-data', expect.anything()))
    const vm = wrapper.vm as unknown as { rows: any[]; loading: boolean }
    wrapper.unmount()
    resolveData([{ instrument_id: 7, symbol: 'AAPL', name: 'Apple', sparkline: [] }])
    await Promise.resolve()
    await Promise.resolve()

    expect(vm.rows).toEqual([])
    expect(vm.loading).toBe(true)
  })

  it('does not publish rows after a late live-price hydration response', async () => {
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce([{ matched_ids: [7] }])
    ;(api.post as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      { instrument_id: 7, symbol: 'AAPL', name: 'Apple', sparkline: [] },
    ])
    let resolvePrices!: () => void
    const pricesLoaded = new Promise<void>(resolve => { resolvePrices = resolve })
    stores.watchlist.fetchPrices.mockReturnValueOnce(pricesLoaded)

    const wrapper = mount(DashboardHeatMapWidget, {
      props: { config: { universeType: 'screener', screenerId: 1 } },
      global: { stubs: globalStubs },
    })

    await vi.waitFor(() => expect(stores.watchlist.fetchPrices).toHaveBeenCalledWith(['AAPL'], false))
    const vm = wrapper.vm as unknown as { rows: any[]; loading: boolean }
    wrapper.unmount()
    resolvePrices()
    await Promise.resolve()
    await Promise.resolve()

    expect(vm.rows).toEqual([])
    expect(vm.loading).toBe(true)
  })
})
