import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const store = vi.hoisted(() => ({
  watchlists: [{
    id: 1,
    name: 'Primary',
    is_managed: false,
    is_locked: false,
    items: [],
  }],
  fetchPrices: vi.fn(),
  createWatchlist: vi.fn(),
  renameWatchlist: vi.fn(),
  deleteWatchlist: vi.fn(),
  copyWatchlist: vi.fn(),
  lockWatchlist: vi.fn(),
  unlockWatchlist: vi.fn(),
  addBySymbol: vi.fn(),
  removeItem: vi.fn(),
}))

vi.mock('@/stores/watchlist', () => ({
  useWatchlistStore: () => store,
}))

import DashboardWatchlistWidget from '@/components/dashboard/DashboardWatchlistWidget.vue'

const globalStubs = {
  DashboardInstrumentSearch: { template: '<div />' },
  Sparkline: { template: '<span />' },
  'router-link': { template: '<a><slot /></a>' },
}

describe('DashboardWatchlistWidget lifecycle fencing', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    store.fetchPrices.mockResolvedValue(undefined)
    store.renameWatchlist.mockResolvedValue(undefined)
    store.deleteWatchlist.mockResolvedValue(undefined)
    store.lockWatchlist.mockResolvedValue(undefined)
    store.unlockWatchlist.mockResolvedValue(undefined)
    store.addBySymbol.mockResolvedValue(undefined)
  })

  it('does not emit a late create patch after the widget unmounts', async () => {
    let resolveCreated!: (watchlist: any) => void
    const created = new Promise(resolve => { resolveCreated = resolve })
    store.createWatchlist.mockReturnValueOnce(created)
    const wrapper = mount(DashboardWatchlistWidget, {
      props: { config: { watchlistId: 1 } },
      global: { stubs: globalStubs },
    })

    await wrapper.get('.watchlist-toolbar button').trigger('click')
    await Promise.resolve()
    wrapper.unmount()
    resolveCreated({ id: 2, name: 'Created' })
    await Promise.resolve()
    await Promise.resolve()

    expect(wrapper.emitted('patchConfig')).toBeUndefined()
  })

  it('does not clear add input after a late add response post-unmount', async () => {
    let resolveAdded!: () => void
    const added = new Promise<void>(resolve => { resolveAdded = resolve })
    store.addBySymbol.mockReturnValueOnce(added)
    const wrapper = mount(DashboardWatchlistWidget, {
      props: { config: { watchlistId: 1 } },
      global: { stubs: {
        ...globalStubs,
        DashboardInstrumentSearch: {
          template: '<button class="add-symbol" @click="$emit(\'select\', \'AAPL\')" />',
          emits: ['select'],
        },
      } },
    })

    const vm = wrapper.vm as unknown as { addSymbol: string }
    vm.addSymbol = 'AAPL'
    await wrapper.find('.add-symbol').trigger('click')
    await Promise.resolve()
    wrapper.unmount()
    resolveAdded()
    await Promise.resolve()
    await Promise.resolve()

    expect(vm.addSymbol).toBe('AAPL')
  })
})
