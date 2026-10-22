import { flushPromises, shallowMount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { defineComponent } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import WorkstationToolContent from '@/components/workstation/WorkstationToolContent.vue'
import { useWatchlistStore } from '@/stores/watchlist'
import type { WorkspaceWindowState } from '@/stores/workspace'

const { apiDelete, apiGet, apiPost } = vi.hoisted(() => ({
  apiDelete: vi.fn(),
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  api: {
    delete: apiDelete,
    get: apiGet,
    patch: vi.fn(),
    post: apiPost,
    put: vi.fn(),
  },
}))

const ToolWindowStub = defineComponent({
  name: 'ToolWindow',
  template: '<div class="tool-window-stub"><slot /></div>',
})

const VirtualWatchlistToolStub = defineComponent({
  name: 'VirtualWatchlistTool',
  emits: ['row-action', 'update:tag-columns'],
  template: '<div data-testid="virtual-watchlist-tool-stub" />',
})

describe('WorkstationToolContent Tag Column mutations', () => {
  let pinia: ReturnType<typeof createPinia>

  afterEach(() => {
    vi.restoreAllMocks()
  })

  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    apiGet.mockResolvedValue([])
    apiDelete.mockReset()
    apiPost.mockReset()
  })

  it('revalidates and mutates only the selected personal target, surfacing failure outside the personal-list branch', async () => {
    const watchlistStore = useWatchlistStore()
    watchlistStore.watchlists = [
      {
        id: 7,
        name: 'Core',
        is_managed: false,
        is_locked: false,
        items: [{ id: 11, instrument_id: 101, symbol: 'SPY', name: 'SPY' }],
      },
      {
        id: 8,
        name: 'Other',
        is_managed: false,
        is_locked: false,
        items: [],
      },
    ]
    apiDelete.mockRejectedValueOnce(new Error('offline'))
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = shallowMount(WorkstationToolContent, {
      props: {
        tool: {
          instance_key: 'benchmark-list',
          tool_type: 'benchmark_list',
          title: 'Benchmarks',
          configuration: {},
          link_group: 'blue',
          timeframe_link_group: 'blue',
        } as unknown as WorkspaceWindowState,
        activeWindowKey: 'benchmark-list',
      },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: {
          ToolWindow: ToolWindowStub,
          VirtualWatchlistTool: VirtualWatchlistToolStub,
        },
      },
    })

    wrapper.getComponent(VirtualWatchlistToolStub).vm.$emit(
      'row-action',
      'toggle-tag-membership',
      { symbol: 'SPY', instrumentId: 101 },
      7,
    )
    await flushPromises()

    expect(apiDelete).toHaveBeenCalledOnce()
    expect(apiDelete).toHaveBeenCalledWith('/watchlists/7/items/11')
    expect(wrapper.get('[role="alert"]').text()).toContain('Unable to remove SPY from Core.')
    expect(watchlistStore.watchlists[1].items).toEqual([])
    wrapper.unmount()
    queryClient.clear()
  })

  it('adds membership only to the explicitly selected personal target', async () => {
    const watchlistStore = useWatchlistStore()
    watchlistStore.watchlists = [
      {
        id: 7,
        name: 'Core',
        is_managed: false,
        is_locked: false,
        items: [],
      },
      {
        id: 8,
        name: 'Other',
        is_managed: false,
        is_locked: false,
        items: [],
      },
    ]
    apiPost.mockResolvedValueOnce({ id: 12, instrument_id: 101, symbol: 'SPY', name: 'SPY' })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = shallowMount(WorkstationToolContent, {
      props: {
        tool: {
          instance_key: 'benchmark-list',
          tool_type: 'benchmark_list',
          title: 'Benchmarks',
          configuration: {},
          link_group: 'blue',
          timeframe_link_group: 'blue',
        } as unknown as WorkspaceWindowState,
        activeWindowKey: 'benchmark-list',
      },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: {
          ToolWindow: ToolWindowStub,
          VirtualWatchlistTool: VirtualWatchlistToolStub,
        },
      },
    })

    wrapper.getComponent(VirtualWatchlistToolStub).vm.$emit(
      'row-action',
      'toggle-tag-membership',
      { symbol: 'SPY', instrumentId: 101 },
      7,
    )
    await flushPromises()

    expect(apiPost).toHaveBeenCalledOnce()
    expect(apiPost).toHaveBeenCalledWith('/watchlists/7/items', { instrument_id: 101 })
    expect(watchlistStore.watchlists[0].items).toEqual([
      { id: 12, instrument_id: 101, symbol: 'SPY', name: 'SPY' },
    ])
    expect(watchlistStore.watchlists[1].items).toEqual([])
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    wrapper.unmount()
    queryClient.clear()
  })

  it('persists normalized Tag Column targets and visibility without dropping sibling configuration', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = shallowMount(WorkstationToolContent, {
      props: {
        tool: {
          instance_key: 'benchmark-list',
          tool_type: 'benchmark_list',
          title: 'Benchmarks',
          configuration: {
            tag_watchlist_ids: [3],
            column_keys: ['symbol'],
            keep_unrelated_setting: 'unchanged',
          },
          link_group: 'blue',
          timeframe_link_group: 'blue',
        } as unknown as WorkspaceWindowState,
        activeWindowKey: 'benchmark-list',
      },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: {
          ToolWindow: ToolWindowStub,
          VirtualWatchlistTool: VirtualWatchlistToolStub,
        },
      },
    })

    wrapper.getComponent(VirtualWatchlistToolStub).vm.$emit('update:tag-columns', {
      targetWatchlistIds: [7, 7, 0, -1],
      visibleColumnKeys: ['symbol', 'tag-watchlist:7', 'tag-watchlist:7'],
    })

    expect(wrapper.emitted('configuration')?.at(-1)).toEqual([
      'benchmark-list',
      {
        tag_watchlist_ids: [7],
        column_keys: ['symbol', 'tag-watchlist:7'],
        keep_unrelated_setting: 'unchanged',
      },
    ])
    wrapper.unmount()
    queryClient.clear()
  })

  it('rejects a forged membership event for a locked target before transport', async () => {
    const watchlistStore = useWatchlistStore()
    watchlistStore.watchlists = [
      {
        id: 7,
        name: 'Managed Core',
        is_managed: true,
        is_locked: true,
        items: [],
      },
    ]
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = shallowMount(WorkstationToolContent, {
      props: {
        tool: {
          instance_key: 'benchmark-list',
          tool_type: 'benchmark_list',
          title: 'Benchmarks',
          configuration: {},
          link_group: 'blue',
          timeframe_link_group: 'blue',
        } as unknown as WorkspaceWindowState,
        activeWindowKey: 'benchmark-list',
      },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: {
          ToolWindow: ToolWindowStub,
          VirtualWatchlistTool: VirtualWatchlistToolStub,
        },
      },
    })

    wrapper.getComponent(VirtualWatchlistToolStub).vm.$emit(
      'row-action',
      'toggle-tag-membership',
      { symbol: 'SPY', instrumentId: 101 },
      7,
    )
    await flushPromises()

    expect(apiDelete).not.toHaveBeenCalled()
    expect(apiPost).not.toHaveBeenCalled()
    expect(wrapper.get('[role="alert"]').text()).toContain('unlocked personal WatchList')
    expect(watchlistStore.watchlists[0].items).toEqual([])
    wrapper.unmount()
    queryClient.clear()
  })

  it('surfaces a failed add and leaves the selected target unchanged', async () => {
    const watchlistStore = useWatchlistStore()
    watchlistStore.watchlists = [
      {
        id: 7,
        name: 'Core',
        is_managed: false,
        is_locked: false,
        items: [],
      },
      {
        id: 8,
        name: 'Other',
        is_managed: false,
        is_locked: false,
        items: [],
      },
    ]
    apiPost.mockRejectedValueOnce(new Error('offline'))
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = shallowMount(WorkstationToolContent, {
      props: {
        tool: {
          instance_key: 'benchmark-list',
          tool_type: 'benchmark_list',
          title: 'Benchmarks',
          configuration: {},
          link_group: 'blue',
          timeframe_link_group: 'blue',
        } as unknown as WorkspaceWindowState,
        activeWindowKey: 'benchmark-list',
      },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: {
          ToolWindow: ToolWindowStub,
          VirtualWatchlistTool: VirtualWatchlistToolStub,
        },
      },
    })

    wrapper.getComponent(VirtualWatchlistToolStub).vm.$emit(
      'row-action',
      'toggle-tag-membership',
      { symbol: 'SPY', instrumentId: 101 },
      7,
    )
    await flushPromises()

    expect(apiPost).toHaveBeenCalledOnce()
    expect(apiPost).toHaveBeenCalledWith('/watchlists/7/items', { instrument_id: 101 })
    expect(wrapper.get('[role="alert"]').text()).toContain('Unable to add SPY to Core.')
    expect(watchlistStore.watchlists[0].items).toEqual([])
    expect(watchlistStore.watchlists[1].items).toEqual([])
    wrapper.unmount()
    queryClient.clear()
  })

  it('ignores a duplicate in-flight toggle for the same target and instrument', async () => {
    const watchlistStore = useWatchlistStore()
    watchlistStore.watchlists = [
      {
        id: 7,
        name: 'Core',
        is_managed: false,
        is_locked: false,
        items: [],
      },
    ]
    let resolveAdd: ((item: { id: number; instrument_id: number; symbol: string; name: string }) => void) | undefined
    apiPost.mockImplementationOnce(() => new Promise(resolve => { resolveAdd = resolve }))
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = shallowMount(WorkstationToolContent, {
      props: {
        tool: {
          instance_key: 'benchmark-list',
          tool_type: 'benchmark_list',
          title: 'Benchmarks',
          configuration: {},
          link_group: 'blue',
          timeframe_link_group: 'blue',
        } as unknown as WorkspaceWindowState,
        activeWindowKey: 'benchmark-list',
      },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: {
          ToolWindow: ToolWindowStub,
          VirtualWatchlistTool: VirtualWatchlistToolStub,
        },
      },
    })
    const list = wrapper.getComponent(VirtualWatchlistToolStub)
    const row = { symbol: 'SPY', instrumentId: 101 }
    list.vm.$emit('row-action', 'toggle-tag-membership', row, 7)
    list.vm.$emit('row-action', 'toggle-tag-membership', row, 7)

    await vi.waitFor(() => expect(apiPost).toHaveBeenCalledOnce())
    expect(apiPost).toHaveBeenCalledWith('/watchlists/7/items', { instrument_id: 101 })
    expect(watchlistStore.watchlists[0].items).toEqual([])
    resolveAdd?.({ id: 12, instrument_id: 101, symbol: 'SPY', name: 'SPY' })
    await flushPromises()

    expect(watchlistStore.watchlists[0].items).toEqual([
      { id: 12, instrument_id: 101, symbol: 'SPY', name: 'SPY' },
    ])
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    wrapper.unmount()
    queryClient.clear()
  })

  it('routes the personal WatchList surface through the same target-guarded membership mutation', async () => {
    const watchlistStore = useWatchlistStore()
    watchlistStore.watchlists = [
      {
        id: 7,
        name: 'Core',
        is_managed: false,
        is_locked: false,
        items: [{ id: 11, instrument_id: 101, symbol: 'SPY', name: 'SPY' }],
      },
      {
        id: 8,
        name: 'Other',
        is_managed: false,
        is_locked: false,
        items: [{ id: 22, instrument_id: 101, symbol: 'SPY', name: 'SPY' }],
      },
    ]
    apiDelete.mockResolvedValueOnce(undefined)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = shallowMount(WorkstationToolContent, {
      props: {
        tool: {
          instance_key: 'watchlist-personal',
          tool_type: 'watchlist',
          title: 'Core',
          configuration: { personal: true, watchlist_id: 7 },
          link_group: 'blue',
          timeframe_link_group: 'blue',
        } as unknown as WorkspaceWindowState,
        activeWindowKey: 'watchlist-personal',
      },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: {
          ToolWindow: ToolWindowStub,
          VirtualWatchlistTool: VirtualWatchlistToolStub,
        },
      },
    })

    wrapper.getComponent(VirtualWatchlistToolStub).vm.$emit(
      'row-action',
      'toggle-tag-membership',
      { symbol: 'SPY', instrumentId: 101 },
      7,
    )
    await flushPromises()

    expect(apiDelete).toHaveBeenCalledOnce()
    expect(apiDelete).toHaveBeenCalledWith('/watchlists/7/items/11')
    expect(watchlistStore.watchlists[0].items).toEqual([])
    expect(watchlistStore.watchlists[1].items).toEqual([
      { id: 22, instrument_id: 101, symbol: 'SPY', name: 'SPY' },
    ])
    wrapper.unmount()
    queryClient.clear()
  })
})
