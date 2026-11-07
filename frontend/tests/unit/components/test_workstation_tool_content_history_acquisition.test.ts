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
import { refreshMountedWorkstationChartPanels, usePanelStore } from '@/stores/chart'
import { clearOhlcvRequestCache } from '@/lib/workstation/ohlcvRequests'
import { useWorkspaceStore } from '@/stores/workspace'
import type { WorkspaceWindowState } from '@/stores/workspace'

const ToolWindowShell = defineComponent({
  name: 'ToolWindow',
  props: ['title', 'symbol'],
  emits: ['update:timeframe'],
  setup(props, { slots, emit }) {
    return () => h('div', { class: 'tool-window-shell', 'data-symbol': props.symbol }, [
      props.symbol ? h('span', { class: 'tool-window__symbol' }, String(props.symbol)) : null,
      h('button', { class: 'choose-weekly', onClick: () => emit('update:timeframe', 'W1') }, 'Weekly'),
      h('button', { class: 'choose-monthly', onClick: () => emit('update:timeframe', 'MN') }, 'Monthly'),
      slots.default?.(),
    ])
  },
})

const EmptyChartStub = defineComponent({
  name: 'UPlotChart',
  template: '<div class="uplot" data-test="local-chart-surface" />',
})

function chartFixture(): WorkspaceWindowState {
  return {
    id: 31,
    instance_key: 'workstation-history-acquisition-test',
    tool_type: 'chart',
    title: 'Test chart',
    link_group: 'blue',
    configuration: { symbol: 'TCNEW' },
    style: {},
    state_schema_version: 1,
    position: 0,
  }
}

function mountedChartTool(instanceKey: string, linkGroup: 'blue' | 'red' = 'blue'): WorkspaceWindowState {
  return { ...chartFixture(), instance_key: instanceKey, link_group: linkGroup, configuration: {} }
}

