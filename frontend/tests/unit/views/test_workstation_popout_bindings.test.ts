import { defineComponent, h, nextTick, reactive } from 'vue'
import { flushPromises, mount as rawMount, type MountingOptions } from '@vue/test-utils'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const harness = vi.hoisted(() => {
  const ratioWindow = {
    instance_key: 'ratio-chart',
    tool_type: 'chart',
    title: 'Relative strength',
    link_group: 'blue',
    configuration: { expression: '=SPY/RSP', auto_ratio: true } as Record<string, unknown>,
  }
  const popoutWindow = {
    instance_key: 'benchmark-list',
    tool_type: 'watchlist',
    title: 'Benchmarks',
    link_group: 'blue',
    configuration: {} as Record<string, unknown>,
  }
  const chartWindow = {
    instance_key: 'chart-main',
    tool_type: 'chart',
    title: 'Chart',
    link_group: 'blue',
    configuration: {} as Record<string, unknown>,
  }
  const tab = {
    stable_key: 'us-top-down',
    name: 'US Top Down',
    windows: [popoutWindow, chartWindow, ratioWindow],
    active_window_key: 'benchmark-list',
    layout_config: null,
  }
  const workspace = {
    workspace: { id: 1, is_default: false, name: 'US Top Down', tabs: [tab], settings: { factory_id: 'us-top-down' } },
    workspaces: [{ id: 1, name: 'US Top Down', is_default: false, position: 0, revision: 1 }],
    activeTabKey: 'us-top-down',
    activeTab: tab,
    linkedSymbol: 'SPY',
    linkedTimeframe: 'D1',
    isPersistenceLeader: true,
    loading: false,
    error: null,
    snapshotSaveStatus: 'saved' as 'saved' | 'saving' | 'error',
    snapshotSaveError: null as string | null,
    constituentETF: null,
    etfHoldings: {} as Record<string, { snapshot?: { id: number; etf_symbol: string } } | null>,
    etfConstituentSnapshotErrors: {} as Record<string, string | null>,
    marketGroups: { 'us-benchmarks': { members: [] }, 'sp500-sectors': { members: [] } },
    groupSnapshots: {},
    breadth: {},
    breadthHistory: {},
    technicals: {} as Record<string, { freshness?: string } | null>,
    marketAnalysisRefreshing: false,
    connect: vi.fn(),
    disconnect: vi.fn(),
    loadDefault: vi.fn().mockResolvedValue(undefined),
    refreshMarketAnalysis: vi.fn().mockResolvedValue(undefined),
    refreshWorkspaces: vi.fn().mockResolvedValue(undefined),
    switchWorkspace: vi.fn().mockResolvedValue(undefined),
    publishSymbol: vi.fn(),
    publishTimeframe: vi.fn(),
    symbolForLinkGroup: vi.fn(() => 'XLK'),
    selectToolSymbol: vi.fn(),
    loadETFHoldings: vi.fn().mockResolvedValue(undefined),
    setConstituentETF: vi.fn(),
    loadETFIndustries: vi.fn().mockResolvedValue(undefined),
    loadTechnical: vi.fn().mockResolvedValue(undefined),
    scheduleSnapshot: vi.fn(),
    saveSnapshot: vi.fn().mockResolvedValue(true),
    setActiveWindow: vi.fn(),
    updateToolLinkGroup: vi.fn(),
    updateToolTimeframe: vi.fn(),
    timeframeLinkGroupForTool: vi.fn((_tool: unknown) => 'blue'),
    timeframeForTool: vi.fn((_windowKey: string) => 'D1'),
    timeframeForLinkGroup: vi.fn((_group: string, isolatedTimeframe?: string | null) => isolatedTimeframe ?? 'D1'),
    updateToolTimeframeLinkGroup: vi.fn(),
    selectIndustryProxy: vi.fn(),
    selectIndustry: vi.fn(),
    closeTool: vi.fn(),
    cloneActiveTab: vi.fn(),
    renameTab: vi.fn(() => true),
    captureTabRecovery: vi.fn(),
    deleteTab: vi.fn(),
    restoreDeletedTab: vi.fn(),
    resetFactoryWorkspace: vi.fn(),
    openTool: vi.fn(),
    isEditorTarget: vi.fn(() => false),
  }
  const recent = {
    recent: [{ symbol: 'XLK', name: 'Technology Select Sector SPDR Fund', viewedAt: 2 }],
    add: vi.fn(),
    previous: vi.fn(),
    clear: vi.fn(),
  }
  const drawings = {
    activeToolType: null as string | null,
    setActiveTool: vi.fn(),
  }
  const chart = {
    symbol: 'SPY',
    timeframe: 'D1',
    instrument: { id: 2, symbol: 'SPY' } as { id: number; symbol: string } | null,
    barType: 'candles',
    bars: [] as unknown[],
    isLoading: false,
    isFetchingHistory: false,
    error: null as string | null,
    loadBars: vi.fn(async (symbol: string) => { chart.symbol = symbol }),
    refreshLocalBars: vi.fn(async () => undefined),
  }
  return { workspace, recent, drawings, chart, popoutWindow, chartWindow, ratioWindow }
})
const routeState = vi.hoisted(() => ({ path: '/popout/benchmark-list', params: { windowKey: 'benchmark-list' }, query: {} as Record<string, string> }))
const routerPush = vi.hoisted(() => vi.fn())
const routerReplace = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const apiGet = vi.hoisted(() => vi.fn().mockResolvedValue([]))
const apiPost = vi.hoisted(() => vi.fn())
const dataPreparationPost = vi.hoisted(() => vi.fn())
const refreshMountedPanels = vi.hoisted(() => vi.fn().mockResolvedValue(undefined))
const openableTools = vi.hoisted(() => [
  { key: 'chart', tool_type: 'chart', title: 'Chart', instance_prefix: 'chart', configuration: { symbol: 'SPY', timeframe: 'D1' } },
  { key: 'watchlist', tool_type: 'watchlist', title: 'WatchList', instance_prefix: 'watchlist', configuration: { personal: true, watchlist_id: null } },
  { key: 'favorites', tool_type: 'watchlist', title: 'My Favorites', instance_prefix: 'favorites', configuration: { personal: true, favorites: true } },
  { key: 'notes', tool_type: 'notes', title: 'Notes', instance_prefix: 'notes', configuration: { scope: 'active-instrument' } },
  { key: 'alerts', tool_type: 'alerts', title: 'Alerts', instance_prefix: 'alerts', configuration: { scope: 'active-instrument' } },
  { key: 'easy-scan', tool_type: 'scan', title: 'EasyScan', instance_prefix: 'easy-scan', configuration: { scope: 'saved-conditions' } },
  { key: 'market-gauge', tool_type: 'gauge', title: 'Market Gauge', instance_prefix: 'market-gauge', configuration: { scope: 'saved-scans' } },
  { key: 'study-lab', tool_type: 'study_lab', title: 'Study Lab', instance_prefix: 'study-lab', configuration: { symbol: 'SPY' } },
  { key: 'research-results', tool_type: 'research_results', title: 'Study Results', instance_prefix: 'research-results', configuration: {} },
  { key: 'relative-rotation', tool_type: 'relative_rotation', title: 'Relative Rotation', instance_prefix: 'relative-rotation', configuration: { group_key: 'sp500-sectors', benchmark: 'SPY', timeframe: 'D1', sampling: 1, lookback: 20, tail_length: 10, adjusted: true } },
  { key: 'breadth', tool_type: 'breadth', title: 'Market Breadth', instance_prefix: 'breadth', configuration: { group_key: 'sp500-sectors' } },
  { key: 'market-map', tool_type: 'market_map', title: 'Market Map', instance_prefix: 'market-map', configuration: { group_by: 'sector_industry', period: '1D', area_metric: 'market_cap', color_metric: 'return' } },
  { key: 'technical-summary', tool_type: 'technical_summary', title: 'Technicals', instance_prefix: 'technical-summary', configuration: { scope: 'selected' } },
  { key: 'coverage', tool_type: 'coverage', title: 'Coverage', instance_prefix: 'coverage', configuration: { scope: 'selected' } },
  { key: 'report', tool_type: 'report', title: 'Instrument Report', instance_prefix: 'report', configuration: {} },
  { key: 'code-library', tool_type: 'code_library', title: 'Python Library', instance_prefix: 'code-library', configuration: {} },
  { key: 'benchmark-list', tool_type: 'watchlist', title: 'Benchmarks', instance_prefix: 'benchmark-list', configuration: { market_group: 'us-benchmarks' } },
  { key: 'industry-list', tool_type: 'watchlist', title: 'Industries', instance_prefix: 'industry-list', configuration: { market_group: 'selected-sector-industries' } },
  { key: 'constituent-list', tool_type: 'watchlist', title: 'Constituents', instance_prefix: 'constituent-list', configuration: { market_group: 'selected-industry-constituents' } },
  { key: 'sector-list', tool_type: 'watchlist', title: 'S&P 500 Sectors', instance_prefix: 'sector-list', configuration: { market_group: 'sp500-sectors' } },
  { key: 'ratio-chart', tool_type: 'chart', title: 'Relative Strength', instance_prefix: 'ratio-chart', configuration: { expression: '=SPY/RSP', timeframe: 'D1', auto_ratio: true } },
])

vi.mock('@/stores/workspace', () => ({
  useWorkspaceStore: () => Object.assign(harness.workspace, {
    toolCatalogue: openableTools,
    toolDefinition: (key: string) => openableTools.find(tool => tool.key === key) ?? null,
    loadToolCatalogue: vi.fn().mockResolvedValue(openableTools),
  }),
}))
vi.mock('@/stores/chart', () => ({
  useChartStore: () => harness.chart,
  refreshMountedWorkstationChartPanels: refreshMountedPanels,
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ logout: vi.fn().mockResolvedValue(undefined) }) }))
vi.mock('@/stores/watchlist', () => ({ useWatchlistStore: () => ({ reorderItems: vi.fn().mockResolvedValue(undefined) }) }))
vi.mock('@/stores/recentInstruments', () => ({ useRecentInstrumentsStore: () => harness.recent }))
vi.mock('@/stores/drawings', () => ({ useDrawingsStore: () => harness.drawings }))
vi.mock('@/lib/instruments', () => ({
  ensureKnownInstrumentSymbol: vi.fn((symbol: string) => Promise.resolve(symbol)),
  resolveKnownInstrument: vi.fn((symbol: string) => Promise.resolve({ symbol, id: 77 })),
}))
vi.mock('@/lib/api', () => ({
  api: {
    get: apiGet,
    post: (path: string, body: unknown, options?: unknown) => path === '/data/ensure'
      ? dataPreparationPost(body, options)
      : options === undefined ? apiPost(path, body) : apiPost(path, body, options),
  },
}))
vi.mock('@/components/workstation/WorkspaceLayoutHost.vue', () => ({ default: defineComponent({ template: '<div />' }) }))
vi.mock('golden-layout', () => ({}))
vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRoute: () => routeState,
    useRouter: () => ({ resolve: vi.fn(), push: routerPush, replace: routerReplace }),
  }
})

import WorkstationView from '@/views/WorkstationView.vue'
import { resolveKnownInstrument } from '@/lib/instruments'
import { holdingDrilldownRouteQuery, holdingDrilldownRouteState } from '@/lib/etfHoldingDrilldown'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

function readyPreparationResponse(request: any, call = 1) {
  const now = '2026-11-06T12:00:00Z'
  const datasets = request.datasets ?? ['identity', 'profile', 'history']
  const targetId = request.target?.kind === 'instrument' ? request.target.instrument_id ?? null : null
  const targetSymbol = request.target?.kind === 'instrument' ? request.target.symbol ?? null : null
  return {
    request_id: `workstation-preparation-${call}`,
    status: 'ready',
    created_at: now,
    updated_at: now,
    last_progress_at: now,
    version: 1,
    target: request.target,
    completed: datasets.length,
    total: datasets.length,
    has_pending_work: false,
    dependencies: datasets.map((dataset: string) => ({
      dependency_id: `${dataset}:${targetId ?? targetSymbol ?? 'fixture'}`,
      depends_on: [],
      instrument_id: targetId,
      symbol: targetSymbol,
      dataset,
      status: 'ready',
      requested_start: null,
      requested_end: null,
      covered_start: dataset === 'history' ? '2024-01-01T00:00:00Z' : null,
      covered_end: dataset === 'history' ? now : null,
      reason_code: null,
      retry_at: null,
      updated_at: now,
      covered_ranges: dataset === 'history'
        ? [{ start_at: '2024-01-01T00:00:00Z', end_at: now, data_source_id: 1, market_series_id: 1, adjustment_basis: 'split', adjustment_version: '1', is_adjusted: true }]
        : [],
    })),
  }
}

const NavigationLinkStub = defineComponent({
  props: { to: { type: String, required: true } },
  setup(props, { attrs, slots }) {
    return () => h('a', {
      ...attrs,
      href: props.to,
      onClick: (event: MouseEvent) => {
        event.preventDefault()
        routerPush(props.to)
        const click = attrs.onClick
        if (Array.isArray(click)) click.forEach(handler => typeof handler === 'function' && handler(event))
        else if (typeof click === 'function') click(event)
      },
    }, slots.default?.())
  },
})

function mount(component: typeof WorkstationView, options: MountingOptions<typeof WorkstationView> = {}) {
  return rawMount(component, {
    ...options,
    global: {
      ...options.global,
      stubs: {
        'router-link': NavigationLinkStub,
        ...options.global?.stubs,
      },
      plugins: [
        ...(options.global?.plugins ?? []),
        [VueQueryPlugin, { queryClient: new QueryClient() }],
      ],
    },
  })
}

function appendChartPlotTarget(parent: Element, windowKey: string) {
  const toolWindow = document.createElement('section')
  toolWindow.className = 'tool-window'
  toolWindow.dataset.windowKey = windowKey
  const plot = document.createElement('div')
  plot.className = 'uplot'
  toolWindow.append(plot)
  parent.append(toolWindow)
  return plot
}

const ToolStub = defineComponent({
  emits: ['conditionFilterMode', 'pinnedBooleanKeys', 'columnGroups', 'stackedColumnKeys', 'configuration', 'selectProxy', 'selectIndustry', 'compare', 'ratio', 'row-action', 'open-study'],
  template: `<div class="tool-stub">
    <button class="open-study" @click="$emit('open-study', { name: 'Saved XLB study', versionId: 42, source: 'return 1', outputContract: 'scalar', parameterSchema: {}, defaultParameters: { symbol: 'XLB', timeframe: 'W1', benchmark: 'QQQ', adjustment: 'raw', session: 'all', universe_source_id: 'saved-universe', symbols: 'XLB,XLK', start_date: '2025-01-01', end_date: '2025-12-31', as_of: '2025-12-31' } })">Open saved study</button>
    <button class="mode" @click="$emit('conditionFilterMode', 'benchmark-list', 'active')">mode</button>
    <button class="pin" @click="$emit('pinnedBooleanKeys', 'benchmark-list', ['above_ma50'])">pin</button>
    <button class="groups" @click="$emit('columnGroups', 'benchmark-list', { rsi14: 'Momentum' })">groups</button>
    <button class="stack" @click="$emit('stackedColumnKeys', 'benchmark-list', ['rsi14'])">stack</button>
    <button class="configuration" @click="$emit('configuration', 'benchmark-list', { column_keys: ['symbol'] })">configuration</button>
    <button class="proxy" @click="$emit('selectProxy', 'XLK', 99)">proxy</button>
    <button class="proxy-without-id" @click="$emit('selectProxy', 'XLK')">proxy without id</button>
    <button class="industry" @click="$emit('selectIndustry', 'Semiconductors', 'XLK')">industry</button>
    <button class="compare" @click="$emit('compare', ['SPY', 'XLK', 'XLE'])">compare</button>
    <button class="ratio" @click="$emit('ratio', ['XLK', 'SPY'])">ratio</button>
    <button class="copy" @click="$emit('row-action', 'copy', { symbol: 'XLK', instrumentId: 1 })">copy</button>
  </div>`,
})

