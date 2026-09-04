import { defineComponent } from 'vue'
import { mount as rawMount, type MountingOptions } from '@vue/test-utils'
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
    constituentETF: null,
    marketGroups: { 'us-benchmarks': { members: [] }, 'sp500-sectors': { members: [] } },
    groupSnapshots: {},
    breadth: {},
    breadthHistory: {},
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
    loadETFIndustries: vi.fn().mockResolvedValue(undefined),
    loadTechnical: vi.fn().mockResolvedValue(undefined),
    scheduleSnapshot: vi.fn(),
    setActiveWindow: vi.fn(),
    updateToolLinkGroup: vi.fn(),
    updateToolTimeframe: vi.fn(),
    updateToolTimeframeLinkGroup: vi.fn(),
    selectIndustryProxy: vi.fn(),
    selectIndustry: vi.fn(),
    closeTool: vi.fn(),
    cloneActiveTab: vi.fn(),
    resetFactoryWorkspace: vi.fn(),
    openTool: vi.fn(),
    isEditorTarget: vi.fn(() => false),
  }
  const recent = {
    recent: [{ symbol: 'XLK', name: 'Technology Select Sector SPDR Fund', viewedAt: 2 }],
    add: vi.fn(),
    clear: vi.fn(),
  }
  return { workspace, recent, popoutWindow, chartWindow, ratioWindow }
})
const routeState = vi.hoisted(() => ({ path: '/popout/benchmark-list', params: { windowKey: 'benchmark-list' }, query: {} as Record<string, string> }))
const apiGet = vi.hoisted(() => vi.fn().mockResolvedValue([]))

vi.mock('@/stores/workspace', () => ({
  OPENABLE_WORKSTATION_TOOLS: [],
  useWorkspaceStore: () => harness.workspace,
}))
vi.mock('@/stores/chart', () => ({
  useChartStore: () => ({ symbol: 'SPY', timeframe: 'D1', barType: 'candles', bars: [], isLoading: false, isFetchingHistory: false, error: null, loadBars: vi.fn().mockResolvedValue(undefined) }),
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ logout: vi.fn().mockResolvedValue(undefined) }) }))
vi.mock('@/stores/watchlist', () => ({ useWatchlistStore: () => ({ reorderItems: vi.fn().mockResolvedValue(undefined) }) }))
vi.mock('@/stores/recentInstruments', () => ({ useRecentInstrumentsStore: () => harness.recent }))
vi.mock('@/lib/instruments', () => ({
  ensureKnownInstrumentSymbol: vi.fn((symbol: string) => Promise.resolve(symbol)),
  resolveKnownInstrument: vi.fn((symbol: string) => Promise.resolve({ symbol, id: 77 })),
}))
vi.mock('@/lib/api', () => ({ api: { get: apiGet } }))
vi.mock('@/components/workstation/WorkspaceLayoutHost.vue', () => ({ default: defineComponent({ template: '<div />' }) }))
vi.mock('golden-layout', () => ({}))
vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({ resolve: vi.fn(), push: vi.fn() }),
}))

import WorkstationView from '@/views/WorkstationView.vue'

function mount(component: typeof WorkstationView, options: MountingOptions<typeof WorkstationView> = {}) {
  return rawMount(component, {
    ...options,
    global: {
      ...options.global,
      plugins: [
        ...(options.global?.plugins ?? []),
        [VueQueryPlugin, { queryClient: new QueryClient() }],
      ],
    },
  })
}

