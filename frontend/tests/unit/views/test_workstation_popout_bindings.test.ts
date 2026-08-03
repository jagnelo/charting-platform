import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
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
    workspace: { is_default: false, name: 'US Top Down', tabs: [tab], settings: { factory_id: 'us-top-down' } },
    activeTabKey: 'us-top-down',
    activeTab: tab,
    linkedSymbol: 'SPY',
    linkedTimeframe: 'D1',
    isPersistenceLeader: true,
    loading: false,
    error: null,
    constituentETF: null,
    marketGroups: { 'us-benchmarks': { members: [] }, 'sp500-sectors': { members: [] } },
    marketAnalysisRefreshing: false,
    connect: vi.fn(),
    loadDefault: vi.fn().mockResolvedValue(undefined),
    refreshMarketAnalysis: vi.fn().mockResolvedValue(undefined),
    publishSymbol: vi.fn(),
    publishTimeframe: vi.fn(),
    symbolForLinkGroup: vi.fn(() => 'XLK'),
    selectToolSymbol: vi.fn(),
    loadETFHoldings: vi.fn().mockResolvedValue(undefined),
    loadETFIndustries: vi.fn().mockResolvedValue(undefined),
    loadTechnical: vi.fn().mockResolvedValue(undefined),
    scheduleSnapshot: vi.fn(),
    updateToolLinkGroup: vi.fn(),
    updateToolTimeframe: vi.fn(),
    updateToolTimeframeLinkGroup: vi.fn(),
    selectIndustryProxy: vi.fn(),
    closeTool: vi.fn(),
    cloneActiveTab: vi.fn(),
    resetFactoryWorkspace: vi.fn(),
    openTool: vi.fn(),
    isEditorTarget: vi.fn(() => false),
  }
  return { workspace, popoutWindow, chartWindow }
})

vi.mock('@/stores/workspace', () => ({
  OPENABLE_WORKSTATION_TOOLS: [],
  useWorkspaceStore: () => harness.workspace,
}))
vi.mock('@/stores/chart', () => ({
  useChartStore: () => ({ symbol: 'SPY', timeframe: 'D1', barType: 'candles', bars: [], isLoading: false, isFetchingHistory: false, error: null, loadBars: vi.fn().mockResolvedValue(undefined) }),
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ logout: vi.fn().mockResolvedValue(undefined) }) }))
vi.mock('@/lib/instruments', () => ({ ensureKnownInstrumentSymbol: vi.fn().mockResolvedValue('SPY') }))
vi.mock('@/components/workstation/WorkspaceLayoutHost.vue', () => ({ default: defineComponent({ template: '<div />' }) }))
vi.mock('golden-layout', () => ({}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/popout/benchmark-list', params: { windowKey: 'benchmark-list' }, query: {} }),
  useRouter: () => ({ resolve: vi.fn(), push: vi.fn() }),
}))

import WorkstationView from '@/views/WorkstationView.vue'

const ToolStub = defineComponent({
  emits: ['conditionFilterMode', 'pinnedBooleanKeys', 'columnGroups', 'stackedColumnKeys', 'configuration', 'selectProxy', 'compare', 'row-action'],
  template: `<div class="tool-stub">
    <button class="mode" @click="$emit('conditionFilterMode', 'benchmark-list', 'active')">mode</button>
    <button class="pin" @click="$emit('pinnedBooleanKeys', 'benchmark-list', ['above_ma50'])">pin</button>
    <button class="groups" @click="$emit('columnGroups', 'benchmark-list', { rsi14: 'Momentum' })">groups</button>
    <button class="stack" @click="$emit('stackedColumnKeys', 'benchmark-list', ['rsi14'])">stack</button>
    <button class="configuration" @click="$emit('configuration', 'benchmark-list', { column_keys: ['symbol'] })">configuration</button>
    <button class="proxy" @click="$emit('selectProxy', 'XLK')">proxy</button>
    <button class="compare" @click="$emit('compare', ['SPY', 'XLK', 'XLE'])">compare</button>
    <button class="copy" @click="$emit('row-action', 'copy', { symbol: 'XLK', instrumentId: 1 })">copy</button>
  </div>`,
})

describe('WorkstationView pop-out bindings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    harness.popoutWindow.configuration = {}
    harness.chartWindow.configuration = {}
  })

  it('forwards watchlist persistence and proxy events from a floated tool to the shell', async () => {
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
    await wrapper.find('.compare').trigger('click')
    await wrapper.find('.copy').trigger('click')

    expect(harness.popoutWindow.configuration).toMatchObject({
      condition_filter_mode: 'active',
      pinned_boolean_keys: ['above_ma50'],
      column_groups: { rsi14: 'Momentum' },
      stacked_column_keys: ['rsi14'],
      column_keys: ['symbol'],
    })
    expect(harness.chartWindow.configuration).toMatchObject({ comparison_symbols: ['XLK', 'XLE'] })
    expect(harness.workspace.error).toBe('Copied XLK')
    expect(harness.workspace.selectIndustryProxy).toHaveBeenCalledWith('XLK')
    expect(harness.workspace.scheduleSnapshot).toHaveBeenCalled()
    expect(harness.workspace.publishSymbol).not.toHaveBeenCalled()
    expect(harness.workspace.symbolForLinkGroup).toHaveBeenCalledWith('blue', null)
  })
})
