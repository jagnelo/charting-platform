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
import { usePanelStore } from '@/stores/chart'
import { useWorkspaceStore } from '@/stores/workspace'
import type { WorkspaceWindowState } from '@/stores/workspace'

const ToolWindowShell = defineComponent({
  name: 'ToolWindow',
  setup(_, { slots }) {
    return () => h('div', { class: 'tool-window-shell' }, slots.default?.())
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

describe('WorkstationToolContent missing chart history entrypoint', () => {
  beforeEach(() => {
    vi.resetAllMocks()
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
})
