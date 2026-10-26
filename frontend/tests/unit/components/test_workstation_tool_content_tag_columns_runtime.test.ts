import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

const { apiGet, apiPost, apiPatch, apiDelete, apiPut } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPatch: vi.fn(),
  apiDelete: vi.fn(),
  apiPut: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  api: {
    get: apiGet,
    post: apiPost,
    patch: apiPatch,
    delete: apiDelete,
    put: apiPut,
  },
}))

import WorkstationToolContent from '@/components/workstation/WorkstationToolContent.vue'
import VirtualWatchlistTool from '@/components/workstation/VirtualWatchlistTool.vue'
import { CHART_PLOT_DRAG_MIME } from '@/lib/workstation/plotDrag'
import { useWatchlistStore } from '@/stores/watchlist'
import { useWorkspaceStore } from '@/stores/workspace'
import { usePanelStore } from '@/stores/chart'
import type { WorkspaceWindowState } from '@/stores/workspace'

const ToolWindowShell = defineComponent({
  name: 'ToolWindow',
  setup(_, { slots }) {
    return () => h('div', { class: 'tool-window-shell' }, slots.default?.())
  },
})

const UPlotChartCustomDateSortStub = defineComponent({
  name: 'UPlotChart',
  emits: ['custom-date-sort-range'],
  setup(_, { emit }) {
    return () => h('button', {
      'data-test': 'emit-custom-date-sort-range',
      onClick: () => emit('custom-date-sort-range', { start: '2024-01-02', end: '2024-01-03' }),
    }, 'Select range')
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

function setupParent(
  targets: Array<Record<string, unknown>>,
  tagWatchlistIds: number[],
  toolConfiguration: Record<string, unknown> = {},
) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const watchlistStore = useWatchlistStore(pinia)
  const workspaceStore = useWorkspaceStore(pinia)
  watchlistStore.watchlists = [
    watchlist(3, 'Primary', [{ id: 11, instrument_id: 101, symbol: 'SPY', name: 'SPDR S&P 500 ETF' }]),
    ...targets,
  ] as never
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = mount(WorkstationToolContent, {
    props: {
      tool: toolFixture({
        ...toolConfiguration,
        tag_watchlist_ids: tagWatchlistIds,
        column_keys: ['symbol', ...tagWatchlistIds.map(id => `tag-watchlist:${id}`)],
      }),
    },
    global: {
      plugins: [pinia, [VueQueryPlugin, { queryClient }]],
      stubs: { ToolWindow: ToolWindowShell },
    },
  })
  return { queryClient, watchlistStore, workspaceStore, wrapper }
}

describe('WorkstationToolContent Tag Column parent mutation path', () => {
  beforeEach(() => {
    apiGet.mockReset().mockResolvedValue([])
    apiPost.mockReset().mockResolvedValue({ id: 22, instrument_id: 101, symbol: 'SPY' })
    apiPatch.mockReset()
    apiDelete.mockReset().mockResolvedValue(undefined)
    apiPut.mockReset().mockResolvedValue(undefined)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('routes ordinary accessible row-menu add and remove clicks through the parent to the selected-list store mutations', async () => {
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

    await wrapper.get('.watchlist__row').trigger('contextmenu', { clientX: 20, clientY: 24 })
    await flushPromises()
    const removeAction = wrapper.findAll('button[role="menuitem"]')
      .find(button => button.text() === 'Remove SPY from Tag · Core')
    expect(removeAction).toBeDefined()
    await removeAction!.trigger('click')
    await flushPromises()

    expect(apiDelete).toHaveBeenCalledWith('/watchlists/7/items/22')
    expect(watchlistStore.watchlists.find(item => item.id === 7)?.items).toEqual([])
    expect(wrapper.get('.watchlist__row').text()).toContain('—')

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

  it('uses the canonical workspace Tag Column target when a mounted tool has a stale virtual snapshot', async () => {
    const { queryClient, watchlistStore, workspaceStore, wrapper } = setupParent(
      [watchlist(7, 'Stale target', []), watchlist(8, 'Canonical target', [])],
      [7],
    )
    await flushPromises()

    workspaceStore.workspace = {
      id: 44,
      user_id: 1,
      name: 'Primary',
      is_default: true,
      position: 0,
      revision: 2,
      schema_version: 1,
      settings: {},
      tabs: [{
        id: 51,
        stable_key: 'main',
        name: 'Main',
        position: 0,
        layout_config: {},
        active_window_key: 'personal-watchlist-test',
        windows: [toolFixture({
          tag_watchlist_ids: [8],
          column_keys: ['symbol', 'tag-watchlist:8'],
        })],
      }],
    }
    await flushPromises()

    await wrapper.get('.watchlist__row').trigger('contextmenu', { clientX: 20, clientY: 24 })
    await flushPromises()
    const actions = wrapper.findAll('button[role="menuitem"]')
    expect(actions.some(button => button.text() === 'Add SPY to Tag · Canonical target')).toBe(true)
    expect(actions.some(button => button.text().includes('Stale target'))).toBe(false)

    await actions.find(button => button.text() === 'Add SPY to Tag · Canonical target')!.trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/watchlists/8/items', { instrument_id: 101 })
    expect(watchlistStore.watchlists.find(item => item.id === 8)?.items).toEqual([
      { id: 22, instrument_id: 101, symbol: 'SPY' },
    ])
    expect(watchlistStore.watchlists.find(item => item.id === 7)?.items).toEqual([])

    wrapper.unmount()
    queryClient.clear()
  })

  it('keeps failed Tag Column addition out of membership and shows the parent error', async () => {
    const { queryClient, watchlistStore, wrapper } = setupParent(
      [watchlist(7, 'Core', [])],
      [7],
    )
    apiPost.mockRejectedValueOnce(new Error('offline test transport'))
    await flushPromises()

    await wrapper.get('.watchlist__row').trigger('contextmenu', { clientX: 20, clientY: 24 })
    await flushPromises()
    const addAction = wrapper.findAll('button[role="menuitem"]')
      .find(button => button.text() === 'Add SPY to Tag · Core')
    expect(addAction).toBeDefined()
    await addAction!.trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/watchlists/7/items', { instrument_id: 101 })
    expect(watchlistStore.watchlists.find(item => item.id === 7)?.items).toEqual([])
    expect(wrapper.get('.watchlist__row').text()).toContain('—')
    expect(wrapper.get('[role="alert"]').text()).toBe('Unable to add SPY to Core.')
    expect(wrapper.emitted('configuration')).toBeUndefined()

    wrapper.unmount()
    queryClient.clear()
  })

  it('keeps failed Tag Column membership removal visible and preserves its configuration', async () => {
    const { queryClient, wrapper } = setupParent(
      [watchlist(7, 'Core', [{ id: 24, instrument_id: 101, symbol: 'SPY' }])],
      [7],
    )
    apiDelete.mockRejectedValueOnce(new Error('offline test transport'))
    await flushPromises()

    await wrapper.get('.watchlist__row').trigger('contextmenu', { clientX: 20, clientY: 24 })
    await flushPromises()
    const removeAction = wrapper.findAll('button[role="menuitem"]')
      .find(button => button.text() === 'Remove SPY from Tag · Core')
    expect(removeAction).toBeDefined()
    await removeAction!.trigger('click')
    await flushPromises()

    expect(apiDelete).toHaveBeenCalledWith('/watchlists/7/items/24')
    expect(wrapper.get('.watchlist__row').text()).toContain('In')
    expect(wrapper.get('[role="alert"]').text()).toBe('Unable to remove SPY from Core.')
    expect(wrapper.emitted('configuration')).toBeUndefined()

    wrapper.unmount()
    queryClient.clear()
  })

  it('renames, copies, and deletes a selected WatchList without dropping Tag Column settings', async () => {
    const renamed = watchlist(3, 'Primary Renamed', [{ id: 11, instrument_id: 101, symbol: 'SPY' }])
    const copied = watchlist(9, 'Primary Renamed (copy)', [{ id: 19, instrument_id: 101, symbol: 'SPY' }])
    const { queryClient, watchlistStore, wrapper } = setupParent(
      [watchlist(7, 'Core', [])],
      [7],
    )
    await flushPromises()

    apiPatch.mockResolvedValueOnce(renamed)
    await wrapper.get('input[aria-label="Personal watchlist name"]').setValue('Primary Renamed')
    await wrapper.get('button[aria-label="Rename personal watchlist"]').trigger('click')
    await flushPromises()

    expect(apiPatch).toHaveBeenCalledWith('/watchlists/3', { name: 'Primary Renamed' })
    expect(watchlistStore.watchlists.find(item => item.id === 3)?.name).toBe('Primary Renamed')

    apiPost.mockResolvedValueOnce(copied)
    await wrapper.get('button[aria-label="Copy personal watchlist"]').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/watchlists/3/copy', {})
    expect(watchlistStore.watchlists.find(item => item.id === 9)?.name).toBe('Primary Renamed (copy)')
    expect(wrapper.get('select[aria-label="Personal watchlist"]').element.value).toBe('9')
    expect(wrapper.emitted('configuration')?.at(-1)).toEqual([
      'personal-watchlist-test',
      expect.objectContaining({
        watchlist_id: 9,
        tag_watchlist_ids: [7],
        column_keys: ['symbol', 'tag-watchlist:7'],
      }),
    ])

    vi.spyOn(window, 'confirm').mockReturnValue(true)
    await wrapper.get('button[aria-label="Delete personal watchlist"]').trigger('click')
    await flushPromises()

    expect(apiDelete).toHaveBeenCalledWith('/watchlists/9')
    expect(watchlistStore.watchlists.some(item => item.id === 9)).toBe(false)
    expect(wrapper.get('select[aria-label="Personal watchlist"]').element.value).toBe('3')
    expect(wrapper.emitted('configuration')?.at(-1)).toEqual([
      'personal-watchlist-test',
      expect.objectContaining({
        watchlist_id: 3,
        tag_watchlist_ids: [7],
        column_keys: ['symbol', 'tag-watchlist:7'],
      }),
    ])

    wrapper.unmount()
    queryClient.clear()
  })

  it('recomputes the mounted Tag Column remove affordance when its target becomes locked', async () => {
    const { queryClient, watchlistStore, wrapper } = setupParent(
      [watchlist(7, 'Core', [{ id: 24, instrument_id: 101, symbol: 'SPY' }])],
      [7],
    )
    await flushPromises()
    await wrapper.get('.watchlist__row').trigger('contextmenu', { clientX: 20, clientY: 24 })
    await flushPromises()

    const removeAction = wrapper.findAll('button[role="menuitem"]')
      .find(button => button.text() === 'Remove SPY from Tag · Core')
    expect(removeAction).toBeDefined()
    expect(removeAction!.element.disabled).toBe(false)

    watchlistStore.watchlists.find(item => item.id === 7)!.is_locked = true
    await flushPromises()

    expect(removeAction!.element.disabled).toBe(true)
    expect(apiDelete).not.toHaveBeenCalled()

    wrapper.unmount()
    queryClient.clear()
  })

  it('routes ordinary list copy and move actions through the parent transfer mutation', async () => {
    const copied = { id: 22, instrument_id: 101, symbol: 'SPY', name: 'SPDR S&P 500 ETF' }
    const moved = { id: 23, instrument_id: 101, symbol: 'SPY', name: 'SPDR S&P 500 ETF' }
    const { queryClient, watchlistStore, wrapper } = setupParent(
      [watchlist(7, 'Copy target', []), watchlist(8, 'Move target', [])],
      [],
    )
    await flushPromises()

    await wrapper.get('.watchlist__row').trigger('contextmenu', { clientX: 20, clientY: 24 })
    await flushPromises()
    await wrapper.get('select[aria-label="Target watchlist"]').setValue('7')
    apiPost.mockResolvedValueOnce([copied])
    await wrapper.get('button[data-membership-action="copy"]').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenNthCalledWith(1, '/watchlists/7/items/transfer-batch', {
      source_watchlist_id: 3,
      item_ids: [11],
      mode: 'copy',
    })
    expect(watchlistStore.watchlists.find(item => item.id === 3)?.items).toHaveLength(1)
    expect(watchlistStore.watchlists.find(item => item.id === 7)?.items).toEqual([copied])

    await wrapper.get('.watchlist__row').trigger('contextmenu', { clientX: 20, clientY: 24 })
    await flushPromises()
    await wrapper.get('select[aria-label="Target watchlist"]').setValue('8')
    apiPost.mockResolvedValueOnce([moved])
    await wrapper.get('button[data-membership-action="move"]').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenNthCalledWith(2, '/watchlists/8/items/transfer-batch', {
      source_watchlist_id: 3,
      item_ids: [11],
      mode: 'move',
    })
    expect(watchlistStore.watchlists.find(item => item.id === 3)?.items).toEqual([])
    expect(watchlistStore.watchlists.find(item => item.id === 8)?.items).toEqual([moved])

    wrapper.unmount()
    queryClient.clear()
  })

  it('publishes Tag Column add and remove configuration from the mounted parent', async () => {
    const { queryClient, wrapper } = setupParent(
      [watchlist(7, 'Core', [])],
      [],
    )
    await flushPromises()

    await wrapper.get('button[aria-label="Columns"]').trigger('click')
    await wrapper.get('select[aria-label="Tag Column target WatchList"]').setValue('7')
    await wrapper.get('button[aria-label="Add Tag Column"]').trigger('click')

    expect(wrapper.emitted('configuration')?.at(-1)).toEqual([
      'personal-watchlist-test',
      expect.objectContaining({
        tag_watchlist_ids: [7],
        column_keys: ['symbol', 'tag-watchlist:7'],
      }),
    ])

    // Model the owning workspace applying the emitted configuration before
    // the user removes the same target through the mounted child editor.
    await wrapper.setProps({
      tool: toolFixture({
        tag_watchlist_ids: [7],
        column_keys: ['symbol', 'tag-watchlist:7'],
      }),
    })
    await flushPromises()
    await wrapper.findAll('button[aria-label="Remove Tag · Core"]').at(-1)?.trigger('click')

    expect(wrapper.emitted('configuration')?.at(-1)).toEqual([
      'personal-watchlist-test',
      expect.objectContaining({
        tag_watchlist_ids: [],
        column_keys: ['symbol'],
      }),
    ])

    wrapper.unmount()
    queryClient.clear()
  })

  it('keeps Tag Column visibility when a saved column set is saved, applied, and deleted', async () => {
    const { queryClient, wrapper } = setupParent(
      [watchlist(7, 'Core', [])],
      [7],
    )
    const savedSet = {
      stable_key: 'tag-view-v1',
      name: 'Tagged view',
      version: 1,
      payload: {
        configuration: {
          column_keys: ['symbol', 'tag-watchlist:7'],
          pinned_boolean_keys: [],
          column_groups: {},
          stacked_column_keys: [],
        },
        schema_version: 1,
      },
    }
    let savedSetLoads = 0
    apiGet.mockImplementation((path: string, params?: { kind?: string }) => {
      if (path === '/workspaces/library/items' && params?.kind === 'column_set') {
        savedSetLoads += 1
        return Promise.resolve(savedSetLoads <= 3 ? [savedSet] : [])
      }
      return Promise.resolve([])
    })
    await flushPromises()

    await wrapper.get('button[aria-label="Column sets"]').trigger('click')
    await flushPromises()
    await wrapper.get('input[aria-label="Column set name"]').setValue('Current tag view')
    await wrapper.get('button[aria-label="Save column set"]').trigger('click')
    await flushPromises()

    expect(apiPut).toHaveBeenCalledWith(
      expect.stringMatching(/^\/workspaces\/library\/items\/column_set\/current-tag-view-/),
      expect.objectContaining({
        payload: expect.objectContaining({
          configuration: expect.objectContaining({ column_keys: ['symbol', 'tag-watchlist:7'] }),
        }),
      }),
    )
    await wrapper.get('button[aria-label="Apply column set Tagged view version 1"]').trigger('click')
    expect(wrapper.emitted('columns')?.at(-1)).toEqual([
      'personal-watchlist-test',
      ['symbol', 'tag-watchlist:7'],
    ])

    await wrapper.get('button[aria-label="Column sets"]').trigger('click')
    await flushPromises()
    await wrapper.get('button[aria-label="Delete column set Tagged view"]').trigger('click')
    await flushPromises()
    expect(apiDelete).toHaveBeenCalledWith('/workspaces/library/items/column_set/tag-view-v1')

    wrapper.unmount()
    queryClient.clear()
  })

  it('routes a mounted WatchList membership toggle through the parent for add and remove', async () => {
    const { queryClient, watchlistStore, wrapper } = setupParent(
      [watchlist(7, 'Core', [])],
      [7],
    )
    await flushPromises()
    const child = wrapper.findComponent(VirtualWatchlistTool)
    const selectedRow = { symbol: 'SPY', instrumentId: 101 }

    child.vm.$emit('row-action', 'toggle-tag-membership', selectedRow, 7)
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/watchlists/7/items', { instrument_id: 101 })
    expect(watchlistStore.watchlists.find(item => item.id === 7)?.items).toEqual([
      expect.objectContaining({ instrument_id: 101, symbol: 'SPY' }),
    ])

    child.vm.$emit('row-action', 'toggle-tag-membership', selectedRow, 7)
    await flushPromises()

    expect(apiDelete).toHaveBeenCalledWith('/watchlists/7/items/22')
    expect(watchlistStore.watchlists.find(item => item.id === 7)?.items).toEqual([])

    wrapper.unmount()
    queryClient.clear()
  })

  it('routes membership actions from a non-personal WatchList through the mounted parent', async () => {
    const { queryClient, watchlistStore, wrapper } = setupParent(
      [watchlist(7, 'Core', [])],
      [7],
      { personal: false },
    )
    await flushPromises()
    const child = wrapper.findComponent(VirtualWatchlistTool)

    child.vm.$emit('row-action', 'toggle-tag-membership', { symbol: 'SPY', instrumentId: 101 }, 7)
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/watchlists/7/items', { instrument_id: 101 })
    expect(watchlistStore.watchlists.find(item => item.id === 7)?.items).toEqual([
      expect.objectContaining({ instrument_id: 101, symbol: 'SPY' }),
    ])

    wrapper.unmount()
    queryClient.clear()
  })

  it('adds a chart indicator dropped on the mounted WatchList to its visible column configuration', async () => {
    const { queryClient, wrapper } = setupParent([watchlist(7, 'Core', [])], [])
    await flushPromises()
    const payload = {
      version: 1,
      kind: 'chart-plot',
      indicator: {
        type: 'rsi', params: { length: 14 }, output: 'rsi', timeframe: 'D1',
        label: 'RSI (14)', sourceWindowKey: 'chart-primary',
      },
    }
    const dataTransfer = {
      types: [CHART_PLOT_DRAG_MIME],
      getData: (type: string) => type === CHART_PLOT_DRAG_MIME ? JSON.stringify(payload) : '',
      dropEffect: 'none',
    }
    const target = wrapper.get('.watchlist')

    await target.trigger('dragenter', { dataTransfer })
    await target.trigger('dragover', { dataTransfer })
    expect(wrapper.get('.watchlist__plot-drop-hint').text()).toContain('Drop to add')
    await target.trigger('dragleave', { dataTransfer, relatedTarget: null })
    expect(wrapper.find('.watchlist__plot-drop-hint').exists()).toBe(false)
    await target.trigger('dragenter', { dataTransfer })
    await target.trigger('dragover', { dataTransfer })
    await target.trigger('drop', { dataTransfer })
    await flushPromises()

    expect(wrapper.find('.watchlist__plot-drop-hint').exists()).toBe(false)
    expect(wrapper.emitted('configuration')?.at(-1)).toEqual([
      'personal-watchlist-test',
      expect.objectContaining({
        column_keys: ['symbol', 'indicator:rsi:{"length":14}:D1:rsi'],
        indicator_columns: [expect.objectContaining({
          name: 'RSI (14)', indicator: 'rsi', params: { length: 14 }, timeframe: 'D1', output: 'rsi',
        })],
      }),
    ])

    wrapper.unmount()
    queryClient.clear()
  })

  it('adds a dropped Python plot as a visible WatchList column without changing indicator columns', async () => {
    const { queryClient, wrapper } = setupParent([watchlist(7, 'Core', [])], [])
    await flushPromises()
    const payload = {
      version: 1,
      kind: 'python-plot',
      python: { codeVersionId: 74, name: 'Daily breadth', timeframe: 'D1', sourceWindowKey: 'study-1' },
    }
    const dataTransfer = {
      types: [CHART_PLOT_DRAG_MIME],
      getData: (type: string) => type === CHART_PLOT_DRAG_MIME ? JSON.stringify(payload) : '',
      dropEffect: 'none',
    }

    await wrapper.get('.watchlist').trigger('drop', { dataTransfer })
    await flushPromises()

    expect(wrapper.emitted('configuration')?.at(-1)).toEqual([
      'personal-watchlist-test',
      expect.objectContaining({
        column_keys: ['symbol', 'python:74'],
        python_columns: [{ code_version_id: 74, name: 'Daily breadth', timeframe: 'D1' }],
      }),
    ])

    wrapper.unmount()
    queryClient.clear()
  })

  it('keeps a multi-output chart plot out of WatchList columns until an output is selected', async () => {
    const { queryClient, wrapper } = setupParent([watchlist(7, 'Core', [])], [])
    await flushPromises()
    const payload = {
      version: 1,
      kind: 'chart-plot',
      indicator: {
        type: 'macd', params: { fast: 12, slow: 26, signal: 9 }, timeframe: 'D1',
        label: 'MACD', sourceWindowKey: 'chart-primary',
      },
    }
    const dataTransfer = {
      types: [CHART_PLOT_DRAG_MIME],
      getData: (type: string) => type === CHART_PLOT_DRAG_MIME ? JSON.stringify(payload) : '',
      dropEffect: 'none',
    }

    await wrapper.get('.watchlist').trigger('drop', { dataTransfer })
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('explicit output is selected')
    expect(wrapper.emitted('configuration')).toBeUndefined()

    wrapper.unmount()
    queryClient.clear()
  })

  it('persists a dropped technical condition before exposing its Boolean WatchList column', async () => {
    const { queryClient, wrapper } = setupParent([watchlist(7, 'Core', [])], [])
    await flushPromises()
    const payload = {
      version: 1,
      kind: 'technical-condition',
      condition: { type: 'indicator_threshold', indicator: 'rsi', params: { length: 14 }, output: 'rsi', op: 'gt', value: 50 },
      timeframe: 'D1', label: 'RSI above 50', sourceWindowKey: 'chart-primary',
    }
    const dataTransfer = {
      types: [CHART_PLOT_DRAG_MIME],
      getData: (type: string) => type === CHART_PLOT_DRAG_MIME ? JSON.stringify(payload) : '',
      dropEffect: 'none',
    }

    await wrapper.get('.watchlist').trigger('drop', { dataTransfer })
    await flushPromises()

    expect(apiPut).toHaveBeenCalledWith('/workspaces/library/conditions/drag-rsi-above-50-d1', expect.objectContaining({
      name: 'RSI above 50',
      condition: payload.condition,
      dependency_metadata: { source: 'technical-condition-drag', timeframe: 'D1' },
    }))
    expect(apiPost).toHaveBeenCalledWith('/screeners/from-condition/drag-rsi-above-50-d1', {
      name: 'RSI above 50 Boolean', universe_type: 'all', timeframe: 'D1',
    })
    expect(apiPost).toHaveBeenCalledWith('/screeners/22/run', {})
    expect(wrapper.emitted('configuration')?.at(-1)).toEqual([
      'personal-watchlist-test',
      expect.objectContaining({
        column_keys: ['symbol', 'condition:drag-rsi-above-50-d1'],
        condition_columns: [{
          key: 'condition:drag-rsi-above-50-d1', name: 'RSI above 50', screener_id: 22, timeframe: 'D1',
        }],
      }),
    ])

    wrapper.unmount()
    queryClient.clear()
  })

  it('does not expose a Boolean column when saving its dropped condition fails', async () => {
    const { queryClient, wrapper } = setupParent([watchlist(7, 'Core', [])], [])
    await flushPromises()
    apiPut.mockRejectedValueOnce(new Error('condition library unavailable'))
    const payload = {
      version: 1,
      kind: 'technical-condition',
      condition: { type: 'indicator_threshold', indicator: 'rsi', params: { length: 14 }, output: 'rsi', op: 'gt', value: 50 },
      timeframe: 'D1', label: 'RSI above 50', sourceWindowKey: 'chart-primary',
    }
    const dataTransfer = {
      types: [CHART_PLOT_DRAG_MIME],
      getData: (type: string) => type === CHART_PLOT_DRAG_MIME ? JSON.stringify(payload) : '',
      dropEffect: 'none',
    }

    await wrapper.get('.watchlist').trigger('drop', { dataTransfer })
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('Unable to create RSI above 50 Boolean column')
    expect(wrapper.emitted('configuration')).toBeUndefined()
    expect(apiPost).not.toHaveBeenCalledWith('/screeners/from-condition/drag-rsi-above-50-d1', expect.anything())

    wrapper.unmount()
    queryClient.clear()
  })

  it('publishes an ordinary personal WatchList selection and renders that list through the parent', async () => {
    vi.useFakeTimers()
    const { queryClient, wrapper } = setupParent(
      [watchlist(7, 'Core', [{ id: 21, instrument_id: 202, symbol: 'XLE', name: 'Energy' }])],
      [],
    )

    try {
      await flushPromises()
      await wrapper.get('select[aria-label="Personal watchlist"]').setValue('7')
      await flushPromises()

      expect(wrapper.get('.watchlist__row').text()).toContain('XLE')
      expect(wrapper.emitted('configuration')?.at(-1)).toEqual([
        'personal-watchlist-test',
        expect.objectContaining({
          watchlist_id: 7,
          tag_watchlist_ids: [],
          column_keys: ['symbol'],
        }),
      ])
    } finally {
      wrapper.unmount()
      queryClient.clear()
      vi.clearAllTimers()
      vi.useRealTimers()
    }
  })

  it('creates a named personal WatchList through the parent and preserves Tag Column configuration', async () => {
    const { queryClient, watchlistStore, wrapper } = setupParent(
      [watchlist(7, 'Core', [])],
      [7],
    )
    await flushPromises()

    await wrapper.get('button[aria-label="Create personal watchlist"]').trigger('click')
    expect(apiPost).not.toHaveBeenCalled()

    await wrapper.get('input[aria-label="Personal watchlist name"]').setValue('New Research')
    apiPost.mockResolvedValueOnce(watchlist(9, 'New Research', []))
    await wrapper.get('button[aria-label="Create personal watchlist"]').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/watchlists', {
      name: 'New Research',
      description: undefined,
    })
    expect(watchlistStore.watchlists.find(item => item.id === 9)?.name).toBe('New Research')
    expect(wrapper.get('select[aria-label="Personal watchlist"]').element.value).toBe('9')
    expect(wrapper.emitted('configuration')?.at(-1)).toEqual([
      'personal-watchlist-test',
      expect.objectContaining({
        watchlist_id: 9,
        tag_watchlist_ids: [7],
        column_keys: ['symbol', 'tag-watchlist:7'],
      }),
    ])

    wrapper.unmount()
    queryClient.clear()
  })

  it('preserves creation state after failure and allows a successful retry', async () => {
    const { queryClient, watchlistStore, wrapper } = setupParent(
      [watchlist(7, 'Core', [])],
      [7],
    )
    await flushPromises()
    const configEventsBefore = wrapper.emitted('configuration')?.length ?? 0
    apiPost.mockRejectedValueOnce(new Error('offline test transport'))

    const nameInput = wrapper.get('input[aria-label="Personal watchlist name"]')
    await nameInput.setValue('Retry Research')
    await wrapper.get('button[aria-label="Create personal watchlist"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toBe('Unable to create personal watchlist')
    expect((nameInput.element as HTMLInputElement).value).toBe('Retry Research')
    expect(wrapper.get('select[aria-label="Personal watchlist"]').element.value).toBe('3')
    expect(watchlistStore.watchlists.map(item => item.id)).toEqual([3, 7])
    expect(apiPost).toHaveBeenCalledWith('/watchlists', {
      name: 'Retry Research',
      description: undefined,
    })
    expect(wrapper.emitted('configuration')?.length ?? 0).toBe(configEventsBefore)

    apiPost.mockResolvedValueOnce(watchlist(9, 'Retry Research', []))
    await wrapper.get('button[aria-label="Create personal watchlist"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect((nameInput.element as HTMLInputElement).value).toBe('Retry Research')
    expect(wrapper.get('select[aria-label="Personal watchlist"]').element.value).toBe('9')
    expect(watchlistStore.watchlists.map(item => item.id)).toEqual([3, 7, 9])
    expect(apiPost).toHaveBeenNthCalledWith(2, '/watchlists', {
      name: 'Retry Research',
      description: undefined,
    })
    expect(wrapper.emitted('configuration')?.at(-1)).toEqual([
      'personal-watchlist-test',
      expect.objectContaining({
        watchlist_id: 9,
        tag_watchlist_ids: [7],
        column_keys: ['symbol', 'tag-watchlist:7'],
      }),
    ])

    wrapper.unmount()
    queryClient.clear()
  })

  it('adds a resolved symbol through the selected-list parent without losing Tag Columns', async () => {
    const item = { id: 25, instrument_id: 202, symbol: 'XLE', name: 'Energy Select Sector SPDR Fund' }
    const { queryClient, watchlistStore, wrapper } = setupParent(
      [watchlist(7, 'Core', [])],
      [7],
    )
    apiGet.mockImplementation(async path => {
      if (path === '/instruments/XLE') return { id: 202, symbol: 'XLE' }
      return []
    })
    apiPost.mockResolvedValueOnce(item)
    await flushPromises()

    await wrapper.get('input[aria-label="Add symbol to personal watchlist"]').setValue('xle')
    await wrapper.get('button[aria-label="Add symbol to personal watchlist"]').trigger('click')
    await flushPromises()

    expect(apiPost).toHaveBeenCalledWith('/watchlists/3/items', { instrument_id: 202 })
    expect(watchlistStore.watchlists.find(list => list.id === 3)?.items).toContainEqual(item)
    expect(wrapper.emitted('configuration')?.at(-1)).toEqual([
      'personal-watchlist-test',
      expect.objectContaining({
        watchlist_id: 3,
        tag_watchlist_ids: [7],
        column_keys: ['symbol', 'tag-watchlist:7'],
      }),
    ])

    wrapper.unmount()
    queryClient.clear()
  })

  it('keeps an unresolved symbol draft and leaves the selected list unchanged', async () => {
    const { queryClient, watchlistStore, wrapper } = setupParent(
      [watchlist(7, 'Core', [])],
      [7],
    )
    await flushPromises()
    apiGet.mockRejectedValueOnce(new Error('API GET /instruments/ZZZZ → 404: {"detail":"not found"}'))
    const configEventsBefore = wrapper.emitted('configuration')?.length ?? 0

    const symbolInput = wrapper.get('input[aria-label="Add symbol to personal watchlist"]')
    await symbolInput.setValue('zzzz')
    await wrapper.get('button[aria-label="Add symbol to personal watchlist"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('ZZZZ could not be added')
    expect((symbolInput.element as HTMLInputElement).value).toBe('zzzz')
    expect(apiPost).not.toHaveBeenCalled()
    expect(watchlistStore.watchlists.find(item => item.id === 3)?.items).toEqual([
      { id: 11, instrument_id: 101, symbol: 'SPY', name: 'SPDR S&P 500 ETF' },
    ])
    expect(watchlistStore.watchlists.find(item => item.id === 7)?.items).toEqual([])
    expect(wrapper.emitted('configuration')?.length ?? 0).toBe(configEventsBefore)

    wrapper.unmount()
    queryClient.clear()
  })

  it('routes an ordinary row selection through the mounted parent with its instrument identity', async () => {
    const { queryClient, wrapper } = setupParent(
      [watchlist(7, 'Core', [{ id: 21, instrument_id: 202, symbol: 'XLE', name: 'Energy' }])],
      [],
    )
    await flushPromises()

    await wrapper.get('.watchlist__row').trigger('click')

    expect(wrapper.emitted('select')).toEqual([['SPY', 101]])

    wrapper.unmount()
    queryClient.clear()
  })
})

describe('WorkstationToolContent Custom Date Sort coverage identity', () => {
  beforeEach(() => {
    apiGet.mockReset().mockImplementation((path: string) => {
      if (path === '/coverage/instruments/SPY/ohlcv') {
        return Promise.resolve({
          symbol: 'QQQ',
          timeframe: 'D1',
          adjusted: true,
          requested_start: '2024-01-02',
          requested_end: '2024-01-03',
          explanation: '',
          lineage: {
            source_lineage: 'provider_only',
            unknown_bar_count: 0,
            provider_bar_count: 2,
            derived_bar_count: 0,
            source_timeframes: ['D1'],
          },
        })
      }
      return Promise.resolve([])
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('reports mismatched coverage identity without reading bars or presenting a value', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const chartStore = usePanelStore('workstation-custom-date-sort-identity-test')
    chartStore.symbol = 'SPY'
    chartStore.timeframe = 'D1'
    chartStore.error = null
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const chart = toolFixture({ symbol: 'SPY' })
    chart.instance_key = 'custom-date-sort-identity-test'
    chart.tool_type = 'chart'
    chart.title = 'SPY chart'
    chart.configuration = { symbol: 'SPY' }
    const wrapper = mount(WorkstationToolContent, {
      props: { tool: chart },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: {
          UPlotChart: UPlotChartCustomDateSortStub,
          ChartPlotLibrary: { template: '<div />' },
          ChartTemplateControl: { template: '<div />' },
          DrawingToolbar: { template: '<div />' },
          ToolWindow: ToolWindowShell,
        },
      },
    })

    await wrapper.get('[data-test="emit-custom-date-sort-range"]').trigger('click')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Coverage was returned for a different instrument.'))

    expect(apiGet).toHaveBeenCalledWith(
      '/coverage/instruments/SPY/ohlcv',
      expect.objectContaining({ timeframe: 'D1', mode: 'historical', adjusted: true }),
      expect.any(Object),
    )
    expect(wrapper.text()).not.toContain('+0.00%')

    wrapper.unmount()
    queryClient.clear()
  })

  it('discards a coverage response that resolves after the chart symbol changes', async () => {
    let resolveCoverage!: (coverage: Record<string, unknown>) => void
    apiGet.mockImplementation((path: string) => {
      if (path === '/coverage/instruments/SPY/ohlcv') {
        return new Promise(resolve => { resolveCoverage = resolve })
      }
      return Promise.resolve([])
    })
    const pinia = createPinia()
    setActivePinia(pinia)
    const chartStore = usePanelStore('workstation-custom-date-sort-identity-test')
    chartStore.symbol = 'SPY'
    chartStore.timeframe = 'D1'
    chartStore.error = null
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const chart = toolFixture({ symbol: 'SPY' })
    chart.instance_key = 'custom-date-sort-identity-test'
    chart.tool_type = 'chart'
    chart.title = 'SPY chart'
    chart.configuration = { symbol: 'SPY' }
    const wrapper = mount(WorkstationToolContent, {
      props: { tool: chart },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: {
          UPlotChart: UPlotChartCustomDateSortStub,
          ChartPlotLibrary: { template: '<div />' },
          ChartTemplateControl: { template: '<div />' },
          DrawingToolbar: { template: '<div />' },
          ToolWindow: ToolWindowShell,
        },
      },
    })

    await wrapper.get('[data-test="emit-custom-date-sort-range"]').trigger('click')
    await vi.waitFor(() => expect(resolveCoverage).toBeTypeOf('function'))
    chartStore.symbol = 'QQQ'
    await wrapper.vm.$nextTick()
    resolveCoverage({ symbol: 'SPY', explanation: 'stale result' })
    await flushPromises()

    expect(wrapper.find('.chart-tool__custom-date-sort').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('stale result')

    wrapper.unmount()
    queryClient.clear()
  })
})