const ToolStub = defineComponent({
  emits: ['conditionFilterMode', 'pinnedBooleanKeys', 'columnGroups', 'stackedColumnKeys', 'configuration', 'selectProxy', 'selectIndustry', 'compare', 'ratio', 'row-action'],
  template: `<div class="tool-stub">
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
    harness.popoutWindow.configuration = {}
    harness.chartWindow.configuration = {}
    harness.ratioWindow.configuration = { expression: '=SPY/RSP', auto_ratio: true }
    routeState.path = '/popout/benchmark-list'
    routeState.params = { windowKey: 'benchmark-list' }
    routeState.query = {}
    apiGet.mockReset()
    apiGet.mockResolvedValue([])
    harness.workspace.loadDefault = vi.fn().mockResolvedValue(undefined)
    harness.workspace.marketGroups = { 'us-benchmarks': { members: [] }, 'sp500-sectors': { members: [] } }
    harness.workspace.groupSnapshots = {}
    harness.workspace.breadth = {}
    harness.workspace.breadthHistory = {}
    harness.recent.recent = [{ symbol: 'XLK', name: 'Technology Select Sector SPDR Fund', viewedAt: 2 }]
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
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/instruments/search', { q: 'xl', canonical_only: true }))
    await vi.waitFor(() => expect(wrapper.find('[role="listbox"]').exists()).toBe(true))
    expect(wrapper.findAll('[role="option"]')[0].text()).toContain('XLK')
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'Enter' })
    expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'XLE', instrumentId: 89, group: 'blue' }))
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false)
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
    await wrapper.find('.workstation').trigger('keydown', { key: ' ', shiftKey: true })
    expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'IWM', group: 'blue' }))

    releaseHydration()
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenLastCalledWith(expect.objectContaining({ symbol: 'IWM', group: 'blue' })))
    wrapper.unmount()
  })

  it('exposes an explicit loading state while canonical symbol search is pending', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockImplementation(() => new Promise(() => undefined))
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const input = wrapper.get('input[aria-label="Active symbol"]')
    await input.setValue('zz')
    await vi.waitFor(() => expect(wrapper.find('[role="listbox"]').exists()).toBe(true))
    expect(wrapper.get('[role="listbox"]').attributes('aria-busy')).toBe('true')
    expect(wrapper.get('[role="status"]').text()).toContain('Searching canonical instruments')
    expect(input.attributes('aria-busy')).toBe('true')
    wrapper.unmount()
  })

  it('renders an explicit no-result state without creating a selectable row', async () => {
    routeState.path = '/'
    routeState.params = {}
    apiGet.mockResolvedValue([])
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    const input = wrapper.get('input[aria-label="Active symbol"]')
    await input.setValue('zzzz')
    await vi.waitFor(() => expect(wrapper.get('[role="listbox"] .workstation__symbol-search-message').text()).toContain('No canonical instruments found'))
    expect(wrapper.findAll('[role="option"]')).toHaveLength(0)
    expect(input.attributes('aria-expanded')).toBe('true')
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
    await vi.waitFor(() => expect(wrapper.get('[role="alert"]').text()).toContain('Unable to search canonical instruments'))
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
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/instruments/search', { q: 'xlk', canonical_only: true }))
    await vi.waitFor(() => expect(wrapper.find('[role="listbox"]').exists()).toBe(true))
    await input.trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('[role="listbox"]').exists()).toBe(false)

    await input.setValue('xl')
    await vi.waitFor(() => expect(wrapper.find('[role="listbox"]').exists()).toBe(true))
    await wrapper.get('.workstation__search > button').trigger('click')
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
    await vi.waitFor(() => expect(apiGet).toHaveBeenCalledWith('/instruments/search', { q: 'xlk', canonical_only: true }))
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
    expect(wrapper.get('.workstation__help-popover').attributes('role')).toBe('menu')

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
    await vi.waitFor(() => expect(document.activeElement).toBe(helpMenu.get('[role="menuitem"]').element))
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

  it('traverses the canonical workstation universe with Ctrl+wheel outside editors', async () => {
    harness.workspace.marketGroups = {
      'us-benchmarks': { members: [{ instrument: { symbol: 'SPY' } }, { instrument: { symbol: 'QQQ' } }, { instrument: { symbol: 'DIA' } }] },
      'sp500-sectors': { members: [] },
    }
    routeState.path = '/'
    routeState.params = {}
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
    harness.workspace.publishSymbol.mockClear()

    wrapper.element.dispatchEvent(new WheelEvent('wheel', { ctrlKey: true, deltaY: 1, bubbles: true, cancelable: true }))
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'QQQ', group: 'blue' })))
    wrapper.unmount()
  })

  it('retains Ctrl+wheel traversal when the wheel event omits ctrlKey', async () => {
    harness.workspace.marketGroups = {
      'us-benchmarks': { members: [{ instrument: { symbol: 'SPY' } }, { instrument: { symbol: 'QQQ' } }] },
      'sp500-sectors': { members: [] },
    }
    routeState.path = '/'
    routeState.params = {}
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'SPY' })))
    harness.workspace.publishSymbol.mockClear()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Control' }))
    wrapper.element.dispatchEvent(new WheelEvent('wheel', { deltaY: 1, bubbles: true, cancelable: true }))
    await vi.waitFor(() => expect(harness.workspace.publishSymbol).toHaveBeenCalledWith(expect.objectContaining({ symbol: 'QQQ', group: 'blue' })))
    window.dispatchEvent(new KeyboardEvent('keyup', { key: 'Control' }))
    wrapper.unmount()
  })

  it('coordinates top-down refresh through Vue Query and resumes it after visibility returns', async () => {
    routeState.path = '/'
    routeState.params = {}
    const originalVisibility = document.visibilityState
    const wrapper = mount(WorkstationView, {
      global: { stubs: { WorkstationToolContent: ToolStub, WorkspaceLayoutHost: true } },
    })
    await vi.waitFor(() => expect(harness.workspace.refreshMarketAnalysis).toHaveBeenCalled())
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
    expect(status.attributes('title')).toContain('API GET /market-groups/etf/SPY/industries')
    harness.workspace.error = null
  })
})
