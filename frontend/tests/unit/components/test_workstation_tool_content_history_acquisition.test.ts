import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

const { apiGet, apiPost, apiPatch, apiDelete, apiPut, promoteQueued } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPatch: vi.fn(),
  apiDelete: vi.fn(),
  apiPut: vi.fn(),
  promoteQueued: vi.fn(),
}))

vi.mock('@/lib/api', () => ({
  api: {
    get: apiGet,
    post: apiPost,
    patch: apiPatch,
    delete: apiDelete,
    put: apiPut,
  },
  setQueuedApiRequestPriority: promoteQueued,
}))

import WorkstationToolContent from '@/components/workstation/WorkstationToolContent.vue'
import { refreshMountedWorkstationChartPanels, usePanelStore } from '@/stores/chart'
import { clearOhlcvRequestCache } from '@/lib/workstation/ohlcvRequests'
import { dataPreparationCoordinator, type DataEnsureResponse } from '@/lib/dataPreparation'
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
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mount(WorkstationToolContent, {
      props: { tool, activeWindowKey: tool.instance_key },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
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
    expect(apiGet).toHaveBeenCalledWith('/market-groups/sp500', undefined, {
      priority: 'low', queueKey: 'top-down:market-group:sp500',
    })
    wrapper.unmount()

    // Opening/closing a docked tool may remount virtual roots. The same
    // all-family readiness context should share one authenticated query across
    // that remount instead of repeating the expensive global calculation.
    const remounted = mount(WorkstationToolContent, {
      props: { tool, activeWindowKey: tool.instance_key },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
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
    expect(apiGet.mock.calls.filter(([path]) => path === '/analysis/benchmark-families/readiness')).toHaveLength(1)
    remounted.unmount()
    queryClient.clear()
  })

  it('promotes a queued benchmark universe read when its semantic list becomes visible', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const workspaceStore = useWorkspaceStore(pinia)
    const rootGroup = deferred<any>()
    apiGet.mockImplementation((path: string) => {
      if (path === '/market-groups/us-benchmarks') return rootGroup.promise
      if (path === '/market-groups/sp500') return Promise.resolve({ members: [], provenance: {} })
      if (path === '/analysis/benchmark-families/sp500/overview') return Promise.resolve({ mappings: [] })
      if (path === '/analysis/benchmark-families/readiness') return Promise.resolve({ status: 'ready', families: [], provider_probe_evidence: [] })
      return Promise.resolve([])
    })
    const shellRead = workspaceStore.loadMarketGroup('us-benchmarks', { priority: 'auto' })
    const tool: WorkspaceWindowState = {
      id: -33,
      instance_key: 'benchmark-list-visible-clone',
      tool_type: 'watchlist',
      title: 'Benchmarks',
      link_group: 'blue',
      configuration: { workspace_role: 'benchmark-universe' },
      style: {},
      state_schema_version: 1,
      position: 0,
    }
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const rectSpy = vi.spyOn(HTMLElement.prototype, 'getClientRects').mockImplementation(function () {
      return this.classList.contains('tool-window-shell') ? [{} as DOMRect] as DOMRectList : [] as unknown as DOMRectList
    })
    const wrapper = mount(WorkstationToolContent, {
      props: { tool, activeWindowKey: tool.instance_key },
      attachTo: document.body,
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
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

    expect(apiGet.mock.calls.filter(([path]) => path === '/market-groups/us-benchmarks')).toHaveLength(1)
    expect(promoteQueued).toHaveBeenCalledWith('top-down:market-group:us-benchmarks', 'high')
    rootGroup.resolve({ members: [], provenance: { benchmark_families: [] } })
    await shellRead
    await flushPromises()
    expect(workspaceStore.marketGroups['us-benchmarks']).toBeDefined()

    wrapper.unmount()
    rectSpy.mockRestore()
    queryClient.clear()
  })

  it('clears family busy state when switching to cached plain benchmarks while the old family response is pending', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const workspaceStore = useWorkspaceStore(pinia)
    const members = ['DIA', 'IWM', 'QQQ', 'RSP', 'SPY'].map((symbol, index) => ({
      id: index + 1,
      instrument_id: index + 101,
      position: index,
      instrument: { id: index + 101, symbol, name: `${symbol} fund` },
    }))
    workspaceStore.marketGroups['us-benchmarks'] = { members, provenance: {} } as never
    const familyGroup = deferred<any>()
    const familySnapshot = deferred<any>()
    const familyOverview = deferred<any>()
    apiGet.mockImplementation((path: string) => {
      if (path === '/market-groups/sp500') return familyGroup.promise
      if (path === '/analysis/groups/sp500/snapshot') return familySnapshot.promise
      if (path === '/analysis/benchmark-families/sp500/overview') return familyOverview.promise
      if (path === '/analysis/benchmark-families/readiness') return Promise.resolve({ status: 'ready', families: [], provider_probe_evidence: [] })
      return Promise.resolve([])
    })
    const tool: WorkspaceWindowState = {
      id: -95,
      instance_key: 'benchmark-family-switch',
      tool_type: 'watchlist',
      title: 'Benchmarks',
      link_group: 'blue',
      configuration: { workspace_role: 'benchmark-universe', benchmark_family_key: 'sp500', as_of: '2026-11-07' },
      style: {},
      state_schema_version: 1,
      position: 0,
    }
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mount(WorkstationToolContent, {
      props: { tool, activeWindowKey: tool.instance_key },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: {
          VirtualWatchlistTool: {
            props: ['label', 'rows', 'loading'],
            template: '<section :aria-label="label" :aria-busy="loading ? \'true\' : \'false\'"><span v-for="row in rows" :key="row.symbol">{{ row.symbol }}</span></section>',
          },
          ToolWindow: ToolWindowShell,
          UPlotChart: EmptyChartStub,
          ChartPlotLibrary: true,
          ChartTemplateControl: true,
          DrawingToolbar: true,
        },
      },
    })

    await vi.waitFor(() => expect(wrapper.get('.benchmark-surface section[aria-busy]')
      .attributes('aria-busy')).toBe('true'))
    await wrapper.setProps({ tool: { ...tool, configuration: { ...tool.configuration, benchmark_family_key: null } } })
    await flushPromises()
    const plainList = wrapper.get('[aria-label="Major US benchmarks"]')
    expect(plainList.attributes('aria-busy')).toBe('false')
    expect(plainList.text()).toContain('DIA')
    expect(plainList.text()).toContain('SPY')

    familyGroup.resolve({ members: [], provenance: {} })
    familySnapshot.resolve({ group_key: 'sp500', rows: [] })
    familyOverview.resolve({ mappings: [] })
    await flushPromises()
    expect(plainList.attributes('aria-busy')).toBe('false')
    expect(plainList.text()).toContain('SPY')

    wrapper.unmount()
    queryClient.clear()
  })

  it('keeps both constituent context and missing-snapshot messages in normal flow', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const tool: WorkspaceWindowState = {
      id: 31, instance_key: 'constituent-list', tool_type: 'watchlist', title: 'Constituents',
      link_group: 'blue', configuration: { workspace_role: 'constituents' }, style: {}, state_schema_version: 1, position: 0,
    }
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mount(WorkstationToolContent, {
      props: { tool },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: {
          VirtualWatchlistTool: { template: '<div class="watchlist-caption">{{ label }}</div>', props: ['label'] },
          ToolWindow: ToolWindowShell,
          UPlotChart: EmptyChartStub,
          ChartPlotLibrary: true,
          ChartTemplateControl: true,
          DrawingToolbar: true,
        },
      },
    })
    await flushPromises()

    const instruction = wrapper.get('.constituent-tool__empty-context')
    const caption = wrapper.get('.watchlist-caption')
    const pane = wrapper.get('.constituent-tool')
    expect(instruction.text()).toContain('Choose an ETF or industry')
    expect(caption.text()).toContain('No point-in-time ETF holdings snapshot')
    expect(instruction.element.parentElement).toBe(pane.element)
    expect(caption.element.parentElement).toBe(pane.element)
    expect(Array.from(pane.element.children).indexOf(instruction.element)).toBeLessThan(
      Array.from(pane.element.children).indexOf(caption.element),
    )

    wrapper.unmount()
    queryClient.clear()
  })

  it('publishes curated sector members before a delayed sector analysis snapshot', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const groupResponse = deferred<unknown>()
    const snapshot = deferred<unknown>()
    const sectorMembers = ['XLK', 'XLY', 'XLP', 'XLE', 'XLF', 'XLV', 'XLI', 'XLB', 'XLRE', 'XLC', 'XLU']
      .map((symbol, index) => ({
        id: index + 1,
        instrument_id: index + 101,
        position: index,
        instrument: { id: index + 101, symbol, name: `${symbol} sector fund` },
      }))
    const workspaceStore = useWorkspaceStore(pinia)
    apiGet.mockImplementation((path: string) => {
      if (path === '/market-groups/sp500-sectors') {
        return groupResponse.promise
      }
      if (path === '/analysis/groups/sp500-sectors/snapshot') return snapshot.promise
      return Promise.resolve([])
    })
    const rowsStub = defineComponent({
      props: ['rows'],
      setup(props) {
        return () => h('div', { 'data-test': 'sector-catalogue-rows' }, (props.rows as Array<{ symbol: string }>).map(row => row.symbol).join(','))
      },
    })
    const tool: WorkspaceWindowState = {
      id: 38, instance_key: 'sector-list', tool_type: 'watchlist', title: 'S&P 500 Sectors',
      link_group: 'blue', configuration: { workspace_role: 'sector-universe' }, style: {}, state_schema_version: 1, position: 0,
    }
    const shellGroupRead = workspaceStore.loadMarketGroup('sp500-sectors')
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mount(WorkstationToolContent, {
      props: { tool, activeWindowKey: tool.instance_key },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: {
          VirtualWatchlistTool: rowsStub, UPlotChart: EmptyChartStub, ChartPlotLibrary: true,
          ChartTemplateControl: true, DrawingToolbar: true, ToolWindow: ToolWindowShell,
        },
      },
    })

    const analysisRead = workspaceStore.loadGroupSnapshot('sp500-sectors', 'SPY')
    expect(apiGet.mock.calls.filter(([path]) => path === '/market-groups/sp500-sectors')).toHaveLength(1)
    groupResponse.resolve({ stable_key: 'sp500-sectors', members: sectorMembers, provenance: {} })
    await shellGroupRead
    await vi.waitFor(() => expect(workspaceStore.marketGroups['sp500-sectors']?.members).toHaveLength(11))
    expect(wrapper.get('[data-test="sector-catalogue-rows"]').text()).toContain('XLB')
    expect(apiGet).toHaveBeenCalledWith('/market-groups/sp500-sectors', undefined, {
      priority: 'auto', queueKey: 'top-down:market-group:sp500-sectors',
    })
    expect(apiGet).toHaveBeenCalledWith('/analysis/groups/sp500-sectors/snapshot', { benchmark: 'SPY' }, {
      priority: 'auto', queueKey: 'top-down:group-snapshot:sp500-sectors',
    })
    expect(workspaceStore.groupSnapshots['sp500-sectors']).toBeUndefined()

    snapshot.resolve({ group_key: 'sp500-sectors', rows: [] })
    await analysisRead
    await flushPromises()
    wrapper.unmount()
    queryClient.clear()
  })

  it('starts breadth preparation independently of delayed local reads and refreshes on worker progress', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const initialBreadthRead = deferred<unknown>()
    let breadthReads = 0
    apiGet.mockImplementation((path: string) => {
      if (path === '/market-groups/sp500-sectors') return Promise.resolve({ members: [], provenance: {} })
      if (path === '/analysis/groups/sp500-sectors/breadth' && breadthReads++ === 0) return initialBreadthRead.promise
      if (path.startsWith('/analysis/groups/sp500-sectors/')) return Promise.resolve({ group_key: 'sp500-sectors', rows: [], members: [] })
      return Promise.resolve([])
    })
    const pendingByTarget = new Map<string, ReturnType<typeof deferred<DataEnsureResponse>>>()
    const progressByTarget = new Map<string, (value: { response: DataEnsureResponse }) => void>()
    const ensure = vi.spyOn(dataPreparationCoordinator, 'ensure').mockImplementation((request, options) => {
      const target = request.target.kind === 'instrument' ? `instrument:${request.target.symbol}` : `${request.target.kind}:${request.target.group_key ?? request.target.family_key}`
      const pending = deferred<DataEnsureResponse>()
      pendingByTarget.set(target, pending)
      if (options?.onProgress) progressByTarget.set(target, options.onProgress as (value: { response: DataEnsureResponse }) => void)
      expect(request).toMatchObject({
        target: target === 'instrument:SPY' ? { kind: 'instrument', symbol: 'SPY' } : { kind: 'market_group', group_key: 'sp500-sectors' },
        datasets: ['history'],
        timeframe: 'D1',
        adjusted: true,
      })
      expect(request).not.toHaveProperty('start_at')
      return pending.promise
    })
    const tool: WorkspaceWindowState = {
      id: 36, instance_key: 'breadth-preparation', tool_type: 'breadth', title: 'S&P 500 Sectors',
      link_group: 'blue', configuration: { group_key: 'sp500-sectors' }, style: {}, state_schema_version: 1, position: 0,
    }
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mount(WorkstationToolContent, {
      props: { tool, activeWindowKey: tool.instance_key },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: { VirtualWatchlistTool: true, UPlotChart: EmptyChartStub, ChartPlotLibrary: true, ChartTemplateControl: true, DrawingToolbar: true, ToolWindow: ToolWindowShell, RouterLink: { template: '<a><slot /></a>' }, BreadthHistoryUPlot: true, GenericBreadthHistoryUPlot: true },
      },
    })
    await vi.waitFor(() => expect(ensure).toHaveBeenCalledTimes(2))
    expect(new Set(ensure.mock.calls.map(([request]) => request.target.kind === 'instrument' ? `instrument:${request.target.symbol}` : `${request.target.kind}:${request.target.group_key ?? request.target.family_key}`))).toEqual(new Set(['market_group:sp500-sectors', 'instrument:SPY']))

    const breadthRead = () => apiGet.mock.calls.filter(([path]) => path === '/analysis/groups/sp500-sectors/breadth').length
    expect(breadthRead()).toBe(1)
    initialBreadthRead.resolve({ group_key: 'sp500-sectors', rows: [], members: [] })
    await flushPromises()
    const readsBeforeProgress = breadthRead()
    const partial: DataEnsureResponse = {
      request_id: 'breadth-progress', status: 'partial', created_at: '2026-11-07T10:00:00Z', updated_at: '2026-11-07T10:00:01Z', version: 2,
      target: { kind: 'market_group', group_key: 'sp500-sectors' }, completed: 1, total: 2, last_progress_at: '2026-11-07T10:00:01Z',
      dependencies: [],
    }
    progressByTarget.get('instrument:SPY')?.({ response: partial })
    await vi.waitFor(() => expect(breadthRead()).toBeGreaterThan(readsBeforeProgress))

    for (const [target, pending] of pendingByTarget) {
      pending.resolve({ ...partial, target: target === 'instrument:SPY' ? { kind: 'instrument', symbol: 'SPY' } : { kind: 'market_group', group_key: 'sp500-sectors' }, status: 'ready', version: 3, completed: 2, total: 2 })
    }
    await flushPromises()
    wrapper.unmount()
    queryClient.clear()
    ensure.mockRestore()
  })

  it('keeps generic breadth drilldown actions and history in the scrollable analysis panel', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const tool: WorkspaceWindowState = {
      id: 36, instance_key: 'breadth-drilldown-layout', tool_type: 'breadth', title: 'S&P 500 Sectors',
      link_group: 'blue', configuration: { group_key: 'sp500-sectors' }, style: {}, state_schema_version: 1, position: 0,
    }
    const member = { instrument_id: 1001, symbol: 'AAA', name: 'Alpha Incorporated', value: true, metric: 0.12 }
    apiPost.mockImplementation((path: string) => path === '/analysis/breadth'
      ? {
          definition_version: 1, definition_hash: 'breadth-layout', universe: { kind: 'group', key: 'sp500-sectors' },
          condition: { kind: 'above_moving_average' }, timeframe: 'D1', adjustment: 'split_adjusted',
          requested_count: 1, eligible_count: 1, pass_count: 1, excluded_count: 0, percentage: 1, coverage: 1,
          members: [member], exclusions: [],
        }
      : {
          definition_version: 1, definition_hash: 'breadth-layout', universe: { kind: 'group', key: 'sp500-sectors' },
          condition: { kind: 'above_moving_average' }, timeframe: 'D1', adjustment: 'split_adjusted',
          points: [{ timestamp: '2026-11-07T00:00:00Z', requested_count: 1, eligible_count: 1, pass_count: 1, excluded_count: 0, percentage: 1, coverage: 1, members: [member], exclusions: [] }],
          occurrences: [],
        })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const wrapper = mount(WorkstationToolContent, {
      props: { tool, activeWindowKey: tool.instance_key },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: {
          UPlotChart: EmptyChartStub, ChartPlotLibrary: { template: '<div />' }, ChartTemplateControl: { template: '<div />' },
          DrawingToolbar: { template: '<div />' }, ToolWindow: ToolWindowShell,
          BreadthHistoryUPlot: true,
          GenericBreadthHistoryUPlot: { template: '<div class="generic-breadth-history" data-test="generic-breadth-history" />', props: ['history'] },
        },
      },
    })

    await wrapper.get('.breadth-tool__custom button').trigger('click')
    const drilldown = wrapper.get('[aria-label="Generic breadth member drilldown"]')
    await vi.waitFor(() => expect(drilldown.text()).toContain('Pass 1'))
    expect(wrapper.get('.breadth-tool').element.querySelector('[data-test="generic-breadth-history"]')).not.toBeNull()
    const passFilter = drilldown.get('button[aria-pressed="true"]')
    const failFilter = drilldown.get('button[aria-pressed="false"]')
    await passFilter.trigger('click')
    await failFilter.trigger('click')
    expect(drilldown.findAll('button').find(button => button.text() === 'Fail 0')?.attributes('aria-pressed')).toBe('true')
    await drilldown.findAll('button').find(button => button.text() === 'Pass 1')?.trigger('click')
    await drilldown.get('button[aria-label="Select AAA Alpha Incorporated"]').trigger('click')
    expect(wrapper.emitted('select')).toEqual([['AAA', 1001]])
    wrapper.unmount()
    queryClient.clear()
  })

  it('keeps a completed generic breadth result visible while its independent history request is pending', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const tool: WorkspaceWindowState = {
      id: 36, instance_key: 'breadth-result-before-history', tool_type: 'breadth', title: 'S&P 500 Sectors',
      link_group: 'blue', configuration: { group_key: 'sp500-sectors' }, style: {}, state_schema_version: 1, position: 0,
    }
    const historyPending = deferred<unknown>()
    const member = { instrument_id: 1001, symbol: 'AAA', name: 'Alpha Incorporated', value: true, metric: 0.12 }
    apiPost.mockImplementation((path: string) => path === '/analysis/breadth'
      ? Promise.resolve({
          definition_version: 1, definition_hash: 'breadth-result-before-history', universe: { kind: 'group', key: 'sp500-sectors' },
          condition: { kind: 'above_moving_average' }, timeframe: 'D1', adjustment: 'split_adjusted',
          requested_count: 2, eligible_count: 2, pass_count: 1, excluded_count: 0, percentage: 0.5, coverage: 1,
          members: [member], exclusions: [],
        })
      : path === '/analysis/breadth/history'
        ? historyPending.promise
        : Promise.resolve({}))
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
    const wrapper = mount(WorkstationToolContent, {
      props: { tool, activeWindowKey: tool.instance_key },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: {
          UPlotChart: EmptyChartStub, ChartPlotLibrary: { template: '<div />' }, ChartTemplateControl: { template: '<div />' },
          DrawingToolbar: { template: '<div />' }, ToolWindow: ToolWindowShell,
          BreadthHistoryUPlot: true, GenericBreadthHistoryUPlot: true,
        },
      },
    })

    await wrapper.get('.breadth-tool__custom button').trigger('click')
    await vi.waitFor(() => expect(apiPost).toHaveBeenCalledWith('/analysis/breadth', expect.any(Object)))
    await vi.waitFor(() => expect(apiPost).toHaveBeenCalledWith('/analysis/breadth/history', expect.objectContaining({ limit: 500 })))
    await vi.waitFor(() => expect(wrapper.get('.breadth-tool__custom-result').text()).toContain('50.0%'))
    expect(wrapper.text()).toContain('Updating historical breadth…')
    expect(wrapper.get('[aria-label="Generic breadth member drilldown"]').text()).toContain('Pass 1')

    historyPending.resolve({
      definition_version: 1,
      definition_hash: 'breadth-result-before-history',
      universe: { kind: 'group', key: 'sp500-sectors' },
      condition: { kind: 'above_moving_average' },
      timeframe: 'D1',
      adjustment: 'split_adjusted',
      points: [],
      occurrences: [],
    })
    await flushPromises()
    expect(wrapper.get('.breadth-tool__custom-result').text()).toContain('50.0%')
    expect(wrapper.text()).not.toContain('Updating historical breadth…')
    wrapper.unmount()
    queryClient.clear()
  })

  it('reserves the drawing rail while keeping inactive chart controls out of keyboard access', async () => {
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
          DrawingToolbar: { template: '<div class="chart-tool__drawing-toolbar" data-test="chart-drawing-toolbar"><button>Trend Line</button></div>' },
          ToolWindow: ToolWindowShell,
        },
      },
    })

    const inactiveRail = wrapper.get('.chart-tool__drawing-toolbar--inactive')
    expect(inactiveRail.attributes('aria-hidden')).toBe('true')
    expect(inactiveRail.attributes('inert')).toBe('')
    expect(inactiveRail.findAll('button')).toHaveLength(0)
    await wrapper.setProps({ activeWindowKey: tool.instance_key })
    expect(wrapper.find('[data-test="chart-drawing-toolbar"]').exists()).toBe(true)
    expect(wrapper.find('.chart-tool__drawing-toolbar--inactive').exists()).toBe(false)
    await wrapper.setProps({ activeWindowKey: 'another-chart' })
    expect(wrapper.find('[data-test="chart-drawing-toolbar"]').exists()).toBe(false)
    expect(wrapper.find('.chart-tool__drawing-toolbar--inactive').exists()).toBe(true)

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
    tool.configuration = { timeframe_link_group: 'red' }
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

  it('keeps the Industry surface when a saved generic personal flag collides with its semantic role', async () => {
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
      // Older/cloned windows can retain the generic watchlist flag. The
      // factory's semantic industry role must still win when classifications
      // are unavailable rather than showing unrelated personal lists.
      link_group: 'blue', configuration: { personal: true }, style: {}, state_schema_version: 1, position: 1,
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

    expect(wrapper.find('.personal-watchlist-tool').exists()).toBe(false)
    expect(wrapper.find('.industry-list').exists()).toBe(false)
    expect(wrapper.get('.tool-state').text()).toContain('No source-classified industries are available for IGV')
    expect(wrapper.get('.tool-window__symbol').text()).toBe('IGV')
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
    expect(wrapper.find('.personal-watchlist-tool').exists()).toBe(false)
    expect(wrapper.get('.tool-state').text()).toContain('No source-classified industries are available for XHB')
    expect(wrapper.get('.tool-window__symbol').text()).toBe('XHB')
    expect(workspaceStore.linkedSymbol).toBe('UNXQ')

    wrapper.unmount()
    queryClient.clear()
  })

  it('starts profile classification for every resolved equity in the selected snapshot without waiting on a held member', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const workspaceStore = useWorkspaceStore(pinia)
    workspaceStore.setConstituentETF('XLB')
    const rows = Array.from({ length: 26 }, (_, index) => ({
      id: index + 1, snapshot_id: 19, constituent_instrument_id: 1000 + index,
      constituent_symbol: `EQ${index + 1}`, reported_symbol: `EQ${index + 1}`,
      holding_type: 'equity', row_type: 'security', is_resolved: true,
    }))
    rows.push({
      id: 27, snapshot_id: 19, constituent_instrument_id: null,
      constituent_symbol: null, reported_symbol: 'UNRESOLVED',
      holding_type: 'equity', row_type: 'security', is_resolved: false,
    } as never)
    rows.push({
      id: 28, snapshot_id: 19, constituent_instrument_id: null,
      constituent_symbol: null, reported_symbol: null,
      holding_type: 'cash', row_type: 'security', is_resolved: false,
    } as never)
    workspaceStore.etfHoldings = {
      XLB: { snapshot: { id: 19, composition_date: '2026-11-06' }, holdings: rows, total: rows.length, limit: 500, offset: 0, has_next: false } as never,
    }
    workspaceStore.etfIndustries = {
      XLB: {
        etf_symbol: 'XLB', composition_date: '2026-11-02', known_at: '2026-11-03T08:15:00Z',
        provenance: 'dated_holdings_snapshot', source_provider: 'controlled-source', completeness_status: 'partial',
        industries: [{ industry: 'Chemicals', constituent_count: 2, resolved_count: 1 }], exclusions: ['unclassified_constituent'],
      },
    }
    const refreshComposition = vi.spyOn(workspaceStore, 'loadETFIndustries').mockResolvedValue(null)
    const deferredById = new Map<number, ReturnType<typeof deferred<DataEnsureResponse>>>()
    const ensure = vi.spyOn(dataPreparationCoordinator, 'ensure').mockImplementation((request, _options) => {
      const id = (request.target as { instrument_id: number }).instrument_id
      const pending = deferred<DataEnsureResponse>()
      deferredById.set(id, pending)
      return pending.promise
    })
    const tool: WorkspaceWindowState = {
      id: 33, instance_key: 'industry-list', tool_type: 'watchlist', title: 'Industries',
      link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 1,
    }
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mount(WorkstationToolContent, {
      props: { tool },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: { UPlotChart: EmptyChartStub, ChartPlotLibrary: { template: '<div />' }, ChartTemplateControl: { template: '<div />' }, DrawingToolbar: { template: '<div />' }, ToolWindow: ToolWindowShell, RouterLink: { template: '<a><slot /></a>' } },
      },
    })
    await flushPromises()

    expect(ensure).toHaveBeenCalledTimes(26)
    expect(wrapper.text()).toContain('Chemicals')
    for (const [request] of ensure.mock.calls) {
      expect(request).toMatchObject({ datasets: ['profile'], required_profile_fields: ['industry'] })
      expect(request.target.kind).toBe('instrument')
    }
    expect(new Set(ensure.mock.calls.map(([request]) => (request.target as { instrument_id: number }).instrument_id))).toHaveProperty('size', 26)

    const ready: DataEnsureResponse = {
      request_id: 'profile-1000', status: 'ready', created_at: '2026-11-07T10:00:00Z', updated_at: '2026-11-07T10:00:00Z', version: 1,
      target: { kind: 'instrument', instrument_id: 1000 }, completed: 1, total: 1, last_progress_at: '2026-11-07T10:00:00Z',
      dependencies: [{ dependency_id: 'profile:1000', depends_on: [], instrument_id: 1000, symbol: 'EQ1', dataset: 'profile', status: 'ready', requested_start: null, requested_end: null, covered_start: null, covered_end: null, reason_code: null, retry_at: null, updated_at: '2026-11-07T10:00:00Z', covered_ranges: [] }],
    }
    deferredById.get(1000)!.resolve({
      ...ready,
      request_id: 'profile-1000-held', status: 'waiting', completed: 0,
      dependencies: [{ ...ready.dependencies[0]!, status: 'waiting', reason_code: 'provider_quota_admission_denied', retry_at: null }],
    })
    await flushPromises()
    expect(refreshComposition).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Preparing source industry classifications')
    deferredById.get(1001)!.resolve({
      ...ready,
      request_id: 'profile-1001', target: { kind: 'instrument', instrument_id: 1001 },
      dependencies: [{ ...ready.dependencies[0]!, dependency_id: 'profile:1001', instrument_id: 1001, symbol: 'EQ2' }],
    })
    await flushPromises()
    expect(refreshComposition).toHaveBeenCalledWith('XLB')

    for (const [id, pending] of deferredById) {
      if (id === 1000 || id === 1001) continue
      pending.resolve({ ...ready, request_id: `profile-${id}`, target: { kind: 'instrument', instrument_id: id }, dependencies: [{ ...ready.dependencies[0]!, dependency_id: `profile:${id}`, instrument_id: id, symbol: `EQ${id - 999}` }] })
    }
    await flushPromises()
    wrapper.unmount()
    queryClient.clear()
    ensure.mockRestore()
    refreshComposition.mockRestore()
  })

  it('does not prepare present-day profiles for an explicitly historical Industries view', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const workspaceStore = useWorkspaceStore(pinia)
    workspaceStore.setConstituentETF('XLB')
    workspaceStore.etfHoldings = {
      XLB: { snapshot: { id: 19, composition_date: '2025-11-06' }, holdings: [{
        id: 1, snapshot_id: 19, constituent_instrument_id: 1000, constituent_symbol: 'EQ1', reported_symbol: 'EQ1',
        holding_type: 'equity', row_type: 'security', is_resolved: true,
      }], total: 1, limit: 500, offset: 0, has_next: false } as never,
    }
    const ensure = vi.spyOn(dataPreparationCoordinator, 'ensure').mockResolvedValue({} as DataEnsureResponse)
    const tool: WorkspaceWindowState = {
      id: 34, instance_key: 'industry-list-history', tool_type: 'watchlist', title: 'Industries',
      link_group: 'blue', configuration: { as_of: '2025-11-07T00:00:00Z' }, style: {}, state_schema_version: 1, position: 1,
    }
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mount(WorkstationToolContent, {
      props: { tool },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: { UPlotChart: EmptyChartStub, ChartPlotLibrary: { template: '<div />' }, ChartTemplateControl: { template: '<div />' }, DrawingToolbar: { template: '<div />' }, ToolWindow: ToolWindowShell, RouterLink: { template: '<a><slot /></a>' } },
      },
    })
    await flushPromises()
    expect(ensure).not.toHaveBeenCalled()
    wrapper.unmount()
    queryClient.clear()
    ensure.mockRestore()
  })

  it('cancels stale snapshot preparation and only refreshes composition for the replacement context', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const workspaceStore = useWorkspaceStore(pinia)
    workspaceStore.setConstituentETF('XLB')
    const page = (snapshotId: number, instrumentId: number) => ({
      snapshot: { id: snapshotId, composition_date: '2026-11-06' },
      holdings: [{
        id: snapshotId, snapshot_id: snapshotId, constituent_instrument_id: instrumentId,
        constituent_symbol: `EQ${instrumentId}`, reported_symbol: `EQ${instrumentId}`,
        holding_type: 'equity', row_type: 'security', is_resolved: true,
      }], total: 1, limit: 500, offset: 0, has_next: false,
    })
    workspaceStore.etfHoldings = { XLB: page(19, 1000) as never }
    const refreshComposition = vi.spyOn(workspaceStore, 'loadETFIndustries').mockResolvedValue(null)
    const pendingById = new Map<number, ReturnType<typeof deferred<DataEnsureResponse>>>()
    const ensure = vi.spyOn(dataPreparationCoordinator, 'ensure').mockImplementation(request => {
      const id = (request.target as { instrument_id: number }).instrument_id
      const pending = deferred<DataEnsureResponse>()
      pendingById.set(id, pending)
      return pending.promise
    })
    const tool: WorkspaceWindowState = {
      id: 35, instance_key: 'industry-list-snapshot-race', tool_type: 'watchlist', title: 'Industries',
      link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 1,
    }
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const wrapper = mount(WorkstationToolContent, {
      props: { tool },
      global: {
        plugins: [pinia, [VueQueryPlugin, { queryClient }]],
        stubs: { UPlotChart: EmptyChartStub, ChartPlotLibrary: { template: '<div />' }, ChartTemplateControl: { template: '<div />' }, DrawingToolbar: { template: '<div />' }, ToolWindow: ToolWindowShell, RouterLink: { template: '<a><slot /></a>' } },
      },
    })
    await flushPromises()
    expect(ensure).toHaveBeenCalledTimes(1)
    const oldSignal = ensure.mock.calls[0]![1]?.signal

    workspaceStore.etfHoldings = { ...workspaceStore.etfHoldings, XLB: page(20, 2000) as never }
    await flushPromises()
    expect(ensure).toHaveBeenCalledTimes(2)
    expect(oldSignal?.aborted).toBe(true)

    const readyResponse = (id: number): DataEnsureResponse => ({
      request_id: `profile-${id}`, status: 'ready', created_at: '2026-11-07T10:00:00Z', updated_at: '2026-11-07T10:00:00Z', version: 1,
      target: { kind: 'instrument', instrument_id: id }, completed: 1, total: 1, last_progress_at: '2026-11-07T10:00:00Z',
      dependencies: [{ dependency_id: `profile:${id}`, depends_on: [], instrument_id: id, symbol: `EQ${id}`, dataset: 'profile', status: 'ready', requested_start: null, requested_end: null, covered_start: null, covered_end: null, reason_code: null, retry_at: null, updated_at: '2026-11-07T10:00:00Z', covered_ranges: [] }],
    })
    pendingById.get(1000)!.resolve(readyResponse(1000))
    await flushPromises()
    expect(refreshComposition).not.toHaveBeenCalled()
    pendingById.get(2000)!.resolve(readyResponse(2000))
    await flushPromises()
    expect(refreshComposition).toHaveBeenCalledTimes(1)
    expect(refreshComposition).toHaveBeenCalledWith('XLB')

    wrapper.unmount()
    queryClient.clear()
    ensure.mockRestore()
    refreshComposition.mockRestore()
  })
})