describe('WorkstationView pop-out bindings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    const historyState = { ...(window.history.state ?? {}) }
    delete historyState.tcHoldingSelectionHandoff
    delete historyState.tcHoldingIdentityHandoff
    window.history.replaceState(historyState, '', window.location.href)
    refreshMountedPanels.mockReset().mockResolvedValue(undefined)
    harness.workspace.refreshMarketAnalysis.mockReset().mockResolvedValue(undefined)
    harness.popoutWindow.configuration = {}
    harness.chartWindow.configuration = {}
    harness.ratioWindow.configuration = { expression: '=SPY/RSP', auto_ratio: true }
    routeState.path = '/popout/benchmark-list'
    routeState.params = { windowKey: 'benchmark-list' }
    routeState.query = {}
    harness.workspace.activeTab.active_window_key = 'benchmark-list'
    apiGet.mockReset()
    apiGet.mockResolvedValue([])
    apiPost.mockReset()
    dataPreparationPost.mockReset().mockImplementation(async (request: any) =>
      readyPreparationResponse(request, dataPreparationPost.mock.calls.length),
    )
    harness.workspace.loadETFHoldings = vi.fn().mockResolvedValue(undefined)
    harness.workspace.loadETFIndustries = vi.fn().mockResolvedValue(undefined)
    harness.workspace.loadTechnical = vi.fn().mockResolvedValue(undefined)
    harness.workspace.linkedTimeframe = 'D1'
    harness.workspace.linkedSymbol = 'SPY'
    harness.workspace.constituentETF = null
    harness.workspace.error = null
    harness.workspace.snapshotSaveStatus = 'saved'
    harness.workspace.snapshotSaveError = null
    harness.workspace.etfHoldings = {}
    harness.workspace.etfConstituentSnapshotErrors = {}
    harness.workspace.technicals = {}
    harness.chart.symbol = 'SPY'
    harness.chart.timeframe = 'D1'
    harness.chart.instrument = { id: 2, symbol: 'SPY' }
    harness.chart.bars = []
    harness.chart.loadBars.mockClear()
    harness.chart.refreshLocalBars.mockClear()
    harness.workspace.publishTimeframe = vi.fn()
    harness.workspace.loadDefault = vi.fn().mockResolvedValue(undefined)
    harness.workspace.activeTab = harness.workspace.workspace.tabs[0]
    harness.workspace.openTool.mockReset()
    harness.workspace.renameTab.mockReset().mockReturnValue(true)
    harness.workspace.marketGroups = { 'us-benchmarks': { members: [] }, 'sp500-sectors': { members: [] } }
    harness.workspace.groupSnapshots = {}
    harness.workspace.breadth = {}
    harness.workspace.breadthHistory = {}
    harness.recent.recent = [{ symbol: 'XLK', name: 'Technology Select Sector SPDR Fund', viewedAt: 2 }]
    harness.drawings.activeToolType = null
    harness.drawings.setActiveTool.mockClear()
  })

  it('preserves a saved Library study symbol and dataset defaults when opening the immutable version', async () => {
    routeState.path = '/popout/benchmark-list'
    routeState.params = { windowKey: 'benchmark-list' }
    harness.workspace.linkedSymbol = 'SPY'
    harness.workspace.activeTab.active_window_key = 'study-lab-return'
    harness.workspace.openTool.mockReturnValue({ instance_key: 'study-lab-return', title: 'Study Lab' })
    const wrapper = mount(WorkstationView, {
      attachTo: document.body,
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    wrapper.element.insertAdjacentHTML('beforeend', '<div class="workspace-layout-host__virtual-tool" data-tool-key="study-lab-return"></div>')
    try {
      await wrapper.get('.open-study').trigger('click')
      await flushPromises()

      expect(harness.workspace.openTool).toHaveBeenCalledWith(
        expect.objectContaining({ tool_type: 'study_lab' }),
        expect.objectContaining({
          study_asset_version_id: 42,
          symbol: 'XLB',
          timeframe: 'W1',
          benchmark: 'QQQ',
          adjustment: 'raw',
          session: 'all',
          universe_source_id: 'saved-universe',
          symbols: 'XLB,XLK',
          start_date: '2025-01-01',
          end_date: '2025-12-31',
          as_of: '2025-12-31',
        }),
      )
      expect(harness.workspace.linkedSymbol).toBe('SPY')
    } finally {
      wrapper.unmount()
      wrapper.element.remove()
    }
  })

  it('opens shared feature routes through RouterLink navigation', async () => {
    routeState.path = '/chart'
    routeState.params = {}
    const wrapper = mount(WorkstationView, {
      attachTo: document.body,
      global: {
        stubs: {
          WorkstationToolContent: ToolStub,
          WorkspaceLayoutHost: true,
          'router-link': NavigationLinkStub,
        },
      },
    })
    try {
      await wrapper.get('.workstation__brand').trigger('click')
      const menu = wrapper.get('[role="menu"][aria-label="Application navigation"]')
      const links = menu.findAll('[role="menuitem"]')
      expect(links).toHaveLength(11)
      expect(menu.get('[data-navigation-key="etf"]').attributes('href')).toBe('/legacy/etf-holdings')
      expect(menu.get('[data-navigation-key="strategy-v2"]').attributes('href')).toBe('/legacy/strategy-lab-v2')

      await menu.get('[data-navigation-key="etf"]').trigger('click')
      expect(routerPush).toHaveBeenCalledWith('/legacy/etf-holdings')
    } finally {
      wrapper.unmount()
      wrapper.element.remove()
    }
  })

  it('supports keyboard menu navigation, Escape focus return, and a bounded narrow viewport', async () => {
    routeState.path = '/chart'
    routeState.params = {}
    const originalWidth = window.innerWidth
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 320 })
    const wrapper = mount(WorkstationView, {
      attachTo: document.body,
      global: {
        stubs: {
          WorkstationToolContent: ToolStub,
          WorkspaceLayoutHost: true,
          'router-link': NavigationLinkStub,
        },
      },
    })
    const trigger = wrapper.get('.workstation__brand')
    try {
      await trigger.trigger('keydown', { key: 'ArrowDown' })
      await flushPromises()
      const menu = wrapper.get('.workstation__application-menu')
      const menuItems = menu.findAll('[role="menuitem"]')
      expect(document.activeElement).toBe(menuItems[0].element)
      const menuLeft = Number.parseFloat((menu.element as HTMLElement).style.left)
      const menuWidth = Number.parseFloat((menu.element as HTMLElement).style.width)
      expect(menuLeft).toBeGreaterThanOrEqual(8)
      expect(menuLeft + menuWidth).toBeLessThanOrEqual(312)

      await menuItems[0].trigger('keydown', { key: 'ArrowDown' })
      await flushPromises()
      expect(document.activeElement).toBe(menuItems[1].element)
      await menuItems[1].trigger('keydown', { key: 'Escape' })
      await nextTick()
      expect(wrapper.find('.workstation__application-menu').exists()).toBe(false)
      expect(document.activeElement).toBe(trigger.element)
    } finally {
      wrapper.unmount()
      wrapper.element.remove()
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: originalWidth })
    }
  })

  it('discovers a ticker-shaped local miss after debounce without acquiring during typing', async () => {
    routeState.path = '/chart'
    routeState.params = {}
    apiGet.mockImplementation((path: string, params?: Record<string, unknown>) => {
      if (path === '/instruments/search' && params?.q === 'QQQ') return Promise.resolve([{ symbol: 'QQQ', name: 'Invesco QQQ Trust', type: 'ETF', exchange: 'NASDAQ', instrument_id: 3 }])
      if (path === '/instruments/search') return Promise.resolve([])
      return Promise.resolve([])
    })
    apiPost.mockResolvedValue({
      request_id: 'controlled-discovery', status: 'complete',
      candidates: [{ symbol: 'BWET', name: 'Controlled candidate', exchange: 'ARCX', type: 'ETF', provider: 'test-fixture', instrument_id: null, identity_status: 'provider_candidate' }],
      source_outcomes: [],
    })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true, 'router-link': NavigationLinkStub } },
    })
    try {
      await flushPromises()
      expect(apiPost).not.toHaveBeenCalled()

      const input = wrapper.get('[aria-label="Active symbol"]')
      await input.setValue('QQQ')
      await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/instruments/search', { q: 'QQQ', canonical_only: true }, { priority: 'high' }))
      await vi.waitFor(() => expect(wrapper.get('.workstation__canonical-symbol-options').text()).toContain('QQQ'))
      expect(apiPost).not.toHaveBeenCalled()

      await input.setValue('BWET')
      await vi.waitFor(() => expect(apiPost).toHaveBeenCalledWith('/instruments/discover', expect.objectContaining({
        query: 'BWET', types: [], limit: 10, request_id: expect.any(String),
      }), expect.objectContaining({ priority: 'high', signal: expect.any(AbortSignal) })), { timeout: 1500 })
      expect(apiPost).toHaveBeenCalledTimes(1)
      expect(wrapper.text()).toContain('Select one to verify its identity')
      expect(wrapper.text()).toContain('Use BWET')
    } finally {
      wrapper.unmount()
    }
  })

  it('acknowledges a cold tool command immediately and applies it exactly once after hydration', async () => {
    routeState.path = '/chart'
    routeState.params = {}
    const tab = harness.workspace.activeTab
    ;(harness.workspace as { activeTab: typeof tab | null }).activeTab = null
    let finishLoad!: () => void
    harness.workspace.loadDefault.mockImplementation(() => new Promise<void>(resolve => { finishLoad = resolve }))
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await wrapper.get('.workstation__tool-library > button').trigger('click')
      await wrapper.findAll('.workstation__tool-library-menu [role="menuitem"]')
        .find(item => item.text() === 'Study Results')!.trigger('click')
      expect(harness.workspace.openTool).not.toHaveBeenCalled()
      expect(wrapper.find('.workstation__tool-library-menu').exists()).toBe(false)
    } finally {
      harness.workspace.activeTab = tab
      finishLoad()
      await flushPromises()
      wrapper.unmount()
    }
    expect(harness.workspace.openTool).toHaveBeenCalledTimes(1)
    expect(harness.workspace.openTool).toHaveBeenCalledWith(
      expect.objectContaining({ tool_type: 'research_results', title: 'Study Results' }),
      {},
    )
  })

  it('persists ordinary active-layout selection so reload restores the intended workspace context', async () => {
    routeState.path = '/chart'
    routeState.params = {}
    const topDown = harness.workspace.workspace.tabs[0]
    const studyTab = {
      stable_key: 'study-lab',
      name: 'Study Lab',
      windows: [{ instance_key: 'results', tool_type: 'research_results', title: 'Study Results', link_group: 'grey', configuration: {} }],
      active_window_key: 'study',
      layout_config: null,
    }
    harness.workspace.workspace.tabs = [topDown, studyTab]
    harness.workspace.activeTab = topDown
    harness.workspace.activeTabKey = topDown.stable_key
    harness.workspace.saveSnapshot.mockResolvedValue(true)
    const wrapper = mount(WorkstationView, {
      attachTo: document.body,
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })

    await wrapper.get('[data-tab-key="study-lab"]').trigger('click')
    await flushPromises()

    expect(harness.workspace.activeTabKey).toBe('study-lab')
    expect(harness.workspace.scheduleSnapshot).toHaveBeenCalled()
    expect(harness.workspace.saveSnapshot).toHaveBeenCalled()
    wrapper.unmount()
    harness.workspace.workspace.tabs = [topDown]
    harness.workspace.activeTab = topDown
    harness.workspace.activeTabKey = topDown.stable_key
  })

  it('cancels an accepted cold tool command when its workstation unmounts before hydration', async () => {
    routeState.path = '/chart'
    routeState.params = {}
    const tab = harness.workspace.activeTab
    ;(harness.workspace as { activeTab: typeof tab | null }).activeTab = null
    let finishLoad!: () => void
    harness.workspace.loadDefault.mockImplementation(() => new Promise<void>(resolve => { finishLoad = resolve }))
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await wrapper.get('.workstation__tool-library > button').trigger('click')
    await wrapper.get('.workstation__tool-library-menu [role="menuitem"]').trigger('click')
    expect(harness.workspace.openTool).not.toHaveBeenCalled()
    wrapper.unmount()
    harness.workspace.activeTab = tab
    finishLoad()
    await flushPromises()
    expect(harness.workspace.openTool).not.toHaveBeenCalled()
  })

  it('opens a tool immediately if a usable tab exists while initial loading remains pending', async () => {
    routeState.path = '/chart'
    routeState.params = {}
    let finishLoad!: () => void
    harness.workspace.loadDefault.mockImplementation(() => new Promise<void>(resolve => { finishLoad = resolve }))
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await wrapper.get('.workstation__tool-library > button').trigger('click')
      await wrapper.get('.workstation__tool-library-menu [role="menuitem"]').trigger('click')
      expect(harness.workspace.openTool).toHaveBeenCalledTimes(1)
      expect(wrapper.find('.workstation__tool-library-menu').exists()).toBe(false)
      finishLoad()
      await flushPromises()
      expect(harness.workspace.openTool).toHaveBeenCalledTimes(1)
    } finally {
      finishLoad()
      wrapper.unmount()
    }
  })

  it('forwards watchlist persistence and proxy events from a floated tool to the shell', async () => {
    const configurationReference = harness.popoutWindow.configuration
    const wrapper = mount(WorkstationView, {
      global: {
        stubs: {
          WorkstationToolContent: ToolStub,
          WorkspaceLayoutHost: true,
        },
      },
    })

    await wrapper.find('.configuration').trigger('click')
    await wrapper.find('.mode').trigger('click')
    await wrapper.find('.pin').trigger('click')
    await wrapper.find('.groups').trigger('click')
    await wrapper.find('.stack').trigger('click')
    await wrapper.find('.proxy').trigger('click')
    await wrapper.find('.industry').trigger('click')
    await wrapper.find('.compare').trigger('click')
    await wrapper.find('.ratio').trigger('click')
    await wrapper.find('.copy').trigger('click')

    expect(harness.popoutWindow.configuration).toMatchObject({
      condition_filter_mode: 'active',
      pinned_boolean_keys: ['above_ma50'],
      column_groups: { rsi14: 'Momentum' },
      stacked_column_keys: ['rsi14'],
      column_keys: ['symbol'],
    })
    expect(harness.popoutWindow.configuration).toBe(configurationReference)
    expect(harness.chartWindow.configuration).toMatchObject({ comparison_symbols: ['XLK', 'XLE'] })
    expect(harness.ratioWindow.configuration).toMatchObject({ expression: '=XLK/SPY', auto_ratio: false })
    expect(harness.workspace.error).toBe('Copied XLK')
    expect(harness.workspace.selectIndustryProxy).toHaveBeenCalledWith('XLK')
    expect(harness.workspace.selectIndustry).toHaveBeenCalledWith('XLK', 'Semiconductors')
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'XLK', instrumentId: 99, group: 'blue' })))
    expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'XLK', instrumentId: 99, group: 'blue', sourceWindowKey: 'workstation' }))
    expect(harness.workspace.scheduleSnapshot).toHaveBeenCalled()
    expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'XLK', group: 'blue', sourceWindowKey: 'workstation' }))
    expect(harness.workspace.symbolForLinkGroup).toHaveBeenCalledWith('blue', null)
    wrapper.unmount()
  })

  it('names and focuses the pop-out landmark for keyboard users', async () => {
    let finishWorkspaceLoad!: () => void
    harness.workspace.loadDefault.mockReturnValue(new Promise<void>(resolve => { finishWorkspaceLoad = resolve }))
    const wrapper = mount(WorkstationView, {
      attachTo: document.body,
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })

    const popout = wrapper.get('.workstation__popout')
    expect(popout.attributes('aria-label')).toBe('TC2000 Benchmarks pop-out')
    expect(popout.attributes('tabindex')).toBe('-1')
    const popoutContextId = popout.attributes('aria-describedby')
    expect(popoutContextId).toMatch(/-popout-context$/)
    expect(popoutContextId).not.toBe('workstation-popout-context')
    expect(popout.get(`#${popoutContextId}`).text()).toContain('browser-managed pop-out window')
    expect(popout.get(`#${popoutContextId}`).text()).toContain('controlled by the browser and operating system')
    await nextTick()
    expect(harness.workspace.loadDefault).toHaveBeenCalled()
    expect(document.activeElement).toBe(popout.element)
    finishWorkspaceLoad()
    await flushPromises()
    wrapper.unmount()
  })

  it('gives the compact clone-layout control an explicit accessible name', async () => {
    routeState.path = '/'
    routeState.params = {}
    const wrapper = mount(WorkstationView, {
      attachTo: document.body,
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })

    const cloneButton = wrapper.get('button[aria-label="Duplicate layout"]')
    expect(cloneButton.text()).toBe('+')
    expect(await cloneButton.attributes('title')).toBe('Duplicate layout')
    await wrapper.get('.workstation__workspace-menu > button').trigger('click')
    expect(wrapper.get('.workstation__layout-list input[aria-label="Rename layout"]').exists()).toBe(true)
    await cloneButton.trigger('click')
    expect(harness.workspace.cloneActiveTab).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('gives the compact factory-reset control an explicit accessible name', async () => {
    routeState.path = '/'
    routeState.params = {}
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })

    const resetButton = wrapper.get('button[aria-label="Reset factory workspace"]')
    expect(resetButton.text()).toBe('')
    expect(await resetButton.attributes('title')).toBe('Reset factory workspace')
    await resetButton.trigger('click')
    expect(confirm).toHaveBeenCalledWith('Reset this factory workspace? Your current layout changes will be replaced.')
    expect(harness.workspace.resetFactoryWorkspace).toHaveBeenCalledTimes(1)
    confirm.mockRestore()
    wrapper.unmount()
  })

  it('offers an accessible undo for a confirmed layout deletion in the same workspace', async () => {
    routeState.path = '/'
    routeState.params = {}
    const baseTab = harness.workspace.workspace.tabs[0]
    const deletedTab = { ...baseTab, id: 2, stable_key: 'layout-recovery', name: 'Saved layout', position: 1 }
    harness.workspace.workspace.tabs = [baseTab, deletedTab]
    const recovery = { workspace_id: 1, tab: deletedTab, position: 1 }
    harness.workspace.captureTabRecovery.mockReturnValue(recovery)
    harness.workspace.deleteTab.mockImplementation((stableKey: string) => {
      harness.workspace.workspace.tabs = harness.workspace.workspace.tabs.filter(tab => tab.stable_key !== stableKey)
      return true
    })
    harness.workspace.restoreDeletedTab.mockReturnValue(true)
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })

    try {
      await wrapper.get('button[title="Manage workspace layouts"]').trigger('click')
      await wrapper.get('button[aria-label="Delete layout Saved layout"]').trigger('click')
      expect(confirm).toHaveBeenCalledWith('Delete layout “Saved layout”?')
      expect(harness.workspace.deleteTab).toHaveBeenCalledWith('layout-recovery')
      const recoveryNotice = wrapper.get('.workstation__layout-recovery')
      expect(recoveryNotice.attributes('role')).toBe('status')
      expect(recoveryNotice.text()).toContain('Deleted layout “Saved layout”.')

      await recoveryNotice.get('button[role="menuitem"]').trigger('click')
      expect(harness.workspace.restoreDeletedTab).toHaveBeenCalledWith(recovery)
      expect(harness.workspace.saveSnapshot).toHaveBeenCalledTimes(1)
      await vi.waitFor(() => expect(wrapper.find('.workstation__layout-recovery').exists()).toBe(false))
    } finally {
      confirm.mockRestore()
      wrapper.unmount()
    }
  })

  it('keeps layout recovery visible through save failure and until a retry is acknowledged', async () => {
    routeState.path = '/'
    routeState.params = {}
    const baseTab = harness.workspace.workspace.tabs[0]
    const deletedTab = { ...baseTab, id: 2, stable_key: 'layout-recovery', name: 'Saved layout', position: 1 }
    harness.workspace.workspace.tabs = [baseTab, deletedTab]
    const recovery = { workspace_id: 1, tab: deletedTab, position: 1 }
    harness.workspace.captureTabRecovery.mockReturnValue(recovery)
    harness.workspace.deleteTab.mockImplementation((stableKey: string) => {
      harness.workspace.workspace.tabs = harness.workspace.workspace.tabs.filter(tab => tab.stable_key !== stableKey)
      return true
    })
    harness.workspace.restoreDeletedTab.mockReturnValue(true)
    let finishSave!: (saved: boolean) => void
    const pendingSave = new Promise<boolean>(resolve => { finishSave = resolve })
    harness.workspace.saveSnapshot.mockReturnValueOnce(pendingSave).mockResolvedValueOnce(true)
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })

    try {
      await wrapper.get('button[title="Manage workspace layouts"]').trigger('click')
      await wrapper.get('button[aria-label="Delete layout Saved layout"]').trigger('click')
      await wrapper.get('.workstation__layout-recovery button[role="menuitem"]').trigger('click')
      await vi.waitFor(() => expect(wrapper.get('.workstation__layout-recovery').text()).toContain('Restoring layout'))
      expect(wrapper.get('.workstation__layout-recovery button[role="menuitem"]').attributes('disabled')).toBeDefined()
      expect(wrapper.find('.workstation__layout-recovery').exists()).toBe(true)
      finishSave(false)
      await vi.waitFor(() => expect(wrapper.get('.workstation__layout-recovery').text()).toContain('was not saved'))
      expect(wrapper.get('.workstation__layout-recovery button[role="menuitem"]').text()).toBe('Retry save')
      expect(harness.workspace.restoreDeletedTab).toHaveBeenCalledTimes(1)

      await wrapper.get('.workstation__layout-recovery button[role="menuitem"]').trigger('click')
      await vi.waitFor(() => expect(wrapper.find('.workstation__layout-recovery').exists()).toBe(false))
      expect(harness.workspace.restoreDeletedTab).toHaveBeenCalledTimes(1)
      expect(harness.workspace.saveSnapshot).toHaveBeenCalledTimes(2)
    } finally {
      confirm.mockRestore()
      wrapper.unmount()
    }
  })

  it('announces workspace save failure and offers a keyboard-focusable retry', async () => {
    routeState.path = '/'
    routeState.params = {}
    harness.workspace.snapshotSaveStatus = 'error'
    harness.workspace.snapshotSaveError = 'Workspace changed elsewhere.'
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })

    const status = wrapper.get('[aria-label="Workspace save status"]')
    expect(status.attributes('role')).toBe('status')
    expect(status.text()).toBe('Workspace save failed')
    const retry = wrapper.get('button.workstation__snapshot-save-retry')
    expect(retry.text()).toBe('Retry save')
    expect(retry.element.tagName).toBe('BUTTON')
    await retry.trigger('click')
    expect(harness.workspace.saveSnapshot).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('announces an unavailable pop-out tool as an assertive recovery alert', async () => {
    routeState.params = { windowKey: 'missing-tool' }
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })

    const recovery = wrapper.get('.workstation__missing-tool')
    expect(recovery.text()).toBe('The requested tool is unavailable. It remains in the source workspace.')
    expect(recovery.attributes('role')).toBe('alert')
    expect(recovery.attributes('aria-live')).toBe('assertive')
    wrapper.unmount()
  })

  it('hydrates missing shared market analysis when a pop-out opens after the leader refresh', async () => {
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })

    await vi.waitFor(() => expect(harness.workspace.refreshMarketAnalysis).toHaveBeenCalledTimes(1))
    wrapper.unmount()
  })

  it('does not refetch shared market analysis when a pop-out already has the canonical inputs', async () => {
    harness.workspace.marketGroups = {
      'us-benchmarks': { members: [] },
      'sp500-sectors': { members: [] },
    }
    harness.workspace.groupSnapshots = {
      'us-benchmarks': { rows: [] },
      'sp500-sectors': { rows: [] },
    }
    harness.workspace.breadth = { 'sp500-sectors': {} }
    harness.workspace.breadthHistory = { 'sp500-sectors': {} }

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })

    await new Promise(resolve => setTimeout(resolve, 0))
    expect(harness.workspace.refreshMarketAnalysis).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('does not hydrate market analysis for a chart pop-out', async () => {
    routeState.path = '/popout/chart-main'
    routeState.params = { windowKey: 'chart-main' }

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })

    await new Promise(resolve => setTimeout(resolve, 0))
    expect(harness.workspace.refreshMarketAnalysis).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('resolves a canonical identity when a proxy action does not include a row id', async () => {
    routeState.path = '/popout/benchmark-list'
    routeState.params = { windowKey: 'benchmark-list' }
    const wrapper = mount(WorkstationView, {
      global: {
        stubs: {
          WorkstationToolContent: ToolStub,
          WorkspaceLayoutHost: true,
        },
      },
    })

    await wrapper.find('.proxy-without-id').trigger('click')

    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(
      expect.objectContaining({ symbol: 'XLK', instrumentId: 77, group: 'blue' }),
    ))
    wrapper.unmount()
  })

  it('provides keyboard-navigable canonical symbol search in the workstation shell', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockResolvedValue([
      { symbol: 'XLK', name: 'Technology Select Sector SPDR Fund', exchange: 'ARCX', type: 'ETF', instrument_id: 88 },
      { symbol: 'XLE', name: 'Energy Select Sector SPDR Fund', exchange: 'ARCX', type: 'ETF', instrument_id: 89 },
    ])
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
    const input = wrapper.get('input[aria-label="Active symbol"]')
    await input.setValue('xl')
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/instruments/search', { q: 'xl', canonical_only: true }, { priority: 'high' }))
    await vi.waitFor(() => expect(wrapper.find('[role="listbox"]').exists()).toBe(true))
    const listbox = wrapper.get('[role="listbox"]')
    const resultsId = listbox.attributes('id')
    const searchStateId = wrapper.get('.workstation__symbol-search-state').attributes('id')
    expect(resultsId).toMatch(/-symbol-results$/)
    expect(resultsId).not.toBe('workstation-symbol-results')
    expect(searchStateId).toMatch(/-symbol-search-state$/)
    expect(searchStateId).not.toBe('workstation-symbol-search-state')
    expect(input.attributes('aria-controls')).toBe(resultsId)
    expect(input.attributes('aria-describedby')).toBe(searchStateId)
    expect(wrapper.findAll('[role="option"]')[0].text()).toContain('XLK')
    const firstOptionId = wrapper.findAll('[role="option"]')[0].attributes('id')
    expect(firstOptionId).toMatch(/-symbol-option-0$/)
    expect(input.attributes('aria-activedescendant')).toBe(firstOptionId)
    await input.trigger('keydown', { key: 'ArrowDown' })
    const secondOptionId = wrapper.findAll('[role="option"]')[1].attributes('id')
    expect(input.attributes('aria-activedescendant')).toBe(secondOptionId)
    await input.trigger('keydown', { key: 'Enter' })
    expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'XLE', instrumentId: 89, group: 'blue' }))
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('submits the typed ticker instead of its first partial local result on Enter', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockImplementation(async (path: string, params?: Record<string, unknown>) => {
      if (path === '/instruments/search' && params?.q === 'F') {
        return [{ symbol: 'FTI', name: 'TechnipFMC plc', exchange: 'NYSE', type: 'Common Stock', instrument_id: 17 }]
      }
      if (path === '/instruments/F') return { id: 18, symbol: 'F', name: 'Ford Motor Company' }
      return []
    })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
    harness.workspace.publishSymbol.mockClear()

    const input = wrapper.get('input[aria-label="Active symbol"]')
    await input.setValue('F')
    await vi.waitFor(() => expect(wrapper.text()).toContain('TechnipFMC plc'))
    await input.trigger('keydown', { key: 'Enter' })

    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'F', instrumentId: 77 })))
    expect(harness.workspace.publishSymbol).not.toHaveBeenCalledWith(expect.objectContaining({ symbol: 'FTI' }))
    wrapper.unmount()
  })

  it('resolves the exact discovered ticker on Enter after the matching lookup completes', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockImplementation(async (path: string) => {
      if (path.startsWith('/coverage/instruments/')) return { status: 'ready', bar_count: 124, missing_slices: [] }
      return []
    })
    apiPost
      .mockResolvedValueOnce({
        request_id: 'f-discovery', status: 'complete',
        candidates: [{ symbol: 'F', name: 'Ford Motor Company', exchange: 'XNYS', type: 'Common Stock', provider: 'fixture', instrument_id: null, identity_status: 'provider_candidate' }],
        source_outcomes: [],
      })
      .mockResolvedValueOnce({
        request_id: 'f-resolution', status: 'resolved',
        instrument: { instrument_id: 83, symbol: 'F', identity_status: 'verified', instrument_type: 'Common Stock' },
        source_outcomes: [],
      })

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
    harness.workspace.publishSymbol.mockClear()
    const input = wrapper.get('input[aria-label="Active symbol"]')
    await input.setValue('F')
    await input.trigger('keydown', { key: 'Enter' })

    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'F', instrumentId: 83 })))
    expect(apiPost).toHaveBeenNthCalledWith(1, '/instruments/discover', expect.objectContaining({ query: 'F' }), expect.objectContaining({ priority: 'high', signal: expect.any(AbortSignal) }))
    expect(apiPost).toHaveBeenNthCalledWith(2, '/instruments/acquire', expect.objectContaining({
      symbol: 'F', provider_candidate: { provider: 'fixture', symbol: 'F', exchange: 'XNYS' },
    }), expect.objectContaining({ priority: 'high', signal: expect.any(AbortSignal) }))
    expect(apiPost.mock.calls.filter(([path]) => path === '/instruments/acquire')).toHaveLength(1)
    expect(harness.workspace.publishSymbol).not.toHaveBeenCalledWith(expect.objectContaining({ symbol: 'FTI' }))
    wrapper.unmount()
  })

  it('keeps a deliberate Enter intent through a known temporary discovery hold', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockImplementation(async (path: string) => {
      if (path.startsWith('/coverage/instruments/')) return { status: 'ready', bar_count: 20, missing_slices: [] }
      return []
    })
    let discoveryAttempts = 0
    apiPost.mockImplementation(async (path: string, body: Record<string, any>) => {
      if (path === '/instruments/discover') {
        discoveryAttempts += 1
        if (discoveryAttempts === 1) return { request_id: 'f-held-discovery', status: 'held', candidates: [], retry_at: new Date(Date.now() + 80).toISOString(), source_outcomes: [] }
        return {
          request_id: 'f-discovery-ready', status: 'complete',
          candidates: [{ symbol: 'F', name: 'Ford Motor Company', exchange: 'XNYS', type: 'Common Stock', provider: 'fixture', instrument_id: null, identity_status: 'provider_candidate' }],
          source_outcomes: [],
        }
      }
      if (path === '/instruments/acquire') return {
        request_id: 'f-identity-ready', status: 'resolved',
        instrument: { instrument_id: 83, symbol: 'F', identity_status: 'verified', instrument_type: 'Common Stock' }, source_outcomes: [],
      }
      if (path === '/etf-holdings/F/acquire') return { request_id: body.request_id, instrument_id: 83, symbol: 'F', outcome: 'unavailable', refresh: true, refresh_attempted: true, refresh_succeeded: false, profile: null, provider_request_log_ids: [], message: 'No fund holdings.' }
      throw new Error(`Unexpected request: ${path}`)
    })

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
      harness.workspace.publishSymbol.mockClear()
      const input = wrapper.get('input[aria-label="Active symbol"]')
      await input.setValue('F')
      await vi.waitFor(() => expect(apiPost).toHaveBeenCalledWith('/instruments/discover', expect.objectContaining({ query: 'F' }), expect.objectContaining({ priority: 'high', signal: expect.any(AbortSignal) })))
      await vi.waitFor(() => expect(wrapper.text()).toContain('Ticker lookup is temporarily waiting to retry after'))
      expect(harness.workspace.publishSymbol).not.toHaveBeenCalled()
      await input.trigger('keydown', { key: 'Enter' })

      await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'F', instrumentId: 83 })))
      expect(apiPost.mock.calls.filter(([path]) => path === '/instruments/discover')).toHaveLength(2)
      expect(apiPost.mock.calls.filter(([path]) => path === '/instruments/acquire')).toHaveLength(1)
    } finally {
      wrapper.unmount()
    }
  })

  it('keeps an explicit candidate click through a known temporary identity hold', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockImplementation(async (path: string) => {
      if (path.startsWith('/coverage/instruments/')) return { status: 'ready', bar_count: 20, missing_slices: [] }
      return []
    })
    let resolutionAttempts = 0
    apiPost.mockImplementation(async (path: string, body: Record<string, any>) => {
      if (path === '/instruments/discover') return {
        request_id: 'bw-discovery', status: 'complete',
        candidates: [{ symbol: 'BWET', name: 'Controlled ETV', exchange: 'XNYS', type: 'Exchange Traded Vehicle', provider: 'fixture', instrument_id: null, identity_status: 'provider_candidate' }],
        source_outcomes: [],
      }
      if (path === '/instruments/acquire') {
        resolutionAttempts += 1
        if (resolutionAttempts === 1) return { request_id: 'bwet-held', status: 'held', instrument: null, retry_at: new Date(Date.now() + 80).toISOString(), source_outcomes: [] }
        return {
        request_id: 'bwet-resolved', status: 'resolved',
        instrument: { instrument_id: 690, symbol: 'BWET', identity_status: 'verified', instrument_type: 'Exchange Traded Vehicle' }, source_outcomes: [],
        }
      }
      if (path === '/etf-holdings/BWET/acquire') return { request_id: body.request_id, instrument_id: 690, symbol: 'BWET', outcome: 'unavailable', refresh: true, refresh_attempted: true, refresh_succeeded: false, profile: null, provider_request_log_ids: [], message: 'No current holdings.' }
      throw new Error(`Unexpected request: ${path}`)
    })

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
      harness.workspace.publishSymbol.mockClear()
      await wrapper.get('input[aria-label="Active symbol"]').setValue('BWET')
      const option = await vi.waitFor(() => {
        const candidate = wrapper.findAll('.workstation__source-option').find(button => button.text().includes('Use BWET'))
        expect(candidate).toBeTruthy()
        return candidate
      })
      await option!.trigger('click')
      await vi.waitFor(() => expect(wrapper.text()).toContain('Ticker confirmation is temporarily waiting to retry after'))
      expect(harness.workspace.publishSymbol).not.toHaveBeenCalled()

      await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'BWET', instrumentId: 690 })))
      expect(resolutionAttempts).toBe(2)
      expect(apiPost.mock.calls.filter(([path]) => path === '/instruments/discover')).toHaveLength(1)
    } finally {
      wrapper.unmount()
    }
  })

  it('keeps a verified symbol selected while the initial workspace read completes later', async () => {
    routeState.path = '/chart'
    routeState.params = {}
    const originalWorkspace = harness.workspace
    harness.workspace = reactive(originalWorkspace)
    harness.workspace.linkedSymbol = 'SPY'
    harness.workspace.workspace.settings.linked_symbols = { blue: { symbol: 'SPY', instrument_id: 2 } }
    const isolatedTool = {
      instance_key: 'isolated-study', tool_type: 'study_lab', title: 'Isolated Study',
      link_group: 'grey', configuration: { symbol: 'XLB', instrument_id: 43 },
    }
    harness.workspace.workspace.tabs[0]!.windows.push(isolatedTool)
    harness.workspace.publishSymbol.mockImplementation((event: any) => {
      harness.workspace.linkedSymbol = event.symbol
    })
    let finishWorkspaceLoad!: () => void
    harness.workspace.loadDefault.mockReturnValueOnce(new Promise<void>(resolve => {
      finishWorkspaceLoad = () => {
        harness.workspace.linkedSymbol = 'SPY'
        resolve()
      }
    }))
    apiGet.mockImplementation(async (path: string, params?: Record<string, unknown>) => {
      if (path === '/instruments/search') return []
      return []
    })
    apiPost.mockImplementation(async (path: string, body: Record<string, any>) => {
      if (path === '/instruments/discover') return {
        request_id: 'tcnew-discovery', status: 'complete',
        candidates: [{ symbol: 'TCNEW', name: 'Test Instrument', exchange: 'TEST', type: 'Stock', provider: 'fixture', instrument_id: null, identity_status: 'provider_candidate' }],
        source_outcomes: [],
      }
      if (path === '/instruments/acquire') return {
        request_id: body.request_id, status: 'resolved',
        instrument: { instrument_id: 990011, symbol: 'TCNEW', identity_status: 'resolved', instrument_type: 'Common Stock' },
        source_outcomes: [],
      }
      throw new Error(`Unexpected request: ${path}`)
    })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })

    try {
      await vi.waitFor(() => expect(harness.workspace.loadDefault).toHaveBeenCalled())
      const input = wrapper.get('input[aria-label="Active symbol"]')
      await input.setValue('TCNEW')
      const candidate = await vi.waitFor(() => {
        const button = wrapper.findAll('.workstation__source-option').find(item => item.text().includes('Use TCNEW'))
        expect(button).toBeTruthy()
        return button!
      })
      await candidate.trigger('click')
      await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({
        symbol: 'TCNEW', instrumentId: 990011, group: 'blue',
      })))
      expect(wrapper.get('input[aria-label="Active symbol"]').element.value).toBe('TCNEW')

      finishWorkspaceLoad()
      await vi.waitFor(() => {
        expect(harness.workspace.linkedSymbol).toBe('TCNEW')
        expect(wrapper.get('input[aria-label="Active symbol"]').element.value).toBe('TCNEW')
      })
      expect(routerReplace).toHaveBeenLastCalledWith(expect.objectContaining({ path: '/chart/TCNEW' }))
      expect(harness.workspace.publishSymbol).toHaveBeenLastCalledWith(expect.objectContaining({
        symbol: 'TCNEW', instrumentId: 990011, group: 'blue',
      }))
      expect(isolatedTool.configuration).toEqual({ symbol: 'XLB', instrument_id: 43 })
      expect(dataPreparationPost).toHaveBeenCalledWith(expect.objectContaining({
        target: { kind: 'instrument', instrument_id: 990011 },
        datasets: ['identity', 'profile', 'history'],
        timeframe: 'D1',
      }), expect.anything())
    } finally {
      finishWorkspaceLoad()
      wrapper.unmount()
      harness.workspace = originalWorkspace
      harness.workspace.workspace.tabs[0]!.windows = harness.workspace.workspace.tabs[0]!.windows.filter(
        tool => tool.instance_key !== 'isolated-study',
      )
    }
  })

  it('cancels a held dashboard discovery when the user edits to a different query', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockResolvedValue([])
    apiPost.mockImplementation(async (_path: string, body: Record<string, unknown>) => {
      if (body.query === 'OLD') return { request_id: 'old-held', status: 'held', candidates: [], retry_at: new Date(Date.now() + 180).toISOString(), source_outcomes: [] }
      if (body.query === 'NEW') return { request_id: 'new-no-match', status: 'no_match', candidates: [], source_outcomes: [] }
      throw new Error(`Unexpected discovery query: ${String(body.query)}`)
    })

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      const input = wrapper.get('input[aria-label="Active symbol"]')
      await input.setValue('OLD')
      await vi.waitFor(() => expect(wrapper.text()).toContain('Ticker lookup is temporarily waiting to retry after'))
      await input.setValue('NEW')
      await vi.waitFor(() => expect(apiPost).toHaveBeenCalledWith('/instruments/discover', expect.objectContaining({ query: 'NEW' }), expect.objectContaining({ priority: 'high', signal: expect.any(AbortSignal) })))
      await new Promise(resolve => setTimeout(resolve, 140))
      expect(apiPost.mock.calls.filter(([path, body]) => path === '/instruments/discover' && body.query === 'OLD')).toHaveLength(1)
      expect(apiPost).not.toHaveBeenCalledWith('/instruments/acquire', expect.objectContaining({ symbol: 'OLD' }))
      expect(wrapper.text()).not.toContain('Use OLD')
    } finally {
      wrapper.unmount()
    }
  })

  it('keeps a discovery hard hold distinct from a terminal no-match and never retries it', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockResolvedValue([])
    apiPost.mockResolvedValue({
      request_id: 'held-discovery', status: 'held', candidates: [],
      source_outcomes: [{ provider: 'fixture', capability: 'search', operation: 'discover', status: 'held', reason_code: 'controlled_internal_reason' }],
    })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await wrapper.get('input[aria-label="Active symbol"]').setValue('HOLD')
      await vi.waitFor(() => expect(wrapper.text()).toContain('Ticker lookup is unavailable. You can try again manually.'))
      expect(wrapper.get('[role="listbox"]').text()).not.toContain('No matching ticker is available')
      expect(wrapper.text()).not.toContain('controlled_internal_reason')
      await new Promise(resolve => setTimeout(resolve, 100))
      expect(apiPost.mock.calls.filter(([path]) => path === '/instruments/discover')).toHaveLength(1)
      expect(apiPost).not.toHaveBeenCalledWith('/instruments/acquire', expect.anything())
    } finally {
      wrapper.unmount()
    }
  })

  it('resolves the exact discovered ticker from Go while its matching lookup is pending', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockImplementation(async (path: string) => {
      if (path.startsWith('/coverage/instruments/')) return { status: 'ready', bar_count: 124, missing_slices: [] }
      return []
    })
    apiPost
      .mockResolvedValueOnce({
        status: 'complete', candidates: [{ symbol: 'F', name: 'Ford Motor Company', exchange: 'XNYS', type: 'Common Stock', provider: 'fixture', instrument_id: null, identity_status: 'provider_candidate' }], source_outcomes: [],
      })
      .mockResolvedValueOnce({ status: 'resolved', instrument: { instrument_id: 83, symbol: 'F', identity_status: 'verified', instrument_type: 'Common Stock' }, source_outcomes: [] })

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
    harness.workspace.publishSymbol.mockClear()
    await wrapper.get('input[aria-label="Active symbol"]').setValue('F')
    await wrapper.findAll('button').find(button => button.text() === 'Go')!.trigger('click')

    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'F', instrumentId: 83 })))
    expect(apiPost).toHaveBeenNthCalledWith(1, '/instruments/discover', expect.objectContaining({ query: 'F' }), expect.objectContaining({ priority: 'high', signal: expect.any(AbortSignal) }))
    expect(apiPost).toHaveBeenNthCalledWith(2, '/instruments/acquire', expect.objectContaining({
      symbol: 'F', provider_candidate: { provider: 'fixture', symbol: 'F', exchange: 'XNYS' },
    }), expect.objectContaining({ priority: 'high', signal: expect.any(AbortSignal) }))
    wrapper.unmount()
  })

  it('submits a pending exact remote candidate from Go without selecting a stale query result', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockResolvedValue([])
    let finishFordDiscovery!: (value: unknown) => void
    const fordDiscovery = new Promise(resolve => { finishFordDiscovery = resolve })
    apiPost
      .mockReturnValueOnce(fordDiscovery as ReturnType<typeof apiPost>)
      .mockResolvedValueOnce({ status: 'no_match', candidates: [], source_outcomes: [] })

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
    harness.workspace.publishSymbol.mockClear()
    const input = wrapper.get('input[aria-label="Active symbol"]')
    await input.setValue('F')
    await vi.waitFor(() => expect(apiPost).toHaveBeenCalledTimes(1))
    await wrapper.findAll('button').find(button => button.text() === 'Go')!.trigger('click')

    await input.setValue('BWET')
    await vi.waitFor(() => expect(apiPost).toHaveBeenCalledTimes(2))
    finishFordDiscovery({
      request_id: 'stale-f', status: 'complete',
      candidates: [{ symbol: 'F', name: 'Ford Motor Company', exchange: 'XNYS', type: 'Common Stock', provider: 'fixture', instrument_id: null, identity_status: 'provider_candidate' }],
      source_outcomes: [],
    })
    await flushPromises()
    await vi.waitFor(() => expect(wrapper.text()).toContain('No matching ticker is available for “BWET”'))
    expect(apiPost.mock.calls.filter(([path, body]) => path === '/instruments/acquire' && body?.provider_candidate)).toHaveLength(0)
    expect(harness.workspace.publishSymbol).not.toHaveBeenCalledWith(expect.objectContaining({ symbol: 'F' }))
    expect(harness.workspace.publishSymbol).not.toHaveBeenCalledWith(expect.objectContaining({ symbol: 'BWET' }))
    wrapper.unmount()
  })

  it('clears only its superseded symbol error after a later confirmed candidate selection', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockImplementation(async (path: string) => {
      if (path.startsWith('/coverage/instruments/')) return { status: 'ready', bar_count: 124, missing_slices: [] }
      return []
    })
    apiPost
      .mockResolvedValueOnce({ status: 'no_match', candidates: [], source_outcomes: [] })
      .mockResolvedValueOnce({
        status: 'complete', candidates: [{ symbol: 'F', name: 'Ford Motor Company', exchange: 'XNYS', type: 'Common Stock', provider: 'fixture', instrument_id: null, identity_status: 'provider_candidate' }], source_outcomes: [],
      })
      .mockResolvedValueOnce({ status: 'resolved', instrument: { instrument_id: 83, symbol: 'F', identity_status: 'verified' }, source_outcomes: [] })

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
    vi.mocked(resolveKnownInstrument).mockRejectedValueOnce(new Error('Workstation symbol "BAD" is not available.'))
    const input = wrapper.get('input[aria-label="Active symbol"]')
    await input.setValue('BAD')
    await wrapper.findAll('button').find(button => button.text() === 'Go')!.trigger('click')
    await vi.waitFor(() => expect(harness.workspace.error).toContain('Workstation symbol "BAD" is not available.'))

    await input.setValue('F')
    await vi.waitFor(() => expect(wrapper.find('.workstation__source-option').exists()).toBe(true))
    await wrapper.get('.workstation__source-option').trigger('click')
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'F', instrumentId: 83 })))
    expect(harness.workspace.error).toBeNull()
    expect(wrapper.get('.workstation__footer').text()).not.toContain('Workstation symbol "BAD" is not available.')
    wrapper.unmount()
  })

  it('does not publish a late canonical lookup error over a newer confirmed selection', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockImplementation(async (path: string) => {
      if (path.startsWith('/coverage/instruments/')) return { status: 'ready', bar_count: 124, missing_slices: [] }
      return []
    })
    apiPost
      .mockResolvedValueOnce({ status: 'no_match', candidates: [], source_outcomes: [] })
      .mockResolvedValueOnce({
        status: 'complete', candidates: [{ symbol: 'GOOD', name: 'Confirmed Instrument', exchange: 'XNYS', type: 'Common Stock', provider: 'fixture', instrument_id: null, identity_status: 'provider_candidate' }], source_outcomes: [],
      })
      .mockResolvedValueOnce({ status: 'resolved', instrument: { instrument_id: 91, symbol: 'GOOD', identity_status: 'verified', instrument_type: 'Common Stock' }, source_outcomes: [] })
    let rejectBad!: (reason: Error) => void
    const badResolution = new Promise<never>((_resolve, reject) => { rejectBad = reject })

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
    harness.workspace.publishSymbol.mockClear()
    vi.mocked(resolveKnownInstrument).mockImplementation(async (symbol: string) => {
      if (symbol.toUpperCase() === 'BAD') return badResolution
      return { symbol, id: 77 }
    })
    const input = wrapper.get('input[aria-label="Active symbol"]')
    await input.setValue('BAD')
    await wrapper.findAll('button').find(button => button.text() === 'Go')!.trigger('click')
    await vi.waitFor(() => expect(resolveKnownInstrument).toHaveBeenCalledWith('BAD', 'Workstation symbol', expect.objectContaining({ canonicalOnly: true, priority: 'high', signal: expect.any(AbortSignal) })))

    await input.setValue('GOOD')
    await vi.waitFor(() => expect(wrapper.find('.workstation__source-option').exists()).toBe(true))
    await wrapper.get('.workstation__source-option').trigger('click')
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'GOOD', instrumentId: 91 })))
    rejectBad(new Error('Workstation symbol "BAD" is not available.'))
    await flushPromises()

    expect(harness.workspace.error).toBeNull()
    expect(harness.workspace.publishSymbol).not.toHaveBeenCalledWith(expect.objectContaining({ symbol: 'BAD' }))
    wrapper.unmount()
  })

  it('uses an exact local ticker match when it is not the default first result', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockImplementation(async (path: string, params?: Record<string, unknown>) => {
      if (path === '/instruments/search' && params?.q === 'XLE') {
        return [
          { symbol: 'XLK', name: 'Technology Select Sector SPDR Fund', exchange: 'ARCX', type: 'ETF', instrument_id: 88 },
          { symbol: 'XLE', name: 'Energy Select Sector SPDR Fund', exchange: 'ARCX', type: 'ETF', instrument_id: 89 },
        ]
      }
      if (path === '/instruments/XLE') return { id: 89, symbol: 'XLE', name: 'Energy Select Sector SPDR Fund' }
      return []
    })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
    harness.workspace.publishSymbol.mockClear()

    const input = wrapper.get('input[aria-label="Active symbol"]')
    await input.setValue('XLE')
    await vi.waitFor(() => expect(wrapper.text()).toContain('Technology Select Sector SPDR Fund'))
    await input.trigger('keydown', { key: 'Enter' })

    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'XLE', instrumentId: 89 })))
    expect(harness.workspace.publishSymbol).not.toHaveBeenCalledWith(expect.objectContaining({ symbol: 'XLK' }))
    wrapper.unmount()
  })

  it('uses Backspace for viewed-symbol history when the workstation owns focus', async () => {
    routeState.path = '/'
    routeState.params = {}
    harness.recent.previous.mockReturnValueOnce('XLK').mockReturnValueOnce(null)
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const event = new KeyboardEvent('keydown', { key: 'Backspace', bubbles: true, cancelable: true })
    wrapper.find('.workstation').element.dispatchEvent(event)
    await flushPromises()

    expect(event.defaultPrevented).toBe(true)
    expect(harness.recent.previous).toHaveBeenCalledOnce()
    expect(harness.recent.add).toHaveBeenCalledWith('XLK', undefined, false)
    expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'XLK', group: 'blue' }))
    expect(dataPreparationPost).toHaveBeenCalledWith(expect.objectContaining({
      target: { kind: 'instrument', instrument_id: 77 }, datasets: ['identity', 'profile', 'history'], timeframe: 'D1', adjusted: true,
    }), expect.objectContaining({ signal: expect.any(AbortSignal) }))
    const selectedRequest = dataPreparationPost.mock.calls.find(([request]) =>
      request.target.kind === 'instrument' && request.target.instrument_id === 77,
    )?.[0]
    expect(selectedRequest).not.toHaveProperty('start_at')
    expect(selectedRequest).not.toHaveProperty('end_at')
    expect(apiPost).not.toHaveBeenCalledWith('/instruments/acquire', expect.objectContaining({ symbol: 'XLK' }))
    const oldestEntryEvent = new KeyboardEvent('keydown', { key: 'Backspace', bubbles: true, cancelable: true })
    wrapper.find('.workstation').element.dispatchEvent(oldestEntryEvent)
    expect(oldestEntryEvent.defaultPrevented).toBe(true)
    expect(harness.recent.previous).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('prepares the visible default chart and also prepares deliberate Space traversal', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockResolvedValue([])
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))

    await vi.waitFor(() => expect(dataPreparationPost).toHaveBeenCalledTimes(1))
    expect(dataPreparationPost.mock.calls[0]?.[0]).toMatchObject({
      target: { kind: 'instrument', symbol: 'SPY' }, datasets: ['identity', 'profile', 'history'], timeframe: 'D1', adjusted: true,
    })
    expect(dataPreparationPost.mock.calls[0]?.[0]).not.toHaveProperty('start_at')
    expect(dataPreparationPost.mock.calls[0]?.[0]).not.toHaveProperty('end_at')
    const workstation = wrapper.find('.workstation').element
    const firstRequestCount = dataPreparationPost.mock.calls.length
    workstation.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true }))
    await vi.waitFor(() => expect(dataPreparationPost.mock.calls.length).toBeGreaterThan(firstRequestCount))
    const traversedRequest = dataPreparationPost.mock.calls[firstRequestCount]?.[0]
    expect(traversedRequest).toMatchObject({ datasets: ['identity', 'profile', 'history'], timeframe: 'D1', adjusted: true })
    expect(traversedRequest).not.toHaveProperty('start_at')
    expect(traversedRequest).not.toHaveProperty('end_at')
    const secondRequestCount = dataPreparationPost.mock.calls.length
    workstation.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', ctrlKey: true, bubbles: true, cancelable: true }))
    await vi.waitFor(() => expect(dataPreparationPost.mock.calls.length).toBeGreaterThan(secondRequestCount))
    expect(dataPreparationPost.mock.calls.at(-1)?.[0]).toMatchObject({ datasets: ['identity', 'profile', 'history'], timeframe: 'D1' })
    expect(dataPreparationPost.mock.calls.at(-1)?.[0]).not.toHaveProperty('start_at')
    expect(dataPreparationPost.mock.calls.at(-1)?.[0]).not.toHaveProperty('end_at')
    wrapper.unmount()
  })

  it('uses Shift+L to maximize only the selected tool and leaves editor shortcuts alone', async () => {
    routeState.path = '/'
    routeState.params = {}
    const wrapper = mount(WorkstationView, {
      attachTo: document.body,
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const workstation = wrapper.find('.workstation').element
    const selectedTool = document.createElement('section')
    selectedTool.className = 'tool-window'
    selectedTool.dataset.windowKey = 'benchmark-list'
    const maximize = document.createElement('button')
    maximize.setAttribute('aria-label', 'Maximize tool')
    const maximizeClick = vi.fn()
    maximize.addEventListener('click', maximizeClick)
    selectedTool.append(maximize)
    workstation.appendChild(selectedTool)
    expect(workstation.isConnected).toBe(true)
    expect(document.querySelector('.tool-window[data-window-key="benchmark-list"]')).not.toBeNull()

    const event = new KeyboardEvent('keydown', { key: 'L', shiftKey: true, bubbles: true, cancelable: true })
    workstation.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    expect(maximizeClick).toHaveBeenCalledOnce()

    const editor = document.createElement('input')
    workstation.appendChild(editor)
    harness.workspace.isEditorTarget.mockImplementation(target => target === editor)
    const editorEvent = new KeyboardEvent('keydown', { key: 'L', shiftKey: true, bubbles: true, cancelable: true })
    editor.dispatchEvent(editorEvent)
    expect(editorEvent.defaultPrevented).toBe(false)
    expect(maximizeClick).toHaveBeenCalledOnce()
    harness.workspace.isEditorTarget.mockImplementation(() => false)
    wrapper.unmount()
  })

  it('uses Shift+N to open active-symbol notes from the shell and yields to interactive controls', async () => {
    routeState.path = '/'
    routeState.params = {}
    harness.workspace.openTool.mockReturnValue({ instance_key: 'notes-new', tool_type: 'notes' })
    const wrapper = mount(WorkstationView, {
      attachTo: document.body,
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const workstation = wrapper.find('.workstation').element
    await wrapper.find('.workstation').trigger('keydown', { key: 'N', shiftKey: true })
    expect(harness.workspace.openTool).toHaveBeenCalledWith(
      expect.objectContaining({ tool_type: 'notes', configuration: { scope: 'active-instrument' } }),
      {},
    )

    const editor = document.createElement('input')
    workstation.appendChild(editor)
    harness.workspace.isEditorTarget.mockImplementation(target => target === editor)
    await wrapper.find('input[aria-label="Active symbol"]').trigger('keydown', { key: 'n', shiftKey: true })

    const button = document.createElement('button')
    workstation.appendChild(button)
    await wrapper.find('button[title="Keyboard shortcuts"]').trigger('keydown', { key: 'n', shiftKey: true })
    expect(harness.workspace.openTool).toHaveBeenCalledTimes(1)
    harness.workspace.isEditorTarget.mockImplementation(() => false)
    wrapper.unmount()
  })

  it('uses Shift+D to toggle Trend Line only when a chart is active', async () => {
    routeState.path = '/'
    routeState.params = {}
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const workstation = wrapper.find('.workstation').element

    const watchlistEvent = new KeyboardEvent('keydown', { key: 'D', shiftKey: true, bubbles: true, cancelable: true })
    workstation.dispatchEvent(watchlistEvent)
    expect(watchlistEvent.defaultPrevented).toBe(false)
    expect(harness.drawings.setActiveTool).not.toHaveBeenCalled()

    harness.workspace.activeTab.active_window_key = 'chart-main'
    const chartEvent = new KeyboardEvent('keydown', { key: 'D', shiftKey: true, bubbles: true, cancelable: true })
    workstation.dispatchEvent(chartEvent)
    expect(chartEvent.defaultPrevented).toBe(true)
    expect(harness.drawings.setActiveTool).toHaveBeenLastCalledWith('trendline')

    harness.drawings.activeToolType = 'trendline'
    const toggleOffEvent = new KeyboardEvent('keydown', { key: 'D', shiftKey: true, bubbles: true, cancelable: true })
    workstation.dispatchEvent(toggleOffEvent)
    expect(harness.drawings.setActiveTool).toHaveBeenLastCalledWith(null)
    harness.workspace.activeTab.active_window_key = 'benchmark-list'
    wrapper.unmount()
  })

  it('maps supported Ctrl+number shortcuts to direct active-chart timeframes', async () => {
    routeState.path = '/'
    routeState.params = {}
    harness.workspace.activeTab.active_window_key = 'chart-main'
    harness.workspace.updateToolTimeframe.mockReturnValue(true)
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const workstation = wrapper.find('.workstation').element

    for (const [key, timeframe] of [['1', 'M1'], ['3', 'M5'], ['4', 'M15'], ['5', 'M30'], ['6', 'H1']] as const) {
      const event = new KeyboardEvent('keydown', { key, ctrlKey: true, bubbles: true, cancelable: true })
      workstation.dispatchEvent(event)
      expect(event.defaultPrevented).toBe(true)
      expect(harness.workspace.updateToolTimeframe).toHaveBeenLastCalledWith('chart-main', timeframe)
    }

    harness.workspace.updateToolTimeframe.mockClear()
    const unsupportedInterval = new KeyboardEvent('keydown', { key: '2', ctrlKey: true, bubbles: true, cancelable: true })
    workstation.dispatchEvent(unsupportedInterval)
    expect(unsupportedInterval.defaultPrevented).toBe(false)
    expect(harness.workspace.updateToolTimeframe).not.toHaveBeenCalled()

    harness.workspace.activeTab.active_window_key = 'benchmark-list'
    const nonChart = new KeyboardEvent('keydown', { key: '1', ctrlKey: true, bubbles: true, cancelable: true })
    workstation.dispatchEvent(nonChart)
    expect(nonChart.defaultPrevented).toBe(false)
    expect(harness.workspace.updateToolTimeframe).not.toHaveBeenCalled()
    harness.workspace.activeTab.active_window_key = 'benchmark-list'
    wrapper.unmount()
  })

  it('maps supported plain number shortcuts to daily and weekly active-chart intervals', async () => {
    routeState.path = '/'
    routeState.params = {}
    harness.workspace.activeTab.active_window_key = 'chart-main'
    harness.workspace.updateToolTimeframe.mockReturnValue(true)
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const workstation = wrapper.find('.workstation').element

    for (const [key, timeframe] of [['1', 'D1'], ['5', 'W1']] as const) {
      const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true })
      workstation.dispatchEvent(event)
      expect(event.defaultPrevented).toBe(true)
      expect(harness.workspace.updateToolTimeframe).toHaveBeenLastCalledWith('chart-main', timeframe)
    }

    harness.workspace.updateToolTimeframe.mockClear()
    const unsupportedInterval = new KeyboardEvent('keydown', { key: '2', bubbles: true, cancelable: true })
    workstation.dispatchEvent(unsupportedInterval)
    expect(unsupportedInterval.defaultPrevented).toBe(true) // remains type-to-search
    expect(harness.workspace.updateToolTimeframe).not.toHaveBeenCalled()

    harness.workspace.activeTab.active_window_key = 'benchmark-list'
    const nonChart = new KeyboardEvent('keydown', { key: '1', bubbles: true, cancelable: true })
    workstation.dispatchEvent(nonChart)
    expect(nonChart.defaultPrevented).toBe(true) // symbol search retains ownership
    expect(harness.workspace.updateToolTimeframe).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('leaves the period key to the active chart date pointer and keeps symbol search elsewhere', async () => {
    routeState.path = '/'
    routeState.params = {}
    harness.workspace.activeTab.active_window_key = 'chart-main'
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const workstation = wrapper.find('.workstation').element

    const chartEvent = new KeyboardEvent('keydown', { key: '.', bubbles: true, cancelable: true })
    workstation.dispatchEvent(chartEvent)
    expect(chartEvent.defaultPrevented).toBe(false)

    harness.workspace.activeTab.active_window_key = 'benchmark-list'
    const nonChartEvent = new KeyboardEvent('keydown', { key: '.', bubbles: true, cancelable: true })
    workstation.dispatchEvent(nonChartEvent)
    expect(nonChartEvent.defaultPrevented).toBe(true)
    wrapper.unmount()
  })

  it('routes unmodified F1-F12 shortcuts to the active chart template control only', async () => {
    routeState.path = '/'
    routeState.params = {}
    harness.workspace.activeTab.active_window_key = 'chart-main'
    const received: CustomEvent[] = []
    const listener = (event: Event) => received.push(event as CustomEvent)
    window.addEventListener('tc2000:chart-template-key', listener)
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const workstation = wrapper.find('.workstation').element

    const chartEvent = new KeyboardEvent('keydown', { key: 'F5', bubbles: true, cancelable: true })
    workstation.dispatchEvent(chartEvent)
    expect(chartEvent.defaultPrevented).toBe(true)
    expect(received).toHaveLength(1)
    expect(received[0].detail).toEqual({ windowKey: 'chart-main', functionKey: 'F5' })

    harness.workspace.activeTab.active_window_key = 'benchmark-list'
    const nonChartEvent = new KeyboardEvent('keydown', { key: 'F5', bubbles: true, cancelable: true })
    workstation.dispatchEvent(nonChartEvent)
    expect(nonChartEvent.defaultPrevented).toBe(false)
    expect(received).toHaveLength(1)

    const modifiedEvent = new KeyboardEvent('keydown', { key: 'F5', ctrlKey: true, bubbles: true, cancelable: true })
    workstation.dispatchEvent(modifiedEvent)
    expect(received).toHaveLength(1)
    window.removeEventListener('tc2000:chart-template-key', listener)
    wrapper.unmount()
  })

  it('cycles supported Ctrl+B chart styles only on the active chart', async () => {
    routeState.path = '/'
    routeState.params = {}
    harness.workspace.activeTab.active_window_key = 'chart-main'
    harness.chartWindow.configuration = { bar_type: 'ohlc', marker: 'preserved' }
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const workstation = wrapper.find('.workstation').element

    for (const expected of ['candles', 'line', 'hlc', 'ohlc']) {
      const event = new KeyboardEvent('keydown', { key: 'b', ctrlKey: true, bubbles: true, cancelable: true })
      workstation.dispatchEvent(event)
      expect(event.defaultPrevented).toBe(true)
      expect(harness.chartWindow.configuration.bar_type).toBe(expected)
      expect(harness.chartWindow.configuration.marker).toBe('preserved')
    }

    harness.workspace.activeTab.active_window_key = 'benchmark-list'
    const nonChart = new KeyboardEvent('keydown', { key: 'b', ctrlKey: true, bubbles: true, cancelable: true })
    workstation.dispatchEvent(nonChart)
    expect(nonChart.defaultPrevented).toBe(false)
    expect(harness.chartWindow.configuration.bar_type).toBe('ohlc')
    harness.workspace.activeTab.active_window_key = 'benchmark-list'
    wrapper.unmount()

    harness.workspace.activeTab.active_window_key = 'chart-main'
    harness.chartWindow.configuration = {}
    const defaultStyleWrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const defaultStyleEvent = new KeyboardEvent('keydown', { key: 'b', ctrlKey: true, bubbles: true, cancelable: true })
    defaultStyleWrapper.find('.workstation').element.dispatchEvent(defaultStyleEvent)
    expect(defaultStyleEvent.defaultPrevented).toBe(true)
    expect(harness.chartWindow.configuration.bar_type).toBe('line')
    harness.workspace.activeTab.active_window_key = 'benchmark-list'
    defaultStyleWrapper.unmount()
  })

  it('opens the active chart plot library with slash but leaves other windows untouched', () => {
    routeState.path = '/'
    routeState.params = {}
    harness.workspace.activeTab.active_window_key = 'chart-main'
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const workstation = wrapper.find('.workstation').element
    const toolWindow = document.createElement('section')
    toolWindow.className = 'tool-window'
    toolWindow.dataset.windowKey = 'chart-main'
    const trigger = document.createElement('button')
    trigger.setAttribute('aria-label', 'Chart plot library')
    const click = vi.fn()
    trigger.addEventListener('click', click)
    toolWindow.append(trigger)
    document.body.append(toolWindow)

    const event = new KeyboardEvent('keydown', { key: '/', bubbles: true, cancelable: true })
    workstation.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
    expect(click).toHaveBeenCalledOnce()

    harness.workspace.activeTab.active_window_key = 'benchmark-list'
    const nonChart = new KeyboardEvent('keydown', { key: '/', bubbles: true, cancelable: true })
    workstation.dispatchEvent(nonChart)
    expect(nonChart.defaultPrevented).toBe(false)
    expect(click).toHaveBeenCalledOnce()

    toolWindow.remove()
    wrapper.unmount()
  })

  it('replays a newer shell traversal after late workspace hydration', async () => {
    routeState.path = '/'
    routeState.params = {}
    harness.workspace.marketGroups = {
      'us-benchmarks': {
        members: [
          { instrument: { symbol: 'SPY', id: 1 } },
          { instrument: { symbol: 'QQQ', id: 2 } },
          { instrument: { symbol: 'DIA', id: 3 } },
          { instrument: { symbol: 'IWM', id: 4 } },
        ],
      },
      'sp500-sectors': { members: [] },
    }
    let releaseHydration!: () => void
    harness.workspace.loadDefault = vi.fn(() => new Promise<void>(resolve => { releaseHydration = resolve }))
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await wrapper.find('.workstation').trigger('keydown', { key: ' ', ctrlKey: true })
    expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'IWM', group: 'blue' }))

    releaseHydration()
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenLastCalledWith(expect.objectContaining({ symbol: 'IWM', group: 'blue' })))
    wrapper.unmount()
  })

  it('replays a linked timeframe selected before initial workspace hydration', async () => {
    routeState.path = '/'
    routeState.params = {}
    let releaseHydration!: () => void
    harness.workspace.loadDefault = vi.fn(() => new Promise<void>(resolve => {
      releaseHydration = () => {
        // Simulate the persisted snapshot replacing a choice made from the
        // shell while its request was still in flight.
        harness.workspace.linkedTimeframe = 'D1'
        resolve()
      }
    }))
    harness.workspace.publishTimeframe = vi.fn((timeframe: string) => {
      harness.workspace.linkedTimeframe = timeframe
    })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })

    await wrapper.get('select[aria-label="Linked timeframe"]').setValue('H1')
    expect(harness.workspace.linkedTimeframe).toBe('H1')
    expect(harness.workspace.publishTimeframe).toHaveBeenCalledTimes(1)

    releaseHydration()
    await vi.waitFor(() => {
      expect(harness.workspace.publishTimeframe).toHaveBeenLastCalledWith('H1', 'blue', 'workstation')
      expect(harness.workspace.linkedTimeframe).toBe('H1')
    })
    expect(harness.workspace.publishTimeframe).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('prepares the primary chart timeframe without a comparison widget and ignores superseded history', async () => {
    routeState.path = '/chart/AMD'
    routeState.params = { symbol: 'AMD' }
    harness.workspace.linkedSymbol = 'AMD'
    const originalWindows = harness.workspace.activeTab.windows
    const originalLinkedTimeframeDescriptor = Object.getOwnPropertyDescriptor(harness.workspace, 'linkedTimeframe')
    const reactiveTimeframe = reactive({ value: 'D1' })
    Object.defineProperty(harness.workspace, 'linkedTimeframe', {
      configurable: true,
      get: () => reactiveTimeframe.value,
      set: (value: string) => { reactiveTimeframe.value = value },
    })
    harness.workspace.activeTab.windows = [harness.chartWindow]
    harness.chart.symbol = 'AMD'
    harness.chart.timeframe = 'D1'
    harness.chart.instrument = { id: 36, symbol: 'AMD' }
    const originalLoadBarsImplementation = harness.chart.loadBars.getMockImplementation()
    harness.chart.loadBars.mockImplementation(async (symbol: string, timeframe?: string) => {
      harness.chart.symbol = symbol
      if (timeframe) harness.chart.timeframe = timeframe
    })
    vi.mocked(resolveKnownInstrument).mockResolvedValueOnce({ symbol: 'AMD', id: 36 } as any)
    harness.workspace.publishTimeframe = vi.fn((timeframe: string) => {
      harness.workspace.linkedTimeframe = timeframe
    })

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await vi.waitFor(() => expect(dataPreparationPost).toHaveBeenCalledTimes(1))
      await vi.waitFor(() => expect(wrapper.text()).toContain('The admitted D1 history for AMD is available locally.'))
      await flushPromises()
      dataPreparationPost.mockClear()
      const firstMinute = deferred<any>()
      const fiveMinute = deferred<any>()
      dataPreparationPost.mockImplementation((request: any) => {
        if (request.timeframe === 'M1') return firstMinute.promise
        if (request.timeframe === 'M5') return fiveMinute.promise
        return Promise.resolve(readyPreparationResponse(request, dataPreparationPost.mock.calls.length))
      })
      harness.chart.loadBars.mockClear()
      harness.chart.refreshLocalBars.mockClear()

      const linkedTimeframe = wrapper.get('select[aria-label="Linked timeframe"]')
      await linkedTimeframe.setValue('M1')
      await vi.waitFor(() => expect(dataPreparationPost).toHaveBeenCalledTimes(1))
      expect(dataPreparationPost.mock.calls[0]?.[0]).toMatchObject({
        target: { kind: 'instrument', instrument_id: 36 },
        datasets: ['history'],
        timeframe: 'M1',
        adjusted: true,
      })
      expect(harness.chart.loadBars).toHaveBeenCalledWith('AMD', 'M1', 'candles', true)

      await linkedTimeframe.setValue('M5')
      await vi.waitFor(() => expect(dataPreparationPost).toHaveBeenCalledTimes(2))
      expect(dataPreparationPost.mock.calls[1]?.[0]).toMatchObject({
        target: { kind: 'instrument', instrument_id: 36 },
        datasets: ['history'],
        timeframe: 'M5',
      })
      expect(dataPreparationPost).toHaveBeenCalledTimes(2)

      firstMinute.resolve(readyPreparationResponse(dataPreparationPost.mock.calls[0]?.[0], 2))
      await flushPromises()
      expect(harness.chart.refreshLocalBars).not.toHaveBeenCalled()

      fiveMinute.resolve(readyPreparationResponse(dataPreparationPost.mock.calls[1]?.[0], 3))
      await vi.waitFor(() => expect(harness.chart.refreshLocalBars).toHaveBeenCalledTimes(1))
      expect(wrapper.text()).toContain('The admitted M5 history for AMD is available locally.')
      expect(harness.chart.refreshLocalBars).toHaveBeenCalledTimes(1)
    } finally {
      harness.workspace.activeTab.windows = originalWindows
      wrapper.unmount()
      if (originalLoadBarsImplementation) harness.chart.loadBars.mockImplementation(originalLoadBarsImplementation)
      if (originalLinkedTimeframeDescriptor) Object.defineProperty(harness.workspace, 'linkedTimeframe', originalLinkedTimeframeDescriptor)
    }
  })

  it('does not continue initial hydration after the workstation unmounts', async () => {
    routeState.path = '/'
    routeState.params = {}
    let releaseHydration!: () => void
    harness.workspace.loadDefault = vi.fn(() => new Promise<void>(resolve => { releaseHydration = resolve }))
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })

    expect(harness.workspace.loadDefault).toHaveBeenCalledTimes(1)
    wrapper.unmount()
    releaseHydration()
    await flushPromises()

    expect(harness.workspace.publishSymbol).not.toHaveBeenCalled()
  })

  it('exposes an accessible loading state while canonical symbol search is pending', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockImplementation(() => new Promise(() => undefined))
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const input = wrapper.get('input[aria-label="Active symbol"]')
    await input.setValue('zz')
    await vi.waitFor(() => expect(wrapper.find('[role="listbox"]').exists()).toBe(true))
    const listbox = wrapper.get('[role="listbox"]')
    expect(listbox.attributes('aria-busy')).toBe('true')
    expect(listbox.get('[role="status"]').text()).toContain('Searching canonical instruments')
    expect(wrapper.find('.workstation__source-actions').exists()).toBe(false)
    expect(input.attributes('aria-busy')).toBe('true')
    wrapper.unmount()
  })

  it('runs canonical search for a DOM input event when the route-hydrated ticker value is unchanged', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockResolvedValue([{ symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', exchange: 'ARCX', type: 'ETF', instrument_id: 1 }])
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
    const input = wrapper.get('input[aria-label="Active symbol"]')
    expect((input.element as HTMLInputElement).value).toBe('SPY')
    expect(input.attributes('aria-expanded')).toBe('false')

    // The user can deliberately re-edit/paste the same ticker after route
    // hydration. A ref watcher alone would not run because the value is equal.
    await input.trigger('input')
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/instruments/search', { q: 'SPY', canonical_only: true }, { priority: 'high' }))
    await vi.waitFor(() => expect(wrapper.findAll('[role="option"]').some(option => option.text().includes('SPY'))).toBe(true))
    expect(input.attributes('aria-expanded')).toBe('true')
    expect(apiPost).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('starts local search and discovery on a one-shot edit while the hydrated search is closed', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockImplementation(async (path, params) => {
      if (path !== '/instruments/search') return []
      if (params?.q === 'SPY') return [{ symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', exchange: 'ARCX', type: 'ETF', instrument_id: 1 }]
      return []
    })
    apiPost.mockResolvedValue({ request_id: 'nvda-1', status: 'no_match', candidates: [], source_outcomes: [] })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
    const input = wrapper.get('input[aria-label="Active symbol"]')
    expect(input.attributes('aria-expanded')).toBe('false')
    expect(apiPost).not.toHaveBeenCalled()

    // Model a single paste/fill input event while the closed picker has a
    // route-hydrated value. The DOM event must start the normal local-search
    // then discovery debounce without requiring focus/open/second keystroke.
    ;(input.element as HTMLInputElement).value = 'NVDA'
    await input.trigger('input')

    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/instruments/search', { q: 'NVDA', canonical_only: true }, { priority: 'high' }))
    await vi.waitFor(() => expect(apiPost).toHaveBeenCalledWith('/instruments/discover', expect.objectContaining({ query: 'NVDA' }), expect.objectContaining({ priority: 'high', signal: expect.any(AbortSignal) })))
    await vi.waitFor(() => expect(wrapper.text()).toContain('No matching ticker is available for “NVDA”'))
    expect(apiPost).toHaveBeenCalledTimes(1)
    expect(input.attributes('aria-expanded')).toBe('true')
    wrapper.unmount()
  })

  it('starts the latest Workstation discovery while an older query is pending and ignores its stale candidate', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockResolvedValue([])
    let finishOldDiscovery!: (value: unknown) => void
    const oldDiscovery = new Promise(resolve => { finishOldDiscovery = resolve })
    apiPost
      .mockReturnValueOnce(oldDiscovery as ReturnType<typeof apiPost>)
      .mockResolvedValueOnce({ request_id: 'bw-2', status: 'no_match', candidates: [], source_outcomes: [] })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const input = wrapper.get('input[aria-label="Active symbol"]')
    await input.setValue('TCNEW')
    await vi.waitFor(() => expect(apiPost).toHaveBeenCalledTimes(1))
    await input.setValue('BWET')
    await vi.waitFor(() => expect(apiPost).toHaveBeenCalledTimes(2))
    expect(apiPost).toHaveBeenNthCalledWith(2, '/instruments/discover', expect.objectContaining({ query: 'BWET' }), expect.objectContaining({ priority: 'high', signal: expect.any(AbortSignal) }))
    await vi.waitFor(() => expect(wrapper.text()).toContain('No matching ticker is available for “BWET”'))

    finishOldDiscovery({
      request_id: 'tc-1', status: 'complete',
      candidates: [{ symbol: 'TCNEW', name: 'Stale candidate', exchange: 'TEST', type: 'Stock', provider: 'fixture', instrument_id: null, identity_status: 'provider_candidate' }],
      source_outcomes: [],
    })
    await flushPromises()
    expect(wrapper.text()).not.toContain('Use TCNEW')
    expect(wrapper.find('.workstation__source-option').exists()).toBe(false)
    wrapper.unmount()
  })

  it('renders an explicit no-result state without creating a selectable row', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockResolvedValue([])
    apiPost.mockResolvedValue({ request_id: 'fixture', status: 'no_match', candidates: [], source_outcomes: [] })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const input = wrapper.get('input[aria-label="Active symbol"]')
    await input.setValue('zzzz')
    await vi.waitFor(() => expect(wrapper.get('.workstation__symbol-results .workstation__symbol-search-message').text()).toContain('No matching ticker is available'))
    const listbox = wrapper.get('[role="listbox"]')
    expect(listbox.text()).toContain('No matching ticker is available for “ZZZZ”')
    expect(wrapper.findAll('[role="option"]')).toHaveLength(0)
    expect(wrapper.find('.workstation__source-actions').exists()).toBe(false)
    expect(input.attributes('aria-expanded')).toBe('true')
    wrapper.unmount()
  })

  it('automatically discovers a local miss and resolves the selected candidate before workstation selection', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockResolvedValue([])
    apiPost
      .mockResolvedValueOnce({
        request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d', status: 'complete',
        candidates: [{ symbol: 'OIH', name: 'Oil Services ETF', exchange: 'NYSE Arca', type: 'ETF', provider: 'free-source', instrument_id: null, identity_status: 'provider_candidate' }],
        source_outcomes: [],
      })
      .mockResolvedValueOnce({
        request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d', status: 'resolved',
        instrument: { instrument_id: 43, symbol: 'OIH', identity_status: 'resolved', instrument_type: 'ETF' }, source_outcomes: [],
      })
      .mockResolvedValueOnce({
        request_id: 'f9fc3c4c-8ba9-44e3-bf11-bf3c5eaef82d', instrument_id: 43, symbol: 'OIH',
        outcome: 'unavailable', refresh: true, refresh_attempted: true, refresh_succeeded: false,
        profile: null, provider_request_log_ids: [], message: 'No current fixture holdings are available.',
      })

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const input = wrapper.get('input[aria-label="Active symbol"]')
    await input.setValue('OIH')
    await vi.waitFor(() => expect(wrapper.find('.workstation__source-actions button').exists()).toBe(true))
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/instruments/search', { q: 'OIH', canonical_only: true }, { priority: 'high' }))
    expect(wrapper.get('[role="listbox"]').element.contains(wrapper.get('.workstation__source-actions').element)).toBe(false)
    expect(apiPost).toHaveBeenNthCalledWith(1, '/instruments/discover', {
      query: 'OIH', types: [], limit: 10, request_id: expect.stringMatching(/^[0-9a-f-]{36}$/),
    }, expect.objectContaining({ priority: 'high', signal: expect.any(AbortSignal) }))
    const candidate = wrapper.findAll('.workstation__source-option').find(button => button.text().includes('Use OIH'))
    expect(candidate).toBeTruthy()
    await candidate!.trigger('click')
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'OIH', instrumentId: 43 })))
    await vi.waitFor(() => expect(apiPost).toHaveBeenCalledTimes(2))
    expect(apiPost).toHaveBeenNthCalledWith(2, '/instruments/acquire', {
      symbol: 'OIH', provider_candidate: { provider: 'free-source', symbol: 'OIH', exchange: 'NYSE Arca' },
      request_id: expect.stringMatching(/^[0-9a-f-]{36}$/),
    }, expect.objectContaining({ priority: 'high', signal: expect.any(AbortSignal) }))
    expect(apiPost.mock.calls[1][1].request_id).not.toBe(apiPost.mock.calls[0][1].request_id)
    expect(resolveKnownInstrument).not.toHaveBeenCalledWith('OIH', 'Workstation symbol', { canonicalOnly: true })
    await vi.waitFor(() => expect(dataPreparationPost.mock.calls.some(([request]) => request.target.instrument_id === 43 && request.datasets.includes('holdings'))).toBe(true))
    await flushPromises()
    await vi.waitFor(() => expect(harness.workspace.refreshMarketAnalysis).toHaveBeenCalled())
    wrapper.unmount()
  })

  it('refreshes local technical details after selected history is persisted', async () => {
    routeState.path = '/'
    routeState.params = {}
    let historyPersisted = false
    const technicalReadResults: Array<{ freshness?: string } | null> = []
    apiGet.mockImplementation(async (path: string) => {
      if (path === '/instruments/search') return []
      if (path === '/coverage/instruments/OIH/ohlcv') {
        return { status: 'missing', bar_count: 0, missing_slices: [{ start: '2026-10-01T00:00:00Z', end: '2026-11-01T00:00:00Z' }] }
      }
      if (path === '/instruments/43/history-availability') {
        return { instrument_id: 43, symbol: 'OIH', timeframe: 'D1', adjusted: true, status: 'eligible', earliest_start: '2024-01-01T00:00:00Z', max_requested_bars: 2000, reason_code: null }
      }
      return []
    })
    apiPost.mockImplementation(async (path: string, body: Record<string, any>) => {
      if (path === '/instruments/discover') {
        return {
          request_id: 'discover-oih', status: 'complete',
          candidates: [{ symbol: 'OIH', name: 'Oil services ETF', exchange: 'ARCX', type: 'Common Stock', provider: 'fixture', instrument_id: null, identity_status: 'provider_candidate' }],
          source_outcomes: [],
        }
      }
      if (path === '/instruments/acquire' && body.provider_candidate) {
        return { request_id: 'resolve-oih', status: 'resolved', instrument: { instrument_id: 43, symbol: 'OIH', identity_status: 'verified' }, source_outcomes: [] }
      }
      if (path === '/instruments/acquire') {
        return { request_id: 'existing-oih', status: 'resolved', instrument: { instrument_id: 43, symbol: 'OIH', identity_status: 'verified' }, source_outcomes: [] }
      }
      if (path === '/instruments/43/history-acquisitions') {
        historyPersisted = true
        return {
          request_id: 'history-oih', status: 'complete', instrument_id: 43, symbol: 'OIH', timeframe: 'D1', adjusted: true,
          requested_start: body.start, requested_end: body.end, coverage: { status: 'ready', bar_count: 12, missing_slices: [] }, bars: [], source_outcomes: [],
        }
      }
      return {}
    })
    dataPreparationPost.mockImplementation(async (request: any) => {
      if (request.target.instrument_id === 43 && request.datasets.includes('history')) historyPersisted = true
      return readyPreparationResponse(request, dataPreparationPost.mock.calls.length)
    })
    harness.workspace.publishSymbol = vi.fn(({ symbol }: { symbol: string }) => { harness.workspace.linkedSymbol = symbol })
    harness.workspace.loadTechnical = vi.fn(async (symbol: string) => {
      harness.workspace.technicals[symbol] = historyPersisted ? { freshness: 'current' } : null
      if (symbol === 'OIH') technicalReadResults.push(harness.workspace.technicals[symbol])
      return harness.workspace.technicals[symbol]
    })
    harness.chart.refreshLocalBars.mockImplementation(async () => { harness.chart.bars = [{ close: 42 }] })

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      const input = wrapper.get('input[aria-label="Active symbol"]')
      await input.setValue('OIH')
      await vi.waitFor(() => expect(wrapper.find('.workstation__source-actions button').exists()).toBe(true))
      await wrapper.findAll('.workstation__source-option').find(button => button.text().includes('Use OIH'))!.trigger('click')

      await vi.waitFor(() => expect(dataPreparationPost).toHaveBeenCalledWith(expect.objectContaining({
        target: { kind: 'instrument', instrument_id: 43 }, datasets: ['identity', 'profile', 'history'], timeframe: 'D1', adjusted: true,
      }), expect.anything()))
      expect(harness.chart.symbol).toBe('OIH')
      expect(harness.workspace.linkedSymbol).toBe('OIH')
      await flushPromises()
      expect(wrapper.text()).toContain('The admitted D1 history for OIH is available locally.')
      await vi.waitFor(() => expect(harness.chart.refreshLocalBars).toHaveBeenCalledOnce())
      expect(harness.workspace.loadTechnical.mock.calls.filter(([symbol]) => symbol === 'OIH')).toHaveLength(2)
      expect(technicalReadResults).toEqual([null, { freshness: 'current' }])
      expect(harness.workspace.technicals.OIH).toEqual({ freshness: 'current' })
      expect(harness.chart.symbol).toBe('OIH')
    } finally {
      wrapper.unmount()
    }
  })

  it('does not let a late shared-preparation completion refresh technicals for a newer symbol', async () => {
    routeState.path = '/'
    routeState.params = {}
    let finishA!: (value: unknown) => void
    apiGet.mockImplementation(async (path: string) => {
      if (path === '/instruments/search') return []
      if (path.startsWith('/coverage/instruments/')) {
        return { status: 'missing', bar_count: 0, missing_slices: [{ start: '2026-10-01T00:00:00Z', end: '2026-11-01T00:00:00Z' }] }
      }
      const availabilityId = Number(path.match(/^\/instruments\/(\d+)\/history-availability$/)?.[1])
      if (availabilityId === 71 || availabilityId === 72) {
        return { instrument_id: availabilityId, symbol: availabilityId === 71 ? 'AAA' : 'BBB', timeframe: 'D1', adjusted: true, status: 'eligible', earliest_start: '2024-01-01T00:00:00Z', max_requested_bars: 2000, reason_code: null }
      }
      return []
    })
    apiPost.mockImplementation((path: string, body: Record<string, any>) => {
      if (path === '/instruments/discover') {
        const symbol = String(body.query)
        return Promise.resolve({
          request_id: `discover-${symbol}`, status: 'complete',
          candidates: [{ symbol, name: `${symbol} fixture`, exchange: 'XNAS', type: 'Common Stock', provider: 'fixture', instrument_id: null, identity_status: 'provider_candidate' }],
          source_outcomes: [],
        })
      }
      if (path === '/instruments/acquire' && body.provider_candidate) {
        const symbol = String(body.symbol)
        return Promise.resolve({ request_id: `resolve-${symbol}`, status: 'resolved', instrument: { instrument_id: symbol === 'AAA' ? 71 : 72, symbol, identity_status: 'verified' }, source_outcomes: [] })
      }
      if (path === '/instruments/acquire') {
        const symbol = String(body.symbol)
        return Promise.resolve({ request_id: `identity-${symbol}`, status: 'resolved', instrument: { instrument_id: symbol === 'AAA' ? 71 : 72, symbol, identity_status: 'verified' }, source_outcomes: [] })
      }
      return Promise.resolve({})
    })
    dataPreparationPost.mockImplementation((request: any) => {
      if (request.target.instrument_id === 71) {
        return new Promise(resolve => { finishA = () => resolve(readyPreparationResponse(request, 71)) })
      }
      return Promise.resolve(readyPreparationResponse(request, 72))
    })
    harness.workspace.publishSymbol = vi.fn(({ symbol }: { symbol: string }) => { harness.workspace.linkedSymbol = symbol })
    harness.workspace.loadTechnical = vi.fn(async (symbol: string) => { harness.workspace.technicals[symbol] = { freshness: symbol === 'BBB' ? 'current' : 'stale' } })

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      const input = wrapper.get('input[aria-label="Active symbol"]')
      await input.setValue('AAA')
      await vi.waitFor(() => expect(wrapper.find('.workstation__source-actions button').exists()).toBe(true))
      await wrapper.findAll('.workstation__source-option').find(button => button.text().includes('Use AAA'))!.trigger('click')
      await vi.waitFor(() => expect(dataPreparationPost.mock.calls.some(([request]) => request.target.instrument_id === 71)).toBe(true))

      await input.setValue('BBB')
      await vi.waitFor(() => expect(wrapper.find('.workstation__source-actions button').exists()).toBe(true))
      await wrapper.findAll('.workstation__source-option').find(button => button.text().includes('Use BBB'))!.trigger('click')
      await vi.waitFor(() => expect(harness.chart.symbol).toBe('BBB'))
      await vi.waitFor(() => expect(dataPreparationPost.mock.calls.some(([request]) => request.target.instrument_id === 72)).toBe(true))
      await vi.waitFor(() => expect(harness.chart.refreshLocalBars).toHaveBeenCalledOnce())
      expect(harness.workspace.loadTechnical.mock.calls.filter(([symbol]) => symbol === 'BBB')).toHaveLength(2)

      finishA?.()
      await flushPromises()
      expect(harness.workspace.loadTechnical.mock.calls.filter(([symbol]) => symbol === 'AAA')).toHaveLength(1)
      expect(harness.chart.refreshLocalBars).toHaveBeenCalledOnce()
      expect(harness.workspace.linkedSymbol).toBe('BBB')
      expect(harness.workspace.technicals.BBB).toEqual({ freshness: 'current' })
    } finally {
      wrapper.unmount()
    }
  })

  it('keeps a locally typed stock out of the ETF refresh path even when an old ETF snapshot exists', async () => {
    routeState.path = '/'
    routeState.params = {}
    const oldSnapshot = { id: 801, etf_symbol: 'CURR' }
    harness.workspace.etfHoldings = { CURR: { snapshot: oldSnapshot } }
    harness.workspace.loadETFHoldings = vi.fn(async () => harness.workspace.etfHoldings.CURR)
    apiGet.mockImplementation(async (path: string, params?: Record<string, unknown>) => {
      if (path === '/instruments/search' && params?.q === 'CURR') {
        return [{ symbol: 'CURR', name: 'Misclassified local fixture', type: 'Stock', exchange: 'ARCX', instrument_id: 81, identity_status: 'provisional' }]
      }
      if (path === '/coverage/instruments/CURR/ohlcv') return { status: 'ready', bar_count: 20, missing_slices: [] }
      if (path === '/etf-holdings/CURR/capability') return {
        availability: 'current', source_tier: 'issuer_native', identity_verified: true,
        usable_for_current_analysis: true, displayable_last_known: true,
        consecutive_failures: 0, reason: 'Current controlled cache.',
        symbol_audit: { tier: 0, outcome: 'not_run', evidence_state: 'test_fixture', next_action: '', evidence_refs: [] },
      }
      return []
    })
    harness.workspace.setConstituentETF = vi.fn((symbol: string | null) => { harness.workspace.constituentETF = symbol })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      const input = wrapper.get('input[aria-label="Active symbol"]')
      await input.setValue('CURR')
      await vi.waitFor(() => expect(wrapper.find('.workstation__canonical-symbol-options [role="option"]').exists()).toBe(true))
      vi.mocked(harness.workspace.loadETFHoldings).mockClear()
      await wrapper.get('.workstation__canonical-symbol-options [role="option"]').trigger('mousedown')
      await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'CURR', instrumentId: 81 })))
      expect(dataPreparationPost.mock.calls.some(([request]) => request.target.instrument_id === 81 && request.datasets.includes('holdings'))).toBe(false)
      expect(apiGet).not.toHaveBeenCalledWith('/etf-holdings/CURR/capability')
      expect(harness.workspace.loadETFHoldings).toHaveBeenCalledWith('CURR', 'high')
      expect(harness.workspace.etfHoldings.CURR?.snapshot).toBe(oldSnapshot)
      expect(harness.workspace.constituentETF).toBeNull()
    } finally {
      wrapper.unmount()
    }
  })

  it.each(['stale', 'unknown'] as const)('refreshes a saved ETF once when capability is %s and reads back the same fund', async capabilityState => {
    routeState.path = '/'
    routeState.params = {}
    const oldSnapshot = { id: 811, etf_symbol: 'STALE' }
    const updatedSnapshot = { id: 812, etf_symbol: 'STALE' }
    harness.workspace.etfHoldings = { STALE: { snapshot: oldSnapshot } }
    let localHoldingsReads = 0
    harness.workspace.loadETFHoldings = vi.fn(async (symbol: string) => {
      expect(symbol).toBe('STALE')
      localHoldingsReads += 1
      if (localHoldingsReads > 1) harness.workspace.etfHoldings.STALE = { snapshot: updatedSnapshot }
      return harness.workspace.etfHoldings.STALE
    })
    apiGet.mockImplementation(async (path: string, params?: Record<string, unknown>) => {
      if (path === '/instruments/search' && params?.q === 'STALE') {
        return [{ symbol: 'STALE', name: 'Stale fixture ETF', type: 'ETF', exchange: 'ARCX', instrument_id: 82, identity_status: 'resolved' }]
      }
      if (path === '/coverage/instruments/STALE/ohlcv') return { status: 'ready', bar_count: 20, missing_slices: [] }
      if (path === '/etf-holdings/STALE/capability' && capabilityState === 'unknown') {
        throw new Error('The capability view is unavailable in this controlled case.')
      }
      if (path === '/etf-holdings/STALE/capability') return {
        availability: 'stale', source_tier: 'issuer_native', identity_verified: true,
        usable_for_current_analysis: false, displayable_last_known: true,
        consecutive_failures: 0, reason: 'The controlled snapshot is stale.',
        symbol_audit: { tier: 0, outcome: 'not_run', evidence_state: 'test_fixture', next_action: '', evidence_refs: [] },
      }
      return []
    })
    apiPost.mockImplementation(async (path: string) => path === '/instruments/acquire'
      ? { request_id: 'identity-stale', status: 'resolved', instrument: { instrument_id: 82, symbol: 'STALE', identity_status: 'resolved' }, source_outcomes: [] }
      : {
        request_id: 'refresh-stale', instrument_id: 82, symbol: 'STALE', outcome: 'acquired',
        refresh: true, refresh_attempted: true, refresh_succeeded: true,
        profile: { symbol: 'STALE', instrument_id: 82 }, snapshot: updatedSnapshot,
        provider_request_log_ids: [],
      })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      const input = wrapper.get('input[aria-label="Active symbol"]')
      await input.setValue('STALE')
      await vi.waitFor(() => expect(wrapper.find('.workstation__canonical-symbol-options [role="option"]').exists()).toBe(true))
      await wrapper.get('.workstation__canonical-symbol-options [role="option"]').trigger('mousedown')
      await vi.waitFor(() => expect(dataPreparationPost.mock.calls.some(([request]) =>
        request.target.instrument_id === 82 && request.datasets.join(',') === 'holdings',
      )).toBe(true))
      await vi.waitFor(() => expect(harness.workspace.etfHoldings.STALE?.snapshot).toBe(updatedSnapshot))
      expect(apiPost).not.toHaveBeenCalledWith('/etf-holdings/STALE/acquire', expect.anything())
      expect(localHoldingsReads).toBe(2)
      expect(wrapper.findAll('.workstation__selection-acquisition').map(element => element.text()).join(' ')).toContain('Current holdings for STALE are available locally.')
    } finally {
      wrapper.unmount()
    }
  })

  it('does not let a late ETF refresh readback replace the newly selected fund status', async () => {
    routeState.path = '/'
    routeState.params = {}
    const savedA = { id: 831, etf_symbol: 'FRESH' }
    const updatedA = { id: 832, etf_symbol: 'FRESH' }
    const currentB = { id: 833, etf_symbol: 'NEXT' }
    harness.workspace.etfHoldings = {
      FRESH: { snapshot: savedA },
      NEXT: { snapshot: currentB },
    }
    let aReadCount = 0
    let finishAReadback!: () => void
    harness.workspace.loadETFHoldings = vi.fn((symbol: string) => {
      if (symbol === 'FRESH') {
        aReadCount += 1
        if (aReadCount === 2) {
          return new Promise(resolve => {
            finishAReadback = () => resolve({ snapshot: updatedA })
          })
        }
        return Promise.resolve({ snapshot: savedA })
      }
      return Promise.resolve({ snapshot: currentB })
    })
    apiGet.mockImplementation(async (path: string, params?: Record<string, unknown>) => {
      const symbol = String(params?.q ?? '').toUpperCase()
      if (path === '/instruments/search' && ['FRESH', 'NEXT'].includes(symbol)) {
        return [{ symbol, name: `${symbol} fixture ETF`, type: 'ETF', exchange: 'ARCX', instrument_id: symbol === 'FRESH' ? 91 : 92 }]
      }
      if (path.startsWith('/coverage/instruments/')) return { status: 'ready', bar_count: 20, missing_slices: [] }
      if (path === '/etf-holdings/FRESH/capability') return {
        availability: 'stale', source_tier: 'issuer_native', identity_verified: true,
        usable_for_current_analysis: false, displayable_last_known: true,
        consecutive_failures: 0, reason: 'The controlled snapshot needs refresh.',
        symbol_audit: { tier: 0, outcome: 'not_run', evidence_state: 'test_fixture', next_action: '', evidence_refs: [] },
      }
      if (path === '/etf-holdings/NEXT/capability') return {
        availability: 'current', source_tier: 'issuer_native', identity_verified: true,
        usable_for_current_analysis: true, displayable_last_known: true,
        consecutive_failures: 0, reason: 'The controlled cache is current.',
        symbol_audit: { tier: 0, outcome: 'not_run', evidence_state: 'test_fixture', next_action: '', evidence_refs: [] },
      }
      return []
    })
    apiPost.mockImplementation((path: string, body: Record<string, any>) => {
      if (path === '/instruments/acquire') {
        const symbol = String(body.symbol)
        return Promise.resolve({
          request_id: `identity-${symbol}`, status: 'resolved',
          instrument: { instrument_id: symbol === 'FRESH' ? 91 : 92, symbol, identity_status: 'resolved', instrument_type: 'Exchange Traded Vehicle' },
          source_outcomes: [],
        })
      }
      return Promise.resolve({})
    })
    harness.workspace.setConstituentETF = vi.fn((symbol: string | null) => { harness.workspace.constituentETF = symbol })

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      const input = wrapper.get('input[aria-label="Active symbol"]')
      await input.setValue('FRESH')
      await vi.waitFor(() => expect(wrapper.find('.workstation__canonical-symbol-options [role="option"]').exists()).toBe(true))
      await wrapper.get('.workstation__canonical-symbol-options [role="option"]').trigger('mousedown')
      await vi.waitFor(() => expect(dataPreparationPost.mock.calls.some(([request]) =>
        request.target.instrument_id === 91 && request.datasets.join(',') === 'holdings',
      )).toBe(true))
      await vi.waitFor(() => expect(aReadCount).toBe(2))

      await input.setValue('NEXT')
      await vi.waitFor(() => expect(wrapper.find('.workstation__canonical-symbol-options [role="option"]').exists()).toBe(true))
      await wrapper.get('.workstation__canonical-symbol-options [role="option"]').trigger('mousedown')
      await vi.waitFor(() => expect(wrapper.findAll('.workstation__selection-acquisition').map(element => element.text()).join(' '))
        .toContain('Current holdings for NEXT are available locally.'))
      expect(harness.workspace.constituentETF).toBe('NEXT')

      finishAReadback()
      await flushPromises()
      expect(harness.workspace.constituentETF).toBe('NEXT')
      expect(wrapper.findAll('.workstation__selection-acquisition').map(element => element.text()).join(' '))
        .toContain('Current holdings for NEXT are available locally.')
      expect(apiPost).not.toHaveBeenCalledWith('/etf-holdings/FRESH/acquire', expect.anything())
    } finally {
      wrapper.unmount()
    }
  })

  it.each(['held', 'failed'] as const)('keeps last-known %s ETF holdings visible after a governed refresh result', async outcome => {
    routeState.path = '/'
    routeState.params = {}
    const savedSnapshot = { id: 821, etf_symbol: 'SAVED' }
    harness.workspace.etfHoldings = { SAVED: { snapshot: savedSnapshot } }
    apiGet.mockImplementation(async (path: string, params?: Record<string, unknown>) => {
      if (path === '/instruments/search' && params?.q === 'SAVED') {
        return [{ symbol: 'SAVED', name: 'Saved fixture ETF', type: 'ETF', exchange: 'ARCX', instrument_id: 83 }]
      }
      if (path === '/coverage/instruments/SAVED/ohlcv') return { status: 'ready', bar_count: 20, missing_slices: [] }
      if (path === '/etf-holdings/SAVED/capability') return {
        availability: 'degraded', source_tier: 'issuer_native', identity_verified: true,
        usable_for_current_analysis: false, displayable_last_known: true,
        consecutive_failures: 1, reason: 'The controlled cache is degraded.',
        symbol_audit: { tier: 0, outcome: 'not_run', evidence_state: 'test_fixture', next_action: '', evidence_refs: [] },
      }
      return []
    })
    dataPreparationPost.mockImplementation(async (request: any) => {
      if (!request.datasets.includes('holdings')) return readyPreparationResponse(request, dataPreparationPost.mock.calls.length)
      const held = outcome === 'held'
      const result = readyPreparationResponse(request, dataPreparationPost.mock.calls.length)
      result.status = held ? 'waiting' : 'failed'
      result.completed = 0
      result.dependencies = result.dependencies.map((dependency: any) => ({
        ...dependency,
        status: held ? 'waiting' : 'failed',
        reason_code: held ? 'provider_quota_admission_denied' : 'provider_source_unavailable',
        retry_at: held ? new Date(Date.now() + 60_000).toISOString() : null,
      }))
      return result
    })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      const input = wrapper.get('input[aria-label="Active symbol"]')
      await input.setValue('SAVED')
      await vi.waitFor(() => expect(wrapper.find('.workstation__canonical-symbol-options [role="option"]').exists()).toBe(true))
      await wrapper.get('.workstation__canonical-symbol-options [role="option"]').trigger('mousedown')
      await vi.waitFor(() => expect(dataPreparationPost.mock.calls.some(([request]) => request.datasets.includes('holdings'))).toBe(true))
      const status = outcome === 'held'
        ? 'Last-known holdings for SAVED remain visible. Holdings for SAVED: The data source is temporarily at its request capacity.'
        : 'Last-known holdings for SAVED remain visible. Holdings for SAVED: A reviewed data source could not complete this request.'
      await vi.waitFor(() => expect(wrapper.text()).toContain(status))
      expect(wrapper.text()).not.toContain('provider_quota_admission_denied')
      expect(harness.workspace.etfHoldings.SAVED?.snapshot).toBe(savedSnapshot)
    } finally {
      wrapper.unmount()
    }
  })

  it('keeps keyboard-focusable source actions open and lets Escape dismiss them', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockResolvedValue([])
    apiPost.mockResolvedValueOnce({
      request_id: 'fixture', status: 'complete',
      candidates: [{ symbol: 'OIH', name: 'Oil services fund', exchange: 'ARCX', type: 'ETF', provider: 'test-fixture', instrument_id: null, identity_status: 'provider_candidate' }],
      source_outcomes: [],
    })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const input = wrapper.get('input[aria-label="Active symbol"]')
    await input.setValue('OIH')
    await vi.waitFor(() => expect(wrapper.find('.workstation__source-actions button').exists()).toBe(true))
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/instruments/search', { q: 'OIH', canonical_only: true }, { priority: 'high' }))
    const action = wrapper.find('.workstation__source-actions button')
    expect((action.element as HTMLButtonElement).tabIndex).toBe(0)
    await input.trigger('focusout', { relatedTarget: action.element })
    expect(input.attributes('aria-expanded')).toBe('true')
    await action.trigger('keydown', { key: 'Escape' })
    expect(input.attributes('aria-expanded')).toBe('false')
    await flushPromises()
    await vi.waitFor(() => expect(harness.workspace.refreshMarketAnalysis).toHaveBeenCalled())
    wrapper.unmount()
  })

  it('renders a recoverable canonical search error and clears it on a new query', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockRejectedValueOnce(new Error('search unavailable'))
    apiGet.mockResolvedValueOnce([{ symbol: 'XLK', name: 'Technology Select Sector SPDR Fund', exchange: 'ARCX', type: 'ETF' }])
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const input = wrapper.get('input[aria-label="Active symbol"]')
    await input.setValue('bad')
    await vi.waitFor(() => expect(wrapper.get('[role="listbox"] [role="alert"]').text()).toContain('Unable to search canonical instruments'))
    expect(wrapper.findAll('[role="listbox"] [role="option"]')).toHaveLength(0)
    await input.setValue('xlk')
    await vi.waitFor(() => expect(wrapper.find('[role="option"]').text()).toContain('XLK'))
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows a deep-linked benchmark in the active-symbol editor before workspace hydration completes', () => {
    routeState.path = '/chart/SPY'
    routeState.params = { symbol: 'SPY' }
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })

    expect((wrapper.get('input[aria-label="Active symbol"]').element as HTMLInputElement).value).toBe('SPY')
    wrapper.unmount()
  })

  it('keeps a newly selected canonical ticker in the chart URL and removes obsolete holding-route context', async () => {
    routeState.path = '/chart'
    routeState.params = {}
    routeState.query = { holding_history_intent: 'selected', holding_snapshot_id: '77', unrelated: 'keep' }
    apiGet.mockImplementation(async (path: string, params?: Record<string, unknown>) => {
      if (path === '/instruments/search' && params?.q === 'XLE') {
        return [{ symbol: 'XLE', name: 'Energy Select Sector SPDR Fund', exchange: 'ARCX', type: 'ETF', instrument_id: 89 }]
      }
      return []
    })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
    const input = wrapper.get('input[aria-label="Active symbol"]')
    await input.setValue('XLE')
    await vi.waitFor(() => expect(wrapper.findAll('[role="option"]').some(option => option.text().includes('XLE'))).toBe(true))
    await wrapper.findAll('[role="option"]').find(option => option.text().includes('XLE'))!.trigger('mousedown')

    await vi.waitFor(() => expect(routerReplace).toHaveBeenCalledWith(expect.objectContaining({ path: '/chart/XLE' })))
    const destination = routerReplace.mock.calls.at(-1)?.[0]
    expect(destination.query).toMatchObject({ unrelated: 'keep' })
    expect(destination.query).not.toHaveProperty('holding_history_intent')
    expect(destination.query).not.toHaveProperty('holding_snapshot_id')
    expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'XLE', instrumentId: 89 }))
    wrapper.unmount()
  })

  it('syncs a blue-linked selection to the main chart URL and clears root-route holding context', async () => {
    routeState.path = '/chart'
    routeState.params = {}
    routeState.query = { holding_snapshot_id: '77', holding_row_id: '9', unrelated: 'keep' }
    harness.workspace = reactive(harness.workspace)
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))

    // A linked pop-out/workspace publication updates the shared selection without
    // going through the shell combobox handler.
    harness.workspace.linkedSymbol = 'XLE'

    await vi.waitFor(() => expect(routerReplace).toHaveBeenCalledWith(expect.objectContaining({ path: '/chart/XLE' })))
    const destination = routerReplace.mock.calls.at(-1)?.[0]
    expect(destination.query).toMatchObject({ unrelated: 'keep' })
    expect(Object.keys(destination.query).some(key => key.startsWith('holding_'))).toBe(false)
    expect(harness.chart.loadBars).toHaveBeenCalledWith('XLE', 'D1', 'candles', true)
    wrapper.unmount()
  })

  it('keeps a typed exact symbol when a prior map publication arrives while Go has focus', async () => {
    routeState.path = '/chart'
    routeState.params = {}
    harness.workspace = reactive(harness.workspace)
    harness.workspace.publishSymbol.mockImplementation((event: any) => {
      harness.workspace.linkedSymbol = event.symbol
    })
    const search = deferred<Array<{ symbol: string; name: string; exchange: string; type: string; instrument_id: number }>>()
    apiGet.mockImplementation(async (path: string, params?: Record<string, unknown>) => {
      if (path === '/instruments/search' && params?.q === 'SPY') return search.promise
      if (path.startsWith('/coverage/instruments/')) return { status: 'ready', bar_count: 124, missing_slices: [] }
      return []
    })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
      harness.workspace.publishSymbol.mockClear()

      // A map tile was selected first, and its committed blue symbol is still
      // visible while the user starts a different exact ticker query.
      harness.workspace.linkedSymbol = 'SPYG'
      await nextTick()
      const input = wrapper.get('input[aria-label="Active symbol"]')
      ;(input.element as HTMLInputElement).focus()
      await input.setValue('SPY')
      await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/instruments/search', { q: 'SPY', canonical_only: true }, { priority: 'high' }))

      // Clicking Go moves focus off the input before its click handler. A late
      // map/link publication in that boundary must not replace the user's draft.
      const go = wrapper.get('.workstation__search > button[type="button"]')
      ;(go.element as HTMLButtonElement).focus()
      harness.workspace.linkedSymbol = 'SPYV'
      await nextTick()
      expect((input.element as HTMLInputElement).value).toBe('SPY')

      search.resolve([
        { symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', exchange: 'ARCX', type: 'ETF', instrument_id: 2 },
        { symbol: 'SPYG', name: 'SPDR Portfolio S&P 500 Growth ETF', exchange: 'ARCX', type: 'ETF', instrument_id: 19 },
        { symbol: 'SPYV', name: 'SPDR Portfolio S&P 500 Value ETF', exchange: 'ARCX', type: 'ETF', instrument_id: 18 },
      ])
      await flushPromises()
      await go.trigger('click')

      await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY', instrumentId: 2 })))
      expect(harness.workspace.publishSymbol).not.toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPYV' }))
      expect(wrapper.get('.workstation__footer > span').text()).toBe('SPY')
    } finally {
      wrapper.unmount()
    }
  })

  it('allows a newer Go intent to finish while an older query is still unresolved', async () => {
    routeState.path = '/chart'
    routeState.params = {}
    harness.workspace = reactive(harness.workspace)
    harness.workspace.publishSymbol.mockImplementation((event: any) => {
      harness.workspace.linkedSymbol = event.symbol
    })
    const oldSearch = deferred<Array<{ symbol: string; name: string; exchange: string; type: string; instrument_id: number }>>()
    apiGet.mockImplementation(async (path: string, params?: Record<string, unknown>) => {
      if (path === '/instruments/search' && params?.q === 'SPYV') return oldSearch.promise
      if (path === '/instruments/search' && params?.q === 'SPY') return [
        { symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', exchange: 'ARCX', type: 'ETF', instrument_id: 2 },
        { symbol: 'SPYG', name: 'SPDR Portfolio S&P 500 Growth ETF', exchange: 'ARCX', type: 'ETF', instrument_id: 19 },
        { symbol: 'SPYV', name: 'SPDR Portfolio S&P 500 Value ETF', exchange: 'ARCX', type: 'ETF', instrument_id: 18 },
      ]
      if (path.startsWith('/coverage/instruments/')) return { status: 'ready', bar_count: 124, missing_slices: [] }
      return []
    })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
      harness.workspace.publishSymbol.mockClear()
      const input = wrapper.get('input[aria-label="Active symbol"]')
      await input.setValue('SPYV')
      await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/instruments/search', { q: 'SPYV', canonical_only: true }, { priority: 'high' }))
      const go = wrapper.get('.workstation__search > button[type="button"]')
      await go.trigger('click')

      // Repeated Go for the same unresolved query is coalesced, but a newer
      // exact query can submit and supersede its pending result.
      await go.trigger('click')
      await input.setValue('SPY')
      await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/instruments/search', { q: 'SPY', canonical_only: true }, { priority: 'high' }))
      await go.trigger('click')
      await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY', instrumentId: 2 })))

      oldSearch.resolve([{ symbol: 'SPYV', name: 'SPY Value', exchange: 'ARCX', type: 'ETF', instrument_id: 18 }])
      await flushPromises()
      expect(harness.workspace.publishSymbol).not.toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPYV' }))
    } finally {
      wrapper.unmount()
    }
  })

  it('keeps an intentional arrow-selected prefix result when Go submits the current query', async () => {
    routeState.path = '/chart'
    routeState.params = {}
    harness.workspace = reactive(harness.workspace)
    harness.workspace.publishSymbol.mockImplementation((event: any) => {
      harness.workspace.linkedSymbol = event.symbol
    })
    apiGet.mockImplementation(async (path: string, params?: Record<string, unknown>) => {
      if (path === '/instruments/search' && params?.q === 'SPY') return [
        { symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', exchange: 'ARCX', type: 'ETF', instrument_id: 2 },
        { symbol: 'SPYG', name: 'SPDR Portfolio S&P 500 Growth ETF', exchange: 'ARCX', type: 'ETF', instrument_id: 19 },
        { symbol: 'SPYV', name: 'SPDR Portfolio S&P 500 Value ETF', exchange: 'ARCX', type: 'ETF', instrument_id: 18 },
      ]
      if (path.startsWith('/coverage/instruments/')) return { status: 'ready', bar_count: 124, missing_slices: [] }
      return []
    })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
      harness.workspace.publishSymbol.mockClear()
      const input = wrapper.get('input[aria-label="Active symbol"]')
      await input.setValue('SPY')
      await vi.waitFor(() => expect(wrapper.findAll('[role="option"]')).toHaveLength(3))
      await input.trigger('keydown', { key: 'ArrowDown' })
      await wrapper.get('.workstation__search > button[type="button"]').trigger('click')
      await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPYG', instrumentId: 19 })))
      expect(harness.workspace.publishSymbol).not.toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY', instrumentId: 2 }))
    } finally {
      wrapper.unmount()
    }
  })

  it('uses a canonical exact result that arrives while Go is waiting for search', async () => {
    routeState.path = '/chart'
    routeState.params = {}
    harness.workspace = reactive(harness.workspace)
    harness.workspace.publishSymbol.mockImplementation((event: any) => {
      harness.workspace.linkedSymbol = event.symbol
    })
    const search = deferred<Array<{ symbol: string; name: string; exchange: string; type: string; instrument_id: number }>>()
    apiGet.mockImplementation(async (path: string, params?: Record<string, unknown>) => {
      if (path === '/instruments/search' && params?.q === 'SPY') return search.promise
      if (path.startsWith('/coverage/instruments/')) return { status: 'ready', bar_count: 124, missing_slices: [] }
      return []
    })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
      harness.workspace.publishSymbol.mockClear()
      const input = wrapper.get('input[aria-label="Active symbol"]')
      await input.setValue('SPY')
      await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/instruments/search', { q: 'SPY', canonical_only: true }, { priority: 'high' }))
      await wrapper.get('.workstation__search > button[type="button"]').trigger('click')

      search.resolve([
        { symbol: 'SPY', name: 'SPDR S&P 500 ETF Trust', exchange: 'ARCX', type: 'ETF', instrument_id: 2 },
        { symbol: 'SPYG', name: 'SPDR Portfolio S&P 500 Growth ETF', exchange: 'ARCX', type: 'ETF', instrument_id: 19 },
        { symbol: 'SPYV', name: 'SPDR Portfolio S&P 500 Value ETF', exchange: 'ARCX', type: 'ETF', instrument_id: 18 },
      ])
      await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY', instrumentId: 2 })))
      expect(harness.workspace.publishSymbol).not.toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPYV' }))
    } finally {
      wrapper.unmount()
    }
  })

  it('keeps selected holding route provenance through linked-symbol workspace hydration', async () => {
    const context = {
      etfSymbol: 'IWM', instrumentId: 8802, canonicalSymbol: 'UNXQ', snapshotId: 8801,
      compositionDate: '2026-10-27', knownAt: '2026-10-28T12:00:00Z',
      provenance: 'issuer_current_holdings', sourceProvider: 'fixture-only', holdingRowId: 8803,
      sourceRowId: 'issuer-row-8803', reportedSymbol: 'UNXQ', reportedName: 'Uncached Example Equity', holdingType: 'equity',
    }
    const confirmedIdentity = {
      status: 'resolved',
      instrument: { instrument_id: 8802, symbol: 'UNXQ', identity_status: 'resolved', instrument_type: 'Common Stock' },
    }
    routeState.path = '/chart/UNXQ'
    routeState.params = { symbol: 'UNXQ' }
    routeState.query = { ...holdingDrilldownRouteQuery(context), holding_history_intent: 'selected' }
    harness.workspace = reactive(harness.workspace)
    harness.workspace.linkedSymbol = 'SPY'
    harness.workspace.publishSymbol.mockImplementation((event: any) => {
      harness.workspace.linkedSymbol = event.symbol
    })
    harness.workspace.setConstituentETF.mockImplementation((symbol: string | null) => {
      harness.workspace.constituentETF = symbol
    })
    let finishWorkspaceLoad!: () => void
    harness.workspace.loadDefault.mockReturnValueOnce(new Promise<void>(resolve => { finishWorkspaceLoad = resolve }))
    const historyState = { ...(window.history.state ?? {}), ...holdingDrilldownRouteState(context, confirmedIdentity as any) }
    window.history.replaceState(historyState, '', window.location.href)
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })

    try {
      await vi.waitFor(() => expect(harness.workspace.loadDefault).toHaveBeenCalled())
      harness.workspace.linkedSymbol = 'SPYV'
      await nextTick()
      expect(routerReplace).not.toHaveBeenCalledWith(expect.objectContaining({ path: '/chart/SPYV' }))
      expect(routeState.query).toMatchObject({ ...holdingDrilldownRouteQuery(context), holding_history_intent: 'selected' })

      finishWorkspaceLoad()
      await vi.waitFor(() => expect(wrapper.get('[data-testid="active-holding-lineage"]').text()).toBe('UNXQ from IWM holdings · 2026-10-27'))
      expect(dataPreparationPost.mock.calls.some(([request]) => request.target?.kind === 'instrument'
        && request.target.instrument_id === 8802)).toBe(true)
      expect(harness.workspace.setConstituentETF).toHaveBeenCalledWith('IWM')

      routerReplace.mockClear()
      harness.workspace.linkedSymbol = 'SPY'
      await nextTick()
      expect(routerReplace).toHaveBeenCalledWith(expect.objectContaining({ path: '/chart/SPY' }))
      expect(Object.keys(routerReplace.mock.calls[0]![0].query).some(key => key.startsWith('holding_'))).toBe(false)
    } finally {
      wrapper.unmount()
      const nextState = { ...(window.history.state ?? {}) }
      delete nextState.tcHoldingSelectionHandoff
      delete nextState.tcHoldingIdentityHandoff
      window.history.replaceState(nextState, '', window.location.href)
    }
  })

  it('preserves same-symbol holding route provenance until workspace hydration finishes, then clears it on a new selection', async () => {
    const context = {
      etfSymbol: 'IWM', instrumentId: 8802, canonicalSymbol: 'UNXQ', snapshotId: 8801,
      compositionDate: '2026-10-27', knownAt: '2026-10-28T12:00:00Z',
      provenance: 'issuer_current_holdings', sourceProvider: 'fixture-only', holdingRowId: 8803,
      sourceRowId: 'issuer-row-8803', reportedSymbol: 'UNXQ', reportedName: 'Uncached Example Equity', holdingType: 'equity',
    }
    const confirmedIdentity = {
      status: 'resolved',
      instrument: { instrument_id: 8802, symbol: 'UNXQ', identity_status: 'resolved', instrument_type: 'Common Stock' },
    }
    routeState.path = '/chart/UNXQ'
    routeState.params = { symbol: 'UNXQ' }
    routeState.query = { ...holdingDrilldownRouteQuery(context), holding_history_intent: 'selected' }
    harness.workspace = reactive(harness.workspace)
    harness.workspace.linkedSymbol = 'SPY'
    harness.workspace.publishSymbol.mockImplementation((event: any) => {
      harness.workspace.linkedSymbol = event.symbol
    })
    harness.workspace.setConstituentETF.mockImplementation((symbol: string | null) => {
      harness.workspace.constituentETF = symbol
    })
    let finishWorkspaceLoad!: () => void
    harness.workspace.loadDefault.mockReturnValueOnce(new Promise<void>(resolve => { finishWorkspaceLoad = resolve }))
    const historyState = { ...(window.history.state ?? {}), ...holdingDrilldownRouteState(context, confirmedIdentity as any) }
    window.history.replaceState(historyState, '', window.location.href)
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })

    try {
      await vi.waitFor(() => expect(harness.workspace.loadDefault).toHaveBeenCalled())
      harness.workspace.linkedSymbol = 'UNXQ'
      await nextTick()
      expect(routerReplace).not.toHaveBeenCalledWith(expect.objectContaining({ path: '/chart/UNXQ' }))
      expect(routeState.query).toMatchObject({ ...holdingDrilldownRouteQuery(context), holding_history_intent: 'selected' })

      finishWorkspaceLoad()
      await vi.waitFor(() => expect(wrapper.get('[data-testid="active-holding-lineage"]').text()).toBe('UNXQ from IWM holdings · 2026-10-27'))
      expect(routeState.query).toMatchObject({ ...holdingDrilldownRouteQuery(context), holding_history_intent: 'selected' })
      expect(harness.workspace.setConstituentETF).toHaveBeenCalledWith('IWM')

      routerReplace.mockClear()
      harness.workspace.linkedSymbol = 'SPY'
      await nextTick()
      expect(routerReplace).toHaveBeenCalledWith(expect.objectContaining({ path: '/chart/SPY' }))
      expect(Object.keys(routerReplace.mock.calls[0]![0].query).some(key => key.startsWith('holding_'))).toBe(false)
    } finally {
      wrapper.unmount()
      const nextState = { ...(window.history.state ?? {}) }
      delete nextState.tcHoldingSelectionHandoff
      delete nextState.tcHoldingIdentityHandoff
      window.history.replaceState(nextState, '', window.location.href)
    }
  })

  it('keeps private basket selection on its supported dashboard route without ticker identity or profile requests', async () => {
    routeState.path = '/chart/SPY'
    routeState.params = { symbol: 'SPY' }
    routeState.query = { holding_snapshot_id: '77', holding_row_id: '9' }
    harness.workspace = reactive(harness.workspace)
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await vi.waitFor(() => expect(harness.chart.loadBars).toHaveBeenCalledWith('SPY', 'D1', 'candles', true))
      harness.workspace.linkedSymbol = 'BASKET:8'
      await vi.waitFor(() => expect(harness.chart.loadBars).toHaveBeenCalledWith('BASKET:8', 'D1', 'candles', true))
      await vi.waitFor(() => expect(routerReplace).toHaveBeenCalledWith(expect.objectContaining({ path: '/chart/BASKET%3A8' })))
      expect(Object.keys(routerReplace.mock.calls.at(-1)?.[0].query ?? {}).some(key => key.startsWith('holding_'))).toBe(false)
      expect(resolveKnownInstrument).not.toHaveBeenCalledWith('BASKET:8', expect.anything(), expect.anything())
      expect(apiGet).not.toHaveBeenCalledWith('/instruments/BASKET:8', expect.anything())
      expect(harness.workspace.loadTechnical).not.toHaveBeenCalledWith('BASKET:8')
      expect(harness.workspace.loadETFHoldings).not.toHaveBeenCalledWith('BASKET:8')
      expect(harness.workspace.loadETFIndustries).not.toHaveBeenCalledWith('BASKET:8')
      expect(dataPreparationPost.mock.calls.some(([request]) => request.target?.kind === 'instrument'
        && request.target.symbol === 'BASKET:8')).toBe(false)
      expect(harness.recent.add).not.toHaveBeenCalledWith('BASKET:8', expect.anything(), expect.anything())
    } finally {
      wrapper.unmount()
    }
  })

  it('consumes a verified selected-holding route on the dashboard and fences its late history response', async () => {
    const context = {
      etfSymbol: 'IWM',
      instrumentId: 8802,
      canonicalSymbol: 'UNXQ',
      snapshotId: 8801,
      compositionDate: '2026-10-27',
      knownAt: '2026-10-28T12:00:00Z',
      provenance: 'issuer_current_holdings',
      sourceProvider: 'fixture-only',
      holdingRowId: 8803,
      sourceRowId: 'issuer-row-8803',
      reportedSymbol: 'UNXQ',
      reportedName: 'Uncached Example Equity',
      holdingType: 'equity',
    }
    const confirmedIdentity = {
      request_id: 'resolved-unxq',
      status: 'resolved',
      instrument: { instrument_id: 8802, symbol: 'UNXQ', identity_status: 'verified', instrument_type: 'Equity' },
      source_outcomes: [],
    }
    const previousHistoryState = window.history.state
    routeState.path = '/chart/UNXQ'
    routeState.params = { symbol: 'UNXQ' }
    routeState.query = { ...holdingDrilldownRouteQuery(context), holding_history_intent: 'selected' }
    window.history.replaceState({
      ...(previousHistoryState && typeof previousHistoryState === 'object' ? previousHistoryState : {}),
      tcHoldingSelectionHandoff: JSON.stringify(context),
      tcHoldingIdentityHandoff: JSON.stringify(confirmedIdentity),
    }, '', window.location.href)
    let resolveOriginalPreparation!: (value: any) => void
    dataPreparationPost.mockImplementationOnce(() => new Promise(resolve => { resolveOriginalPreparation = resolve }))
    dataPreparationPost.mockImplementation(async (request: any) => readyPreparationResponse(request, dataPreparationPost.mock.calls.length))
    harness.workspace.publishSymbol.mockImplementation((event: any) => { harness.workspace.linkedSymbol = event.symbol })
    harness.workspace.setConstituentETF.mockImplementation((symbol: string | null) => { harness.workspace.constituentETF = symbol })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await vi.waitFor(() => expect(dataPreparationPost).toHaveBeenCalledTimes(1))
      expect(harness.workspace.setConstituentETF).toHaveBeenCalledWith('IWM')
      expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'UNXQ', instrumentId: 8802 }))
      expect(dataPreparationPost.mock.calls[0]?.[0]).toMatchObject({ target: { kind: 'instrument', instrument_id: 8802 } })
      expect(resolveKnownInstrument).not.toHaveBeenCalledWith('UNXQ', expect.anything(), expect.anything())
      expect(window.history.state.tcHoldingSelectionHandoff).toBeUndefined()
      expect(window.history.state.tcHoldingIdentityHandoff).toBeUndefined()

      const input = wrapper.get('input[aria-label="Active symbol"]')
      await input.setValue('QQQ')
      await wrapper.findAll('button').find(button => button.text() === 'Go')!.trigger('click')
      await vi.waitFor(() => expect(dataPreparationPost).toHaveBeenCalledTimes(2))
      expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'QQQ' }))

      resolveOriginalPreparation(readyPreparationResponse(dataPreparationPost.mock.calls[0]![0], 1))
      await flushPromises()
      expect(wrapper.find('[data-testid="active-holding-lineage"]').exists()).toBe(false)
      expect(wrapper.text()).not.toContain('History for UNXQ')
      expect(harness.workspace.constituentETF).toBeNull()
    } finally {
      wrapper.unmount()
      const nextState = { ...(window.history.state ?? {}) }
      delete nextState.tcHoldingSelectionHandoff
      delete nextState.tcHoldingIdentityHandoff
      window.history.replaceState(nextState, '', window.location.href)
    }
  })

  it('does not trust a replayed dated holding URL as membership or instrument identity', async () => {
    const context = {
      etfSymbol: 'IWM',
      instrumentId: 8802,
      canonicalSymbol: 'UNXQ',
      snapshotId: 8801,
      compositionDate: '2026-10-27',
      knownAt: '2026-10-28T12:00:00Z',
      provenance: 'issuer_current_holdings',
      sourceProvider: 'fixture-only',
      holdingRowId: 8803,
      sourceRowId: 'issuer-row-8803',
      reportedSymbol: 'UNXQ',
      reportedName: 'Uncached Example Equity',
      holdingType: 'equity',
    }
    routeState.path = '/chart/UNXQ'
    routeState.params = { symbol: 'UNXQ' }
    routeState.query = { ...holdingDrilldownRouteQuery(context), holding_history_intent: 'selected' }
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'UNXQ' })))
      await vi.waitFor(() => expect(dataPreparationPost).toHaveBeenCalledTimes(1))
      expect(resolveKnownInstrument).toHaveBeenCalledWith('UNXQ', 'Workstation symbol', expect.objectContaining({ canonicalOnly: true, priority: 'high', signal: expect.any(AbortSignal) }))
      expect(dataPreparationPost.mock.calls[0]?.[0]).toMatchObject({ target: { kind: 'instrument', instrument_id: 77 } })
      expect(dataPreparationPost.mock.calls[0]?.[0].target).not.toMatchObject({ instrument_id: 8802 })
      expect(harness.workspace.setConstituentETF).not.toHaveBeenCalledWith('IWM')
      expect(wrapper.find('[data-testid="active-holding-lineage"]').exists()).toBe(false)
    } finally {
      wrapper.unmount()
    }
  })

  it('restores dated holding details only after canonical identity independently matches', async () => {
    const context = {
      etfSymbol: 'IWM',
      instrumentId: 8802,
      canonicalSymbol: 'UNXQ',
      snapshotId: 8801,
      compositionDate: '2026-10-27',
      knownAt: '2026-10-28T12:00:00Z',
      provenance: 'issuer_current_holdings',
      sourceProvider: 'fixture-only',
      holdingRowId: 8803,
      sourceRowId: 'issuer-row-8803',
      reportedSymbol: 'UNXQ',
      reportedName: 'Uncached Example Equity',
      holdingType: 'equity',
    }
    routeState.path = '/chart/UNXQ'
    routeState.params = { symbol: 'UNXQ' }
    routeState.query = { ...holdingDrilldownRouteQuery(context), holding_history_intent: 'selected' }
    vi.mocked(resolveKnownInstrument).mockResolvedValueOnce({ symbol: 'UNXQ', id: 8802 })
    harness.workspace.publishSymbol.mockImplementation((event: any) => { harness.workspace.linkedSymbol = event.symbol })

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await vi.waitFor(() => expect(dataPreparationPost).toHaveBeenCalledTimes(1))
    expect(resolveKnownInstrument).toHaveBeenCalledWith('UNXQ', 'Workstation symbol', expect.objectContaining({ canonicalOnly: true, priority: 'high', signal: expect.any(AbortSignal) }))
      expect(dataPreparationPost.mock.calls[0]?.[0]).toMatchObject({ target: { kind: 'instrument', instrument_id: 8802 } })
      expect(harness.workspace.setConstituentETF).not.toHaveBeenCalledWith('IWM')
      expect(wrapper.get('[data-testid="active-holding-lineage"]').text()).toBe('UNXQ from IWM dated holdings · 2026-10-27')
      expect(wrapper.get('[data-testid="active-holding-lineage"]').attributes('title')).toContain('snapshot 8801 · row 8803')
      expect(wrapper.get('[data-testid="active-holding-lineage"]').attributes('title')).toContain('issuer-row-8803')
      expect(wrapper.get('[data-testid="active-holding-lineage"]').attributes('title')).toContain('does not establish current ETF analysis eligibility')
    } finally {
      wrapper.unmount()
    }
  })

  it('hydrates local ETF data and starts shared preparation on a fresh plain-chart mount', async () => {
    routeState.path = '/chart'
    routeState.params = {}
    harness.workspace.constituentETF = null

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await vi.waitFor(() => expect(harness.workspace.loadETFHoldings).toHaveBeenCalledWith('SPY', 'high'))
      expect(harness.workspace.loadETFIndustries).toHaveBeenCalledWith('SPY', 'high')
      await vi.waitFor(() => expect(dataPreparationPost).toHaveBeenCalledTimes(1))
      expect(dataPreparationPost.mock.calls[0]?.[0]).toMatchObject({ target: { kind: 'instrument', symbol: 'SPY' } })
      expect(apiPost).not.toHaveBeenCalled()
      expect(harness.workspace.setConstituentETF).toHaveBeenCalledWith(null)
    } finally {
      wrapper.unmount()
    }
  })

  it('describes usable partial price history independently from pending instrument metadata', async () => {
    routeState.path = '/chart/BWET'
    routeState.params = { symbol: 'BWET' }
    dataPreparationPost.mockImplementation(async (request: any) => {
      const progress = readyPreparationResponse(request, dataPreparationPost.mock.calls.length)
      if (!request.datasets?.includes('history')) return progress
      progress.status = 'partial'
      progress.completed = 1
      progress.total = 3
      progress.has_pending_work = true
      const retryAt = '2026-11-06T12:05:00Z'
      const identity = progress.dependencies.find((dependency: any) => dependency.dataset === 'identity')
      const profile = progress.dependencies.find((dependency: any) => dependency.dataset === 'profile')
      const history = progress.dependencies.find((dependency: any) => dependency.dataset === 'history')
      for (const dependency of [identity, profile]) {
        dependency.status = 'waiting'
        dependency.reason_code = 'provider_capacity_deferred'
        dependency.retry_at = retryAt
      }
      history.status = 'partial'
      history.reason_code = 'history_coverage_partial'
      return progress
    })

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await flushPromises()
      expect(wrapper.text()).toContain('Partial D1 price history for BWET remains available.')
      expect(wrapper.text()).toContain('Instrument identity and profile details are still being checked.')
      expect(wrapper.text()).not.toContain('Preparing the admitted D1 history for BWET (1/3)')
    } finally {
      wrapper.unmount()
    }
  })

  it('uses the selected holdings dependency reason when aggregate preparation is partial', async () => {
    routeState.path = '/chart/BWET'
    routeState.params = { symbol: 'BWET' }
    let aggregateIncludedReadyHistory = false
    apiGet.mockImplementation(async (path: string) => {
      if (path === '/instruments/search') return [{ symbol: 'BWET', type: 'ETF', instrument_id: 77 }]
      return []
    })
    dataPreparationPost.mockImplementation(async (request: any) => {
      const progress = readyPreparationResponse(request, dataPreparationPost.mock.calls.length)
      if (request.datasets?.includes('holdings')) {
        const now = '2026-11-06T12:00:00Z'
        const id = request.target.instrument_id
        const coveredRange = [{ start_at: '2025-01-01T00:00:00Z', end_at: now,
          data_source_id: 4, market_series_id: 9, adjustment_basis: 'split_dividend', adjustment_version: 'v1', is_adjusted: true }]
        progress.status = 'partial'
        progress.completed = 3
        progress.total = 4
        progress.has_pending_work = false
        progress.dependencies = [
          { dependency_id: `identity:${id}`, depends_on: [], instrument_id: id, symbol: 'BWET', dataset: 'identity', status: 'ready', requested_start: null, requested_end: null, covered_start: null, covered_end: null, reason_code: null, retry_at: null, updated_at: now, covered_ranges: [] },
          { dependency_id: `profile:${id}`, depends_on: [`identity:${id}`], instrument_id: id, symbol: 'BWET', dataset: 'profile', status: 'ready', requested_start: null, requested_end: null, covered_start: null, covered_end: null, reason_code: null, retry_at: null, updated_at: now, covered_ranges: [] },
          { dependency_id: `history:${id}:D1`, depends_on: [`identity:${id}`], instrument_id: id, symbol: 'BWET', dataset: 'history', status: 'ready', requested_start: null, requested_end: null, covered_start: '2025-01-01T00:00:00Z', covered_end: now, reason_code: null, retry_at: null, updated_at: now, covered_ranges: coveredRange },
          { dependency_id: `holdings:${id}`, depends_on: [`identity:${id}`], instrument_id: id, symbol: 'BWET', dataset: 'holdings', status: 'failed', requested_start: null, requested_end: null, covered_start: null, covered_end: null, reason_code: 'future_dated_source', retry_at: null, updated_at: now, covered_ranges: [] },
        ]
        aggregateIncludedReadyHistory = progress.dependencies.some((dependency: any) => dependency.dataset === 'history' && dependency.status === 'ready')
      }
      return progress
    })

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await vi.waitFor(() => expect(wrapper.text()).toContain('Current holdings are unavailable because the latest source snapshot is dated in the future.'))
      await vi.waitFor(() => expect(harness.chart.loadBars).toHaveBeenCalledWith('BWET', 'D1', 'candles', true))
      expect(aggregateIncludedReadyHistory).toBe(true)
      expect(wrapper.text()).not.toContain('Some requested data is unavailable.')
      expect(wrapper.text()).not.toContain('future_dated_source')
      expect(dataPreparationPost).toHaveBeenCalledWith(expect.objectContaining({
        target: { kind: 'instrument', instrument_id: 77 }, datasets: ['holdings'],
      }), expect.anything())
    } finally {
      wrapper.unmount()
    }
  })

  it('starts selected ETF holdings preparation while independent local chart and technical reads are still pending', async () => {
    routeState.path = '/chart/BWET'
    routeState.params = { symbol: 'BWET' }
    apiGet.mockImplementation(async (path: string) => {
      if (path === '/instruments/search') return [{ symbol: 'BWET', type: 'ETF', instrument_id: 77 }]
      return []
    })
    let finishChart!: () => void
    let finishTechnical!: () => void
    const chartPending = new Promise<void>(resolve => { finishChart = resolve })
    const technicalPending = new Promise<void>(resolve => { finishTechnical = resolve })
    let chartSettled = false
    let technicalSettled = false
    harness.chart.loadBars.mockImplementation(async (symbol: string) => {
      harness.chart.symbol = symbol
      await chartPending
      chartSettled = true
    })
    harness.workspace.loadTechnical = vi.fn(async () => {
      await technicalPending
      technicalSettled = true
    })

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await vi.waitFor(() => expect(dataPreparationPost.mock.calls.some(([request]) =>
        request.target?.kind === 'instrument' && request.target.instrument_id === 77 && request.datasets?.includes('holdings'),
      )).toBe(true))
      const holdingsEnsure = dataPreparationPost.mock.calls.find(([request]) => request.datasets?.includes('holdings'))
      expect(holdingsEnsure?.[0]).toMatchObject({ target: { kind: 'instrument', instrument_id: 77 }, datasets: ['holdings'] })
      expect(holdingsEnsure?.[1]).toMatchObject({ priority: 'high' })
      expect(chartSettled).toBe(false)
      expect(technicalSettled).toBe(false)

      finishChart()
      finishTechnical()
      await flushPromises()
    } finally {
      wrapper.unmount()
    }
  })

  it('publishes current saved ETF holdings while chart and technical hydration remain pending', async () => {
    routeState.path = '/chart/BWET'
    routeState.params = { symbol: 'BWET' }
    apiGet.mockImplementation(async (path: string) => {
      if (path === '/instruments/search') return [{ symbol: 'BWET', type: 'ETF', instrument_id: 77 }]
      if (path === '/etf-holdings/BWET/capability') {
        return { availability: 'current', identity_verified: true, usable_for_current_analysis: true }
      }
      return []
    })
    let finishChart!: () => void
    let finishTechnical!: () => void
    let finishHoldings!: () => void
    const chartPending = new Promise<void>(resolve => { finishChart = resolve })
    const technicalPending = new Promise<void>(resolve => { finishTechnical = resolve })
    const holdingsPending = new Promise<void>(resolve => { finishHoldings = resolve })
    let chartSettled = false
    let technicalSettled = false
    harness.chart.loadBars.mockImplementation(async (symbol: string) => {
      harness.chart.symbol = symbol
      await chartPending
      chartSettled = true
    })
    harness.workspace.loadTechnical = vi.fn(async () => {
      await technicalPending
      technicalSettled = true
    })
    harness.workspace.loadETFHoldings = vi.fn(async (symbol: string) => {
      await holdingsPending
      harness.workspace.etfHoldings[symbol] = { snapshot: { id: 700, etf_symbol: symbol } }
      return { snapshot: { id: 700, etf_symbol: symbol } }
    })

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith(
        '/etf-holdings/BWET/capability', undefined, expect.objectContaining({ priority: 'high', signal: expect.any(AbortSignal) }),
      ))
      expect(harness.workspace.loadETFHoldings).toHaveBeenCalledWith('BWET', 'high')
      finishHoldings()
      await vi.waitFor(() => expect(wrapper.text()).toContain('Current holdings for BWET are available locally.'))
      expect(chartSettled).toBe(false)
      expect(technicalSettled).toBe(false)
      expect(dataPreparationPost.mock.calls.some(([request]) => request.datasets?.includes('holdings'))).toBe(false)

      finishChart()
      finishTechnical()
      await flushPromises()
    } finally {
      wrapper.unmount()
    }
  })

  it('shows newly prepared history on a cold canonical chart without another click or reload', async () => {
    routeState.path = '/chart/NVDA'
    routeState.params = { symbol: 'NVDA' }
    vi.mocked(resolveKnownInstrument).mockResolvedValueOnce({ symbol: 'NVDA', id: 77001 })
    harness.chart.bars = []
    harness.chart.refreshLocalBars.mockImplementation(async () => {
      harness.chart.bars = [{ time: '2026-11-06', open: 100, high: 102, low: 99, close: 101, volume: 10 }]
    })
    dataPreparationPost.mockImplementationOnce(async (request: any) => {
      const partial = readyPreparationResponse(request, 1)
      partial.status = 'partial'
      partial.version = 1
      partial.has_pending_work = true
      partial.completed = 1
      partial.total = 3
      partial.dependencies.find((dependency: any) => dependency.dataset === 'profile')!.status = 'queued'
      partial.dependencies.find((dependency: any) => dependency.dataset === 'history')!.status = 'partial'
      return partial
    })
    apiGet.mockImplementation(async (path: string) => {
      if (!path.startsWith('/data/requests/')) return []
      const request = dataPreparationPost.mock.calls[0]?.[0]
      const complete = readyPreparationResponse(request, 1)
      complete.version = 2
      return complete
    })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await vi.waitFor(() => expect(dataPreparationPost).toHaveBeenCalledTimes(1))
      const request = dataPreparationPost.mock.calls[0]?.[0]
      expect(request).toMatchObject({ target: { kind: 'instrument', instrument_id: 77001 } })
      expect(request).not.toHaveProperty('start_at')
      expect(request).not.toHaveProperty('end_at')
      expect(dataPreparationPost.mock.calls[0]?.[1]).toMatchObject({ priority: 'high' })
      await vi.waitFor(() => expect(harness.chart.refreshLocalBars).toHaveBeenCalled())
      expect(harness.chart.bars).toHaveLength(1)
      expect(harness.chart.bars[0]).toMatchObject({ close: 101 })
      expect((wrapper.get('input[aria-label="Active symbol"]').element as HTMLInputElement).value).toBe('NVDA')
      expect(resolveKnownInstrument).toHaveBeenCalledWith('NVDA', 'Workstation symbol', expect.objectContaining({ canonicalOnly: true, priority: 'high', signal: expect.any(AbortSignal) }))
    } finally {
      wrapper.unmount()
    }
  })

  it('renders an initially empty deep-linked chart from preparation progress without another interaction', async () => {
    routeState.path = '/chart/NVDA'
    routeState.params = { symbol: 'NVDA' }
    // Keep this request key distinct from the preceding cold-chart case. The
    // shared coordinator intentionally coalesces a still-settling request
    // across a rapid unmount/remount of the same instrument.
    vi.mocked(resolveKnownInstrument).mockResolvedValueOnce({ symbol: 'NVDA', id: 77002 })
    harness.chart.bars = []
    harness.chart.refreshLocalBars.mockImplementation(async () => {
      harness.chart.bars = [{ time: '2026-11-06', open: 100, high: 102, low: 99, close: 101, volume: 10 }]
    })
    dataPreparationPost.mockImplementationOnce(async (request: any) => {
      const partial = readyPreparationResponse(request, 1)
      partial.status = 'partial'
      partial.version = 1
      partial.has_pending_work = true
      partial.completed = 1
      partial.total = 3
      partial.dependencies.find((dependency: any) => dependency.dataset === 'profile')!.status = 'queued'
      partial.dependencies.find((dependency: any) => dependency.dataset === 'history')!.status = 'partial'
      return partial
    })
    apiGet.mockImplementation(async (path: string) => {
      if (!path.startsWith('/data/requests/')) return []
      const request = dataPreparationPost.mock.calls[0]?.[0]
      return readyPreparationResponse(request, 2)
    })
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await vi.waitFor(() => expect(dataPreparationPost).toHaveBeenCalledTimes(1))
      expect(dataPreparationPost.mock.calls[0]?.[0]).toMatchObject({ target: { kind: 'instrument', instrument_id: 77002 } })
      expect(dataPreparationPost.mock.calls[0]?.[0]).not.toHaveProperty('start_at')
      expect(dataPreparationPost.mock.calls[0]?.[0]).not.toHaveProperty('end_at')
      await vi.waitFor(() => expect(harness.chart.refreshLocalBars).toHaveBeenCalled())
      expect(harness.chart.bars).toHaveLength(1)
      expect(harness.chart.bars[0]).toMatchObject({ close: 101 })
      expect((wrapper.get('input[aria-label="Active symbol"]').element as HTMLInputElement).value).toBe('NVDA')
    } finally {
      wrapper.unmount()
    }
  })

  it('keeps a real parent ETF bound during a plain-chart restore', async () => {
    routeState.path = '/chart'
    routeState.params = {}
    harness.workspace.constituentETF = 'XLK'

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await vi.waitFor(() => expect(harness.chart.loadBars).toHaveBeenCalledWith('SPY', 'D1', 'candles', true))
      expect(harness.workspace.constituentETF).toBe('XLK')
      expect(harness.workspace.loadETFHoldings).not.toHaveBeenCalledWith('SPY')
      expect(harness.workspace.loadETFIndustries).not.toHaveBeenCalledWith('SPY')
      expect(harness.workspace.setConstituentETF).not.toHaveBeenCalled()
      expect(apiPost).not.toHaveBeenCalled()
    } finally {
      wrapper.unmount()
    }
  })

  it('closes autocomplete for Escape and the explicit Go action while the input stays focused', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockResolvedValue([{ symbol: 'XLK', name: 'Technology Select Sector SPDR Fund', exchange: 'ARCX', type: 'ETF' }])
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
    const input = wrapper.get('input[aria-label="Active symbol"]')
    await input.setValue('xlk')
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/instruments/search', { q: 'xlk', canonical_only: true }, { priority: 'high' }))
    await vi.waitFor(() => expect(wrapper.find('[role="listbox"]').exists()).toBe(true))
    await input.trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false)

    await input.setValue('xl')
    await vi.waitFor(() => expect(wrapper.find('[role="listbox"]').exists()).toBe(true))
    await wrapper.get('.workstation__search > button').trigger('click')
    await vi.waitFor(() => expect(wrapper.find('[role="listbox"]').exists()).toBe(false))
    await flushPromises()
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('opens recent symbols, selects one, and dismisses the history menu', async () => {
    routeState.path = '/'
    routeState.params = {}
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const historyButton = wrapper.get('button[aria-label="Recent symbols"]')
    expect(await historyButton.attributes('aria-haspopup')).toBe('menu')
    await historyButton.trigger('click')
    const history = wrapper.get('.workstation__recent-symbols')
    expect(history.attributes('role')).toBe('menu')
    expect(history.findAll('button[role="menuitem"]').find(button => button.text().includes('XLK'))).toBeTruthy()
    expect(await historyButton.attributes('aria-expanded')).toBe('true')

    await history.findAll('button[role="menuitem"]').find(button => button.text().includes('XLK'))!.trigger('click')
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'XLK', group: 'blue' })))
    expect(wrapper.find('.workstation__recent-symbols').exists()).toBe(false)
    expect(await historyButton.attributes('aria-expanded')).toBe('false')

    await historyButton.trigger('click')
    await wrapper.trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('.workstation__recent-symbols').exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps a layout rename draft through an unrelated render and commits it before blur', async () => {
    routeState.path = '/chart'
    routeState.params = {}
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await wrapper.get('button[title="Manage workspace layouts"]').trigger('click')
    const renameField = wrapper.findAll('input[aria-label="Rename layout"]').at(-1)!
    ;(renameField.element as HTMLInputElement).value = 'Review Layout'
    await renameField.trigger('input')

    expect(harness.workspace.renameTab).toHaveBeenCalledWith('us-top-down', 'Review Layout')
    await wrapper.vm.$forceUpdate()
    await nextTick()
    expect((renameField.element as HTMLInputElement).value).toBe('Review Layout')
    wrapper.unmount()
  })

  it('closes autocomplete before an outside tool pointer can be intercepted', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockResolvedValue([{ symbol: 'XLK', name: 'Technology Select Sector SPDR Fund', exchange: 'ARCX', type: 'ETF' }])
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
    const input = wrapper.get('input[aria-label="Active symbol"]')
    await input.setValue('xlk')
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/instruments/search', { q: 'xlk', canonical_only: true }, { priority: 'high' }))
    await vi.waitFor(() => expect(wrapper.find('[role="listbox"]').exists()).toBe(true))
    await wrapper.find('.workstation__tabs').trigger('pointerdown')
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('dismisses transient workstation menus on outside pointer and Escape', async () => {
    routeState.path = '/'
    routeState.params = {}
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })

    const workspaceButton = wrapper.get('button[title="Manage workspace layouts"]')
    const toolButton = wrapper.get('.workstation__tool-library > button')
    expect(await workspaceButton.attributes('aria-haspopup')).toBe('menu')
    expect(await toolButton.attributes('aria-haspopup')).toBe('menu')

    await workspaceButton.trigger('click')
    await toolButton.trigger('click')
    expect(wrapper.get('.workstation__tool-library-menu').attributes('role')).toBe('menu')
    expect(wrapper.find('.workstation__workspace-popover').exists()).toBe(false)
    expect(await workspaceButton.attributes('aria-expanded')).toBe('false')
    expect(await toolButton.attributes('aria-expanded')).toBe('true')

    await wrapper.get('button[title="Keyboard shortcuts"]').trigger('click')
    expect(wrapper.find('.workstation__tool-library-menu').exists()).toBe(false)
    expect(wrapper.get('.workstation__help-popover').attributes('role')).toBe('dialog')
    expect(wrapper.get('button[title="Keyboard shortcuts"]').attributes('aria-haspopup')).toBe('dialog')
    expect(wrapper.get('.workstation__help-popover').attributes('aria-labelledby')).toBe('keyboard-help-title')
    expect(wrapper.get('.workstation__help-popover').text()).toContain("/Open the active chart's plot library and search indicators")
    expect(wrapper.get('.workstation__help-popover').text()).toContain('Ctrl+BCycle HLC and OHLC bars, candles, and line style on the active chart')

    await wrapper.find('.workstation__tabs').trigger('pointerdown')
    expect(wrapper.find('.workstation__help-popover').exists()).toBe(false)

    await workspaceButton.trigger('click')
    await toolButton.trigger('click')
    await wrapper.trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('.workstation__workspace-popover').exists()).toBe(false)
    expect(wrapper.find('.workstation__tool-library-menu').exists()).toBe(false)
    expect(await workspaceButton.attributes('aria-expanded')).toBe('false')
    expect(await toolButton.attributes('aria-expanded')).toBe('false')
    wrapper.unmount()
  })

  it('exposes the specialized factory roles in the Add tool catalogue', async () => {
    routeState.path = '/chart'
    routeState.params = {}
    const wrapper = mount(WorkstationView, {
      attachTo: document.body,
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true, 'router-link': NavigationLinkStub } },
    })
    try {
      await wrapper.get('.workstation__tool-library > button').trigger('click')
      const menu = wrapper.get('.workstation__tool-library-menu')
      const labels = menu.findAll('[role="menuitem"]').map(item => item.text().trim())
      expect(labels).toContain('S&P 500 Sectors')
      expect(labels).toContain('Industries')
      expect(labels).toContain('Constituents')
      expect(labels).toContain('Relative Strength')
      expect(labels).toContain('Relative Rotation')
      expect(new Set(labels).size).toBe(labels.length)
    } finally {
      wrapper.unmount()
      wrapper.element.remove()
    }
  })

  it('removes shell geometry listeners when outside pointer or focus closes fixed menus', async () => {
    routeState.path = '/'
    routeState.params = {}
    const addSpy = vi.spyOn(window, 'addEventListener')
    const removeSpy = vi.spyOn(window, 'removeEventListener')
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const workspaceButton = wrapper.get('button[title="Manage workspace layouts"]')
    await workspaceButton.trigger('click')
    expect(addSpy).toHaveBeenCalledWith('scroll', expect.any(Function), true)
    await wrapper.find('.workstation__tabs').trigger('pointerdown')
    expect(removeSpy).toHaveBeenCalledWith('scroll', expect.any(Function), true)
    await workspaceButton.trigger('click')
    await wrapper.find('.workstation__tabs').trigger('focusin')
    expect(removeSpy.mock.calls.filter(([type]) => type === 'scroll').length).toBeGreaterThanOrEqual(2)
    wrapper.unmount()
  })

  it('does not reposition the open tool menu between an interior pointer press and release', async () => {
    routeState.path = '/chart'
    routeState.params = {}
    let triggerLeft = 120
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const trigger = wrapper.get('.workstation__tool-library > button')
    vi.spyOn(trigger.element, 'getBoundingClientRect').mockImplementation(() => ({
      x: triggerLeft,
      y: 32,
      left: triggerLeft,
      top: 32,
      right: triggerLeft + 72,
      bottom: 56,
      width: 72,
      height: 24,
      toJSON: () => ({}),
    }) as DOMRect)

    await trigger.trigger('click')
    await nextTick()
    const menu = wrapper.get('.workstation__tool-library-menu')
    const positionedBeforePress = menu.attributes('style')
    expect(positionedBeforePress).toContain('left: 120px')

    triggerLeft = 420
    const item = menu.get('[role="menuitem"]')
    await item.trigger('pointerdown', { button: 0 })
    await nextTick()

    // A shell-level interior press must not move the fixed hit target before
    // the browser delivers the corresponding pointerup/click.
    expect(menu.attributes('style')).toBe(positionedBeforePress)
    await item.trigger('focusin')
    await nextTick()
    expect(menu.attributes('style')).toBe(positionedBeforePress)
    await item.trigger('pointerup', { button: 0 })

    // Geometry still follows the trigger on actual viewport changes.
    window.dispatchEvent(new Event('resize'))
    await nextTick()
    expect(menu.attributes('style')).toContain('left: 420px')

    await item.trigger('click')
    expect(wrapper.find('.workstation__tool-library-menu').exists()).toBe(false)
    expect(harness.workspace.openTool).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('opens shell menus from the keyboard, navigates items, and restores trigger focus', async () => {
    routeState.path = '/'
    routeState.params = {}
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
      attachTo: document.body,
    })
    const help = wrapper.get('button[title="Keyboard shortcuts"]')
    await help.trigger('keydown', { key: 'ArrowDown' })
    const helpMenu = wrapper.get('.workstation__help-popover')
    await vi.waitFor(() => expect(document.activeElement).toBe(helpMenu.element))
    await helpMenu.trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('.workstation__help-popover').exists()).toBe(false)
    expect(document.activeElement).toBe(help.element)

    const workspace = wrapper.get('button[title="Manage workspace layouts"]')
    await workspace.trigger('keydown', { key: 'ArrowDown' })
    const workspaceMenu = wrapper.get('.workstation__workspace-popover')
    await vi.waitFor(() => expect(document.activeElement).toBe(workspaceMenu.get('[role="listbox"]').element))
    await workspaceMenu.get('[role="listbox"]').trigger('keydown', { key: 'End' })
    expect(document.activeElement).toBe(workspaceMenu.get('[role="listbox"]').element)
    expect(workspaceMenu.get('[role="listbox"]').attributes('aria-activedescendant')).toBe('saved-workspace-1')
    await workspaceMenu.get('[role="listbox"]').trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('.workstation__workspace-popover').exists()).toBe(false)
    expect(document.activeElement).toBe(workspace.element)

    await workspace.trigger('keydown', { key: 'ArrowDown' })
    const reopenedWorkspaceMenu = wrapper.get('.workstation__workspace-popover')
    await vi.waitFor(() => expect(document.activeElement).toBe(reopenedWorkspaceMenu.get('[role="listbox"]').element))
    await reopenedWorkspaceMenu.trigger('keydown', { key: 'End' })
    expect(document.activeElement).toBe(reopenedWorkspaceMenu.findAll('[role="menuitem"]').at(-1)!.element)
    await reopenedWorkspaceMenu.trigger('keydown', { key: 'Escape' })
    expect(document.activeElement).toBe(workspace.element)
    wrapper.unmount()
  })

  it('keeps each shell menu trigger linked to its controlled menu', async () => {
    routeState.path = '/'
    routeState.params = {}
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
      attachTo: document.body,
    })

    const triggers = [
      wrapper.get('button[title="Manage workspace layouts"]'),
      wrapper.get('button[title="Keyboard shortcuts"]'),
      wrapper.get('button[aria-label="Recent symbols"]'),
      wrapper.get('button[title="Open a workstation tool"]'),
    ]
    const menuIds = triggers.map(trigger => trigger.attributes('aria-controls'))

    expect(menuIds.every(Boolean)).toBe(true)
    expect(new Set(menuIds).size).toBe(menuIds.length)
    expect(triggers.every(trigger => trigger.attributes('aria-expanded') === 'false')).toBe(true)

    const menuSelectors = [
      '.workstation__workspace-popover',
      '.workstation__help-popover',
      '.workstation__recent-symbols',
      '.workstation__tool-library-menu',
    ]
    for (let index = 0; index < triggers.length; index += 1) {
      await triggers[index].trigger('click')
      const menu = wrapper.get(menuSelectors[index])
      expect(menu.attributes('id')).toBe(menuIds[index])
      expect(triggers[index].attributes('aria-expanded')).toBe('true')
      await triggers[index].trigger('click')
      expect(wrapper.find(menuSelectors[index]).exists()).toBe(false)
    }

    wrapper.unmount()
  })

  it('opens tools from the authenticated server catalogue while retaining stable semantic keys', async () => {
    routeState.path = '/'
    routeState.params = {}
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await wrapper.get('button[title="Open a workstation tool"]').trigger('click')
    const items = wrapper.findAll('.workstation__tool-library-menu [role="menuitem"]')
    expect(items).toHaveLength(21)
    expect(items.map(item => item.text())).toEqual(openableTools.map(tool => tool.title))
    for (const [index, definition] of openableTools.entries()) {
      if (index > 0) await wrapper.get('.workstation__tool-library > button').trigger('click')
      const item = wrapper.findAll('.workstation__tool-library-menu [role="menuitem"]')
        .find(candidate => candidate.text() === definition.title)
      expect(item, `Add-tool item ${definition.key}`).toBeDefined()
      await item!.trigger('click')
      expect(harness.workspace.openTool).toHaveBeenNthCalledWith(index + 1, definition, {})
    }
    wrapper.unmount()
  })

  it('opens the recent-symbol menu at its last item when ArrowUp is pressed', async () => {
    routeState.path = '/'
    routeState.params = {}
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
      attachTo: document.body,
    })
    const trigger = wrapper.get('button[aria-label="Recent symbols"]')

    await trigger.trigger('keydown', { key: 'ArrowUp' })

    const items = wrapper.findAll('.workstation__recent-symbols [role="menuitem"]')
    expect(items.length).toBeGreaterThan(1)
    await vi.waitFor(() => expect(document.activeElement).toBe(items.at(-1)!.element))
    wrapper.unmount()
  })

  it('supports roving keyboard navigation and activation for workspace tabs', async () => {
    routeState.path = '/'
    routeState.params = {}
    const originalTabs = harness.workspace.workspace.tabs
    const secondTab = {
      stable_key: 'study-lab',
      name: 'Study Lab',
      windows: [harness.chartWindow],
      active_window_key: 'chart-main',
      layout_config: null,
    }
    harness.workspace.workspace.tabs = [originalTabs[0], secondTab]
    harness.workspace.activeTabKey = originalTabs[0].stable_key
    const wrapper = mount(WorkstationView, {
      attachTo: document.body,
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })

    const tabs = wrapper.findAll('.workstation__tabs [role="tab"]')
    expect(tabs).toHaveLength(2)
    expect(await tabs[0].attributes('aria-selected')).toBe('true')
    expect(await tabs[0].attributes('tabindex')).toBe('0')
    expect(await tabs[1].attributes('tabindex')).toBe('-1')

    await tabs[0].trigger('keydown', { key: 'ArrowRight' })
    expect(document.activeElement).toBe(tabs[1].element)
    await tabs[1].trigger('keydown', { key: 'Enter' })
    expect(harness.workspace.activeTabKey).toBe('study-lab')
    expect(harness.workspace.scheduleSnapshot).toHaveBeenCalled()

    await tabs[1].trigger('keydown', { key: 'Home' })
    expect(document.activeElement).toBe(tabs[0].element)
    await tabs[0].trigger('keydown', { key: ' ' })
    expect(harness.workspace.activeTabKey).toBe('us-top-down')
    wrapper.unmount()
    harness.workspace.workspace.tabs = originalTabs
    harness.workspace.activeTabKey = 'us-top-down'
  })

  it('routes Ctrl+wheel over a chart plot to its live timeframe update', async () => {
    routeState.path = '/'
    routeState.params = {}
    harness.chartWindow.configuration = { timeframe: 'D1', timeframe_link_group: 'green' }
    harness.workspace.timeframeLinkGroupForTool.mockReturnValue('green')
    harness.workspace.timeframeForTool.mockReturnValueOnce('D1').mockReturnValueOnce('W1')
    harness.workspace.updateToolTimeframe.mockReturnValue(true)
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
    harness.workspace.publishSymbol.mockClear()

    const plot = appendChartPlotTarget(wrapper.element, 'chart-main')
    const plotWheel = vi.fn()
    plot.addEventListener('wheel', plotWheel)
    const nextEvent = new WheelEvent('wheel', { ctrlKey: true, deltaY: 1, bubbles: true, cancelable: true })
    plot.dispatchEvent(nextEvent)
    expect(nextEvent.defaultPrevented).toBe(true)
    expect(plotWheel).not.toHaveBeenCalled()
    expect(harness.workspace.timeframeForTool).toHaveBeenNthCalledWith(1, 'chart-main')
    expect(harness.workspace.updateToolTimeframe).toHaveBeenNthCalledWith(1, 'chart-main', 'W1')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Control' }))
    const previousEvent = new WheelEvent('wheel', { deltaY: -1, bubbles: true, cancelable: true })
    plot.dispatchEvent(previousEvent)
    expect(harness.workspace.timeframeForTool).toHaveBeenNthCalledWith(2, 'chart-main')
    expect(harness.workspace.updateToolTimeframe).toHaveBeenNthCalledWith(2, 'chart-main', 'D1')
    expect(harness.workspace.publishSymbol).not.toHaveBeenCalled()
    window.dispatchEvent(new KeyboardEvent('keyup', { key: 'Control' }))
    wrapper.unmount()
  })

  it('cycles only the active chart timeframe with equals and minus', async () => {
    routeState.path = '/'
    routeState.params = {}
    harness.workspace.timeframeForTool.mockReturnValueOnce('D1').mockReturnValueOnce('W1')
    harness.workspace.updateToolTimeframe.mockReturnValue(true)
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const chart = appendChartPlotTarget(wrapper.element, 'chart-main')
    chart.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    expect(harness.workspace.setActiveWindow).toHaveBeenCalledWith('chart-main')
    harness.workspace.activeTab.active_window_key = 'chart-main'

    const next = new KeyboardEvent('keydown', { key: '=', bubbles: true, cancelable: true })
    wrapper.element.dispatchEvent(next)
    expect(next.defaultPrevented).toBe(true)
    expect(harness.workspace.updateToolTimeframe).toHaveBeenNthCalledWith(1, 'chart-main', 'W1')

    const previous = new KeyboardEvent('keydown', { key: '-', bubbles: true, cancelable: true })
    wrapper.element.dispatchEvent(previous)
    expect(previous.defaultPrevented).toBe(true)
    expect(harness.workspace.updateToolTimeframe).toHaveBeenNthCalledWith(2, 'chart-main', 'D1')

    for (const key of ['=', '-']) {
      const projectionShortcut = new KeyboardEvent('keydown', { key, shiftKey: true, bubbles: true, cancelable: true })
      wrapper.element.dispatchEvent(projectionShortcut)
      expect(projectionShortcut.defaultPrevented).toBe(false)
    }
    expect(harness.workspace.updateToolTimeframe).toHaveBeenCalledTimes(2)

    harness.workspace.activeTab.active_window_key = 'benchmark-list'
    const watchlistShortcut = new KeyboardEvent('keydown', { key: '=', bubbles: true, cancelable: true })
    wrapper.element.dispatchEvent(watchlistShortcut)
    expect(harness.workspace.updateToolTimeframe).toHaveBeenCalledTimes(2)
    expect(watchlistShortcut.defaultPrevented).toBe(true)

    wrapper.unmount()
    harness.workspace.activeTab.active_window_key = 'benchmark-list'
  })

  it('leaves Ctrl+wheel on non-chart surfaces to their local owner', async () => {
    routeState.path = '/'
    routeState.params = {}
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
    harness.workspace.publishSymbol.mockClear()

    const toolWindow = document.createElement('section')
    toolWindow.className = 'tool-window'
    toolWindow.dataset.windowKey = 'benchmark-list'
    const watchlistScroll = document.createElement('div')
    watchlistScroll.className = 'watchlist__scroll'
    toolWindow.append(watchlistScroll)
    wrapper.element.append(toolWindow)
    const localWheel = vi.fn()
    watchlistScroll.addEventListener('wheel', localWheel)
    const event = new WheelEvent('wheel', { ctrlKey: true, deltaY: 1, bubbles: true, cancelable: true })
    watchlistScroll.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(false)
    expect(localWheel).toHaveBeenCalledOnce()
    expect(harness.workspace.updateToolTimeframe).not.toHaveBeenCalled()
    expect(harness.workspace.publishSymbol).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('coordinates top-down refresh through Vue Query and resumes it after visibility returns', async () => {
    routeState.path = '/'
    routeState.params = {}
    let finishInitialRefresh!: () => void
    harness.workspace.refreshMarketAnalysis.mockImplementation(() => new Promise<void>(resolve => {
      finishInitialRefresh = resolve
    }))
    const cachedBar = { time: '2026-11-06', open: 100, high: 102, low: 99, close: 101, volume: 10 }
    harness.chart.bars = [cachedBar]
    const originalVisibility = document.visibilityState
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.refreshMarketAnalysis).toHaveBeenCalled())
    await vi.waitFor(() => expect(harness.chart.loadBars).toHaveBeenCalledWith('SPY', 'D1', 'candles', true))
    expect(harness.workspace.refreshMarketAnalysis).toHaveBeenCalledTimes(1)
    expect(harness.chart.bars).toEqual([cachedBar])
    finishInitialRefresh()
    await flushPromises()
    harness.workspace.refreshMarketAnalysis.mockClear()

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    document.dispatchEvent(new Event('visibilitychange'))
    await Promise.resolve()
    expect(harness.workspace.refreshMarketAnalysis).not.toHaveBeenCalled()

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.waitFor(() => expect(harness.workspace.refreshMarketAnalysis).toHaveBeenCalledTimes(1))

    wrapper.unmount()
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: originalVisibility })
  })

  it('keeps a deep-linked cached chart usable when optional market analysis fails', async () => {
    routeState.path = '/chart/NVDA'
    routeState.params = { symbol: 'NVDA' }
    vi.mocked(resolveKnownInstrument).mockResolvedValueOnce({ symbol: 'NVDA', id: 77001 })
    const cachedBar = { time: '2026-11-06', open: 100, high: 102, low: 99, close: 101, volume: 10 }
    harness.chart.bars = [cachedBar]
    harness.workspace.refreshMarketAnalysis.mockRejectedValue(new Error('Optional market analysis failed'))

    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    try {
      await vi.waitFor(() => expect(harness.chart.loadBars).toHaveBeenCalledWith('NVDA', 'D1', 'candles', true))
      await vi.waitFor(() => expect(dataPreparationPost).toHaveBeenCalled())
      expect(harness.chart.bars).toEqual([cachedBar])
      expect((wrapper.get('input[aria-label="Active symbol"]').element as HTMLInputElement).value).toBe('NVDA')
    } finally {
      wrapper.unmount()
    }
  })

  it.each([
    ['401', 'Session or permission required'],
    ['403', 'Session or permission required'],
    ['404', 'Some market data is unavailable'],
    ['409', 'Workspace changed elsewhere; recovery is available'],
    ['503', 'Market service unavailable; cached data retained'],
  ])('maps transport status %s to concise footer copy', async (statusCode, expected) => {
    routeState.path = '/'
    routeState.params = {}
    harness.workspace.error = `API GET /market-groups/etf/SPY/industries → ${statusCode}: unavailable`
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })

    const status = wrapper.find('.workstation__footer span:nth-child(3)')
    expect(status.text()).toBe(expected)
    expect(status.attributes('role')).toBe('status')
    expect(status.attributes('aria-live')).toBe('polite')
    expect(status.attributes('aria-atomic')).toBe('true')
    expect(status.attributes('title')).toContain('API GET /market-groups/etf/SPY/industries')
    harness.workspace.error = null
  })

  it('does not show a prior ETF current-analysis failure in the next fund context', async () => {
    routeState.path = '/'
    routeState.params = {}
    harness.workspace.constituentETF = 'IGV'
    harness.workspace.etfConstituentSnapshotErrors = {
      IGV: 'Current constituent analysis for IGV is unavailable because its holdings are not current.',
      USMV: null,
    }
    const igvWrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const igvStatus = igvWrapper.find('.workstation__footer span:nth-child(3)')
    expect(igvStatus.text()).toBe('Current constituent analysis for IGV is unavailable because its holdings are not current.')
    expect(igvStatus.attributes('title')).toContain('IGV')
    igvWrapper.unmount()

    harness.workspace.constituentETF = 'USMV'
    const usmvWrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const status = usmvWrapper.find('.workstation__footer span:nth-child(3)')
    expect(status.text()).toBe('Ready')
    expect(status.attributes('title')).toBeUndefined()
    usmvWrapper.unmount()
  })
})