function mountChartTool(tool: WorkspaceWindowState, pinia: ReturnType<typeof createPinia>, queryClient: QueryClient, activeWindowKey = 'another-chart') {
  return mount(WorkstationToolContent, {
    props: { tool, activeWindowKey },
    global: {
      plugins: [pinia, [VueQueryPlugin, { queryClient }]],
      stubs: {
        UPlotChart: EmptyChartStub,
        ChartPlotLibrary: { template: '<div />' },
        ChartTemplateControl: { template: '<div />' },
        DrawingToolbar: { template: '<div />' },
        ToolWindow: ToolWindowShell,
      },
    },
  })
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

describe('WorkstationToolContent missing chart history entrypoint', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    clearOhlcvRequestCache()
    vi.stubGlobal('crypto', { randomUUID: () => 'd145917b-65a1-4d45-8fb8-968bc47df606' })
    apiGet.mockResolvedValue([])
    apiPost.mockResolvedValue({})
    apiPatch.mockResolvedValue({})
    apiDelete.mockResolvedValue(undefined)
    apiPut.mockResolvedValue(undefined)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('renders and loads a cloned benchmark-universe tool from semantic role, not its remapped window key', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const workspaceStore = useWorkspaceStore(pinia)
    workspaceStore.marketGroups['us-benchmarks'] = {
      members: [],
      provenance: { benchmark_families: [{ logical_key: 'sp500', name: 'S&P 500' }] },
    } as never
    apiGet.mockImplementation((path: string) => {
      if (path === '/market-groups/sp500') return Promise.resolve({ members: [], provenance: {} })
      if (path === '/analysis/benchmark-families/sp500/overview') return Promise.resolve({ mappings: [{ role: 'cap_weight', symbol: 'SPY', label: 'Cap-weight proxy', verification_state: 'verified', holdings_available: true }] })
      if (path === '/analysis/benchmark-families/readiness') return Promise.resolve({ status: 'ready', families: [], provider_probe_evidence: [] })
      return Promise.resolve([])
    })
    const tool: WorkspaceWindowState = {
      id: -32,
      instance_key: 'benchmark-list-clone-abc123',
      tool_type: 'watchlist',
      title: 'Benchmarks',
      link_group: 'blue',
      configuration: { workspace_role: 'benchmark-universe', benchmark_family_key: 'sp500' },
      style: {},
      state_schema_version: 1,
      position: 0,
    }
    const wrapper = mount(WorkstationToolContent, {
      props: { tool, activeWindowKey: tool.instance_key },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient: new QueryClient({ defaultOptions: { queries: { retry: false } } }) }]],
        stubs: {
          VirtualWatchlistTool: true,
          ToolWindow: ToolWindowShell,
          UPlotChart: EmptyChartStub,
          ChartPlotLibrary: true,
          ChartTemplateControl: true,
          DrawingToolbar: true,
        },
      },
    })

    await flushPromises()

    expect(wrapper.get('select[aria-label="Benchmark family"]').element).toHaveProperty('value', 'sp500')
    expect(wrapper.get('[aria-label="Selected benchmark family roles"]').text()).toContain('SPY')
    expect(apiGet).toHaveBeenCalledWith('/market-groups/sp500')
    wrapper.unmount()
  })

  it('removes chart drawing controls from inactive docked tools and restores them only for the active chart', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const tool = chartFixture()
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const wrapper = mount(WorkstationToolContent, {
      props: { tool, activeWindowKey: 'another-chart' },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: {
          UPlotChart: EmptyChartStub,
          ChartPlotLibrary: { template: '<div />' },
          ChartTemplateControl: { template: '<div />' },
          DrawingToolbar: { template: '<div data-test="chart-drawing-toolbar" />' },
          ToolWindow: ToolWindowShell,
        },
      },
    })

    expect(wrapper.find('[data-test="chart-drawing-toolbar"]').exists()).toBe(false)
    await wrapper.setProps({ activeWindowKey: tool.instance_key })
    expect(wrapper.find('[data-test="chart-drawing-toolbar"]').exists()).toBe(true)
    await wrapper.setProps({ activeWindowKey: 'another-chart' })
    expect(wrapper.find('[data-test="chart-drawing-toolbar"]').exists()).toBe(false)

    wrapper.unmount()
    queryClient.clear()
  })

  it('offers one explicit action only on the focused empty chart and refreshes that panel from local bars', async () => {
    const instrumentId = 990014
    const bar = {
      ts: '2026-10-27T12:34:00Z',
      open: 10,
      high: 11,
      low: 9,
      close: 10.5,
      volume: 100,
    }
    let historyAcquired = false
    const localReadbacks: Array<{ path: string; returnedBars: number }> = []
    apiGet.mockImplementation((path: string) => {
      if (path === '/coverage/instruments/TCNEW/ohlcv') {
        return Promise.resolve({
          status: 'missing',
          bar_count: 0,
          missing_slices: [{ start: '2026-10-26T00:00:00Z', end: '2026-10-27T00:00:00Z' }],
        })
      }
      if (path === '/instruments/TCNEW') {
        return Promise.resolve({ id: instrumentId, symbol: 'TCNEW', name: 'Controlled fixture symbol', stats: { week52_high: 12 } })
      }
      if (path === `/instruments/${instrumentId}/history-availability`) {
        return Promise.resolve({ instrument_id: instrumentId, symbol: 'TCNEW', timeframe: 'D1', adjusted: true, status: 'eligible', earliest_start: '2024-01-01T00:00:00Z', max_requested_bars: 2000, reason_code: null })
      }
      if (path === '/instrument-indicators/990014') return Promise.resolve({ indicators: [] })
      if (path === '/ohlcv/local/TCNEW/D1') {
        const rows = historyAcquired ? [bar] : []
        localReadbacks.push({ path, returnedBars: rows.length })
        return Promise.resolve(rows)
      }
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string) => {
      if (path === '/instruments/acquire') {
        return Promise.resolve({
          request_id: 'd145917b-65a1-4d45-8fb8-968bc47df606',
          status: 'resolved',
          instrument: { instrument_id: instrumentId, symbol: 'TCNEW', identity_status: 'resolved' },
          source_outcomes: [{ provider: 'test-fixture', capability: 'fixture_only', operation: 'ui_test', status: 'used' }],
        })
      }
      if (path === `/instruments/${instrumentId}/history-acquisitions`) {
        historyAcquired = true
        return Promise.resolve({
          request_id: 'd145917b-65a1-4d45-8fb8-968bc47df606',
          status: 'complete',
          instrument_id: instrumentId,
          symbol: 'TCNEW',
          timeframe: 'D1',
          adjusted: true,
          requested_start: '2026-04-30T12:34:00.000Z',
          requested_end: '2026-10-27T12:34:00.000Z',
          coverage: { status: 'ready', bar_count: 1, missing_slices: [] },
          bars: [bar],
          source_outcomes: [{ provider: 'test-fixture', capability: 'fixture_only', operation: 'ui_test', status: 'used' }],
        })
      }
      return Promise.resolve({})
    })

    const pinia = createPinia()
    setActivePinia(pinia)
    const workspaceStore = useWorkspaceStore(pinia)
    workspaceStore.publishSymbol({ symbol: 'TCNEW', instrumentId, group: 'blue', sourceWindowKey: 'fixture' })
    const tool = chartFixture()
    const chartStore = usePanelStore(`workstation-${tool.instance_key}`, pinia)
    chartStore.symbol = 'TCNEW'
    chartStore.timeframe = 'D1'
    chartStore.barType = 'candles'
    chartStore.transformParams = {}
    chartStore.instrument = { id: instrumentId, symbol: 'TCNEW', name: 'Controlled fixture symbol' } as never
    chartStore.bars = []
    chartStore.error = null
    chartStore.isLoading = false

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mount(WorkstationToolContent, {
      props: { tool, activeWindowKey: 'another-chart' },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: {
          UPlotChart: EmptyChartStub,
          ChartPlotLibrary: { template: '<div />' },
          ChartTemplateControl: { template: '<div />' },
          DrawingToolbar: { template: '<div />' },
          ToolWindow: ToolWindowShell,
        },
      },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="workstation-history-acquisition"]').exists()).toBe(false)
    const acquisitionPosts = () => apiPost.mock.calls.filter(([path]) => String(path).includes('/instruments/acquire') || String(path).includes('/history-acquisitions'))
    expect(acquisitionPosts()).toEqual([])

    await wrapper.setProps({ activeWindowKey: tool.instance_key })
    const action = wrapper.get('[data-testid="history-load-missing"]')
    expect(wrapper.get('[data-testid="workstation-history-acquisition"]').text()).toContain('No local chart bars are available for TCNEW.')
    expect(acquisitionPosts()).toEqual([])
    await action.trigger('click')

    await vi.waitFor(() => expect(chartStore.bars).toEqual([bar]))
    expect(acquisitionPosts().map(([path]) => path)).toEqual([
      '/instruments/acquire',
      `/instruments/${instrumentId}/history-acquisitions`,
    ])
    expect(apiGet.mock.calls.filter(([path]) => path === '/coverage/instruments/TCNEW/ohlcv')).toHaveLength(1)
    expect(localReadbacks).toEqual([{ path: '/ohlcv/local/TCNEW/D1', returnedBars: 1 }])
    expect(wrapper.find('[data-testid="workstation-history-acquisition"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="local-chart-surface"]').exists()).toBe(true)

    wrapper.unmount()
    queryClient.clear()
  })

  it('leaves passive D1 mount alone and loads W1/MN on deliberate timeframe changes', async () => {
    const instrumentId = 990021
    const pinia = createPinia()
    setActivePinia(pinia)
    const workspaceStore = useWorkspaceStore(pinia)
    workspaceStore.linkedSymbol = 'SPY'
    workspaceStore.linkedTimeframe = 'D1'
    const tool = mountedChartTool('workstation-explicit-weekly-history')
    workspaceStore.workspace = {
      id: 1, user_id: 1, name: 'Test', is_default: true, position: 0, revision: 1, schema_version: 1, settings: { linked_timeframe: 'D1' },
      tabs: [{ id: 1, stable_key: 'main', name: 'Main', position: 0, layout_config: {}, active_window_key: tool.instance_key, windows: [tool] }],
    }
    workspaceStore.activeTabKey = 'main'
    apiGet.mockImplementation((path: string, params?: Record<string, unknown>) => {
      if (path === '/instruments/SPY') return Promise.resolve({ id: instrumentId, symbol: 'SPY', stats: {} })
      if (path === `/instrument-indicators/${instrumentId}`) return Promise.resolve({ indicators: [] })
      if (path.startsWith('/ohlcv/local/SPY/')) return Promise.resolve([])
      if (path === `/instruments/${instrumentId}/history-availability`) {
        return Promise.resolve({ instrument_id: instrumentId, symbol: 'SPY', timeframe: params?.timeframe, adjusted: true, status: 'eligible', earliest_start: '2024-01-01T00:00:00Z', max_requested_bars: 2000, reason_code: null })
      }
      if (path === '/coverage/instruments/SPY/ohlcv' && ['D1', 'W1', 'MN'].includes(String(params?.timeframe))) {
        return Promise.resolve({ status: 'missing', bar_count: 0, missing_slices: [{ start: '2024-01-01T00:00:00Z', end: '2026-01-01T00:00:00Z' }] })
      }
      return Promise.resolve([])
    })
    apiPost.mockImplementation((path: string, payload?: Record<string, unknown>) => {
      if (path === '/instruments/acquire') return Promise.resolve({ status: 'resolved', instrument: { instrument_id: instrumentId, symbol: 'SPY', identity_status: 'resolved' }, source_outcomes: [] })
      const timeframe = String(payload?.timeframe ?? 'W1')
      return Promise.resolve({
        status: 'complete', instrument_id: instrumentId, symbol: 'SPY', timeframe, adjusted: true,
        requested_start: '2024-01-01T00:00:00Z', requested_end: '2026-01-01T00:00:00Z',
        coverage: { status: 'ready', bar_count: timeframe === 'W1' ? 100 : 24, missing_slices: [] }, bars: [], source_outcomes: [],
      })
    })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mountChartTool(tool, pinia, queryClient)
    await flushPromises()
    expect(apiPost).not.toHaveBeenCalled()

    await wrapper.get('.choose-weekly').trigger('click')
    await flushPromises()

    const historyCall = apiPost.mock.calls.find(([path]) => String(path).includes('/history-acquisitions'))
    expect(historyCall?.[0]).toBe(`/instruments/${instrumentId}/history-acquisitions`)
    expect(historyCall?.[1]).toMatchObject({ timeframe: 'W1', adjusted: true })
    expect(wrapper.text()).toContain('Loaded 100 W1 bars for SPY.')
    await wrapper.get('.choose-monthly').trigger('click')
    await flushPromises()
    const historyCalls = apiPost.mock.calls.filter(([path]) => String(path).includes('/history-acquisitions'))
    expect(historyCalls.map(([, payload]) => (payload as { timeframe: string }).timeframe)).toEqual(['W1', 'MN'])
    expect(wrapper.text()).toContain('Loaded 24 MN bars for SPY.')
    expect(apiPost).toHaveBeenCalledTimes(4) // each explicit interval confirms identity, then acquires its bounded history

    wrapper.unmount()
    queryClient.clear()
  })

  it('refreshes only mounted panels that still match the selected local history scope', async () => {
    const instrumentId = 990014
    const acquiredBar = {
      ts: '2026-11-03T15:00:00Z', open: 10, high: 11, low: 9, close: 10.5, volume: 100,
      is_adjusted: true, is_derived: false,
    }
    const otherBar = {
      ts: '2026-11-03T15:00:00Z', open: 30, high: 31, low: 29, close: 30.5, volume: 300,
      is_adjusted: true, is_derived: false,
    }
    let persisted = false
    const localReads: string[] = []
    apiGet.mockImplementation((path: string) => {
      if (path.startsWith('/instruments/')) {
        const symbol = path.slice('/instruments/'.length)
        return Promise.resolve({ id: symbol === 'TCNEW' ? instrumentId : 990015, symbol, name: `${symbol} fixture`, stats: { week52_high: 40 } })
      }
      if (path.startsWith('/instrument-indicators/')) return Promise.resolve({ indicators: [] })
      if (path.startsWith('/ohlcv/local/')) {
        const [, , , symbol] = path.split('/')
        localReads.push(symbol ?? '')
        if (symbol === 'TCNEW') return Promise.resolve(persisted ? [acquiredBar] : [])
        if (symbol === 'OTHER') return Promise.resolve([otherBar])
      }
      return Promise.resolve([])
    })

    const pinia = createPinia()
    setActivePinia(pinia)
    const workspaceStore = useWorkspaceStore(pinia)
    workspaceStore.publishSymbol({ symbol: 'TCNEW', instrumentId, group: 'blue', sourceWindowKey: 'fixture' })
    workspaceStore.publishSymbol({ symbol: 'OTHER', instrumentId: 990015, group: 'red', sourceWindowKey: 'fixture' })
    const selectedTool = mountedChartTool('workstation-selected-history-refresh')
    const unrelatedTool = mountedChartTool('workstation-unrelated-red-chart', 'red')
    const selectedStore = usePanelStore(`workstation-${selectedTool.instance_key}`, pinia)
    const unrelatedStore = usePanelStore(`workstation-${unrelatedTool.instance_key}`, pinia)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const selectedWrapper = mountChartTool(selectedTool, pinia, queryClient)
    const unrelatedWrapper = mountChartTool(unrelatedTool, pinia, queryClient)
    await flushPromises()

    expect(selectedStore.symbol).toBe('TCNEW')
    expect(selectedStore.bars).toEqual([])
    expect(unrelatedStore.symbol).toBe('OTHER')
    expect(unrelatedStore.bars).toEqual([otherBar])
    const unrelatedReadsBefore = localReads.filter(symbol => symbol === 'OTHER').length

    persisted = true
    await refreshMountedWorkstationChartPanels('TCNEW', 'D1', () => true)

    expect(selectedStore.bars).toEqual([acquiredBar])
    expect(localReads.filter(symbol => symbol === 'TCNEW').length).toBeGreaterThan(1)
    expect(localReads.filter(symbol => symbol === 'OTHER')).toHaveLength(unrelatedReadsBefore)
    expect(unrelatedStore.bars).toEqual([otherBar])
    expect(apiPost).not.toHaveBeenCalled()

    selectedWrapper.unmount()
    unrelatedWrapper.unmount()
    queryClient.clear()
  })

  it('does not let a late A local refresh replace the same panel after it switches to B', async () => {
    const instrumentIdA = 990014
    const instrumentIdB = 990015
    const barA = { ts: '2026-11-03T14:00:00Z', open: 10, high: 11, low: 9, close: 10.5, volume: 100 }
    const barB = { ts: '2026-11-03T15:00:00Z', open: 20, high: 21, low: 19, close: 20.5, volume: 200 }
    const lateA = deferred<typeof barA[]>()
    let aReadCount = 0
    apiGet.mockImplementation((path: string) => {
      if (path.startsWith('/instruments/')) {
        const symbol = path.slice('/instruments/'.length)
        return Promise.resolve({ id: symbol === 'TCNEW' ? instrumentIdA : instrumentIdB, symbol, name: `${symbol} fixture`, stats: { week52_high: 40 } })
      }
      if (path.startsWith('/instrument-indicators/')) return Promise.resolve({ indicators: [] })
      if (path === '/ohlcv/local/TCNEW/D1') {
        aReadCount += 1
        return aReadCount === 1 ? Promise.resolve([]) : lateA.promise
      }
      if (path === '/ohlcv/local/OTHER/D1') return Promise.resolve([barB])
      return Promise.resolve([])
    })

    const pinia = createPinia()
    setActivePinia(pinia)
    const workspaceStore = useWorkspaceStore(pinia)
    workspaceStore.publishSymbol({ symbol: 'TCNEW', instrumentId: instrumentIdA, group: 'blue', sourceWindowKey: 'fixture' })
    const tool = mountedChartTool('workstation-late-history-switch')
    const chartStore = usePanelStore(`workstation-${tool.instance_key}`, pinia)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mountChartTool(tool, pinia, queryClient)
    await flushPromises()
    expect(chartStore.symbol).toBe('TCNEW')
    expect(chartStore.bars).toEqual([])

    const refreshA = refreshMountedWorkstationChartPanels('TCNEW', 'D1', () => true)
    await vi.waitFor(() => expect(aReadCount).toBe(2))
    workspaceStore.publishSymbol({ symbol: 'OTHER', instrumentId: instrumentIdB, group: 'blue', sourceWindowKey: 'fixture' })
    await vi.waitFor(() => expect(chartStore.symbol).toBe('OTHER'))
    await vi.waitFor(() => expect(chartStore.bars).toEqual([barB]))
    lateA.resolve([barA])
    await refreshA

    expect(chartStore.symbol).toBe('OTHER')
    expect(chartStore.bars).toEqual([barB])
    expect(apiPost).not.toHaveBeenCalled()

    wrapper.unmount()
    queryClient.clear()
  })

  it('keeps an unresolved reported-row picker across same-snapshot refreshes and clears it for a new snapshot', async () => {
    const holding = {
      id: 991601,
      snapshot_id: 991203,
      constituent_instrument_id: null,
      constituent_symbol: null,
      constituent_name: null,
      reported_symbol: 'UNXQ',
      reported_name: 'Unlisted Example Software Corp',
      position: 1,
      weight: '0.125',
      holding_type: 'equity',
      row_type: 'security',
      source_row_id: 'igv-controlled-row-991601',
      is_resolved: false,
    }
    const snapshot = {
      id: 991203,
      etf_symbol: 'IGV',
      etf_name: 'Controlled fixture fund',
      composition_date: '2026-11-02',
      known_at: '2026-11-03T08:15:00Z',
      provenance: 'controlled_fixture_only',
      source_provider: 'test-fixture',
    }
    const holdingsPage = (snapshotId: number) => ({
      snapshot: { ...snapshot, id: snapshotId },
      holdings: [{ ...holding, snapshot_id: snapshotId }],
      total: 1,
      limit: 500,
      offset: 0,
      has_next: false,
    })

    apiGet.mockImplementation((path: string) => {
      if (path === '/etf-holdings/IGV/holdings') return Promise.resolve(holdingsPage(snapshot.id))
      return Promise.resolve([])
    })
    const pinia = createPinia()
    setActivePinia(pinia)
    const workspaceStore = useWorkspaceStore(pinia)
    workspaceStore.setConstituentETF('IGV')
    workspaceStore.etfHoldings = { IGV: holdingsPage(snapshot.id) as never }
    const tool: WorkspaceWindowState = {
      id: 31,
      instance_key: 'constituent-list',
      tool_type: 'watchlist',
      title: 'Constituents',
      link_group: 'blue',
      configuration: {},
      style: {},
      state_schema_version: 1,
      position: 0,
    }
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mount(WorkstationToolContent, {
      props: { tool },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: {
          UPlotChart: EmptyChartStub,
          ChartPlotLibrary: { template: '<div />' },
          ChartTemplateControl: { template: '<div />' },
          DrawingToolbar: { template: '<div />' },
          ToolWindow: ToolWindowShell,
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })
    await flushPromises()

    await wrapper.get('.watchlist__row').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="reported-holding-selection"]').exists()).toBe(true)
    expect((wrapper.get('input[role="combobox"]').element as HTMLInputElement).value).toBe('UNXQ')

    // A same-snapshot API refresh replaces the holdings page object but must
    // keep the exact reported-row action and its discovery component mounted.
    await workspaceStore.loadETFHoldings('IGV')
    await flushPromises()
    expect(wrapper.find('[data-testid="reported-holding-selection"]').exists()).toBe(true)
    expect((wrapper.get('input[role="combobox"]').element as HTMLInputElement).value).toBe('UNXQ')

    // A genuinely different snapshot must still invalidate that row action.
    workspaceStore.etfHoldings = { ...workspaceStore.etfHoldings, IGV: holdingsPage(snapshot.id + 1) as never }
    await flushPromises()
    expect(wrapper.find('[data-testid="reported-holding-selection"]').exists()).toBe(false)

    await wrapper.get('.watchlist__row').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="reported-holding-selection"]').exists()).toBe(true)
    workspaceStore.selectedIndustry = 'Technology'
    await flushPromises()
    expect(wrapper.find('[data-testid="reported-holding-selection"]').exists()).toBe(false)

    workspaceStore.selectedIndustry = null
    await flushPromises()
    await wrapper.get('.watchlist__row').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="reported-holding-selection"]').exists()).toBe(true)
    workspaceStore.setConstituentETF('XHB')
    await flushPromises()
    expect(wrapper.find('[data-testid="reported-holding-selection"]').exists()).toBe(false)

    wrapper.unmount()
    queryClient.clear()
  })

  it('selects a resolved holding through the dashboard event with exact snapshot, row and as-of provenance', async () => {
    const snapshot = {
      id: 991203, etf_symbol: 'IGV', etf_name: 'Controlled fixture fund',
      composition_date: '2026-11-02', known_at: '2026-11-03T08:15:00Z',
      provenance: 'controlled_fixture_only', source_provider: 'test-fixture',
    }
    const holding = {
      id: 991601, snapshot_id: snapshot.id, constituent_instrument_id: 991700,
      constituent_symbol: 'UNXQ', constituent_name: 'Unlisted Example Software Corp',
      reported_symbol: 'UNXQ', reported_name: 'Unlisted Example Software Corp',
      position: 1, weight: '0.125', holding_type: 'equity', row_type: 'security',
      source_row_id: 'igv-controlled-row-991601', is_resolved: true,
    }
    const page = { snapshot, holdings: [holding], total: 1, limit: 500, offset: 0, has_next: false }
    apiGet.mockImplementation((path: string) => path === '/etf-holdings/IGV/holdings' ? Promise.resolve(page) : Promise.resolve([]))
    const pinia = createPinia()
    setActivePinia(pinia)
    const workspaceStore = useWorkspaceStore(pinia)
    workspaceStore.setConstituentETF('IGV')
    workspaceStore.linkedSymbol = 'UNXQ'
    workspaceStore.etfHoldings = { IGV: page as never }
    const tool: WorkspaceWindowState = {
      id: 31, instance_key: 'constituent-list', tool_type: 'watchlist', title: 'Constituents',
      link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0,
    }
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mount(WorkstationToolContent, {
      props: { tool },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: {
          UPlotChart: EmptyChartStub, ChartPlotLibrary: { template: '<div />' },
          ChartTemplateControl: { template: '<div />' }, DrawingToolbar: { template: '<div />' },
          ToolWindow: ToolWindowShell, RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })
    await flushPromises()
    expect(wrapper.get('.tool-window__symbol').text()).toBe('IGV')
    expect(wrapper.get('.tool-window-shell').attributes('data-symbol')).toBe('IGV')
    await wrapper.get('.watchlist__row').trigger('click')

    const event = wrapper.emitted('holdingSelect')?.[0]
    expect(event?.[0]).toBe('UNXQ')
    expect(event?.[1]).toMatchObject({
      instrumentId: 991700, canonicalSymbol: 'UNXQ', snapshotId: 991203,
      compositionDate: '2026-11-02', knownAt: '2026-11-03T08:15:00Z',
      holdingRowId: 991601, sourceRowId: 'igv-controlled-row-991601',
    })
    expect(wrapper.emitted('holdingDrilldown')).toBeUndefined()
    expect(workspaceStore.constituentETF).toBe('IGV')
    expect(apiPost).not.toHaveBeenCalled()

    // The same composition surface must keep naming its retained fund while a
    // constituent is the active chart symbol, then follow an independent fund
    // selection as soon as the workspace context changes.
    expect(workspaceStore.linkedSymbol).toBe('UNXQ')
    expect(wrapper.get('.tool-window__symbol').text()).toBe('IGV')
    workspaceStore.setConstituentETF('XHB')
    await flushPromises()
    expect(wrapper.get('.tool-window__symbol').text()).toBe('XHB')

    wrapper.unmount()
    queryClient.clear()
  })

  it('labels the Industry surface with its retained ETF while a constituent remains the active chart symbol', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const workspaceStore = useWorkspaceStore(pinia)
    workspaceStore.setConstituentETF('IGV')
    workspaceStore.etfIndustries = {
      IGV: {
        etf_symbol: 'IGV', composition_date: '2026-11-02', known_at: '2026-11-03T08:15:00Z',
        provenance: 'dated_holdings_snapshot', source_provider: 'controlled-source', completeness_status: 'complete',
        industries: [], exclusions: ['unresolved_holding', 'unclassified_constituent'],
        classification_systems: ['GICS'], classification_coverage: 0,
      },
    }
    workspaceStore.linkedSymbol = 'UNXQ'
    const tool: WorkspaceWindowState = {
      id: 32, instance_key: 'industry-list', tool_type: 'watchlist', title: 'Industries',
      link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 1,
    }
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mount(WorkstationToolContent, {
      props: { tool },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: {
          UPlotChart: EmptyChartStub, ChartPlotLibrary: { template: '<div />' },
          ChartTemplateControl: { template: '<div />' }, DrawingToolbar: { template: '<div />' },
          ToolWindow: ToolWindowShell, RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })
    await flushPromises()

    expect(wrapper.get('.tool-window__symbol').text()).toBe('IGV')
    expect(wrapper.text()).toContain('No source-classified industries are available for IGV')
    expect(wrapper.text()).toContain('Classification exclusions: holdings without a canonical identity; constituents without source classification')
    expect(wrapper.text()).toContain('controlled-source · dated_holdings_snapshot · 0% classified')
    workspaceStore.setConstituentETF('XHB')
    workspaceStore.etfIndustries = {
      ...workspaceStore.etfIndustries,
      XHB: {
        etf_symbol: 'XHB', composition_date: '2026-11-01', known_at: null,
        provenance: 'dated_holdings_snapshot', source_provider: 'controlled-source', completeness_status: 'partial',
        industries: [], exclusions: ['unclassified_constituent'], classification_systems: ['GICS'], classification_coverage: 0,
      },
    }
    await flushPromises()
    expect(wrapper.get('.tool-window__symbol').text()).toBe('XHB')
    expect(wrapper.text()).toContain('No source-classified industries are available for XHB')
    expect(workspaceStore.linkedSymbol).toBe('UNXQ')

    wrapper.unmount()
    queryClient.clear()
  })
})
