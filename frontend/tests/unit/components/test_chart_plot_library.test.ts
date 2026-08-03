import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ChartPlotLibrary from '@/components/workstation/ChartPlotLibrary.vue'
import { usePanelStore } from '@/stores/chart'
import { useWorkspaceStore } from '@/stores/workspace'
import { CHART_PLOT_DRAG_MIME } from '@/lib/workstation/plotDrag'

const apiMock = vi.hoisted(() => ({ put: vi.fn().mockResolvedValue({}), post: vi.fn().mockResolvedValue({}) }))
vi.mock('@/lib/api', () => ({ api: apiMock }))

describe('ChartPlotLibrary', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiMock.put.mockReset().mockResolvedValue({})
    apiMock.post.mockReset().mockResolvedValue({})
  })

  it('manages indicator plots without losing their serializable configuration', async () => {
    const chart = usePanelStore('plot-library-test')
    chart.setIndicators([{ type: 'sma', params: { period: 20 }, style: { color: '#ff0000', lineWidth: 1 }, pane: 'main' }])
    const wrapper = mount(ChartPlotLibrary, { props: { sourceWindowKey: 'source', linkGroup: 'blue' }, global: { provide: { panelId: 'plot-library-test' } } })
    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    await wrapper.get('[aria-label="Add indicator plot"]').setValue('ema')
    expect(chart.indicators).toHaveLength(2)

    await wrapper.get('[aria-label="Hide SMA(20)"]').trigger('click')
    expect(chart.indicators[0].hidden).toBe(true)
    await wrapper.get('[aria-label="Duplicate EMA(50)"]').trigger('click')
    expect(chart.indicators).toHaveLength(3)
    await wrapper.get('[aria-label="Move EMA(50) up"]').trigger('click')
    expect(chart.indicators[0].type).toBe('ema')
    await wrapper.findAll('[aria-label="Delete EMA(50)"]')[0].trigger('click')
    expect(chart.indicators).toHaveLength(2)
  })

  it('writes a versioned serializable payload when a plot is dragged', async () => {
    const chart = usePanelStore('plot-drag-test')
    chart.setIndicators([{ type: 'rsi', params: { period: 14 }, style: { color: '#ff0000', lineWidth: 1 }, pane: 'separate' }])
    const values = new Map<string, string>()
    const dataTransfer = {
      effectAllowed: '',
      setData: (type: string, value: string) => values.set(type, value),
      getData: (type: string) => values.get(type) ?? '',
    } as unknown as DataTransfer
    const wrapper = mount(ChartPlotLibrary, { props: { sourceWindowKey: 'source', linkGroup: 'blue' }, global: { provide: { panelId: 'plot-drag-test' } } })

    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    await wrapper.get('li').trigger('dragstart', { dataTransfer })

    expect(values.has(CHART_PLOT_DRAG_MIME)).toBe(true)
    expect(JSON.parse(values.get(CHART_PLOT_DRAG_MIME) ?? '')).toMatchObject({
      version: 1,
      kind: 'chart-plot',
      indicator: { type: 'rsi', params: { period: 14 }, timeframe: 'D1', sourceWindowKey: 'source' },
    })
    expect(dataTransfer.effectAllowed).toBe('copy')
  })

  it('copies a plot only to chart windows in its linked symbol group', async () => {
    const workspace = useWorkspaceStore()
    workspace.workspace = {
      id: 1, user_id: 1, name: 'Test', is_default: true, position: 0, revision: 1, schema_version: 1, settings: {},
      tabs: [{ id: 1, stable_key: 'test', name: 'Test', position: 0, active_window_key: 'source', layout_config: {}, windows: [
        { id: 1, instance_key: 'source', tool_type: 'chart', title: 'Source', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 },
        { id: 2, instance_key: 'linked', tool_type: 'chart', title: 'Linked', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 1 },
        { id: 3, instance_key: 'isolated', tool_type: 'chart', title: 'Isolated', link_group: 'grey', configuration: {}, style: {}, state_schema_version: 1, position: 2 },
      ] }],
    }
    workspace.activeTabKey = 'test'
    const scheduleSnapshot = vi.spyOn(workspace, 'scheduleSnapshot').mockImplementation(() => {})
    usePanelStore('linked-copy-test').setIndicators([{ type: 'sma', params: { period: 20 }, style: { color: '#ff0000', lineWidth: 1 }, pane: 'main' }])
    const wrapper = mount(ChartPlotLibrary, { props: { sourceWindowKey: 'source', linkGroup: 'blue' }, global: { provide: { panelId: 'linked-copy-test' } } })

    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    await wrapper.get('[aria-label="Copy SMA(20) to linked charts"]').trigger('click')

    expect(workspace.activeTab?.windows[1].configuration.indicators).toEqual([{ type: 'sma', params: { period: 20 }, style: { color: '#ff0000', lineWidth: 1 }, pane: 'main' }])
    expect(workspace.activeTab?.windows[2].configuration.indicators).toBeUndefined()
    expect(scheduleSnapshot).toHaveBeenCalledOnce()
  })

  it('copies a plot to an explicitly selected isolated chart target', async () => {
    const workspace = useWorkspaceStore()
    workspace.workspace = {
      id: 1, user_id: 1, name: 'Test', is_default: true, position: 0, revision: 1, schema_version: 1, settings: {},
      tabs: [{ id: 1, stable_key: 'test', name: 'Test', position: 0, active_window_key: 'source', layout_config: {}, windows: [
        { id: 1, instance_key: 'source', tool_type: 'chart', title: 'Source', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 },
        { id: 2, instance_key: 'isolated', tool_type: 'chart', title: 'Isolated', link_group: 'grey', configuration: {}, style: {}, state_schema_version: 1, position: 1 },
      ] }],
    }
    workspace.activeTabKey = 'test'
    vi.spyOn(workspace, 'scheduleSnapshot').mockImplementation(() => {})
    usePanelStore('explicit-copy-test').setIndicators([{ type: 'sma', params: { period: 20 }, style: { color: '#ff0000', lineWidth: 1 }, pane: 'main' }])
    const wrapper = mount(ChartPlotLibrary, { props: { sourceWindowKey: 'source', linkGroup: 'blue' }, global: { provide: { panelId: 'explicit-copy-test' } } })

    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    await wrapper.get('[aria-label="Copy plot target"]').setValue('isolated')
    await wrapper.get('[aria-label="Copy SMA(20) to selected chart target"]').trigger('click')

    expect(workspace.activeTab?.windows[1].configuration.indicators).toEqual([{ type: 'sma', params: { period: 20 }, style: { color: '#ff0000', lineWidth: 1 }, pane: 'main' }])
  })

  it('promotes a plot into a reusable condition and EasyScan', async () => {
    const chart = usePanelStore('promotion-test')
    chart.setIndicators([{ type: 'rsi', params: { period: 14 }, style: { color: '#ff0000', lineWidth: 1 }, pane: 'separate' }])
    const wrapper = mount(ChartPlotLibrary, { props: { sourceWindowKey: 'source', linkGroup: 'blue' }, global: { provide: { panelId: 'promotion-test' } } })
    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    await wrapper.get('[aria-label="Promote RSI(14)"]').trigger('click')
    await wrapper.get('[aria-label="Plot promotion target"]').setValue('scan')
    await wrapper.get('[aria-label="Plot promotion threshold"]').setValue('70')
    await wrapper.get('[aria-label="Plot promotion name"]').setValue('Overbought RSI')
    await wrapper.get('.chart-plots__promotion button').trigger('click')
    await vi.waitFor(() => expect(wrapper.find('[role="status"]').exists()).toBe(true))
    expect(apiMock.put).toHaveBeenCalledWith('/workspaces/library/conditions/overbought-rsi', expect.objectContaining({ name: 'Overbought RSI' }))
    expect(apiMock.post).toHaveBeenCalledWith('/screeners/from-condition/overbought-rsi', expect.objectContaining({ name: 'Overbought RSI Scan', timeframe: 'D1' }))
    expect(wrapper.get('[role="status"]').text()).toContain('EasyScan')
  })

  it('promotes a plot into an indicator alert for the active canonical instrument', async () => {
    const chart = usePanelStore('alert-promotion-test')
    chart.instrument = { id: 42 } as any
    chart.setIndicators([{ type: 'ema', params: { period: 20 }, style: { color: '#ff0000', lineWidth: 1 }, pane: 'main' }])
    const wrapper = mount(ChartPlotLibrary, { props: { sourceWindowKey: 'source', linkGroup: 'blue' }, global: { provide: { panelId: 'alert-promotion-test' } } })
    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    await wrapper.get('[aria-label="Promote EMA(20)"]').trigger('click')
    await wrapper.get('[aria-label="Plot promotion target"]').setValue('alert')
    await wrapper.get('[aria-label="Plot promotion threshold"]').setValue('100')
    await wrapper.get('[aria-label="Plot promotion name"]').setValue('EMA alert')
    await wrapper.get('.chart-plots__promotion button').trigger('click')
    await vi.waitFor(() => expect(wrapper.find('[role="status"]').exists()).toBe(true))
    expect(apiMock.post).toHaveBeenCalledWith('/alerts/indicator', expect.objectContaining({ instrument_id: 42, indicator_a_type: 'ema', threshold_value: 100 }))
    expect(wrapper.get('[role="status"]').text()).toContain('indicator alert')
  })

  it('promotes a plot into a selected watchlist filter and persists its active condition', async () => {
    const workspace = useWorkspaceStore()
    workspace.workspace = {
      id: 1, user_id: 1, name: 'Test', is_default: true, position: 0, revision: 1, schema_version: 1, settings: {},
      tabs: [{ id: 1, stable_key: 'test', name: 'Test', position: 0, active_window_key: 'source', layout_config: {}, windows: [
        { id: 1, instance_key: 'source', tool_type: 'chart', title: 'Source', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 },
        { id: 2, instance_key: 'target-list', tool_type: 'watchlist', title: 'Momentum', link_group: 'grey', configuration: {}, style: {}, state_schema_version: 1, position: 1 },
      ] }],
    }
    workspace.activeTabKey = 'test'
    const scheduleSnapshot = vi.spyOn(workspace, 'scheduleSnapshot').mockImplementation(() => {})
    apiMock.post.mockImplementation((path: string) => path.startsWith('/screeners/from-condition/') ? Promise.resolve({ id: 77 }) : Promise.resolve({}))
    const chart = usePanelStore('filter-promotion-test')
    chart.setIndicators([{ type: 'sma', params: { period: 20 }, style: { color: '#ff0000', lineWidth: 1 }, pane: 'main' }])
    const wrapper = mount(ChartPlotLibrary, { props: { sourceWindowKey: 'source', linkGroup: 'blue' }, global: { provide: { panelId: 'filter-promotion-test' } } })

    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    await wrapper.get('[aria-label="Promote SMA(20)"]').trigger('click')
    await wrapper.get('[aria-label="Plot promotion target"]').setValue('filter')
    await wrapper.get('[aria-label="Plot promotion threshold"]').setValue('50')
    await wrapper.get('[aria-label="Plot promotion name"]').setValue('SMA filter')
    await wrapper.get('.chart-plots__promotion button').trigger('click')
    await vi.waitFor(() => expect(wrapper.find('[role="status"]').exists()).toBe(true))

    expect(workspace.activeTab?.windows[1].configuration).toMatchObject({ condition_screener_id: 77, condition_filter_mode: 'active' })
    expect(scheduleSnapshot).toHaveBeenCalled()
    expect(wrapper.get('[role="status"]').text()).toContain('Momentum filter')
  })
})
