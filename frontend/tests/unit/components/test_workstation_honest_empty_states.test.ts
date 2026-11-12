import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('@/lib/api', () => ({
  api: {
    get: apiGet,
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    put: vi.fn(),
  },
  setQueuedApiRequestPriority: vi.fn(),
}))

import WorkstationToolContent from '@/components/workstation/WorkstationToolContent.vue'
import { usePanelStore } from '@/stores/chart'
import { useWorkspaceStore } from '@/stores/workspace'
import type { WorkspaceWindowState } from '@/stores/workspace'

const ToolWindowShell = defineComponent({
  name: 'ToolWindow',
  props: ['title', 'symbol'],
  emits: ['update:timeframe'],
  setup(_props, { slots }) {
    return () => h('div', { class: 'tool-window-shell' }, [slots.default?.()])
  },
})

const UPlotChartStub = defineComponent({
  name: 'UPlotChart',
  template: '<div class="uplot" />',
})

function toolFixture(instanceKey: string, toolType: string, configuration: Record<string, unknown> = {}): WorkspaceWindowState {
  return {
    id: 91,
    instance_key: instanceKey,
    tool_type: toolType,
    title: instanceKey,
    link_group: 'blue',
    configuration,
    style: {},
    state_schema_version: 1,
    position: 0,
  }
}

function mountTool(tool: WorkspaceWindowState, pinia: ReturnType<typeof createPinia>) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return mount(WorkstationToolContent, {
    props: { tool, activeWindowKey: 'honest-empty-state-test' },
    global: {
      plugins: [pinia, [VueQueryPlugin, { queryClient }]],
      stubs: {
        UPlotChart: UPlotChartStub,
        ChartPlotLibrary: { template: '<div />' },
        ChartTemplateControl: { template: '<div />' },
        DrawingToolbar: { template: '<div />' },
        ToolWindow: ToolWindowShell,
      },
    },
  })
}

describe('honest empty and loading states', () => {
  beforeEach(() => {
    // Never settle: these tests inspect the states before any response arrives.
    apiGet.mockReturnValue(new Promise(() => undefined))
    const pinia = createPinia()
    setActivePinia(pinia)
  })

  afterEach(() => {
    apiGet.mockReset()
  })

  it('shows a plain no-history message instead of a blank chart after an empty load', async () => {
    // The local OHLCV read answers 200 with an empty bar list.
    apiGet.mockImplementation((path: string) => path.includes('/ohlcv/') ? Promise.resolve([]) : new Promise(() => undefined))
    const pinia = createPinia()
    setActivePinia(pinia)
    const chartStore = usePanelStore('honest-empty-chart')
    chartStore.symbol = 'SPY'
    chartStore.timeframe = 'D1'
    const wrapper = mountTool(toolFixture('honest-empty-chart', 'chart', { symbol: 'SPY' }), pinia)

    await vi.waitFor(() => expect(wrapper.text()).toContain('No local D1 price history is available for SPY yet.'))
    expect(wrapper.get('.chart-tool__status').attributes('role')).toBe('status')
    wrapper.unmount()
  })

  it('keeps the loading message, not the no-history message, while the chart is still loading', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const chartStore = usePanelStore('honest-loading-chart')
    chartStore.symbol = 'SPY'
    chartStore.timeframe = 'D1'
    chartStore.bars = []
    chartStore.isLoading = true
    chartStore.error = null
    const wrapper = mountTool(toolFixture('honest-loading-chart', 'chart', { symbol: 'SPY' }), pinia)

    expect(wrapper.text()).toContain('Loading SPY…')
    expect(wrapper.text()).not.toContain('No local D1 price history')
    wrapper.unmount()
  })

  it('aligns the industry header with every row cell, including the proxy column', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const workspaceStore = useWorkspaceStore()
    workspaceStore.constituentETF = 'SPY'
    workspaceStore.etfIndustries = {
      SPY: {
        composition_date: '2026-11-06',
        source_provider: 'test-provider',
        provenance: 'test-provenance',
        classification_coverage: 1,
        exclusions: [],
        industries: [
          { industry: 'Software', resolved_count: 3, constituent_count: 4, classification_systems: ['gics'] },
        ],
      },
    } as unknown as typeof workspaceStore.etfIndustries
    const wrapper = mountTool(toolFixture('industry-list', 'watchlist', { workspace_role: 'industry-universe' }), pinia)

    const header = wrapper.get('.industry-list__header')
    const headerCells = header.findAll(':scope > span')
    expect(headerCells.map(cell => cell.text())).toContain('Proxies')

    const row = wrapper.get('.industry-list__row')
    // The row's classification label is a provenance footnote rather than a grid column.
    const rowCells = row.findAll(':scope > strong, :scope > span')
    expect(rowCells).toHaveLength(headerCells.length)
    expect(rowCells[2]?.text()).toBe('—')
    expect(rowCells[2]?.classes()).toContain('industry-list__proxy-count')
    wrapper.unmount()
  })

  it('shows a loading placeholder for technicals until the request settles, then Unavailable when empty', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const chartStore = usePanelStore('honest-technicals-chart')
    chartStore.symbol = 'SPY'
    chartStore.timeframe = 'D1'
    const workspaceStore = useWorkspaceStore()
    const pending = mountTool(toolFixture('technical-summary', 'technical_summary', { symbol: 'SPY' }), pinia)
    expect(pending.findAll('.metrics b').map(cell => cell.text())).toEqual(['…', '…', '…', '…'])
    pending.unmount()

    workspaceStore.technicals = { SPY: null } as unknown as typeof workspaceStore.technicals
    const settled = mountTool(toolFixture('technical-summary', 'technical_summary', { symbol: 'SPY' }), pinia)
    expect(settled.findAll('.metrics b').map(cell => cell.text())).toContain('Unavailable')
    expect(settled.findAll('.metrics b').map(cell => cell.text())).not.toContain('…')
    settled.unmount()
  })

  it('shows the selected ETF holdings loading state instead of the empty-selection prompt', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const chartStore = usePanelStore('honest-constituents-chart')
    chartStore.symbol = 'SPY'
    const workspaceStore = useWorkspaceStore()
    workspaceStore.constituentETF = 'SPY'
    workspaceStore.etfHoldings = {}
    const wrapper = mountTool(toolFixture('constituent-list', 'watchlist', { workspace_role: 'constituent-universe' }), pinia)

    expect(wrapper.get('.constituent-tool__empty-context').text()).toBe('Loading SPY holdings…')
    wrapper.unmount()
  })
})
