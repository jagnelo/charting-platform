import { flushPromises, mount as vueMount } from '@vue/test-utils'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ChartPlotLibrary from '@/components/workstation/ChartPlotLibrary.vue'
import { usePanelStore } from '@/stores/chart'
import { useWorkspaceStore } from '@/stores/workspace'
import { CHART_PLOT_DRAG_MIME } from '@/lib/workstation/plotDrag'

function mount(component: typeof ChartPlotLibrary, options: Record<string, any> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return vueMount(component, { ...options, global: { ...(options.global ?? {}), plugins: [[VueQueryPlugin, { queryClient }], ...((options.global?.plugins as any[]) ?? [])] } })
}

const apiMock = vi.hoisted(() => ({ get: vi.fn().mockResolvedValue([]), put: vi.fn().mockResolvedValue({}), post: vi.fn().mockResolvedValue({}) }))
vi.mock('@/lib/api', () => ({ api: apiMock }))

describe('ChartPlotLibrary', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiMock.get.mockReset().mockResolvedValue([])
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
    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')

    await wrapper.get('[aria-label="Hide SMA(20)"]').trigger('click')
    expect(chart.indicators[0].hidden).toBe(true)
    await wrapper.get('[aria-label="Duplicate EMA(50)"]').trigger('click')
    expect(chart.indicators).toHaveLength(3)
    await wrapper.get('[aria-label="Move EMA(50) up"]').trigger('click')
    expect(chart.indicators[0].type).toBe('ema')
    await wrapper.findAll('[aria-label="Delete EMA(50)"]')[0].trigger('click')
    expect(chart.indicators).toHaveLength(2)
  })

  it('opens from the keyboard, focuses the first plot control, and restores focus on Escape', async () => {
    const wrapper = mount(ChartPlotLibrary, { props: { sourceWindowKey: 'source', linkGroup: 'blue' }, global: { provide: { panelId: 'plot-library-keyboard-test' } }, attachTo: document.body })
    const trigger = wrapper.get('button[aria-label="Chart plot library"]')
    await trigger.trigger('keydown', { key: 'ArrowDown' })
    expect(wrapper.get('[role="menu"]').exists()).toBe(true)
    expect(document.activeElement).toBe(wrapper.get('[aria-label="Add indicator plot"]').element)
    await wrapper.get('[role="menu"]').trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
    wrapper.unmount()
  })

  it('closes through the header control and restores trigger focus', async () => {
    const wrapper = mount(ChartPlotLibrary, { attachTo: document.body, props: { sourceWindowKey: 'source', linkGroup: 'blue' }, global: { provide: { panelId: 'plot-library-close-test' } } })
    const trigger = wrapper.get('button[aria-label="Chart plot library"]')
    await trigger.trigger('click')
    await wrapper.get('button[aria-label="Close chart plot library"]').trigger('click')
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
    wrapper.unmount()
  })

  it('clamps the menu to a narrow viewport and removes the resize listener on close', async () => {
    const addSpy = vi.spyOn(window, 'addEventListener')
    const removeSpy = vi.spyOn(window, 'removeEventListener')
    vi.stubGlobal('innerWidth', 220)
    const wrapper = mount(ChartPlotLibrary, { props: { sourceWindowKey: 'source', linkGroup: 'blue' }, global: { provide: { panelId: 'plot-library-viewport-test' } } })
    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    await flushPromises()
    const menu = wrapper.get('[role="menu"]').element as HTMLElement
    expect(menu.style.left).toBe('8px')
    expect(menu.style.width).toBe('204px')
    expect(addSpy).toHaveBeenCalledWith('resize', expect.any(Function))
    await wrapper.get('button[aria-label="Close chart plot library"]').trigger('click')
    expect(removeSpy).toHaveBeenCalledWith('resize', expect.any(Function))
    wrapper.unmount()
    vi.unstubAllGlobals()
    addSpy.mockRestore()
    removeSpy.mockRestore()
  })

  it('opens above a bottom-edge trigger and removes scroll listeners on close', async () => {
    const addSpy = vi.spyOn(window, 'addEventListener')
    const removeSpy = vi.spyOn(window, 'removeEventListener')
    vi.stubGlobal('innerWidth', 390)
    vi.stubGlobal('innerHeight', 180)
    const wrapper = mount(ChartPlotLibrary, { attachTo: document.body, props: { sourceWindowKey: 'source', linkGroup: 'blue' }, global: { provide: { panelId: 'plot-library-bottom-test' } } })
    const trigger = wrapper.get('button[aria-label="Chart plot library"]').element as HTMLButtonElement
    vi.spyOn(trigger, 'getBoundingClientRect').mockReturnValue({
      x: 120, y: 156, top: 156, left: 120, right: 220, bottom: 174, width: 100, height: 18,
      toJSON: () => ({}),
    })
    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    await flushPromises()
    const menu = wrapper.get('[role="menu"]').element as HTMLElement
    expect(menu.style.top).toBe('8px')
    expect(menu.style.maxHeight).toBe('164px')
    expect(addSpy).toHaveBeenCalledWith('scroll', expect.any(Function), true)
    await wrapper.get('button[aria-label="Close chart plot library"]').trigger('click')
    expect(removeSpy).toHaveBeenCalledWith('scroll', expect.any(Function), true)
    wrapper.unmount()
    vi.unstubAllGlobals()
    addSpy.mockRestore()
    removeSpy.mockRestore()
  })

  it('persists a newly added plot immediately for drag-to-tool handoffs', async () => {
    const chart = usePanelStore('plot-library-immediate-save-test')
    chart.instrument = { id: 42 } as any
    const wrapper = mount(ChartPlotLibrary, { props: { sourceWindowKey: 'source', linkGroup: 'blue' }, global: { provide: { panelId: 'plot-library-immediate-save-test' } } })
    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    await wrapper.get('[aria-label="Add indicator plot"]').setValue('rsi')
    await flushPromises()

    expect(apiMock.put).toHaveBeenCalledWith('/instrument-indicators/42', { indicators: chart.indicators })
  })

  it('closes the fixed plot menu after inserting an indicator so chart gestures are not intercepted', async () => {
    const chart = usePanelStore('plot-library-close-after-add-test')
    const wrapper = mount(ChartPlotLibrary, { props: { sourceWindowKey: 'source', linkGroup: 'blue' }, global: { provide: { panelId: 'plot-library-close-after-add-test' } } })
    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    await wrapper.get('[aria-label="Add indicator plot"]').setValue('rsi')
    await flushPromises()
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
    expect(chart.indicators).toHaveLength(1)
  })

  it('waits for the instrument indicator save before closing after insertion', async () => {
    const chart = usePanelStore('plot-library-await-save-test')
    chart.instrument = { id: 42 } as any
    let release!: () => void
    apiMock.put.mockImplementationOnce(() => new Promise(resolve => { release = () => resolve({}) }))
    const wrapper = mount(ChartPlotLibrary, { props: { sourceWindowKey: 'source', linkGroup: 'blue' }, global: { provide: { panelId: 'plot-library-await-save-test' } } })
    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    const insertion = wrapper.get('[aria-label="Add indicator plot"]').setValue('rsi')
    await Promise.resolve()
    expect(wrapper.find('[role="menu"]').exists()).toBe(true)
    release()
    await insertion
    await flushPromises()
    expect(apiMock.put).toHaveBeenCalledWith('/instrument-indicators/42', { indicators: chart.indicators })
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
  })

  it('loads and adds a typed Python plot asset without executing frontend code', async () => {
    apiMock.get.mockResolvedValue([{ kind: 'plot', name: 'Breadth plot', versions: [{ id: 91, version_number: 2 }] }])
    const chart = usePanelStore('python-plot-library-test')
    const wrapper = mount(ChartPlotLibrary, { props: { sourceWindowKey: 'source', linkGroup: 'blue' }, global: { provide: { panelId: 'python-plot-library-test' } } })
    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    await wrapper.findAll('button').find(button => button.text() === 'Load Python plots')!.trigger('click')
    await flushPromises()
    await wrapper.get('[aria-label="Python plot asset"]').setValue('91')
    await wrapper.findAll('.chart-plots__python button').find(button => button.text() === 'Add')!.trigger('click')
    expect(wrapper.emitted('update:python-plots')?.at(-1)).toEqual([[{ code_version_id: 91, name: 'Breadth plot v2', color: '#ffb74d', timeframe: chart.timeframe, instance_key: expect.any(String) }]])
    expect(apiMock.get).toHaveBeenCalledWith('/code/assets')
  })

  it('loads retained EasyScan history and adds a reusable numeric scan plot', async () => {
    apiMock.get.mockImplementation((path: string) => {
      if (path === '/screeners') return Promise.resolve([{ id: 17, name: 'Breadth scan' }])
      if (path === '/screeners/17/plot') return Promise.resolve({ points: [{ timestamp: '2026-01-01T00:00:00Z', value: 42 }] })
      return Promise.resolve([])
    })
    const wrapper = mount(ChartPlotLibrary, { props: { sourceWindowKey: 'source', linkGroup: 'blue' }, global: { provide: { panelId: 'scan-plot-library-test' } } })
    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    await wrapper.findAll('button').find(button => button.text() === 'Load EasyScan plots')!.trigger('click')
    await flushPromises()
    await wrapper.get('[aria-label="EasyScan plot asset"]').setValue('17:percentage')
    await wrapper.findAll('.chart-plots__scan button').find(button => button.text() === 'Add')!.trigger('click')
    expect(wrapper.emitted('update:scan-plots')?.at(-1)).toEqual([[{ screener_id: 17, name: 'Breadth scan', metric: 'percentage', color: '#4dd0e1', instance_key: expect.any(String) }]])
    expect(apiMock.get).toHaveBeenCalledWith('/screeners/17/plot', { metric: 'percentage' })
  })

  it('keeps scan plots serializable and supports visibility and removal', async () => {
    const wrapper = mount(ChartPlotLibrary, {
      props: { sourceWindowKey: 'source', linkGroup: 'blue', scanPlots: [{ screener_id: 17, name: 'Breadth scan', metric: 'count', color: '#4dd0e1', instance_key: 'scan-a' }] },
      global: { provide: { panelId: 'scan-plot-management-test' } },
    })
    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    await wrapper.get('[aria-label="Hide Breadth scan"]').trigger('click')
    expect(wrapper.emitted('update:scan-plots')?.at(-1)).toEqual([[expect.objectContaining({ screener_id: 17, hidden: true })]])
    await wrapper.get('[aria-label="Remove Breadth scan"]').trigger('click')
    expect(wrapper.emitted('update:scan-plots')?.at(-1)).toEqual([[]])
  })

  it('renders reusable Python plots in the library and removes them through the shared configuration contract', async () => {
    const wrapper = mount(ChartPlotLibrary, {
      props: { sourceWindowKey: 'source', linkGroup: 'blue', pythonPlots: [{ code_version_id: 91, name: 'Breadth plot v2', timeframe: 'D1' }] },
      global: { provide: { panelId: 'python-plot-render-test' } },
    })
    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    expect(wrapper.get('.chart-plots__python-item').text()).toContain('Breadth plot v2')
    await wrapper.get('[aria-label="Remove Breadth plot v2"]').trigger('click')
    expect(wrapper.emitted('update:python-plots')?.at(-1)).toEqual([[]])
  })

  it('manages Python plot visibility, order, duplication, and drag payloads', async () => {
    const values = new Map<string, string>()
    const dataTransfer = {
      effectAllowed: '',
      setData: (type: string, value: string) => values.set(type, value),
      getData: (type: string) => values.get(type) ?? '',
    } as unknown as DataTransfer
    const wrapper = mount(ChartPlotLibrary, {
      props: { sourceWindowKey: 'source', linkGroup: 'blue', pythonPlots: [
        { code_version_id: 91, name: 'Breadth plot', color: '#4dd0e1', timeframe: 'D1', instance_key: 'breadth-a' },
        { code_version_id: 92, name: 'Volatility plot', color: '#ffb74d', timeframe: 'W1', instance_key: 'volatility-a' },
      ] },
      global: { provide: { panelId: 'python-plot-management-test' } },
    })
    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    await wrapper.get('[aria-label="Hide Breadth plot"]').trigger('click')
    expect((wrapper.emitted('update:python-plots')?.at(-1)?.[0] as any[])[0]).toMatchObject({ code_version_id: 91, hidden: true })
    await wrapper.get('[aria-label="Move Volatility plot up"]').trigger('click')
    expect(wrapper.emitted('update:python-plots')?.at(-1)?.[0]).toMatchObject([{ code_version_id: 92 }, { code_version_id: 91 }])
    await wrapper.setProps({ pythonPlots: [
      { code_version_id: 92, name: 'Volatility plot', color: '#ffb74d', timeframe: 'W1', instance_key: 'volatility-a' },
      { code_version_id: 91, name: 'Breadth plot', color: '#4dd0e1', timeframe: 'D1', instance_key: 'breadth-a', hidden: true },
    ] })
    await wrapper.get('[aria-label="Duplicate Volatility plot"]').trigger('click')
    expect((wrapper.emitted('update:python-plots')?.at(-1)?.[0] as any[])).toHaveLength(3)
    await wrapper.findAll('.chart-plots__python-item')[0].trigger('dragstart', { dataTransfer })
    expect(JSON.parse(values.get('application/x-charting-platform-plot') ?? '')).toMatchObject({ kind: 'python-plot', python: { codeVersionId: 92, timeframe: 'W1' } })
  })

  it('copies a Python plot into an explicit watchlist target', async () => {
    const workspace = useWorkspaceStore()
    workspace.workspace = {
      id: 1, user_id: 1, name: 'Test', is_default: true, position: 0, revision: 1, schema_version: 1, settings: {},
      tabs: [{ id: 1, stable_key: 'test', name: 'Test', position: 0, active_window_key: 'source', layout_config: {}, windows: [
        { id: 1, instance_key: 'source', tool_type: 'chart', title: 'Source', link_group: 'blue', configuration: {}, style: {}, state_schema_version: 1, position: 0 },
        { id: 2, instance_key: 'target-list', tool_type: 'watchlist', title: 'Momentum', link_group: 'grey', configuration: {}, style: {}, state_schema_version: 1, position: 1 },
      ] }],
    }
    workspace.activeTabKey = 'test'
    vi.spyOn(workspace, 'scheduleSnapshot').mockImplementation(() => {})
    const wrapper = mount(ChartPlotLibrary, {
      props: { sourceWindowKey: 'source', linkGroup: 'blue', pythonPlots: [{ code_version_id: 91, name: 'Breadth plot', timeframe: 'D1', instance_key: 'breadth-a' }] },
      global: { provide: { panelId: 'python-plot-target-test' } },
    })
    await wrapper.get('button[aria-label="Chart plot library"]').trigger('click')
    await wrapper.get('[aria-label="Copy plot target"]').setValue('target-list')
    await wrapper.get('[aria-label="Copy Breadth plot to selected chart target"]').trigger('click')
    expect(workspace.activeTab?.windows[1].configuration.python_columns).toEqual([{ code_version_id: 91, name: 'Breadth plot', timeframe: 'D1' }])
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
