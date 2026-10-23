import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

const { apiGet, apiPost, apiDelete } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  api: {
    get: apiGet,
    post: apiPost,
    delete: apiDelete,
  },
}))

import WorkstationToolContent from '@/components/workstation/WorkstationToolContent.vue'
import { useWatchlistStore } from '@/stores/watchlist'
import type { WorkspaceWindowState } from '@/stores/workspace'

const ToolWindowShell = defineComponent({
  name: 'ToolWindow',
  setup(_, { slots }) {
    return () => h('div', { class: 'tool-window-shell' }, slots.default?.())
  },
})

function toolFixture(configuration: Record<string, unknown>): WorkspaceWindowState {
  return {
    id: 31,
    instance_key: 'personal-watchlist-test',
    tool_type: 'watchlist',
    title: 'Personal WatchList',
    link_group: 'A',
    configuration: {
      personal: true,
      watchlist_id: 3,
      ...configuration,
    },
    style: {},
    state_schema_version: 1,
    position: 0,
  }
}

function watchlist(id: number, name: string, items: Array<Record<string, unknown>>, overrides = {}) {
  return {
    id,
    name,
    description: null,
    is_managed: false,
    is_locked: false,
    items,
    ...overrides,
  }
}

function setupParent(targets: Array<Record<string, unknown>>, tagWatchlistIds: number[]) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const watchlistStore = useWatchlistStore(pinia)
  watchlistStore.watchlists = [
    watchlist(3, 'Primary', [{ id: 11, instrument_id: 101, symbol: 'SPY', name: 'SPDR S&P 500 ETF' }]),
    ...targets,
  ] as never
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = mount(WorkstationToolContent, {
    props: {
      tool: toolFixture({
        tag_watchlist_ids: tagWatchlistIds,
        column_keys: ['symbol', ...tagWatchlistIds.map(id => `tag-watchlist:${id}`)],
      }),
    },
    global: {
      plugins: [pinia, [VueQueryPlugin, { queryClient }]],
      stubs: { ToolWindow: ToolWindowShell },
    },
  })
  return { queryClient, watchlistStore, wrapper }
}

describe('WorkstationToolContent Tag Column parent mutation path', () => {
  beforeEach(() => {
    apiGet.mockReset().mockResolvedValue([])
    apiPost.mockReset().mockResolvedValue({ id: 22, instrument_id: 101, symbol: 'SPY' })
    apiDelete.mockReset().mockResolvedValue(undefined)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('routes an ordinary accessible row-menu click through the parent to the selected-list store mutation', async () => {
    const { queryClient, watchlistStore, wrapper } = setupParent(
      [watchlist(7, 'Core', [])],
      [7],
    )
    await flushPromises()

    await wrapper.get('.watchlist__row').trigger('contextmenu', { clientX: 20, clientY: 24 })
    await flushPromises()
    const addAction = wrapper.findAll('button[role="menuitem"]')
      .find(button => button.text() === 'Add SPY to Tag · Core')
    expect(addAction).toBeDefined()
    await addAction!.trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/watchlists/7/items', { instrument_id: 101 })
    expect(watchlistStore.watchlists.find(item => item.id === 7)?.items).toEqual([
      { id: 22, instrument_id: 101, symbol: 'SPY' },
    ])
    expect(wrapper.get('.watchlist__row').text()).toContain('In')

    wrapper.unmount()
    queryClient.clear()
  })

  it('keeps locked and unavailable targets non-mutating through the mounted parent path', async () => {
    const { queryClient, wrapper } = setupParent(
      [
        watchlist(8, 'Locked', [{ id: 18, instrument_id: 101, symbol: 'SPY' }], { is_locked: true }),
      ],
      [8, 9],
    )
    await flushPromises()

    await wrapper.get('.watchlist__row').trigger('contextmenu', { clientX: 20, clientY: 24 })
    await flushPromises()

    const disabledActions = wrapper.findAll('button[role="menuitem"]:disabled')
    const lockedAction = disabledActions.find(button => button.text() === 'Remove SPY from Tag · Locked')
    const unavailableAction = disabledActions.find(button => button.text().includes('Membership unavailable'))
    expect(lockedAction).toBeDefined()
    expect(unavailableAction).toBeDefined()
    expect(apiPost).not.toHaveBeenCalled()
    expect(apiDelete).not.toHaveBeenCalled()

    wrapper.unmount()
    queryClient.clear()
  })
})
